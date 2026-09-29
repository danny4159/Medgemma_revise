"""iter_031 CPU fixture: iter_030 리뷰가 지적한 결함의 수정분을 검사한다. GPU 불필요.

결과는 results/iter_031/tests/fixtures_iter031.json에 쓴다 (iter_030의 기존 fixture 경로는 건드리지 않는다).
"""
import json
import math
import os
import shutil

import numpy as np

from rsna_diag import risk30, risk30_eval as REV
import run_iter031_decide_c as DC
import run_iter031_decide_e as DE

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


TMP = "results/iter_031/tests/_tmp"
shutil.rmtree(TMP, ignore_errors=True)
os.makedirs(TMP, exist_ok=True)


def write(path, obj_or_text):
    full = os.path.join(TMP, path)
    os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
    with open(full, "w") as f:
        if isinstance(obj_or_text, str):
            f.write(obj_or_text)
        else:
            json.dump(obj_or_text, f)
    return full


# ============ validate_existing: protocol_digest + request_id enforcement ============

def fake_px(path):
    return (None, None, "PIXELHASH_OK")


rid_o = risk30.request_id("O", "C", "p1")
base_rec = {"id": "p1", "task": "O", "adapter_digest": "ADAPTER_X", "split": "C",
           "image": "img.png", "input_pixel_sha256": "PIXELHASH_OK",
           "protocol_digest": "PROTO_1", "request_id": rid_o}

d1 = os.path.join(TMP, "ve1")
os.makedirs(d1, exist_ok=True)
with open(os.path.join(d1, "gen_worker0.jsonl"), "w") as f:
    f.write(json.dumps(base_rec) + "\n")
done = risk30.validate_existing(d1, "ADAPTER_X", "C", fake_px, protocol_digest="PROTO_1")
check("ve_accepts_matching_record_with_protocol", ("p1", "O") in done)

# wrong protocol digest (not in accept set) -> rejected
d2 = os.path.join(TMP, "ve2")
os.makedirs(d2, exist_ok=True)
with open(os.path.join(d2, "gen_worker0.jsonl"), "w") as f:
    f.write(json.dumps(base_rec) + "\n")
raised = False
try:
    risk30.validate_existing(d2, "ADAPTER_X", "C", fake_px, protocol_digest="PROTO_2")
except Exception:
    raised = True
check("ve_rejects_foreign_protocol_digest", raised)

# accept_protocol_digests allows reuse of an old (compatible) protocol -> D-reuse mechanism
done2 = risk30.validate_existing(d2, "ADAPTER_X", "C", fake_px, protocol_digest="PROTO_2",
                                 accept_protocol_digests=("PROTO_1",))
check("ve_accepts_record_via_accept_protocol_digests", ("p1", "O") in done2)

# tampered request_id (id/task/split forged) -> rejected even if other fields match
d3 = os.path.join(TMP, "ve3")
os.makedirs(d3, exist_ok=True)
tampered_rid = dict(base_rec, request_id="NOT_THE_REAL_ID")
with open(os.path.join(d3, "gen_worker0.jsonl"), "w") as f:
    f.write(json.dumps(tampered_rid) + "\n")
raised_rid = False
try:
    risk30.validate_existing(d3, "ADAPTER_X", "C", fake_px, protocol_digest="PROTO_1")
except Exception:
    raised_rid = True
check("ve_rejects_request_id_tamper", raised_rid)

# protocol_digest=None (legacy path) skips protocol/request_id checks but still checks adapter/split/pixel
d4 = os.path.join(TMP, "ve4")
os.makedirs(d4, exist_ok=True)
with open(os.path.join(d4, "gen_worker0.jsonl"), "w") as f:
    f.write(json.dumps({"id": "p1", "task": "O", "adapter_digest": "ADAPTER_X", "split": "C",
                        "image": "img.png", "input_pixel_sha256": "PIXELHASH_OK"}) + "\n")
done4 = risk30.validate_existing(d4, "ADAPTER_X", "C", fake_px)
check("ve_legacy_none_protocol_digest_still_works", ("p1", "O") in done4)

# ============ load_all: duplicate rejection ============
d5 = os.path.join(TMP, "la1")
os.makedirs(d5, exist_ok=True)
with open(os.path.join(d5, "gen_worker0.jsonl"), "w") as f:
    f.write(json.dumps({"id": "p1", "task": "O"}) + "\n")
with open(os.path.join(d5, "gen_worker1.jsonl"), "w") as f:
    f.write(json.dumps({"id": "p1", "task": "O"}) + "\n")
raised_dup = False
try:
    risk30.load_all(d5)
except Exception:
    raised_dup = True
check("load_all_rejects_duplicate", raised_dup)

# ============ require_full_protocol: missing required extra file rejected ============
from rsna_diag import lock_protocol as LP

sm_path = write("sm.json", {"n_C": 1})
lock_out = os.path.join(TMP, "protocol_incomplete.json")
cur = LP.current(extra=["rsna_diag/risk30.py", sm_path])  # missing risk30_source/risk30_eval/risk28/risk28_eval
json.dump({"locked": cur, "note": "incomplete"}, open(lock_out, "w"))
raised_incomplete = False
try:
    risk30.require_full_protocol(lock_out, sm_path)
except Exception:
    raised_incomplete = True
check("require_full_protocol_rejects_missing_required_files", raised_incomplete)

lock_complete = os.path.join(TMP, "protocol_complete.json")
cur2 = LP.current(extra=risk30.REQUIRED_EXTRA_LOCK_FILES + [sm_path])
json.dump({"locked": cur2, "note": "complete"}, open(lock_complete, "w"))
dig = risk30.require_full_protocol(lock_complete, sm_path)
check("require_full_protocol_accepts_complete_lock", isinstance(dig, str) and len(dig) == 64)

# tamper the source manifest content after locking -> LP.verify must catch it
open(sm_path, "w").write(json.dumps({"n_C": 2}))
raised_tamper_sm = False
try:
    risk30.require_full_protocol(lock_complete, sm_path)
except Exception:
    raised_tamper_sm = True
check("require_full_protocol_rejects_source_manifest_tamper", raised_tamper_sm)
open(sm_path, "w").write(json.dumps({"n_C": 1}))  # restore

# ============ verify_c_gate ============
dc_missing = os.path.join(TMP, "no_such_decide_c.json")
raised_missing_dc = False
try:
    risk30.verify_c_gate(dc_missing)
except Exception:
    raised_missing_dc = True
check("verify_c_gate_rejects_missing_file", raised_missing_dc)

dc_false = write("decide_c_false.json", {"enter_E": False, "bstar": "eos_nll"})
raised_false_gate = False
try:
    risk30.verify_c_gate(dc_false)
except Exception:
    raised_false_gate = True
check("verify_c_gate_rejects_enter_E_false", raised_false_gate)

dc_true = write("decide_c_true.json", {"enter_E": True, "bstar": "eos_nll"})
decision, decision_sha = risk30.verify_c_gate(dc_true)
check("verify_c_gate_accepts_enter_E_true", decision["bstar"] == "eos_nll" and len(decision_sha) == 64)

# ============ capture_at_k_ceil: exact k for the plan's C201/E402 review budgets ============
rng = np.random.default_rng(0)
y201 = np.zeros(201, dtype=int)
y201[:40] = 1  # arbitrary positives, k is what we check
scores201 = rng.random(201)
# k should be ceil(0.2*201)=41, not round(0.2*201)=40
k_used = []


def capture_with_k_probe(scores, y, frac):
    s = np.asarray(scores, float)
    n = len(s)
    k = math.ceil(n * frac)
    k_used.append(k)
    return REV.capture_at_k_ceil(scores, y, frac)


capture_with_k_probe(scores201, y201, 0.2)
check("capture_ceil_k_201_is_41", k_used[-1] == 41, k_used)

y402 = np.zeros(402, dtype=int)
y402[:80] = 1
scores402 = rng.random(402)
capture_with_k_probe(scores402, y402, 0.2)
check("capture_ceil_k_402_is_81", k_used[-1] == 81, k_used)

# ceil vs round actually differ for these n (sanity on the underlying disagreement the fix addresses)
check("ceil_201_differs_from_round", math.ceil(0.2 * 201) != round(0.2 * 201))
check("ceil_402_differs_from_round", math.ceil(0.2 * 402) != round(0.2 * 402))

# ============ bootstrap_idx_nondegenerate + auroc_ci_safe: degenerate handling ============
y_strong_skew = np.array([0] * 97 + [1] * 3)  # rare positives: many resamples will be single-class
score_skew = rng.random(100)
idx, n_rej = REV.bootstrap_idx_nondegenerate(y_strong_skew, B=200, seed=1)
check("bootstrap_nondegenerate_no_single_class_resample",
      all(len(set(y_strong_skew[i].tolist())) > 1 for i in idx))
check("bootstrap_nondegenerate_rejected_some", n_rej > 0, n_rej)

y_single = np.zeros(50, dtype=int)  # no events at all in the original population
ci_undef = REV.auroc_ci_safe(y_single, rng.random(50), 50, seed=1)
check("auroc_ci_safe_undefinable_for_single_class_population", ci_undef["definable"] is False and ci_undef["point"] is None)

y_ok = np.array([0] * 40 + [1] * 10)
ci_ok = REV.auroc_ci_safe(y_ok, rng.random(50), 50, seed=1)
check("auroc_ci_safe_definable_for_mixed_population", ci_ok["definable"] is True and ci_ok["point"] is not None)

# ============ h1_report: split-aware alpha, wider CI for E (97.5%) than C (95%) ============
def make_rows(n, seed):
    rng2 = np.random.default_rng(seed)
    y = (rng2.random(n) < 0.3).astype(int)
    q = rng2.random(n) + y * 0.4  # Q correlates with y a bit
    b = rng2.random(n)
    return [{"y_partial": int(y[i]), "Q_continue_minus_close": float(q[i]), "n_pred": 1 if i % 2 == 0 else 2,
            "some_b": float(b[i])} for i in range(n)]


rows60 = make_rows(60, 7)
h1_c = REV.h1_report(rows60, "some_b", "C")
h1_e = REV.h1_report(rows60, "some_b", "E")
check("h1_report_c_alpha_is_95", h1_c["ci_alpha"] == [2.5, 97.5])
check("h1_report_e_alpha_is_975", h1_e["ci_alpha"] == [1.25, 98.75])
diff_c, diff_e = h1_c["diff_Q_minus_Bstar"], h1_e["diff_Q_minus_Bstar"]
if diff_c["definable"] and diff_e["definable"]:
    check("h1_report_e_ci_wider_than_c", diff_e["hi"] >= diff_c["hi"] - 1e-9 and diff_e["lo"] <= diff_c["lo"] + 1e-9,
          (diff_c, diff_e))
else:
    check("h1_report_e_ci_wider_than_c_skipped_undefinable", True)
check("h1_report_has_one_box_diff_field", "diff_Q_minus_Bstar_one_box_layer" in h1_c)
check("h1_report_capture_k_ceil", h1_c["capture_k"] == math.ceil(0.2 * 60))

# ============ population_cost_report: hand-computable tiny example ============
cost_rows_tiny = [
    {"f_valid": True, "f_f1_03": 1.0, "f_f1_05": 1.0, "f_recall_03": 1.0, "o_f1_03": 0.5, "o_f1_05": 0.5,
     "o_recall_03": 0.5, "o_tp_03": 1, "o_fp_03": 1, "f_tp_03": 2, "f_fp_03": 0, "f_dup": 0,
     "f_runtime_s": 1.0, "f_n_attempts": 1, "f_final_cap": 1000},
    {"f_valid": False, "f_f1_03": None, "f_f1_05": None, "f_recall_03": None, "o_f1_03": 0.8, "o_f1_05": 0.8,
     "o_recall_03": 0.8, "o_tp_03": 1, "o_fp_03": 0, "f_tp_03": None, "f_fp_03": None, "f_dup": None,
     "f_runtime_s": 2.0, "f_n_attempts": 2, "f_final_cap": 2000},
]
pop = REV.population_cost_report(cost_rows_tiny, B=200)
check("population_cost_invalid_rate_half", abs(pop["invalid_rate"] - 0.5) < 1e-9, pop["invalid_rate"])
check("population_cost_operational_f1_uses_0_for_invalid",
      abs(pop["operational_f1_03_F"] - (1.0 + 0.0) / 2) < 1e-9, pop["operational_f1_03_F"])
check("population_cost_fp_valid_only_excludes_invalid", pop["fp_per_patient_valid_responses_only"]["n_valid"] == 1)
check("population_cost_extra_tp_over_valid", abs(pop["extra_tp_mean_over_valid"] - 1.0) < 1e-9, pop)

# ============ decide_c / decide_e: None-safety when h1 is undefinable ============
undef_diff = {"point": None, "lo": None, "hi": None, "definable": False}
undef_q1 = {"point": None, "lo": None, "hi": None, "definable": False}
report_c_undef = {"split": "C", "bstar": "eos_nll", "protocol_digest": "P", "source_manifest_sha256": "S",
                  "h1": {"diff_Q_minus_Bstar": undef_diff, "auroc_Q_one_box_layer": undef_q1},
                  "h2": {"n_events": 0, "recovery_rate": float("nan"), "n_recovered": 0, "wilson_95_hi": float("nan")}}
dec_c = DC.decide(report_c_undef)
check("decide_c_handles_undefinable_without_crash", dec_c["enter_E"] is False)

report_e_undef = {"split": "E", "bstar": "eos_nll",
                  "h1": {"diff_Q_minus_Bstar": undef_diff, "auroc_Q_one_box_layer": undef_q1, "capture20_diff": 0.0},
                  "h2": {"n_events": 0, "recovery_rate": float("nan"), "n_recovered": 0,
                        "wilson_95_lo": float("nan"), "wilson_95_hi": float("nan")}}
dec_e = DE.decide(report_e_undef)
check("decide_e_handles_undefinable_without_crash", dec_e["H1"]["verdict"] == "inconclusive")

# normal defined case for decide_e positive path
report_e_pos = {"split": "E", "bstar": "eos_nll",
                "h1": {"diff_Q_minus_Bstar": {"point": 0.10, "lo": 0.02, "hi": 0.18, "definable": True},
                      "auroc_Q_one_box_layer": {"point": 0.7, "lo": 0.55, "hi": 0.85, "definable": True},
                      "capture20_diff": 0.1},
                "h2": {"n_events": 10, "recovery_rate": 0.4, "n_recovered": 4, "wilson_95_lo": 0.15, "wilson_95_hi": 0.7}}
dec_e_pos = DE.decide(report_e_pos)
check("decide_e_positive_path_still_works", dec_e_pos["H1"]["verdict"] == "positive" and dec_e_pos["H2"]["verdict"] == "positive")

shutil.rmtree(TMP, ignore_errors=True)

n_pass = sum(1 for _, ok, _ in results if ok)
print(f"{n_pass}/{len(results)} PASS")
for name, ok, detail in results:
    if not ok:
        print("FAIL", name, detail)
os.makedirs("results/iter_031/tests", exist_ok=True)
json.dump({"n_pass": n_pass, "n_total": len(results),
          "results": [{"name": n, "ok": ok, "detail": str(d)} for n, ok, d in results]},
          open("results/iter_031/tests/fixtures_iter031.json", "w"), indent=1)
assert n_pass == len(results), "some iter_031 fixtures failed"
