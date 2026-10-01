"""계획 전용 effort 선택. 모델 호출 없이 기존 리뷰·사고 노트의 결정을 사용한다."""

TIERS = ("deep_medium", "deep_high", "normal", "light")
STRATEGIC_SCOPES = {"research_direction", "core_contribution", "foundational_interpretation"}


def choose(requested=None, reason=None, *, explicit=False, source="default"):
    """옛 deep 자동 추천은 medium으로, 명시적 CLI deep는 high로 해석한다.

    high 자동 선택에는 중요한 판단 범위와 세 근거가 모두 필요하다.
    근거 누락은 실험 실패가 아니며 medium에서 필요한 조사를 이어간다.
    """
    reason = reason if isinstance(reason, dict) else {}
    tier = requested
    note = ""
    if tier == "deep":
        tier = "deep_high" if explicit else "deep_medium"
        note = "기존 deep 명시 지정을 유지" if explicit else "옛 deep 추천은 세분화 근거가 없어 medium에서 재평가"
    if tier not in TIERS:
        tier = "deep_medium"
        note = "계획 등급 미지정: medium 기본값"
    if tier == "deep_high" and not explicit:
        complete = (reason.get("scope") in STRATEGIC_SCOPES and
                    all(isinstance(reason.get(key), str) and reason[key].strip()
                        for key in ("decision", "difficulty", "impact")))
        if not complete:
            tier = "deep_medium"
            note = "high의 전략 범위·중요한 결정·어려운 근거·판단 영향이 불충분하여 medium에서 확인"
    return {"tier": tier, "requested_tier": requested, "reason": reason,
            "source": source, "explicit": explicit, "note": note}
