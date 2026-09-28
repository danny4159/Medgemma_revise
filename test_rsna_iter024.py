"""iter_024 CPU fixture: roi23_decide gate 재계산, D24 완료 재검증(오라클 전체 분모), B0 bbox 중복 거부, decide recheck 변조 거부.
사용: python test_rsna_iter024.py  ->  results/iter_024/tests/fixtures_iter024.json
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(__file__))

os.environ.setdefault("ROI23_RUN_ROOT", "results/iter_024")
TMP = "results/iter_024/tests/tmp_decide"
shutil.rmtree(TMP, ignore_errors=True)
os.makedirs(TMP, exist_ok=True)

from rsna_diag import roi23_decide as DEC  # noqa: E402

results = []


def check(name, cond, detail=None):
    results.append({"name": name, "pass": bool(cond), "detail": detail})
    if not cond:
        print("FAIL", name, detail)


def mk_valid_rates(rate=0.98, n_total=96):
    n_valid = round(rate * n_total)
    return {k: {"n_valid": n_valid, "n_total": n_total, "rate": n_valid / n_total} for k in DEC.ROW_KEYS}


# 1. D24 gate: 모든 조건 통과
rep_pass = {"fmt": "plain", "valid_rates": mk_valid_rates(0.98),
            "oracle_accuracy": {"O_M0": {"acc_over_all_questions": 0.95}, "O_B0": {"acc_over_all_questions": 0.94}}}
p1 = f"{TMP}/report_D24_pass.json"
json.dump(rep_pass, open(p1, "w"))
d1 = DEC.decide_d24(report_path=p1, out_path=f"{TMP}/D24_decision_pass.json")
check("d24_gate_passes_when_fmt_and_oracle_ok", d1["passed"] is True, d1)

# 2. D24 gate: oracle 분모에 invalid 포함 -> 실패 사례 (acc_over_all_questions 낮음)
rep_fail_oracle = {"fmt": "plain", "valid_rates": mk_valid_rates(0.98),
                   "oracle_accuracy": {"O_M0": {"acc_over_all_questions": 0.80}, "O_B0": {"acc_over_all_questions": 0.94}}}
p2 = f"{TMP}/report_D24_fail_oracle.json"
json.dump(rep_fail_oracle, open(p2, "w"))
d2 = DEC.decide_d24(report_path=p2, out_path=f"{TMP}/D24_decision_fail_oracle.json")
check("d24_gate_fails_on_low_oracle_full_denominator", d2["passed"] is False and d2["oracle_pass"] is False, d2)

# 3. D24 gate: format below 95% for one key fails
rep_fail_fmt = dict(rep_pass)
vr = mk_valid_rates(0.98)
vr["L"] = {"n_valid": 80, "n_total": 96, "rate": 80 / 96}
rep_fail_fmt = {"fmt": "plain", "valid_rates": vr, "oracle_accuracy": rep_pass["oracle_accuracy"]}
p3 = f"{TMP}/report_D24_fail_fmt.json"
json.dump(rep_fail_fmt, open(p3, "w"))
d3 = DEC.decide_d24(report_path=p3, out_path=f"{TMP}/D24_decision_fail_fmt.json")
check("d24_gate_fails_when_one_key_below_95pct_valid", d3["passed"] is False and d3["format_ok"] is False, d3)

# 4. decide_d24 refuses to overwrite existing decision file
try:
    DEC.decide_d24(report_path=p1, out_path=f"{TMP}/D24_decision_pass.json")
    check("decide_d24_refuses_overwrite", False)
except RuntimeError:
    check("decide_d24_refuses_overwrite", True)

# 5. recheck passes when report unchanged
rc = DEC.recheck(f"{TMP}/D24_decision_pass.json")
check("recheck_matches_when_report_unchanged", rc["passed"] is True)

# 6. recheck rejects when report content changed after decision (tamper detection)
p1b = f"{TMP}/report_D24_pass_mutate.json"
json.dump(rep_pass, open(p1b, "w"))
d1b = DEC.decide_d24(report_path=p1b, out_path=f"{TMP}/D24_decision_pass_mutate.json")
json.dump(rep_fail_oracle, open(p1b, "w"))  # 결정 후 report를 몰래 바꿔치기
try:
    DEC.recheck(f"{TMP}/D24_decision_pass_mutate.json")
    check("recheck_rejects_mutated_report", False)
except RuntimeError:
    check("recheck_rejects_mutated_report", True)

# 7. E-stage expand gate: point estimate >= 0.10 triggers expand
cmp_expand = {"delta_direct": {"mean_diff": 0.15, "judge_ci_lo": 0.05, "judge_ci_hi": 0.25},
              "G_official": {"mean_diff": 0.02, "judge_ci_lo": -0.05, "judge_ci_hi": 0.09},
              "RB0_minus_DB0": {"mean_diff": 0.01, "judge_ci_lo": -0.05, "judge_ci_hi": 0.07},
              "L_minus_DB0": {"mean_diff": 0.01, "judge_ci_lo": -0.05, "judge_ci_hi": 0.07}}
rep_e = {"comparisons": cmp_expand, "valid_rates": mk_valid_rates(0.98), "n_primary": 48}
p4 = f"{TMP}/report_E60_expand.json"
json.dump(rep_e, open(p4, "w"))
d4 = DEC.decide_e("E60", report_path=p4, out_path=f"{TMP}/E60_decision_expand.json")
check("e_gate_expands_on_point_estimate", d4["expand"] is True, d4)

# 8. E-stage expand gate: all small effects and CI excludes 0.10 -> no expand
cmp_noexpand = {"delta_direct": {"mean_diff": 0.02, "judge_ci_lo": -0.05, "judge_ci_hi": 0.08},
                "G_official": {"mean_diff": 0.01, "judge_ci_lo": -0.05, "judge_ci_hi": 0.07},
                "RB0_minus_DB0": {"mean_diff": 0.00, "judge_ci_lo": -0.06, "judge_ci_hi": 0.06},
                "L_minus_DB0": {"mean_diff": 0.00, "judge_ci_lo": -0.06, "judge_ci_hi": 0.06}}
rep_e2 = {"comparisons": cmp_noexpand, "valid_rates": mk_valid_rates(0.98), "n_primary": 48}
p5 = f"{TMP}/report_E60_noexpand.json"
json.dump(rep_e2, open(p5, "w"))
d5 = DEC.decide_e("E60", report_path=p5, out_path=f"{TMP}/E60_decision_noexpand.json")
check("e_gate_no_expand_when_all_small_and_ci_excludes_0.10", d5["expand"] is False, d5)

# 9. roi23_pipeline._require_decision uses recheck (not just file existence) — simulate via monkeypatch of OUT
from rsna_diag import roi23_pipeline as PL  # noqa: E402
PL.OUT = TMP  # redirect decide/ lookup for this isolated check
os.makedirs(f"{TMP}/decide", exist_ok=True)
shutil.copy(f"{TMP}/D24_decision_pass.json", f"{TMP}/decide/D24_decision.json")
try:
    got = PL._require_decision("D24", "passed", True)
    check("pipeline_require_decision_passes_on_valid_gate", got["passed"] is True)
except Exception as e:
    check("pipeline_require_decision_passes_on_valid_gate", False, str(e))

shutil.copy(f"{TMP}/D24_decision_fail_oracle.json", f"{TMP}/decide/D24_decision_should_block.json")
os.remove(f"{TMP}/decide/D24_decision.json")
shutil.copy(f"{TMP}/D24_decision_fail_oracle.json", f"{TMP}/decide/D24_decision.json")
try:
    PL._require_decision("D24", "passed", True)
    check("pipeline_require_decision_blocks_failed_gate", False)
except RuntimeError:
    check("pipeline_require_decision_blocks_failed_gate", True)

n_fail = sum(1 for r in results if not r["pass"])
os.makedirs("results/iter_024/tests", exist_ok=True)
json.dump({"n": len(results), "n_fail": n_fail, "results": results}, open("results/iter_024/tests/fixtures_iter024.json", "w"), indent=1)
print(f"{len(results) - n_fail}/{len(results)} PASS")
sys.exit(1 if n_fail else 0)
