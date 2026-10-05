"""production metric을 사용하지 않는 raw 출력·환자 bootstrap 재계산."""
import argparse
import json
import re
from pathlib import Path
import numpy as np
import a81_common as C


def verify(report_path, dest):
    report = C.read(report_path); split = report['split']
    rows = C.read(C.ROOT / f'data/baseline_{split}.json')
    ids = [r['id'] for r in rows]
    assert ids == report['ids']
    outputs = {c: {} for c in ('A', 'T', 'X')}
    for p in Path(report['provenance']['out']).glob('worker*/records/*.json'):
        r = C.read(p); cond = r['request']['cond']; rid = r['request']['id']
        assert rid not in outputs[cond]
        t = r['text'].strip()
        m = re.fullmatch(r'([1-5])\s*\.?', t)
        outputs[cond][rid] = int(m[1]) if r['ended_eos'] and m else None
    for v in outputs.values(): assert set(v) == set(ids)
    predictions = {c: [outputs[c][i] for i in ids] for c in outputs}
    qraw = {}
    for p in {r['Q_source'] for r in rows}:
        for line in Path(p).read_text().splitlines():
            r = json.loads(line)
            if r['id'] not in ids: continue
            assert r['id'] not in qraw
            m = re.fullmatch(r'([1-5])\s*\.?', r['text'].strip())
            qraw[r['id']] = int(m[1]) if m and r['ended_eos'] else None
    predictions['Q'] = [qraw[i] for i in ids]
    feat = C.read('results/iter_078/features.json')['items']
    predictions['C_argmax'] = [int(np.asarray(feat[i]['probs']).argmax()) + 1 for i in ids]
    chosen = report['M']
    if chosen == 'Q': predictions['M'] = predictions['Q']
    elif chosen == 'C_argmax': predictions['M'] = predictions['C_argmax']
    elif chosen == 'C_median':
        predictions['M'] = [next(j+1 for j in range(5) if sum(feat[i]['probs'][:j+1]) >= .5) for i in ids]
    else:
        tau = float(chosen.split('_')[1])
        predictions['M'] = [q if max(feat[i]['probs']) < tau and q is not None else c
                            for i,q,c in zip(ids,predictions['Q'],predictions['C_argmax'])]
    assert predictions == report['predictions']
    y = np.array([r['grade'] for r in rows]); classes = sorted(set(y.tolist()))
    errs = {k: np.array([4 if p is None else abs(int(t)-p) for t,p in zip(y, ps)], float) for k,ps in predictions.items()}
    def metric(e, ix):
        return np.mean([e[ix][y[ix] == g].mean() for g in classes if np.any(y[ix] == g)])
    checks = []
    for k,e in errs.items():
        s = report['systems'][k]
        checks.extend([abs(metric(e, np.arange(len(y))) - s['class_std_mae']) < 1e-12,
                       abs(e.mean()-s['mae']) < 1e-12, int(sum(e >= 2)) == s['err_ge2_n'],
                       sum(p is None for p in predictions[k]) == s['invalid_n'],
                       sum(a == c for a,c in zip(predictions[k], predictions['C_argmax'])) == s['matches_C_n']])
    pats = sorted({r['patient'] for r in rows}, key=int)
    inds = [np.array([i for i,r in enumerate(rows) if r['patient'] == p]) for p in pats]
    rng = np.random.default_rng(7501); diffs = {k: [] for k in ('M','T','X','Q','C_argmax')}; missing = 0
    for _ in range(10000):
        ix = np.concatenate([inds[i] for i in rng.integers(0, len(pats), len(pats))])
        missing += len(set(y[ix])) < len(classes)
        a = metric(errs['A'], ix)
        for k in diffs: diffs[k].append(a - metric(errs[k], ix))
    for k, vals in diffs.items():
        stored = report['paired']['A-'+k]
        checks.append(np.allclose(np.percentile(vals, [2.5,97.5]), stored['ci95'], atol=1e-12, rtol=0))
        checks.append(missing == stored['n_missing_class_replicates'])
    cor = [r['id'] for i,r in enumerate(rows) if errs['A'][i] < errs['C_argmax'][i]]
    damaged = [r['id'] for i,r in enumerate(rows) if errs['C_argmax'][i] == 0 and errs['A'][i] > 0]
    toward = []
    for i,r in enumerate(rows):
        q,a,c = (predictions[k][i] for k in ('Q','A','C_argmax'))
        if q is not None and a is not None and abs(q-y[i]) < abs(c-y[i]) and abs(a-y[i]) > abs(q-y[i]) and abs(a-c) < abs(q-c): toward.append(r['id'])
    tr = report['posthoc_transitions']
    checks.extend([cor == tr['C_error_reduced_ids'], damaged == tr['C_correct_damaged_ids'], toward == tr['Q_better_moved_toward_C_ids']])
    visual = all(np.percentile(diffs[k], 97.5) < 0 for k in ('T','X'))
    min_gain = report['systems']['A']['class_std_mae'] - report['systems']['M']['class_std_mae'] <= -.1
    positive = min_gain and np.percentile(diffs['M'],97.5) < 0 and visual and sum(errs['A'] >= 2) <= sum(errs['M'] >= 2)
    pid = {r['id']:r['patient'] for r in rows}
    pilot = not positive and visual and len({pid[i] for i in cor}) >= 2 and len({pid[i] for i in toward}) >= 2
    verdict = 'positive_exploratory' if positive else ('method_pilot_candidate' if pilot else ('negative' if not visual and not min_gain else 'inconclusive'))
    checks.append(verdict == report['criteria']['verdict'])
    result = {'passed': bool(all(checks)), 'checks': len(checks), 'failures': sum(not bool(x) for x in checks),
              'report_sha256': C.sha(report_path), 'missing_class_replicates': int(missing), 'verdict': verdict,
              'sources': {str(p):C.sha(p) for p in [Path(report_path), C.ROOT / f'data/baseline_{split}.json']},
              'raw_files': {str(p):C.sha(p) for p in Path(report['provenance']['out']).glob('worker*/records/*.json')}}
    C.save(dest, result)
    assert result['passed'], result
    print(result['passed'], result['checks'], result['verdict'])


if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('report'); p.add_argument('dest'); a=p.parse_args(); verify(a.report,a.dest)
