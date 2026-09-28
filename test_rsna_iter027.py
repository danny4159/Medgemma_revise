"""iter_027 CPU fixture: roi26_eval의 primary/boundary 분리, donor invalid=0점 규약, source-missing 오류,
reader/rule 부호, 극단 시나리오(S/Q4/C_query) 독립 검증. 사용: python test_rsna_iter027.py"""
import json

import numpy as np

from rsna_diag import roi26_eval as E, roi26_spec as R26

results = []


def check(name, cond, detail=None):
    results.append({"name": name, "pass": bool(cond), "detail": detail})
    print(("PASS" if cond else "FAIL"), name)


# 1 box per quadrant GT (yxyx_norm 0-1000 스케일, roi23 center_yx/quadrant_of와 동일 규약)
GT = {"TL": [[100, 100, 200, 200]], "TR": [[100, 700, 200, 800]], "BL": [[700, 100, 800, 200]], "BR": [[700, 700, 800, 800]]}
ALL_BOXES = [b for t in R26.TARGETS for b in GT[t]]

# 시나리오 1: 완벽한 선택 (질의 t에 GT[t]만 반환)
perfect = {t: list(GT[t]) for t in R26.TARGETS}
s, tp, p, g, det = E.patient_score(perfect, GT)
q4 = E.q4_select(perfect, GT)
cq = E.c_query(perfect, GT)
check("perfect_S_eq_1", abs(s - 1.0) < 1e-9, s)
check("perfect_Q4_true", q4 is True, q4)
check("perfect_Cquery_positive", cq > 0, cq)

# 시나리오 2: 전체 GT 복사 (질의와 무관하게 4개 전부 반환)
copy_all = {t: list(ALL_BOXES) for t in R26.TARGETS}
s2, tp2, p2, g2, det2 = E.patient_score(copy_all, GT)
q4_2 = E.q4_select(copy_all, GT)
cq2 = E.c_query(copy_all, GT)
check("copy_S_eq_0.4", abs(s2 - 0.4) < 1e-9, s2)
check("copy_Q4_false", q4_2 is False, q4_2)
check("copy_Cquery_eq_0", abs(cq2 - 0.0) < 1e-9, cq2)

# 시나리오 3: 빈 목록
empty = {t: [] for t in R26.TARGETS}
s3, tp3, p3, g3, det3 = E.patient_score(empty, GT)
q4_3 = E.q4_select(empty, GT)
check("empty_S_eq_0", abs(s3 - 0.0) < 1e-9, s3)
check("empty_Q4_false", q4_3 is False, q4_3)

# 시나리오 4: rule_copy_empty_baseline 래퍼로 동일 값 재확인 (실제 평가 경로가 쓰는 함수)
gts_fmt = {"pA": {"boxes": [{"yxyx_norm": b} for b in ALL_BOXES]}}
src = {"pA": (ALL_BOXES, "valid_nonempty")}
base = E.rule_copy_empty_baseline(src, gts_fmt, ["pA"])
check("wrapper_copy_S_eq_0.4", abs(base["copy"]["S"][0] - 0.4) < 1e-9, base["copy"]["S"].tolist())
check("wrapper_empty_S_eq_0", abs(base["empty"]["S"][0] - 0.0) < 1e-9, base["empty"]["S"].tolist())
check("wrapper_rule_S_eq_1", abs(base["rule"]["S"][0] - 1.0) < 1e-9, base["rule"]["S"].tolist())

# 시나리오 5: source 완전 누락(id가 dict에 없음) -> EvalError (execution gap), score 0으로 숨기지 않는다
try:
    E.rule_copy_empty_baseline({}, gts_fmt, ["pA"])
    check("missing_source_raises", False, "no exception")
except E.EvalError:
    check("missing_source_raises", True)

# 시나리오 5b: status="missing" (recs_b.get(i) None으로 예측된 경우)도 동일하게 오류
try:
    E.rule_copy_empty_baseline({"pA": (None, "missing")}, gts_fmt, ["pA"])
    check("status_missing_raises", False, "no exception")
except E.EvalError:
    check("status_missing_raises", True)

# 시나리오 5c: 실제 parse 실패(예: invalid_json)는 execution gap이 아니라 모델 실패 -> 0점 처리(예외 아님)
base2 = E.rule_copy_empty_baseline({"pA": (None, "invalid_json")}, gts_fmt, ["pA"])
check("model_failure_scores_zero_not_raise", base2["copy"]["invalid"][0] and abs(base2["copy"]["S"][0]) < 1e-9,
      {"invalid": bool(base2["copy"]["invalid"][0]), "S": float(base2["copy"]["S"][0])})

# 시나리오 6: donor invalid -> donor_S=0.0 (NaN 삭제로 쌍 제외하지 않는다)
per_id = {
    "a": {t: {"status": "valid_nonempty", "boxes": GT[t]} for t in R26.TARGETS},  # a: valid, GT를 그대로 반환(완벽)
    "b": {t: {"status": "invalid_json", "boxes": []} for t in R26.TARGETS},  # b: invalid (4개 중 하나라도 invalid)
}
gts2 = {"a": {"boxes": [{"yxyx_norm": b} for b in ALL_BOXES]}, "b": {"boxes": [{"yxyx_norm": b} for b in ALL_BOXES]}}
donor_map = {"a": "b", "b": "a"}
m, det = E.build_metrics(per_id, gts2, ["a", "b"], donor_map=donor_map)
check("donor_invalid_scores_zero_not_nan", (not np.isnan(m["donor_S"][0])) and abs(m["donor_S"][0] - 0.0) < 1e-9,
      m["donor_S"].tolist())
check("donor_valid_case_not_nan_for_b", not np.isnan(m["donor_S"][1]), m["donor_S"].tolist())

# 시나리오 6b: donor가 배정되지 않은 홀수 인원(짝 없음)은 여전히 nan으로 제외한다
per_id3 = dict(per_id)
per_id3["c"] = per_id["a"]
gts3 = dict(gts2)
gts3["c"] = gts2["a"]
donor_map3 = {"a": "b", "b": "a", "c": None}
m3, _ = E.build_metrics(per_id3, gts3, ["a", "b", "c"], donor_map=donor_map3)
check("donor_unpaired_is_nan", np.isnan(m3["donor_S"][2]), m3["donor_S"].tolist())

# 시나리오 7: donor_pairs가 SHA256 순서 결정론적임을 확인 (매 실행 동일 페어링)
pairs1, dm1 = E.donor_pairs(["p1", "p2", "p3", "p4", "p5"])
pairs2, dm2 = E.donor_pairs(["p5", "p4", "p3", "p2", "p1"])  # 입력 순서를 바꿔도 동일해야 함
check("donor_pairs_order_invariant", pairs1 == pairs2, {"pairs1": pairs1, "pairs2": pairs2})
check("donor_pairs_odd_one_excluded", len(dm1) == 4 and sum(1 for k in ["p1", "p2", "p3", "p4", "p5"] if k not in dm1) == 1,
      dm1)

# 시나리오 8: reader/rule 격차의 부호 규약 - paired_ci(a,b)는 mean(a-b)를 반환해야 한다 (reader-direct, rule-direct 모두 이 규약)
a = np.array([0.8, 0.6, 0.4])
b = np.array([0.5, 0.5, 0.5])
pc = E.paired_ci(a, b, seed=1, B=200)
check("paired_ci_mean_is_a_minus_b", abs(pc["mean_diff"] - float(np.mean(a - b))) < 1e-9, pc["mean_diff"])

# 시나리오 9: exact_binom_ci 경계값 (k=0, k=n)
lo0, hi0 = E.exact_binom_ci(0, 10)
lon, hin = E.exact_binom_ci(10, 10)
check("exact_ci_k0_lo_is_zero", lo0 == 0.0, (lo0, hi0))
check("exact_ci_kn_hi_is_one", hin == 1.0, (lon, hin))

# 시나리오 10: cluster_paired_ci - 쌍 단위 resample이며 개별 diff 평균과 point estimate가 일치해야 한다
diff_by_id = {"p1": 0.3, "p2": 0.3, "p3": -0.1, "p4": -0.1}
pairs_ = [("p1", "p2"), ("p3", "p4")]
cc = E.cluster_paired_ci(diff_by_id, pairs_, seed=1, B=500)
check("cluster_paired_ci_mean_matches", abs(cc["mean_diff"] - 0.1) < 1e-9, cc)

n = sum(1 for r in results if r["pass"])
out = {"n": len(results), "n_pass": n, "checks": results}
import os
os.makedirs("results/iter_027/tests", exist_ok=True)
json.dump(out, open("results/iter_027/tests/fixtures_iter027.json", "w"), indent=1, default=str)
print(f"{n}/{len(results)} passed")
