"""iter_019 stage 실행기 (qa_run.py 패턴 재사용): worker 수와 GPU 수 분리, 허용 GPU·메모리 여유·완료 검증·자식 종료 코드 강제.

사용: python -m rsna_diag.mi19_run --requests R --out-dir D --protocol P --workers N --peak-gb G [--gpus 0,1]
"""
import argparse
import glob
import json
import os
import signal
import subprocess
import sys
import time

from . import generate, mi19_gen, mi19_protocol, mi19_requests as Q, queue_lock

MIB_PER_GIB = 1024


class GpuError(RuntimeError):
    pass


def atomic_json(obj, path):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def allowed_gpus():
    raw = os.environ.get("CUDA_VISIBLE_DEVICES")
    if not raw:
        raise GpuError("CUDA_VISIBLE_DEVICES not set (allowed GPU set unknown)")
    try:
        return [int(x) for x in raw.split(",")]
    except ValueError:
        raise GpuError(f"non-integer CUDA_VISIBLE_DEVICES {raw!r}")


def query_gpus(idx):
    r = subprocess.run(["nvidia-smi", "--query-gpu=index,uuid,memory.used,memory.total", "--format=csv,noheader,nounits"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise GpuError(f"nvidia-smi failed rc={r.returncode}: {r.stderr[:200]}")
    rows = {}
    for ln in r.stdout.strip().splitlines():
        i, u, mu, mt = [x.strip() for x in ln.split(",")]
        rows[int(i)] = {"uuid": u, "used_mib": int(mu), "total_mib": int(mt)}
    missing = [i for i in idx if i not in rows]
    if missing:
        raise GpuError(f"gpus {missing} not reported by nvidia-smi")
    return {i: rows[i] for i in idx}


def plan_gpus(gpus, workers, peak_gb, allowed, snapshot):
    if not gpus or not set(gpus) <= set(allowed):
        raise GpuError(f"gpus {gpus} not within allowed {allowed}")
    assign = [(k, gpus[k % len(gpus)]) for k in range(workers)]
    for g in gpus:
        n = sum(1 for _, x in assign if x == g)
        need = n * (peak_gb + 2.0) * MIB_PER_GIB
        free = snapshot[g]["total_mib"] - snapshot[g]["used_mib"]
        if n and need > free:
            raise GpuError(f"gpu {g}: {n} workers x ({peak_gb}+2) GiB = {need:.0f} MiB > free {free} MiB")
    return assign


def live_workers(out_dir):
    live = []
    for f in sorted(glob.glob(os.path.join(out_dir, "worker*.lock"))):
        fd = os.open(f, os.O_RDWR)
        try:
            import fcntl
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                live.append((f, queue_lock._read(fd)))
                continue
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
    return live


def stop_children(procs, grace=60.0):
    for p in procs:
        if p.poll() is None:
            p.terminate()
    t0 = time.time()
    while time.time() - t0 < grace and any(p.poll() is None for p in procs):
        time.sleep(0.5)
    for p in procs:
        if p.poll() is None:
            p.kill()
    for p in procs:
        p.wait()
    return [{"pid": p.pid, "returncode": p.returncode} for p in procs]


def verify_job(out_dir, rows, cfg, pdig):
    mi19_gen.check_inputs(rows)
    files = {f: mi19_gen.read_strict(f) for f in sorted(glob.glob(os.path.join(out_dir, "gen_worker*.jsonl")))}
    cache = {}
    px = lambda p: cache.setdefault(p, generate.load_image(p)[2])
    done = mi19_gen.validate_records(files, rows, cfg, pdig, px)
    missing = [r["request_id"] for r in rows if r["request_id"] not in done]
    return done, missing


class _Term(BaseException):
    pass


def _on_term(signum, frame):
    raise _Term(f"signal {signum}")


class _Args:
    def __init__(self, **kw):
        self.requests = kw["requests"]
        self.out_dir = kw["out_dir"]
        self.protocol = kw["protocol"]
        self.workers = kw["workers"]
        self.gpus = kw.get("gpus")
        self.peak_gb = kw["peak_gb"]
        self.max_requests = kw.get("max_requests")
        self.time_limit = kw.get("time_limit")
        self.repair_tail = kw.get("repair_tail", False)
        self.poll_s = kw.get("poll_s", 15.0)


def main_run(**kwargs):
    """프로그램적 호출(파이프라인 오케스트레이터용). returns exit code (0=success)."""
    a = _Args(**kwargs)
    try:
        return run_stage(a)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1


def main():
    signal.signal(signal.SIGTERM, _on_term)
    ap = argparse.ArgumentParser()
    ap.add_argument("--requests", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--workers", type=int, required=True)
    ap.add_argument("--gpus", default=None)
    ap.add_argument("--peak-gb", type=float, required=True)
    ap.add_argument("--max-requests", type=int, default=None)
    ap.add_argument("--time-limit", type=float, default=None)
    ap.add_argument("--repair-tail", action="store_true")
    ap.add_argument("--poll-s", type=float, default=15.0)
    a = ap.parse_args()
    sys.exit(run_stage(a))


def run_stage(a):
    # SIGTERM 처리를 run_stage 자체에 건다: main()의 CLI 진입 경로뿐 아니라 mi19_pipeline처럼
    # main_run()을 같은 프로세스에서 직접 호출하는 경로에서도 부모가 죽을 때 자식을 정리한다.
    prev_handler = signal.signal(signal.SIGTERM, _on_term)
    try:
        return _run_stage_inner(a)
    finally:
        signal.signal(signal.SIGTERM, prev_handler)


def _run_stage_inner(a):
    pdig = mi19_protocol.verify(a.protocol)
    cfg, _ = mi19_protocol.static_cfg()
    rows = Q.load_rows(a.requests, cfg)
    if json.load(open(a.protocol))["locked"]["files"].get(a.requests) != generate.sha(open(a.requests, "rb").read()):
        sys.exit(f"{a.requests} not locked in {a.protocol}")
    allowed = allowed_gpus()
    gpus = [int(x) for x in a.gpus.split(",")] if a.gpus else allowed
    out_dir = a.out_dir
    os.makedirs(out_dir, exist_ok=True)
    cp = os.path.join(out_dir, "completion.json")
    if os.path.exists(cp):
        done, missing = verify_job(out_dir, rows, cfg, pdig)
        if not missing:
            print(f"already complete & re-verified ({len(rows)} requests); skip", flush=True)
            sys.exit(0)
    alive = live_workers(out_dir)
    if alive:
        sys.exit(f"live worker(s) still own {out_dir}: {alive}")
    snap = query_gpus(gpus)
    assign = plan_gpus(gpus, a.workers, a.peak_gb, allowed, snap)
    info = queue_lock.my_info(role="mi19_run")
    rlk, own, _ = queue_lock.try_lock(os.path.join(out_dir, "run.lock"), info)
    if rlk is None:
        sys.exit(f"another mi19_run owns {out_dir}: {own}")
    aid = f"{time.strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"
    att_dir = os.path.join(out_dir, "attempts")
    os.makedirs(att_dir, exist_ok=True)
    att_path = os.path.join(att_dir, f"attempt_{aid}.json")
    att = {"attempt_id": aid, "status": "running", "pid": os.getpid(), "t_start": time.time(), "workers": a.workers,
           "assign_worker_gpu": assign, "gpu_uuid": {g: snap[g]["uuid"] for g in gpus}, "peak_gb_assumed": a.peak_gb,
           "gpu_snapshot_before": snap, "allowed": allowed}
    procs = []
    try:
        if os.path.exists(cp):
            os.replace(cp, os.path.join(att_dir, f"completion_superseded_by_{aid}.json"))
        atomic_json(att, att_path)
        for k, g in assign:
            cmd = [sys.executable, "-m", "rsna_diag.mi19_gen", "--requests", a.requests, "--out-dir", out_dir,
                   "--worker", str(k), "--protocol", a.protocol]
            if a.max_requests is not None:
                cmd += ["--max-requests", str(a.max_requests)]
            if a.time_limit:
                cmd += ["--time-limit", str(a.time_limit)]
            if a.repair_tail:
                cmd += ["--repair-tail"]
            env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(g), CUDA_DEVICE_ORDER="PCI_BUS_ID")
            procs.append(subprocess.Popen(cmd, env=env, stdout=open(f"{out_dir}/worker{k}.stdout.log", "a"),
                                          stderr=open(f"{out_dir}/worker{k}.stderr.log", "a")))
        att["children"] = [{"pid": p.pid, "start": queue_lock.proc_start(p.pid), "worker": k, "gpu": g} for p, (k, g) in zip(procs, assign)]
        atomic_json(att, att_path)
        t0 = time.time()
        rl = open(f"{out_dir}/resource_log.jsonl", "a")
        while any(p.poll() is None for p in procs):
            try:
                q = query_gpus(gpus)
                apps = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,used_memory", "--format=csv,noheader,nounits"],
                                      capture_output=True, text=True).stdout.strip().splitlines()
            except GpuError as e:
                q, apps = {"error": str(e)}, []
            rl.write(json.dumps({"t": time.time() - t0, "gpus": q, "apps": apps}) + "\n")
            rl.flush()
            time.sleep(a.poll_s)
        codes = [p.returncode for p in procs]
        wall = time.time() - t0
        err = None
        try:
            done, missing = verify_job(out_dir, rows, cfg, pdig)
        except mi19_gen.GenError as e:
            done, missing, err = {}, [r["request_id"] for r in rows], str(e)[:500]
        per_file = {os.path.basename(f): len(mi19_gen.read_strict(f)) for f in sorted(glob.glob(f"{out_dir}/gen_worker*.jsonl"))}
        rep = {"n_expected": len(rows), "n_actual_unique": len(done), "n_missing": len(missing), "n_duplicate": 0,
               "n_extra": 0, "returncodes": codes, "wall_s": wall, "per_file": per_file, "protocol_digest": pdig,
               "worker_gpu": assign, "gpu_uuid": att["gpu_uuid"], "verify_error": err, "requests": a.requests,
               "requests_sha256": generate.sha(open(a.requests, "rb").read()), "config_digest": cfg, "attempt_id": aid}
        atomic_json(rep, f"{out_dir}/last_run.json")
        ok = not missing and err is None and all(c == 0 for c in codes)
        att.update({"status": "complete" if ok else "failed_or_incomplete", "returncodes": codes, "t_end": time.time(), "report": rep})
        atomic_json(att, att_path)
        if ok:
            atomic_json(rep, cp)
        print(f"rc={codes} wall={wall:.0f}s n={len(done)}/{len(rows)} ok={ok}", flush=True)
        sys.exit(0 if ok else 2)
    finally:
        stopped = stop_children(procs) if any(p.poll() is None for p in procs) else [{"pid": p.pid, "returncode": p.returncode} for p in procs]
        if att["status"] == "running":
            att.update({"status": "interrupted", "t_end": time.time(), "children_final": stopped})
            try:
                atomic_json(att, att_path)
            except OSError:
                pass
        rlk.release()


if __name__ == "__main__":
    main()
