"""iter_030 CPU fixture: 사건 계산, branch index, D24 선택, force logits processor, correction_029 decision.

GPU 불필요. rsna_diag.risk30_source/risk30의 순수 함수와 run_iter030_correction029.decide를 검사한다.
"""
import json
import math
import os
import shutil

import numpy as np

from rsna_diag import risk30_source as RS
from rsna_diag import risk30
import run_iter030_correction029 as CORR

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


# --- branch_index: last occurrence of 23131, +1 ---
check("branch_index_basic", RS.branch_index([1, 23131, 5, 23131, 236775, 106]) == 4)
check("branch_index_none", RS.branch_index([1, 2, 3]) is None)
check("branch_index_last_token", RS.branch_index([23131]) == 1)

# --- event_from_boxes: strict partial-omission event ---
gt2 = [[0, 0, 100, 100], [500, 500, 600, 600]]
pred_hit_one = [[0, 0, 100, 100]]
ev = RS.event_from_boxes(pred_hit_one, gt2, thr=0.3)
check("event_tp1_fn1_partial", ev["tp"] == 1 and ev["fn"] == 1 and ev["y_partial"] is True, ev)

pred_hit_both = [[0, 0, 100, 100], [500, 500, 600, 600]]
ev2 = RS.event_from_boxes(pred_hit_both, gt2, thr=0.3)
check("event_full_match_not_partial", ev2["tp"] == 2 and ev2["y_partial"] is False, ev2)

pred_none = []
ev3 = RS.event_from_boxes(pred_none, gt2, thr=0.3)
check("event_empty_pred_no_tp_not_partial", ev3["tp"] == 0 and ev3["y_partial"] is False, ev3)

# TP present but the *matched* box only partially overlaps a second GT that shares area 0 with all preds
gt_three = [[0, 0, 100, 100], [500, 500, 600, 600], [700, 700, 800, 800]]
pred_two = [[0, 0, 100, 100], [500, 500, 600, 600]]
ev4 = RS.event_from_boxes(pred_two, gt_three, thr=0.3)
check("event_multi_gt_one_uncovered", ev4["tp"] == 2 and ev4["fn"] == 1 and ev4["y_partial"] is True, ev4)

# --- gt_norm_boxes: recompute must match stored value within tol; mismatch raises ---
aff = (10, 20, 500)
from rsna_diag import geometry
xyxy = [30.0, 40.0, 130.0, 240.0]
correct_norm = geometry.canvas_to_norm(xyxy, *aff)
ok_entries = [{"xyxy_px": xyxy, "yxyx_norm": correct_norm}]
out = RS.gt_norm_boxes(ok_entries, aff)
check("gt_norm_boxes_matches_recomputed", out == [correct_norm], out)

bad_entries = [{"xyxy_px": xyxy, "yxyx_norm": [0, 0, 1, 1]}]
raised = False
try:
    RS.gt_norm_boxes(bad_entries, aff)
except RuntimeError:
    raised = True
check("gt_norm_boxes_mismatch_raises", raised)

# --- select_d24: 12 one-box + 12 two-box, hash-ordered, deterministic ---
def fake_manifest(n_one=15, n_two=15):
    C = {}
    for i in range(n_one):
        pid = f"one_{i:03d}"
        C[pid] = {"id": pid, "n_pred_boxes": 1}
    for i in range(n_two):
        pid = f"two_{i:03d}"
        C[pid] = {"id": pid, "n_pred_boxes": 2}
    return {"patients": {"C": C}}

m = fake_manifest()
d24 = RS.select_d24(m)
check("select_d24_counts", len(d24["one_box"]) == 12 and len(d24["two_box"]) == 12)
d24b = RS.select_d24(m)
check("select_d24_deterministic", [p["id"] for p in d24["one_box"]] == [p["id"] for p in d24b["one_box"]])
raised2 = False
try:
    RS.select_d24(fake_manifest(n_one=5, n_two=20))
except RuntimeError:
    raised2 = True
check("select_d24_raises_if_insufficient", raised2)


# --- force logits processor: forces exactly one id at the target step, passthrough otherwise ---
class FakeTensor:
    """torch 없이 make_force_processor의 __call__ 분기 로직만 검증하는 최소 모사."""
    pass


try:
    import torch as T

    def run_processor_case(prompt_len, branch_step, force_id, n_calls, vocab=10):
        proc = risk30.make_force_processor(prompt_len, branch_step, force_id)
        outs = []
        for step in range(n_calls):
            input_ids = T.zeros((1, prompt_len + step), dtype=T.long)
            scores = T.arange(vocab, dtype=T.float32).unsqueeze(0) * 1.0
            out = proc(input_ids, scores.clone())
            outs.append(out)
        return outs

    outs = run_processor_case(prompt_len=5, branch_step=2, force_id=7, n_calls=5)
    # before branch step: passthrough (unchanged scores)
    check("force_processor_passthrough_before", bool(T.equal(outs[0], T.arange(10, dtype=T.float32).unsqueeze(0))))
    check("force_processor_passthrough_after_step1", bool(T.equal(outs[1], T.arange(10, dtype=T.float32).unsqueeze(0))))
    # exactly at branch step: only force_id is finite, and it's the argmax
    at_branch = outs[2]
    check("force_processor_forces_argmax", int(at_branch.argmax()) == 7, at_branch)
    check("force_processor_only_one_finite", bool((at_branch == float("-inf")).sum() == 9), at_branch)
    # after firing once: reverts to passthrough even if input_ids length would match branch_step again is impossible
    # since step is monotonic here, but check "done" flag prevents re-firing on a hypothetical repeat call
    proc2 = risk30.make_force_processor(prompt_len=5, branch_step=2, force_id=7)
    input_ids_at2 = T.zeros((1, 7), dtype=T.long)
    s1 = proc2(input_ids_at2, T.arange(10, dtype=T.float32).unsqueeze(0).clone())
    s2 = proc2(input_ids_at2, T.arange(10, dtype=T.float32).unsqueeze(0).clone())
    check("force_processor_fires_once_only", int(s1.argmax()) == 7 and bool(T.equal(s2, T.arange(10, dtype=T.float32).unsqueeze(0))))
    torch_available = True
except ImportError:
    torch_available = False
    check("torch_unavailable_skip_processor_tests", True, "torch not importable in this env; GPU test covers real generate() path")


# --- correction_029 decide(): uses E's 97.5% CI, includes token_nll_eos, detects C/E-opposite fixture ---
def make_eval_fixture(auroc_token_nll_eos, diff_e975_lo, diff_e975_point=0.12):
    names = ["token_nll", "token_nll_eos", "entropy", "seed_disagreement", "presence_m0", "presence_b0",
             "ptrue_m0", "ptrue_b0"]
    raw_auroc = {n: 0.5 for n in names}
    raw_auroc["token_nll_eos"] = auroc_token_nll_eos
    cis = {n: {"auroc": {"point": raw_auroc[n], "lo": raw_auroc[n] - 0.1, "hi": raw_auroc[n] + 0.05},
              "capture20": {"point": 0.3, "hi": 0.3}} for n in names}
    capture = {n: 0.3 for n in names}
    capture["presence_b0"] = 0.4  # rep_V > rep_T capture so requery's v_cap>t_cap side condition can hold
    e = {"representative_T": "token_nll_eos", "representative_V": "presence_b0",
        "raw_auroc": dict(raw_auroc, random=0.5), "cis": cis,
        "capture_at_20pct": capture,
        "diff_V_minus_T_auroc_975": {"point": diff_e975_point, "lo": diff_e975_lo, "hi": diff_e975_point + 0.05}}
    c = {"representative_T": "token_nll_eos", "representative_V": "presence_b0"}
    verify = {"ok": True}
    return e, c, verify


e_pos, c_pos, v_pos = make_eval_fixture(auroc_token_nll_eos=0.55, diff_e975_lo=0.02)
d_pos = CORR.decide(e_pos, c_pos, v_pos)
check("correction_token_nll_eos_included_in_family", "token_nll_eos" in d_pos["token_family_checked"])

# case where token/seed family is negative but requery (E-based) is positive: overall stays a distinct branch
e_req, c_req, v_req = make_eval_fixture(auroc_token_nll_eos=0.5, diff_e975_lo=0.02)
d_req = CORR.decide(e_req, c_req, v_req)
check("correction_requery_uses_E_975_ci", d_req["requery_additional_info_positive"]["positive"] is True,
      d_req["requery_additional_info_positive"])

# case where C would say requery-positive but E (the correct source) says negative -> decision must follow E
e_conflict, c_conflict, v_conflict = make_eval_fixture(auroc_token_nll_eos=0.5, diff_e975_lo=-0.01)
d_conflict = CORR.decide(e_conflict, c_conflict, v_conflict)
check("correction_follows_E_not_C_on_conflict", d_conflict["requery_additional_info_positive"]["positive"] is False,
      d_conflict["requery_additional_info_positive"])

raised3 = False
try:
    CORR.decide(e_pos, {"representative_T": "wrong", "representative_V": "presence_b0"}, v_pos)
except RuntimeError:
    raised3 = True
check("correction_rejects_c_e_representative_mismatch", raised3)

raised4 = False
try:
    CORR.decide(e_pos, c_pos, {"ok": False})
except RuntimeError:
    raised4 = True
check("correction_rejects_failed_independent_verify", raised4)

# --- overwrite refusal: main() must refuse if decision.json already exists ---
tmp_out = "results/iter_030/tests/_tmp_correction_overwrite"
shutil.rmtree(tmp_out, ignore_errors=True)
os.makedirs(tmp_out, exist_ok=True)
old_out = CORR.OUT
CORR.OUT = tmp_out
os.makedirs(tmp_out, exist_ok=True)
json.dump({"pre_existing": True}, open(os.path.join(tmp_out, "decision.json"), "w"))
raised5 = False
try:
    CORR.main()
except RuntimeError:
    raised5 = True
finally:
    CORR.OUT = old_out
    shutil.rmtree(tmp_out, ignore_errors=True)
check("correction_main_refuses_overwrite", raised5)


# --- validate_existing: duplicate/tamper/stale rejection (no GPU needed) ---
tmp_ve = "results/iter_030/tests/_tmp_validate_existing"
shutil.rmtree(tmp_ve, ignore_errors=True)
os.makedirs(tmp_ve, exist_ok=True)


def fake_px(path):
    return (None, None, "PIXELHASH_OK")


base_rec = {"id": "p1", "task": "O", "adapter_digest": "ADAPTER_X", "split": "C",
           "image": "img.png", "input_pixel_sha256": "PIXELHASH_OK"}
with open(os.path.join(tmp_ve, "gen_worker0.jsonl"), "w") as f:
    f.write(json.dumps(base_rec) + "\n")
done = risk30.validate_existing(tmp_ve, "ADAPTER_X", "C", fake_px)
check("validate_existing_accepts_matching_record", ("p1", "O") in done)

# duplicate across files
with open(os.path.join(tmp_ve, "gen_worker1.jsonl"), "w") as f:
    f.write(json.dumps(base_rec) + "\n")
raised_dup = False
try:
    risk30.validate_existing(tmp_ve, "ADAPTER_X", "C", fake_px)
except Exception:
    raised_dup = True
check("validate_existing_rejects_duplicate_across_files", raised_dup)
shutil.rmtree(tmp_ve, ignore_errors=True)

# tamper: adapter_digest mismatch
os.makedirs(tmp_ve, exist_ok=True)
tampered = dict(base_rec, adapter_digest="WRONG_ADAPTER")
with open(os.path.join(tmp_ve, "gen_worker0.jsonl"), "w") as f:
    f.write(json.dumps(tampered) + "\n")
raised_tamper = False
try:
    risk30.validate_existing(tmp_ve, "ADAPTER_X", "C", fake_px)
except Exception:
    raised_tamper = True
check("validate_existing_rejects_adapter_tamper", raised_tamper)
shutil.rmtree(tmp_ve, ignore_errors=True)

# stale: split mismatch (e.g. someone points a C run at an E-produced file)
os.makedirs(tmp_ve, exist_ok=True)
stale = dict(base_rec, split="E")
with open(os.path.join(tmp_ve, "gen_worker0.jsonl"), "w") as f:
    f.write(json.dumps(stale) + "\n")
raised_stale = False
try:
    risk30.validate_existing(tmp_ve, "ADAPTER_X", "C", fake_px)
except Exception:
    raised_stale = True
check("validate_existing_rejects_split_mismatch", raised_stale)
shutil.rmtree(tmp_ve, ignore_errors=True)

# input changed since completion: pixel hash mismatch
os.makedirs(tmp_ve, exist_ok=True)
with open(os.path.join(tmp_ve, "gen_worker0.jsonl"), "w") as f:
    f.write(json.dumps(base_rec) + "\n")
raised_px = False
try:
    risk30.validate_existing(tmp_ve, "ADAPTER_X", "C", lambda p: (None, None, "DIFFERENT_HASH"))
except Exception:
    raised_px = True
check("validate_existing_rejects_changed_input_pixel", raised_px)
shutil.rmtree(tmp_ve, ignore_errors=True)

n_pass = sum(1 for _, ok, _ in results if ok)
print(f"{n_pass}/{len(results)} PASS")
for name, ok, detail in results:
    if not ok:
        print("FAIL", name, detail)
os.makedirs("results/iter_030/tests", exist_ok=True)
json.dump({"n_pass": n_pass, "n_total": len(results),
          "results": [{"name": n, "ok": ok, "detail": str(d)} for n, ok, d in results]},
          open("results/iter_030/tests/fixtures_iter030.json", "w"), indent=1)
assert n_pass == len(results), "some iter_030 fixtures failed"
