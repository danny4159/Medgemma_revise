"""iter_017 evidence 정보 수준 진단의 공통 문구·packet·좌표 교란(X) mapping (결과를 보기 전에 고정).

조건: U(정보 미제공) / B(검출 유무) / K(유무+개수) / L(유무+개수+좌표) / X(L과 동일하되 좌표만 같은 k의 다른 환자 것).
packet은 항상 detection, count, boxes 세 필드(고정 key 순서). 기존 qa_spec의 evidence 문구는 덮어쓰지 않는다.
localizer 출력 상태: valid_nonempty | valid_empty | 그 외(invalid/truncated -> 모든 조건에서 세 필드 not_provided, 실패 상태는 metadata).
"""
import hashlib
import json
import random

from . import qa_spec as S

VERSION = "ev17_common_v1"
NP = "not_provided"
COMMON = ("The localization output may be incorrect or incomplete and concerns only pulmonary opacity. "
          "Assess the original image for the question. Fields marked not_provided contain no supplied information. "
          "Box coordinates, when supplied, are yxyx integers in [0,1000] relative to the entire square-padded image.")
CONDS = ("U", "B", "K", "L")
ALL_CONDS = ("U", "B", "K", "L", "X")
COND_NAME = {c: f"ev17_{c}" for c in ALL_CONDS}


def cond_of(name):
    return name[len("ev17_"):]


def packet(cond, status, boxes):
    """cond: U|B|K|L|X. status: valid_nonempty|valid_empty|other. boxes: 표시할 좌표 목록(L은 자기 것, X는 donor 것; 그 외는 무시)."""
    if cond not in ALL_CONDS:
        raise ValueError(cond)
    if cond == "U" or status not in ("valid_nonempty", "valid_empty"):
        return {"detection": NP, "count": NP, "boxes": NP}
    if status == "valid_empty":
        return {"detection": "none", "count": 0, "boxes": []}
    k = len(boxes)
    if k < 1:
        raise ValueError("nonempty status without boxes")
    if cond == "B":
        return {"detection": "present", "count": NP, "boxes": NP}
    if cond == "K":
        return {"detection": "present", "count": k, "boxes": NP}
    return {"detection": "present", "count": k, "boxes": [{"box_2d": [int(round(v)) for v in b]} for b in boxes]}


def packet_json(p):
    if list(p) != ["detection", "count", "boxes"]:
        raise ValueError("packet key order")
    return json.dumps(p, separators=(",", ":"))


def evidence_text(cond, status, boxes):
    return f"{COMMON}\nLocalization output: {packet_json(packet(cond, status, boxes))}"


def prompt(target, cond, status, boxes, fmt="plain"):
    """qa_spec.qa_prompt와 같은 구조(EVIDENCE_HEAD + evidence + 질문 + 출력 지시)."""
    return S.qa_prompt(target, fmt, evidence_text(cond, status, boxes))


def hash_key(pid, salt):
    return hashlib.sha256(f"{salt}:{pid}".encode()).hexdigest()


def donor_map(items, seed=17, salt="ev17_x_v1"):
    """items: {patient_id: boxes} (비어 있지 않은 유효 예측을 가진 환자만). 같은 k 그룹 안에서 patient ID의 고정 hash 순서로 정렬하고
    seed로 정한 순환 이동(1..n-1)으로 donor를 배정한다. category·정답·영상은 사용하지 않는다. 그룹 크기 1은 자기 자신(기록).
    returns {pid: {"donor": pid2, "k": k, "shift": s, "group_n": n, "same_coords": bool}}."""
    groups = {}
    for pid, b in items.items():
        groups.setdefault(len(b), []).append(pid)
    out = {}
    for k, ids in sorted(groups.items()):
        order = sorted(ids, key=lambda i: hash_key(i, salt))
        n = len(order)
        shift = random.Random(f"{salt}:{seed}:{k}:{n}").randrange(1, n) if n > 1 else 0
        for j, pid in enumerate(order):
            d = order[(j + shift) % n]
            out[pid] = {"donor": d, "k": k, "shift": shift, "group_n": n,
                        "same_coords": [list(map(int, x)) for x in items[d]] == [list(map(int, x)) for x in items[pid]]}
    return out
