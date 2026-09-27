"""iter_019 mi19_baseline(C/N) 독립 검사: NCC가 실제 삽입한 patch 위치를 scale 1에서 정확히 찾는지 확인한다."""
import json
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, "/SSD1_1TB/home/milab/daniel/08_medgemma/research")
from rsna_diag import mi19_baseline as B
from rsna_diag import geometry

results = []


def check(name, cond, detail=None):
    results.append({"name": name, "pass": bool(cond), "detail": detail})


def test_condition_C_copies_box():
    box = [123.0, 45.0, 678.0, 321.0]
    out = B.condition_C(box)
    check("condition_C_identity", out == list(box))


def test_ncc_finds_exact_patch(tmp_prefix="/tmp/iter019_ncc_test"):
    rng = np.random.RandomState(7)
    side = 200
    img = (rng.rand(side, side) * 50 + 30).astype(np.uint8)
    # 배치할 distinctive patch
    patch = (rng.rand(20, 30) * 255).astype(np.uint8)
    r0, c0 = 90, 60
    img[r0:r0 + 20, c0:c0 + 30] = patch
    ref_rgb = np.repeat(img[:, :, None], 3, axis=2)  # ref == target 이미지에서 같은 patch를 다른 위치에도 복사
    tgt = img.copy()
    r1, c1 = 30, 140
    tgt[r1:r1 + 20, c1:c1 + 30] = patch
    tgt_rgb = np.repeat(tgt[:, :, None], 3, axis=2)
    ref_path, tgt_path = f"{tmp_prefix}_ref.png", f"{tmp_prefix}_tgt.png"
    Image.fromarray(ref_rgb).save(ref_path)
    Image.fromarray(tgt_rgb).save(tgt_path)
    top, left, sidepad = geometry.pad_offsets(side, side)
    ref_box_norm = geometry.canvas_to_norm([c0, r0, c0 + 30, r0 + 20], top, left, sidepad)
    pred, meta = B.condition_N(ref_path, tgt_path, ref_box_norm, (top, left, sidepad))
    check("ncc_meta_ok", meta.get("status") == "ok", meta)
    if pred is not None:
        x0, y0, x1, y1 = geometry.norm_to_canvas(pred, top, left, sidepad)
        check("ncc_finds_row", abs(y0 - r1) <= 1, (y0, r1))
        check("ncc_finds_col", abs(x0 - c1) <= 1, (x0, c1))
        check("ncc_scale_near_1", abs(meta["scale"] - 1.0) < 1e-6, meta["scale"])
    else:
        check("ncc_finds_row", False)
        check("ncc_finds_col", False)
        check("ncc_scale_near_1", False)


def test_ncc_constant_template_rejected(tmp_prefix="/tmp/iter019_ncc_const"):
    side = 60
    img = np.full((side, side), 128, dtype=np.uint8)
    ref_rgb = np.repeat(img[:, :, None], 3, axis=2)
    tgt_rgb = ref_rgb.copy()
    ref_path, tgt_path = f"{tmp_prefix}_ref.png", f"{tmp_prefix}_tgt.png"
    Image.fromarray(ref_rgb).save(ref_path)
    Image.fromarray(tgt_rgb).save(tgt_path)
    top, left, sidepad = geometry.pad_offsets(side, side)
    ref_box_norm = geometry.canvas_to_norm([10, 10, 30, 30], top, left, sidepad)
    pred, meta = B.condition_N(ref_path, tgt_path, ref_box_norm, (top, left, sidepad))
    check("ncc_constant_rejected", pred is None and meta.get("status") == "constant_template", meta)


for fn in [test_condition_C_copies_box, test_ncc_finds_exact_patch, test_ncc_constant_template_rejected]:
    fn()

n_pass = sum(1 for r in results if r["pass"])
print(json.dumps({"n": len(results), "n_pass": n_pass, "results": results}, indent=1, default=str))
json.dump({"n": len(results), "n_pass": n_pass, "results": results},
          open("/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_019/tests/fixtures_baseline.json", "w"), indent=1, default=str)
assert n_pass == len(results)
