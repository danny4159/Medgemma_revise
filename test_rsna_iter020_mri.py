"""iter_020 회귀 검사: MHA 방향/sagittal 축 결정, 일반화된 render_slice, NCC padding 좌표 수정.

iter_019 리뷰에서 확인된 결함(needs_fix)에 대한 독립 fixture:
- mi19_data/mi19_manifest가 항상 DimSize[0](x)를 sagittal 축으로 가정하던 버그
  (실제 SPIDER masks/107_t2.mha처럼 z가 sagittal인 비항등 방향에서 잘못됨).
- mi19_baseline.condition_N이 padded PNG를 norm_to_canvas(비padded 좌표)로 잘라 위치가 어긋나던 버그.
결과: results/iter_021/tests/fixtures_mri.json
"""
import json
import sys
import zipfile

import numpy as np
from PIL import Image

sys.path.insert(0, "/SSD1_1TB/home/milab/daniel/08_medgemma/research")
from rsna_diag import mi19_mha as M
from rsna_diag import mi19_render as R
from rsna_diag import mi19_baseline as B
from rsna_diag import geometry

results = []


def check(name, cond, detail=None):
    results.append({"name": name, "pass": bool(cond), "detail": detail})


def test_sagittal_axis_identity():
    # x축(index0)이 R/L, 부호 양수 (원래 가정과 동일한 케이스)
    direction = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    j, sign = M.sagittal_axis(direction, "RAI")
    check("identity_j_sag", j == 0, j)
    check("identity_sign", sign == 1.0, sign)
    axes = M.axis_layout(j)
    check("identity_axes", axes == (2, 0, 1), axes)  # array_axis_sag=2(x last axis), row=0(z),col=1(y)


def test_sagittal_axis_permuted_z_is_sagittal():
    # z(index2)가 R/L, 음의 부호 (실제 107_t2.mha와 유사한 패턴)
    direction = [[0.0, 1.0, 0.0], [0.0, 0.0, -1.0], [-1.0, 0.0, 0.0]]
    j, sign = M.sagittal_axis(direction, "ASL")
    check("permuted_j_sag", j == 2, j)
    check("permuted_sign", sign == -1.0, sign)
    axes = M.axis_layout(j)
    # remaining index axes = [0,1] -> idx_col=0,idx_row=1 -> array_axis_row=2-1=1, array_axis_col=2-0=2
    check("permuted_axes", axes == (0, 1, 2), axes)


def test_sagittal_axis_ambiguous_rejected():
    # 두 축 모두 0.5 이상 -> ambiguous, 반드시 실패해야 함
    direction = [[0.7, 0.7, 0.0], [0.7, -0.7, 0.0], [0.0, 0.0, 1.0]]
    try:
        M.sagittal_axis(direction, "R?S")
        check("ambiguous_rejected", False)
    except M.MhaError:
        check("ambiguous_rejected", True)


def test_sagittal_axis_string_mismatch_rejected():
    # 행렬은 axis0이 R/L이라 하는데 문자열이 동의하지 않음 -> 교차검증 실패로 거부
    direction = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    try:
        M.sagittal_axis(direction, "ASI")  # ao[0]='A' not R/L
        check("string_mismatch_rejected", False)
    except M.MhaError:
        check("string_mismatch_rejected", True)


def test_real_107_t2_mask_orientation():
    z = zipfile.ZipFile("/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_021/source/masks.zip")
    data = z.read("masks/107_t2.mha")
    m = M.read_mha(data)
    check("107_dimsize", m["dim_size_xyz"] == [512, 512, 17], m["dim_size_xyz"])
    j, sign = M.sagittal_axis(m["direction"], m["anatomical_orientation"])
    check("107_j_sag_is_z", j == 2, j)  # only 17 sagittal slices -> must be index axis 2 (z), not x
    axes = M.axis_layout(j)
    array_axis_sag, array_axis_row, array_axis_col = axes
    check("107_array_axis_sag", array_axis_sag == 0, array_axis_sag)  # array shape (17,512,512) -> axis0 has size 17
    check("107_slice_count", m["array"].shape[array_axis_sag] == 17, m["array"].shape)


def test_take_slice_matches_naive_for_identity():
    vol = np.arange(2 * 3 * 4).reshape(2, 3, 4)  # (z,y,x) nz=2,ny=3,nx=4
    axes = M.axis_layout(0)  # x sagittal, legacy case
    for x in range(4):
        got = M.take_slice(vol, *axes, x)
        want = vol[:, :, x]  # legacy row=z,col=y
        check(f"take_slice_identity_x{x}", np.array_equal(got, want))


def test_take_slice_matches_naive_for_z_sagittal():
    vol = np.arange(2 * 3 * 4).reshape(2, 3, 4)  # nz=2 (index axis2=z), ny=3(index1=y), nx=4(index0=x)
    axes = M.axis_layout(2)  # z sagittal (index axis 2)
    array_axis_sag, array_axis_row, array_axis_col = axes
    check("z_sagittal_array_axis_sag", array_axis_sag == 0)  # array axis0 = z(idx2), size 2
    for zi in range(2):
        got = M.take_slice(vol, *axes, zi)
        # remaining index axes = [0(x),1(y)]; idx_col=0(x), idx_row=1(y)
        # array_axis_row = 2-1=1(y), array_axis_col=2-0=2(x) -> raw = vol[zi,:,:] already (y,x) = (row,col)
        want = vol[zi, :, :]
        check(f"z_sagittal_slice_{zi}", np.array_equal(got, want))


def test_render_slice_generic_matches_legacy_shape():
    nz, ny, nx = 6, 8, 3
    vol = np.random.RandomState(0).rand(nz, ny, nx).astype(np.float32) * 100 + 1
    lo, hi = R.volume_window(vol)
    axes = M.axis_layout(0)
    rgb, sr, sc, shape = R.render_slice(vol, 1, axes, spacing_row=2.0, spacing_col=1.0, lo=lo, hi=hi)
    expect_h = round(nz * 2.0)
    check("render_new_h", shape[0] == expect_h, (shape, expect_h))
    check("render_new_w", shape[1] == ny, shape)
    check("render_shape_matches_array", rgb.shape[:2] == shape)


def test_ncc_finds_exact_patch_nonsquare_padding():
    """비정사각(가로>세로) 원본에서 top=0, left>0이 되는 padding으로 NCC의 padded-좌표 처리를 검사한다.
    수정 전 버그: norm_to_canvas가 원본(비padded) 좌표를 반환하는데 이를 그대로 padded PNG 크롭에
    사용해 template이 left만큼 어긋났다."""
    rng = np.random.RandomState(11)
    h, w = 150, 220  # w > h -> left padding > 0, top == 0
    img = (rng.rand(h, w) * 50 + 30).astype(np.uint8)
    patch = (rng.rand(20, 30) * 255).astype(np.uint8)
    r0, c0 = 80, 40
    img[r0:r0 + 20, c0:c0 + 30] = patch
    tgt = img.copy()
    r1, c1 = 10, 150
    tgt[r1:r1 + 20, c1:c1 + 30] = patch
    top, left, side = geometry.pad_offsets(h, w)
    check("padding_is_nonzero_top", top > 0 and left == 0, (top, left, side))
    ref_padded, _ = geometry.pad_square(np.repeat(img[:, :, None], 3, axis=2))
    tgt_padded, _ = geometry.pad_square(np.repeat(tgt[:, :, None], 3, axis=2))
    ref_path, tgt_path = "/tmp/iter020_ncc_ref.png", "/tmp/iter020_ncc_tgt.png"
    Image.fromarray(ref_padded).save(ref_path)
    Image.fromarray(tgt_padded).save(tgt_path)
    ref_box_norm = geometry.canvas_to_norm([c0, r0, c0 + 30, r0 + 20], top, left, side)
    pred, meta = B.condition_N(ref_path, tgt_path, ref_box_norm, (top, left, side))
    check("ncc_nonsquare_meta_ok", meta.get("status") == "ok", meta)
    if pred is not None:
        x0, y0, x1, y1 = geometry.norm_to_canvas(pred, top, left, side)
        check("ncc_nonsquare_finds_row", abs(y0 - r1) <= 1, (y0, r1))
        check("ncc_nonsquare_finds_col", abs(x0 - c1) <= 1, (x0, c1))
        check("ncc_nonsquare_scale_near_1", abs(meta["scale"] - 1.0) < 1e-6, meta["scale"])
    else:
        check("ncc_nonsquare_finds_row", False)
        check("ncc_nonsquare_finds_col", False)
        check("ncc_nonsquare_scale_near_1", False)


for fn in [test_sagittal_axis_identity, test_sagittal_axis_permuted_z_is_sagittal,
           test_sagittal_axis_ambiguous_rejected, test_sagittal_axis_string_mismatch_rejected,
           test_real_107_t2_mask_orientation, test_take_slice_matches_naive_for_identity,
           test_take_slice_matches_naive_for_z_sagittal, test_render_slice_generic_matches_legacy_shape,
           test_ncc_finds_exact_patch_nonsquare_padding]:
    fn()

n_pass = sum(1 for r in results if r["pass"])
print(json.dumps({"n": len(results), "n_pass": n_pass, "results": results}, indent=1, default=str))
import os
os.makedirs("/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_021/tests", exist_ok=True)
json.dump({"n": len(results), "n_pass": n_pass, "results": results},
          open("/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_021/tests/fixtures_mri.json", "w"), indent=1, default=str)
assert n_pass == len(results), "some fixtures failed"
