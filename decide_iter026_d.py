"""iter_026 D24 gate 판정."""
import json

from rsna_diag import roi26_decide as DEC

report = json.load(open("results/iter_026/eval/report_D.json"))
d = DEC.decide_d(report, "results/iter_026/decide/D_decision.json", "results/iter_026/eval/report_D.json")
print(json.dumps(d, indent=1))
