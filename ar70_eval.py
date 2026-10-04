"""iter_070 evaluation: blind rule extraction from raw AutoRG reports -> BA, accuracy, UNKNOWN, P/G/B comparison.

extract_label(text) depends only on the generated text (no GT, no condition). Rules fixed in plan.md before output:
HIGH = explicit high/hyperintense lesion signal without low component; MIXED_HIGH_LOW = explicit high and low
components; everything else (mixed/heterogeneous only, hypo only, enhancement, no signal statement, conflicting) = UNKNOWN.
Usage: python ar70_eval.py <main_dir> <out_json> [exclude_dev_cases:0/1]
"""
import hashlib
import json
import os
import re
import sys

import numpy as np

CLS = ['HIGH', 'MIXED_HIGH_LOW']
PRIOR_B = 'MIXED_HIGH_LOW'  # from train counts (ar70_labels.py: 92 vs 36)
DEV_CASES = ['BraTS-GLI-00012-000', 'BraTS-GLI-00456-000']
CUT = re.compile(r',?\s+(?:with|while|whereas|and)\s+(?:the\s+)?(?:surrounding|adjacent)', re.I)
MIXED_HL = re.compile(r'mixed (?:high|hyperintens\w*) and (?:low|hypointens\w*)|mixed hyperintens\w* and hypointens\w*', re.I)
HIGHP = re.compile(r'hyperintens|high[- ](?:fl?air )?signal|high signal|high intensit', re.I)
LOWP = re.compile(r'hypointens|low[- ]signal|low intensit|\blow\b', re.I)
MIXEDP = re.compile(r'mixed|heterogene', re.I)


def extract_label(text):
    """returns (label, evidence sentence or None)"""
    if not text:
        return 'UNKNOWN', None
    sents = [s.strip() for s in re.split(r'(?<=[.])\s+', text) if s.strip()]
    found = []
    for s in sents:
        if not re.search(r'lesion|abnormal signal|tumou?r', s, re.I):
            continue
        part = CUT.split(s)[0]
        if MIXED_HL.search(part) or (HIGHP.search(part) and LOWP.search(part)):
            found.append(('MIXED_HIGH_LOW', s))
        elif HIGHP.search(part) and not MIXEDP.search(part) and not LOWP.search(part):
            found.append(('HIGH', s))
    labs = {f[0] for f in found}
    if len(labs) == 1:
        return found[0][0], found[0][1]
    return 'UNKNOWN', (found[0][1] if found else None)


def ba(y, p):
    r = []
    for c in CLS:
        idx = [i for i, t in enumerate(y) if t == c]
        r.append(np.mean([p[i] == c for i in idx]) if idx else np.nan)
    return float(np.nanmean(r)), r


def metrics(y, p):
    b, r = ba(y, p)
    return {'BA': b, 'recall_HIGH': r[0], 'recall_MIXED': r[1],
            'acc': float(np.mean([a == c for a, c in zip(p, y)])),
            'unknown_rate': float(np.mean([a == 'UNKNOWN' for a in p]))}


def boot(y, pa, pb, clusters, n=10000, seed=70):
    """cluster paired bootstrap of BA(pa)-BA(pb); returns mean, 95% CI, #degenerate replicates skipped."""
    rng = np.random.default_rng(seed)
    cl = sorted(set(clusters))
    by = {c: [i for i, k in enumerate(clusters) if k == c] for c in cl}
    ds, skipped = [], 0
    for _ in range(n):
        pick = rng.integers(0, len(cl), len(cl))
        idx = [i for k in pick for i in by[cl[k]]]
        yy = [y[i] for i in idx]
        if len(set(yy)) < 2:
            skipped += 1
            continue
        ds.append(ba(yy, [pa[i] for i in idx])[0] - ba(yy, [pb[i] for i in idx])[0])
    return {'diff_mean': float(np.mean(ds)), 'ci95': [float(np.percentile(ds, 2.5)), float(np.percentile(ds, 97.5))], 'skipped': skipped}


def main():
    main_dir, out = sys.argv[1], sys.argv[2]
    excl = len(sys.argv) > 3 and sys.argv[3] == '1'
    L = json.load(open('results/iter_070/data/label_table.json'))
    seal = json.load(open(os.path.join(main_dir, 'seal.json')))
    cases = seal['cases']
    if excl:
        cases = [c for c in cases if c not in DEV_CASES]
    raw = {}
    for c in cases:
        for cond in 'PG':
            p = os.path.join(main_dir, 'results', f'{c}__{cond}.json')
            assert os.path.exists(p), 'missing ' + p
            r = json.load(open(p))
            assert r['status'] == 'ok' and r['case'] == c and r['cond'] == cond
            assert r['protocol_hash'] == json.load(open(os.path.join(main_dir, 'log', sorted(f for f in os.listdir(os.path.join(main_dir, 'log')) if f.startswith('worker_'))[0])))['protocol_hash']
            raw[(c, cond)] = r
    files = [f for f in os.listdir(os.path.join(main_dir, 'results')) if f.endswith('.json')]
    assert len(files) == 2 * len(seal['cases']), (len(files), len(seal['cases']))
    y = [L['val'][c]['label'] for c in cases]
    clusters = [c.split('-')[2] for c in cases]
    preds, ev = {}, {}
    for cond in 'PG':
        pl = []
        for c in cases:
            a = raw[(c, cond)]['attempts'][-1]
            lab, e = extract_label(a['report'])
            pl.append(lab)
            ev.setdefault(c, {})[cond] = {'label': lab, 'evidence': e, 'report': a['report'], 'cap_hit_final': a['cap_hit'], 'n_attempts': len(raw[(c, cond)]['attempts'])}
        preds[cond] = pl
    preds['B'] = [PRIOR_B] * len(cases)
    res = {'n': len(cases), 'excluded_dev_cases': excl, 'class_counts': {c: y.count(c) for c in CLS}, 'n_clusters': len(set(clusters)),
           'metrics': {k: metrics(y, v) for k, v in preds.items()},
           'conversions_P_to_G': {'P_wrong_G_right': sum(1 for i in range(len(y)) if preds['P'][i] != y[i] and preds['G'][i] == y[i]),
                                  'P_right_G_wrong': sum(1 for i in range(len(y)) if preds['P'][i] == y[i] and preds['G'][i] != y[i]),
                                  'same_label_text': sum(1 for c in cases if ev[c]['P']['report'] == ev[c]['G']['report'])},
           'boot': {'G_minus_P_BA': boot(y, preds['G'], preds['P'], clusters), 'P_minus_B_BA': boot(y, preds['P'], preds['B'], clusters),
                    'G_minus_B_BA': boot(y, preds['G'], preds['B'], clusters)}}
    m = res['metrics']

    def crit(k):
        x = m[k]
        return {'BA>=0.70': bool(x['BA'] >= 0.70), 'recalls>=0.60': bool(min(x['recall_HIGH'], x['recall_MIXED']) >= 0.60),
                'unknown<=0.10': bool(x['unknown_rate'] <= 0.10), 'acc_gain_vs_B>=0.10': bool(x['acc'] - m['B']['acc'] >= 0.10)}
    res['criteria'] = {k: crit(k) for k in 'PG'}
    res['criteria_all_met'] = {k: all(v.values()) for k, v in res['criteria'].items()}
    res['per_case'] = {c: {'gt': L['val'][c]['label'], **ev[c]} for c in cases}
    res['inputs'] = {'labels_sha256': hashlib.sha256(open('results/iter_070/data/label_table.json', 'rb').read()).hexdigest(),
                     'eval_sha256': hashlib.sha256(open(__file__, 'rb').read()).hexdigest()}
    json.dump(res, open(out, 'w'), indent=1, ensure_ascii=False)
    print(json.dumps({k: res[k] for k in ['n', 'class_counts', 'metrics', 'conversions_P_to_G', 'boot', 'criteria_all_met']}, indent=1))


if __name__ == '__main__':
    main()
