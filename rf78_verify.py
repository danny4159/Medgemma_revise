"""iter_078 독립 재계산: production 평가기(rf78_eval, sp75_metrics, sp75_vlm.parse)를 호출하지 않고 원시 jsonl·labels·features로 주지표와 paired CI를 다시 계산.
M(선택된 단순 대안)은 select_M.json의 이름에서 features/T24 grade만으로 다시 만든다. 출력 seal(파일 hash)·EOS·유효 출력·종료 코드를 함께 기록.
"""
import glob, hashlib, json, re, sys

import numpy as np

OUT = 'results/iter_078'
Q_SRC = {'V8': 'results/iter_077/gen/V8/R_lr2e-4_ep16', 'E24': 'results/iter_077/gen/E24/R_adapted'}


def sh(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def jl(d):
    return [json.loads(l) for f in sorted(glob.glob(d + '/gen_worker*.jsonl')) for l in open(f) if l.strip()]


def parse(raw):
    t = raw.replace('<end_of_turn>', '').strip()
    if t.endswith('.'):
        t = t[:-1].strip()
    return int(t) if re.fullmatch('[1-5]', t) else None


def cs_mae(t, p):
    t = np.asarray(t)
    e = np.array([4.0 if x is None else abs(a - x) for a, x in zip(t, p)])
    return float(np.mean([e[t == g].mean() for g in range(1, 6) if (t == g).any()])), e


def boot(rows_pat, t, pa, pb, n=10000, seed=7501):
    rng = np.random.default_rng(seed)
    pids = sorted(set(rows_pat), key=int)
    idx = {p: [i for i, q in enumerate(rows_pat) if q == p] for p in pids}
    ds = []
    for _ in range(n):
        ch = rng.integers(0, len(pids), len(pids))
        ix = np.array([i for c in ch for i in idx[pids[c]]])
        ds.append(cs_mae(t[ix], [pa[i] for i in ix])[0] - cs_mae(t[ix], [pb[i] for i in ix])[0])
    return float(np.percentile(ds, 2.5)), float(np.percentile(ds, 97.5))


def med(d):
    return int(np.argmax(np.cumsum(d) >= 0.5 - 1e-12) + 1)


def main():
    split = sys.argv[1]
    root = {'V8': f'{OUT}/gen/V8_main', 'E24': f'{OUT}/gen/E24_main'}[split]
    rep = json.load(open(f'{OUT}/eval/report_{split}.json'))
    reqs = json.load(open(f'{OUT}/data/refs_{split}.json'))['requests']
    lab = json.load(open(f'{OUT}/data/labels_{split}.json'))['labels']
    ids = [q['id'] for q in reqs]
    t = np.array([lab[i]['grade'] for i in ids])
    pat = [lab[i]['patient'] for i in ids]
    out = {'split': split, 'n': len(ids), 'systems': {}, 'completeness': {}, 'seal': {}}
    preds = {}
    for cond in 'LID':
        rs = jl(f'{root}/{cond}')
        by = {r['id']: r for r in rs}
        out['completeness'][cond] = {'n_records': len(rs), 'n_unique': len(by), 'set_equal': set(by) == set(ids), 'n_eos': sum(r['ended_eos'] for r in rs),
                                     'n_parse_valid': sum(parse(r['raw']) is not None for r in rs), 'parse_matches_stored': all(parse(r['raw']) == r['parsed'] for r in rs if r['ended_eos'])}
        preds[cond] = [parse(by[i]['raw']) if by[i]['ended_eos'] else None for i in ids]
        out['seal'][cond] = {f: sh(f) for f in sorted(glob.glob(f'{root}/{cond}/gen_worker*.jsonl'))}
        out['completeness'][cond]['launch_exit_codes'] = json.load(open(f'{root}/launch_result.json'))['conds'][cond]['exit_codes']
    qb = {r['id']: r for r in jl(Q_SRC[split])}
    preds['Q'] = [parse(qb[i]['raw']) if qb[i]['ended_eos'] else None for i in ids]
    ft = json.load(open(f'{OUT}/features.json'))['items']
    man = json.load(open('results/iter_075/data/manifest.json'))['rows']
    bank = [(r['patient'], r['ordinal'], r['grade'], np.array(ft[r['id']]['feat'])) for r in man if r['split'] == 'T24' and r['position_set'] == 'supervised' and not r['excluded']]
    sel = json.load(open(f'{OUT}/eval/select_M.json'))
    cprob = [np.array(ft[i]['probs']) for i in ids]
    def knn(i, k):
        qf = np.array(ft[i]['feat'])
        sims = sorted(((float(qf @ b[3]), b) for b in bank), key=lambda s: (-round(s[0], 12), int(s[1][0]), s[1][1]))
        seen, ch = set(), []
        for s, b in sims:
            if b[0] in seen:
                continue
            seen.add(b[0]); ch.append(b)
            if len(ch) == k:
                break
        d = np.zeros(5)
        for b in ch:
            d[b[2] - 1] += 1 / k
        return d
    name = sel['M']
    if name == 'C_argmax':
        preds['M'] = [int(np.argmax(p)) + 1 for p in cprob]
    elif name == 'Q':
        preds['M'] = preds['Q']
    elif name.startswith('CkNN'):
        m = re.fullmatch(r'CkNN_k(\d)_lam([0-9.]+)', name)
        k, lam = int(m.group(1)), float(m.group(2))
        preds['M'] = [med((1 - lam) * cprob[j] + lam * knn(i, k)) for j, i in enumerate(ids)]
    else:
        raise SystemExit('combo M not re-implemented')
    for c in ('Q', 'L', 'I', 'D', 'M'):
        v, e = cs_mae(t, preds[c])
        out['systems'][c] = {'class_std_mae': v, 'mae': float(e.mean()), 'err_ge2': float((e >= 2).mean()), 'n_invalid': int(sum(p is None for p in preds[c]))}
    out['paired'] = {}
    pairs = (('I', 'L'), ('I', 'D'), ('I', 'M'), ('I', 'Q')) if split == 'E24' else (('I', 'L'), ('I', 'D'), ('I', 'Q'))
    for a, b in pairs:
        pt = cs_mae(t, preds[a])[0] - cs_mae(t, preds[b])[0]
        out['paired'][f'{a}-{b}'] = {'point': pt, 'ci95': boot(pat, t, preds[a], preds[b])}
    # production report와의 최대 차이
    diffs = []
    for c in ('Q', 'L', 'I', 'D', 'M'):
        if split == 'E24':
            diffs.append(abs(out['systems'][c]['class_std_mae'] - rep['systems'][c]['class_std_mae']))
        elif c != 'M':
            diffs.append(abs(out['systems'][c]['class_std_mae'] - rep['vlm_systems'][c]['class_std_mae']))
    if split == 'E24':
        for k, v in out['paired'].items():
            diffs += [abs(v['point'] - rep['paired'][k]['point']), abs(v['ci95'][0] - rep['paired'][k]['ci95'][0]), abs(v['ci95'][1] - rep['paired'][k]['ci95'][1])]
    out['max_abs_diff_vs_production'] = float(max(diffs))
    json.dump(out, open(f'{OUT}/eval/independent_verify_{split}.json', 'w'), indent=1)
    print(json.dumps({'maxdiff': out['max_abs_diff_vs_production'], 'complete': out['completeness'], 'systems': out['systems'], 'paired': out['paired']}))


if __name__ == '__main__':
    main()
