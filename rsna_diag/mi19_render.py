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
from . import mi19_mha as M


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


def resize_scale(spacing_row, spacing_col):
    """returns (scale_row, scale_col) so that physical in-plane pixel spacing becomes isotropic
    (= min(spacing_row, spacing_col))."""
    target = min(spacing_row, spacing_col)
    return spacing_row / target, spacing_col / target


def render_slice(img_vol, sag_idx, axes, spacing_row, spacing_col, lo, hi):
    """img_vol: (nz,ny,nx). axes=(array_axis_sag,array_axis_row,array_axis_col) from mi19_mha.axis_layout.
    spacing_row/spacing_col are the physical ElementSpacing values for the row/col index axes
    (i.e. spacing_xyz[idx_row], spacing_xyz[idx_col] with the same idx_row/idx_col used to build axes).
    returns (uint8 RGB resized array, scale_row, scale_col, new_shape(h,w))."""
    array_axis_sag, array_axis_row, array_axis_col = axes
    native = M.take_slice(img_vol, array_axis_sag, array_axis_row, array_axis_col, sag_idx)
    u8 = to_uint8(native, lo, hi)
    nrow, ncol = u8.shape
    scale_row, scale_col = resize_scale(spacing_row, spacing_col)
    new_h, new_w = max(1, round(nrow * scale_row)), max(1, round(ncol * scale_col))
    im = Image.fromarray(u8, mode="L").resize((new_w, new_h), resample=Image.BILINEAR)
    rgb = np.repeat(np.asarray(im)[:, :, None], 3, axis=2)
    return rgb, new_h / nrow, new_w / ncol, (new_h, new_w)


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
