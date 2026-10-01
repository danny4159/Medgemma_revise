"""iter_048 paired timing block 실행기. block k(1..6)는 E/J/A 세 시스템을 순차 실행한다 (동시 실행 금지). 순서는 가능한 6개 순열을 block마다 한 번씩.
J는 block 홀수=AB, 짝수=BA (3회씩 고정 배정). 구성(worker 수 등)은 decisions/timing_config.json (D24 pilot에서 V96 결과 전에 잠금), adapter는 decisions/v96_gate.json.
python pg48_time.py --k 1 [--attempt 1]
기술 실패(비정상 종료·불완전)면 원본 dir을 보존하고 --attempt N+1 로 paired block 전체(세 시스템)를 새 dir에서 재측정한다. 느리다는 이유의 제외 금지.
"""
import argparse
import itertools
import json
import os
import subprocess
import sys
import time

ROOT = "results/iter_048/timing"
GATE = "results/iter_048/decisions/v96_gate.json"
CFG = "results/iter_048/decisions/timing_config.json"
PERMS = list(itertools.permutations(["E", "J", "A"]))  # 6 순열, 사전식


def run(cmd, log):
    t = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True)
    open(log, "a").write(f"$ {' '.join(cmd)}\nrc={p.returncode} dt={time.time() - t:.1f}\n{p.stdout[-3000:]}\n{p.stderr[-3000:]}\n")
    return p.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, required=True)
    ap.add_argument("--attempt", type=int, default=1)
    a = ap.parse_args()
    gate = json.load(open(GATE))
    cfg = json.load(open(CFG))
    order = PERMS[a.k - 1]
    jorder = "AB" if a.k % 2 == 1 else "BA"
    os.makedirs(ROOT, exist_ok=True)
    log = os.path.join(ROOT, f"block{a.k}_attempt{a.attempt}.driver.log")
    open(log, "a").write(f"# block {a.k} attempt {a.attempt} order={order} J_order={jorder}\n")
    for s in order:
        d = os.path.join(ROOT, f"block{a.k}_a{a.attempt}_{s}")
        if os.path.exists(d):
            sys.exit(f"exists: {d}")
        if s in ("E", "J"):
            cmd = [sys.executable, "pg48_ctime.py", "launch", "--system", s, "--order", jorder if s == "J" else "AB", "--adapter", gate["adapters"][s]["path"], "--out-dir", d,
                   "--workers", str(cfg[s]["workers"]), "--gpus", "0,1", "--barrier", "--warmup-n", "8", "--set", "V96", "--peak-gb", str(cfg[s]["peak_gb"])]
        else:
            cmd = [sys.executable, "mg45_launch.py", "--set", "V96", "--ckpt", "A_final", "--ckpt-path", "results/iter_046/train/U/weights_e5.pth", "--out-dir", d,
                   "--workers", str(cfg["A"]["workers"]), "--gpus", "0,1", "--batch", str(cfg["A"]["batch"]), "--post-thr", "0.8", "--warmup-d8", "--barrier"]
        rc = run(cmd, log)
        print(s, "rc", rc, d, flush=True)
        if rc != 0:
            sys.exit(f"technical failure in {s}: preserve {d}; rerun whole paired block with --attempt {a.attempt + 1}")
        time.sleep(10)  # GPU 메모리 반환·clock 안정화


if __name__ == "__main__":
    main()
