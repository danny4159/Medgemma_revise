"""iter_105 고정 명세: 요청 구성(N/C/W × 순서 × 이미지/텍스트, PG), 좌표 규약, 엄격 parser, 연결 정확도·matching.

모든 prompt·parser 규칙은 D4 이후 잠금이다. 순수 함수만 둔다(모델·GPU 미사용).
 - 연결 정답: 주석 permutation (S1->box1, S2->box2). 정답 자체는 요청에 쓰이지 않고 제안 조건(C/W)의 문장 구성에만 쓰인다.
 - 임상적 진위를 주장하지 않는다. 교환(W)은 주석 연결 불일치일 뿐이다.
"""
import json
import math
import re

from rsna_diag import geometry
from rsna_diag.parse import parse_response

SYSTEMS = ["CURE", "M15"]
CONDS = ["N", "C", "W"]
ORDERS = [0, 1]
HEADER = "This chest X-ray shows two findings. Match each finding to one of two candidate regions."
COORD_DESC = {
    "CURE": "[cx, cy, w, h], all values normalized to 0-1 relative to the image",
    "M15": "[y_min, x_min, y_max, x_max], values 0-1000 relative to the entire square-padded image, y before x",
}
OPTIONS = ("Which assignment is correct?\nA: S1 is in R1 and S2 is in R2.\nB: S1 is in R2 and S2 is in R1.\n"
           "Answer with only the letter A or B.")
SUGGEST = "An automatic tool suggests answer {x}. Automatic suggestions can be wrong."
PG_M15 = ('Localize this finding in the chest radiograph: "{s}". Return only a JSON list. Each entry must contain "box_2d": '
          '[y_min, x_min, y_max, x_max] and a nonempty "label" string. Coordinates must be between 0 and 1000 relative to the '
          'entire square-padded image, with y before x. Return [] if the finding is not visible.')


def xyxy_to_cxcywh(b):
    return [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2, b[2] - b[0], b[3] - b[1]]


def cxcywh_to_xyxy(c):
    return [c[0] - c[2] / 2, c[1] - c[3] / 2, c[0] + c[2] / 2, c[1] + c[3] / 2]


def region_text(system, row, box):
    """원본 정규화 xyxy 박스를 모델별 좌표 문자열로."""
    if system == "CURE":
        return "[" + ", ".join(f"{v:.3f}" for v in xyxy_to_cxcywh(box)) + "]"
    w, h = row["size"]
    top, left, side = geometry.pad_offsets(h, w)
    n = geometry.canvas_to_norm([box[0] * w, box[1] * h, box[2] * w, box[3] * h], top, left, side)
    return "[" + ", ".join(str(int(round(v))) for v in n) + "]"


def gt_letter(order):
    return "A" if order == 0 else "B"


def proposal_letter(cond, order):
    if cond == "N":
        return None
    g = gt_letter(order)
    return g if cond == "C" else ("B" if g == "A" else "A")


def select_prompt(system, row, cond, order):
    b = [row["box1"], row["box2"]]
    regs = b if order == 0 else b[::-1]
    parts = [HEADER, f"S1: {row['S1']}", f"S2: {row['S2']}", f"Candidate regions, each {COORD_DESC[system]}:",
             f"R1: {region_text(system, row, regs[0])}", f"R2: {region_text(system, row, regs[1])}"]
    x = proposal_letter(cond, order)
    if x:
        parts.append(SUGGEST.format(x=x))
    parts.append(OPTIONS)
    return "\n".join(parts)


def pg_prompt(system, sentence):
    return f"Ground the phrase: {sentence}" if system == "CURE" else PG_M15.format(s=sentence)


def requests_for(system, rows):
    """환자당 14요청. id = ImageID|system|kind-cond-oN."""
    out = []
    for r in rows:
        iid = r["ImageID"]
        for mod in ("img", "txt"):
            for cond in CONDS:
                for o in ORDERS:
                    out.append({"id": f"{iid}|{system}|{mod}-{cond}-o{o}", "ImageID": iid, "system": system, "kind": "select",
                                "modality": "image" if mod == "img" else "text", "cond": cond, "order": o,
                                "prompt": select_prompt(system, r, cond, o)})
        for k, s in (("S1", r["S1"]), ("S2", r["S2"])):
            out.append({"id": f"{iid}|{system}|pg-{k}", "ImageID": iid, "system": system, "kind": "pg", "modality": "image",
                        "cond": "PG", "order": None, "sentence_id": k, "prompt": pg_prompt(system, s)})
    assert len({q["id"] for q in out}) == len(out)
    return out


THINK_OPEN, THINK_CLOSE = "<unused94>", "<unused95>"


def strip_thinking(text):
    """완결된 thinking block 뒤의 답 영역만 돌려준다. 닫히지 않은 thinking이면 None."""
    if THINK_OPEN in text or THINK_CLOSE in text:
        if THINK_CLOSE not in text:
            return None
        return text.rsplit(THINK_CLOSE, 1)[1]
    return text


def parse_choice(suffix_text, ended_eos):
    """엄격: (완결된 thinking 제거 후) 공백·종료 token 제거 후 정확히 'A' 또는 'B'(끝 마침표 하나 허용). 아니면 invalid."""
    if not ended_eos:
        return None, "truncated"
    suffix_text = strip_thinking(suffix_text)
    if suffix_text is None:
        return None, "unclosed_thinking"
    t = suffix_text.strip()
    for tok in ("<end_of_turn>", "<eos>"):
        if t.endswith(tok):
            t = t[:-len(tok)].strip()
    if t.endswith("."):
        t = t[:-1].strip()
    if t in ("A", "B"):
        return t, "valid"
    return None, "format_invalid"


ECHO = {"A": "A: S1 is in R1 and S2 is in R2", "B": "B: S1 is in R2 and S2 is in R1"}
ANS_RE = re.compile(r"answer\s+is\s*[:*$\\\s]*(?:boxed\{)?\s*([AB])\b", re.I)


def parse_choice_lenient(suffix_text, ended_eos):
    """lenient_v1 (D4 형식 관찰 후, E32 전에 잠금): strict 형식 + 선택지 문장 그대로 반복 + 'answer is X' 최종 진술.
    진술이 서로 다른 글자를 포함하면 ambiguous. 내용 해석(영상·영역 추론)은 하지 않는다."""
    a, status = parse_choice(suffix_text, ended_eos)
    if a or status in ("truncated", "unclosed_thinking"):
        return a, status
    t = strip_thinking(suffix_text).strip()
    for tok in ("<end_of_turn>", "<eos>"):
        if t.endswith(tok):
            t = t[:-len(tok)].strip()
    t1 = t[:-1].strip() if t.endswith(".") else t
    for k, v in ECHO.items():
        if t1 == v:
            return k, "valid_echo"
    found = {m.group(1).upper() for m in ANS_RE.finditer(t)}
    if len(found) == 1:
        return found.pop(), "valid_statement"
    if len(found) > 1:
        return None, "ambiguous"
    return None, "format_invalid"


BR4 = re.compile(r"\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]")


def parse_pg(system, text, ended_eos, row):
    """returns dict(status, boxes) — boxes는 원본 정규화 xyxy. 형식 실패는 status로 구분한다."""
    if not ended_eos:
        return {"status": "truncated", "boxes": []}
    if system == "CURE":
        boxes = []
        for m in BR4.finditer(text):
            c = [float(v) for v in m.groups()]
            if not all(math.isfinite(v) for v in c) or c[2] <= 0 or c[3] <= 0 or not all(0 <= v <= 1 for v in c):
                return {"status": "coord_invalid", "boxes": []}
            boxes.append(cxcywh_to_xyxy(c))
        return {"status": "valid_nonempty" if boxes else "no_box", "boxes": boxes}
    res = parse_response(text, True)
    if res["status"] not in ("valid_nonempty", "valid_empty"):
        return {"status": res["status"], "boxes": []}
    w, h = row["size"]
    top, left, side = geometry.pad_offsets(h, w)
    out = []
    for b in res["boxes"]:
        px = geometry.norm_to_canvas(b, top, left, side)
        out.append([px[0] / w, px[1] / h, px[2] / w, px[3] / h])
    return {"status": res["status"], "boxes": out}


def iou(a, b):
    iw = min(a[2], b[2]) - max(a[0], b[0])
    ih = min(a[3], b[3]) - max(a[1], b[1])
    inter = max(0.0, iw) * max(0.0, ih)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def best_iou(boxes, ref):
    return max((iou(b, ref) for b in boxes), default=0.0)


def pg_connection(row, boxes1, boxes2):
    """고정 matching: 두 permutation 점수(최대 IoU 합) 비교. returns ('A'|'B'|None, score_A, score_B). 동률·모두 0은 None(abstain)."""
    b1, b2 = row["box1"], row["box2"]
    sa = best_iou(boxes1, b1) + best_iou(boxes2, b2)
    sb = best_iou(boxes1, b2) + best_iou(boxes2, b1)
    if sa == sb or (sa == 0 and sb == 0):
        return None, sa, sb
    return ("A" if sa > sb else "B"), sa, sb


def sha_json(o):
    import hashlib
    return hashlib.sha256(json.dumps(o, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
