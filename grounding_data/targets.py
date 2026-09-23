"""Occupancy target과 pooling 교환법칙 검증 (CPU, float64).

- fine target (64x64): 각 cell에서 annotation이 차지하는 면적 비율. 좌표는 canvas 크기로 정규화한
  [0,1]^2에서 계산하므로 MedGemma processor의 비정방형→896x896 resize(종횡비 비보존)와 같은 좌표계다.
- coarse target (16x16): fine target의 4x4 평균 (MedGemma projector의 AvgPool2d(4)와 같은 격자).
- bbox(NIH)와 수동 mask(SCR)는 서로 다른 annotation 유형이며 같은 함수로 합치지 않는다.
"""
import numpy as np

FINE = 64
COARSE = 16
POOL = FINE // COARSE


def _edges(n):
    return np.linspace(0.0, 1.0, n + 1)


def bbox_union_occupancy(boxes_xyxy, W, H, n=FINE):
    """축 정렬 box union의 cell별 정확한 면적 비율 (좌표 압축, 연속 좌표).

    box 좌표는 canvas 범위 안이어야 한다. 범위 밖이면 clipping하지 않고 ValueError를 낸다.
    """
    xs_all, ys_all, rects = [], [], []
    for x0, y0, x1, y1 in boxes_xyxy:
        if not (0 <= x0 < x1 <= W and 0 <= y0 < y1 <= H):
            raise ValueError(f"box outside canvas or degenerate: {(x0, y0, x1, y1)} canvas {(W, H)}")
        r = (x0 / W, y0 / H, x1 / W, y1 / H)
        rects.append(r)
        xs_all += [r[0], r[2]]
        ys_all += [r[1], r[3]]
    ge = _edges(n)
    xs = np.unique(np.concatenate([ge, xs_all]))
    ys = np.unique(np.concatenate([ge, ys_all]))
    cov = np.zeros((len(ys) - 1, len(xs) - 1), dtype=bool)
    for x0, y0, x1, y1 in rects:
        i0, i1 = np.searchsorted(xs, x0), np.searchsorted(xs, x1)
        j0, j1 = np.searchsorted(ys, y0), np.searchsorted(ys, y1)
        cov[j0:j1, i0:i1] = True
    dx, dy = np.diff(xs), np.diff(ys)
    area = cov * np.outer(dy, dx)
    # 압축 구간 → 목표 cell 번호 (구간 중심 기준)
    cx = np.minimum((((xs[:-1] + xs[1:]) / 2) * n).astype(int), n - 1)
    cy = np.minimum((((ys[:-1] + ys[1:]) / 2) * n).astype(int), n - 1)
    out = np.zeros((n, n))
    np.add.at(out, (cy[:, None].repeat(len(cx), 1), cx[None, :].repeat(len(cy), 0)), area)
    return out * (n * n)  # cell 면적 1/n^2로 나눔


def _overlap_matrix(npix, n):
    """pixel k=[k,k+1)/npix 와 cell c=[c,c+1)/n 의 겹치는 길이 (정규화 좌표)."""
    pe = np.arange(npix + 1) / npix
    ce = _edges(n)
    lo = np.maximum(ce[:-1, None], pe[None, :-1])
    hi = np.minimum(ce[1:, None], pe[None, 1:])
    return np.clip(hi - lo, 0, None)  # (n, npix)


def mask_occupancy(mask, n=FINE):
    """pixel mask(각 pixel = 단위 정사각형)의 cell별 정확한 면적 비율."""
    m = np.asarray(mask, dtype=np.float64)
    H, W = m.shape
    Ay, Ax = _overlap_matrix(H, n), _overlap_matrix(W, n)
    return (Ay @ m @ Ax.T) * (n * n)


def coarse_from_fine(t, pool=POOL):
    n = t.shape[0]
    return t.reshape(n // pool, pool, n // pool, pool).mean(axis=(1, 3))


def avgpool_features(Z, pool=POOL):
    """Z: (n, n, C) → (n/pool, n/pool, C). MedGemma projector의 AvgPool2d(kernel=stride=pool)와 같은 연산."""
    n, _, C = Z.shape
    return Z.reshape(n // pool, pool, n // pool, pool, C).mean(axis=(1, 3))


def upsample_nearest(Zc, pool=POOL):
    return np.repeat(np.repeat(Zc, pool, axis=0), pool, axis=1)


def affine_head(Z, Wt, b):
    return Z @ Wt + b
