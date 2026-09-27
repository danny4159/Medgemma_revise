"""iter_019 mi19_render 독립 검사: resample 배율, bbox/point -> normalized yxyx 변환, geometry round-trip."""
import json
import sys

import numpy as np

sys.path.insert(0, "/SSD1_1TB/home/milab/daniel/08_medgemma/research")
from rsna_diag import mi19_render as R
from rsna_diag import geometry

results = []


def check(name, cond, detail=None):
    results.append({"name": name, "pass": bool(cond), "detail": detail})


def test_window():
    vol = np.zeros((10, 10, 10), dtype=np.float32)
    vol[2:8, 2:8, 2:8] = np.linspace(1, 100, 6 * 6 * 6).reshape(6, 6, 6)
    lo, hi = R.volume_window(vol)
    nz = vol[vol != 0]
    check("window_lo_matches_p1", abs(lo - np.percentile(nz, 1.0)) < 1e-6)
    check("window_hi_matches_p99", abs(hi - np.percentile(nz, 99.0)) < 1e-6)
    u8 = R.to_uint8(vol[:, :, 5], lo, hi)
    check("to_uint8_range", u8.min() >= 0 and u8.max() <= 255)


def test_resize_scale_isotropic():
    # spacing_y=0.5 (dense), spacing_z=2.0 (sparse) -> row axis(z) scaled up by 4x, col axis(y) unchanged
    sr, sc = R.resize_scale(spacing_y=0.5, spacing_z=2.0)
    check("resize_scale_row", abs(sr - 4.0) < 1e-9, sr)
    check("resize_scale_col", abs(sc - 1.0) < 1e-9, sc)


def test_render_slice_shape():
    nz, ny, nx = 6, 8, 3
    vol = np.random.RandomState(0).rand(nz, ny, nx).astype(np.float32) * 100 + 1
    lo, hi = R.volume_window(vol)
    rgb, sr, sc, shape = R.render_slice(vol, 1, spacing_y=1.0, spacing_z=2.0, lo=lo, hi=hi)
    expect_h = round(nz * 2.0)
    check("render_new_h", shape[0] == expect_h, (shape, expect_h))
    check("render_new_w", shape[1] == ny, shape)
    check("render_shape_matches_array", rgb.shape[:2] == shape)


def test_bbox_point_norm_roundtrip():
    # native bbox in a 4x6 (row,col) slice, scale 1x1 (no resample), then pad to square and check via geometry directly
    new_shape = (4, 6)
    bbox_rc = (1, 2, 3, 5)  # row0,col0,row1,col1
    norm = R.native_bbox_to_norm(bbox_rc, 1.0, 1.0, new_shape)
    top, left, side = geometry.pad_offsets(4, 6)
    expect = geometry.canvas_to_norm([2, 1, 5, 3], top, left, side)  # xyxy = [col0,row0,col1,row1]
    check("bbox_norm_matches_geometry", all(abs(a - b) < 1e-9 for a, b in zip(norm, expect)), (norm, expect))
    point_rc = (2, 3)
    pnorm = R.native_point_to_norm(point_rc, 1.0, 1.0, new_shape)
    y_expect = (2 + top) * 1000.0 / side
    x_expect = (3 + left) * 1000.0 / side
    check("point_norm_matches", abs(pnorm[0] - y_expect) < 1e-9 and abs(pnorm[1] - x_expect) < 1e-9, (pnorm, y_expect, x_expect))


def test_bbox_norm_within_range():
    new_shape = (10, 6)
    bbox_rc = (0, 0, 10, 6)  # full extent
    norm = R.native_bbox_to_norm(bbox_rc, 1.0, 1.0, new_shape)
    check("bbox_full_extent_norm_range", all(0 <= v <= 1000 for v in norm), norm)


for fn in [test_window, test_resize_scale_isotropic, test_render_slice_shape, test_bbox_point_norm_roundtrip,
           test_bbox_norm_within_range]:
    fn()

n_pass = sum(1 for r in results if r["pass"])
print(json.dumps({"n": len(results), "n_pass": n_pass, "results": results}, indent=1, default=str))
json.dump({"n": len(results), "n_pass": n_pass, "results": results},
          open("/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_019/tests/fixtures_render.json", "w"), indent=1, default=str)
assert n_pass == len(results)
