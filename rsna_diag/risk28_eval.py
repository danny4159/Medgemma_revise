"""iter_028 평가: AUROC, Capture@20%, Platt calibration(C에서만 적합), Brier/ECE, 환자 paired bootstrap."""
import math

import numpy as np


def auroc(scores, y):
    """동점은 0.5 기여. scores, y: 같은 순서 배열. y in {0,1}."""
    s = np.asarray(scores, float)
    yy = np.asarray(y, int)
    pos = s[yy == 1]
    neg = s[yy == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    wins = 0.0
    for p in pos:
        wins += np.sum(p > neg) + 0.5 * np.sum(p == neg)
    return float(wins / (len(pos) * len(neg)))


def capture_at_k(scores, y, frac=0.2, seed=20260929):
    """상위 frac 비율을 검토할 때 포함되는 사건(y=1) 비율. 경계 동점은 그 집단 내 무작위 검토 기대값."""
    s = np.asarray(scores, float)
    yy = np.asarray(y, int)
    n = len(s)
    k = int(round(n * frac))
    if k <= 0 or yy.sum() == 0:
        return 0.0
    order = np.argsort(-s, kind="stable")
    thresh = s[order[k - 1]]
    above = s > thresh
    tie = s == thresh
    n_take_from_tie = k - int(above.sum())
    captured = float(yy[above].sum())
    if n_take_from_tie > 0 and tie.sum() > 0:
        tie_pos_rate = yy[tie].sum() / tie.sum()
        captured += n_take_from_tie * tie_pos_rate
    return float(captured / yy.sum())


def remaining_after_review(scores, y, frac=0.2):
    s = np.asarray(scores, float)
    yy = np.asarray(y, int)
    n = len(s)
    k = int(round(n * frac))
    cap = capture_at_k(scores, y, frac)
    total_pos = int(yy.sum())
    captured_n = cap * total_pos
    return {"k_reviewed": k, "total_events": total_pos, "captured_expected": captured_n,
            "remaining_expected": total_pos - captured_n,
            "remaining_frac": (total_pos - captured_n) / total_pos if total_pos else float("nan")}


def brier(scores_prob, y):
    p = np.asarray(scores_prob, float)
    yy = np.asarray(y, float)
    return float(np.mean((p - yy) ** 2))


def ece(scores_prob, y, n_bins=10):
    p = np.asarray(scores_prob, float)
    yy = np.asarray(y, float)
    bins = np.linspace(0, 1, n_bins + 1)
    idx = np.clip(np.digitize(p, bins) - 1, 0, n_bins - 1)
    tot = 0.0
    for b in range(n_bins):
        mask = idx == b
        if mask.sum() == 0:
            continue
        conf = p[mask].mean()
        acc = yy[mask].mean()
        tot += (mask.sum() / len(p)) * abs(conf - acc)
    return float(tot)


def fit_platt(scores, y, l2_slope=0.01, iters=2000, lr=0.5):
    """양의 기울기 Platt: p = sigmoid(a*z + b), z = (score-mean)/std (C 통계만 사용). slope에만 L2, intercept 벌점 없음.
    상수 score(std==0)는 Jeffreys 보정 사건 비율의 logit을 상수 확률로 반환한다."""
    s = np.asarray(scores, float)
    yy = np.asarray(y, float)
    mean, std = float(s.mean()), float(s.std())
    if std == 0.0:
        k, n = yy.sum(), len(yy)
        p_const = (k + 0.5) / (n + 1.0)
        return {"mean": mean, "std": std, "a": 0.0, "b": math.log(p_const / (1 - p_const)), "constant": True}
    z = (s - mean) / std
    a, b = 0.0, 0.0
    n = len(z)
    for _ in range(iters):
        logit = a * z + b
        p = 1.0 / (1.0 + np.exp(-logit))
        grad_a = np.mean((p - yy) * z) + l2_slope * a
        grad_b = np.mean(p - yy)
        a -= lr * grad_a
        b -= lr * grad_b
        a = max(a, 0.0)
    return {"mean": mean, "std": std, "a": float(a), "b": float(b), "constant": False}


def apply_platt(cal, scores):
    s = np.asarray(scores, float)
    if cal.get("constant"):
        return np.full_like(s, 1.0 / (1.0 + math.exp(-cal["b"])))
    z = (s - cal["mean"]) / cal["std"]
    logit = cal["a"] * z + cal["b"]
    return 1.0 / (1.0 + np.exp(-logit))


def bootstrap_indices(n, B=10000, seed=28017):
    rng = np.random.default_rng(seed)
    return rng.integers(0, n, size=(B, n), dtype=np.int64)


def metric_ci(values_fn, n, B=10000, seed=28017, alpha_lo=2.5, alpha_hi=97.5):
    idx = bootstrap_indices(n, B, seed)
    vals = np.array([values_fn(row) for row in idx])
    point = values_fn(np.arange(n))
    return {"point": float(point), "lo": float(np.percentile(vals, alpha_lo)),
            "hi": float(np.percentile(vals, alpha_hi)), "B": B, "seed": seed}


def paired_diff_ci(a_fn, b_fn, n, B=10000, seed=28017, alpha_lo=2.5, alpha_hi=97.5):
    idx = bootstrap_indices(n, B, seed)
    a_vals = np.array([a_fn(row) for row in idx])
    b_vals = np.array([b_fn(row) for row in idx])
    d = a_vals - b_vals
    point = a_fn(np.arange(n)) - b_fn(np.arange(n))
    return {"point": float(point), "lo": float(np.percentile(d, alpha_lo)), "hi": float(np.percentile(d, alpha_hi)),
            "B": B, "seed": seed}
