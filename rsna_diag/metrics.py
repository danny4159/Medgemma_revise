"""bbox 평가 (iter_009). 모든 box는 [y0,x0,y1,x1] (0-1000, padding canvas)."""
import itertools
import math

import numpy as np


def area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def inter(a, b):
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def iou(a, b):
    i = inter(a, b)
    u = area(a) + area(b) - i
    return i / u if u > 0 else 0.0


def union_area(boxes):
    """겹친 면적을 한 번만 세는 직사각형 합집합 면적 (좌표 압축)."""
    boxes = [b for b in boxes if area(b) > 0]
    if not boxes:
        return 0.0
    ys = sorted({v for b in boxes for v in (b[0], b[2])})
    tot = 0.0
    for y0, y1 in zip(ys[:-1], ys[1:]):
        iv = sorted((b[1], b[3]) for b in boxes if b[0] <= y0 and b[2] >= y1)
        cur_s = cur_e = None
        length = 0.0
        for s, e in iv:
            if cur_e is None or s > cur_e:
                if cur_e is not None:
                    length += cur_e - cur_s
                cur_s, cur_e = s, e
            else:
                cur_e = max(cur_e, e)
        if cur_e is not None:
            length += cur_e - cur_s
        tot += length * (y1 - y0)
    return tot


def union_iou(pred, gt):
    if not pred and not gt:
        return 0.0
    up, ug = union_area(pred), union_area(gt)
    # 교집합 면적 = up + ug - union(all)
    ia = up + ug - union_area(list(pred) + list(gt))
    u = up + ug - ia
    return ia / u if u > 0 else 0.0


def match(pred, gt, thr):
    """threshold thr 이상 IoU 쌍의 최대 cardinality one-to-one matching.
    동률은 총 IoU 최대, 이후 (gt index 순의) pred index tuple 사전순 최소. returns list[(gi, pi)]."""
    mat = [[iou(p, g) for p in pred] for g in gt]
    best = {"key": None, "pairs": []}

    def rec(gi, used, pairs, tot):
        if gi == len(gt):
            key = (len(pairs), tot)
            cur = best["key"]
            if cur is None or key[0] > cur[0] or (key[0] == cur[0] and key[1] > cur[1] + 1e-12):
                best["key"], best["pairs"] = key, list(pairs)
            return
        # 사전순 최소 tie-break: pred index 오름차순으로 탐색하고 엄격히 더 좋을 때만 갱신 (none 분기는 마지막)
        for pi in range(len(pred)):
            if pi not in used and mat[gi][pi] >= thr:
                pairs.append((gi, pi))
                rec(gi + 1, used | {pi}, pairs, tot + mat[gi][pi])
                pairs.pop()
        rec(gi + 1, used, pairs, tot)

    rec(0, frozenset(), [], 0.0)
    return best["pairs"]


def patient_metrics(pred, gt, thr):
    pairs = match(pred, gt, thr)
    tp = len(pairs)
    prec = tp / len(pred) if pred else 0.0
    rec = tp / len(gt) if gt else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec > 0 else 0.0
    return {"tp": tp, "n_pred": len(pred), "n_gt": len(gt), "precision": prec, "recall": rec, "f1": f1,
            "unmatched_gt": len(gt) - tp, "unmatched_pred": len(pred) - tp}


def max_iou_all(pred, gt):
    return max((iou(p, g) for p in pred for g in gt), default=0.0)


def wilson(k, n, z=1.959964):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def bootstrap_indices(n, B=10000, seed=20260924):
    rng = np.random.default_rng(seed)
    return rng.integers(0, n, size=(B, n), dtype=np.int32)


def paired_boot_ci(a, b, idx):
    """a,b: 같은 환자 순서의 값. 차이 a-b 평균의 percentile 95% CI. returns (mean_diff, lo, hi)."""
    d = np.asarray(a, float) - np.asarray(b, float)
    m = d[idx].mean(axis=1)
    return float(d.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def derangement(n, seed):
    """Sattolo: 고정점이 없는 순열 (단일 순환)."""
    rng = np.random.default_rng(seed)
    p = list(range(n))
    for i in range(n - 1, 0, -1):
        j = int(rng.integers(0, i))
        p[i], p[j] = p[j], p[i]
    assert all(p[i] != i for i in range(n))
    return p


def medoid_box(dev_gt_boxes_per_image):
    """dev 양성 GT box 후보 중 (영상별 best IoU)의 평균이 최대인 실제 box. 동률은 입력 순서(고정 ID 순)."""
    cands = [b for boxes in dev_gt_boxes_per_image for b in boxes]
    best, best_s = None, -1.0
    for c in cands:
        s = float(np.mean([max(iou(c, g) for g in boxes) for boxes in dev_gt_boxes_per_image]))
        if s > best_s + 1e-12:
            best, best_s = c, s
    return best, best_s
