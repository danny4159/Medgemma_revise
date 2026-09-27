"""iter_019 표시 영상 렌더링: MRI volume -> in-plane spacing 보정 uint8 2D slice, bbox·점 좌표 변환.

- intensity window: volume 전체의 유한한 비배경(0이 아닌) intensity의 1-99 percentile로 clip 후 [0,255] 선형 변환.
  같은 volume의 모든 slice에 동일 window를 적용한다.
- 종횡비: in-plane spacing(spacing_y, spacing_z)이 다르면 더 촘촘한 축을 기준으로 다른 축만 배율 조정한다
  (PIL bilinear). 배율은 반올림 정수 픽셀 크기를 만든다.
- bbox/point는 native(z,y) 픽셀 좌표(half-open) -> resize 배율 -> geometry.pad_square affine -> canvas_to_norm 순서로 변환한다.
"""
import numpy as np
from PIL import Image

from . import geometry


def volume_window(img_vol):
    """returns (lo, hi) intensity for 1-99 percentile of finite, nonzero voxels."""
    flat = img_vol.astype(np.float64).ravel()
    finite = flat[np.isfinite(flat)]
    nonzero = finite[finite != 0]
    if nonzero.size == 0:
        nonzero = finite
    lo, hi = np.percentile(nonzero, [1.0, 99.0])
    if hi <= lo:
        hi = lo + 1.0
    return float(lo), float(hi)


def to_uint8(slice2d, lo, hi):
    a = np.clip(slice2d.astype(np.float64), lo, hi)
    a = (a - lo) / (hi - lo)
    return np.round(a * 255.0).astype(np.uint8)


def resize_scale(spacing_y, spacing_z):
    """returns (scale_row, scale_col) so that physical pixel spacing becomes isotropic (= min(spacing_y,spacing_z))."""
    target = min(spacing_y, spacing_z)
    return spacing_z / target, spacing_y / target  # (row scale from z, col scale from y)


def render_slice(img_vol, x_idx, spacing_y, spacing_z, lo, hi):
    """img_vol: (nz,ny,nx). returns (uint8 RGB resized array, scale_row, scale_col, new_shape(h,w))."""
    native = img_vol[:, :, x_idx]  # (nz, ny) = (row=z, col=y)
    u8 = to_uint8(native, lo, hi)
    nz, ny = u8.shape
    scale_row, scale_col = resize_scale(spacing_y, spacing_z)
    new_h, new_w = max(1, round(nz * scale_row)), max(1, round(ny * scale_col))
    im = Image.fromarray(u8, mode="L").resize((new_w, new_h), resample=Image.BILINEAR)
    rgb = np.repeat(np.asarray(im)[:, :, None], 3, axis=2)
    return rgb, new_h / nz, new_w / ny, (new_h, new_w)


def native_bbox_to_norm(bbox_rc, scale_row, scale_col, new_shape, pad_top_left_side=None):
    """bbox_rc: (row0,col0,row1,col1) native half-open. -> resized xyxy -> pad_square -> normalized yxyx[0,1000].
    pad_top_left_side가 주어지면 그 affine을 쓰고, 없으면 new_shape 기준으로 pad_square를 계산한다(호출측이 동일 affine을 재사용해야 함)."""
    r0, c0, r1, c1 = bbox_rc
    x0, y0, x1, y1 = c0 * scale_col, r0 * scale_row, c1 * scale_col, r1 * scale_row
    h, w = new_shape
    top, left, side = pad_top_left_side if pad_top_left_side else geometry.pad_offsets(h, w)
    return geometry.canvas_to_norm([x0, y0, x1, y1], top, left, side)


def native_point_to_norm(point_rc, scale_row, scale_col, new_shape, pad_top_left_side=None):
    r, c = point_rc
    x, y = c * scale_col, r * scale_row
    h, w = new_shape
    top, left, side = pad_top_left_side if pad_top_left_side else geometry.pad_offsets(h, w)
    return [(y + top) * 1000.0 / side, (x + left) * 1000.0 / side]
