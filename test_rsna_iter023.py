"""iter_023 CPU fixture: quadrant geometry, parser 재사용, D24/E60/E200 선택 재현성, CI/permutation 통계.
사용: python test_rsna_iter023.py  ->  results/iter_023/tests/fixtures_iter023.json
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from rsna_diag import qa_requests as QR, roi23_data as D, roi23_eval as E, roi23_requests as Q, roi23_spec as R

results = []


def check(name, cond, detail=None):
    results.append({"name": name, "pass": bool(cond), "detail": detail})
    if not cond:
        print("FAIL", name, detail)


# 1. quadrant/center/margin
check("center_simple", R.center_yx([0, 0, 100, 200]) == (50.0, 100.0))
check("quadrant_tl", R.quadrant_of(100, 100) == "TL")
check("quadrant_boundary_to_lower_right", R.quadrant_of(500, 500) == "BR")
check("quadrant_500_y_only", R.quadrant_of(500, 100) == "BL")
check("quadrant_500_x_only", R.quadrant_of(100, 500) == "TR")
check("quadrant_tr", R.quadrant_of(100, 900) == "TR")
check("quadrant_bl", R.quadrant_of(900, 100) == "BL")
check("quadrant_br", R.quadrant_of(900, 900) == "BR")
check("margin_ok_true", R.margin_ok([[0, 0, 100, 100]]) is True)
check("margin_ok_false_near_vertical", R.margin_ok([[0, 490, 100, 510]]) is False)
check("margin_ok_false_near_horizontal", R.margin_ok([[490, 0, 510, 100]]) is False)
check("margin_boundary_exactly_25_ok", R.margin_ok([[0, 0, 450, 450]]) is True)  # center (225,225): |225-500|=275>=25

box_a = {"ann_id": "a", "yxyx_norm": [0, 0, 100, 100]}   # area 100*100=10000, center (50,50) TL
box_b = {"ann_id": "b", "yxyx_norm": [0, 600, 300, 900]}  # area 300*300=90000, center (150,750) TR
check("largest_box_quadrant_picks_bigger", R.largest_box_quadrant([box_a, box_b]) == "TR")
box_c = {"ann_id": "c", "yxyx_norm": [600, 0, 700, 100]}  # area 100*100=10000 tie with box_a
tie_pick = R.largest_box_quadrant([box_a, box_c])
check("largest_box_quadrant_tie_by_ann_id", tie_pick == "TL", {"got": tie_pick})  # 'a' < 'c'

check("answers_multi_box", R.answers([[0, 0, 100, 100], [900, 900, 950, 950]]) == {"TL": "yes", "TR": "no", "BL": "no", "BR": "yes"})
check("answers_no_box", R.answers([]) == {t: "no" for t in R.TARGETS})

# 2. parser 재사용 (target != "A"이므로 Normal/Abnormal 대응 없음)
st, ans, conv = R.parse_semantic("TL", "plain", "yes<end_of_turn>", True)
check("semantic_plain_valid", (st, ans, conv) == ("valid", "yes", "identity"))
st, ans, conv = R.parse_semantic("TL", "plain", "  No.  <end_of_turn>", True)
check("semantic_strict_already_handles_trailing_punct", (st, ans, conv) == ("valid", "no", "identity"))
st, ans, conv = R.parse_semantic("TL", "json", "no<end_of_turn>", True)  # json 요청에 plain 답: strict 실패, bare_yes_no로 구제
check("semantic_bare_word_rescues_plain_under_json_fmt", (st, ans, conv) == ("valid", "no", "bare_yes_no"))
st, ans, conv = R.parse_semantic("TL", "plain", "normal<end_of_turn>", True)
check("semantic_no_normal_abnormal_for_quadrant_target", st != "valid", {"got": (st, ans, conv)})
st, ans, conv = R.parse_semantic("TL", "json", '{"answer":"yes"}<end_of_turn>', True)
check("semantic_json_valid", (st, ans, conv) == ("valid", "yes", "identity"))
st, ans, conv = R.parse_semantic("TL", "plain", "yes", False)
check("semantic_truncated", st == "truncated")
st, ans, conv = R.parse_semantic("TL", "plain", "[]<end_of_turn>", True)
check("semantic_bbox_list_not_valid", st != "valid")

# 3. D24/E60/E200 재현성 (계획서 수치와 대조)
val_items, val_gts = D.load_val_pool()
chosen, counts = D.select_d24(val_items, val_gts)
check("d24_layer_candidates", counts == {"TL": 28, "TR": 19, "BL": 58, "BR": 53}, counts)
check("d24_n", len(chosen) == 24, len(chosen))
gta = {i: R.answers([b["yxyx_norm"] for b in val_gts[i]["boxes"]]) for i in chosen}
yes_counts = {t: sum(1 for i in chosen if gta[i][t] == "yes") for t in R.TARGETS}
check("d24_yes_counts", yes_counts == {"TL": 8, "TR": 7, "BL": 11, "BR": 13}, yes_counts)
nbox = {}
for i in chosen:
    n = len(val_gts[i]["boxes"])
    nbox[n] = nbox.get(n, 0) + 1
check("d24_box_count_dist", nbox == {1: 10, 2: 12, 3: 2}, nbox)
chosen2, counts2 = D.select_d24(val_items, val_gts)
check("d24_deterministic_rerun", chosen2 == chosen)

conf_items, conf_gts = D.load_confirm_pool()
D.check_disjoint(val_items.keys(), conf_items.keys())
vpix = {v["pixel_sha256"] for v in val_items.values()}
cpix = {v["pixel_sha256"] for v in conf_items.values()}
check("val_confirm_id_disjoint_and_no_pixel_overlap", len(vpix & cpix) == 0)
prim60, bnd60 = D.e_set("E180", conf_gts)
prim200, bnd200 = D.e_set("E600", conf_gts)
check("e60_margin_split", (len(prim60), len(bnd60)) == (48, 12), (len(prim60), len(bnd60)))
check("e200_margin_split", (len(prim200), len(bnd200)) == (160, 40), (len(prim200), len(bnd200)))
check("e60_subset_of_e200_primary_or_boundary", set(prim60) | set(bnd60) <= set(prim200) | set(bnd200))

# D24 patients must not be exam-duplicated with confirm pool ids (different prefixes; check disjoint too)
check("d24_subset_of_val_pool", set(chosen) <= set(val_items))

# 4. request row 구성/검증 (make_row + verify_row round trip)
cfg = "cfgdigest_test"
it = val_items[chosen[0]]
row = QR.make_row(it, "M0", None, "TL", "plain", "direct", R.qa_prompt("TL", "plain"), None, cfg, "unit_test")
check("make_row_verify_direct", Q.verify_row(row, cfg) is True)
ev_txt = R.evidence_text("predicted", [[0, 0, 100, 100]])
row2 = QR.make_row(it, "M0", None, "TL", "plain", "ev_predicted", R.qa_prompt("TL", "plain", ev_txt), R.sha(ev_txt), cfg, "unit_test")
check("make_row_verify_evidence", Q.verify_row(row2, cfg) is True)
try:
    bad = dict(row)
    bad["prompt"] = bad["prompt"] + " tampered"
    Q.verify_row(bad, cfg)
    check("verify_row_rejects_tamper", False)
except Q.RequestError:
    check("verify_row_rejects_tamper", True)

# 5. 통계: clopper_pearson, paired_ci 퇴화 처리, permutation
lo, hi = E.clopper_pearson(0, 0)
check("cp_n0_nan", np.isnan(lo) and np.isnan(hi))
lo, hi = E.clopper_pearson(5, 10, alpha=0.05)
check("cp_5_of_10_matches_known_table", abs(lo - 0.1871) < 0.01 and abs(hi - 0.8129) < 0.01, (lo, hi))
lo, hi = E.clopper_pearson(0, 20, alpha=0.05)
check("cp_0_of_20_upper_matches_known", abs(hi - 0.1684) < 0.01, (lo, hi))

a_all_zero = np.zeros(20)
b_all_zero = np.zeros(20)
r = E.paired_ci(a_all_zero, b_all_zero, seed=23023, B=2000)
check("paired_ci_degenerate_flagged", r["degenerate"] is True and r["ci_lo"] == 0.0 and r["ci_hi"] == 0.0, r)
check("paired_ci_degenerate_has_cp_bounds", "cp_improve_prop_ci" in r and "cp_worsen_prop_ci" in r)

rng = np.random.default_rng(0)
a = rng.integers(0, 2, size=30).astype(float)
b = rng.integers(0, 2, size=30).astype(float)
r2 = E.paired_ci(a, b, seed=23023, B=2000)
check("paired_ci_nondegenerate_no_cp", (r2["degenerate"] is False) or (r2["ci_lo"] != r2["ci_hi"]), r2)

gtm = np.array([[1, 0, 0, 1]] * 10)
predm = gtm.copy()
res = E.permutation_association(predm, gtm, seed=1, B=500)
check("permutation_perfect_match_obs_is_1", res["observed_accuracy"] == 1.0, res)

# 6. rule scoring (bbox invalid handling; R baseline)
gt = {"p1": {"boxes": [{"ann_id": "a", "yxyx_norm": [0, 0, 100, 100]}]}}
bbox_by_id = {"p1": ([[0, 0, 100, 100]], "valid_nonempty")}
vals, detail, n_invalid = E.rule_q4_series(bbox_by_id, {i: R.answers([b["yxyx_norm"] for b in gt[i]["boxes"]]) for i in gt}, ["p1"])
check("rule_q4_correct_match", vals[0] == 1.0 and n_invalid == 0, (vals.tolist(), n_invalid))
bbox_by_id2 = {"p1": (None, "truncated")}
vals2, detail2, n_invalid2 = E.rule_q4_series(bbox_by_id2, {i: R.answers([b["yxyx_norm"] for b in gt[i]["boxes"]]) for i in gt}, ["p1"])
check("rule_q4_invalid_bbox_not_treated_as_no_match", vals2[0] == 0.0 and n_invalid2 == 1, (vals2.tolist(), n_invalid2))

n_fail = sum(1 for r in results if not r["pass"])
os.makedirs("results/iter_023/tests", exist_ok=True)
json.dump({"n": len(results), "n_fail": n_fail, "results": results}, open("results/iter_023/tests/fixtures_iter023.json", "w"), indent=1)
print(f"{len(results) - n_fail}/{len(results)} PASS")
sys.exit(1 if n_fail else 0)
