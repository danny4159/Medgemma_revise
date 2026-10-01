"""iter_048 병렬 job 실행기: 허용 GPU 집합(CUDA_VISIBLE_DEVICES 상속) 안에서만 job을 장치에 배정하고 모두 끝날 때까지 기다린다.

python pg48_jobs.py --log-dir DIR --job GPU "CMD ..." [--job GPU "CMD ..."] ...
 - GPU는 상속된 허용 집합의 물리 index. 각 job은 CUDA_VISIBLE_DEVICES=<GPU> 로 시작한다 (논리/물리 대응은 job 로그 첫 줄에 기록).
 - 시작 직전 nvidia-smi 여유 메모리를 기록한다. 로그는 DIR/job<k>.log (이어쓰기), 종료 코드는 DIR/jobs_<ts>.json.
"""
import argparse
import json
import os
import shlex
import subprocess
import sys
import time


def free_mib():
    r = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,memory.total", "--format=csv,noheader,nounits"], capture_output=True, text=True, check=True)
    return {int(l.split(",")[0]): int(l.split(",")[2]) - int(l.split(",")[1]) for l in r.stdout.strip().splitlines()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log-dir", required=True)
    ap.add_argument("--job", nargs=2, action="append", metavar=("GPU", "CMD"), required=True)
    ap.add_argument("--min-free-gb", type=float, default=0.0, help="job 시작 전 해당 GPU 여유 최소값 (GiB)")
    a = ap.parse_args()
    allowed = [int(x) for x in os.environ.get("CUDA_VISIBLE_DEVICES", "").split(",") if x]
    if not allowed:
        sys.exit("CUDA_VISIBLE_DEVICES not set")
    os.makedirs(a.log_dir, exist_ok=True)
    free = free_mib()
    procs = []
    t0 = time.time()
    for k, (gpu, cmd) in enumerate(a.job):
        g = int(gpu)
        if g not in allowed:
            sys.exit(f"gpu {g} not in allowed {allowed}")
        if free[g] < a.min_free_gb * 1024:
            sys.exit(f"gpu {g} free {free[g]} MiB < {a.min_free_gb} GiB")
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(g))
        lf = open(os.path.join(a.log_dir, f"job{k}.log"), "a")
        lf.write(f"# job{k} gpu(physical)={g} CUDA_VISIBLE_DEVICES={g} free_mib_before={free[g]} start={time.time()} cmd={cmd}\n")
        lf.flush()
        procs.append((k, g, cmd, subprocess.Popen(shlex.split(cmd), env=env, stdout=lf, stderr=subprocess.STDOUT)))
    codes = {}
    for k, g, cmd, p in procs:
        codes[k] = p.wait()
    res = {"wall_s": time.time() - t0, "jobs": [{"k": k, "gpu": g, "cmd": cmd, "rc": codes[k]} for k, g, cmd, _ in procs], "free_mib_before": free}
    json.dump(res, open(os.path.join(a.log_dir, f"jobs_{int(time.time())}.json"), "w"), indent=1)
    print(json.dumps(res))
    sys.exit(0 if all(c == 0 for c in codes.values()) else 1)


if __name__ == "__main__":
    main()
