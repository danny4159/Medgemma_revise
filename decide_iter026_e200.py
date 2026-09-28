"""iter_026 E200 판정: 양성/음성/불확정 분류와 조건부 seed 확장 gate.
사용: python decide_iter026_e200.py"""
import json

from rsna_diag import roi26_decide as DEC

REPORT = "results/iter_027/eval/report_E200.json"
OUT_SEED = "results/iter_027/decide/E200_seed_expansion_decision.json"

report = json.load(open(REPORT))
cls = report.get("classification") or DEC.classify_e200(report)
print("classification:", json.dumps(cls, indent=1))

seed_d = DEC.decide_seed_expansion(report, OUT_SEED, REPORT)
print(json.dumps(seed_d, indent=1))
