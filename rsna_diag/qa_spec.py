"""iter_015 target-scope 진단의 질문·출력 형식·evidence 문장·QA parser·정답 mapping (결과를 보기 전에 고정).

- Q_O: 폐렴 의심 pulmonary opacity 존재. Q_A: RSNA 판독 규약상 Normal이 아닌가(abnormal). 둘은 별도 대화로 실행한다.
- 정답 쌍 (Q_O, Q_A): opacity=(yes,yes), normal=(no,no), not_normal_no_opacity=(no,yes).
- parser는 공백·대소문자·단일 문장부호(plain)만 정규화한다. bbox 목록, 모순, 설명만 있는 답, truncation은 별도 실패로 구분한다.
  빈 목록 []는 no로 바꾸지 않는다.
"""
import hashlib
import json
import re

Q_O = "Is there a pulmonary opacity suspicious for pneumonia in this chest radiograph?"
Q_A = ("Under the RSNA chest-radiograph labeling convention, is this image abnormal rather than Normal? "
       "An abnormal image need not contain an opacity suspicious for pneumonia. A healed rib fracture alone counts as Normal.")
QUESTIONS = {"O": Q_O, "A": Q_A}
FORMATS = {"plain": "Answer only yes or no.", "json": 'Return only {"answer":"yes"} or {"answer":"no"}.'}
TARGETS = ("O", "A")
CATEGORIES = ("opacity", "normal", "not_normal_no_opacity")
GT_PAIR = {"opacity": ("yes", "yes"), "normal": ("no", "no"), "not_normal_no_opacity": ("no", "yes")}

BBOX_FMT = "yxyx integers in [0,1000] relative to the entire square-padded image, y before x"
EVIDENCE_HEAD = "A separate localization step examined this chest radiograph for pulmonary opacities suspicious for pneumonia. "
EVIDENCE_TEXT = {
    "predicted_nonempty": "It proposed these boxes as JSON [y_min, x_min, y_max, x_max] (" + BBOX_FMT + "): {boxes}. The proposal may be wrong.",
    "predicted_empty": "It proposed no boxes. An empty proposal does not mean the image is Normal; it only means no such opacity was localized.",
    "unavailable": "No localization proposal is available for this image. This does not mean the image is Normal.",
    "oracle_nonempty": "Reference annotation boxes for pulmonary opacity, JSON [y_min, x_min, y_max, x_max] (" + BBOX_FMT + "): {boxes}.",
    "oracle_empty": "The reference annotation contains no pulmonary opacity box. This does not mean the image is Normal.",
}


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()


def qa_prompt(target, fmt, evidence_text=None):
    """evidence_text가 있으면 질문 앞에 붙는다 (원본 영상은 항상 함께 제공)."""
    core = f"{QUESTIONS[target]} {FORMATS[fmt]}"
    return core if evidence_text is None else f"{EVIDENCE_HEAD}{evidence_text}\n\n{core}"


def boxes_json(boxes):
    return json.dumps([{"box_2d": [int(round(v)) for v in b]} for b in boxes], separators=(",", ":"))


def evidence_text(kind, boxes=None):
    """kind: predicted|unavailable|oracle. boxes: 유효한 bbox 목록(빈 목록 가능). predicted에서 boxes=None이면 unavailable."""
    if kind == "unavailable" or (kind == "predicted" and boxes is None):
        return EVIDENCE_TEXT["unavailable"]
    key = f"{kind}_{'nonempty' if boxes else 'empty'}"
    return EVIDENCE_TEXT[key].format(boxes=boxes_json(boxes)) if boxes else EVIDENCE_TEXT[key]


EOT = "<end_of_turn>"
_PUNCT = ".!"


def parse_plain(raw, ended_eos):
    """returns (status, answer). status: valid | truncated | empty | bbox_list | contradictory | explanation."""
    if not ended_eos:
        return "truncated", None
    t = raw[:-len(EOT)] if raw.endswith(EOT) else raw
    t = t.strip()
    if not t:
        return "empty", None
    core = t.lower()
    if core and core[-1] in _PUNCT:
        core = core[:-1]
    if core in ("yes", "no"):
        return "valid", core
    if "box_2d" in t or re.fullmatch(r"\s*\[.*\]\s*", t, re.S):
        return "bbox_list", None
    words = set(re.findall(r"[a-z]+", t.lower()))
    if "yes" in words and "no" in words:
        return "contradictory", None
    return "explanation", None


def _pairs(pairs):
    keys = [k for k, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate key")
    return dict(pairs)


def parse_json(raw, ended_eos):
    """단일 answer 키와 yes/no 값만 허용 (fence·추가 키·중복 키 불허)."""
    if not ended_eos:
        return "truncated", None
    t = raw[:-len(EOT)] if raw.endswith(EOT) else raw
    t = t.strip()
    if not t:
        return "empty", None
    if "box_2d" in t:
        return "bbox_list", None
    try:
        v = json.loads(t, object_pairs_hook=_pairs)
    except ValueError:
        words = set(re.findall(r"[a-z]+", t.lower()))
        return ("contradictory" if {"yes", "no"} <= words else "explanation"), None
    if isinstance(v, dict) and list(v) == ["answer"] and v["answer"] in ("yes", "no"):
        return "valid", v["answer"]
    return "schema_error", None


def parse_answer(fmt, raw, ended_eos):
    return (parse_plain if fmt == "plain" else parse_json)(raw, ended_eos)


def request_key(fields):
    """request_id 재계산용. fields 전부(모델 revision, adapter digest, 영상 identity, target, format, condition, prompt sha, evidence digest, config digest)가 포함된다."""
    return sha(json.dumps(fields, sort_keys=True, default=str))[:32]
