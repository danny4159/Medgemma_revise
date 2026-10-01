"""iter_047 D8 기술 gate decision (E 실행 허용 여부). D의 임상 정확도는 보지 않는다 — 형식·입력 정합성·oracle·실행 안정성만 검사한다.
python rr47_gate.py --report D8_report.json --verify D8_verify.json --workers-cmp cmp.json --resume resume.json --tamper tamper.json --out gate.json
run=true 조건(사전 고정): report의 oracle 32/32, 모든 요청 최종 EOS, 비oracle 조건별 형식 유효율 >= 0.90, 독립 verifier PASS,
2/4 worker token 불일치 0, 실제 중단·재개 token 불일치 0, 변조/중복/누락/wrong-config 거부 전부 통과.
E 자료 gate(E_data_gate.json)는 별도이며 rr47_run.make가 따로 강제한다.
"""
import argparse
import json
import os
import sys

MIN_FORMAT_VALID = 0.90


def main():
    ap = argparse.ArgumentParser()
    for k in ("report", "verify", "workers-cmp", "resume", "tamper", "out"):
        ap.add_argument("--" + k, required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("refuse to overwrite gate decision")
    rep, ver = json.load(open(a.report)), json.load(open(a.verify))
    cmp_, res, tam = json.load(open(a.workers_cmp)), json.load(open(a.resume)), json.load(open(a.tamper))
    fs = rep["format_status_counts"]
    per_cond_valid = {}
    for c in ("R1", "R2", "T", "BJ", "BI"):
        n = sum(fs[c].values())
        per_cond_valid[c] = fs[c].get("ok", 0) / n
    checks = dict(
        oracle_all_correct=rep["oracle"]["n"] == 32 and rep["oracle"]["ok"] == 32,
        all_final_eos=rep["n_non_eos_final"] == 0,
        format_valid_each_cond=all(v >= MIN_FORMAT_VALID for v in per_cond_valid.values()),
        independent_verify_pass=bool(ver["passed"]),
        workers_token_mismatch_zero=cmp_["token_mismatch"] == 0 and cmp_["n_common"] == 152,
        resume_token_mismatch_zero=res["token_mismatch"] == 0 and res["n_common"] == 152 and res["killed_midrun"] is True,
        tamper_all_rejected=bool(tam["all_rejected"]),
    )
    dec = dict(run=all(checks.values()), checks=checks, per_cond_format_valid=per_cond_valid,
               inputs=dict(report=a.report, verify=a.verify, workers_cmp=a.workers_cmp, resume=a.resume, tamper=a.tamper))
    tmp = a.out + ".tmp"
    json.dump(dec, open(tmp, "w"), indent=1)
    os.replace(tmp, a.out)
    print(json.dumps(dec, indent=1))


if __name__ == "__main__":
    main()
