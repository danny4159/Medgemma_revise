"""iter_047 소견 상태 교정·보존 진단: 고정 사전·문장 mapping·prompt·상태 parser·평가 규칙 상수 (CPU only).

GT/truth는 평가 함수에만 인자로 들어간다. bbox parser는 쓰지 않는다 (새 상태 schema의 별도 strict parser).
"""
import hashlib
import json
import re

from rsna_diag import parse

VERSION = "rr47_v2"
SEED = 4701          # 표본 선택
BOOT_SEED = 4702     # 환자 bootstrap
BOOT_B = 10000
CAPS = [1000, 2000, 4000]
STATES = ("present", "absent")
ANSWERS = ("present", "absent", "uncertain")
IDS = ("qA", "qB")

# 고정 finding 사전. name: 질문용 이름, sent: 상태별 canonical 문장 (수식어·위치·중증도 없음).
FINDINGS = {
    "cardiomegaly": dict(name="cardiomegaly", present="Cardiomegaly is present.", absent="There is no cardiomegaly."),
    "effusion": dict(name="pleural effusion", present="Pleural effusion is present.", absent="There is no pleural effusion."),
    "consolidation": dict(name="consolidation", present="Consolidation is present.", absent="There is no consolidation."),
    "pneumothorax": dict(name="pneumothorax", present="Pneumothorax is present.", absent="There is no pneumothorax."),
    "nodule": dict(name="pulmonary nodule", present="A pulmonary nodule is present.", absent="There is no pulmonary nodule."),
    "atelectasis": dict(name="atelectasis", present="Atelectasis is present.", absent="There is no atelectasis."),
    "scoliosis": dict(name="scoliosis", present="Scoliosis is present.", absent="There is no scoliosis."),
    "aortic_elongation": dict(name="aortic elongation", present="Aortic elongation is present.", absent="There is no aortic elongation."),
    "pacemaker": dict(name="pacemaker", present="A pacemaker is present.", absent="There is no pacemaker."),
}
FINDING_ORDER = list(FINDINGS)


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def canon(o):
    return json.dumps(o, sort_keys=True, ensure_ascii=False)


def flip(s):
    return "absent" if s == "present" else "present"


def draft_code(a, b):
    """상태 쌍 -> '00','01','10','11' (1=present)."""
    return f"{int(a == 'present')}{int(b == 'present')}"


def code_states(code):
    return ["present" if c == "1" else "absent" for c in code]


DRAFT_CODES = ["00", "01", "10", "11"]


def draft_text(finding_pair, code):
    """finding_pair: {qA: finding, qB: finding}. 두 문장 canonical 초안."""
    st = dict(zip(IDS, code_states(code)))
    return [(i, FINDINGS[finding_pair[i]][st[i]]) for i in IDS]


# ---------------- prompts ----------------
_JSON_TAIL = ('Return only a JSON object, with no other text, in which every key is one of the IDs listed above and every value is exactly one of '
              '"present", "absent" or "uncertain".')


def _draft_block(items):
    return "\n".join(f'{i}: "{s}"' for i, s in items)


def _example(ids):
    return "{" + ", ".join(f'"{i}": "<status>"' for i in ids) + "}"


def prompt_R1(items):
    return ("Below is a draft report with two statements about a chest radiograph. Review each statement against the radiograph and "
            "give the final status of each finding.\n\nDraft report:\n" + _draft_block(items) + "\n\n" + _JSON_TAIL +
            " Format: " + _example(IDS))


R2_EXTRA = ("The draft may be entirely correct. Change a statement only if the radiograph does not support it; "
            "if a statement is supported by the radiograph, keep it unchanged.")


def prompt_R2(items):
    return ("Below is a draft report with two statements about a chest radiograph. Review each statement against the radiograph and "
            "give the final status of each finding. " + R2_EXTRA + "\n\nDraft report:\n" + _draft_block(items) + "\n\n" + _JSON_TAIL +
            " Format: " + _example(IDS))


def prompt_T(items):
    """R2와 같은 소견·초안·출력 지시. 영상은 제공하지 않으며 불확실성을 허용한다."""
    return ("Below is a draft report with two statements about a chest radiograph. No radiograph is attached to this request. "
            "Give the final status of each finding. " + R2_EXTRA.replace("the radiograph", "the available information") +
            " If a status cannot be determined, answer \"uncertain\".\n\nDraft report:\n" + _draft_block(items) + "\n\n" + _JSON_TAIL +
            " Format: " + _example(IDS))


def prompt_BJ(finding_pair):
    names = "\n".join(f'{i}: {FINDINGS[finding_pair[i]]["name"]}' for i in IDS)
    return ("Look at this chest radiograph. For each of the two findings below, decide whether the finding is present or absent in the image.\n\n"
            "Findings:\n" + names + "\n\n" + _JSON_TAIL + " Format: " + _example(IDS))


def prompt_BI(fid, pid):
    return (f'Look at this chest radiograph. Decide whether the following finding is present or absent in the image.\n\nFinding:\n'
            f'{pid}: {FINDINGS[fid]["name"]}\n\n' + _JSON_TAIL.replace("every key is one of the IDs listed above", f'the only key is "{pid}"') +
            " Format: " + _example([pid]))


def prompt_O(items, truth_pair):
    """D8 전용 oracle: 정답 상태를 명시적으로 제공해 schema·편집 연결만 검사한다."""
    ver = "\n".join(f"{i}: {s}" for i, s in truth_pair)
    return ("Below is a draft report with two statements about a chest radiograph, followed by the verified final status of each finding.\n\n"
            "Draft report:\n" + _draft_block(items) + "\n\nVerified final status:\n" + ver +
            "\n\nReturn the verified final status of each finding.\n\n" + _JSON_TAIL + " Format: " + _example(IDS))


# ---------------- parser ----------------
FENCE_OPEN = re.compile(r"^```(?:json)?\s*\n", re.I)
FENCE_CLOSE = re.compile(r"\n?```\s*$")


def _no_dup(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError("dup_key")
        d[k] = v
    return d


def parse_state(raw_suffix, ended_eos, required_ids):
    """엄격 parser. returns dict(status, answers{ID:state|None}, flags).
    status: ok / truncated / empty / not_json / dup_key / wrong_keys / bad_value / multiple_json / think_unclosed.
    허용 wrapper: 앞뒤 공백, 끝의 <end_of_turn>, ```json ... ``` 한 쌍. 그 밖의 문장·여러 JSON·thinking marker는 모두 invalid (고르지 않는다)."""
    res = dict(status="ok", answers={i: None for i in required_ids}, flags=[])
    if not ended_eos:
        res["status"] = "truncated"
        return res
    text = raw_suffix
    if text.endswith(parse.EOT):
        text = text[:-len(parse.EOT)]
    if parse.THINK_OPEN in text or parse.THINK_CLOSE in text:
        # v2(D 형식 수정 1회): 완결된 thinking block 하나(맨 앞 열림, 닫힘 하나)만 허용하고 답은 닫힘 뒤에서만 읽는다. thinking 안의 JSON은 읽지 않는다.
        if not (text.lstrip().startswith(parse.THINK_OPEN) and text.count(parse.THINK_OPEN) == 1 and text.count(parse.THINK_CLOSE) == 1
                and text.index(parse.THINK_OPEN) < text.index(parse.THINK_CLOSE)):
            res["status"] = "think_marker"
            return res
        text = text.split(parse.THINK_CLOSE, 1)[1]
        res["flags"].append("thinking_block")
    t = text.strip()
    if not t:
        res["status"] = "empty"
        return res
    if FENCE_OPEN.match(t) and FENCE_CLOSE.search(t):
        t = FENCE_CLOSE.sub("", FENCE_OPEN.sub("", t, count=1), count=1).strip()
        res["flags"].append("fenced")
    if "```" in t:
        res["status"] = "not_json"
        return res
    try:
        obj, end = json.JSONDecoder(object_pairs_hook=_no_dup).raw_decode(t)
    except ValueError as e:
        res["status"] = "dup_key" if str(e) == "dup_key" else "not_json"
        return res
    if t[end:].strip():
        res["status"] = "multiple_json" if t[end:].lstrip().startswith(("{", "[")) else "not_json"
        return res
    if not isinstance(obj, dict) or sorted(obj) != sorted(required_ids):
        res["status"] = "wrong_keys"
        return res
    ans = {}
    for k, v in obj.items():
        if not isinstance(v, str) or v.strip().lower() not in ANSWERS or v != v.strip().lower():
            res["status"] = "bad_value"
            return res
        ans[k] = v
    res["answers"] = ans
    return res


def final_state(parsed, i):
    """최종 상태: ok면 답, 아니면 'invalid'."""
    if parsed["status"] != "ok":
        return "invalid"
    return parsed["answers"][i]


def render_final(finding_pair, states):
    """결정론적 편집기: 상태 -> canonical 문장. uncertain/invalid는 문장을 만들지 않는다 (None)."""
    out = []
    for i in IDS:
        s = states[i]
        out.append(FINDINGS[finding_pair[i]][s] if s in STATES else None)
    return out


def request_id(kind, patient, cond, targets, prompt_sha, image_sha):
    return sha(f"{VERSION}|{kind}|{patient}|{cond}|{','.join(targets)}|{prompt_sha}|{image_sha}")[:32]
