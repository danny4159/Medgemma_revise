"""iter_026 D24 정식 생성 실행 (7개 요청 파일, 4 worker=2GPU x 2)."""
import sys

from rsna_diag import roi26_run as RR

jobs = ["results/iter_026/requests/D_V__M0.jsonl", "results/iter_026/requests/D_V__B0.jsonl",
        "results/iter_026/requests/D_O__M0.jsonl", "results/iter_026/requests/D_O__B0.jsonl",
        "results/iter_026/requests/D_RD__M0.jsonl", "results/iter_026/requests/D_TEXT__M0.jsonl",
        "results/iter_026/requests/D_TEXT__B0.jsonl"]
protocol = "results/iter_026/protocol_D.json"
allowed = RR.allowed_gpus()
summary = []
for rp in jobs:
    res = RR.run_one(rp, protocol, workers=4, gpus_arg="0,1", peak_gb=9.0, allowed=allowed, out_root="results/iter_026")
    summary.append(res)
    print(res, flush=True)
import json
print(json.dumps(summary))
sys.exit(0 if all(s["status"] in ("complete", "verified_complete") for s in summary) else 2)
