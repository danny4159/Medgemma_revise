"""허용 GPU의 사용 메모리가 모두 --max-used-mib 아래로 내려갈 때까지 기다린다 (다른 사용자의 프로세스는 건드리지 않는다). timing처럼 외부 부하가 결과를 오염시키는 측정 전용.
python pg48_waitgpu.py [--max-used-mib 1500] [--poll 30] [--timeout-s 570]  (rc 0=비었음, 1=timeout)
"""
import argparse
import subprocess
import sys
import time


def used():
    r = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used", "--format=csv,noheader,nounits"], capture_output=True, text=True, check=True)
    return {int(l.split(",")[0]): int(l.split(",")[1]) for l in r.stdout.strip().splitlines()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-used-mib", type=int, default=1500)
    ap.add_argument("--poll", type=int, default=30)
    ap.add_argument("--timeout-s", type=int, default=570)
    a = ap.parse_args()
    t0 = time.time()
    while time.time() - t0 < a.timeout_s:
        u = used()
        if max(u.values()) < a.max_used_mib:
            print("free", u)
            return
        time.sleep(a.poll)
    print("timeout", used())
    sys.exit(1)


if __name__ == "__main__":
    main()
