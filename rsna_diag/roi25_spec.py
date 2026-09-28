"""iter_025 D768 2x2 interface diagnostic: coordinate-list judgment prompts (bbox vs computed-center) x
image-attached vs text-only. 질문·기하·parser는 roi23_spec을 그대로 재사용한다 (TL/TR/BL/BR, center_yx, quadrant_of,
margin_ok, answers, largest_box_quadrant, d24_order_key, parse_answer/parse_semantic).

OB(bbox oracle)/OC(computed-center oracle) 지시문은 결과를 보기 전에 고정한다. I(image attached)/T(text-only)는
같은 지시문 텍스트에서 이미지 첨부 여부만 다르다. fmt는 plain 하나만 쓴다("Answer only yes or no.").
"""
import json

from . import roi23_spec as R

TARGETS = R.TARGETS
QUADRANT_NAME = R.QUADRANT_NAME
FMT = "plain"
CONDITIONS = ("OB_I", "OB_T", "OC_I", "OC_T")
MODALITY_OF = {"OB_I": "image", "OB_T": "text", "OC_I": "image", "OC_T": "text"}
REPRESENTATION_OF = {"OB_I": "bbox", "OB_T": "bbox", "OC_I": "center", "OC_T": "center"}

QUAD_DEF = ("The four quadrants are defined by cy<500 (top) or cy>=500 (bottom), and cx<500 (left) or cx>=500 "
            "(right).")

OB_TMPL = ("Supplied annotation list (reference), JSON list of boxes [y_min, x_min, y_max, x_max] integers on a "
           "0-1000 canvas: {list_json}\n\n"
           "This is a coordinate-list task. Use only the supplied annotation list to answer. If an image is "
           "attached, do not re-detect or replace the listed annotations. Coordinates use a 0-1000 canvas, with x "
           "increasing to the right and y increasing downward. Each box is [y_min, x_min, y_max, x_max]. Its "
           "center is cy=(y_min+y_max)/2 and cx=(x_min+x_max)/2. " + QUAD_DEF + " Is at least one listed center "
           "in the {quadrant} quadrant? Answer only yes or no.")

OC_TMPL = ("Supplied annotation list (reference), JSON list of already computed centers [cy, cx] on a 0-1000 "
           "canvas: {list_json}\n\n"
           "This is a coordinate-list task. Use only the supplied annotation list to answer. If an image is "
           "attached, do not re-detect or replace the listed annotations. Coordinates use a 0-1000 canvas, with x "
           "increasing to the right and y increasing downward. Each entry is an already computed center [cy, cx]. "
           + QUAD_DEF + " Is at least one listed center in the {quadrant} quadrant? Answer only yes or no.")


class SpecError(RuntimeError):
    pass


def boxes_int(boxes_norm):
    """[y0,x0,y1,x1] float -> int-rounded (기존 oracle과 같은 정수 좌표 직렬화)."""
    return [[int(round(v)) for v in b] for b in boxes_norm]


def _half(total):
    x = total / 2.0
    return int(x) if x == int(x) else x


def centers_from_boxes(boxes_i):
    """직렬화된(반올림된) bbox에서 중심을 0.5 단위까지 정확히 계산한다."""
    out = []
    for y0, x0, y1, x1 in boxes_i:
        out.append([_half(y0 + y1), _half(x0 + x1)])
    return out


def check_rounding_preserves_answer(boxes_norm):
    """반올림이 사분면 정답을 바꾸지 않는지 사전 검사한다 (D24는 margin>=25이므로 통과해야 한다)."""
    bi = boxes_int(boxes_norm)
    a_float = R.answers(boxes_norm)
    a_round = R.answers([[float(v) for v in b] for b in bi])
    if a_float != a_round:
        raise SpecError(f"rounding changed quadrant answer: float={a_float} round={a_round} boxes={boxes_norm}")
    return bi


def prompt(condition, target, boxes_i):
    """condition: OB_I|OB_T|OC_I|OC_T. boxes_i: int-rounded [y0,x0,y1,x1] list (nonempty)."""
    if not boxes_i:
        raise SpecError("D768 prompts require a nonempty box list (all D24 patients are opacity-positive)")
    rep = REPRESENTATION_OF[condition]
    q = QUADRANT_NAME[target]
    if rep == "bbox":
        lst = json.dumps(boxes_i, separators=(",", ":"))
        return OB_TMPL.format(list_json=lst, quadrant=q)
    centers = centers_from_boxes(boxes_i)
    lst = json.dumps(centers, separators=(",", ":"))
    return OC_TMPL.format(list_json=lst, quadrant=q)


AR_TMPL = ("Supplied annotation list (reference), list of the quadrant name(s) where an annotation is located: "
           "{list_json}\n\n"
           "This is a list-membership task. Use only the supplied list to answer; do not use any other "
           "information, and do not re-derive quadrants from coordinates or an image. Is \"{quadrant}\" present in "
           "the supplied list? Answer only yes or no.")


def ar_prompt(target, quadrant_names):
    """답 읽기 sanity: 좌표 없이 정답 사분면 이름을 text로 직접 제공하는 최소 list-membership 과제.
    quadrant_names: 사람이 읽는 이름(top-left 등) 목록, 원본 annotation 순서."""
    if not quadrant_names:
        raise SpecError("AR sanity requires a nonempty quadrant-name list")
    lst = json.dumps(quadrant_names, separators=(",", ":"))
    return AR_TMPL.format(list_json=lst, quadrant=QUADRANT_NAME[target])


def quadrant_names_from_boxes(boxes_i):
    """원본 annotation 순서를 유지한 사분면 이름 목록(중복 가능, GT 텍스트 그대로 제공)."""
    names = []
    for y0, x0, y1, x1 in boxes_i:
        cy, cx = R.center_yx([y0, x0, y1, x1])
        q = R.quadrant_of(cy, cx)
        names.append(QUADRANT_NAME[q])
    return names


parse_answer = R.parse_answer
parse_semantic = R.parse_semantic
answers = R.answers
sha = R.sha
