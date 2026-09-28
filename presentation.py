"""사람이 읽는 알림의 표시만 담당한다. 실행 분기나 원본 값은 변경하지 않는다."""

import re


STATUS_LABELS = {
    "success": "계획 기준 충족", "improve": "보완 필요", "inconclusive": "판단 보류",
    "execution_failed": "실험 미완료", "abandon": "해당 접근법 중단",
}


def units(text):
    return len(text.encode("utf-16-le")) // 2


def excerpt(text, limit):
    text = str(text).strip()
    if units(text) <= limit:
        return text
    suffix = " … [축약]"
    out = []
    size = 0
    for char in text:
        size += units(char)
        if size > limit - units(suffix):
            break
        out.append(char)
    return "".join(out).rstrip() + suffix


def notice(title, fields, *, reference="", actions=""):
    """일반 알림은 한 화면, 결정 요청은 질문·답장 안내를 보존한다. 원본은 수정하지 않는다."""
    prefix = [str(title)]
    footer = []
    if reference:
        footer.append("자세히: " + reference)
    if actions:
        footer.append("답장 방법\n" + actions)
    sections = [(str(label), str(value).strip()) for label, value in fields if value is not None and str(value).strip()]
    full = "\n\n".join(prefix + [f"{label}: {value}" for label, value in sections] + footer)
    limit = 2800 if actions else 1000
    field_limit = 260
    if units(full) <= limit and (actions or all(units(value) <= field_limit for _, value in sections)):
        return full
    warning = ("일부 내용은 축약했습니다. 중요한 결정 전 원문을 확인하세요." if actions
               else "긴 설명은 축약했습니다. 상세는 원문을 확인하세요.")
    prefix.append(warning)
    # 호출부의 제목·명령·참조는 고정된 짧은 문자열이며 판단 본문만 예산에 맞춰 표시한다.
    overhead = units("\n\n".join(prefix + footer)) + sum(units(label) + 3 for label, _ in sections)
    budget = max(32, (limit - 50 - overhead) // max(1, len(sections)))
    if not actions:
        budget = min(field_limit, budget)
    return "\n\n".join(prefix + [f"{label}: {excerpt(value, budget)}" for label, value in sections] + footer)


def result_highlight(review):
    """리뷰가 고른 의미 있는 실제 관찰만 강조한다. 성공 판정만으로 발견을 만들지 않는다."""
    milestone = review.get("milestone") or {}
    if (review.get("skipped") or review.get("valid_experiment") is not True
            or review.get("blocking_issues") or review.get("approach_status") == "execution_failed"):
        return ""
    if milestone.get("is_milestone") and milestone.get("title"):
        return str(milestone["title"]).strip()
    return ""


def next_action_summary(text):
    """첫 행동 문장만 표시한다. 상세 조건은 원문에 남고 요약 여부를 명시한다."""
    text = str(text or "").strip()
    sentences = re.split(r"(?<=[.!?。])\s+", text, maxsplit=1)
    if len(sentences) > 1:
        return excerpt(sentences[0], 200) + " (상세 조건은 원문)"
    return text


def iteration_result(n, review):
    """반복 종료와 목표 달성, 미검토/불확정/실패를 구분해 표시한다."""
    highlight = result_highlight(review)
    status = STATUS_LABELS.get(review.get("approach_status"), "판정 확인 필요")
    if review.get("verdict") == "DONE":
        title = f"🎉 iter_{n:03d} | 연구 목표 달성"
    elif review.get("skipped"):
        title = f"🧪 iter_{n:03d} | 작업 종료 · GPT 리뷰 미실시"
    elif highlight:
        title = f"💡🔎 iter_{n:03d} | 중요한 결과·관찰 · {status}"
    else:
        title = f"🧪 iter_{n:03d} | {status}"
    blocking = review.get("blocking_issues") or []
    reuse = review.get("reuse_issues") or []
    caution = str(review.get("failure_scope") or "")
    if reuse:
        caution += f"\n재사용 전 코드 보완 {len(reuse)}건(상세 원문)."
    if len(blocking) > 1:
        caution += f"\n결론을 막는 추가 문제 {len(blocking) - 1}건(상세 원문)."
    # 결과를 무효화하는 문제는 긴 실패 범위 설명보다 먼저 보여준다.
    if blocking:
        caution = "결론 검증 보류: " + str(blocking[0]) + "\n" + caution
    elif review.get("valid_experiment") is False:
        caution = "유효한 가설 검증은 미완료입니다.\n" + caution
    return notice(title, [
        ("💡 관찰", highlight),
        ("핵심 결과", review.get("one_line_summary")),
        ("주의", caution),
        ("다음", next_action_summary(review.get("next_task"))),
    ], reference=f"agent/runs/iter_{n:03d}/" + ("claude_report.md" if review.get("skipped") else "review.md"))
