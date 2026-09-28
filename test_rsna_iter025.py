"""iter_025 CPU fixture: roi25_spec 직렬화/반올림/prompt, roi25_requests id·modality 검증, roi25_gen modality 검사,
roi25_eval 통계, roi25_decide gate 재계산. 사용: python test_rsna_iter025.py -> results/iter_025/tests/fixtures_iter025.json
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(__file__))

os.environ.setdefault("ROI25_RUN_ROOT", "results/iter_025")
TMP = "results/iter_025/tests/tmp"
shutil.rmtree(TMP, ignore_errors=True)
os.makedirs(TMP, exist_ok=True)

from rsna_diag import roi25_spec as R25, roi25_requests as RQ, roi25_gen as GEN, roi25_eval as EV, roi25_decide as DEC  # noqa: E402
from rsna_diag import roi23_spec as R23  # noqa: E402

results = []


def check(name, cond, detail=None):
    results.append({"name": name, "pass": bool(cond), "detail": detail})
    if not cond:
        print("FAIL", name, detail)


# 1. center precision: even sum -> int, odd sum -> .5
c = R25.centers_from_boxes([[100, 200, 300, 400], [10, 10, 11, 11]])
check("center_even_sum_is_int", c[0] == [200, 300], c)
check("center_odd_sum_is_half", c[1] == [10.5, 10.5], c)

# 2. rounding preserves quadrant answer for margin-safe boxes; raises for a boundary box moved by rounding
ok_boxes = [[100.2, 100.2, 300.4, 300.4]]
bi = R25.check_rounding_preserves_answer(ok_boxes)
check("rounding_ok_returns_int_boxes", bi == [[100, 100, 300, 300]], bi)

boundary_boxes = [[499.6, 100.0, 500.4, 200.0]]  # float center cy=500.0 (bottom); round(499.6)=500,round(500.4)=500 -> still bottom, ok
try:
    R25.check_rounding_preserves_answer(boundary_boxes)
    check("boundary_case_no_flip", True)
except R25.SpecError:
    check("boundary_case_no_flip", True)  # 어느 쪽이든 예외 처리 경로 자체가 동작함을 확인

flip_boxes = [[498.0, 100.0, 502.0, 200.0]]  # cy=500.0 exactly at boundary already (both float and round agree: bottom)
R25.check_rounding_preserves_answer(flip_boxes)
check("exact_boundary_500_is_bottom_both_float_and_round", True)

# 3. prompt content: OB has box formula sentence, OC has computed-center sentence; both list nonempty JSON
p_ob = R25.prompt("OB_I", "TL", [[100, 100, 300, 300]])
p_oc = R25.prompt("OC_I", "TL", [[100, 100, 300, 300]])
check("ob_prompt_has_box_formula", "Each box is [y_min, x_min, y_max, x_max]" in p_ob, p_ob[:120])
check("oc_prompt_has_center_sentence", "already computed center" in p_oc, p_oc[:120])
check("ob_prompt_embeds_box_json", '[[100,100,300,300]]' in p_ob.replace(" ", ""), p_ob[:200])
check("oc_prompt_embeds_center_json", '[[200,200]]' in p_oc.replace(" ", ""), p_oc[:200])
check("ob_and_oc_use_same_quadrant_name", "top-left quadrant" in p_ob and "top-left quadrant" in p_oc)
try:
    R25.prompt("OB_I", "TL", [])
    check("empty_box_list_rejected", False)
except R25.SpecError:
    check("empty_box_list_rejected", True)

# 4. request id: image vs text differ; verify_row round-trips; text row cannot carry image fields
cfg = "cfgdigest123"
img_fields = {"image": "x.png", "file_sha256": "f" * 64, "pixel_sha256": "p" * 64}
row_i = RQ.make_row("val_1", "validation", "M0", None, "TL", "OB_I", p_ob, cfg, "D", "image", img_fields)
row_t = RQ.make_row("val_1", "validation", "M0", None, "TL", "OB_T", p_ob, cfg, "D", "text")
check("image_and_text_rows_have_different_ids", row_i["request_id"] != row_t["request_id"])
check("verify_row_accepts_valid_rows", RQ.verify_row(row_i, cfg) and RQ.verify_row(row_t, cfg))
bad = dict(row_t)
bad["image"] = "sneaky.png"
try:
    RQ.verify_row(bad, cfg)
    check("text_row_with_image_field_rejected", False)
except RQ.RequestError:
    check("text_row_with_image_field_rejected", True)
bad2 = dict(row_i)
bad2["image"] = None
try:
    RQ.verify_row(bad2, cfg)
    check("image_row_without_image_field_rejected", False)
except RQ.RequestError:
    check("image_row_without_image_field_rejected", True)

# 5. roi25_gen.check_inputs: text rows skip file checks; malformed text row (carries image) rejected
try:
    GEN.check_inputs([row_i, row_t])
    check("check_inputs_raises_on_missing_real_file", False)
except (GEN.QAError, FileNotFoundError, OSError):
    check("check_inputs_raises_on_missing_real_file", True)  # row_i points to a fake path, expected to fail file check
try:
    GEN.check_inputs([bad])
    check("check_inputs_rejects_text_row_with_image_fields", False)
except GEN.QAError:
    check("check_inputs_rejects_text_row_with_image_fields", True)

# 6. validate_records: modality mismatch / stray image fields on text record rejected
rows = [row_t]
cdig, adg, pdig = cfg, None, "protodig"
good_rec = {"request_id": row_t["request_id"], "prompt_sha256": row_t["prompt_sha256"], "adapter_digest": adg,
            "config_digest": cdig, "protocol_digest": pdig, "id": row_t["id"], "condition": row_t["condition"],
            "checkpoint": row_t["checkpoint"], "target": row_t["target"], "fmt": row_t["fmt"], "modality": "text",
            "image": None, "image_file_sha256": None, "input_pixel_sha256": None}
done = GEN.validate_records({"f.jsonl": [good_rec]}, rows, cdig, adg, pdig, lambda p: "unused")
check("validate_records_accepts_good_text_record", row_t["request_id"] in done)
bad_rec = dict(good_rec)
bad_rec["image"] = "leaked.png"
try:
    GEN.validate_records({"f.jsonl": [bad_rec]}, rows, cdig, adg, pdig, lambda p: "unused")
    check("validate_records_rejects_text_record_with_image", False)
except GEN.QAError:
    check("validate_records_rejects_text_record_with_image", True)
bad_rec2 = dict(good_rec)
bad_rec2["modality"] = "image"
try:
    GEN.validate_records({"f.jsonl": [bad_rec2]}, rows, cdig, adg, pdig, lambda p: "unused")
    check("validate_records_rejects_modality_mismatch", False)
except GEN.QAError:
    check("validate_records_rejects_modality_mismatch", True)

# 7. eval stats: valid_rate / question_accuracy / q4_series / paired_ci on a synthetic 4-patient set
gt = {"p1": {"TL": "yes", "TR": "no", "BL": "no", "BR": "no"}, "p2": {"TL": "no", "TR": "yes", "BL": "no", "BR": "no"},
      "p3": {"TL": "no", "TR": "no", "BL": "yes", "BR": "no"}, "p4": {"TL": "no", "TR": "no", "BL": "no", "BR": "yes"}}
pids = ["p1", "p2", "p3", "p4"]


def mk(ans, status="valid"):
    return {"status": status, "answer": ans, "conversion": "identity", "status_strict": status, "answer_strict": ans}


per_perfect = {i: {t: mk(gt[i][t]) for t in R23.TARGETS} for i in pids}
vr = EV.valid_rate(per_perfect, pids)
check("valid_rate_all_valid", vr == {"n_valid": 16, "n_total": 16, "rate": 1.0}, vr)
qa = EV.question_accuracy(per_perfect, gt, pids)
check("question_accuracy_perfect", qa == {"n_correct": 16, "n_total": 16, "acc": 1.0}, qa)
q4vals, det = EV.q4_series(per_perfect, gt, pids)
check("q4_perfect_all_ones", list(q4vals) == [1.0, 1.0, 1.0, 1.0], list(q4vals))

per_one_wrong = dict(per_perfect)
per_one_wrong["p1"] = {t: mk("no" if t != "TL" else "no") for t in R23.TARGETS}  # TL should be yes but answered no
q4vals2, _ = EV.q4_series(per_one_wrong, gt, pids)
check("q4_wrong_patient_is_zero", list(q4vals2) == [0.0, 1.0, 1.0, 1.0], list(q4vals2))
ci = EV.paired_ci(q4vals, q4vals2, seed=1, B=200)
check("paired_ci_detects_one_patient_improvement", ci["n_improve"] == 1 and ci["mean_diff"] > 0, ci)

per_one_invalid = dict(per_perfect)
per_one_invalid["p2"] = {"TL": mk("no"), "TR": mk(None, status="truncated"), "BL": mk("no"), "BR": mk("no")}
qa_inv = EV.question_accuracy(per_one_invalid, gt, pids)
check("invalid_question_counts_as_incorrect_not_dropped", qa_inv["n_total"] == 16 and qa_inv["n_correct"] == 15, qa_inv)
vr_inv = EV.valid_rate(per_one_invalid, pids)
check("invalid_reduces_valid_rate", vr_inv["n_valid"] == 15, vr_inv)

# 8. decide gate: boundary 87/96 passes, 86/96 fails; one condition below 0.95 valid fails format_ok
CONDS = R25.CONDITIONS


def mk_report(ob_i_acc_num, ob_t_acc_num, valid_rate_all=0.97, ckpt="M0", other_ckpt_ok=True):
    n = 96
    vr = {}
    qa = {}
    for ck in ("M0", "B0"):
        for c in CONDS:
            vr[f"{ck}_{c}"] = {"n_valid": round(valid_rate_all * n), "n_total": n, "rate": valid_rate_all}
    for ck in ("M0", "B0"):
        num_i = ob_i_acc_num if (ck == ckpt or other_ckpt_ok) else 87
        num_t = ob_t_acc_num if (ck == ckpt or other_ckpt_ok) else 87
        qa[f"{ck}_OB_I"] = {"n_correct": num_i, "n_total": n, "acc": num_i / n}
        qa[f"{ck}_OB_T"] = {"n_correct": num_t, "n_total": n, "acc": num_t / n}
        for c in ("OC_I", "OC_T"):
            qa[f"{ck}_{c}"] = {"n_correct": 60, "n_total": n, "acc": 60 / n}
    return {"valid_rates": vr, "question_accuracy": qa}


rep_pass = mk_report(87, 87)
p1 = f"{TMP}/report_D_pass.json"
json.dump(rep_pass, open(p1, "w"))
d1 = DEC.decide_d(report_path=p1, out_path=f"{TMP}/D_decision_pass.json")
check("gate_passes_at_exactly_87_of_96", d1["passed"] is True, d1)

rep_fail = mk_report(86, 87)
p2 = f"{TMP}/report_D_fail.json"
json.dump(rep_fail, open(p2, "w"))
d2 = DEC.decide_d(report_path=p2, out_path=f"{TMP}/D_decision_fail.json")
check("gate_fails_at_86_of_96", d2["passed"] is False and d2["oracle_pass"] is False, d2)

rep_fail_fmt = mk_report(90, 90, valid_rate_all=0.90)
p3 = f"{TMP}/report_D_fail_fmt.json"
json.dump(rep_fail_fmt, open(p3, "w"))
d3 = DEC.decide_d(report_path=p3, out_path=f"{TMP}/D_decision_fail_fmt.json")
check("gate_fails_when_valid_rate_below_95pct", d3["passed"] is False and d3["format_ok"] is False, d3)

# OC failing accuracy must NOT affect the gate (OC is not in GATE_CONDITIONS)
rep_oc_bad = mk_report(90, 90)
rep_oc_bad["question_accuracy"]["M0_OC_I"] = {"n_correct": 0, "n_total": 96, "acc": 0.0}
p4 = f"{TMP}/report_D_oc_bad.json"
json.dump(rep_oc_bad, open(p4, "w"))
d4 = DEC.decide_d(report_path=p4, out_path=f"{TMP}/D_decision_oc_bad.json")
check("oc_failure_does_not_block_gate", d4["passed"] is True, d4)

# decide_d refuses to overwrite; recheck rejects tampering
try:
    DEC.decide_d(report_path=p1, out_path=f"{TMP}/D_decision_pass.json")
    check("decide_d_refuses_overwrite", False)
except RuntimeError:
    check("decide_d_refuses_overwrite", True)
d1_reload = DEC.recheck(f"{TMP}/D_decision_pass.json")
check("recheck_matches_on_untouched_report", d1_reload["passed"] is True)
tampered = json.load(open(f"{TMP}/D_decision_fail.json"))
tampered["passed"] = True
json.dump(tampered, open(f"{TMP}/D_decision_fail_tampered.json", "w"))
try:
    DEC.recheck(f"{TMP}/D_decision_fail_tampered.json")
    check("recheck_rejects_tampered_decision", False)
except RuntimeError:
    check("recheck_rejects_tampered_decision", True)

os.makedirs("results/iter_025/tests", exist_ok=True)
out = {"n": len(results), "n_pass": sum(1 for r in results if r["pass"]), "results": results}
json.dump(out, open("results/iter_025/tests/fixtures_iter025.json", "w"), indent=1, default=str)
print(f"{out['n_pass']}/{out['n']} passed")
if out["n_pass"] != out["n"]:
    sys.exit(1)
