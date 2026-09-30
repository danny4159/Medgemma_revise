"""iter_040 생성 작업 순차 실행기: 각 작업마다 protocol 잠금 -> launcher(4 worker, GPU당 2) -> completion 검증.
python pg40_genjobs.py --jobs NAME=ADAPTER_DIR:REQUESTS [...] [--gate G] --workers 4 --peak-gb 9
기존 protocol/gen 디렉터리는 덮어쓰지 않는다: protocol이 있으면 requests·adapter가 같은지 확인하고 재사용, gen 디렉터리가 completion을 가지면 검증만 한다.
"""
import argparse
import json
import os
import subprocess
import sys

import pg40_run as R

PROTO = "results/iter_040/protocol/protocol_{}.json"
GEN = "results/iter_040/gen/{}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", nargs="+", required=True)
    ap.add_argument("--gate", default=None)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--peak-gb", type=float, default=9.0)
    ap.add_argument("--gpus", default="0,1")
    a = ap.parse_args()
    for j in a.jobs:
        name, rest = j.split("=", 1)
        adapter, req = rest.split(":", 1)
        adapter = None if adapter == "none" else adapter
        pp, gd = PROTO.format(name), GEN.format(name)
        if os.path.exists(pp):
            p = json.load(open(pp))
            if p["requests_path"] != req or (p["adapter"] or {}).get("path") != adapter:
                sys.exit(f"{name}: existing protocol differs from requested job")
        else:
            R.make_protocol(req, pp, adapter=adapter, gate=a.gate)
        if os.path.exists(os.path.join(gd, "completion.json")):
            R.verify_completion(gd, req, pp)
            print(f"{name}: already complete (verified)", flush=True)
            continue
        cmd = [sys.executable, "pg40_run.py", "launch", "--requests", req, "--protocol", pp, "--out-dir", gd, "--workers", str(a.workers),
               "--gpus", a.gpus, "--peak-gb", str(a.peak_gb)]
        r = subprocess.run(cmd)
        if r.returncode != 0:
            sys.exit(f"{name}: launcher failed rc={r.returncode}")
        R.verify_completion(gd, req, pp)
        print(f"{name}: complete + verified", flush=True)


if __name__ == "__main__":
    main()
