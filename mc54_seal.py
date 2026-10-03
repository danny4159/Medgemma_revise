"""raw–report–verifier–decision 최종 연결 봉인 (원자적, 덮어쓰기 금지). 각 파일 digest와 verifier PASS·decision 입력 연결을 재확인한다."""
import glob
import json
import os
import sys

import mc54_run as RUN

E = "results/iter_054/eval"
rep, ver, dec, lock = (f"{E}/{n}.json" for n in ("report", "verify", "decision", "eval_lock"))
out = f"{E}/final_seal.json"
if os.path.exists(out):
    sys.exit("exists")
v, d, r = json.load(open(ver)), json.load(open(dec)), json.load(open(rep))
assert v["all_pass"] is True and v["report_sha256"] == RUN.file_sha(rep)
assert d["inputs"]["report_sha256"] == RUN.file_sha(rep) and d["inputs"]["verify_sha256"] == RUN.file_sha(ver)
assert r["provenance"]["eval_lock_sha256"] == RUN.file_sha(lock)
main = "results/iter_054/raw/main"
recs = RUN.verify_completion(main, "results/iter_054/data/requests.jsonl", "results/iter_054/protocol/protocol_main.json")
seal = {"n_records_verified": len(recs), "decision_label": d["label"],
        "files": {n: RUN.file_sha(p) for n, p in (("report", rep), ("per_pair", f"{E}/per_pair.json"), ("verify", ver), ("decision", dec), ("eval_lock", lock),
                                                   ("completion_main", f"{main}/completion.json"), ("protocol_main", "results/iter_054/protocol/protocol_main.json"),
                                                   ("protocol_tech", "results/iter_054/protocol/protocol_tech.json"),
                                                   ("tech_gate", "results/iter_054/protocol/tech_gate.json"),
                                                   ("requests", "results/iter_054/data/requests.jsonl"))},
        "worker_files": {os.path.basename(f): RUN.file_sha(f) for f in sorted(glob.glob(f"{main}/gen_worker*.jsonl"))},
        "eval_code": r["provenance"]["eval_code"]}
tmp = out + ".tmp"
json.dump(seal, open(tmp, "x"), indent=1)
os.replace(tmp, out)
print("sealed", d["label"], len(recs))
