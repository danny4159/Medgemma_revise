"""두 GPU shard 병렬 실행 orchestrator (iter_009).

- 상속된 CUDA_VISIBLE_DEVICES(허용 집합) 안에서만 GPU를 배정한다 (shard k -> 허용 목록의 k번째 물리 index).
- 각 shard는 `python -m rsna_diag.generate`를 자식 프로세스로 실행한다. 재개 가능하며 --time-limit에서 요청 사이에 안전 종료한다.
- 자원 로그(GPU별 memory.used/util)를 out_dir/resource_log.jsonl에 주기적으로 append한다.
사용: python -m rsna_diag.run_shards --manifest M --ids IDS --out-dir D [--time-limit S] [--prompts ...]
"""
import argparse
import json
import os
import subprocess
import sys
import time


def gpu_snapshot(idx_list):
    out = subprocess.run(["nvidia-smi", "--query-gpu=index,uuid,memory.used,memory.total,utilization.gpu",
                          "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout
    rows = []
    for ln in out.strip().splitlines():
        i, u, mu, mt, ut = [x.strip() for x in ln.split(",")]
        if int(i) in idx_list:
            rows.append({"index": int(i), "uuid": u, "mem_used_mib": int(mu), "mem_total_mib": int(mt), "util": int(ut)})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--ids", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--prompts", default="official_long,concise,legacy_detect")
    ap.add_argument("--time-limit", type=float, default=None)
    ap.add_argument("--n-shards", type=int, default=2)
    ap.add_argument("--carry", default=None)
    ap.add_argument("--queue", action="store_true", help="환자 단위 작업 큐 (claim 파일). 시작 시 기존 claim을 비운다")
    a = ap.parse_args()
    allowed = [int(x) for x in os.environ.get("CUDA_VISIBLE_DEVICES", "0,1").split(",")]
    if a.n_shards > len(allowed):
        sys.exit(f"n_shards {a.n_shards} > allowed GPUs {allowed}")
    os.makedirs(a.out_dir, exist_ok=True)
    procs = []
    claim_dir = f"{a.out_dir}/claims"
    if a.queue:
        os.makedirs(claim_dir, exist_ok=True)
        for f in os.listdir(claim_dir):
            os.remove(os.path.join(claim_dir, f))
    for k in range(a.n_shards):
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(allowed[k]))
        cmd = [sys.executable, "-m", "rsna_diag.generate", "--manifest", a.manifest, "--ids", a.ids,
               "--prompts", a.prompts, "--shard", f"{k}/{a.n_shards}", "--out", f"{a.out_dir}/gen_shard{k}.jsonl"]
        if a.time_limit:
            cmd += ["--time-limit", str(a.time_limit)]
        if a.carry:
            cmd += ["--carry", a.carry]
        if a.queue:
            cmd += ["--claim-dir", claim_dir]
        logf = open(f"{a.out_dir}/shard{k}.stderr.log", "a")
        procs.append(subprocess.Popen(cmd, env=env, stdout=open(f"{a.out_dir}/shard{k}.stdout.log", "a"), stderr=logf))
    t0 = time.time()
    rl = open(f"{a.out_dir}/resource_log.jsonl", "a")
    while any(p.poll() is None for p in procs):
        rl.write(json.dumps({"t": time.time() - t0, "gpus": gpu_snapshot(set(allowed[:a.n_shards]))}) + "\n")
        rl.flush()
        time.sleep(30)
    codes = [p.returncode for p in procs]
    json.dump({"returncodes": codes, "wall_s": time.time() - t0, "allowed_gpus": allowed}, open(f"{a.out_dir}/last_run.json", "w"))
    print("returncodes", codes, "wall_s", round(time.time() - t0))
    sys.exit(0 if all(c == 0 for c in codes) else 1)


if __name__ == "__main__":
    main()
