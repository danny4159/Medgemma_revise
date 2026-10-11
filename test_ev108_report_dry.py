"""ev108_report.py 전체 경로 dry-run: 실제 요청 파일과 합성 답변(재현 가능한 의사난수)으로 보고서·decision·e600 최종 경로를 끝까지 실행한다.
합성 답변은 과학 결과가 아니다. 출력은 results/iter_108/tests/dry_eval (새 폴더만)."""
import json
import sys
from pathlib import Path

import numpy as np

import ev108_report as RP
import ev108_run as RUN
import ev108_spec as S

out = Path(sys.argv[1])
if out.exists():
    sys.exit("exists")
RP.EVAL = out
rng = np.random.default_rng(7)
TEXT = ["Yes.<end_of_turn>", "No<end_of_turn>", "Abnormal<end_of_turn>", "The image shows an opacity.<end_of_turn>"]


def fake_verify(stage, d):
    rows = RUN.read_requests(str(RP.DATA / f"requests_{stage}.jsonl"))
    recs = []
    for r in rows:
        t = TEXT[int(rng.integers(0, 4))]
        recs.append({"request_id": r["request_id"], "stage": r["stage"], "cond": r["cond"], "patient": r["patient"], "target": r["target"],
                     "suffix_text_raw": t, "ended_eos": True, "runtime_s_total": 1.0, "n_input_tokens": 600, "n_output_tokens": 3, "attempts": [1]})
    return recs


RP.load_stage_records = fake_verify
for which, dirs, gate in (("p180", ["TECH=x", "P180R=x"], None), ("e600", ["TECH=x", "P180R=x", "E600R=x"], str(out / "decision_P180.json"))):
    sys.argv = ["ev108_report.py", which, "--dirs"] + dirs + (["--gate", gate] if gate else [])
    if which == "e600":
        d = json.load(open(gate))
        d["run"] = True  # dry-run 전용: 합성 결과에서 확대 경로 실행
        json.dump(d, open(out / "decision_P180_forced_for_dry_run.json", "w"))
        sys.argv[-1] = str(out / "decision_P180_forced_for_dry_run.json")
    RP.main()
print("dry-run ok")
