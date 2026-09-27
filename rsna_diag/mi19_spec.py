"""iter_019 reference-instance 진단의 prompt·출력 형식(결과를 보기 전에 고정).

출력 계약은 기존 RSNA grounding과 동일하다 (parse.parse_response): 'Final Answer:' 뒤 JSON list,
각 entry는 box_2d(yxyx, 0-1000, 대상 정사각 padding 영상 기준)와 비어있지 않은 label. J/S2/A/O는 정확히
한 box를 요구한다(모델이 더 내면 parse.py의 ambiguous/기존 실패 분류로 걸러진다).
"""
import hashlib
import json

BOX_LABEL = "referenced vertebra"
BBOX_FMT = "yxyx integers in [0,1000] relative to the entire square-padded image, y before x"
OUTPUT_INSTR = (
    'Return only a JSON list after the exact marker "Final Answer:". The list must contain exactly one entry with '
    '"box_2d": [y_min, x_min, y_max, x_max] and "label": "referenced vertebra". '
    f"Coordinates must be integers between 0 and 1000 relative to the entire square-padded image, with y before x."
)
DESCRIBE_INSTR = ("Describe, in 1-3 concise plain-language sentences, the location and visible shape of this vertebra "
                   "so it could be recognized in a different sagittal slice from the same MRI volume. "
                   "Do not output coordinates, boxes, or JSON. Do not describe or refer to the second image.")

CONDITIONS = ("J_RT", "J_TR", "S1", "S2", "A", "O")


def box_str(b):
    return json.dumps([int(round(v)) for v in b])


def prompt_J_RT(ref_box_norm):
    return (
        "The first image is a REFERENCE sagittal MRI slice from the same patient's lumbar spine MRI volume as the "
        "second image. Both images use the same square-padded canvas convention. In the first image, a specific "
        f"vertebra (including its posterior elements / vertebral arch) is marked by the box {box_str(ref_box_norm)} "
        f"({BBOX_FMT}). The second image is the TARGET sagittal slice, a different slice from the same MRI volume. "
        "Locate the SAME anatomical vertebra (the same physical vertebra, including its full visible extent and "
        "posterior elements) in the second (target) image. " + OUTPUT_INSTR +
        " The box you return must describe the SECOND image."
    )


def prompt_J_TR(ref_box_norm):
    return (
        "The first image is the TARGET sagittal MRI slice from a lumbar spine MRI volume. The second image is a "
        "REFERENCE sagittal slice from the same MRI volume as the first image. Both images use the same "
        f"square-padded canvas convention. In the second (reference) image, a specific vertebra (including its "
        f"posterior elements / vertebral arch) is marked by the box {box_str(ref_box_norm)} ({BBOX_FMT}). "
        "Locate the SAME anatomical vertebra (the same physical vertebra, including its full visible extent and "
        "posterior elements) in the first (target) image. " + OUTPUT_INSTR +
        " The box you return must describe the FIRST image."
    )


def prompt_S1(ref_box_norm):
    return (
        "The first image is a REFERENCE sagittal MRI slice from the same patient's lumbar spine MRI volume as the "
        "second image. Both images use the same square-padded canvas convention. In the first image, a specific "
        f"vertebra (including its posterior elements / vertebral arch) is marked by the box {box_str(ref_box_norm)} "
        f"({BBOX_FMT}). " + DESCRIBE_INSTR
    )


def prompt_S2(description_text):
    return (
        "This is a sagittal MRI slice from a lumbar spine MRI volume. A specific vertebra was described as follows, "
        f'based on a DIFFERENT slice from the same MRI volume (not shown): "{description_text}" '
        "Locate this vertebra (including its full visible extent and posterior elements) in THIS image. " + OUTPUT_INSTR
    )


def prompt_A(ref_box_norm):
    return (
        "This is a TARGET sagittal MRI slice from a lumbar spine MRI volume. In a DIFFERENT sagittal slice from the "
        "SAME MRI volume (not shown to you), a specific vertebra (including its posterior elements / vertebral arch) "
        f"was marked by the box {box_str(ref_box_norm)} ({BBOX_FMT}), using the exact same square-padded canvas "
        "convention as this image (same padding rule, same 0-1000 normalization, same physical volume grid). "
        "Locate the SAME anatomical vertebra in THIS image. " + OUTPUT_INSTR
    )


def prompt_O(point_norm):
    y, x = point_norm
    return (
        "This is a sagittal MRI slice from a lumbar spine MRI volume. The point (y,x) = "
        f"[{int(round(y))},{int(round(x))}] (in [0,1000] relative to the entire square-padded image, y before x) "
        "lies inside a specific vertebra, including its posterior elements / vertebral arch. Localize the full "
        "visible extent of that vertebra in THIS image. " + OUTPUT_INSTR
    )


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()
