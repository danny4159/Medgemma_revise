"""iter_026 E60->E200 확대 판정: 계획에 사전 고정한 세 조건(기능적 차이/정밀도 보완/모듈형 격차) 중 하나 + 형식 gate."""
import hashlib
import json
import os

REPORT = "results/iter_026/eval/report_E60.json"
OUT = "results/iter_026/decide/E60_to_E200_decision.json"


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


r = json.load(open(REPORT))
fmt_ok = r["valid_rate"]["V_M0"] >= 0.95 and r["valid_rate"]["V_B0"] >= 0.95

diff_s = r["comparisons"]["S_B0_minus_S_M0"]
cq = r["C_query_ci"]
cond1 = abs(diff_s["mean_diff"]) >= 0.05 and (cq["M0"]["ci_lo"] >= 0.05 or cq["B0"]["ci_lo"] >= 0.05)

sub = r["subset"]
ci = sub["B0_direct_Q4_select_exact_ci"]
cond2 = sub["B0_rule_Q4_select_rate"] >= 0.20 and ci[0] <= 0.10 <= ci[1]

rule_gap = r["comparisons"]["S_rule_B0_minus_S_B0_direct"]["mean_diff"]
reader_gap = -r["comparisons"]["S_RD_minus_S_B0"]["mean_diff"]  # S_B0 - S_RD sign flip if reader higher
max_gap = max(rule_gap, reader_gap)
cond3 = (max_gap >= 0.10 and (r["metrics"]["V_B0"]["mean_C_query"] > 0 or sub["B0_direct_Q4_select_successes"] > 0))

reasons = {"functional_diff_candidate": cond1, "precision_supplement": cond2, "modular_gap_candidate": cond3}
passed = fmt_ok and any(reasons.values())

decision = {
    "stage": "E60_to_E200", "report_path": REPORT, "report_sha256": sha_file(REPORT),
    "format_ok": fmt_ok, "valid_rate": r["valid_rate"],
    "S_B0_minus_S_M0": diff_s, "C_query_ci": cq, "subset": sub,
    "rule_minus_direct_S": rule_gap, "reader_minus_direct_S": reader_gap,
    "reasons": reasons, "passed": passed,
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(decision, open(OUT, "w"), indent=1, default=str)
print(json.dumps(decision, indent=1))
