"""iter_026 stage 실행기 (roi25_run.py 기반). 요청 jsonl 파일 목록(각 파일은 단일 checkpoint)을 순차 처리한다.
사용: python -m rsna_diag.roi26_run --jobs f1.jsonl,f2.jsonl --protocol P --workers 2 --peak-gb 10
"""
import argparse
import glob
import signal
import json
import os
import subprocess
import sys
import time

from . import eval_gate, generate, roi26_gen as qa_gen, roi26_protocol as qa_protocol, roi26_requests as Q, queue_lock

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
    try:
        for ln in r.stdout.strip().splitlines():
            i, u, mu, mt = [x.strip() for x in ln.split(",")]
            rows[int(i)] = {"uuid": u, "used_mib": int(mu), "total_mib": int(mt)}
    except ValueError as e:
        raise GpuError(f"cannot parse nvidia-smi output: {r.stdout[:200]}") from e
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


def verify_job(out_dir, rows, cfg, pdig, adapter_dir):
    qa_gen.check_inputs(rows)
    adg = eval_gate.adapter_digest(adapter_dir) if adapter_dir else None
    if adg != rows[0]["adapter_digest"]:
        raise qa_gen.QAError(f"adapter digest {adg} != requests {rows[0]['adapter_digest']}")
    files = {f: qa_gen.read_strict(f) for f in sorted(glob.glob(os.path.join(out_dir, "gen_worker*.jsonl")))}
    cache = {}
    px = lambda p: cache.setdefault(p, generate.load_image(p)[2])
    done = qa_gen.validate_records(files, rows, cfg, adg, pdig, px)
    missing = [r["request_id"] for r in rows if r["request_id"] not in done]
    return done, missing


class _Term(BaseException):
    pass


def _on_term(signum, frame):
    raise _Term(f"signal {signum}")


def run_one(rp, protocol, workers, gpus_arg, peak_gb, allowed, out_root, max_requests=None, time_limit=None,
            repair_tail=False, poll_s=20.0):
    pdig = qa_protocol.verify(protocol)
    cfg, _ = qa_protocol.static_cfg()
    rows = Q.load_rows(rp, cfg)
    if json.load(open(protocol))["locked"]["files"].get(rp) != generate.sha(open(rp, "rb").read()):
        raise RuntimeError(f"{rp} not locked in {protocol}")
    ckpt = rows[0]["checkpoint"]
    tab = Q.checkpoints([ckpt])
    adapter = tab[ckpt]["dir"]
    name = os.path.splitext(os.path.basename(rp))[0]
    out_dir = f"{out_root}/gen/{name}"
    os.makedirs(out_dir, exist_ok=True)
    cp = os.path.join(out_dir, "completion.json")
    if os.path.exists(cp):
        done, missing = verify_job(out_dir, rows, cfg, pdig, adapter)
        c = json.load(open(cp))
        ok_c = (not missing and c.get("protocol_digest") == pdig and c.get("n_expected") == len(rows)
                and c.get("n_actual_unique") == len(rows) and c.get("n_missing") == 0 and c.get("n_duplicate") == 0
                and bool(c.get("returncodes")) and all(x == 0 for x in c["returncodes"]))
        if ok_c:
            print(f"[{name}] already complete & re-verified ({len(rows)} requests); skip", flush=True)
            return {"name": name, "status": "verified_complete", "n": len(rows)}
    alive = live_workers(out_dir)
    if alive:
        raise RuntimeError(f"live worker(s) still own {out_dir}: {alive} (parent was killed?). Wait for/stop them, then rerun.")
    gpus = [int(x) for x in gpus_arg.split(",")] if gpus_arg else allowed
    snap = query_gpus(gpus)
    assign = plan_gpus(gpus, workers, peak_gb, allowed, snap)
    info = queue_lock.my_info(role="roi26_run")
    rlk, own, _ = queue_lock.try_lock(os.path.join(out_dir, "run.lock"), info)
    if rlk is None:
        raise RuntimeError(f"another roi26_run owns {out_dir}: {own}")
    aid = f"{time.strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"
    att_dir = os.path.join(out_dir, "attempts")
    os.makedirs(att_dir, exist_ok=True)
    att_path = os.path.join(att_dir, f"attempt_{aid}.json")
    att = {"attempt_id": aid, "status": "running", "pid": os.getpid(), "t_start": time.time(), "workers": workers,
           "assign_worker_gpu": assign, "gpu_uuid": {g: snap[g]["uuid"] for g in gpus}, "peak_gb_assumed": peak_gb,
           "gpu_snapshot_before": snap, "allowed": allowed}
    procs = []
    try:
        if os.path.exists(cp):
            os.replace(cp, os.path.join(att_dir, f"completion_superseded_by_{aid}.json"))
        atomic_json(att, att_path)
        for k, g in assign:
            cmd = [sys.executable, "-m", "rsna_diag.roi26_gen", "--requests", rp, "--out-dir", out_dir, "--worker", str(k),
                   "--protocol", protocol]
            if adapter:
                cmd += ["--adapter", adapter]
            if max_requests is not None:
                cmd += ["--max-requests", str(max_requests)]
            if time_limit:
                cmd += ["--time-limit", str(time_limit)]
            if repair_tail:
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
            time.sleep(poll_s)
        codes = [p.returncode for p in procs]
        wall = time.time() - t0
        err = None
        try:
            done, missing = verify_job(out_dir, rows, cfg, pdig, adapter)
        except (qa_gen.QAError, eval_gate.GateError) as e:
            done, missing, err = {}, [r["request_id"] for r in rows], str(e)[:500]
        per_file = {os.path.basename(f): len(qa_gen.read_strict(f)) for f in sorted(glob.glob(f"{out_dir}/gen_worker*.jsonl"))}
        rep = {"name": name, "n_expected": len(rows), "n_actual_unique": len(done), "n_missing": len(missing),
               "n_duplicate": 0, "n_extra": 0, "returncodes": codes, "wall_s": wall, "per_file": per_file, "protocol_digest": pdig,
               "adapter_digest": rows[0]["adapter_digest"], "worker_gpu": assign, "gpu_uuid": att["gpu_uuid"], "verify_error": err,
               "requests": rp, "requests_sha256": generate.sha(open(rp, "rb").read()), "config_digest": cfg, "attempt_id": aid}
        atomic_json(rep, f"{out_dir}/last_run.json")
        ok = not missing and err is None and all(c == 0 for c in codes)
        att.update({"status": "complete" if ok else "failed_or_incomplete", "returncodes": codes, "t_end": time.time(), "report": rep})
        atomic_json(att, att_path)
        if ok:
            atomic_json(rep, cp)
        print(f"[{name}] rc={codes} wall={wall:.0f}s n={len(done)}/{len(rows)} ok={ok}", flush=True)
        return {"name": name, "status": "complete" if ok else "FAILED", "n": len(done), "of": len(rows), "wall_s": wall,
                "rc": codes, "missing": len(missing), "err": err}
    finally:
        stopped = stop_children(procs) if any(p.poll() is None for p in procs) else [{"pid": p.pid, "returncode": p.returncode} for p in procs]
        if att["status"] == "running":
            att.update({"status": "interrupted", "t_end": time.time(), "children_final": stopped})
            try:
                atomic_json(att, att_path)
            except OSError:
                pass
        rlk.release()


def main():
    signal.signal(signal.SIGTERM, _on_term)
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True, help="comma-separated request jsonl paths")
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--workers", type=int, required=True)
    ap.add_argument("--gpus", default=None)
    ap.add_argument("--peak-gb", type=float, required=True)
    ap.add_argument("--max-requests", type=int, default=None)
    ap.add_argument("--time-limit", type=float, default=None)
    ap.add_argument("--repair-tail", action="store_true")
    ap.add_argument("--poll-s", type=float, default=20.0)
    ap.add_argument("--out-root", default=Q.OUT)
    a = ap.parse_args()
    allowed = allowed_gpus()
    summary = []
    for rp in a.jobs.split(","):
        res = run_one(rp, a.protocol, a.workers, a.gpus, a.peak_gb, allowed, a.out_root, a.max_requests, a.time_limit,
                      a.repair_tail, a.poll_s)
        summary.append(res)
    print(json.dumps(summary))
    sys.exit(0 if all(s["status"] in ("complete", "verified_complete") for s in summary) else 2)


if __name__ == "__main__":
    main()
