"""iter_068: iter_067 SPIDER D/E12 저장 점수의 한정 재분석(신규 추론 없음, CPU).
p(C) 순위(AUROC) 교란 점검, D 고정 threshold 보정의 E12 평가. 사후 분석이며 독립 확인이 아니다.
사용: python sp68_analysis.py --out-dir results/iter_068/analysis [--nb 10000]
설정은 실행 전 config.json으로 저장하고 기존 출력 파일은 덮어쓰지 않는다."""
import argparse, glob, hashlib, json, math, os, sys, time
import numpy as np

SRC = 'results/iter_067'
OPT = ['A', 'B', 'C', 'D']
MODELS = ('medgemma', 'qwen')
SEED = 68
NB = 10000
CLIP = 1e-8
RIDGE = 1.0
ORD = list(range(1, 10))
COND_ALL = ['S1', 'S2', 'J', 'RT1', 'T']      # 보조 포함(LF는 파생)
CFG = {
    'score': 'softmax over 4 candidates, p(C)=cand_probs[2]; high => II',
    'primary_cond': 'S1 (D 선택 B=t1)', 'aux_conds': ['S2', 'J', 'RT1', 'LF', 'T'],
    'auc_ties': 0.5, 'bootstrap': {'n': NB, 'seed': SEED, 'unit': 'patient (all rows resampled together)'},
    'nested_bootstrap': {'n': NB, 'seed': SEED + 1, 'desc': 'D and E patients resampled independently, D threshold refit'},
    'regression': {'target': 'logit(p(C)) clip 1e-8', 'features': 'ordinal one-hot 1..9 + standardized n1,n2 (D mean/std; std0->0)',
                   'ridge_lambda': RIDGE, 'loss': 'MSE + lambda*sum(coef^2), intercept unpenalized', 'fit_on': 'D all rows, per condition'},
    'threshold_rule': 'D 0/II rows, maximise BA, candidates = midpoints of distinct D scores + +-inf; tie -> largest threshold; pred II iff p>=thr',
    'prevalence': '(nII+1)/(n+2) per ordinal on D, unobserved ordinal -> global; threshold by same D rule',
    'decision': {'auc_all>=': 0.70, 'auc_resid>=': 0.70, 'auc_resid_ci_low>': 0.5, 'within_patient>': 0.5, 'same_ordinal>': 0.5,
                 'BA>=': 0.65, 'recall>=': 0.60, 'margin_vs_prior_and_T': 0.05},
    'note': 'post-hoc development analysis after seeing E12 p(C) AUROC; not preregistered, not independent confirmation',
}


# ---------- 입력 로딩/검증 ----------
def sha_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for ch in iter(lambda: f.read(1 << 22), b''):
            h.update(ch)
    return h.hexdigest()


def sha_s(x):
    return hashlib.sha256(x.encode()).hexdigest()


def read_jsonl_strict(p):
    raw = open(p, 'rb').read()
    if raw and not raw.endswith(b'\n'):
        raise SystemExit(f'torn tail: {p}')
    out = []
    for i, l in enumerate(raw.split(b'\n')[:-1]):
        try:
            out.append(json.loads(l))
        except Exception as e:
            raise SystemExit(f'corrupt line {i} in {p}: {e}')
    return out


def check_inputs(split, protocol, requests, labels):
    """protocol의 requests/labels hash를 현재 파일과 대조하고 protocol digest 반환. code hash 일치는 정보로만 기록."""
    old = json.load(open(protocol))
    if old['requests'] != sha_file(requests):
        raise SystemExit(f'{split}: requests hash mismatch vs protocol')
    if old['labels'] != sha_file(labels):
        raise SystemExit(f'{split}: labels hash mismatch vs protocol')
    code_ok = {f: (sha_file(f) == h) for f, h in old['code'].items() if os.path.exists(f)}
    return sha_s(json.dumps(old, sort_keys=True)), code_ok


def truth_map(labels):
    t = {}
    for p in json.load(open(labels)):
        for i in p['ivd']:
            k = (p['patient'], int(i['k']))
            if k in t:
                raise SystemExit(f'duplicate truth {k}')
            t[k] = int(i['modic'])
    return t


def load_recs(gen_root, model, rows, pdig):
    want = {r['rid']: r for r in rows}
    if len(want) != len(rows):
        raise SystemExit('duplicate rid in requests')
    got = {}
    files = sorted(glob.glob(f'{gen_root}/{model}/worker*.jsonl'))
    if not files:
        raise SystemExit(f'no outputs {gen_root}/{model}')
    for f in files:
        for r in read_jsonl_strict(f):
            if r['rid'] in got:
                raise SystemExit(f"duplicate output {r['rid']}")
            if r['protocol_digest'] != pdig:
                raise SystemExit(f"protocol digest mismatch {r['rid']}")
            got[r['rid']] = r
    if set(got) - set(want):
        raise SystemExit('unexpected rids')
    if set(want) - set(got):
        raise SystemExit(f'missing {len(set(want) - set(got))} rids')
    for rid, q in want.items():
        g = got[rid]
        if (g['patient'], g['ivd'], g['cond'], g['n_images']) != (q['patient'], q['ivd'], q['cond'], len(q['images'])):
            raise SystemExit(f'record/request mismatch {rid}')
        lg = np.array(g['cand_logits'], float); pr = np.array(g['cand_probs'], float)
        if lg.shape != (4,) or pr.shape != (4,) or not np.isfinite(lg).all() or not np.isfinite(pr).all():
            raise SystemExit(f'bad logits/probs {rid}')
        if abs(pr.sum() - 1) > 1e-5:
            raise SystemExit(f'probs not summing to 1 {rid}')
        e = np.exp(lg - lg.max()); e /= e.sum()
        if np.abs(e - pr).max() > 1e-5:
            raise SystemExit(f'probs != softmax(logits) {rid}')
    return got


class Table:
    def __init__(self, recs, truth, conds):
        keys = sorted({(r['patient'], r['ivd']) for r in recs.values()}, key=lambda t: (int(t[0]), t[1]))
        if set(keys) != set(truth):
            raise SystemExit('truth/record key mismatch')
        self.keys = keys
        self.pat = np.array([k[0] for k in keys]); self.k = np.array([k[1] for k in keys])
        self.y = np.array([truth[k] for k in keys])
        if not set(np.unique(self.y)) <= {0, 2}:
            raise SystemExit('non 0/II truth present')
        self.pids = sorted(set(self.pat), key=int)
        self.pidx = np.array([self.pids.index(p) for p in self.pat])
        self.probs = {}
        sp = next(iter(recs)).split('|')[0]
        for c in conds:
            self.probs[c] = np.array([recs[f'{sp}|{p}|{k}|{c}']['cand_probs'] for p, k in keys])
        self.n1 = np.array([recs[f'{sp}|{p}|{k}|S1']['n_images'] for p, k in keys], float)
        self.n2 = np.array([recs[f'{sp}|{p}|{k}|S2']['n_images'] for p, k in keys], float)
        if 'S1' in conds and 'S2' in conds:
            self.probs['LF'] = 0.5 * (self.probs['S1'] + self.probs['S2'])

    def pc(self, c):
        return self.probs[c][:, 2]


def logit(p):
    p = np.clip(p, CLIP, 1 - CLIP)
    return np.log(p / (1 - p))


# ---------- 통계 ----------
def auc_matrix(s, y):
    """pos(II) x neg(0) 쌍 점수: 1 / 0.5 / 0."""
    sp, sn = s[y == 2], s[y == 0]
    d = sp[:, None] - sn[None, :]
    return (d > 0) + 0.5 * (d == 0)


def auroc(s, y):
    if (y == 2).sum() == 0 or (y == 0).sum() == 0:
        return float('nan')
    return float(auc_matrix(s, y).mean())


def row_weights(W, pidx):
    return W[:, pidx]


def boot_auc(s, y, W, pidx, mask_fn=None):
    """환자 cluster bootstrap AUROC. W: [nb, n_patients] 환자 복제 횟수. mask_fn(pos_idx,neg_idx)->pair mask [npos,nneg]."""
    M = auc_matrix(s, y)
    ip, in_ = np.where(y == 2)[0], np.where(y == 0)[0]
    if mask_fn is not None:
        mk = mask_fn(ip, in_).astype(float)
    else:
        mk = np.ones_like(M)
    RW = row_weights(W, pidx)
    wp, wn = RW[:, ip], RW[:, in_]
    num = ((wp @ (M * mk)) * wn).sum(1)
    den = ((wp @ mk) * wn).sum(1)
    v = np.full(len(W), np.nan)
    ok = den > 0
    v[ok] = num[ok] / den[ok]
    return v


def pct_ci(v):
    u = v[~np.isnan(v)]
    if len(u) == 0:
        return None, 0
    return [float(np.percentile(u, 2.5)), float(np.percentile(u, 97.5))], int(len(u))


def boot_weights(n, nb, seed):
    rng = np.random.RandomState(seed)
    idx = rng.randint(0, n, size=(nb, n))
    W = np.zeros((nb, n))
    for b in range(nb):
        W[b] = np.bincount(idx[b], minlength=n)
    return W


def within_patient_auc(s, y, pidx):
    vals, contrib = {}, []
    for i in sorted(set(pidx)):
        m = pidx == i
        a = auroc(s[m], y[m])
        vals[int(i)] = a
        if not math.isnan(a):
            contrib.append((int(i), int((y[m] == 2).sum() * (y[m] == 0).sum())))
    ok = [a for a in vals.values() if not math.isnan(a)]
    return {'mean_equal_weight': float(np.mean(ok)) if ok else None, 'n_patients_used': len(ok), 'n_pairs': int(sum(c for _, c in contrib)),
            'per_patient': vals}


def same_ordinal_auc(s, y, k, pat):
    ip, in_ = np.where(y == 2)[0], np.where(y == 0)[0]
    M = auc_matrix(s, y)
    mk = (k[ip][:, None] == k[in_][None, :]) & (pat[ip][:, None] != pat[in_][None, :])
    n = int(mk.sum())
    ords = sorted({int(k[i]) for a, i in enumerate(ip) for b, j in enumerate(in_) if mk[a, b]})
    val = float((M * mk).sum() / n) if n else None
    return val, {'n_pairs': n, 'ordinals': ords}


def lopo_auc(s, y, pidx):
    out = {}
    for i in sorted(set(pidx)):
        m = pidx != i
        out[int(i)] = auroc(s[m], y[m])
    ok = [v for v in out.values() if not math.isnan(v)]
    return {'min': float(min(ok)), 'max': float(max(ok)), 'per_left_out': out}


# ---------- threshold / prior ----------
def fit_threshold(score, y, w=None):
    """BA 최대 threshold(pred II iff score>=thr). 후보=서로 다른 점수 사이 중점, +-inf. 동률은 가장 큰 threshold. w: 행 가중."""
    w = np.ones(len(y)) if w is None else w
    pos, neg = w * (y == 2), w * (y == 0)
    P, N = pos.sum(), neg.sum()
    if P == 0 or N == 0:
        return float('nan')
    u = np.unique(score[w > 0])
    cands = [-np.inf] + list((u[:-1] + u[1:]) / 2) + [np.inf]
    best, bt = -1, None
    for t in cands:
        pr = score >= t
        ba = 0.5 * ((pos * pr).sum() / P + (neg * ~pr).sum() / N)
        if ba > best + 1e-12 or abs(ba - best) <= 1e-12:
            best, bt = ba, t     # 후보가 오름차순이므로 동률이면 더 큰 값으로 갱신
    return float(bt)


def apply_thr(score, t):
    return score >= t


def counts(y, pred):
    n0, n2 = int((y == 0).sum()), int((y == 2).sum())
    c0 = int(((y == 0) & ~pred).sum()); c2 = int(((y == 2) & pred).sum())
    return n0, c0, n2, c2


def ba_rec(y, pred):
    n0, c0, n2, c2 = counts(y, pred)
    if n0 == 0 or n2 == 0:
        return float('nan'), float('nan'), float('nan')
    r0, r2 = c0 / n0, c2 / n2
    return 0.5 * (r0 + r2), r0, r2


def prevalence_scores(dk, dy, ek, w=None):
    """D 기반 global/ordinal II prevalence(+1 smoothing). 반환: (D행 점수 global, D행 ordinal, E행 global, E행 ordinal)."""
    w = np.ones(len(dy)) if w is None else w
    n = (w).sum(); n2 = (w * (dy == 2)).sum()
    g = (n2 + 1) / (n + 2)
    tab = {}
    for k in np.unique(dk):
        m = dk == k
        tab[int(k)] = ((w[m] * (dy[m] == 2)).sum() + 1) / (w[m].sum() + 2) if w[m].sum() > 0 else g
    ord_d = np.array([tab[int(k)] for k in dk]); ord_e = np.array([tab.get(int(k), g) for k in ek])
    return np.full(len(dk), g), ord_d, np.full(len(ek), g), ord_e


# ---------- 회귀 ----------
def design(tab, mu, sd):
    X = np.zeros((len(tab.y), len(ORD) + 2))
    for i, k in enumerate(tab.k):
        if int(k) in ORD:
            X[i, ORD.index(int(k))] = 1
    for j, v in enumerate((tab.n1, tab.n2)):
        X[:, len(ORD) + j] = 0 if sd[j] == 0 else (v - mu[j]) / sd[j]
    return X


def fit_ridge(D, s):
    mu = [float(D.n1.mean()), float(D.n2.mean())]
    sd = [float(D.n1.std()), float(D.n2.std())]
    X = design(D, mu, sd)
    Xc, sc = X - X.mean(0), s - s.mean()
    n = len(s)
    b = np.linalg.solve(Xc.T @ Xc / n + RIDGE * np.eye(X.shape[1]), Xc.T @ sc / n)
    c = s.mean() - X.mean(0) @ b
    return {'mu': mu, 'sd': sd, 'b': b, 'c': float(c)}


def predict_ridge(fit, tab):
    return design(tab, fit['mu'], fit['sd']) @ fit['b'] + fit['c']


# ---------- 모델별 분석 ----------
def analyze(model, D, E, W, nb):
    res = {'D': {'n_patients': len(D.pids), 'n_ivd': len(D.y), 'II_rows': int((D.y == 2).sum()),
                 'II_rows_per_patient': {p: int(((D.pat == p) & (D.y == 2)).sum()) for p in D.pids},
                 'ivd_per_patient': {p: int((D.pat == p).sum()) for p in D.pids}},
           'E12': {'n_patients': len(E.pids), 'n_ivd': len(E.y), 'II_rows': int((E.y == 2).sum()), 'zero_rows': int((E.y == 0).sum())}}
    # D 선택 재계산 + 원 BA02 argmax 재현
    def ba_argmax(T, c):
        pred = T.probs[c].argmax(1)
        r0 = ((T.y == 0) & (pred == 0)).sum() / (T.y == 0).sum(); r2 = ((T.y == 2) & (pred == 2)).sum() / (T.y == 2).sum()
        return float(0.5 * (r0 + r2))
    res['orig_BA02_argmax'] = {'D': {c: ba_argmax(D, c) for c in ['S1', 'S2', 'J', 'LF', 'T']},
                               'E12': {c: ba_argmax(E, c) for c in ['S1', 'S2', 'J', 'LF', 'T']}}
    res['D_selected_B'] = 't1' if res['orig_BA02_argmax']['D']['S1'] >= res['orig_BA02_argmax']['D']['S2'] else 't2'
    # 순위 분석
    conds = ['S1', 'S2', 'J', 'RT1', 'LF', 'T']
    rank = {}
    for c in conds:
        s = E.pc(c)
        auc = auroc(s, E.y)
        ci, nv = pct_ci(boot_auc(s, E.y, W, E.pidx))
        wp = within_patient_auc(s, E.y, E.pidx)
        so, so_info = same_ordinal_auc(s, E.y, E.k, E.pat)
        # 같은 ordinal 대조 bootstrap
        def mk(ip, in_, E=E):
            return (E.k[ip][:, None] == E.k[in_][None, :]) & (E.pat[ip][:, None] != E.pat[in_][None, :])
        so_ci, so_nv = pct_ci(boot_auc(s, E.y, W, E.pidx, mk))
        rank[c] = {'auc_all': auc, 'auc_all_ci95': ci, 'boot_valid': nv, 'within_patient': {k: v for k, v in wp.items() if k != 'per_patient'},
                   'within_patient_per_patient': wp['per_patient'], 'same_ordinal_diffpatient': so, 'same_ordinal_info': so_info,
                   'same_ordinal_ci95': so_ci, 'same_ordinal_boot_valid': so_nv, 'lopo_auc': lopo_auc(s, E.y, E.pidx)}
    res['rank'] = rank
    # 영상 수·ordinal 대조(S1 주, J 보조): D에서만 적합, E12 적용
    d_ords = set(int(k) for k in D.k)
    sup = np.array([(int(k) in d_ords) and (D.n1.min() <= a <= D.n1.max()) and (D.n2.min() <= b <= D.n2.max()) for k, a, b in zip(E.k, E.n1, E.n2)])
    res['support'] = {'D_ordinals': sorted(d_ords), 'D_n1_range': [float(D.n1.min()), float(D.n1.max())], 'D_n2_range': [float(D.n2.min()), float(D.n2.max())],
                      'E_rows_in_support': int(sup.sum()), 'E_rows_outside': int((~sup).sum()),
                      'E_outside_ordinals': sorted({int(k) for k in E.k[~sup]})}
    ctrl = {}
    for c in ('S1', 'J', 'S2', 'LF'):
        fit = fit_ridge(D, logit(D.pc(c)))
        nuis = predict_ridge(fit, E)
        s = logit(E.pc(c)); resid = s - nuis
        out = {'coef_ordinal': {int(o): float(fit['b'][i]) for i, o in enumerate(ORD)}, 'coef_n1_n2_std': [float(fit['b'][-2]), float(fit['b'][-1])], 'intercept': fit['c'],
               'D_mean_std': {'mu': fit['mu'], 'sd': fit['sd']}}
        for name, v in (('raw', s), ('resid', resid), ('nuisance', nuis)):
            ci, nv = pct_ci(boot_auc(v, E.y, W, E.pidx))
            out[f'auc_{name}'] = auroc(v, E.y); out[f'auc_{name}_ci95'] = ci; out[f'auc_{name}_boot_valid'] = nv
        # 지지 범위 내 민감도
        if (E.y[sup] == 2).any() and (E.y[sup] == 0).any():
            ps = np.unique(E.pidx[sup])
            Wsub = W
            msk = sup
            out['support_only'] = {'rows': int(sup.sum()), 'n_II': int((E.y[sup] == 2).sum()), 'n_0': int((E.y[sup] == 0).sum()),
                                   'auc_raw': auroc(s[msk], E.y[msk]), 'auc_resid': auroc(resid[msk], E.y[msk]), 'auc_nuisance': auroc(nuis[msk], E.y[msk])}
            # bootstrap: 지지 밖 행은 가중치 0
            for name, v in (('raw', s), ('resid', resid)):
                RW = W[:, E.pidx] * msk
                M = auc_matrix(v[msk], E.y[msk]); ip, in_ = np.where(E.y[msk] == 2)[0], np.where(E.y[msk] == 0)[0]
                RWm = RW[:, msk]
                num = ((RWm[:, ip] @ M) * RWm[:, in_]).sum(1); den = RWm[:, ip].sum(1) * RWm[:, in_].sum(1)
                bv = np.full(len(W), np.nan); ok = den > 0; bv[ok] = num[ok] / den[ok]
                out['support_only'][f'auc_{name}_ci95'], out['support_only'][f'auc_{name}_boot_valid'] = pct_ci(bv)
        else:
            out['support_only'] = {'rows': int(sup.sum()), 'note': 'one class vanished; control sufficiency not claimable'}
        ctrl[c] = out
    res['control'] = ctrl
    # D 고정 threshold 보정
    thr = {}
    sS1, sT = D.pc('S1'), D.pc('T')
    pg_d, po_d, pg_e, po_e = prevalence_scores(D.k, D.y, E.k)
    systems = {'S1': (sS1, E.pc('S1')), 'T': (sT, E.pc('T')), 'prior_global': (pg_d, pg_e), 'prior_ordinal': (po_d, po_e)}
    preds, tinfo = {}, {}
    for n, (sd_, se_) in systems.items():
        t = fit_threshold(sd_, D.y)
        preds[n] = apply_thr(se_, t)
        ba_d = ba_rec(D.y, apply_thr(sd_, t))[0]
        ba, r0, r2 = ba_rec(E.y, preds[n])
        tinfo[n] = {'threshold': (t if np.isfinite(t) else str(t)), 'D_BA': ba_d, 'E12_BA': ba, 'recall0': r0, 'recall2': r2,
                    'confusion_[[0->0,0->II],[II->0,II->II]]': [[int(((E.y == 0) & ~preds[n]).sum()), int(((E.y == 0) & preds[n]).sum())],
                                                                [int(((E.y == 2) & ~preds[n]).sum()), int(((E.y == 2) & preds[n]).sum())]]}
    res['threshold'] = tinfo
    # paired BA 차이(환자 bootstrap, 고정 threshold)
    def pat_counts(pred):
        return np.array([counts(E.y[E.pidx == i], pred[E.pidx == i]) for i in range(len(E.pids))], float)
    cn = {n: pat_counts(p) for n, p in preds.items()}

    def bb(cnt):
        s_ = W @ cnt; ok = (s_[:, 0] > 0) & (s_[:, 2] > 0); v = np.full(len(W), np.nan)
        v[ok] = 0.5 * (s_[ok, 1] / s_[ok, 0] + s_[ok, 3] / s_[ok, 2]); return v
    pair = {}
    bs = {n: bb(c) for n, c in cn.items()}
    for n in ('S1', 'T', 'prior_global', 'prior_ordinal'):
        ci, nv = pct_ci(bs[n]); tinfo[n]['E12_BA_ci95'] = ci; tinfo[n]['boot_valid'] = nv
    for b in ('T', 'prior_global', 'prior_ordinal'):
        d = bs['S1'] - bs[b]
        ci, nv = pct_ci(d)
        pair[f'S1-{b}'] = {'point': tinfo['S1']['E12_BA'] - tinfo[b]['E12_BA'], 'ci95': ci, 'boot_valid': nv}
    res['threshold_paired'] = pair
    # D threshold 안정성: D 환자 leave-one-out
    lo = {}
    for i, p in enumerate(D.pids):
        m = D.pat != p
        t = fit_threshold(sS1[m], D.y[m])
        pr = apply_thr(E.pc('S1'), t)
        lo[p] = {'threshold': (t if np.isfinite(t) else str(t)), 'frac_E12_pred_changed': float((pr != preds['S1']).mean()), 'E12_BA': ba_rec(E.y, pr)[0]}
    fin = [v['E12_BA'] for v in lo.values() if not math.isnan(v['E12_BA'])]
    res['threshold_D_lopo'] = {'per_left_out_D_patient': lo, 'E12_BA_range': [float(min(fin)), float(max(fin))] if fin else None,
                               'max_frac_changed': float(max(v['frac_E12_pred_changed'] for v in lo.values()))}
    # nested bootstrap: D, E 환자 독립 재표집, D threshold 재적합
    rng = np.random.RandomState(SEED + 1)
    nD, nE = len(D.pids), len(E.pids)
    out_b = {n: np.full(nb, np.nan) for n in ('S1', 'T', 'prior_global', 'prior_ordinal', 'S1-T', 'S1-prior_ordinal', 'S1-prior_global')}
    lost = 0
    t0 = time.time()
    for b in range(nb):
        dw = np.bincount(rng.randint(0, nD, nD), minlength=nD).astype(float)
        ew = np.bincount(rng.randint(0, nE, nE), minlength=nE).astype(float)
        wr_d = dw[D.pidx]; wr_e = ew[E.pidx]
        if (wr_d * (D.y == 2)).sum() == 0 or (wr_d * (D.y == 0)).sum() == 0 or (wr_e * (E.y == 2)).sum() == 0 or (wr_e * (E.y == 0)).sum() == 0:
            lost += 1; continue
        gd, od, ge, oe = prevalence_scores(D.k, D.y, E.k, wr_d)
        sysb = {'S1': (sS1, E.pc('S1')), 'T': (sT, E.pc('T')), 'prior_global': (gd, ge), 'prior_ordinal': (od, oe)}
        vals = {}
        for n, (a, e_) in sysb.items():
            t = fit_threshold(a, D.y, wr_d)
            pr = e_ >= t
            n0 = (wr_e * (E.y == 0)).sum(); n2 = (wr_e * (E.y == 2)).sum()
            vals[n] = 0.5 * ((wr_e * (E.y == 0) * ~pr).sum() / n0 + (wr_e * (E.y == 2) * pr).sum() / n2)
            out_b[n][b] = vals[n]
        out_b['S1-T'][b] = vals['S1'] - vals['T']; out_b['S1-prior_ordinal'][b] = vals['S1'] - vals['prior_ordinal']; out_b['S1-prior_global'][b] = vals['S1'] - vals['prior_global']
        if b == 99:
            res['nested_time_100_reps_s'] = time.time() - t0
    res['nested_bootstrap'] = {'n': nb, 'class_vanished_replicates': lost, 'valid': nb - lost,
                               **{n: {'ci95': pct_ci(v)[0], 'median': float(np.nanmedian(v))} for n, v in out_b.items()}}
    # 판정 지표(검토 후보 기준)
    r = rank['S1']; c = ctrl['S1']
    chk = {'auc_all>=0.70': r['auc_all'] >= 0.70, 'auc_resid>=0.70': c['auc_resid'] >= 0.70,
           'auc_resid_ci_low>0.5': bool(c['auc_resid_ci95'] and c['auc_resid_ci95'][0] > 0.5),
           'within_patient>0.5': bool(r['within_patient']['mean_equal_weight'] is not None and r['within_patient']['mean_equal_weight'] > 0.5),
           'same_ordinal>0.5': bool(r['same_ordinal_diffpatient'] is not None and r['same_ordinal_diffpatient'] > 0.5),
           'BA>=0.65': tinfo['S1']['E12_BA'] >= 0.65, 'recall0>=0.60': tinfo['S1']['recall0'] >= 0.60, 'recall2>=0.60': tinfo['S1']['recall2'] >= 0.60}
    for b in ('prior_global', 'prior_ordinal', 'T'):
        chk[f'S1-{b}>=0.05'] = pair[f'S1-{b}']['point'] >= 0.05
    chk = {k: bool(v) for k, v in chk.items()}
    control_unresolved = (r['same_ordinal_diffpatient'] is None) or ('auc_resid' not in c['support_only'] and c['support_only'].get('auc_resid') is None)
    res['criteria_S1'] = {'checks': chk, 'all_pass': bool(all(chk.values())), 'control_unresolved_NA_or_support': bool(control_unresolved)}
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out-dir', required=True); ap.add_argument('--nb', type=int, default=NB)
    a = ap.parse_args()
    if os.path.exists(f'{a.out_dir}/report.json'):
        raise SystemExit('report exists; refusing to overwrite')
    os.makedirs(a.out_dir, exist_ok=True)
    cfg = dict(CFG); cfg['bootstrap'] = dict(cfg['bootstrap'], n=a.nb); cfg['nested_bootstrap'] = dict(cfg['nested_bootstrap'], n=a.nb)
    cfgp = f'{a.out_dir}/config.json'
    if not os.path.exists(cfgp):
        json.dump(cfg, open(cfgp, 'w'), indent=1)
    d = f'{SRC}/data'
    inp = {'D': dict(protocol=f'{d}/protocol_D_v2.json', requests=f'{d}/requests_D.jsonl', labels=f'{d}/pairs_D.json', gen=f'{SRC}/gen_D'),
           'E12': dict(protocol=f'{d}/protocol_E12.json', requests=f'{d}/requests_E12.jsonl', labels=f'{d}/pairs_E12.json', gen=f'{SRC}/gen_E12')}
    manifest = {'code_sha256': sha_file(__file__), 'config_sha256': sha_file(cfgp), 'select_D_sha256': sha_file(f'{d}/select_D.json'), 'inputs': {}}
    tabs, pd_ = {}, {}
    for sp, v in inp.items():
        pdig, code_ok = check_inputs(sp, v['protocol'], v['requests'], v['labels'])
        manifest['inputs'][sp] = {**{k: sha_file(x) for k, x in v.items() if k in ('protocol', 'requests', 'labels')}, 'protocol_digest': pdig,
                                  'iter067_code_hash_unchanged': code_ok, 'raw_outputs': {}}
        rows = read_jsonl_strict(v['requests'])
        conds = sorted({r['cond'] for r in rows})
        for m in MODELS:
            recs = load_recs(v['gen'], m, rows, pdig)
            for f in sorted(glob.glob(f"{v['gen']}/{m}/worker*.jsonl")):
                manifest['inputs'][sp]['raw_outputs'][f] = sha_file(f)
            tabs[(sp, m)] = Table(recs, truth_map(v['labels']), conds)
    Dp = {p for p in tabs[('D', 'qwen')].pids}; Ep = {p for p in tabs[('E12', 'qwen')].pids}
    if Dp & Ep:
        raise SystemExit('D/E patient overlap')
    sel = json.load(open(f'{d}/select_D.json'))
    W = boot_weights(len(tabs[('E12', 'qwen')].pids), a.nb, SEED)
    out = {'manifest': manifest, 'scope': 'iter_067 stored outputs (batch1, vision chunk8), post-hoc development analysis, CPU only', 'models': {}}
    for m in MODELS:
        r = analyze(m, tabs[('D', m)], tabs[('E12', m)], W, a.nb)
        r['select_D_file_B'] = sel[m]['B']; r['select_D_reproduced'] = (sel[m]['B'] == r['D_selected_B'])
        out['models'][m] = r
        print(m, 'S1 auc', round(r['rank']['S1']['auc_all'], 3), 'resid', round(r['control']['S1']['auc_resid'], 3), 'BA', round(r['threshold']['S1']['E12_BA'], 3), r['criteria_S1']['all_pass'])
    tmp = f'{a.out_dir}/report.json.tmp.{os.getpid()}'
    json.dump(out, open(tmp, 'w'), indent=1, default=lambda x: float(x) if isinstance(x, (np.floating, np.integer)) else str(x))
    os.replace(tmp, f'{a.out_dir}/report.json')


if __name__ == '__main__':
    main()
