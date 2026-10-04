"""iter_067 평가: BA02(0/II 행 class recall 평균), 4-class confusion, LF·prior·null·R, 환자 cluster paired bootstrap(10,000, seed67), E12 확대 기준/최종 결정.
사용: python sp67_eval.py --split D|E12|E --out-dir results/iter_067/eval/<tag> --requests R --labels L --protocol P --gen-root GEN [--dsel results/iter_067/eval/D/select.json]
평가 시작 시 protocol(code·requests·labels) 재검증, 요청 집합 일치·중복 0·protocol digest 일치를 강제한다."""
import argparse, glob, json, os, sys
import numpy as np
import m65_run as M65
import sp67_run as R

OPT = R.OPT
SEED = 67
NB = 10000


def load_recs(gen_root, model, requests, pdig):
    rows = M65.read_jsonl(requests)
    want = {r['rid'] for r in rows}
    got = {}
    for f in sorted(glob.glob(f'{gen_root}/{model}/worker*.jsonl')):
        for r in M65.read_jsonl(f):
            if r['rid'] in got:
                raise SystemExit(f"duplicate rid {r['rid']}")
            if r['protocol_digest'] != pdig:
                raise SystemExit(f"protocol digest mismatch {r['rid']}")
            got[r['rid']] = r
    if set(got) - want:
        raise SystemExit('unexpected rids')
    missing = want - set(got)
    if missing:
        raise SystemExit(f'missing {len(missing)} rids, e.g. {sorted(missing)[:3]}')
    for r in rows:   # 요청↔record 연결
        g = got[r['rid']]
        if (g['patient'], g['ivd'], g['cond'], g['n_images']) != (r['patient'], r['ivd'], r['cond'], len(r['images'])):
            raise SystemExit(f"record/request mismatch {r['rid']}")
    return got


def truth_map(labels):
    return {(p['patient'], i['k']): i['modic'] for p in json.load(open(labels)) for i in p['ivd']}


def ba02_counts(y, pred):
    """patient-별 집계에 쓸 (n0,c0,n2,c2) 반환용: y,pred 정수 배열."""
    n0 = int((y == 0).sum()); c0 = int(((y == 0) & (pred == 0)).sum())
    n2 = int((y == 2).sum()); c2 = int(((y == 2) & (pred == 2)).sum())
    return n0, c0, n2, c2


class Table:
    """행: (patient,k) 정렬. 환자 인덱스, truth, 조건별 pred/probs."""
    def __init__(self, recs, truth, conds):
        keys = sorted({(r['patient'], r['ivd']) for r in recs.values()}, key=lambda t: (int(t[0]), t[1]))
        self.keys = keys
        self.pat = np.array([k[0] for k in keys]); self.k = np.array([k[1] for k in keys])
        self.y = np.array([truth[k] for k in keys])
        self.pids = sorted(set(self.pat), key=int)
        self.pidx = np.array([self.pids.index(p) for p in self.pat])
        self.probs, self.pred, self.meta = {}, {}, {}
        for c in conds:
            P = np.array([recs[f'{self._split(recs)}|{p}|{k}|{c}']['cand_probs'] for p, k in keys])
            self.probs[c] = P
            self.pred[c] = P.argmax(1)
            rr = [recs[f'{self._split(recs)}|{p}|{k}|{c}'] for p, k in keys]
            self.meta[c] = {'top_in_cand': float(np.mean([r['top_in_candidates'] for r in rr])), 'cand_mass_mean': float(np.mean([r['cand_mass_full'] for r in rr])),
                            't_total_s': float(np.sum([r['t_total_s'] for r in rr])), 'n_images_mean': float(np.mean([r['n_images'] for r in rr]))}

    @staticmethod
    def _split(recs):
        return next(iter(recs)).split('|')[0]

    def patient_counts(self, pred):
        """[n_patients,4] = n0,c0,n2,c2."""
        out = np.zeros((len(self.pids), 4))
        for i in range(len(self.pids)):
            m = self.pidx == i
            out[i] = ba02_counts(self.y[m], pred[m])
        return out

    def add_derived(self, name, probs):
        self.probs[name] = probs; self.pred[name] = probs.argmax(1)


def ba_from_counts(cnt, w=None):
    s = cnt.sum(0) if w is None else (cnt * w[:, None]).sum(0)
    if s[0] == 0 or s[2] == 0:
        return float('nan'), float('nan'), float('nan')
    r0, r2 = s[1] / s[0], s[3] / s[2]
    return 0.5 * (r0 + r2), r0, r2


def boot_weights(n, nb=NB, seed=SEED):
    rng = np.random.RandomState(seed)
    idx = rng.randint(0, n, size=(nb, n))
    W = np.zeros((nb, n))
    for b in range(nb):
        W[b] = np.bincount(idx[b], minlength=n)
    return W


def boot_ba(cnt, W):
    s = W @ cnt                      # [nb,4]
    ok = (s[:, 0] > 0) & (s[:, 2] > 0)
    v = np.full(len(W), np.nan)
    v[ok] = 0.5 * (s[ok, 1] / s[ok, 0] + s[ok, 3] / s[ok, 2])
    return v


def ci(v):
    v = v[~np.isnan(v)]
    return [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))], int(len(v))


def prior_pred(table, dtruth_pairs):
    """D 기반 prior: global 최빈, IVD-ordinal 최빈(없으면 global, 동률은 작은 등급)."""
    def mode(vals):
        c = np.bincount(vals, minlength=4)
        return int(np.argmax(c))   # argmax는 동률 시 첫(작은) index
    gl = mode(np.array(list(dtruth_pairs.values())))
    byk = {}
    for (p, k), g in dtruth_pairs.items():
        byk.setdefault(k, []).append(g)
    ordm = {k: mode(np.array(v)) for k, v in byk.items()}
    return np.full(len(table.y), gl), np.array([ordm.get(int(k), gl) for k in table.k])


def null_ba(table, pred, ndraw=200, seed=SEED):
    """같은 ordinal의 다른 환자 예측을 재배정. donor 없는 행은 제외(미산출 수 보고). returns mean BA, n_rows_used, n_rows_no_donor."""
    rng = np.random.RandomState(seed)
    donors = []
    for i in range(len(table.y)):
        d = np.where((table.k == table.k[i]) & (table.pat != table.pat[i]))[0]
        donors.append(d)
    use = np.array([len(d) > 0 for d in donors])
    vals = []
    for _ in range(ndraw):
        pr = np.array([pred[rng.choice(d)] if len(d) else -1 for d in donors])
        y = table.y[use]; p = pr[use]
        n0, c0, n2, c2 = ba02_counts(y, p)
        if n0 == 0 or n2 == 0:
            return float('nan'), int(use.sum()), int((~use).sum())
        vals.append(0.5 * (c0 / n0 + c2 / n2))
    return float(np.mean(vals)), int(use.sum()), int((~use).sum())


def confusion(y, pred):
    m = np.zeros((4, 4), int)
    for a, b in zip(y, pred):
        m[a, b] += 1
    return m.tolist()


def per_patient_errors(table, pred):
    return {p: int(((table.pidx == i) & (pred != table.y)).sum()) for i, p in enumerate(table.pids)}


def analyze_model(table, dprior_truth, dsel_model):
    conds = ['S1', 'S2', 'J', 'T']
    if 'RT1' in table.pred or 'RT2' in table.pred:
        pass
    P1, P2 = table.probs['S1'], table.probs['S2']
    table.add_derived('LF', 0.5 * (P1 + P2))
    gl, om = prior_pred(table, dprior_truth)
    table.pred['prior_global'], table.pred['prior_ordinal'] = gl, om
    B = dsel_model['B'] if dsel_model else None
    rname = None
    if B and f'R{B.upper()}' in table.pred:
        rname = f'R{B.upper()}'
        table.pred['R'] = table.pred[rname]
    names = ['S1', 'S2', 'J', 'LF', 'T', 'prior_global', 'prior_ordinal'] + (['R'] if rname else [])
    W = boot_weights(len(table.pids))
    res = {'n_patients': len(table.pids), 'n_ivd': int(len(table.y)), 'truth_counts': {R_: int((table.y == i).sum()) for i, R_ in enumerate(['0', 'I', 'II', 'III'])}, 'B': B, 'cond': {}}
    cnts = {}
    for n in names:
        cnt = table.patient_counts(table.pred[n]); cnts[n] = cnt
        ba, r0, r2 = ba_from_counts(cnt)
        bs = boot_ba(cnt, W)
        c, nv = ci(bs) if not np.isnan(ba) else (None, 0)
        nb, nu, nnd = null_ba(table, table.pred[n]) if not n.startswith('prior') else (None, None, None)
        res['cond'][n] = {'BA02': ba, 'recall0': r0, 'recall2': r2, 'BA02_ci95': c, 'boot_valid': nv, 'acc4': float((table.pred[n] == table.y).mean()),
                          'confusion_rows_true_cols_pred': confusion(table.y, table.pred[n]), 'null_BA02': nb, 'null_rows_used': nu, 'null_rows_no_donor': nnd,
                          'pred_counts': np.bincount(table.pred[n], minlength=4).tolist(), 'errors_per_patient': per_patient_errors(table, table.pred[n]),
                          **({k: v for k, v in table.meta.get(n, {}).items()} if n in table.meta else {})}
    comps = {}
    for a, b in [('J', 'S1'), ('J', 'S2'), ('J', 'LF'), ('J', 'R'), ('J', 'T'), ('LF', 'S1'), ('LF', 'S2')]:
        if a in cnts and b in cnts:
            d = boot_ba(cnts[a], W) - boot_ba(cnts[b], W)
            c, nv = ci(d)
            comps[f'{a}-{b}'] = {'point': res['cond'][a]['BA02'] - res['cond'][b]['BA02'], 'ci95': c, 'boot_valid': nv}
    if B:
        bn = 'S1' if B == 't1' else 'S2'
        for a in ('J', 'LF'):
            d = boot_ba(cnts[a], W) - boot_ba(cnts[bn], W)
            c, nv = ci(d)
            comps[f'{a}-B'] = {'point': res['cond'][a]['BA02'] - res['cond'][bn]['BA02'], 'ci95': c, 'boot_valid': nv}
    res['paired'] = comps
    # 실제 I/III 행의 모든 출력
    rare = [{'patient': table.keys[i][0], 'k': int(table.keys[i][1]), 'truth': int(table.y[i]),
             **{n: [OPT[table.pred[n][i]], [round(float(x), 4) for x in (table.probs[n][i] if n in table.probs else [])]] for n in ['S1', 'S2', 'J', 'LF', 'T'] + (['R'] if rname else [])}}
            for i in range(len(table.y)) if table.y[i] in (1, 3)]
    res['rare_rows'] = rare
    return res


def e12_gate(res, dsel_model):
    c = res['cond']
    B = dsel_model['B']
    bname = 'S1' if B == 't1' else 'S2'
    prior = max(c['prior_global']['BA02'], c['prior_ordinal']['BA02'])
    out = {'prior_best': prior, 'checks': {}}
    undefined = False
    sat = []
    for n in ('S1', 'S2', 'J', 'LF'):
        ba = c[n]['BA02']; nl = c[n]['null_BA02']; t = c['T']['BA02']
        if any(v is None or np.isnan(v) for v in (ba, nl, t, prior)):
            undefined = True; continue
        ok = ba >= 0.65 and ba - prior >= 0.05 and ba - t >= 0.05 and ba - nl >= 0.05
        out['checks'][n] = {'BA02': ba, 'ge_0.65': ba >= 0.65, 'minus_prior': ba - prior, 'minus_text': ba - t, 'minus_null': ba - nl, 'ok': bool(ok)}
        if ok:
            sat.append(n)
    diffJ = c['J']['BA02'] - c[bname]['BA02']; diffL = c['LF']['BA02'] - c[bname]['BA02']
    out['proc_diff'] = {'J-B': diffJ, 'LF-B': diffL, 'ok': bool(abs(diffJ) >= 0.05 or abs(diffL) >= 0.05)}
    out['signal_ok'] = bool(sat); out['signal_conditions'] = sat; out['undefined'] = undefined
    out['expand'] = bool(sat) and out['proc_diff']['ok']
    out['verdict'] = 'expand' if out['expand'] else ('indeterminate' if undefined and not sat else 'stop')
    return out


def final_decision(res, dsel_model):
    c, p = res['cond'], res['paired']
    prior = max(c['prior_global']['BA02'], c['prior_ordinal']['BA02'])
    J = c['J']
    chk = {'J_BA>=0.70': J['BA02'] >= 0.70, 'recall0>=0.60': J['recall0'] >= 0.60, 'recall2>=0.60': J['recall2'] >= 0.60,
           'J-prior>=0.05': J['BA02'] - prior >= 0.05, 'J-text>=0.05': J['BA02'] - c['T']['BA02'] >= 0.05, 'J-null>=0.05': J['null_BA02'] is not None and J['BA02'] - J['null_BA02'] >= 0.05}
    for n in ('S1', 'S2', 'LF'):
        d = p.get(f'J-{n}')
        chk[f'J-{n}>=0.05_and_CIlow>0'] = bool(d and d['point'] >= 0.05 and d['ci95'] and d['ci95'][0] > 0)
    d = p.get('J-R')
    chk['J-R_CIlow>0'] = bool(d and d['ci95'] and d['ci95'][0] > 0)
    return {'checks': {k: bool(v) for k, v in chk.items()}, 'joint_added_value_candidate': bool(all(chk.values()))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--split'); ap.add_argument('--out-dir'); ap.add_argument('--requests'); ap.add_argument('--labels'); ap.add_argument('--protocol')
    ap.add_argument('--gen-root'); ap.add_argument('--dsel', default=None); ap.add_argument('--dprior-labels', default='results/iter_067/data/pairs_D.json')
    ap.add_argument('--final', action='store_true'); ap.add_argument('--models', default='medgemma,qwen')
    a = ap.parse_args()
    pdig = R.check_protocol(a.protocol, a.requests, a.labels)
    truth = truth_map(a.labels)
    dtruth = truth_map(a.dprior_labels)
    dsel = json.load(open(a.dsel)) if a.dsel else {}
    rows = M65.read_jsonl(a.requests)
    conds = sorted({r['cond'] for r in rows})
    os.makedirs(a.out_dir, exist_ok=True)
    out = {'split': a.split, 'protocol_digest': pdig, 'requests_sha': M65.sha_file(a.requests), 'labels_sha': M65.sha_file(a.labels), 'dsel': a.dsel, 'models': {}}
    for model in a.models.split(','):
        recs = load_recs(a.gen_root, model, a.requests, pdig)
        t = Table(recs, truth, conds)
        res = analyze_model(t, dtruth, dsel.get(model))
        if a.split.startswith('E') and dsel.get(model):
            res['e12_gate'] = e12_gate(res, dsel[model])
        if a.final:
            res['final'] = final_decision(res, dsel.get(model))
        out['models'][model] = res
    json.dump(out, open(f'{a.out_dir}/report.json', 'w'), indent=1, default=float)
    for m, r in out['models'].items():
        print(m, {n: round(v['BA02'], 3) if v['BA02'] == v['BA02'] else None for n, v in r['cond'].items()}, r.get('e12_gate', {}).get('verdict'))


if __name__ == '__main__':
    main()
