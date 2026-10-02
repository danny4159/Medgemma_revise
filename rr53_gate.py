"""iter_053 D 기술 gate decision (E 실행 허용 여부). D의 임상 정확도(R1/R2/BJ 정답률)는 보지 않는다.
검사: oracle 192/192(정답 상태·ID·결정론적 문장 연결), 모든 요청 최종 EOS, 본조건별 valid>=0.95, 독립 verifier PASS(현재 report와 연결),
pilot 2/4 worker token 불일치 0, 실제 SIGKILL 중단·재개 불일치 0, 변조·중복·누락·wrong config 거부 전부, 공식 processor tensor 검사 통과.
decision에는 모든 입력 파일의 sha256을 기록하며 rr53_run.check_gate_inputs가 protocol 생성·검증 시 다시 계산한다.

python rr53_gate.py --report R --verify V --protocol P --workers-cmp C --resume RS --tamper T --tensor X --out GATE
"""
import argparse
import json
import os
import sys

from rr53_data import OUT, file_sha

MIN_VALID = 0.95
CONDS = ("R1", "R2", "T", "BJ", "BT", "BI")
ORACLE_N = {"chexpert_D16:image": 64, "chexpert_D16:text": 64, "padchest_D8:image": 32, "padchest_D8:text": 32}


def main():
    ap = argparse.ArgumentParser()
    for k in ("report", "verify", "protocol", "workers-cmp", "resume", "tamper", "tensor", "out"):
        ap.add_argument("--" + k, required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("refuse to overwrite gate decision")
    rep, ver = json.load(open(a.report)), json.load(open(a.verify))
    cmp_, res, tam, ten = json.load(open(a.workers_cmp)), json.load(open(a.resume)), json.load(open(a.tamper)), json.load(open(a.tensor))
    orc = rep["oracle"]
    checks = dict(
        report_is_D=rep["stage"] == "D",
        oracle_all_correct=all(orc[k]["n"] == n and orc[k]["ok"] == n for k, n in ORACLE_N.items()) and set(orc) == set(ORACLE_N),
        all_final_eos=rep["n_non_eos_final"] == 0,
        valid_each_cond=all(rep["valid_rate_by_cond"][c] >= MIN_VALID for c in CONDS),
        independent_verify_pass=bool(ver["passed"]) and ver["stage"] == "D",
        verify_bound_to_report=ver["source_digests"]["report"] == file_sha(a.report) and rep["source"]["protocol_sha256"] == file_sha(a.protocol),
        workers_token_mismatch_zero=cmp_["token_mismatch"] == 0 and cmp_["n_common"] == 48 and cmp_["only_a"] == 0 and cmp_["only_b"] == 0,
        resume_token_mismatch_zero=res["token_mismatch"] == 0 and res["n_common"] == 48 and res["killed_midrun"] is True and res["completion_written"] is True,
        tamper_all_rejected=bool(tam["all_rejected"]),
        official_tensor_check_passed=bool(ten["passed"]),
    )
    inputs = {k: dict(path=p, sha256=file_sha(p)) for k, p in dict(report=a.report, verify=a.verify, protocol=a.protocol, workers_cmp=a.workers_cmp,
                                                                  resume=a.resume, tamper=a.tamper, tensor=a.tensor).items()}
    dec = dict(run=all(checks.values()), stage="D", checks=checks, valid_rate_by_cond=rep["valid_rate_by_cond"],
               data_check_sha256=file_sha(f"{OUT}/data/data_check.json"), inputs=inputs, min_valid=MIN_VALID)
    tmp = a.out + ".tmp"
    json.dump(dec, open(tmp, "w"), indent=1)
    os.replace(tmp, a.out)
    print(json.dumps(dict(run=dec["run"], checks=checks), indent=1))


if __name__ == "__main__":
    main()
