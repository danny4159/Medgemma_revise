"""rsna_diag/det_error_audit.py 독립 검증 (medgemma env). 동작 확인 gate:
- 4범주 분류 규칙의 손수 구성 fixture (경계값, 대응 경쟁, threshold 제외, 인접, coverage 부재).
- FP 분해의 배타성/예외 가드.
- ratio_ci_cluster의 퇴화(분모 0) 처리.
- D24 층화 pilot의 결정성과 confirm800 실제 저장 출력에 대한 범주 합 = sft_only 수 검증(det_compare.complementarity와 대조).
"""
import json
import os
import sys

import numpy as np

BASE = "/SSD1_1TB/home/milab/daniel/08_medgemma/research"
sys.path.insert(0, BASE)
from rsna_diag import det_compare as DC  # noqa: E402
from rsna_diag import det_error_audit as A  # noqa: E402
from rsna_diag import det_eval as E  # noqa: E402
from rsna_diag import det_lib as D  # noqa: E402
from rsna_diag import metrics as M  # noqa: E402

results = {"pass": 0, "fail": 0, "details": []}


def check(name, cond, extra=None):
    ok = bool(cond)
    results["pass" if ok else "fail"] += 1
    results["details"].append({"name": name, "ok": ok, "extra": extra})
    if not ok:
        print(f"FAIL: {name} {extra}")


def test_classify_matching_competition():
    gt_box = [400, 400, 500, 500]
    # det selected: 한 후보가 IoU>=0.3인데(경쟁으로 다른 GT에 뺏김을 흉내: bounded_match 밖에서 직접 max_sel 검사만 함)
    det_sel = [[410, 410, 510, 510]]  # IoU with gt_box ~ 0.68
    raw = [([410, 410, 510, 510], 0.9)]
    cat, iou_v, score = A.classify_gt(gt_box, det_sel, raw, thr=0.3)
    check("matching_competition_when_selected_has_candidate", cat == "matching_competition", (cat, iou_v))


def test_classify_threshold_excluded():
    gt_box = [400, 400, 500, 500]
    det_sel = []  # 선택(threshold 이상)에는 후보 없음
    raw = [([410, 410, 510, 510], 0.2)]  # 전체 후보엔 IoU>=0.3인 후보가 있음(낮은 score)
    cat, iou_v, score = A.classify_gt(gt_box, det_sel, raw, thr=0.3)
    check("threshold_excluded", cat == "threshold_excluded" and score == 0.2, (cat, iou_v, score))


def test_classify_adjacent():
    gt_box = [400, 400, 500, 500]
    det_sel = []
    # IoU 0.1~0.3 사이가 되도록 겹치는 후보 구성
    raw = [([450, 450, 550, 550], 0.05)]
    iou_v_manual = M.iou([450, 450, 550, 550], gt_box)
    cat, iou_v, score = A.classify_gt(gt_box, det_sel, raw, thr=0.3)
    check("adjacent_localization_error", cat == "adjacent_localization_error" and 0.1 <= iou_v_manual < 0.3,
          (cat, iou_v, iou_v_manual))


def test_classify_no_coverage_far():
    gt_box = [400, 400, 500, 500]
    det_sel = []
    raw = [([0, 0, 50, 50], 0.9)]  # 전혀 안 겹침
    cat, iou_v, score = A.classify_gt(gt_box, det_sel, raw, thr=0.3)
    check("no_coverage_far", cat == "no_stored_candidate_coverage" and iou_v == 0.0, (cat, iou_v))


def test_classify_no_coverage_empty():
    gt_box = [400, 400, 500, 500]
    cat, iou_v, score = A.classify_gt(gt_box, [], [], thr=0.3)
    check("no_coverage_empty_raw", cat == "no_stored_candidate_coverage" and score is None, (cat, iou_v, score))


def test_classify_boundary_exact_thr():
    # 정확히 thr과 같은 IoU: >=이므로 경쟁이 아니라 threshold_excluded 판정에서 포함돼야 함(>=0.3 검사)
    gt_box = [0, 0, 1000, 1000]
    # 후보가 gt와 완전히 같은 면적 비율로 IoU=0.3이 되도록 설계하기보다, 직접 iou 값을 고정한 합성 케이스로 검증
    # 두 정사각형의 IoU가 정확히 0.3이 되도록 구성: 공유 정사각형 s, 각 면적 A, 교집합 I=0.3*(2A-I) => 풀면 I/A 비율 도출
    import math
    # 단순화: 같은 크기 정사각형이 겹치는 경우 IoU=inter/(2A-inter). thr=0.3 만족하는 offset 계산.
    A_area = 1000.0
    # inter/(2*A-inter) = 0.3 -> inter = 0.6*A - 0.3*inter -> 1.3*inter=0.6A -> inter=0.4615384615*A
    side = math.sqrt(A_area)
    inter_target = 0.6 / 1.3 * A_area
    # 정사각형 두 개, 한쪽을 x축으로 이동 d: 겹치는 폭 = side-d, 넓이 겹침 = (side-d)*side
    # 부동소수점 오차로 IoU가 0.3 미만이 되지 않도록 겹침을 미세하게 늘린다(>=0.3 보장, 경계 검사 취지 유지).
    d = side - inter_target / side - 1e-6
    gt = [0, 0, side, side]
    cand = [0, d, side, side + d]
    iou_v = M.iou(gt, cand)
    check("boundary_setup_near_0.3", abs(iou_v - 0.3) < 1e-6, iou_v)
    cat, ev_iou, score = A.classify_gt(gt, [], [(cand, 0.5)], thr=0.3)
    check("boundary_exact_thr_is_threshold_excluded_not_adjacent", cat == "threshold_excluded", (cat, ev_iou))


def test_fp_decompose_exhaustive_and_competition():
    ids = ["p1"]
    gt = {"p1": {"boxes": [{"yxyx_norm": [400, 400, 500, 500]}]}}
    # pred1은 gt에 잘 맞음(matched), pred2는 같은 gt에 IoU>=thr인데 이미 매칭된 gt라 경쟁으로 unmatched.
    preds = {"p1": {"status": "valid_nonempty", "boxes": [[405, 405, 505, 505], [410, 410, 510, 510]]}}
    out = A.fp_decompose(ids, gt, preds, thr=0.3)
    check("fp_decompose_one_competition", out["competes_for_matched_gt"] == 1 and out["n_fp_total"] == 1, out)


def test_fp_decompose_no_gt():
    ids = ["p2"]
    gt = {"p2": {"boxes": []}}
    preds = {"p2": {"status": "valid_nonempty", "boxes": [[10, 10, 20, 20]]}}
    out = A.fp_decompose(ids, gt, preds, thr=0.3)
    check("fp_decompose_negative_patient_no_gt_within_0.1", out["no_gt_within_0.1"] == 1 and out["n_fp_total"] == 1, out)


def test_ratio_ci_cluster_degenerate_denominator():
    num = np.array([0.0, 0.0, 1.0])
    den = np.array([0.0, 0.0, 2.0])
    idx = np.array([[0, 1], [0, 0], [2, 2]])  # resample0: den[0]+den[1]=0, resample1: den[0]+den[0]=0, resample2: den[2]+den[2]=4>0
    out = A.ratio_ci_cluster(num, den, idx)
    check("ratio_ci_flags_degenerate", out["n_degenerate_denom0"] == 2, out)


def test_stratified_d24_deterministic_and_disjoint():
    gt = json.load(open(f"{BASE}/results/iter_010/manifests/gt_manifest.json"))
    ids = json.load(open(f"{BASE}/results/iter_010/manifests/confirm_ids.json"))
    a = A.stratified_d24(ids, gt)
    b = A.stratified_d24(ids, gt)
    check("d24_len24", len(a) == 24, len(a))
    check("d24_unique", len(set(a)) == len(a))
    check("d24_deterministic", a == b)
    cats = {gt[i]["category"] for i in a}
    check("d24_has_all_categories", cats == {"opacity", "normal", "not_normal_no_opacity"}, cats)
    n_opacity = sum(1 for i in a if gt[i]["category"] == "opacity")
    check("d24_opacity_8", n_opacity == 8, n_opacity)


def test_pilot_d24_on_real_stored_outputs():
    """D24 subset에서 실제 저장 detector17/SFT17 출력으로 파이프라인이 돌아가고, 범주 합이
    같은 subset에서 계산한 det_compare.complementarity의 sft_only와 일치하는지 확인한다."""
    gt, infer = D.load_gt_infer()
    ids = json.load(open(f"{BASE}/results/iter_010/manifests/confirm_ids.json"))
    d24 = A.stratified_d24(ids, gt)
    pos24 = [i for i in d24 if gt[i]["category"] == "opacity"]
    if not pos24:
        check("pilot_d24_has_positive", False, "no positive in D24")
        return
    sel17 = json.load(open(f"{BASE}/results/iter_035/select/seed17/v400_selection.json"))
    raw_full, comp, rid = E.load_verified(f"{BASE}/results/iter_035/confirm800/det17", "confirm800", sel17["selected_checkpoint"])
    thr17 = sel17["selected"]["threshold"]
    det17_sel_full = D.preds_to_norm_yxyx(raw_full, gt, thr17)
    recs, _ = DC.load_stored(f"{BASE}/results/iter_012/confirm_sft_seed17", ids, ("concise",), DC.ADAPTERS[17], infer)
    from rsna_diag import sft_eval as SE
    sft17_full = SE.parse_records(recs, ids, "concise", strict=True)

    raw24 = {i: raw_full[i] for i in d24}
    det_sel24 = {i: det17_sel_full[i] for i in d24}
    sft24 = {i: sft17_full[i] for i in d24}

    idx_dummy = M.bootstrap_indices(len(pos24), B=10, seed=1)
    c03, _ = DC.complementarity(det_sel24, sft24, gt, pos24, 0.3, idx_dummy)
    agg = A.aggregate(pos24, gt, det_sel24, raw24, sft24, 0.3)
    check("pilot_d24_category_sum_matches_sft_only", sum(agg["category_counts"].values()) == c03["sft_only"],
          (agg["category_counts"], c03["sft_only"]))
    check("pilot_d24_total_gt_matches", agg["total_gt"] == c03["total_gt"], (agg["total_gt"], c03["total_gt"]))
    # 후보가 threshold_excluded로 분류된 GT는 반드시 raw_max_iou>=0.3, category_evidence_score는 threshold17 미만이어야 함
    bad = []
    for pid, rows in agg["per_patient_rows"].items():
        for r in rows:
            if r["sft_only_category"] == "threshold_excluded":
                if r["category_evidence_score"] is None or r["category_evidence_score"] >= thr17:
                    bad.append((pid, r))
    check("threshold_excluded_score_below_locked_threshold", len(bad) == 0, bad[:3])


if __name__ == "__main__":
    test_classify_matching_competition()
    test_classify_threshold_excluded()
    test_classify_adjacent()
    test_classify_no_coverage_far()
    test_classify_no_coverage_empty()
    test_classify_boundary_exact_thr()
    test_fp_decompose_exhaustive_and_competition()
    test_fp_decompose_no_gt()
    test_ratio_ci_cluster_degenerate_denominator()
    test_stratified_d24_deterministic_and_disjoint()
    test_pilot_d24_on_real_stored_outputs()
    print(json.dumps({"pass": results["pass"], "fail": results["fail"]}, indent=1))
    out_path = os.environ.get("DET_ERROR_AUDIT_FIXTURES_OUT")
    if out_path:
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
    sys.exit(1 if results["fail"] else 0)
