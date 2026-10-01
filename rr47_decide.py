"""iter_047 사전 투자 판단 (plan.md Evaluation '사전 투자 판단'을 코드로 고정). 입력: rr47_eval.summarize 결과 report + validity 플래그.
결과를 보고 문턱을 바꾸지 않는다. 출력 outcome: simple_alternative_sufficient / positive_min_method_review / negative_no_tradeoff / inconclusive / invalid_run.
"""
R_GOAL = 0.80
HFAIL_GOAL = 0.05
ACC_GAIN = 0.10
R_TRADE = 0.15
HFAIL_TRADE = 0.05
SIMPLE = ["R1", "R2", "BJ", "BI"]


def decide(report, valid):
    c, d = report["conds"], report["diffs"]
    out = dict(valid=bool(valid), criteria={}, flags=[])
    if not valid:
        out["outcome"] = "invalid_run"
        return out
    suff = {k: bool(c[k]["r"]["lo95"] >= R_GOAL and c[k]["h_fail"]["hi95"] <= HFAIL_GOAL) for k in SIMPLE}
    out["criteria"]["simple_sufficient"] = suff
    c2 = d["BJ-T:acc"]
    cond2 = bool(c2["mean"] >= ACC_GAIN and c2["lo"] > 0)
    r_d, h_d = d["BJ-R2:r"], d["BJ-R2:h_fail"]
    cond3 = bool(r_d["mean"] >= R_TRADE and r_d["lo"] > 0 and h_d["mean"] >= HFAIL_TRADE and h_d["lo"] > 0)
    cond4 = {k: bool(c[k]["r"]["hi95"] < R_GOAL or c[k]["h_fail"]["lo95"] > HFAIL_GOAL) for k in SIMPLE}
    out["criteria"].update(image_contributes_BJ_vs_T=cond2, bj_r2_tradeoff=cond3, each_simple_misses_goal=cond4)
    if any(suff.values()):
        out["outcome"] = "simple_alternative_sufficient"
    elif cond2 and cond3 and all(cond4.values()):
        out["outcome"] = "positive_min_method_review"
    else:
        # 음성 계열 flag (투자 보류 근거; 의료 VLM 전체의 기각이 아니다)
        if c2["hi"] < ACC_GAIN:
            out["flags"].append("image_gain_over_text_below_0.10")
        if r_d["hi"] < R_TRADE or h_d["hi"] < HFAIL_TRADE:
            out["flags"].append("bj_r2_tradeoff_not_reached")
        if c["R2"]["h_fail"]["hi95"] <= HFAIL_GOAL:
            out["flags"].append("r2_preserves_within_goal")
        # 필수 양성 조건 중 하나라도 CI 상한이 문턱 미만이면 음성(투자 보류), 아니면 불확정
        neg = c2["hi"] < ACC_GAIN or r_d["hi"] < R_TRADE or h_d["hi"] < HFAIL_TRADE
        out["outcome"] = "negative_no_tradeoff" if neg else "inconclusive"
    return out
