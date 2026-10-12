"""iter_019 C(위치 복사)·N(다중 scale NCC 영상 매칭) baseline. MedGemma를 호출하지 않는다.

C: 같은 volume·같은 렌더링 파이프라인이므로 R의 정규화 box를 T에 그대로 복사한다 (물리 좌표 대조를 겸한다).
N: R의 padding grayscale patch(ref box)를 template으로 삼아 T padding grayscale 전체에서 scale {0.75,1,1.25}
   normalized cross-correlation(NCC, torch conv2d 기반) 최댓값 위치를 찾는다. 동점: scale 1에 가까운 순서 ->
   좌상단(y0,x0) 오름차순. target GT는 검색 범위·scale 선택에 쓰지 않는다.
"""
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

from . import geometry

SCALES = (0.75, 1.0, 1.25)


def condition_C(ref_box_norm):
    return list(ref_box_norm)


def _gray_padded(path):
    arr = np.asarray(Image.open(path).convert("L")).astype(np.float32)
    return arr


def _ncc_map(image, template):
    """image,template: 2D float32 torch tensor. returns NCC map same conv 'valid' output size, or None if template too big."""
    ih, iw = image.shape
    th, tw = template.shape
    if th > ih or tw > iw or th < 1 or tw < 1:
        return None
    img = image.unsqueeze(0).unsqueeze(0)
    tmpl = template.unsqueeze(0).unsqueeze(0)
    n = th * tw
    t_mean = template.mean()
    t0 = tmpl - t_mean
    t_sq_sum = (t0 ** 2).sum()
    ones = torch.ones((1, 1, th, tw), dtype=image.dtype)
    local_sum = F.conv2d(img, ones)
    local_sq_sum = F.conv2d(img ** 2, ones)
    cross = F.conv2d(img, tmpl) - t_mean * local_sum
    var_i = local_sq_sum - (local_sum ** 2) / n
    var_i = torch.clamp(var_i, min=0.0)
    denom = torch.sqrt(var_i) * torch.sqrt(t_sq_sum)
    ncc = torch.where(denom > 1e-6, cross / denom, torch.full_like(cross, -1.0))
    return ncc[0, 0]


def condition_N(ref_path, target_path, ref_box_norm, pad_top_left_side):
    """returns (pred_box_norm, meta). ref_box_norm: R padding canvas [y0,x0,y1,x1] (0-1000).

    ref_path/target_path는 이미 padding된 정사각 PNG이므로, 좌표는 padded 이미지 pixel 공간에서
    직접 다뤄야 한다 (geometry.norm_to_canvas/canvas_to_norm은 padding을 빼거나 더해 '원본'(비padded)
    pixel 공간으로 변환하므로 여기서 쓰면 top/left만큼 어긋난다: norm_to_padded/padded_to_norm 사용)."""
    top, left, side = pad_top_left_side
    ref_img = torch.from_numpy(_gray_padded(ref_path))
    tgt_img = torch.from_numpy(_gray_padded(target_path))
    x0, y0, x1, y1 = geometry.norm_to_padded(ref_box_norm, side)
    x0i, y0i, x1i, y1i = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    x0i, y0i = max(0, x0i), max(0, y0i)
    x1i, y1i = max(x0i + 1, min(ref_img.shape[1], x1i)), max(y0i + 1, min(ref_img.shape[0], y1i))
    patch = ref_img[y0i:y1i, x0i:x1i]
    ph, pw = patch.shape
    if ph < 2 or pw < 2:
        return None, {"status": "template_too_small", "patch_hw": [ph, pw]}
    if float(patch.std()) < 1e-6:
        return None, {"status": "constant_template", "patch_hw": [ph, pw]}
    best = None
    for scale in SCALES:
        th, tw = max(1, round(ph * scale)), max(1, round(pw * scale))
        tmpl = F.interpolate(patch.unsqueeze(0).unsqueeze(0), size=(th, tw), mode="bilinear", align_corners=False)[0, 0]
        ncc = _ncc_map(tgt_img, tmpl)
        if ncc is None:
            continue
        flat = ncc.flatten()
        max_val = float(flat.max())
        # 동점: scale 1에 가까운 순서 -> 좌상단(row,col) 오름차순 (여기서는 scale 루프 순서가 이미 (0.75,1.0,1.25)이므로
        # scale-거리 비교는 best 갱신 시 명시적으로 수행한다)
        idxs = (ncc == max_val).nonzero(as_tuple=False)
        idxs = sorted(idxs.tolist())  # (row,col) 오름차순
        r0, c0 = idxs[0]
        cand = {"scale": scale, "ncc": max_val, "row0": int(r0), "col0": int(c0), "th": th, "tw": tw}
        if best is None:
            best = cand
        else:
            if cand["ncc"] > best["ncc"] + 1e-9:
                best = cand
            elif abs(cand["ncc"] - best["ncc"]) <= 1e-9:
                if abs(cand["scale"] - 1.0) < abs(best["scale"] - 1.0) - 1e-12:
                    best = cand
                elif abs(cand["scale"] - 1.0) == abs(best["scale"] - 1.0) and (cand["row0"], cand["col0"]) < (best["row0"], best["col0"]):
                    best = cand
    if best is None:
        return None, {"status": "no_valid_scale"}
    x0p, y0p = best["col0"], best["row0"]
    x1p, y1p = x0p + best["tw"], y0p + best["th"]
    box_norm = geometry.padded_to_norm([x0p, y0p, x1p, y1p], side)
    return box_norm, {"status": "ok", **best}
