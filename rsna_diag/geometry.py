"""전처리(정사각 padding)와 좌표 변환.

좌표 규약
- 원본/pixel bbox: xyxy = [x0, y0, x1, y1] (pixel, 원본 canvas).
- 모델 출력/GT 정규화 bbox: [y0, x0, y1, x1] in [0, 1000], padding된 정사각 전체 영상 기준.
padding: 중앙 정렬, 위/왼쪽에 floor(d/2), 아래/오른쪽에 나머지 (공식 notebook pad_image_to_square와 동일).
"""
import numpy as np
from PIL import Image


def pad_offsets(h, w):
    """returns (top, left, side)."""
    side = max(h, w)
    top = (side - h) // 2 if h < w else 0
    left = (side - w) // 2 if w < h else 0
    return top, left, side


def to_uint8_rgb_preserving(arr, mode=None):
    """값 보존 경로: uint8 L/RGB는 밝기 유지(gray는 채널 복제), RGBA는 흰 배경 alpha 합성(반올림).

    uint8이 아닌 dtype은 지원하지 않는다 (임의 정규화 금지) -> ValueError.
    """
    a = np.asarray(arr)
    if a.dtype != np.uint8:
        raise ValueError(f"unsupported dtype {a.dtype}")
    if a.ndim == 2:
        return np.repeat(a[:, :, None], 3, axis=2)
    if a.ndim == 3 and a.shape[2] == 1:
        return np.repeat(a, 3, axis=2)
    if a.ndim == 3 and a.shape[2] == 3:
        return a.copy()
    if a.ndim == 3 and a.shape[2] == 4:
        af = a[:, :, 3:4].astype(np.float64) / 255.0
        rgb = a[:, :, :3].astype(np.float64)
        out = rgb * af + 255.0 * (1.0 - af)
        return np.floor(out + 0.5).astype(np.uint8)
    raise ValueError(f"unsupported shape {a.shape}")


def pad_square(rgb):
    """검은 padding, 중앙, 위/왼쪽 floor. returns (padded, (top, left, side))."""
    h, w = rgb.shape[:2]
    top, left, side = pad_offsets(h, w)
    out = np.zeros((side, side, rgb.shape[2]), dtype=rgb.dtype)
    out[top:top + h, left:left + w] = rgb
    return out, (top, left, side)


def notebook_pad_emulation(arr):
    """공식 notebook의 preprocess를 numpy로 모사한다 (skimage 미설치, pip 불가 -> 근사 emulation).

    skimage.util.img_as_ubyte(uint8) = 항등. gray2rgb: 채널 복제(uint8 유지).
    rgba2rgb: img_as_float(x/255) 후 흰 배경 alpha 합성 -> float64 [0,1]. 그 뒤 `* 255` 후 astype(uint8):
      - float 경로(RGBA 입력): 값 x/255*255 를 uint8로 truncation (부동소수 오차로 1 LSB 감소 가능).
      - uint8 경로(L/RGB 입력): uint8 * 255 는 uint8에서 modulo 256 wrap (v -> (255*v) mod 256).
    """
    a = np.asarray(arr)
    if a.dtype != np.uint8:
        raise ValueError("emulation only for uint8 input")
    if a.ndim == 2:
        a = np.repeat(a[:, :, None], 3, axis=2)
    if a.shape[2] == 4:
        f = a.astype(np.float64) / 255.0
        alpha = f[:, :, 3:4]
        a = f[:, :, :3] * alpha + 1.0 * (1.0 - alpha)
    padded, aff = pad_square(a)
    return (padded * 255).astype(np.uint8), aff


def canvas_to_norm(box_xyxy, top, left, side):
    """원본 pixel xyxy -> padding canvas 기준 [y0,x0,y1,x1] (0-1000, float)."""
    x0, y0, x1, y1 = box_xyxy
    return [(y0 + top) * 1000.0 / side, (x0 + left) * 1000.0 / side,
            (y1 + top) * 1000.0 / side, (x1 + left) * 1000.0 / side]


def norm_to_canvas(box_yxyx, top, left, side):
    """padding canvas 기준 [y0,x0,y1,x1] (0-1000) -> 원본 pixel xyxy (clipping 없음)."""
    y0, x0, y1, x1 = box_yxyx
    return [x0 * side / 1000.0 - left, y0 * side / 1000.0 - top,
            x1 * side / 1000.0 - left, y1 * side / 1000.0 - top]


def norm_to_padded(box_yxyx, side):
    """padding canvas 기준 [y0,x0,y1,x1] (0-1000) -> padding된 정사각 이미지 자체의 pixel xyxy
    (top/left를 빼지 않는다; norm_to_canvas와 달리 padded 이미지 파일에 직접 적용하기 위한 함수)."""
    y0, x0, y1, x1 = box_yxyx
    return [x0 * side / 1000.0, y0 * side / 1000.0, x1 * side / 1000.0, y1 * side / 1000.0]


def padded_to_norm(box_xyxy, side):
    """padded 정사각 이미지 pixel xyxy -> normalized [y0,x0,y1,x1] (0-1000) (top/left를 더하지 않는다)."""
    x0, y0, x1, y1 = box_xyxy
    return [y0 * 1000.0 / side, x0 * 1000.0 / side, y1 * 1000.0 / side, x1 * 1000.0 / side]


def to_pil(rgb):
    return Image.fromarray(rgb)
