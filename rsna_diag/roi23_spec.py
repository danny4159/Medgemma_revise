"""iter_023 사분면 전이 진단의 질문·정답 규칙 (결과를 보기 전에 고정).

과제: 주석된 opacity bbox 중 중심이 지정 사분면에 있는 것이 하나 이상인가. 영상 중앙 가로/세로선으로 4분할하고
좌우는 표시된 영상 기준이다 (환자 좌우가 아니다). bbox center=[(y0+y1)/2,(x0+x1)/2]. 500 경계는 lower/right에 배정한다
(margin이 25 미만인 환자는 주평가에서 제외하므로 실제로는 경계값이 주지표에 나타나지 않는다).

evidence 문구는 qa_spec.EVIDENCE_TEXT/evidence_text를 그대로 재사용한다 (bbox proposal 서술은 과제와 무관하게 동일).
parser도 qa_spec.parse_answer/parse_semantic을 그대로 재사용한다 (target이 "A"가 아니므로 Normal/Abnormal 대응은 적용되지 않는다).
"""
import hashlib
import json

from . import qa_spec as QS

TARGETS = ("TL", "TR", "BL", "BR")
QUADRANT_NAME = {"TL": "top-left", "TR": "top-right", "BL": "bottom-left", "BR": "bottom-right"}
FORMATS = QS.FORMATS

TEMPLATE = ("For this task, the location of a pulmonary opacity suspicious for pneumonia is the center of its "
            "enclosing bounding box. Divide the displayed image into four equal quadrants at its horizontal and "
            "vertical midlines. Left and right refer to the displayed image, not the patient's sides. Is at least "
            "one such opacity centered in the {quadrant} quadrant? {fmt}")


def direct_prompt(target, fmt):
    return TEMPLATE.format(quadrant=QUADRANT_NAME[target], fmt=FORMATS[fmt])


def qa_prompt(target, fmt, evidence_text=None):
    core = direct_prompt(target, fmt)
    return core if evidence_text is None else f"{QS.EVIDENCE_HEAD}{evidence_text}\n\n{core}"


def evidence_text(kind, boxes=None):
    return QS.evidence_text(kind, boxes)


def center_yx(box_yxyx):
    y0, x0, y1, x1 = box_yxyx
    return (y0 + y1) / 2.0, (x0 + x1) / 2.0


def quadrant_of(cy, cx):
    top = cy < 500.0
    left = cx < 500.0
    return ("TL" if left else "TR") if top else ("BL" if left else "BR")


def margin_ok(boxes, margin=25.0):
    """모든 box의 중심이 두 중앙선 각각에서 margin 이상 떨어져 있으면 True."""
    for b in boxes:
        cy, cx = center_yx(b)
        if abs(cy - 500.0) < margin or abs(cx - 500.0) < margin:
            return False
    return True


def answers(boxes):
    """returns {target: 'yes'|'no'} - 어떤 box든 중심이 그 사분면에 있으면 yes."""
    quads = {quadrant_of(*center_yx(b)) for b in boxes}
    return {t: ("yes" if t in quads else "no") for t in TARGETS}


def largest_box_quadrant(boxes):
    """가장 큰 GT box의 중심 사분면. 면적 동률은 ann_id로 정렬해 첫 번째를 쓴다 (호출측에서 정렬된 boxes를 넘긴다)."""
    def area(b):
        y0, x0, y1, x1 = b["yxyx_norm"]
        return max(0.0, y1 - y0) * max(0.0, x1 - x0)
    best = sorted(boxes, key=lambda b: (-area(b), b["ann_id"]))[0]
    return quadrant_of(*center_yx(best["yxyx_norm"]))


def d24_order_key(pid):
    return hashlib.sha256(("iter023-D24-v1|" + pid).encode()).hexdigest()


parse_answer = QS.parse_answer
request_key = QS.request_key
sha = QS.sha


def parse_semantic(target, fmt, raw, ended_eos):
    """qa_spec.parse_semantic과 같은 semantic_v1 규칙이되 target 제한이 없다 (TL/TR/BL/BR에는 Normal/Abnormal 대응이 없다:
    qa_spec의 target=='A' 분기를 그대로 두면 우리 target에서 항상 미적용이므로 그 분기 자체를 제외했다).
    returns (status, answer, conversion). conversion: identity | bare_yes_no | json_answer | None."""
    if target not in TARGETS:
        raise ValueError(f"unknown target {target!r}")
    st, ans = QS.parse_answer(fmt, raw, ended_eos)
    if st == "valid":
        return "valid", ans, "identity"
    if st in ("truncated", "empty"):
        return st, None, None
    t = (raw[:-len(QS.EOT)] if raw.endswith(QS.EOT) else raw).strip()
    w = QS._bare_word(t)
    if w in ("yes", "no"):
        return "valid", w, "bare_yes_no"
    if t.startswith("{"):
        try:
            v = json.loads(t, object_pairs_hook=QS._pairs)
        except ValueError:
            v = None
        if isinstance(v, dict) and list(v) == ["answer"] and v["answer"] in ("yes", "no"):
            return "valid", v["answer"], "json_answer"
    return st, None, None
