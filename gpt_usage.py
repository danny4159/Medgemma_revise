"""Codex CLI 텍스트 로그의 표시 사용량 조회. API 비용·구독 소진율로 환산하지 않는다."""

import re


def summarize_log(path):
    sessions = {}
    unreported = 0
    text = path.read_text(encoding="utf-8", errors="replace")
    for block in re.split(r"(?m)(?=^OpenAI Codex v)", text):
        identity = re.search(r"(?m)^session id: (.+)$", block)
        if not identity:
            continue
        model = re.search(r"(?m)^model: (.+)$", block)
        effort = re.search(r"(?m)^reasoning effort: (.+)$", block)
        tokens = re.findall(r"(?m)^tokens used\n([\d,]+)\s*$", block)
        error = bool(re.search(r"(?m)^ERROR:", block))
        value = int(tokens[-1].replace(",", "")) if tokens else None
        if value is None:
            unreported += 1
        sid = identity[1].strip()
        previous = sessions.get(sid, {})
        previous_value = previous.get("displayed_tokens")
        known = [x for x in (previous_value, value) if x is not None]
        sessions[sid] = {
            "model": model[1] if model else "미기록",
            "effort": effort[1] if effort else "미기록",
            "displayed_tokens": max(known) if known else None,
            "had_error": error or previous.get("had_error", False),
        }
    if text.strip() and not sessions:
        unreported += 1
    return {"source": str(path), "sessions": sessions, "session_count": len(sessions),
            "displayed_tokens": sum(s["displayed_tokens"] or 0 for s in sessions.values()),
            "error_sessions": sum(s["had_error"] for s in sessions.values()),
            "unreported_calls": unreported,
            "accounting": "CLI tokens used 표시값. 동일 세션 최댓값. 캐시·입출력 구분/비용/구독 소진율 아님"}


def usage_report(runs_dir):
    lines = ["# GPT 사용량 (로컬 Codex 로그)", "",
             "CLI의 tokens used 표시값이며 비용·구독 한도 소진율이 아닙니다. 캐시·입출력 구분은 이 로그에 없습니다.",
             "동일 session_id의 반복 표시값은 최댓값만 셉니다. 오류·미집계 호출은 별도로 표시합니다.", "",
             "| 반복 | 단계 | 세션 | 사고 수준 | 표시 토큰 | 오류 세션 | 미집계 호출 |",
             "|---|---|---:|---|---:|---:|---:|"]
    sessions = {}
    stages = {}
    for path in sorted(runs_dir.glob("iter_*/*_codex.log")):
        if path.name not in {"plan_codex.log", "review_codex.log"}:
            continue
        data = summarize_log(path)
        stage = "계획" if path.name.startswith("plan_") else "리뷰"
        effort = ", ".join(sorted({s["effort"] for s in data["sessions"].values()})) or "미기록"
        lines.append(f"| {path.parent.name} | {stage} | {data['session_count']} | {effort} | "
                     f"{data['displayed_tokens']:,} | {data['error_sessions']} | {data['unreported_calls']} |")
        for sid, entry in data["sessions"].items():
            value = entry["displayed_tokens"] or 0
            sessions[sid] = max(sessions.get(sid, 0), value)
            stages.setdefault(stage, {})[sid] = max(stages.get(stage, {}).get(sid, 0), value)
    if not stages:
        lines.append("\nGPT 실행 로그가 없습니다.")
    lines += ["", f"확인된 표시 토큰 합계: {sum(sessions.values()):,}",
              " / ".join(f"{stage}: {sum(values.values()):,}" for stage, values in stages.items()),
              "실제 남은 구독 한도는 Codex CLI의 /status 또는 계정 usage dashboard에서 확인하세요."]
    return "\n".join(lines)
