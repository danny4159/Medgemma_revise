"""사람이 읽는 알림의 표시만 담당한다. 실행 분기나 원본 값은 변경하지 않는다."""

import re


STATUS_LABELS = {
    "success": "계획 기준 충족", "improve": "보완 필요", "inconclusive": "판단 보류",
    "execution_failed": "실행 문제로 비교 미완료", "abandon": "해당 접근법 중단",
}


def summary_section(markdown, heading):
    """선택적 사람용 요약 블록만 읽는다. 없으면 기존 기록으로 돌아간다."""
    active = False
    values = {}
    for line in str(markdown or "").splitlines():
        if re.match(r"^#{1,6}\s+", line):
            if active:
                break
            active = line.lstrip("#").strip() == heading
            continue
        if active:
            match = re.match(r"^\s*[-*]\s+(?:\*\*)?([^:*]+?)(?:\*\*)?\s*:\s*(.+)$", line)
            if match:
                values[match[1].strip()] = match[2].strip()
    return values


def research_context(plan):
    return summary_section((plan or {}).get("plan_markdown"), "알림 맥락")


def context_fields(plan):
    context = research_context(plan)
    subject = " · ".join(context.get(key, "") for key in ("연구", "데이터", "모델") if context.get(key))
    question = context.get("질문") or (plan or {}).get("research_question")
    return [("연구 대상", subject), ("확인할 질문", question)]


def transition_text(n, plan, previous):
    current, old = research_context(plan), research_context(previous)
    changes = []
    for key in ("데이터", "모델", "과제", "가설"):
        if current.get(key) and old.get(key) and current[key] != old[key]:
            changes.append(f"{key}: {old[key]} → {current[key]}")
    # 표현이 조금 달라진 것을 자동으로 연구 전환이라 판정하지 않는다.
    connection = current.get("연결") or (plan or {}).get("continuation_reason")
    if connection:
        changes.append(str(connection))
    if not changes and previous:
        changes.append("직전 기록을 이어받습니다. 변경 여부와 이유는 이번 계획 원문을 확인하세요.")
    return (f"iter_{n - 1:03d} → iter_{n:03d}\n" if previous else "") + "\n".join(changes)


def plan_ready(n, plan, previous=None, *, engineer="구현 담당", caution=""):
    context = research_context(plan)
    change = context.get("변경")
    badge = "🔀" if change == "방향 전환" else "🔧" if change == "실행 복구" else "🧭"
    label = f"{change} · " if change in {"방향 전환", "실행 복구", "구체화"} else ""
    return notice(f"{badge} iter_{n:03d} | {label}계획 확정 → 구현·실험 준비", [
        *context_fields(plan),
        ("이전과의 연결", transition_text(n, plan, previous)),
        ("이번에 할 작업", context.get("작업") or plan.get("plan_summary")),
        ("진행 상태", f"{engineer}에게 전달합니다. 실제 학습 시작·완료를 뜻하지 않습니다."),
        ("확인 사항", caution),
    ], reference=f"agent/runs/iter_{n:03d}/plan.md")


def stage_notice(n, stage, plan=None, previous=None, previous_review=None, *, resuming=False, caution=""):
    planning = stage in {"계획", "GPT 계획"} or "사고" in stage
    reviewing = stage in {"리뷰", "GPT 리뷰"}
    if planning:
        title = "다음 연구 계획 검토 중"
        fields = [("직전 연구의 질문", research_context(previous).get("질문") or (previous or {}).get("research_question")),
                  ("이전 결과", (previous_review or {}).get("one_line_summary")),
                  ("지금 하는 일", "기존 결과와 사용자 지시를 바탕으로 무엇을 유지·변경할지 정합니다. 새 과제는 아직 확정 전입니다.")]
    else:
        title = "결과 검증 중" if reviewing else f"{stage} 단계 재개"
        fields = context_fields(plan) + [("지금 하는 일", "실제 결과와 실행 오류를 확인합니다. 아직 최종 판정 전입니다." if reviewing
                                          else "저장된 작업을 이어갑니다. 완료 여부는 결과 검증 뒤 알립니다.")]
    return notice(f"{'▶' if resuming else '🔎' if reviewing else '🧭'} iter_{n:03d} | {title}",
                  fields + [("확인 사항", caution)], reference=f"agent/runs/iter_{n:03d}/")


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


def iteration_result(n, review, plan=None):
    """반복 종료와 목표 달성, 미검토/불확정/실패를 구분해 표시한다."""
    highlight = result_highlight(review)
    status = STATUS_LABELS.get(review.get("approach_status"), "판정 확인 필요")
    if review.get("verdict") == "DONE":
        title = f"🎉 iter_{n:03d} | 연구 목표 달성"
    elif review.get("skipped"):
        title = f"🧪 iter_{n:03d} | 작업 종료 · GPT 리뷰 미실시"
    elif highlight:
        title = f"💡🔎 iter_{n:03d} | 중요한 결과·관찰 · {status}"
    elif review.get("approach_status") == "execution_failed":
        title = f"⚠️ iter_{n:03d} | {status} · 가설 판단 전"
    elif review.get("valid_experiment") is False:
        title = f"🔧 iter_{n:03d} | 준비·코드 검증 결과 · {status}"
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
    summary = summary_section(review.get("review_markdown"), "알림 요약")
    return notice(title, [
        *context_fields(plan),
        ("💡 관찰", highlight),
        ("확인된 결과", summary.get("결과") or review.get("one_line_summary")),
        ("연구상 의미", summary.get("의미")),
        ("주의", caution),
        ("다음 계획에 제안", summary.get("후속") or next_action_summary(review.get("next_task"))),
    ], reference=f"agent/runs/iter_{n:03d}/" + ("claude_report.md" if review.get("skipped") else "review.md"))
