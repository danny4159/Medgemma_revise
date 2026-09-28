"""iter_026 영역 선택 진단의 질문·prompt·parser (결과를 보기 전에 고정).

TL/TR/BL/BR 사분면 기하와 strict bbox parser(parse.py)는 그대로 재사용한다. 세 조건을 정의한다.
- V (direct): 원본 영상만 보고 지정 사분면의 opacity bbox를 반환한다.
- O (oracle, D 전용): 원본 영상 + GT box 전체 목록(참조)을 주고 그 목록에서만 고르게 한다.
- RD (reader): 원본 영상 + B0 예측 bbox 전체 목록(불완전할 수 있는 proposal)을 주고 영상 근거 수정을 허용한다.
직접 prompt는 하나의 템플릿에서 quadrant/condition만 치환한다 (계획 원문 그대로).
"""
import json

from . import parse as PA
from . import roi23_spec as R

TARGETS = R.TARGETS
QUADRANT_NAME = R.QUADRANT_NAME
CONDITION_EXPR = {"TL": "cy<500 and cx<500", "TR": "cy<500 and cx>=500", "BL": "cy>=500 and cx<500",
                  "BR": "cy>=500 and cx>=500"}

V_TMPL = ('Localize all pulmonary opacities suspicious for pneumonia whose bounding-box centers are in the '
          '{quadrant} quadrant of this chest radiograph. Divide the displayed image at its horizontal and vertical '
          'midlines. Left and right refer to the displayed image, not the patient\'s sides. For a box [y_min, '
          'x_min, y_max, x_max], its center is cy=(y_min+y_max)/2 and cx=(x_min+x_max)/2. The requested quadrant '
          'satisfies {condition}. Return only a JSON list. Each entry must contain "box_2d": [y_min, x_min, y_max, '
          'x_max] and a nonempty "label" string. Coordinates must be between 0 and 1000 relative to the entire '
          'square-padded image, with y before x. Return the full enclosing boxes; do not clip boxes to the '
          'quadrant. Exclude opacities centered in other quadrants. Return [] if no such opacity is visible in the '
          'requested quadrant.')

O_TMPL = ('Supplied annotation list (reference; all pulmonary opacities suspicious for pneumonia found in this '
          'chest radiograph), JSON list of boxes [y_min, x_min, y_max, x_max] integers on a 0-1000 canvas: '
          '{list_json}\n\nUse only the supplied annotation list to answer; do not re-detect, replace, or modify '
          'it. Divide the displayed image at its horizontal and vertical midlines. Left and right refer to the '
          'displayed image, not the patient\'s sides. For a box [y_min, x_min, y_max, x_max], its center is '
          'cy=(y_min+y_max)/2 and cx=(x_min+x_max)/2. Select the entries from the supplied list whose center '
          'satisfies {condition} ({quadrant} quadrant). Return only a JSON list containing the selected entries, '
          'unchanged, each with its original "box_2d" and a nonempty "label" string. Return [] if none of the '
          'supplied boxes has its center in the requested quadrant.')

RD_TMPL = ('Supplied proposal (from a separate automated localization pass on this image; may be incomplete, may '
           'contain errors, or may be empty), JSON list of boxes [y_min, x_min, y_max, x_max] integers on a '
           '0-1000 canvas: {list_json}\n\nUsing the image, correct, add, or remove entries as needed to find all '
           'pulmonary opacities suspicious for pneumonia whose bounding-box centers are in the {quadrant} '
           'quadrant of this chest radiograph. Divide the displayed image at its horizontal and vertical '
           'midlines. Left and right refer to the displayed image, not the patient\'s sides. For a box [y_min, '
           'x_min, y_max, x_max], its center is cy=(y_min+y_max)/2 and cx=(x_min+x_max)/2. The requested quadrant '
           'satisfies {condition}. Return only a JSON list. Each entry must contain "box_2d": [y_min, x_min, '
           'y_max, x_max] and a nonempty "label" string. Coordinates must be between 0 and 1000 relative to the '
           'entire square-padded image, with y before x. Return the full enclosing boxes; do not clip boxes to '
           'the quadrant. Exclude opacities centered in other quadrants. Return [] if no such opacity is visible '
           'in the requested quadrant.')

CONDITIONS = ("V", "O", "RD")


class SpecError(RuntimeError):
    pass


def boxes_int(boxes_norm):
    return [[int(round(v)) for v in b] for b in boxes_norm]


def v_prompt(target):
    return V_TMPL.format(quadrant=QUADRANT_NAME[target], condition=CONDITION_EXPR[target])


def o_prompt(target, gt_boxes_i):
    lst = json.dumps(gt_boxes_i, separators=(",", ":"))
    return O_TMPL.format(list_json=lst, quadrant=QUADRANT_NAME[target], condition=CONDITION_EXPR[target])


def rd_prompt(target, proposal_boxes_i):
    lst = json.dumps(proposal_boxes_i, separators=(",", ":"))
    return RD_TMPL.format(list_json=lst, quadrant=QUADRANT_NAME[target], condition=CONDITION_EXPR[target])


def parse_row(raw_suffix, ended_eos):
    """parse.py의 strict bbox parser를 그대로 사용. returns dict(status, boxes, labels, problems, flags)."""
    return PA.parse_response(raw_suffix, ended_eos)


center_yx = R.center_yx
quadrant_of = R.quadrant_of
margin_ok = R.margin_ok
answers = R.answers
sha = R.sha
request_key = R.request_key
