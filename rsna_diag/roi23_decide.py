"""iter_024 stage decision: D24 형식/oracle gate, E60->E200 확대 gate. 파일 존재만으로 통과하지 않는다.

decide()는 report_*.json을 직접 읽어 계획의 사전 고정 기준으로 판정하고 atomic하게 decision 파일을 쓴다
(이미 있으면 덮어쓰지 않는다: 같은 stage를 다시 결정해 유리한 결과로 바꾸지 못한다).
recheck()는 결정 파일이 참조하는 report를 다시 읽어 저장된 판정이 report 내용과 실제로 일치하는지 재계산한다
(roi23_pipeline.cmd_requests가 다음 stage 진입 전에 이 recheck를 호출한다).
"""
import hashlib
import json
import os
import sys

OUT = os.environ.get("ROI23_RUN_ROOT", "results/iter_024")
FMT_MIN_VALID = 0.95
ORACLE_MIN_ACC = 0.90
ROW_KEYS = ("D_M0", "D_B0", "L", "U", "O_M0", "O_B0")


def _sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def atomic_json(obj, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, default=str)
    os.replace(tmp, path)


def _d24_checks(report):
    valid_rates = report["valid_rates"]
    fmt_ok = {k: valid_rates[k]["rate"] >= FMT_MIN_VALID for k in ROW_KEYS}
    format_ok = all(fmt_ok.values())
    oracle = report["oracle_accuracy"]
    oracle_ok = {k: (oracle[k]["acc_over_all_questions"] is not None and oracle[k]["acc_over_all_questions"] >= ORACLE_MIN_ACC)
                 for k in ("O_M0", "O_B0")}
    oracle_pass = all(oracle_ok.values())
    return {"fmt_valid_rates": {k: valid_rates[k]["rate"] for k in ROW_KEYS}, "fmt_ok_by_key": fmt_ok, "format_ok": format_ok,
            "oracle_acc_over_all_questions": {k: oracle[k]["acc_over_all_questions"] for k in ("O_M0", "O_B0")},
            "oracle_ok_by_key": oracle_ok, "oracle_pass": oracle_pass, "passed": bool(format_ok and oracle_pass)}


def decide_d24(report_path=None, out_path=None):
    report_path = report_path or f"{OUT}/eval/report_D24.json"
    out_path = out_path or f"{OUT}/decide/D24_decision.json"
    if os.path.exists(out_path):
        raise RuntimeError(f"{out_path} exists (not overwriting)")
    report = json.load(open(report_path))
    checks = _d24_checks(report)
    decision = {"stage": "D24", "report_path": report_path, "report_sha256": _sha_file(report_path),
                "fmt_used": report.get("fmt", "plain"), **checks}
    atomic_json(decision, out_path)
    return decision


def _e_expand_checks(report):
    cmp_ = report["comparisons"]
    delta_direct = cmp_["delta_direct"]
    g_official = cmp_["G_official"]
    rb0_minus_db0 = cmp_["RB0_minus_DB0"]
    l_minus_db0 = cmp_["L_minus_DB0"]

    def point_ge(d, thr):
        return d["mean_diff"] >= thr

    def ci_contains(d, thr):
        return d["judge_ci_lo"] <= thr <= d["judge_ci_hi"]

    crit_point = point_ge(delta_direct, 0.10) or point_ge(g_official, 0.10)
    crit_reader = point_ge(rb0_minus_db0, 0.10) or point_ge(l_minus_db0, 0.10)
    ci_flags = {"delta_direct": ci_contains(delta_direct, 0.10), "G_official": ci_contains(g_official, 0.10),
                "RB0_minus_DB0": ci_contains(rb0_minus_db0, 0.10), "L_minus_DB0": ci_contains(l_minus_db0, 0.10)}
    crit_ci = any(ci_flags.values())

    valid_rates = report["valid_rates"]
    n_primary = report["n_primary"]
    import math
    q_upper = max(v["n_valid"] / v["n_total"] if v["n_total"] else 1.0 for v in valid_rates.values())
    q_upper = 1.0 - min(v["rate"] for v in valid_rates.values())  # discordance proxy: 1 - min valid rate across keys
    prec_bound = 1.96 * math.sqrt(max(q_upper, 1e-9) / max(n_primary, 1))
    crit_precision_note = {"q_upper_proxy": q_upper, "n_primary": n_primary, "bound_1_96_sqrt_q_over_n": prec_bound,
                           "bound_le_0_12": prec_bound <= 0.12}

    expand = bool(crit_point or crit_reader or crit_ci)
    return {"delta_direct": delta_direct, "G_official": g_official, "RB0_minus_DB0": rb0_minus_db0, "L_minus_DB0": l_minus_db0,
            "crit_point_estimate_ge_0.10": crit_point, "crit_reader_ge_0.10": crit_reader, "ci_contains_0.10": ci_flags,
            "crit_ci_contains_0.10": crit_ci, "precision_note": crit_precision_note, "expand": expand}


def decide_e(stage, report_path=None, out_path=None):
    report_path = report_path or f"{OUT}/eval/report_{stage}.json"
    out_path = out_path or f"{OUT}/decide/{stage}_decision.json"
    if os.path.exists(out_path):
        raise RuntimeError(f"{out_path} exists (not overwriting)")
    report = json.load(open(report_path))
    checks = _e_expand_checks(report)
    decision = {"stage": stage, "report_path": report_path, "report_sha256": _sha_file(report_path), **checks}
    atomic_json(decision, out_path)
    return decision


def recheck(decision_path):
    """decision 파일이 가리키는 report를 다시 읽어 저장된 필드를 재계산하고, 재계산 결과와 저장된 값이 같은지 확인한다."""
    d = json.load(open(decision_path))
    report_path = d["report_path"]
    if not os.path.exists(report_path):
        raise RuntimeError(f"decision {decision_path} refers to missing report {report_path}")
    cur_sha = _sha_file(report_path)
    if cur_sha != d["report_sha256"]:
        raise RuntimeError(f"report {report_path} changed since decision {decision_path} was made")
    report = json.load(open(report_path))
    if d["stage"] == "D24":
        recomputed = _d24_checks(report)
        key = "passed"
    else:
        recomputed = _e_expand_checks(report)
        key = "expand"
    if recomputed[key] != d[key]:
        raise RuntimeError(f"decision {decision_path} field {key} does not match recomputed value from {report_path}")
    return d


def main():
    stage = sys.argv[1]
    if stage == "D24":
        print(json.dumps(decide_d24(), default=str))
    else:
        print(json.dumps(decide_e(stage), default=str))


if __name__ == "__main__":
    main()
