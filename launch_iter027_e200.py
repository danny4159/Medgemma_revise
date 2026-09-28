"""iter_027 E200_extra 완료 실행.

각 job은 실제로 어떤 protocol_digest로 이미 기록된 데이터가 있는지에 맞춰 서로 다른 protocol 파일을 쓴다:
- V_M0: iter_026에서 405/560 완료된 상태였고 원본 protocol_E200_extra.json(v1)의 digest로 기록돼 있다.
  roi26_eval.py(평가 전용, 생성 미사용)의 iter_027 수정 때문에 v1을 그대로 verify()하면 실패하므로
  allowed_edits_gen.json(생성 의미가 바뀌지 않았음을 기록한 사전 승인)을 써서 v1 digest를 그대로 재사용한다.
- V_B0: iter_027 세션 중 protocol_E200_extra_v3.json(재잠금본) digest로 388/560 기록된 상태이므로
  그 기록과 일치하도록 v3을 그대로 쓴다(폐기하면 이미 완료된 유효 생성을 버리게 된다).
- RD_M0: 아직 기록이 없으므로 v3을 그대로 쓴다.

사용: python launch_iter027_e200.py --workers 4
"""
import argparse
import json
import sys

from rsna_diag import roi26_run as RR

ap = argparse.ArgumentParser()
ap.add_argument("--workers", type=int, required=True)
ap.add_argument("--peak-gb", type=float, default=9.0)
a = ap.parse_args()

ALLOWED_EDITS_PATH = "results/iter_027/allowed_edits_gen.json"
allowed_edits = json.load(open(ALLOWED_EDITS_PATH))

jobs = [
    ("results/iter_026/requests/E200_extra_V__M0.jsonl", "results/iter_026/protocol_E200_extra.json", allowed_edits, ALLOWED_EDITS_PATH),
    ("results/iter_026/requests/E200_extra_V__B0.jsonl", "results/iter_026/protocol_E200_extra_v3.json", allowed_edits, ALLOWED_EDITS_PATH),
    ("results/iter_026/requests/E200_extra_RD__M0.jsonl", "results/iter_026/protocol_E200_extra_v3.json", allowed_edits, ALLOWED_EDITS_PATH),
]
allowed = RR.allowed_gpus()
summary = []
for rp, protocol, ae, aep in jobs:
    res = RR.run_one(rp, protocol, workers=a.workers, gpus_arg="0,1", peak_gb=a.peak_gb, allowed=allowed,
                     out_root="results/iter_026", allowed_edits=ae, allowed_edits_path=aep)
    summary.append(res)
    print(res, flush=True)
json.dump(summary, open("results/iter_027/launch_e200_summary.json", "w"), indent=1, default=str)
print(json.dumps(summary))
sys.exit(0 if all(s["status"] in ("complete", "verified_complete") for s in summary) else 2)
