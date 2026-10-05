"""문헌 탐색 → 후보 심사 → 기록. 실험·Git branch·기존 목표를 호출하지 않는다."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path

from .contracts import (EXPLORE, CRITIC, validate, candidate_valid, axes_valid, sources_valid,
                        nomination_problems, recommendation_problems)
from .runtime import now, read_json, save

PACKAGE = Path(__file__).resolve().parent
STATUS_LABELS = {"exploring": "탐색", "investigating": "집중 조사", "recommended": "문헌상 유망",
                 "held": "보류", "excluded": "제외"}


def rebuild(root):
    state = {"round": 0, "candidates": {}, "next_question": "의료 데이터 특성과 지속적인 현장 수요가 만나는 중요한 문제는 무엇인가?",
             "focus_id": "", "stalled": 0, "paused": False, "recent": []}
    for path in sorted((root / "rounds").glob("round_*/done.json")):
        record = read_json(path)
        if record["number"] != state["round"] + 1:
            raise ValueError("회차 기록 순서가 끊겼습니다. 원본을 확인하세요")
        state["round"] = record["number"]
        for candidate in record["candidates"]:
            state["candidates"][candidate["id"]] = candidate
        state["next_question"] = record["next_question"]
        state["focus_id"] = record["focus_id"]
        state["stalled"] = 0 if record["evidence_added"] else state["stalled"] + 1
        state["paused"] = record["next_action"] == "pause"
        state["recent"] = (state["recent"] + [{k: record[k] for k in ("number", "question", "what_changed", "next_question")}])[-5:]
    return state


def context(state):
    index = [{**{k: c[k] for k in ("id", "problem_key", "title", "status", "summary", "uncertainty")},
              "review_reason": c.get("review_reason", ""),
              "next_questions": c["next_questions"]} for c in state["candidates"].values()]
    focused = state["candidates"].get(state["focus_id"])
    active = [c for c in state["candidates"].values() if c["status"] in {"exploring", "investigating"}]
    selected = ([focused] if focused else []) + [c for c in active if not focused or c["id"] != focused["id"]][:2]
    return json.dumps({"candidate_index": index, "relevant_documents": selected,
                       "recent_decisions": state["recent"], "next_question": state["next_question"]}, ensure_ascii=False)


def base_prompt(role):
    return (f"확인 기준 날짜: {date.today().isoformat()}\n"
            + (PACKAGE / "GOAL.md").read_text() + "\n"
            + (PACKAGE / "POLICY.md").read_text() + "\n"
            + (PACKAGE / "prompts" / f"{role}.md").read_text())


def validate_exploration(result, state):
    validate(result, EXPLORE)
    if not result["question"].strip() or not result["what_changed"].strip():
        raise ValueError("질문과 판단 변화 기록 누락")
    if result["next_action"] == "continue" and not result["next_question"].strip():
        raise ValueError("계속 진행할 다음 질문이 없습니다")
    ids, keys = set(), {}
    for c in state["candidates"].values():
        keys[c["problem_key"].strip().casefold()] = c["id"]
    for candidate in result["candidates"]:
        candidate_valid(candidate)
        cid, key = candidate["id"], candidate["problem_key"].strip().casefold()
        if cid in ids or (key in keys and keys[key] != cid):
            raise ValueError("후보/문제 key 중복: 기존 후보를 갱신해야 합니다")
        ids.add(cid)
        keys[key] = cid
        previous = state["candidates"].get(cid)
        if previous:
            if previous["problem_key"] != candidate["problem_key"]:
                raise ValueError("기존 후보의 문제 key를 바꿀 수 없습니다")
            if previous["status"] in {"recommended", "held", "excluded"} and not candidate["reopen_reason"].strip():
                raise ValueError("보존 후보 재검토에는 새 근거/사용자 지시가 필요합니다")
    if sum(c["status"] == "nominate" for c in result["candidates"]) > 1:
        raise ValueError("추천 심사는 회차당 하나만 요청하세요")
    if result["focus_id"] and result["focus_id"] not in ids | state["candidates"].keys():
        raise ValueError("다음 집중 후보가 존재하지 않습니다")


def render(root, state):
    lines = ["# 의료 AI 연구 문제 탐색", "", "추천은 문헌상 판단이며 실험·임상 검증이 아닙니다.", "",
             f"완료 회차: {state['round']}", f"다음 질문: {state['next_question']}", "",
             "| 후보 | 상태 | 핵심 |", "|---|---|---|"]
    for c in state["candidates"].values():
        title = c["title"].replace("|", "/").replace("\n", " ")
        summary = c["summary"].replace("|", "/").replace("\n", " ")
        lines.append(f"| [{title}](candidates/{c['id']}.md) | {STATUS_LABELS[c['status']]} | {summary} |")
        source_text = "\n".join(f"- [{s['title']}]({s['url']}) — {s['access']}, 확인 {s['checked_at']}; {s['locator']}\n"
                                f"  주장: {s['claim']} / 한계: {s['limitations']}" for s in c["sources"])
        save(root / "candidates" / f"{c['id']}.md", f"# {c['title']}\n\n상태: {STATUS_LABELS[c['status']]}\n\n"
             + c["report_markdown"] + "\n\n## 출처\n\n" + source_text
             + "\n\n## 최근 심사\n\n" + c.get("review_markdown", "추천 심사 전")
             + f"\n\n원본: ../rounds/round_{c['updated_round']:04d}/\n")
    save(root / "INDEX.md", "\n".join(lines) + "\n")
    save(root / "catalog.json", state)


def run_round(root, state, model, channel):
    number = state["round"] + 1
    folder = root / "rounds" / f"round_{number:04d}"
    folder.mkdir(parents=True, exist_ok=True)
    save(root / "status.json", {"state": "researching", "round": number, "question": state["next_question"], "time": now()})
    result = model.call(folder / "explore", base_prompt("explore") + "\n\n이전 근거와 다음 질문:\n" + context(state), EXPLORE)
    validate_exploration(result, state)
    save(folder / "research.json", result)
    save(folder / "research.md", result["report_markdown"])
    candidates = deepcopy(result["candidates"])
    notifications = []
    for candidate in candidates:
        cid = candidate["id"]
        candidate["updated_round"] = number
        if candidate["status"] == "nominate":
            problems = nomination_problems(candidate)
            if problems:
                candidate["status"] = "investigating"
                candidate["review_markdown"] = "추천 진입 보류: " + "; ".join(problems)
                candidate["review_reason"] = candidate["review_markdown"]
                result["focus_id"] = cid
                result["next_question"] = "추천 전 부족한 근거를 확보할 수 있는가: " + "; ".join(problems)
            else:
                save(root / "status.json", {"state": "reviewing", "round": number, "candidate": cid, "time": now()})
                review = model.call(folder / "critic", base_prompt("critic") + "\n\n심사할 후보:\n"
                                    + json.dumps(candidate, ensure_ascii=False), CRITIC)
                validate(review, CRITIC)
                axes_valid(review["criteria"])
                sources_valid(review["additional_sources"])
                save(folder / "review.json", review)
                save(folder / "review.md", review["report_markdown"])
                problems = recommendation_problems(candidate, review)
                candidate["status"] = {"recommend": "recommended", "deepen": "investigating",
                                       "hold": "held", "exclude": "excluded"}[review["verdict"]]
                if candidate["status"] == "recommended" and problems:
                    candidate["status"] = "held"
                candidate["review_markdown"] = review["report_markdown"]
                candidate["review_reason"] = review["reason"]
                if problems:
                    candidate["review_markdown"] += "\n\n연결 검사: " + "; ".join(problems)
                candidate["review_next_question"] = review["next_question"]
                if candidate["status"] == "recommended":
                    notifications.append((f"candidate-{cid}-{number}", f"💡 문헌상 유망 후보 | {candidate['title']}\n"
                        f"핵심: {candidate['summary']}\n선정 근거: {review['reason']}\n"
                        f"미확인: {candidate['uncertainty']}\n실험 검증 전입니다. 다음에는 다른 후보를 탐색합니다.\n"
                        f"상세: {root / 'candidates' / (cid + '.md')}"))
                elif review["verdict"] == "deepen":
                    result["focus_id"], result["next_question"] = cid, review["next_question"]
        old = state["candidates"].get(cid)
        if old and old["status"] == "recommended" and candidate["status"] != "recommended":
            notifications.append((f"reconsider-{cid}-{number}", f"🔎 기존 추천 재검토 | {candidate['title']}\n"
                                  f"현재: {STATUS_LABELS[candidate['status']]}\n근거: {candidate['reopen_reason']}"))
    combined = {**state["candidates"], **{c["id"]: c for c in candidates}}
    focus = combined.get(result["focus_id"])
    if focus and focus["status"] in {"recommended", "held", "excluded"}:
        result["focus_id"] = ""
        result["next_question"] = "선정·보류 후보와 겹치지 않으면서 목표에 부합하는 다음 문제는 무엇인가?"
    if result["next_action"] == "pause":
        notifications.append((f"pause-{number}", f"⏸ 탐색 범위 재검토 필요\n{result['what_changed']}\n"
                              f"남은 질문: {result['next_question']}"))
    elif number % 3 == 0:
        notifications.append((f"progress-{number}", f"🧭 연구 탐색 | {number}회차\n"
                              f"확인: {result['what_changed']}\n다음 질문: {result['next_question']}"))
    record = {k: result[k] for k in ("question", "what_changed", "next_question", "focus_id", "next_action", "evidence_added")}
    record.update(number=number, candidates=candidates, notifications=notifications, time=now())
    # done.json 단일 원자적 commit 이후 파생 파일/알림은 재개 시 재생한다.
    save(folder / "done.json", record)
    state = rebuild(root)
    render(root, state)
    replay_notifications(root, channel)
    return state


def replay_notifications(root, channel):
    for path in sorted((root / "rounds").glob("round_*/done.json")):
        for key, text in read_json(path).get("notifications", []):
            channel.send(key, text)
