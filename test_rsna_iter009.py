"""iter_009 fixture 검증. 실행: python test_rsna_iter009.py  -> results/iter_010/tests/fixtures_reused_iter009.json (모든 항목 pass여야 exit 0)."""
import json
import math
import os
import sys
import tempfile
import zipfile

import numpy as np

from rsna_diag import generate, geometry, metrics as M, parse as PA, prompts, rsna_data as rd

R = {}


def check(name, cond, detail=None):
    R[name] = {"pass": bool(cond), "detail": detail}
    print(("PASS " if cond else "FAIL ") + name, detail if not cond else "")


def suffix(final, thinking="reason", marker=True):
    body = f"Final Answer: {final}" if marker else final
    return f"<unused94>thought\n{thinking}<unused95>{body}<end_of_turn>"


# ---- 1. 전처리 ----
L = np.array([[0, 1, 100], [200, 254, 255]], dtype=np.uint8)
out = geometry.to_uint8_rgb_preserving(L)
check("uint8_L_brightness_preserved_and_channel_replicated",
      out.shape == (2, 3, 3) and (out[:, :, 0] == L).all() and (out[:, :, 1] == L).all() and (out[:, :, 2] == L).all())
emu, _ = geometry.notebook_pad_emulation(L)
check("notebook_uint8_times_255_wraps_for_L_input_documented",
      emu[0, 2, 0] == (100 * 255) % 256 and emu[1, 2, 0] == (255 * 255) % 256 and not (emu[:2, :, 0] == L).all(),
      {"v100->": int(emu[0, 2, 0]), "v255->": int(emu[1, 2, 0]), "v0->": int(emu[0, 0, 0]), "v1->": int(emu[0, 1, 0])})
rgb = np.array([[[10, 20, 30]]], dtype=np.uint8)
check("uint8_RGB_preserved", (geometry.to_uint8_rgb_preserving(rgb) == rgb).all())
rgba = np.array([[[100, 100, 100, 128], [50, 60, 70, 255], [50, 60, 70, 0]]], dtype=np.uint8)
comp = geometry.to_uint8_rgb_preserving(rgba)
exp0 = int(math.floor(100 * 128 / 255 + 255 * (1 - 128 / 255) + 0.5))
check("RGBA_white_alpha_composite_hand_calc",
      comp[0, 0, 0] == exp0 == 177 and tuple(comp[0, 1]) == (50, 60, 70) and tuple(comp[0, 2]) == (255, 255, 255), comp.tolist())
emu_rgba, _ = geometry.notebook_pad_emulation(rgba)
check("notebook_RGBA_float_path_not_wrapped", abs(int(emu_rgba[1, 1, 0]) - 50) <= 1, emu_rgba.tolist())
try:
    geometry.to_uint8_rgb_preserving(np.zeros((2, 2), np.uint16))
    check("non_uint8_rejected_no_silent_normalization", False)
except ValueError:
    check("non_uint8_rejected_no_silent_normalization", True)

# ---- 2. padding 좌표 왕복 ----
for (h, w) in [(101, 200), (200, 101), (1024, 1024), (7, 30)]:
    img = np.full((h, w, 3), 200, np.uint8)
    pad, (top, left, side) = geometry.pad_square(img)
    assert pad.shape[:2] == (side, side) and side == max(h, w)
    assert top == ((side - h) // 2 if h < w else 0) and left == ((side - w) // 2 if w < h else 0)
    bottom, right = side - h - top, side - w - left
    box = [3.5, 2.25, min(w, 30.0), min(h, 40.0)]
    norm = geometry.canvas_to_norm(box, top, left, side)
    back = geometry.norm_to_canvas(norm, top, left, side)
    check(f"padding_roundtrip_{h}x{w}", np.allclose(back, box) and pad[top, left, 0] == 200 and
          (h == w or (pad[:top].sum() == 0 and pad[:, :left].sum() == 0 and pad[top + h:].sum() == 0 and pad[:, left + w:].sum() == 0)),
          {"top": top, "left": left, "bottom": bottom, "right": right, "floor_on_top_left": top <= bottom and left <= right})

# ---- 3. 데이터 연결 ----
with tempfile.TemporaryDirectory() as td:
    zp = os.path.join(td, "t.zip")
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("a/x.dcm", b"1")
        z.writestr("b/x.dcm", b"2")
        z.writestr("b/y.dcm", b"3")
    rz = rd.RsnaZip(zp)
    check("zip_basename_collision_detected", len(rz.collisions) == 1 and rz.collisions[0][0] == "x", rz.collisions)
    mp = os.path.join(td, "m.json")
    json.dump([{"SOPInstanceUID": "s1", "img_id": "00000001_000.png"}, {"SOPInstanceUID": "s1", "img_id": "00000002_000.png"}], open(mp, "w"))
    sm, dups = rd.load_mapping(mp)
    check("mapping_duplicate_sop_detected", dups == ["s1"])


class FakeZip:
    members = {}
    collisions = []

    def read(self, sop):
        raise KeyError(sop)


ann = {"sA": {"cats": {rd.CAT_POS}, "boxes": [{"ann_id": "a", "n": 1, "canvas": [1024, 1024], "xywh": [1, 1, 10, 10]}],
              "exclude": False, "study": "st", "series": "se", "n_ann": 1},
       "sB": {"cats": {rd.CAT_NORMAL}, "boxes": [], "exclude": False, "study": "st", "series": "se", "n_ann": 1},
       "sC": {"cats": {rd.CAT_NORMAL, rd.CAT_NLONN}, "boxes": [], "exclude": False, "study": "st", "series": "se", "n_ann": 2},
       "sD": {"cats": {rd.CAT_POS}, "boxes": [{"ann_id": "d", "n": 1, "canvas": [1024, 1024], "xywh": [1020, 1, 10, 10]}],
              "exclude": False, "study": "st", "series": "se", "n_ann": 1},
       "sE": {"cats": {rd.CAT_NORMAL}, "boxes": [], "exclude": True, "study": "st", "series": "se", "n_ann": 1}}
smap = {"sA": {"img_id": "00000001_000.png", "StudyInstanceUID": "st", "SeriesInstanceUID": "se"},
        "sC": {"img_id": "notanid.png", "StudyInstanceUID": "st", "SeriesInstanceUID": "se"},
        "sD": {"img_id": "00000004_000.png", "StudyInstanceUID": "st", "SeriesInstanceUID": "se"},
        "sE": {"img_id": "00000005_000.png", "StudyInstanceUID": "st", "SeriesInstanceUID": "se"}}
recs, _ = rd.audit_all({}, ann, smap, [], FakeZip())
check("uid_missing_in_mapping_flagged", "not_in_mapping" in recs["sB"]["reasons"])
check("uid_missing_in_zip_flagged", "not_in_zip" in recs["sA"]["reasons"])
check("ambiguous_category_flagged", any(r.startswith("calculated_cats") for r in recs["sC"]["reasons"]))
check("bbox_out_of_canvas_flagged", "out of canvas" in recs["sD"]["reasons"])
check("exclude_label_flagged", "exclude_label" in recs["sE"]["reasons"])
check("bad_img_id_flagged", "bad_img_id" in recs["sC"]["reasons"])

fake = {}
for i in range(300):
    p = f"{i:08d}"
    cat = [rd.CAT_POS, rd.CAT_NORMAL, rd.CAT_NLONN][i % 3]
    fake[f"s{i}"] = {"sop": f"s{i}", "patient": p, "category": cat, "reasons": [], "boxes": []}
fake["s_dup"] = {"sop": "s_dup", "patient": "00000000", "category": rd.CAT_NORMAL, "reasons": [], "boxes": []}
ch, bias = rd.patient_choice(fake, {"00000003"})
check("patient_exclusion_and_priority", "00000003" not in ch and ch["00000000"]["category"] == rd.CAT_POS and bias["n_patients_multi_category"] == 1)
try:
    rd.make_split(ch)
    check("insufficient_patients_raises_not_silently_shrinks", False)
except RuntimeError:
    check("insufficient_patients_raises_not_silently_shrinks", True)
bigger = {f"s{i}": {"sop": f"s{i}", "patient": f"{i:08d}", "category": [rd.CAT_POS, rd.CAT_NORMAL, rd.CAT_NLONN][i % 3],
                    "reasons": [], "boxes": []} for i in range(6000)}
chb, _ = rd.patient_choice(bigger, set())
sp, _, rsv = rd.make_split(chb)
chb2, _ = rd.patient_choice(bigger, set())
sp2, _, _ = rd.make_split(chb2)
allp = [p for v in sp.values() for p in v]
check("split_patient_disjoint_sizes_deterministic_with_reserve",
      len(allp) == len(set(allp)) and [len(sp[k]) for k in ("train", "validation", "confirm")] == [2400, 400, 800] and sp == sp2
      and not (set(allp) & {p for v in rsv.values() for p in v}) and len(rsv[rd.CAT_POS]) == 2000 - 1800)
try:
    rd.audit_all({}, ann, smap, ["dupSOP"], FakeZip())
    check("mapping_duplicate_aborts_audit", False)
except rd.AuditError:
    check("mapping_duplicate_aborts_audit", True)
_fz = FakeZip()
_fz.collisions = [("x", "a/x.dcm", "b/x.dcm")]
try:
    rd.audit_all({}, ann, smap, [], _fz)
    check("zip_collision_aborts_audit", False)
except rd.AuditError:
    check("zip_collision_aborts_audit", True)

# ---- 4. parser ----
good = '```json[{"box_2d": [10, 20, 300, 400], "label": "opacity"}]```'
r = PA.parse_response(suffix(good), True)
check("parse_valid_nonempty_official_style", r["status"] == "valid_nonempty" and r["boxes"] == [[10, 20, 300, 400]], r)
r = PA.parse_response(suffix('[{"box_2d": [1, 2, 3, 4], "label": "fake"}]', thinking='draft [{"box_2d": [900,900,950,950], "label": "x"}]'), True)
check("fake_json_inside_thinking_ignored", r["status"] == "valid_nonempty" and r["boxes"] == [[1, 2, 3, 4]])
r = PA.parse_response(suffix('[{"box_2d": [1, 2, 3, 4], "label": "a"}] ... Final Answer: [{"box_2d": [5, 6, 7, 8], "label": "b"}]'), True)
check("multiple_different_final_answers_ambiguous", r["status"] == "ambiguous", r)
r = PA.parse_response(f"<unused94>t<unused95>Final Answer: {good}\nFinal Answer: {good}<end_of_turn>", True)
check("repeated_identical_final_ok_flagged", r["status"] == "valid_nonempty" and "repeated_identical_final" in r["flags"])
r = PA.parse_response(suffix("[]"), True)
check("empty_list_valid_detection_none", r["status"] == "valid_empty" and r["boxes"] == [])
r = PA.parse_response("<unused94>thought\nlong ... [{\"box_2d\": [1,2", False)
check("truncated_separated_from_content_error", r["status"] == "truncated")
r = PA.parse_response("<unused94>thought\nsomething<end_of_turn>", True)
check("unclosed_thinking_flagged", r["status"] == "unclosed_thinking")
r = PA.parse_response(suffix('[{"box_2d": [300, 20, 100, 400], "label": "a"}]'), True)
check("inverted_endpoints_not_repaired", r["status"] == "coord_invalid" and r["boxes"] == [[300.0, 20.0, 100.0, 400.0]], r)
r = PA.parse_response(suffix('[{"box_2d": [NaN, 20, 100, 400], "label": "a"}]'), True)
check("nan_coordinate_invalid", r["status"] == "coord_invalid", r)
r = PA.parse_response(suffix('[{"box_2d": [0, 20, 1200, 400], "label": "a"}]'), True)
check("out_of_range_not_clipped", r["status"] == "coord_invalid" and r["boxes"][0][2] == 1200.0)
r = PA.parse_response(suffix('[{"box_2d": [1, 2, 30, 40], "label": " "}]'), True)
check("empty_label_schema_error", r["status"] == "schema_error")
dup = '[{"box_2d": [1, 2, 30, 40], "label": "a"}, {"box_2d": [1, 2, 30, 40], "label": "a"}]'
r = PA.parse_response(suffix(dup), True)
check("duplicate_boxes_kept_not_deduped", r["status"] == "valid_nonempty" and len(r["boxes"]) == 2 and PA.duplicates(r["boxes"]) == 1)
r = PA.parse_response("```json\n" + '[{"box_2d": [1, 2, 30, 40], "label": "a"}]' + "\n```<end_of_turn>", True)
check("no_thinking_no_marker_unique_list_allowed_flagged", r["status"] == "valid_nonempty" and "marker_missing" in r["flags"] and "fenced" in r["flags"])
r = PA.parse_response(suffix('[{"box_2d": [1, 2, 30, 40], "label": "a"'), True)
check("unbalanced_json_grammar_error", r["status"] == "grammar_error", r)
r = PA.parse_response("hello no lists<end_of_turn>", True)
check("no_json_status", r["status"] == "no_json")

# ---- 5. matching / union 손계산 ----
A, B = [0, 0, 10, 10], [5, 5, 15, 15]
check("iou_hand_calc", abs(M.iou(A, B) - 25 / 175) < 1e-12)
check("union_area_no_double_count", abs(M.union_area([A, B]) - 175) < 1e-9 and abs(M.union_area([A, A]) - 100) < 1e-9)
check("union_iou_hand_calc", abs(M.union_iou([A, B], [[0, 0, 15, 15]]) - 175 / 225) < 1e-9)
g1, g2 = [0, 0, 10, 10], [0, 8, 10, 18]
p1, p2 = [0, 0, 10, 10], [0, 7, 10, 17]
pairs = M.match([p1, p2], [g1, g2], 0.3)
check("max_cardinality_matching_two", len(pairs) == 2, pairs)
pairs = M.match([[0, 0, 10, 10]], [g1, [0, 1, 10, 11]], 0.3)
check("one_to_one_no_double_use", len(pairs) == 1)
m = M.patient_metrics([A, [900, 900, 950, 950]], [A, B], 0.3)
check("patient_metrics_hand_calc", m["tp"] == 1 and abs(m["precision"] - 0.5) < 1e-12 and abs(m["recall"] - 0.5) < 1e-12 and abs(m["f1"] - 0.5) < 1e-12)
check("empty_pred_zero_f1", M.patient_metrics([], [A], 0.3)["f1"] == 0.0)
lo, hi = M.wilson(0, 10)
lo2, hi2 = M.wilson(10, 10)
check("wilson_bounds", lo == 0 and abs(hi - 0.2775) < 1e-3 and abs(hi2 - 1) < 1e-9 and abs(lo2 - 0.7225) < 1e-3, [lo, hi, lo2, hi2])
d = M.derangement(50, 1)
check("derangement_no_fixed_point_permutation", sorted(d) == list(range(50)) and all(d[i] != i for i in range(50)))
bx, sc = M.medoid_box([[A], [[0, 0, 10, 12]], [[100, 100, 200, 200]]])
check("medoid_is_real_gt_box", bx in (A, [0, 0, 10, 12], [100, 100, 200, 200]) and bx != [100, 100, 200, 200])

# ---- 6. stale completion / 입력 변경 ----
pr = prompts.all_prompts()
env = {"model_id": "m", "model_revision": "r", "dtype": "bf16", "transformers": "t", "torch": "x", "preprocess": generate.PREPROC_VERSION,
       "chat_template_sha256": "c", "eos_token_id": [1, 106], "do_pan_and_scan": False, "image_size": "s"}
d1, _ = generate.config_digest(env, pr)
pr2 = dict(pr)
pr2["concise"] = pr["concise"] + " "
d2, _ = generate.config_digest(env, pr2)
check("config_digest_changes_with_prompt", d1 != d2)
env2 = dict(env, revision_marker=1, model_revision="r2")
d3, _ = generate.config_digest(env2, pr)
check("config_digest_changes_with_model_revision", d1 != d3)
check("prompts_extracted_from_sources", "Final Answer" in pr["official_long"] and "pulmonary opacity suspicious for pneumonia" in pr["official_long"]
      and pr["legacy_detect"].startswith("Detect the pulmonary opacity") and "{object_name}" not in pr["official_long"])

# ---- 7. evaluate.py 종단 fixture (합성 결과, 손계산 기대값) ----
from rsna_diag import evaluate as EV

def _rec(i, p, raw, eos=True):
    return {"id": i, "prompt_name": p, "suffix_text_raw": raw, "ended_eos": eos, "attempts": [{"cap": 1000}], "final_cap": 1000,
            "n_output_tokens": 10, "runtime_s_total": 1.0, "peak_mem_alloc_gb_max": 8.0}

_gt = {}
for k in range(6):
    _gt[f"p{k}"] = {"split": "s", "category": "opacity", "boxes": [{"yxyx_norm": [100, 100, 300, 300]}]}
for k in range(2):
    _gt[f"n{k}"] = {"split": "s", "category": "normal", "boxes": []}
    _gt[f"x{k}"] = {"split": "s", "category": "not_normal_no_opacity", "boxes": []}
hit = "[{\"box_2d\": [100, 100, 300, 300], \"label\": \"o\"}]"
miss = "[{\"box_2d\": [700, 700, 900, 900], \"label\": \"o\"}]"
_recs = {}
for i in _gt:
    for pn in EV.PROMPTS:
        raw = "[]"
        if i in ("p0", "p1"):
            raw = hit
        elif i in ("p2", "p3"):
            raw = miss
        elif i == "n1":
            raw = miss
        _recs[(i, pn)] = _rec(i, pn, f"<unused94>t<unused95>Final Answer: {raw}<end_of_turn>")
_recs[("p4", "official_long")] = _rec("p4", "official_long", "<unused94>t", eos=False)
res, _, _, _ = EV.evaluate(_recs, _gt, "s", prior_box=[100, 100, 300, 300], B=200)
pm = res["primary"]
check("evaluate_common_hard_mismatch_hand_count", pm["common_hard_mismatch"]["k"] == 2 and pm["common_hard_mismatch"]["n"] == 6 and pm["common_ids"] == ["p2", "p3"], pm["common_hard_mismatch"])
check("evaluate_truncated_counted_as_invalid_not_hard", res["prompts"]["official_long"]["status_positive"].get("truncated") == 1 and "p4" not in res["prompts"]["official_long"]["hard_mismatch"]["ids"])
check("evaluate_verdict_not_evaluable_when_valid_below_95", pm["verdict"] == "not_evaluable_valid_output_rate_below_95pct")
check("evaluate_f1_end_to_end_hand_calc_concise", abs(res["prompts"]["concise"]["f1@0.3_end_to_end"] - 2 / 6) < 1e-9)
check("evaluate_official_f1_truncated_zero", abs(res["prompts"]["official_long"]["f1@0.3_end_to_end"] - 2 / 6) < 1e-9)
check("evaluate_negative_extra_prediction_rate", res["prompts"]["concise"]["neg_Normal"]["valid_nonempty"]["k"] == 1 and res["prompts"]["concise"]["neg_Normal"]["valid_empty"]["k"] == 1)
check("evaluate_prior_baseline_hand_calc", abs(res["baselines"]["prior_f1@0.3"] - 2 / 6 * 0 - res["baselines"]["prior_f1@0.3"]) < 1e-12 and abs(res["baselines"]["prior_f1@0.3"] - 1.0) < 1e-12)
check("evaluate_missing_requests_reported", len(EV.evaluate({k: v for k, v in _recs.items() if k != ("p0", "concise")}, _gt, "s", None, 50)[0]["missing_requests"]) == 1)

OUT = sys.argv[1] if len(sys.argv) > 1 else "results/iter_010/tests"
os.makedirs(OUT, exist_ok=True)
json.dump(R, open(os.path.join(OUT, "fixtures_reused_iter009.json"), "w"), indent=1)
n_fail = sum(1 for v in R.values() if not v["pass"])
print(f"{len(R) - n_fail}/{len(R)} pass")
sys.exit(1 if n_fail else 0)
