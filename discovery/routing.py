"""추가 모델 호출 없이 다음 작업의 종류로 사고 강도를 선택한다."""
from .contracts import NEXT_WORK, validate


def evidence_work():
    return {"kind": "evidence", "decision": "", "difficulty": ""}


def validate_work(work):
    validate(work, NEXT_WORK, "next_work")
    if work["kind"] != "evidence" and not all(work[k].strip() for k in ("decision", "difficulty")):
        raise ValueError("high 요청에는 내릴 결정과 판단이 어려운 이유가 필요합니다")


def select_effort(state):
    if state["round"] == 0:
        return "high", "최초 분야 지도와 탐색 방향 설정"
    work = state.get("next_work", evidence_work())
    validate_work(work)
    if work["kind"] in {"strategy", "conflict"}:
        return "high", f"{work['decision']} — {work['difficulty']}"
    return "medium", "정해진 질문의 문헌·수요 조사와 근거 보완"
