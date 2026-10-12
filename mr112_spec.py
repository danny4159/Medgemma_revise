"""iter_112 고정 규칙 (결과를 보기 전 lock). 순수 함수만 둔다. GT는 여기서 다루지 않는다.
MedRegA 좌표는 원 영상 기준 xyxy 0-999 정수, 기존 평가 좌표(yxyx 0-1000 canvas)와 혼용하지 않는다."""
import hashlib
import math

HEAD = ("You are a helpful medical assistant. Your task is object recognition. You are required to recognize "
        "the object in the given region. The region is represented in the form of bounding box, [x1, y1, x2, y2], "
        "with integers ranging from 0 to 999. These values correspond to the top left x, top left y, bottom right x, "
        "and bottom right y. <image>\n")
# 공식 demo_data id=7 (CT)의 영역 식별 template. modality 어구만 'CT scan' -> 'chest X-ray scan'.
TAIL = "What is <ref>this</ref><box>[[{x1}, {y1}, {x2}, {y2}]]</box> in this chest X-ray scan?"
TARGET = "lung opacity"
FULL_BOX = (0, 0, 999, 999)
THR, EPOCH = 0.70, 18
GEN_MAX_NEW_TOKENS = 400
TECH_N = 12
K_FRAC = 0.25
IOU_MAIN, IOU_AUX = 0.3, 0.5


def q999(v, size):
    return min(999, max(0, int(round(v / size * 1000))))


def box_to_medrega(box_px, w, h):
    x1, y1, x2, y2 = box_px
    return (q999(x1, w), q999(y1, h), q999(x2, w), q999(y2, h))


def prompt(box):
    return HEAD + TAIL.format(x1=box[0], y1=box[1], x2=box[2], y2=box[3])


def tech_key(patient):
    return hashlib.sha256(("iter112:" + patient).encode()).hexdigest()


def n_review(n):
    return math.ceil(K_FRAC * n)
