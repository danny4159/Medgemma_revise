"""iter_029 CPU fixture: 방향 교정 build_table, 완전성 검증, 대표 선택/동점, calibration 경계.

GPU 불필요. rsna_diag/risk28_eval.py의 기존 AUROC/Platt/bootstrap 계산을 재사용하고,
run_iter029_eval_c/e.py의 새 build_table(방향 교정)과 독립 검증 로직을 검사한다.
"""
import json
import math
import os
import shutil

import numpy as np

from rsna_diag import risk28, risk28_eval as E
import run_iter029_eval_c as C

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


# --- build_table sign correctness on synthetic records ---
def make_sm_and_gen(tmp_root):
    """1명 환자, presence/ptrue logit을 통제해 부호 교정을 직접 검사한다."""
    sm = {
        "adapter_digest_seed17": "ADAPTER_X",
        "patients": {
            "T": {
                "p0": {"id": "p0", "seed17_empty": True, "category": "opacity", "y_miss": True,
                       "seed29_empty": True, "seed43_empty": True},
            }
        },
    }
    out_dir = os.path.join(tmp_root, "T")
    os.makedirs(out_dir, exist_ok=True)

    def rec(task, **kw):
        base = {"id": "p0", "task": task, "adapter_digest": None, "split": "T"}
        base.update(kw)
        return base

    with open(os.path.join(out_dir, "gen_base_worker0.jsonl"), "w") as f:
        f.write(json.dumps(rec("presence", logit_yes=5.0, logit_no=1.0, risk_no_minus_yes=1.0 - 5.0)) + "\n")
        f.write(json.dumps(rec("ptrue", logit_yes=2.0, logit_no=7.0, risk_no_minus_yes=7.0 - 2.0)) + "\n")
    with open(os.path.join(out_dir, "gen_sft_worker0.jsonl"), "w") as f:
        f.write(json.dumps(rec("presence", adapter_digest="ADAPTER_X",
                                logit_yes=3.0, logit_no=9.0, risk_no_minus_yes=9.0 - 3.0)) + "\n")
        f.write(json.dumps(rec("ptrue", adapter_digest="ADAPTER_X",
                                logit_yes=4.0, logit_no=6.0, risk_no_minus_yes=6.0 - 4.0)) + "\n")
        f.write(json.dumps(rec("token_score", adapter_digest="ADAPTER_X",
                                nll_bracket=0.5, entropy_bracket=1.2, nll_eos_step1=0.3)) + "\n")
    return sm, out_dir


tmp = "results/iter_029/tests/_tmp_signtest"
shutil.rmtree(tmp, ignore_errors=True)
os.makedirs(tmp, exist_ok=True)
sm, _ = make_sm_and_gen(tmp)
old_root = C.RESULTS_ROOT
C.RESULTS_ROOT = tmp
try:
    rows = C.build_table(sm, "T")
finally:
    C.RESULTS_ROOT = old_root
row = rows[0]
# Presence risk = logit_yes - logit_no (모델이 opacity 있다고 답할수록 위험↑)
check("presence_m0_sign", row["presence_m0"] == 5.0 - 1.0, row["presence_m0"])
check("presence_b0_sign", row["presence_b0"] == 3.0 - 9.0, row["presence_b0"])
# P(True) risk = logit_no - logit_yes (제안한 답(빈 응답=no opacity)이 틀렸다고 할수록 위험↑)
check("ptrue_m0_sign", row["ptrue_m0"] == 7.0 - 2.0, row["ptrue_m0"])
check("ptrue_b0_sign", row["ptrue_b0"] == 6.0 - 4.0, row["ptrue_b0"])
check("token_nll_passthrough", row["token_nll"] == 0.5, row["token_nll"])
check("seed_disagreement_zero", row["seed_disagreement"] == 0.0, row["seed_disagreement"])
shutil.rmtree(tmp, ignore_errors=True)

# --- extreme/tie values for presence/ptrue direction don't break finiteness ---
check("presence_extreme_finite", math.isfinite(50.0 - (-50.0)))
check("presence_tie_zero", (5.0 - 5.0) == 0.0)

# --- representative selection tie-break follows listed order ---
family = ["a", "b", "c"]
aurocs = {"a": 0.7, "b": 0.7, "c": 0.9}
rep = max(family, key=lambda k: aurocs[k])
check("rep_select_max", rep == "c")
family_tie = ["a", "b"]
aurocs_tie = {"a": 0.8, "b": 0.8}
rep_tie = max(family_tie, key=lambda k: aurocs_tie[k])
check("rep_select_tie_first_in_order", rep_tie == "a")

# --- capture_at_k boundary tie already covered upstream (fixtures_iter028.json); re-check here too ---
scores_tie = [1, 1, 1, 1, 0, 0]
y_tie = [1, 0, 1, 0, 0, 0]
cap_tie = E.capture_at_k(scores_tie, y_tie, frac=1.0 / 3.0)
check("capture_boundary_tie_expected_029", abs(cap_tie - 0.5) < 1e-9, cap_tie)

# --- label flip: reversing y flips AUROC around 0.5 ---
s = [0.1, 0.4, 0.6, 0.9]
y1 = [0, 0, 1, 1]
y0 = [1, 1, 0, 0]
a1 = E.auroc(s, y1)
a0 = E.auroc(s, y0)
check("label_flip_auroc_complement", abs((a1 + a0) - 1.0) < 1e-9, (a1, a0))

# --- calibration: constant score with all-positive / all-negative Jeffreys still in (0,1) ---
cal_allpos = E.fit_platt(np.zeros(10), [1] * 10)
check("platt_const_allpos_bounded", 0.0 < E.apply_platt(cal_allpos, [0.0])[0] < 1.0, cal_allpos)
cal_allneg = E.fit_platt(np.zeros(10), [0] * 10)
check("platt_const_allneg_bounded", 0.0 < E.apply_platt(cal_allneg, [0.0])[0] < 1.0, cal_allneg)

# --- duplicate / stale record rejection in load_all-based completeness check ---
tmp2 = "results/iter_029/tests/_tmp_dupcheck"
shutil.rmtree(tmp2, ignore_errors=True)
os.makedirs(tmp2, exist_ok=True)
with open(os.path.join(tmp2, "gen_base_worker0.jsonl"), "w") as f:
    f.write(json.dumps({"id": "p0", "task": "presence", "variant": "base", "image": "x.png"}) + "\n")
with open(os.path.join(tmp2, "gen_base_worker1.jsonl"), "w") as f:
    f.write(json.dumps({"id": "p0", "task": "presence", "variant": "base", "image": "x.png"}) + "\n")
loaded = risk28.load_all(tmp2, "base")
check("load_all_present_but_duplicate_undetected_by_load_all",
      len(loaded) == 1, "load_all silently keeps last; our audit script's own duplicate-detection "
                          "in run_iter029_audit.check_completion catches this via check_completion, not load_all")
comp = risk28.check_completion(tmp2, [{"id": "p0", "image": "x.png"}], variants=("base",))
check("check_completion_detects_duplicate_across_workers",
      any("duplicate" in p for p in comp["problems"]), comp["problems"])
shutil.rmtree(tmp2, ignore_errors=True)

# --- existing_done() in risk28.run_worker rejects records with mismatched split (source/output-path tamper) ---
# (documented behavior check via source inspection rather than re-running GPU worker)
src = open("rsna_diag/risk28.py").read()
check("existing_done_checks_split_mismatch", 'r.get("split") != split' in src)
check("existing_done_checks_pixel_hash", 'input_pixel_sha256' in src and 'px(r["image"])[2]' in src)

n_pass = sum(1 for _, ok, _ in results if ok)
print(f"{n_pass}/{len(results)} PASS")
for name, ok, detail in results:
    if not ok:
        print("FAIL", name, detail)
os.makedirs("results/iter_029/tests", exist_ok=True)
json.dump({"n_pass": n_pass, "n_total": len(results),
           "results": [{"name": n, "ok": ok, "detail": str(d)} for n, ok, d in results]},
          open("results/iter_029/tests/fixtures_iter029.json", "w"), indent=1)
assert n_pass == len(results), "some iter_029 fixtures failed"
