"""iter_048 순차 실행기: 여러 명령을 차례로 실행하고 첫 실패에서 멈춘다 (로그는 --log 에 이어쓰기, 종료 코드는 --log.json).
python pg48_seq.py --log results/iter_048/logs/x.log --cmd "python a.py ..." --cmd "python b.py ..."
환경(CUDA_VISIBLE_DEVICES 등)은 상속한다. 각 명령의 종료 코드·소요 시간을 기록한다 (GPU 지정은 pg43_run의 --gpus 인자 등 명령 자체가 담당).
"""
import argparse
import json
import os
import shlex
import subprocess
import sys
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--cmd", action="append", required=True)
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.log) or ".", exist_ok=True)
    res = []
    with open(a.log, "a") as lf:
        for c in a.cmd:
            t0 = time.time()
            lf.write(f"\n# {time.strftime('%F %T')} $ {c}\n")
            lf.flush()
            rc = subprocess.run(shlex.split(c), stdout=lf, stderr=subprocess.STDOUT).returncode
            res.append({"cmd": c, "rc": rc, "wall_s": time.time() - t0})
            lf.write(f"# rc={rc} wall={time.time() - t0:.1f}s\n")
            lf.flush()
            if rc != 0:
                break
    p = a.log + f".{int(time.time())}.json"
    json.dump(res, open(p, "w"), indent=1)
    print(json.dumps(res))
    sys.exit(0 if len(res) == len(a.cmd) and all(r["rc"] == 0 for r in res) else 1)


if __name__ == "__main__":
    main()
