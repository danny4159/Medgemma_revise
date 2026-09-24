"""생성 worker 병렬 실행 orchestrator (iter_010). worker 수와 GPU 수를 분리한다.

- 상속된 CUDA_VISIBLE_DEVICES(허용 집합) 안에서만 GPU를 배정한다: worker k -> gpus[k % len(gpus)] (같은 GPU에 여러 worker 가능).
- 각 worker는 `python -m rsna_diag.generate`(원자적 claim 큐, worker별 출력 gen_worker{k}.jsonl). 기존 claim은 지우지 않는다
  (죽은 소유자의 claim만 worker가 스스로 회수). 같은 out-dir에 대한 동시 orchestrator는 run.lock으로 거부한다.
- 종료 후 예상 요청 집합 == 실제 집합(중복·누락·잉여 0)일 때만 completion.json을 쓴다.
- 자원 로그: GPU별 memory.used/util과 프로세스별 사용량을 resource_log.jsonl에 주기적으로 append한다.
사용: python -m rsna_diag.run_shards --manifest M --ids IDS --out-dir D --protocol P --prompts a,b --workers N [--adapter DIR]
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import time

from . import generate, lock_protocol, prompts as P, queue_lock


def gpu_snapshot(idx_list):
    q = lambda cmd: subprocess.run(cmd, capture_output=True, text=True).stdout
    out = q(["nvidia-smi", "--query-gpu=index,uuid,memory.used,memory.total,utilization.gpu", "--format=csv,noheader,nounits"])
    rows = []
    for ln in out.strip().splitlines():
        i, u, mu, mt, ut = [x.strip() for x in ln.split(",")]
        if int(i) in idx_list:
            rows.append({"index": int(i), "uuid": u, "mem_used_mib": int(mu), "mem_total_mib": int(mt), "util": int(ut)})
    apps = q(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,used_memory", "--format=csv,noheader,nounits"])
    procs = [ln.strip() for ln in apps.strip().splitlines() if ln.strip()]
    return rows, procs


def finalize(out_dir, items, pnames, prompts_used, adapter_digest, protocol_digest):
    """예상 요청 집합과 실제 집합을 대조한다. returns (complete, report)."""
    files = {f: generate.read_records(f) for f in sorted(glob.glob(os.path.join(out_dir, "gen_worker*.jsonl")))}
    expected = {(i["id"], p) for i in items for p in pnames}
    got, dup, extra = {}, [], []
    for fn, recs in files.items():
        for r in recs:
            k = (r["id"], r["prompt_name"])
            if k not in expected:
                extra.append(k)
            if k in got:
                dup.append(k)
            got[k] = r
    missing = sorted(expected - set(got))
    rep = {"n_expected": len(expected), "n_actual_unique": len(got), "n_missing": len(missing), "n_duplicate": len(dup),
           "n_extra": len(extra), "missing_head": missing[:5], "per_file": {os.path.basename(f): len(r) for f, r in files.items()},
           "adapter_digest": adapter_digest, "protocol_digest": protocol_digest, "prompts": pnames}
    return (not missing and not dup and not extra), rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--ids", default=None)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--prompts", required=True)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--gpus", default=None, help="허용 집합의 부분집합 (기본: CUDA_VISIBLE_DEVICES 전체)")
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--time-limit", type=float, default=None)
    ap.add_argument("--max-requests", type=int, default=None, help="worker별 (pilot/test용)")
    a = ap.parse_args()
    pdig = lock_protocol.verify(a.protocol)
    allowed = [int(x) for x in os.environ.get("CUDA_VISIBLE_DEVICES", "0,1").split(",")]
    gpus = [int(x) for x in a.gpus.split(",")] if a.gpus else allowed
    if not set(gpus) <= set(allowed):
        sys.exit(f"gpus {gpus} not within allowed {allowed}")
    os.makedirs(a.out_dir, exist_ok=True)
    info = queue_lock.my_info(role="run_shards")
    rl_path = os.path.join(a.out_dir, "run.lock")
    rlk, own, _ = queue_lock.try_lock(rl_path, info)
    if rlk is None:
        sys.exit(f"another run_shards owns {a.out_dir}: {own}")
    try:
        procs = []
        for k in range(a.workers):
            env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(gpus[k % len(gpus)]))
            cmd = [sys.executable, "-m", "rsna_diag.generate", "--manifest", a.manifest, "--prompts", a.prompts,
                   "--worker", str(k), "--out-dir", a.out_dir, "--protocol", a.protocol]
            if a.ids:
                cmd += ["--ids", a.ids]
            if a.adapter:
                cmd += ["--adapter", a.adapter]
            if a.time_limit:
                cmd += ["--time-limit", str(a.time_limit)]
            if a.max_requests is not None:
                cmd += ["--max-requests", str(a.max_requests)]
            procs.append(subprocess.Popen(cmd, env=env, stdout=open(f"{a.out_dir}/worker{k}.stdout.log", "a"),
                                          stderr=open(f"{a.out_dir}/worker{k}.stderr.log", "a")))
        t0 = time.time()
        rl = open(f"{a.out_dir}/resource_log.jsonl", "a")
        while any(p.poll() is None for p in procs):
            rows, apps = gpu_snapshot(set(gpus))
            rl.write(json.dumps({"t": time.time() - t0, "gpus": rows, "compute_apps": apps}) + "\n")
            rl.flush()
            time.sleep(30)
        codes = [p.returncode for p in procs]
        items = [json.loads(ln) for ln in open(a.manifest) if ln.strip()]
        if a.ids:
            keep = set(json.load(open(a.ids)))
            items = [i for i in items if i["id"] in keep]
        pnames = a.prompts.split(",")
        complete, rep = finalize(a.out_dir, items, pnames, {p: P.all_prompts()[p] for p in pnames}, a.adapter, pdig)
        rep.update({"returncodes": codes, "wall_s": time.time() - t0, "allowed_gpus": allowed, "gpus_used": gpus,
                    "n_workers": a.workers, "worker_gpu": [gpus[k % len(gpus)] for k in range(a.workers)]})
        json.dump(rep, open(f"{a.out_dir}/last_run.json", "w"), indent=1)
        if complete and all(c == 0 for c in codes):
            json.dump(rep, open(f"{a.out_dir}/completion.json", "w"), indent=1)
        print("returncodes", codes, "wall_s", round(rep["wall_s"]), "complete", complete, {k: rep[k] for k in ("n_expected", "n_actual_unique", "n_missing")})
        sys.exit(0 if complete and all(c == 0 for c in codes) else 2)
    finally:
        rlk.release()


if __name__ == "__main__":
    main()
