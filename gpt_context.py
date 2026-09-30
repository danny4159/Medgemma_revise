"""GPT용 출처 연결 문맥. 원본 기록·정책·판정은 변경하지 않는다."""

import json


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def history_context(records):
    """모든 접근법의 상태와 최신 관찰, 최근 반복의 상세 문제를 전달한다."""
    lines = [
        "전체 이력: agent/INDEX.md, agent/JOURNEY.md, agent/DECISIONS.md (원본 유지).",
        "아래는 탐색용 색인이다. 이전 사실을 근거로 선택/기각하기 전 해당 plan/review 원문을 확인한다.",
        "새 방향·목표 변경·현재 설명과의 모순은 과거 관련 기록까지 넓혀 확인한다.",
    ]
    # approach_id가 바뀌거나 실행이 실패해도 진단 체류 이력이 사라지지 않는다.
    active = [r for r in records if r.get("plan") and not r.get("superseded")]
    streak = []
    for r in reversed(active):
        if r["plan"].get("experiment_role") not in {"setup", "diagnostic"}:
            break
        streak.append(r["n"])
    lines.append(_json({"strategy_overview": {
        "diagnostic_setup_streak": list(reversed(streak)),
        "note": "계획 역할의 연속 기록(실행 실패·준비 포함), 유효 실험 수나 낭비 판정이 아님. 횟수로 강제 중단하지 않는다.",
    }}))
    tracks = {}
    for r in active:
        track = r["plan"].get("research_track")
        if track:
            tracks.setdefault(track, []).append(r)
    for track, group in tracks.items():
        last = group[-1]
        lines.append(_json({"research_track": track, "iters": [r["n"] for r in group],
                            "related_iterations": last["plan"].get("related_iterations", []),
                            "decision_contract": last["plan"].get("decision_contract", {}),
                            "last_next_task": last["review"].get("next_task"),
                            "source": f"agent/runs/iter_{last['n']:03d}/"}))
    groups = {}
    for r in records:
        plan = r["plan"]
        if not plan:
            continue
        key = plan.get("approach_id") or plan.get("approach") or str(r["n"])
        groups.setdefault(key, []).append(r)
    for key, group in groups.items():
        last = group[-1]
        review = last["review"]
        superseded = bool(last["superseded"])
        lines.append(_json({
            "approach": key, "name": last["plan"].get("approach"),
            "iters": [r["n"] for r in group],
            "valid_experiments": sum(r["review"].get("valid_experiment") is True for r in group),
            "status": "사용자 보완으로 전환 (실패/완료 아님)" if superseded else review.get("approach_status", "진행 중"),
            "latest_observation": review.get("one_line_summary") or last["plan"].get("plan_summary"),
            "failure_scope": review.get("failure_scope"),
            "source": f"agent/runs/iter_{last['n']:03d}/",
        }))
        # 후속 실행 실패나 사용자 전환이 이전 유효한 관찰을 가리지 않도록 별도 연결한다.
        valid = [r for r in group if r["review"].get("valid_experiment") is True]
        if valid and valid[-1] is not last:
            r = valid[-1]
            lines.append(_json({"last_valid_iter": r["n"],
                                "observation": r["review"].get("one_line_summary"),
                                "failure_scope": r["review"].get("failure_scope"),
                                "source": f"agent/runs/iter_{r['n']:03d}/review.json"}))
    lines.append("최근 반복의 미해결 사항 (반복 횟수만으로 재실험/기각하지 않는다):")
    for r in records[-3:]:
        review = r["review"]
        lines.append(_json({"iter": r["n"], "source": f"agent/runs/iter_{r['n']:03d}/",
                            **{k: review.get(k) for k in (
                                "verdict", "valid_experiment", "next_task", "reason",
                                "blocking_issues", "reuse_issues", "deferred_issues")}}))
    return "\n".join(lines)


def asset_context(records):
    """보존 위치는 모두 색인화하고 모듈별 승인 원문은 선택 시 읽게 한다."""
    lines = [
        "전체 모듈별 승인·결함·검증: agent/CODE_ASSETS.md 및 아래 각 review.json/code_assets.",
        "색인의 commit/status는 재사용 승인이 아니다. 선택한 파일·의존성의 원본 SHA,",
        "모듈별 approved/needs_fix/rejected, checks, unpreserved_paths를 반드시 읽고 확인한다.",
        "과거 success만으로 현재 파일을 승인하거나 누락 자산을 새로 구현하지 않는다.",
    ]
    for r in records:
        commit, archive = r["commit"], r["archive"]
        if not commit and not archive and not r["recovery"]:
            continue
        entry = {"iter": r["n"], "source": f"agent/runs/iter_{r['n']:03d}/",
                 "sha": commit.get("sha"),
                 "reusable_code": r["review"].get("reusable_code"),
                 "module_statuses": [a.get("status") for a in r["review"].get("code_assets", [])],
                 "unpreserved_paths": commit.get("unpreserved_paths", [])}
        if archive:
            entry["archive"] = archive
        if r["recovery"]:
            entry["recovery"] = f"agent/runs/iter_{r['n']:03d}/code_recovery.md"
        lines.append(_json(entry))
    return "\n".join(lines)


def limitation_context(registry, selected):
    lines = [
        "전체 근거: agent/LIMITATIONS.md, agent/LIMITATIONS.json, 각 review.json/limitation_updates.",
        "validated는 명시한 사용·평가 조건에서의 재현이며 일반화/내부 원인 확정이 아니다.",
        "현재/직전 계획의 한계는 상세 전달한다. 다른 한계를 선택하거나 상태를 변경하기 전",
        "해당 원문의 evidence·usage_checks·remaining_questions와 목표 범위를 모두 확인한다.",
    ]
    for identity, entry in registry.items():
        data = dict(entry) if identity in selected else {
            k: entry.get(k) for k in ("status", "claim", "goal_start", "review_iteration")
        }
        data["id"] = identity
        n = entry.get("review_iteration")
        data["source"] = f"agent/runs/iter_{n:03d}/review.json" if n else "agent/LIMITATIONS.json"
        lines.append(_json(data))
    return "\n".join(lines)
