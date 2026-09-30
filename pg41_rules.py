"""iter_041 사전 판정 규칙 (결과를 보기 전에 고정; 생성 protocol에 hash 잠금). 계획: agent/runs/iter_041/plan.md 'Evaluation'.

- 개발 단계 투자 판단 기준이며 임상 허용 한계가 아니다.
- 정확도: C 주분석의 Δ_AB = F1(I) - F1(J_AB), Δ_BA = F1(I) - F1(J_BA)  (F1@0.3, 환자 평균; invalid는 문장 점수 0 포함).
- 비용: I(독립 두 요청 병렬) 대 J(공동 한 요청)의 동일 worker/GPU 구성 큐 비교.
"""
DELTA_MIN = 0.05            # 공동 손실 최소 기준 (C 현재 F1 ~0.58의 약 9%)
DELTA_STRONG_NEG = 0.02     # 두 순서 CI 상한이 이 이하이면 '제한된 정확도 유지' 강한 근거
DEVSEC_RATIO_MIN = 1.25     # 독립 device-seconds / J
P95_LAT_RATIO_MIN = 1.20    # 독립 p95 환자 지연 / J
THROUGHPUT_RATIO_MAX = 0.80  # 독립 처리량 / J 처리량
BOOT_B = 10000
BOOT_SEED = 20260930
MAIN_LEVEL = 0.975


def accuracy_class(c_ab, c_ba, b_ab_mean, b_ba_mean, common_ab_mean, common_ba_mean):
    """c_ab/c_ba: C의 [mean, lo, hi] (97.5% CI). b_*_mean: B Δ 점추정. common_*: C의 공통 valid/EOS subset Δ 점추정.
    returns dict(class in {positive, negative, strong_negative, uncertain})."""
    pos = (c_ab[0] >= DELTA_MIN and c_ba[0] >= DELTA_MIN and c_ab[1] > 0 and c_ba[1] > 0
           and b_ab_mean > 0 and b_ba_mean > 0 and common_ab_mean > 0 and common_ba_mean > 0)
    neg = c_ab[2] < DELTA_MIN and c_ba[2] < DELTA_MIN
    strong = c_ab[2] <= DELTA_STRONG_NEG and c_ba[2] <= DELTA_STRONG_NEG
    cls = "positive" if pos else ("negative" if neg else "uncertain")
    return {"class": cls, "strong_negative": bool(neg and strong)}


def cost_class(devsec_ratio, p95_ratio, thr_ratio):
    """각 인자는 두 J 순서(AB, BA) 모두에 대한 값의 리스트. 두 순서에서 모두 충족해야 한다 (보수적)."""
    ok_dev = all(v >= DEVSEC_RATIO_MIN for v in devsec_ratio)
    ok_lat = all(v >= P95_LAT_RATIO_MIN for v in p95_ratio) or all(v <= THROUGHPUT_RATIO_MAX for v in thr_ratio)
    return {"devsec_ratio_ge_1.25_both": ok_dev, "p95_or_throughput_criterion_both": ok_lat, "cost_burden": bool(ok_dev and ok_lat)}


def overall(acc, cost, cost_boundary):
    """acc: accuracy_class 결과, cost: cost_class 결과, cost_boundary: 비용 비율 구간이 기준을 가로지르는지.
    positive_method_pilot_candidate: 정확도 손실과 비용 부담이 함께 있음 (확정 아님; 비용 경계면 uncertain).
    independent_baseline_preserved: 정확도 손실이 없거나(음성) 비용 부담이 기준 미만."""
    if acc["class"] == "positive" and cost["cost_burden"] and not cost_boundary:
        return "positive_method_pilot_candidate"
    if acc["class"] == "negative" or (acc["class"] == "positive" and not cost["cost_burden"] and not cost_boundary):
        return "independent_baseline_preserved_hold_joint_investment"
    return "uncertain_hold_no_extension"
