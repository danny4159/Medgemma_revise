"""iter_026 E60->E200 확대 판정: rsna_diag.roi26_decide.decide_e60_to_e200(승인된 모듈)을 실제로 호출한다.
이전 버전은 report 필드를 직접 재구현해 C_query 조건을 점추정 대신 CI 하한으로 잘못 대체했고 reader 격차의 부호를
반전시켰다. 이번 버전은 eval_iter026.py가 만드는 report["primary"]/report["subset"] 스키마를 그대로
roi26_decide 모듈에 넘겨 판정한다(스키마 불일치 해소)."""
import json

from rsna_diag import roi26_decide as DEC

REPORT = "results/iter_027/eval/report_E60.json"
OUT = "results/iter_027/decide/E60_to_E200_decision.json"

report = json.load(open(REPORT))
d = DEC.decide_e60_to_e200(report, OUT, REPORT)
print(json.dumps(d, indent=1))
