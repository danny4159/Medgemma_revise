"""Claude stream-json 로컬 집계. 외부 호출·파일 변경 없이 누적값의 중복을 제거한다."""

import json


TOKEN_FIELDS = (
    "inputTokens", "outputTokens", "thinkingTokens", "cacheReadInputTokens",
    "cacheCreationInputTokens", "webSearchRequests", "costUSD",
)


def summarize_stream(path):
    """세션별 누적 high-water mark와 호출별 통계를 분리한다.

    이 CLI 로그의 modelUsage/total_cost_usd는 재개 시에도 세션 누적이다.
    result 없는 중단은 비용을 추측하지 않고 미집계 가능성을 표시한다.
    """
    sessions = {}
    seen = set()
    denials = set()
    pending = False
    malformed = 0
    current_session = None
    with path.open(encoding="utf-8") as stream:
        for index, line in enumerate(stream):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                if line.strip().startswith("{"):
                    malformed += 1
                continue
            if not isinstance(event, dict):
                continue
            current_session = event.get("session_id") or current_session
            kind = event.get("type")
            if kind in {"assistant", "user"} or (kind == "system" and event.get("subtype") == "init"):
                pending = True
            if kind != "result":
                continue
            pending = False
            identity = event.get("uuid") or f"line:{index}"
            if identity in seen:
                continue
            seen.add(identity)
            sid = current_session or f"unknown:{identity}"
            session = sessions.setdefault(sid, {
                "reported_cost_usd": None, "model_usage": {}, "result_events": 0,
                "error_results": 0, "num_turns": 0, "invocation_usage": {},
            })
            session["result_events"] += 1
            session["error_results"] += int(bool(event.get("is_error")))
            session["num_turns"] += event.get("num_turns") or 0
            cost = event.get("total_cost_usd")
            if isinstance(cost, (int, float)):
                session["reported_cost_usd"] = max(session["reported_cost_usd"] or 0, cost)
            for model, counters in (event.get("modelUsage") or {}).items():
                high = session["model_usage"].setdefault(model, {})
                for key in TOKEN_FIELDS:
                    value = counters.get(key)
                    if isinstance(value, (int, float)):
                        high[key] = max(high.get(key, 0), value)
            # 호출별 usage는 누적 modelUsage와 별도 보관하며 둘을 더하지 않는다.
            usage = event.get("usage") or {}
            for key in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
                value = usage.get(key)
                if isinstance(value, (int, float)):
                    target = session["invocation_usage"]
                    target[key] = target.get(key, 0) + value
            for item in event.get("permission_denials") or []:
                denials.add((sid, item.get("tool_use_id") or json.dumps(item, sort_keys=True)))

    models = {}
    for session in sessions.values():
        for model, counters in session["model_usage"].items():
            total = models.setdefault(model, {})
            for key, value in counters.items():
                total[key] = total.get(key, 0) + value
    warnings = []
    if pending or not sessions or malformed:
        warnings.append("result 없는 중단 또는 불완전 로그: 미집계 사용량이 있을 수 있음")
    if any(sid.startswith("unknown:") for sid in sessions):
        warnings.append("session_id 누락: 세션 누적 중복 제거를 보장할 수 없음")
    if any(not s["model_usage"] or s["reported_cost_usd"] is None for s in sessions.values()):
        warnings.append("일부 result의 누적 비용/모델별 사용량 누락: 표시값은 확인된 부분만 포함")
    return {
        "source": str(path), "accounting": "세션별 누적 최대값; 실제 청구액·구독 소진율 아님",
        "reported_cost_usd": sum(s["reported_cost_usd"] or 0 for s in sessions.values()),
        "num_turns": sum(s["num_turns"] for s in sessions.values()),
        "result_events": sum(s["result_events"] for s in sessions.values()),
        "error_results": sum(s["error_results"] for s in sessions.values()),
        "permission_denials": len(denials), "model_usage": models,
        "sessions": sessions, "warnings": warnings,
    }


def usage_report(runs_dir):
    """과거 로그도 읽는 조회 전용 보고서. 같은 세션이 여러 파일에 있어도 총비용은 한 번만 센다."""
    lines = ["# Claude 사용량 (로컬 로그)", "",
             "API 환산 추정치이며 실제 청구액·구독 한도 소진율이 아닙니다.",
             "output에 thinking 포함. cache read는 반복 이력이며 고유 문서량이 아닙니다.", "",
             "| 반복 | 모델 | 턴 | 비용 추정 USD | output | thinking | cache write | cache read |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    costs = {}
    paths = sorted(runs_dir.glob("iter_*/claude_stream.jsonl"))
    for path in paths:
        data = summarize_stream(path)
        models = data["model_usage"]
        counts = [sum(m.get(k, 0) for m in models.values()) for k in
                  ("outputTokens", "thinkingTokens", "cacheCreationInputTokens", "cacheReadInputTokens")]
        model_text = ", ".join(models) or "미기록"
        lines.append(f"| {path.parent.name} | {model_text} | {data['num_turns']} | "
                     f"{data['reported_cost_usd']:.4f} | " + " | ".join(f"{c:,}" for c in counts) + " |")
        for sid, session in data["sessions"].items():
            key = f"{path}:{sid}" if sid.startswith("unknown:") else sid
            costs[key] = max(costs.get(key, 0), session["reported_cost_usd"] or 0)
        for warning in data["warnings"]:
            lines.append(f"\n{path.parent.name}: {warning}\n")
    if not paths:
        lines.append("\nClaude 실행 로그가 없습니다.")
    lines += ["", f"확인된 누적 비용 추정치 합계: ${sum(costs.values()):.4f} (세션 중복 제거)",
              "호출 종료 시 반복별 claude_usage.json 저장. 원본: claude_stream.jsonl.",
              "중단되어 result가 없는 호출의 사용량은 위 합계에 모두 포함되지 않을 수 있습니다."]
    return "\n".join(lines)
