"""기술 6명 F 12요청 재생성이 iter_016 저장 F와 (입력 ids·출력 token) 일치하는지 대조하고 다음 단계 gate decision을 쓴다.
python ev108_frepro.py <gen_dir> <decision_out.json>"""
import json
import sys
from pathlib import Path

import ev108_data as D
import ev108_run as RUN

d, out = sys.argv[1], Path(sys.argv[2])
if out.exists():
    sys.exit("exists")
recs = RUN.verify_completion(d, "results/iter_108/data/requests_FREPRO.jsonl", "results/iter_108/protocol/protocol_FREPRO.json")
F, _ = D.load_F()
rows = []
for r in recs:
    f = F[(r["patient"], r["target"])]
    rows.append({"patient": r["patient"], "target": r["target"], "input_ids_equal": r["input_ids_sha256"] == f["input_ids_sha256"],
                 "suffix_equal": r["suffix_ids"] == f["suffix_ids"], "ended_eos": r["ended_eos"], "text_new": r["suffix_text_raw"], "text_saved": f["suffix_text_raw"]})
ok = all(x["input_ids_equal"] and x["suffix_equal"] for x in rows)
dec = {"run": bool(ok), "stage": "FREPRO", "n": len(rows), "n_suffix_equal": sum(x["suffix_equal"] for x in rows),
       "n_input_ids_equal": sum(x["input_ids_equal"] for x in rows), "rows": rows, "gen_dir": d,
       "rule": "plan §5: F가 재현되지 않으면 원인 확인; 재현 시 저장 F를 주대조로 사용"}
out.write_text(json.dumps(dec, indent=1))
print(json.dumps({k: v for k, v in dec.items() if k != "rows"}))
