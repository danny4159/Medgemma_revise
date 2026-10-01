"""iter_046 V96 추론/timing 실행기 (기본 python).

  python mg46_timing.py v96     최종 A checkpoint의 V96 192문장 추론 (2 GPU x 1 worker, batch 4; D24 cfg 비교로 확정한 구성은 --workers/--batch로 지정)
  python mg46_timing.py block --k 1 [--attempt 1]   A와 P의 paired timing block (동시 실행 금지, 선행 순서 A/P/A/P/A/P)
  python mg46_timing.py cfg --label A_final   D24에서 구성(worker/batch) 비교용 실행 (선택 성능과 무관, 출력 정합성·처리량·peak 기록)
기술 실패(비정상 종료·불완전)면 원본 dir을 보존하고 --attempt N+1 로 paired block 전체를 재측정한다. 느리다는 이유의 제외 금지.
최종 checkpoint는 decisions/final_selection.json (V96 이전 D24 선택, 잠금됨).
"""
import argparse
import json
import os
import subprocess
import sys
import time

ROOT = "results/iter_046"
FINAL = f"{ROOT}/decisions/final_selection.json"
TIMING = f"{ROOT}/timing"


def run(cmd, log):
    t = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True)
    with open(log, "a") as f:
        f.write(f"$ {' '.join(cmd)}\nrc={p.returncode} dt={time.time() - t:.1f}\n{p.stdout[-3000:]}\n{p.stderr[-3000:]}\n")
    return p.returncode


def launch_cmd(sysname, d, fin, workers=2, batch=4, set_="V96", timing=True):
    if sysname == "A":
        cmd = [sys.executable, "mg45_launch.py", "--set", set_, "--ckpt", "A_final", "--ckpt-path", fin["ckpt_path"], "--out-dir", d]
        thr = fin["selected_threshold"]
    else:
        cmd = [sys.executable, "mg45_launch.py", "--set", set_, "--ckpt", "P", "--out-dir", d]
        thr = 0.4
    cmd += ["--workers", str(workers), "--gpus", "0,1", "--batch", str(batch)]
    if timing:
        cmd += ["--post-thr", str(thr), "--warmup-d8", "--barrier"]
    return cmd


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("v96")
    v.add_argument("--workers", type=int, default=2)
    v.add_argument("--batch", type=int, default=4)
    b = sub.add_parser("block")
    b.add_argument("--k", type=int, required=True)
    b.add_argument("--attempt", type=int, default=1)
    c = sub.add_parser("cfg")
    c.add_argument("--workers", type=int, required=True)
    c.add_argument("--batch", type=int, required=True)
    c.add_argument("--tag", required=True)
    a = ap.parse_args()
    fin = json.load(open(FINAL))
    if a.cmd == "v96":
        d = f"{ROOT}/mg/V96_A_w2b4"
        sys.exit(subprocess.call(launch_cmd("A", d, fin, a.workers, a.batch, "V96", timing=False)))
    if a.cmd == "cfg":
        d = f"{ROOT}/cfg/D24_A_{a.tag}"
        sys.exit(subprocess.call(launch_cmd("A", d, fin, a.workers, a.batch, "D24", timing=False)))
    # block
    os.makedirs(TIMING, exist_ok=True)
    ap_ = f"{TIMING}/attempts.json"
    if a.attempt != 1:
        cur = json.load(open(ap_)) if os.path.exists(ap_) else {}
        cur[str(a.k)] = a.attempt
        json.dump(cur, open(ap_, "w"))
    lead = "A" if a.k % 2 == 1 else "P"
    order = [lead, "P" if lead == "A" else "A"]
    log = f"{TIMING}/block{a.k}_attempt{a.attempt}.driver.log"
    for s in order:
        d = f"{TIMING}/block{a.k}_a{a.attempt}_{s}"
        if os.path.exists(d):
            sys.exit(f"exists: {d}")
        rc = run(launch_cmd(s, d, fin), log)
        print(s, "rc", rc, d, flush=True)
        if rc != 0:
            sys.exit(f"technical failure in {s}: preserve {d}; rerun whole paired block with --attempt {a.attempt + 1}")
        time.sleep(10)


if __name__ == "__main__":
    main()
