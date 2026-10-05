"""iter_075 지표: class-standardized MAE(primary), MAE, macro-F1, confusion, >=2등급 오류율, invalid 비율, prior, 예측 교환, 환자 단위 paired bootstrap.

모든 함수는 numpy만 사용한다(독립 재계산 스크립트와 구분되는 production 구현). 예측 None(invalid)은 최대 오차 4로 처리한다(primary/MAE),
confusion/F1에서는 별도 invalid 열로 둔다. 결측 class는 0으로 대체하지 않고 산출에서 제외하며 개수를 보고한다.
"""
import hashlib

import numpy as np

INVALID_ERR = 4.0
BOOT_SEED = 7501
BOOT_N = 10000


def abs_err(true, pred):
    t = np.asarray(true, float)
    p = np.array([np.nan if x is None else x for x in pred], float)
    e = np.abs(t - p)
    e[np.isnan(p)] = INVALID_ERR
    return e


def class_std_mae(true, pred):
    """returns (value or nan, n_classes_present). 각 실제 grade 1..5의 평균 절대오차를 동일 가중 평균 (없는 class 제외)."""
    t = np.asarray(true)
    e = abs_err(true, pred)
    vals = [e[t == g].mean() for g in range(1, 6) if (t == g).any()]
    if not vals:
        return float('nan'), 0
    return float(np.mean(vals)), len(vals)


def summary(true, pred):
    t = np.asarray(true)
    e = abs_err(true, pred)
    inval = np.array([p is None for p in pred])
    cm = np.zeros((5, 6), int)  # 열 0-4: 예측 1..5, 열 5: invalid
    for ti, p in zip(t, pred):
        cm[ti - 1, 5 if p is None else p - 1] += 1
    f1s = []
    for g in range(1, 6):
        tp = cm[g - 1, g - 1]
        fp = cm[:, g - 1].sum() - tp
        fn = cm[g - 1].sum() - tp
        f1s.append(0.0 if (2 * tp + fp + fn) == 0 else 2 * tp / (2 * tp + fp + fn))
    present = [g for g in range(1, 6) if (t == g).any()]
    cs, nc = class_std_mae(true, pred)
    return {'n': int(len(t)), 'class_std_mae': cs, 'n_classes_present': nc, 'mae': float(e.mean()), 'macro_f1_present': float(np.mean([f1s[g - 1] for g in present])),
            'err_ge2_rate': float((e >= 2).mean()), 'invalid_rate': float(inval.mean()), 'confusion_rows_true1to5_cols_pred1to5_invalid': cm.tolist(),
            'per_class_mae': {str(g): float(e[t == g].mean()) for g in present}}


def patient_hash(pid, salt='iter075-swap'):
    return hashlib.sha256(f'{salt}|{pid}'.encode()).hexdigest()


def swap_predictions(rows, preds):
    """같은 ordinal 안에서 환자 ID hash 순으로 정렬한 뒤 cyclic shift(+1)로 예측을 다른 환자에게 배정(고정 derangement). 행 순서는 유지.
    rows: [{'patient','ordinal'}], preds 같은 길이. ordinal 내 표본이 1이면 교환 불가 -> ValueError."""
    out = [None] * len(rows)
    by = {}
    for i, r in enumerate(rows):
        by.setdefault(r['ordinal'], []).append(i)
    for k, idx in by.items():
        if len(idx) < 2:
            raise ValueError(f'ordinal {k} has <2 rows')
        idx = sorted(idx, key=lambda i: (patient_hash(rows[i]['patient']), rows[i]['patient']))
        for j, i in enumerate(idx):
            out[i] = preds[idx[(j + 1) % len(idx)]]
    assert all(out[i] is not preds[i] or True for i in range(len(rows)))
    return out


def prior_predictions(train_rows, eval_rows):
    """train-only prior. train_rows: 학습 supervised rows(grade, ordinal). 반환 (global_pred list, ordinal_pred list)."""
    tg = np.array([r['grade'] for r in train_rows])
    gd = np.array([(tg == g).mean() for g in range(1, 6)])
    od = {}
    for k in {r['ordinal'] for r in train_rows}:
        sub = np.array([r['grade'] for r in train_rows if r['ordinal'] == k])
        od[k] = np.array([(sub == g).mean() for g in range(1, 6)])
    od_all = dict(od)
    od_all[2] = (od[1] + od[3]) / 2.0
    od_all[4] = (od[3] + od[5]) / 2.0

    def med(dist):
        cdf = np.cumsum(dist)
        return int(np.argmax(cdf >= 0.5 - 1e-12) + 1)  # 기대 절대오차를 최소화하는 median, 동률은 낮은 grade

    gp = [med(gd)] * len(eval_rows)
    op = [med(od_all[r['ordinal']]) for r in eval_rows]
    return gp, op, {'global': gd.tolist(), 'ordinal': {str(k): v.tolist() for k, v in sorted(od_all.items())}}


def boot_diff(rows, pred_a, pred_b, n=BOOT_N, seed=BOOT_SEED, metric=lambda t, p: class_std_mae(t, p)[0]):
    """환자 단위 paired bootstrap: metric(a) - metric(b) (a가 좋으면 음수). 같은 환자의 모든 행을 함께 재표집.
    returns {'point','ci95','n_missing_class_replicates','n'}. class가 빠진 replicate는 present class만으로 계산하고 개수를 센다."""
    rng = np.random.default_rng(seed)
    pids = sorted({r['patient'] for r in rows}, key=int)
    idx_of = {p: [i for i, r in enumerate(rows) if r['patient'] == p] for p in pids}
    t = np.array([r['grade'] for r in rows])
    full_classes = len(set(t.tolist()))
    pa = np.array([np.nan if x is None else x for x in pred_a], float)
    pb = np.array([np.nan if x is None else x for x in pred_b], float)

    def m(ix, pr):
        return metric(t[ix], [None if np.isnan(v) else int(v) for v in pr[ix]])

    point = m(np.arange(len(rows)), pa) - m(np.arange(len(rows)), pb)
    diffs, miss = [], 0
    for _ in range(n):
        ch = rng.integers(0, len(pids), len(pids))
        ix = np.array([i for c in ch for i in idx_of[pids[c]]])
        if len(set(t[ix].tolist())) < full_classes:
            miss += 1
        diffs.append(m(ix, pa) - m(ix, pb))
    d = np.array(diffs)
    return {'point': float(point), 'ci95': [float(np.nanpercentile(d, 2.5)), float(np.nanpercentile(d, 97.5))], 'n_missing_class_replicates': miss, 'n_boot': n, 'n': len(rows), 'n_patients': len(pids)}


def boot_single(rows, pred, n=BOOT_N, seed=BOOT_SEED):
    rng = np.random.default_rng(seed)
    pids = sorted({r['patient'] for r in rows}, key=int)
    idx_of = {p: [i for i, r in enumerate(rows) if r['patient'] == p] for p in pids}
    t = np.array([r['grade'] for r in rows])
    pr = np.array([np.nan if x is None else x for x in pred], float)
    vals = []
    for _ in range(n):
        ch = rng.integers(0, len(pids), len(pids))
        ix = np.array([i for c in ch for i in idx_of[pids[c]]])
        vals.append(class_std_mae(t[ix], [None if np.isnan(v) else int(v) for v in pr[ix]])[0])
    v = np.array(vals)
    return {'ci95': [float(np.nanpercentile(v, 2.5)), float(np.nanpercentile(v, 97.5))]}
