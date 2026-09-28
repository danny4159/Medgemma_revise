"""iter_026 stage gate 판정 (계획에 사전 고정한 절대 기준). report 내용을 그대로 재검증한다."""
import hashlib
import json
import os

D_MIN_VALID = 92  # /96
E_MIN_VALID_RATE = 0.95


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


def decide_d(report, out_path, report_path):
    """direct M0/B0 각 96요청 중 bbox 형식 valid>=92. oracle/reader는 gate에 포함하지 않는다."""
    valid = {"V_M0": report["valid_count"]["V_M0"], "V_B0": report["valid_count"]["V_B0"]}
    ok = {k: v >= D_MIN_VALID for k, v in valid.items()}
    passed = all(ok.values())
    d = {"stage": "D", "report_path": report_path, "report_sha256": _sha_file(report_path),
         "valid_count": valid, "min_required": D_MIN_VALID, "ok_by_key": ok, "passed": passed}
    atomic_json(d, out_path)
    return d


def decide_e60_to_e200(report, out_path, report_path):
    """확대 기준 3가지 중 하나 + 형식 gate."""
    vr = report["valid_rate_primary"]
    fmt_ok = vr["V_M0"] >= E_MIN_VALID_RATE and vr["V_B0"] >= E_MIN_VALID_RATE
    diff_s = report["primary"]["S_B0_minus_S_M0"]
    cond1 = fmt_ok and abs(diff_s["mean_diff"]) >= 0.05 and (report["primary"]["C_query_B0_ci_lo"] >= 0.05
                                                              or report["primary"]["C_query_M0_ci_lo"] >= 0.05)
    subset = report["subset"]
    q4_rule = subset["B0_rule_Q4_select_rate"]
    q4_direct_ci_hi = subset["B0_direct_Q4_select_exact_ci"][1]
    cond2 = fmt_ok and q4_rule >= 0.20 and q4_direct_ci_hi >= 0.10 >= subset["B0_direct_Q4_select_exact_ci"][0]
    gap = report["primary"]["rule_or_reader_minus_B0_direct_S"]
    cond3 = (fmt_ok and gap.get("max_mean_diff", 0.0) >= 0.10
             and (report["primary"]["C_query_B0_mean"] > 0 or subset["B0_direct_Q4_select_successes"] > 0))
    reasons = {"functional_diff_candidate": cond1, "precision_supplement": cond2, "modular_gap_candidate": cond3}
    passed = fmt_ok and any(reasons.values())
    d = {"stage": "E60_to_E200", "report_path": report_path, "report_sha256": _sha_file(report_path),
         "format_ok": fmt_ok, "reasons": reasons, "passed": passed}
    atomic_json(d, out_path)
    return d


def decide_seed_expansion(report, out_path, report_path):
    """조건부 기존 seed 재현 진입: 양성 조건 충족 또는 규칙 대비 명확한 직접 활용 격차."""
    positive = report.get("positive_candidate", False)
    gap = report["primary"].get("rule_minus_B0_direct_S", {})
    clear_gap = gap.get("mean_diff", 0.0) >= 0.10 and gap.get("ci_lo", -1.0) > 0.0
    passed = bool(positive or clear_gap)
    d = {"stage": "seed_expansion", "report_path": report_path, "report_sha256": _sha_file(report_path),
         "positive_candidate": positive, "clear_rule_gap": clear_gap, "passed": passed}
    atomic_json(d, out_path)
    return d


def classify_e200(report):
    """양성/음성/불확정 후보 판정 (최종 investment 판단은 사람이 읽는 보고서에서 서술)."""
    p = report["primary"]
    sub = report["subset"]
    pos = (p["S_B0_minus_S_M0"]["mean_diff"] >= 0.05 and p["S_B0_minus_S_M0"]["ci_lo"] > 0
           and p["S_B0_minus_Copy_B0"]["mean_diff"] >= 0.05 and p["S_B0_minus_Copy_B0"]["ci_lo"] > 0
           and p["C_query_B0_ci_lo"] > 0
           and sub["B0_direct_Q4_select_rate"] >= 0.10 and sub["B0_direct_Q4_select_successes"] > 0
           and p["donor_diff_B0"]["ci_lo"] > 0)
    fmt_ok = report["valid_rate_primary"]["V_M0"] >= E_MIN_VALID_RATE and report["valid_rate_primary"]["V_B0"] >= E_MIN_VALID_RATE
    neg = (fmt_ok and sub["B0_direct_Q4_select_exact_ci"][1] < 0.10 and sub["B0_rule_Q4_select_exact_ci"][0] > 0.20)
    return {"positive_candidate": pos, "negative_candidate": neg, "inconclusive": not (pos or neg)}
