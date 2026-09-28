"""iter_028: risk28 worker를 여러 GPU/프로세스로 분산 실행하고 모두 끝날 때까지 기다린다.

--config: "GPU_ID:variant" 쌍의 리스트. 예: 2-worker 기본 구성은
  0:base 1:sft
4-worker(GPU당 2개)는
  0:base 1:sft 0:sft 1:base
각 항목이 독립 worker 프로세스가 되며 worker index는 등장 순서(0부터)로 자동 부여한다.
같은 (variant) 내 여러 worker는 동일 item 목록에 대해 원자적 claim으로 자동 분업한다.
"""
import argparse
import json
import os
import subprocess
import sys
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-manifest", required=True)
    ap.add_argument("--split", required=True, choices=["C", "E", "D24"])
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--adapter", required=True, help="sft variant adapter dir")
    ap.add_argument("--config", nargs="+", required=True, help="GPU:variant pairs, e.g. 0:base 1:sft")
    ap.add_argument("--time-limit", type=float, default=None)
    ap.add_argument("--ids", default=None)
    a = ap.parse_args()

    os.makedirs(a.out_dir, exist_ok=True)
    procs = []
    t0 = time.time()
    variant_worker_idx = {}
    for i, item in enumerate(a.config):
        gpu, variant = item.split(":")
        widx = variant_worker_idx.get(variant, 0)
        variant_worker_idx[variant] = widx + 1
        cmd = [sys.executable, "-m", "rsna_diag.risk28", "--source-manifest", a.source_manifest,
               "--split", a.split, "--variant", variant, "--out-dir", a.out_dir,
               "--worker", str(widx), "--protocol", a.protocol]
        if variant == "sft":
            cmd += ["--adapter", a.adapter]
        if a.time_limit:
            cmd += ["--time-limit", str(a.time_limit)]
        if a.ids:
            cmd += ["--ids", a.ids]
        env = dict(os.environ)
        env["CUDA_VISIBLE_DEVICES"] = gpu
        log_path = os.path.join(a.out_dir, f"launch_{variant}_w{widx}_gpu{gpu}.log")
        logf = open(log_path, "w")
        p = subprocess.Popen(cmd, env=env, stdout=logf, stderr=subprocess.STDOUT, cwd=os.getcwd())
        procs.append({"proc": p, "gpu": gpu, "variant": variant, "worker": widx, "log": log_path, "logf": logf})
        print(f"launched pid={p.pid} gpu={gpu} variant={variant} worker={widx}")

    results = []
    for pr in procs:
        rc = pr["proc"].wait()
        pr["logf"].close()
        results.append({"gpu": pr["gpu"], "variant": pr["variant"], "worker": pr["worker"],
                         "returncode": rc, "log": pr["log"]})
        print(f"finished gpu={pr['gpu']} variant={pr['variant']} worker={pr['worker']} rc={rc}")
    wall_s = time.time() - t0
    out = {"config": a.config, "wall_s": wall_s, "results": results}
    json.dump(out, open(os.path.join(a.out_dir, "launch_result.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))
    if any(r["returncode"] != 0 for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
