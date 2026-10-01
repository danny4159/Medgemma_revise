"""iter_045 paired timing block 실행기. block k(1..6)는 C와 MG-selected를 순차 실행한다 (동시 실행 금지).
선행 시스템: C/MG/C/MG/C/MG (k 홀수=C 먼저). 구성은 D24/pilot에서 잠근 값:
  C : 4 worker (GPU당 2), 환자 단위 claim, warm-up D8 4환자(8요청) 후 barrier.
  MG: decisions/D24_select.json의 ckpt·threshold, 2 worker(GPU당 1), batch 4, inline 후처리, warm-up D8 16문장 후 barrier.
python mg45_timing.py --k 1 [--attempt 1]
기술 실패(비정상 종료·불완전)면 원본 dir을 보존하고 --attempt N+1 로 paired block 전체(두 시스템)를 새 dir에 재측정한다. 느리다는 이유의 제외 금지.
"""
import argparse
import json
import os
import subprocess
import sys
import time

SEL = "results/iter_045/decisions/D24_select.json"
ROOT = "results/iter_045/timing/main"


def run(cmd, log):
    t = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True)
    open(log, "a").write(f"$ {' '.join(cmd)}\nrc={p.returncode} dt={time.time()-t:.1f}\n{p.stdout[-3000:]}\n{p.stderr[-3000:]}\n")
    return p.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, required=True)
    ap.add_argument("--attempt", type=int, default=1)
    a = ap.parse_args()
    sel = json.load(open(SEL))["selected"]
    lead = "C" if a.k % 2 == 1 else "MG"
    order = [lead, "MG" if lead == "C" else "C"]
    os.makedirs(ROOT, exist_ok=True)
    log = os.path.join(ROOT, f"block{a.k}_attempt{a.attempt}.driver.log")
    for sysname in order:
        d = os.path.join(ROOT, f"block{a.k}_a{a.attempt}_{sysname}")
        if os.path.exists(d):
            sys.exit(f"exists: {d}")
        if sysname == "C":
            cmd = [sys.executable, "mg45_ctime.py", "launch", "--out-dir", d, "--workers", "4", "--gpus", "0,1", "--barrier", "--warmup-n", "8"]
        else:
            cmd = [sys.executable, "mg45_launch.py", "--set", "V96", "--ckpt", sel["ckpt"], "--out-dir", d, "--workers", "2", "--gpus", "0,1",
                   "--batch", "4", "--post-thr", str(sel["threshold"]), "--warmup-d8", "--barrier"]
        rc = run(cmd, log)
        print(sysname, "rc", rc, d)
        if rc != 0:
            sys.exit(f"technical failure in {sysname}: preserve {d}; rerun whole paired block with --attempt {a.attempt + 1}")
        time.sleep(10)  # GPU 메모리 반환·clock 안정화


if __name__ == "__main__":
    main()
