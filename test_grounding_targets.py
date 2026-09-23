"""iter_005 CPU geometry/target 검증 (모델 가중치 로딩 없음, GPU 0).

실행: python research/test_grounding_targets.py --out research/results/iter_005/targets_tests.json
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grounding_data import nih  # noqa: E402
from grounding_data import targets as T  # noqa: E402

MEDGEMMA_CONFIG = ("/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache/hub/models--google--medgemma-1.5-4b-it/"
                   "snapshots/91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b/config.json")
TOL = 1e-10
RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append({"test": name, "pass": bool(cond), "detail": str(detail)[:300]})
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {str(detail)[:150]}", flush=True)


def union_area_px(t, W, H, n=T.FINE):
    return t.sum() / (n * n) * W * H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    W = H = 1024

    # 1) cell 정렬 rectangle
    t = T.bbox_union_occupancy([(0, 0, 16, 16)], W, H)
    e = np.zeros((64, 64))
    e[0, 0] = 1
    check("aligned 16px box -> one full cell", np.abs(t - e).max() < TOL)
    # 2) 네 cell에 걸친 box
    t = T.bbox_union_occupancy([(8, 8, 24, 24)], W, H)
    e = np.zeros((64, 64))
    e[:2, :2] = 0.25
    check("straddling box -> 4 cells x 0.25", np.abs(t - e).max() < TOL)
    # 3) 겹치는 box: union 면적 보존 (이중 계산 없음)
    boxes = [(100, 100, 300, 250), (200, 150, 400, 400), (350, 50, 380, 90)]
    ua = 200 * 150 + 200 * 250 - (100 * 100) + 30 * 40
    t = T.bbox_union_occupancy(boxes, W, H)
    check("overlapping boxes: union area preserved", abs(union_area_px(t, W, H) - ua) < 1e-6,
          (union_area_px(t, W, H), ua))
    check("occupancy within [0,1]", t.min() >= -TOL and t.max() <= 1 + TOL)
    # 4) sub-cell 작은 box (비정수 좌표)
    t = T.bbox_union_occupancy([(100.5, 200.25, 103.5, 202.25)], W, H)
    check("small sub-pixel box area preserved", abs(union_area_px(t, W, H) - 6.0) < 1e-8, union_area_px(t, W, H))
    check("small box stays in its cell(s)", np.count_nonzero(t > 0) == 1 and t[200 // 16, 100 // 16] > 0)
    # 5) 비정방형 canvas → 896x896 resize: 정규화 좌표 target 동일, 면적 비율 보존
    W2, H2 = 2000, 1000
    b2 = [(123.0, 456.0, 987.0, 789.0), (1500.0, 10.0, 1999.0, 300.0)]
    t_orig = T.bbox_union_occupancy(b2, W2, H2)
    sx, sy = 896 / W2, 896 / H2
    t_res = T.bbox_union_occupancy([(x0 * sx, y0 * sy, x1 * sx, y1 * sy) for x0, y0, x1, y1 in b2], 896, 896)
    check("non-square resize: identical targets", np.abs(t_orig - t_res).max() < TOL, np.abs(t_orig - t_res).max())
    frac = (864 * 333 + 499 * 290) / (W2 * H2)
    check("non-square: area fraction preserved", abs(t_orig.mean() - frac) < TOL, (t_orig.mean(), frac))
    # 6) coarse = fine 4x4 평균 = 16 격자 직접 계산
    c1 = T.coarse_from_fine(T.bbox_union_occupancy(boxes, W, H))
    c2 = T.bbox_union_occupancy(boxes, W, H, n=16)
    check("coarse = 4x4 mean of fine = direct 16-grid", np.abs(c1 - c2).max() < TOL, np.abs(c1 - c2).max())
    # 7) mask occupancy vs bbox occupancy (pixel 정렬 정수 box)
    m = np.zeros((H, W))
    for x0, y0, x1, y1 in boxes:
        m[y0:y1, x0:x1] = 1
    check("mask occupancy == bbox occupancy (pixel aligned)",
          np.abs(T.mask_occupancy(m) - T.bbox_union_occupancy(boxes, W, H)).max() < TOL)
    # 비정방형·비배수 mask 크기: 면적 비율 보존
    rng = np.random.default_rng(0)
    m3 = (rng.random((1000, 777)) > 0.7).astype(float)
    tm = T.mask_occupancy(m3)
    check("mask occupancy non-divisible size: area fraction preserved", abs(tm.mean() - m3.mean()) < TOL)
    # 8) bbox CSV 명시적 파싱 (비정상 header, trailing 빈 열, xywh→xyxy)
    csv_text = ("Image Index,Finding Label,Bbox [x,y,w,h],,,\n"
                "00013118_008.png,Atelectasis,225.084745762712,547.019216763771,86.7796610169491,79.1864406779661,,,\n"
                "x.png,Mass,10,20,30,40\n")
    bx, rep = nih.parse_bbox_csv(csv_text)
    check("bbox header core/trailing detected",
          rep["header_core_matches_expected"] and rep["trailing_header_all_empty"] and rep["n_header_cols"] == 9, rep)
    check("xywh -> xyxy", bx[1]["xyxy"] == [10.0, 20.0, 40.0, 60.0]
          and abs(bx[0]["xyxy"][2] - (225.084745762712 + 86.7796610169491)) < 1e-9)
    # 9) 범위 밖 box는 clipping 없이 오류/보고
    try:
        T.bbox_union_occupancy([(1000, 1000, 1030, 1010)], W, H)
        raised = False
    except ValueError:
        raised = True
    check("out-of-canvas box raises (no clipping)", raised)
    rep_oob = nih.canvas_checks([{"line": 2, "image": "a", "label": "Mass", "xywh": [1000, 1000, 30, 10],
                                  "xyxy": [1000, 1000, 1030, 1010]}])
    check("canvas_checks reports raw exceed", rep_oob and rep_oob[0]["issues"] == ["exceeds_canvas"])

    # 10) 실제 projector 설정 (config만 사용, 가중치 없음): patches 64, tokens 16x16, AvgPool 4
    import torch
    from transformers import Gemma3Config
    from transformers.models.gemma3.modeling_gemma3 import Gemma3MultiModalProjector
    cfg = Gemma3Config.from_dict(json.load(open(MEDGEMMA_CONFIG)))
    proj = Gemma3MultiModalProjector(cfg)
    check("real projector geometry 64 -> 16 (kernel 4)",
          proj.patches_per_image == 64 and proj.tokens_per_side == 16 and proj.kernel_size == 4,
          (proj.patches_per_image, proj.tokens_per_side, proj.kernel_size))
    C = cfg.vision_config.hidden_size
    Z = rng.standard_normal((64, 64, C))
    zt = torch.from_numpy(Z).permute(2, 0, 1)[None]  # (1,C,64,64): forward의 reshape 규약(row-major patch)
    pooled_t = proj.avg_pool(zt)[0].permute(1, 2, 0).numpy()
    check("numpy avgpool == real projector AvgPool2d (float64)",
          np.abs(pooled_t - T.avgpool_features(Z)).max() < TOL, np.abs(pooled_t - T.avgpool_features(Z)).max())
    # 11) 같은 고정 affine head에서 P(h(Z)) = h(P(Z))
    Wt = rng.standard_normal((C, 1)) / np.sqrt(C)
    b = rng.standard_normal(1)
    lhs = T.avgpool_features(T.affine_head(Z, Wt, b))
    rhs = T.affine_head(T.avgpool_features(Z), Wt, b)
    d = np.abs(lhs - rhs).max()
    check("affine commutation P(h(Z)) == h(P(Z)) float64 <= 1e-10", d <= TOL, d)
    Wt8 = rng.standard_normal((C, 8)) / np.sqrt(C)
    d8 = np.abs(T.avgpool_features(T.affine_head(Z, Wt8, 0.1)) - T.affine_head(T.avgpool_features(Z), Wt8, 0.1)).max()
    check("affine commutation (8 outputs)", d8 <= TOL, d8)
    # 참고 (주장 아님): sigmoid 이후 값은 교환되지 않는다
    sig = lambda x: 1 / (1 + np.exp(-x))
    ds = np.abs(T.avgpool_features(sig(T.affine_head(Z, Wt, b))) - sig(T.affine_head(T.avgpool_features(Z), Wt, b))).max()
    check("reference: sigmoid breaks commutation (diff > 1e-6, reported only)", ds > 1e-6, ds)
    # U(P(Z)) 형태와 nearest upsampling
    U = T.upsample_nearest(T.avgpool_features(Z))
    check("U(P(Z)) shape 64x64 and blockwise constant", U.shape == Z.shape
          and np.abs(U[0:4, 0:4] - U[0, 0]).max() == 0)

    n_fail = sum(not r["pass"] for r in RESULTS)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump({"n": len(RESULTS), "n_fail": n_fail, "tol": TOL, "results": RESULTS}, f, indent=1)
    print(f"target/geometry tests: {len(RESULTS) - n_fail}/{len(RESULTS)} pass")
    if n_fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
