"""사람이 읽는 알림의 표시만 담당한다. 실행 분기나 원본 값은 변경하지 않는다."""


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
    """핵심 먼저, 원문·답장 방법은 끝에. 긴 본문만 축약하고 안내 공간은 보장한다."""
    prefix = [str(title)]
    footer = []
    if reference:
        footer.append("자세히: " + reference)
    if actions:
        footer.append("답장 방법\n" + actions)
    sections = [(str(label), str(value).strip()) for label, value in fields if value is not None and str(value).strip()]
    full = "\n\n".join(prefix + [f"{label}\n{value}" for label, value in sections] + footer)
    if units(full) <= 3200:
        return full
    warning = "일부 내용은 축약했습니다. 중요한 결정 전 원문을 확인하세요."
    prefix.append(warning)
    # 호출부의 제목·명령·참조는 고정된 짧은 문자열이며 판단 본문만 예산에 맞춰 표시한다.
    overhead = units("\n\n".join(prefix + footer)) + sum(units(label) + 3 for label, _ in sections)
    budget = max(32, (3150 - overhead) // max(1, len(sections)))
    return "\n\n".join(prefix + [f"{label}\n{excerpt(value, budget)}" for label, value in sections] + footer)


def iteration_result(n, review):
    """반복 종료와 목표 달성, 미검토/불확정/실패를 구분해 표시한다."""
    if review.get("verdict") == "DONE":
        title = f"🎉 iter_{n:03d} | 연구 목표 달성"
    elif review.get("skipped"):
        title = f"🧪 iter_{n:03d} | 작업 종료 · GPT 리뷰 미실시"
    else:
        status = STATUS_LABELS.get(review.get("approach_status"), "판정 확인 필요")
        title = f"🧪 iter_{n:03d} | {status}"
    concerns = (review.get("blocking_issues") or []) + (review.get("reuse_issues") or [])
    caution = "\n".join(([review["failure_scope"]] if review.get("failure_scope") else [])
                        + [f"- {item}" for item in concerns])
    return notice(title, [
        ("핵심 결과", review.get("one_line_summary")),
        ("의미", review.get("goal_progress") or review.get("approach_note")),
        ("주의", caution),
        ("다음", review.get("next_task")),
    ], reference=f"agent/runs/iter_{n:03d}/" + ("claude_report.md" if review.get("skipped") else "review.md"))
