"""평가 실행 전에 평가 소스·manifest·completion digest를 잠근다 (결과를 보기 전)."""
import json
import os
import sys

import mc54_eval as E
import mc54_run as RUN

out = sys.argv[1]
if os.path.exists(out):
    sys.exit("exists")
lk = {"eval_code": {f: RUN.file_sha(f) for f in E.EVAL_CODE}, "eval_manifest_sha256": RUN.file_sha(E.EVM),
      "completion_sha256": RUN.file_sha(os.path.join(E.MAIN, "completion.json")), "protocol_main_sha256": RUN.file_sha(E.PROTO),
      "thresholds_source": "mc54_decide.TH (plan.md Evaluation)", "bootstrap": {"n_rep": E.NREP, "seed": E.SEED},
      "primary_parser": E.PRIMARY_PARSER, "baseline_set": E.BASE}
json.dump(lk, open(out, "x"), indent=1)
print("locked", out)
