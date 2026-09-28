"""iter_015/016 target-scope 진단의 질문·출력 형식·evidence 문장·QA parser·정답 mapping (결과를 보기 전에 고정).

iter_016: strict parser(parse_plain/parse_json)는 그대로 두고 별도의 semantic_v1(parse_semantic)을 추가한다. parser는 정답 category를 입력으로 받지 않는다.

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


SEMANTIC_VERSION = "semantic_v1"
_NORMAL_MAP = {"normal": "no", "abnormal": "yes"}


def _bare_word(t):
    """전체 문자열이 단어 하나(+ 마지막 단일 . 또는 !)이면 소문자 단어, 아니면 None. 내부 공백·중복 문장부호는 받지 않는다."""
    core = t.lower()
    if core and core[-1] in _PUNCT:
        core = core[:-1]
    return core if re.fullmatch(r"[a-z]+", core) else None


def parse_semantic(target, fmt, raw, ended_eos):
    """semantic_v1. returns (status, answer, conversion). conversion: identity(strict와 동일) | bare_yes_no | json_answer | bare_normal_abnormal | None.

    1 EOS 없으면 truncated. 2 끝의 <end_of_turn> 한 개와 앞뒤 공백만 제거. 3 전체가 yes/no(대소문자·마지막 단일 . !)면 두 출력 지시 모두 받는다.
    4 전체가 JSON이고 유일한 키 answer의 값이 정확한 소문자 yes/no면 받는다(중복 키·추가 키·배열·fence 불가).
    5 target=='A'에서만 전체 bare Normal/Abnormal을 no/yes로 대응한다 (JSON 값의 Normal/Abnormal, Q_O의 Normal은 불허).
    설명문·혼합 답·모순·bbox·빈 목록·부분 일치는 구제하지 않는다 (strict parser의 실패 분류를 그대로 쓴다)."""
    if target not in QUESTIONS:
        raise ValueError(f"unknown target {target!r}")
    st, ans = parse_answer(fmt, raw, ended_eos)
    if st == "valid":
        return "valid", ans, "identity"
    if st == "truncated" or st == "empty":
        return st, None, None
    t = (raw[:-len(EOT)] if raw.endswith(EOT) else raw).strip()
    w = _bare_word(t)
    if w in ("yes", "no"):
        return "valid", w, "bare_yes_no"
    if w in _NORMAL_MAP and target == "A":
        return "valid", _NORMAL_MAP[w], "bare_normal_abnormal"
    if t.startswith("{"):
        try:
            v = json.loads(t, object_pairs_hook=_pairs)
        except ValueError:
            v = None
        if isinstance(v, dict) and list(v) == ["answer"] and v["answer"] in ("yes", "no"):
            return "valid", v["answer"], "json_answer"
    return st, None, None


def request_key(fields):
    """request_id 재계산용. fields 전부(모델 revision, adapter digest, 영상 identity, target, format, condition, prompt sha, evidence digest, config digest)가 포함된다."""
    return sha(json.dumps(fields, sort_keys=True, default=str))[:32]
