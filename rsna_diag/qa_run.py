"""iter_015 stage 실행기: worker 수와 GPU 수를 분리하고, 허용 GPU 집합·메모리 여유·완료 검증·자식 종료 코드를 강제한다.

- 허용 집합 = 상속된 CUDA_VISIBLE_DEVICES(정수 목록). --gpus는 그 부분집합. worker k -> gpus[k % len(gpus)] (같은 GPU에 여러 worker 가능).
- 실행 전 nvidia-smi를 조회한다. 조회 실패·파싱 실패는 실행하지 않는다. GPU별 (다른 프로세스 점유 + worker 수 x (측정 peak + 2GiB 여유)) <= 총 용량이어야 한다.
- 이미 완료된 job은 모델을 올리지 않고 현재 입력·config·protocol·adapter와 다시 대조한 뒤 건너뛴다.
- job 종료 후 모든 자식 종료 코드 수집, 요청 집합 == record 집합(누락·중복·잉여 0)이고 record 검증을 통과할 때만 completion.json을 원자적으로 쓴다.
사용: python -m rsna_diag.qa_run --stage S --ckpts M0,B0 --protocol P --workers 4 --peak-gb 10
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import time

from . import eval_gate, generate, qa_gen, qa_protocol, qa_requests as Q, queue_lock

OUT = Q.OUT
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
    """returns {index: {uuid, used_mib, total_mib}}; nvidia-smi 실패·누락이면 GpuError."""
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
    """허용 집합 검사와 GPU별 메모리 합산. returns 배정 list[(worker, gpu)]. 위반 시 GpuError."""
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


def load_job(stage, ckpt, protocol):
    rp = f"{OUT}/requests/{stage}__{ckpt}.jsonl"
    cfg, _ = qa_protocol.static_cfg()
    rows = Q.load_rows(rp, cfg)
    if json.load(open(protocol))["locked"]["files"].get(rp) != generate.sha(open(rp, "rb").read()):
        raise RuntimeError(f"{rp} not locked in {protocol}")
    return rp, rows, cfg


def verify_job(out_dir, rows, cfg, pdig, adapter_dir, require_complete=True):
    """out_dir의 모든 record를 요청 행·현재 입력·adapter·config·protocol과 대조. returns (done dict, missing list)."""
    adg = eval_gate.adapter_digest(adapter_dir) if adapter_dir else None
    if adg != rows[0]["adapter_digest"]:
        raise qa_gen.QAError(f"adapter digest {adg} != requests {rows[0]['adapter_digest']}")
    files = {f: qa_gen.read_strict(f) for f in sorted(glob.glob(os.path.join(out_dir, "gen_worker*.jsonl")))}
    cache = {}
    px = lambda p: cache.setdefault(p, generate.load_image(p)[2])
    done = qa_gen.validate_records(files, rows, cfg, adg, pdig, px)
    missing = [r["request_id"] for r in rows if r["request_id"] not in done]
    return done, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--ckpts", required=True)
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--workers", type=int, required=True)
    ap.add_argument("--gpus", default=None)
    ap.add_argument("--peak-gb", type=float, required=True, help="worker당 측정 peak GiB (pilot 실측값). 각 worker에 2GiB 여유를 더해 검사한다")
    ap.add_argument("--max-requests", type=int, default=None, help="worker별 (pilot/test 전용)")
    ap.add_argument("--time-limit", type=float, default=None)
    ap.add_argument("--repair-tail", action="store_true")
    ap.add_argument("--poll-s", type=float, default=20.0)
    ap.add_argument("--out-suffix", default="", help="pilot 등 별도 경로용 (기본: 정식 gen 경로)")
    a = ap.parse_args()
    pdig = qa_protocol.verify(a.protocol)
    tab = json.load(open(f"{OUT}/manifests/checkpoints.json"))
    allowed = allowed_gpus()
    gpus = [int(x) for x in a.gpus.split(",")] if a.gpus else allowed
    summary = []
    for ckpt in a.ckpts.split(","):
        rp, rows, cfg = load_job(a.stage, ckpt, a.protocol)
        out_dir = f"{OUT}/gen{a.out_suffix}/{a.stage}__{ckpt}"
        os.makedirs(out_dir, exist_ok=True)
        adapter = tab[ckpt]["dir"]
        cp = os.path.join(out_dir, "completion.json")
        if os.path.exists(cp):
            done, missing = verify_job(out_dir, rows, cfg, pdig, adapter)
            c = json.load(open(cp))
            if not missing and c.get("protocol_digest") == pdig and c.get("n_expected") == len(rows):
                print(f"[{ckpt}] already complete & re-verified ({len(rows)} requests); skip", flush=True)
                summary.append({"ckpt": ckpt, "status": "verified_complete", "n": len(rows)})
                continue
        snap = query_gpus(gpus)
        assign = plan_gpus(gpus, a.workers, a.peak_gb, allowed, snap)
        info = queue_lock.my_info(role="qa_run")
        rlk, own, _ = queue_lock.try_lock(os.path.join(out_dir, "run.lock"), info)
        if rlk is None:
            sys.exit(f"another qa_run owns {out_dir}: {own}")
        aid = f"{time.strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"
        att_dir = os.path.join(out_dir, "attempts")
        os.makedirs(att_dir, exist_ok=True)
        att_path = os.path.join(att_dir, f"attempt_{aid}.json")
        att = {"attempt_id": aid, "status": "running", "pid": os.getpid(), "t_start": time.time(), "workers": a.workers,
               "assign_worker_gpu": assign, "gpu_uuid": {g: snap[g]["uuid"] for g in gpus}, "peak_gb_assumed": a.peak_gb,
               "gpu_snapshot_before": snap, "allowed": allowed}
        procs = []
        try:
            if os.path.exists(cp):  # 새 시도 시작: 이전 completion은 현재 성공 근거가 아니다 (삭제하지 않고 보존)
                os.replace(cp, os.path.join(att_dir, f"completion_superseded_by_{aid}.json"))
            atomic_json(att, att_path)
            for k, g in assign:
                cmd = [sys.executable, "-m", "rsna_diag.qa_gen", "--requests", rp, "--out-dir", out_dir, "--worker", str(k),
                       "--protocol", a.protocol]
                if adapter:
                    cmd += ["--adapter", adapter]
                if a.max_requests is not None:
                    cmd += ["--max-requests", str(a.max_requests)]
                if a.time_limit:
                    cmd += ["--time-limit", str(a.time_limit)]
                if a.repair_tail:
                    cmd += ["--repair-tail"]
                env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(g), CUDA_DEVICE_ORDER="PCI_BUS_ID")
                procs.append(subprocess.Popen(cmd, env=env, stdout=open(f"{out_dir}/worker{k}.stdout.log", "a"),
                                              stderr=open(f"{out_dir}/worker{k}.stderr.log", "a")))
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
                done, missing = verify_job(out_dir, rows, cfg, pdig, adapter)
            except (qa_gen.QAError, eval_gate.GateError) as e:
                done, missing, err = {}, [r["request_id"] for r in rows], str(e)[:500]
            per_file = {os.path.basename(f): len(qa_gen.read_strict(f)) for f in sorted(glob.glob(f"{out_dir}/gen_worker*.jsonl"))}
            rep = {"stage": a.stage, "checkpoint": ckpt, "n_expected": len(rows), "n_actual_unique": len(done), "n_missing": len(missing),
                   "n_duplicate": 0, "n_extra": 0, "returncodes": codes, "wall_s": wall, "per_file": per_file, "protocol_digest": pdig,
                   "adapter_digest": rows[0]["adapter_digest"], "worker_gpu": assign, "gpu_uuid": att["gpu_uuid"], "verify_error": err,
                   "requests": rp, "attempt_id": aid}
            atomic_json(rep, f"{out_dir}/last_run.json")
            ok = not missing and err is None and all(c == 0 for c in codes)
            att.update({"status": "complete" if ok else "failed_or_incomplete", "returncodes": codes, "t_end": time.time(), "report": rep})
            atomic_json(att, att_path)
            if ok:
                atomic_json(rep, cp)
            elif a.max_requests is None:
                summary.append({"ckpt": ckpt, "status": "FAILED", "rc": codes, "missing": len(missing), "err": err})
            print(f"[{ckpt}] rc={codes} wall={wall:.0f}s n={len(done)}/{len(rows)} ok={ok}", flush=True)
            summary.append({"ckpt": ckpt, "status": "complete" if ok else "incomplete", "n": len(done), "of": len(rows), "wall_s": wall})
        finally:
            if att["status"] == "running":
                att.update({"status": "interrupted", "t_end": time.time(),
                            "children": [{"pid": p.pid, "returncode": p.poll()} for p in procs]})
                try:
                    atomic_json(att, att_path)
                except OSError:
                    pass
            rlk.release()
    print(json.dumps(summary))
    sys.exit(0 if all(s["status"] in ("complete", "verified_complete") for s in summary) else 2)


if __name__ == "__main__":
    main()
