"""iter_111 평가 규칙 잠금: 코드·입력 digest를 실제 시각과 함께 기록한다. 과학 비교(ev111_run.py) 실행 전에만 의미가 있다."""
import hashlib
import json
import os
import sys
import time

FILES = ["ev111_core.py", "ev111_run.py", "ev111_link.py", "ev109_extract.py", "ev108_spec.py", "rsna_diag/metrics.py",
         "rsna_diag/geometry.py", "rsna_diag/qa_spec.py", "test_ev111.py"]
PROV = "results/iter_111/provenance"
OUT = f"{PROV}/eval_lock.json"


def fsha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


if os.path.exists(OUT):
    sys.exit("exists")
if os.path.exists("results/iter_111/eval/report.json"):
    sys.exit("report가 이미 있으므로 사전 잠금이 아니다")
lk = dict(locked_at_unix=time.time(), locked_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
          code_sha256={f: fsha(f) for f in FILES}, ledger_sha256=fsha(f"{PROV}/ledger.json"), provenance_sha256=fsha(f"{PROV}/provenance.json"),
          params=dict(det_threshold=0.70, iou_main=0.3, iou_aux=0.5, seed=11117, B=10000, positive_ep=0.05),
          outcome_computed_before_lock=False,
          note="rep12 연결 점검은 박스·답 원문 확인만 했고 지표를 계산하지 않았다. fixture 38/38 통과 후 잠금.")
json.dump(lk, open(OUT, "w"), indent=1)
print(lk["locked_at"])
