"""iter_026 E60/E200_extra 정식 생성 실행.
사용: python launch_iter026_e.py E60
     python launch_iter026_e.py E200_extra
"""
import json
import sys

from rsna_diag import roi26_run as RR

stage = sys.argv[1]
jobs = [f"results/iter_026/requests/{stage}_V__M0.jsonl", f"results/iter_026/requests/{stage}_V__B0.jsonl",
        f"results/iter_026/requests/{stage}_RD__M0.jsonl"]
protocol = f"results/iter_026/protocol_{stage}.json"
allowed = RR.allowed_gpus()
summary = []
for rp in jobs:
    res = RR.run_one(rp, protocol, workers=4, gpus_arg="0,1", peak_gb=9.0, allowed=allowed, out_root="results/iter_026")
    summary.append(res)
    print(res, flush=True)
print(json.dumps(summary))
sys.exit(0 if all(s["status"] in ("complete", "verified_complete") for s in summary) else 2)
