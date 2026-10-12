"""iter_117 원시 답·공유 미해결 변수·기하·bootstrap·최종 분기의 독립 검산.

생산 ed116_eval/spec/analyze는 import하지 않는다. 고정 parser만 재사용한다.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import ev108_spec as S
import ev109_extract as X
from ed116_verify import max_match

POL = ('K', 'B', 'G', 'M', 'N', 'E', 'R', 'T', 'S')
JOINT = ('K', 'B', 'N', 'E', 'R', 'T', 'S')
FREE = ('G', 'N', 'E', 'R', 'T')
COMP = ('K', 'B', 'G', 'M', 'N', 'E', 'S')


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(4 << 20), b''):
            h.update(b)
    return h.hexdigest()


def policies(base):
    a = dict(base)
    k, b, g, e = (a[q] for q in ('K', 'B', 'G', 'E'))
    a['M'] = k if g is None else ('yes' if (k, b, g).count('yes') >= 2 else 'no')
    a['S'] = e if e is not None and e == b else k
    return a


def scalar(p, a):
    y, kc = p['y'], p['base']['K'] == p['y']
    c = {q: int(a[q] == y) for q in POL}
    d = {}
    for q in POL:
        d.update({f'correct_{q}': c[q], f'correction_{q}': int(not kc) * c[q],
                  f'harm_{q}': int(kc) * (1 - c[q]),
                  f'harmwrong_{q}': int(kc and a[q] is not None and a[q] != y),
                  f'flip_to_yes_{q}': int(a[q] == 'yes' and p['base']['K'] == 'no'),
                  f'flip_to_no_{q}': int(a[q] == 'no' and p['base']['K'] == 'yes')})
        if q != 'R':
            d[f'diff_R_{q}'] = c['R'] - c[q]
    for q in JOINT:
        count = p['n_det'] if a[q] == 'yes' else 0
        for th in ('03', '05'):
            tp = p['tp' + th] if a[q] == 'yes' else 0
            d[f'joint{th}_{q}'] = int(a[q] == 'yes' and tp == count == p['n_gt']) if y == 'yes' else int(a[q] == 'no')
            d[f'fp{th}_{q}'] = count - tp
            d[f'fn{th}_{q}'] = p['n_gt'] - tp if y == 'yes' else 0
        d[f'posf1_03_{q}'] = (2 * p['tp03'] / (count + p['n_gt'])) if y == 'yes' and a[q] == 'yes' else 0.0
    for q in JOINT:
        if q != 'R':
            d[f'jdiff03_R_{q}'] = d['joint03_R'] - d[f'joint03_{q}']
    return d


def bounds(p):
    free = [q for q in FREE if p['base'][q] is None]
    values = []
    for combo in itertools.product(('yes', 'no'), repeat=len(free)):
        a = dict(p['base'])
        a.update(zip(free, combo))
        values.append(scalar(p, policies(a)))
    return ({k: min(v[k] for v in values) for k in values[0]},
            {k: max(v[k] for v in values) for k in values[0]})


def group(patients):
    pts = [scalar(p, p['base']) for p in patients]
    rg = [bounds(p) for p in patients]
    n = len(pts)
    idx = np.random.default_rng(11617).integers(0, n, size=(10000, n), dtype=np.int32)
    kc = np.array([int(p['base']['K'] == p['y']) for p in patients])
    def ci(v, den=None):
        v = np.asarray(v, float)
        if den is None:
            point, samples = v.mean(), v[idx].mean(axis=1)
        else:
            den = np.asarray(den, float)
            if not den.sum():
                return [None, None, None]
            ds = den[idx].sum(axis=1)
            samples = v[idx].sum(axis=1)[ds > 0] / ds[ds > 0]
            point = v.sum() / den.sum()
        return [float(point), *map(float, np.percentile(samples, [2.5, 97.5]))]
    vec = lambda k: [v[k] for v in pts]
    ci95 = {}
    for q in POL:
        if q != 'R':
            ci95[f'diff_R_{q}'] = ci(vec(f'diff_R_{q}'))
        ci95[f'accuracy_{q}'] = ci(vec(f'correct_{q}'))
        ci95[f'correction_rate_{q}'] = ci(vec(f'correction_{q}'), 1 - kc)
        ci95[f'harm_rate_{q}'] = ci(vec(f'harm_{q}'), kc)
    for q in JOINT:
        if q != 'R':
            ci95[f'jdiff03_R_{q}'] = ci(vec(f'jdiff03_R_{q}'))
    return dict(n=n, n_K_correct=int(kc.sum()), n_K_wrong=int(n - kc.sum()),
                point={k: sum(v[k] for v in pts) for k in pts[0]},
                range_min={k: sum(lo[k] for lo, hi in rg) for k in pts[0]},
                range_max={k: sum(hi[k] for lo, hi in rg) for k in pts[0]}, ci95=ci95,
                n_unresolved_cells={q: sum(p['base'][q] is None for p in patients) for q in FREE})


def decision(mm, ag):
    criteria = {}
    for mode in ('point', 'worst', 'best'):
        def v(rep, key, high):
            if mode == 'point':
                return rep['point'][key]
            use_min = (mode == 'worst') == high
            return rep['range_min' if use_min else 'range_max'][key]
        c = {'R_correction>=10': v(mm, 'correction_R', True) >= 10,
             'R_harm<=5': v(mm, 'harm_R', False) <= 5,
             **{f'R_minus_{q}>=5': v(mm, f'diff_R_{q}', True) >= 5 for q in COMP},
             'agree_harm_rate<=0.05': v(ag, 'harm_R', False) <= .05 * ag['n_K_correct']}
        criteria[mode] = c
    pt, worst, best = (all(criteria[m].values()) for m in ('point', 'worst', 'best'))
    label = ('positive_exploratory' if pt and worst else 'inconclusive_unresolved_flips_criteria' if pt else
             'inconclusive_unresolved_could_satisfy' if best else 'hold_current_frozen_setting')
    return dict(label=label, **criteria)


def compare_group(expected, actual):
    checks = []
    for field in ('n', 'n_K_correct', 'n_K_wrong', 'point', 'range_min', 'range_max', 'ci95', 'n_unresolved_cells'):
        def eq(x, y):
            if isinstance(x, dict):
                return isinstance(y, dict) and set(x) == set(y) and all(eq(v, y[k]) for k, v in x.items())
            if isinstance(x, list):
                return isinstance(y, list) and len(x) == len(y) and all(eq(a, b) for a, b in zip(x, y))
            return x == y if x is None or y is None else abs(x - y) < 1e-10
        checks.append(dict(name=field, passed=eq(expected[field], actual[field])))
    return checks


def make_patient(row, gt, ans):
    k = X.resolve('O', row['O']['raw'], row['O']['ended_eos'])['answer']
    st, _ = S.parse_saved_bbox(row['SFT']['raw'], row['SFT']['ended_eos'])
    boxes = [b for s, b in zip(row['det']['scores'], row['det']['boxes_xyxy_px']) if s >= .70]
    top, left, side = row['pad']
    pred = [[(b[1] + top) * 1000 / side, (b[0] + left) * 1000 / side,
             (b[3] + top) * 1000 / side, (b[2] + left) * 1000 / side] for b in boxes]
    base = policies(dict(K=k, B='yes' if boxes else 'no', G={'ok': 'yes', 'empty': 'no'}.get(st), **ans))
    return dict(id=row['id'], cat=gt['category'], y='yes' if gt['category'] == 'opacity' else 'no', base=base,
                n_det=len(pred), n_gt=len(gt['gt_yxyx_norm']),
                tp03=max_match(pred, gt['gt_yxyx_norm'], .3), tp05=max_match(pred, gt['gt_yxyx_norm'], .5))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='results/iter_117')
    a = ap.parse_args()
    root = Path(a.root)
    rep = json.loads((root / 'eval/report.json').read_text())
    pp = json.loads((root / 'eval/per_patient.json').read_text())
    rows = {r['id']: r for r in json.load(open('results/iter_116/provenance/ledger_nogt.json'))['rows']}
    gt = json.load(open('results/iter_116/provenance/gt.json'))
    sel = json.load(open('results/iter_116/lock/selection.json'))
    recs, checks = {}, []
    def chk(name, ok):
        checks.append(dict(name=name, passed=bool(ok)))
    for fn in sorted((root / 'gen/MAIN').glob('gen_worker*.jsonl')):
        for ln in fn.read_text().splitlines():
            r = json.loads(ln)
            key = (r['patient'], r['cond'])
            if key in recs:
                raise ValueError('중복 출력')
            recs[key] = r
    selected = sel['mismatch'] + sel['control']
    chk('exact_record_matrix', set(recs) == {(i, c) for i in selected for c in 'NERT'} and len(recs) == 696)
    chk('exact_per_patient_matrix', len(pp) == len(selected) and {r['id'] for r in pp} == set(selected))
    key = lambda i: hashlib.sha256(('iter116|' + rows[i]['patient']).encode()).hexdigest()
    match, agree, unknown = [], [], []
    for i, row in rows.items():
        k = X.resolve('O', row['O']['raw'], row['O']['ended_eos'])['answer']
        b = 'yes' if any(s >= .70 for s in row['det']['scores']) else 'no'
        (unknown if k is None else agree if k == b else match).append(i)
    chk('selection_original', sorted(match, key=key) == sel['mismatch'] and sorted(agree, key=key)[12:99] == sel['control']
        and sorted(agree, key=key)[:12] == sel['tech'] and sorted(unknown) == sel['unresolved'])
    patients = {}
    for i in selected:
        ma = {c: X.resolve('O', recs[i, c]['suffix_text_raw'], recs[i, c]['ended_eos'])['answer'] for c in 'NERT'}
        patients[i] = make_patient(rows[i], gt[i], ma)
    for row in pp:
        i = row['id']
        chk(f'patient_{i}', row['answers'] == patients[i]['base'] and row['gt'] == patients[i]['y'] and
            all(row['raw'][c] == recs[i, c]['suffix_text_raw'] and row['ended_eos'][c] == recs[i, c]['ended_eos'] and
                row['request_ids'][c] == recs[i, c]['request_id'] for c in 'NERT') and
            row['n_det'] == patients[i]['n_det'] and row['tp03'] == patients[i]['tp03'] and
            row['n_gt'] == patients[i]['n_gt'] and row['gt_boxes_yxyx_norm'] == gt[i]['gt_yxyx_norm'])
        p = patients[i]
        kc = p['base']['K'] == p['y']
        chk(f'events_{i}', row['K_correct'] == kc and row['B_correct'] == (p['base']['B'] == p['y']) and
            all(row['correction'][q] == (not kc and p['base'][q] == p['y']) and
                row['resolved_harm'][q] == (kc and p['base'][q] is not None and p['base'][q] != p['y']) for q in POL) and
            row['wrong_advice_adopted_R'] == (i in sel['mismatch'] and kc and p['base']['R'] == p['base']['B']) and
            row['useful_advice_not_adopted_R'] == (i in sel['mismatch'] and not kc and p['base']['R'] == p['base']['K']))
    independent = {}
    for g in ('mismatch', 'control'):
        independent[g] = group([patients[i] for i in sel[g]])
        checks.extend(dict(name=g + '_' + c['name'], passed=c['passed']) for c in compare_group(independent[g], rep[g]))
    dec = decision(independent['mismatch'], independent['control'])
    chk('decision_all_original_inequalities_and_label', all(dec[k] == rep['decision'][k] for k in dec))
    obs = json.loads((root / 'eval/observations.json').read_text())
    # 사전 고정 집단의 3개 상태(정답/확정 오답/미해결)와 R-N/R-E 교차표.
    for name, table in obs['strata'].items():
        ids = table['ids']
        want = [i for i in sel[table['group']] if (patients[i]['base']['K'] == patients[i]['y']) == table['K_correct']]
        chk(name + '_ids_denominator', ids == want and table['n'] == len(want))
        for q in POL:
            want_counts = dict(correct=sum(patients[i]['base'][q] == patients[i]['y'] for i in ids),
                               wrong=sum(patients[i]['base'][q] is not None and patients[i]['base'][q] != patients[i]['y'] for i in ids),
                               unresolved=sum(patients[i]['base'][q] is None for i in ids))
            chk(name + '_' + q, table['policies'][q] == want_counts)
    for g in ('mismatch', 'control'):
        def state(i, q):
            a, y = patients[i]['base'][q], patients[i]['y']
            return 'unresolved' if a is None else 'correct' if a == y else 'wrong'
        for q in ('N', 'E'):
            for cell, saved in obs['paired'][g]['R_vs_' + q].items():
                r, c = cell.split('/')
                ids = [i for i in sel[g] if state(i, 'R') == r and state(i, q) == c]
                chk(g + '_R_vs_' + q + '_' + cell, saved == dict(n=len(ids), ids=ids))
        for cat in ('opacity', 'normal', 'not_normal_no_opacity'):
            ids = [i for i in sel[g] if gt[i]['category'] == cat]
            saved = obs['category_transitions'][g][cat]
            want = dict(n=len(ids), policies={q: dict(
                to_yes=sum(patients[i]['base']['K'] == 'no' and patients[i]['base'][q] == 'yes' for i in ids),
                to_no=sum(patients[i]['base']['K'] == 'yes' and patients[i]['base'][q] == 'no' for i in ids),
                unresolved=sum(patients[i]['base'][q] is None for i in ids)) for q in POL})
            chk(g + '_' + cat + '_all_transitions', saved == want)
        for c in 'NERT':
            raw = [recs[i, c] for i in sel[g]]
            resolved = [X.resolve('O', r['suffix_text_raw'], r['ended_eos']) for r in raw]
            sources = {src: sum(r['source'] == src for r in resolved) for src in {r['source'] for r in resolved}}
            reasons = {why: sum(r['source'] == 'unresolved' and r['reason'] == why for r in resolved)
                       for why in {r['reason'] for r in resolved if r['source'] == 'unresolved'}}
            fmt = rep['format'][g][c]
            chk(g + '_' + c + '_format_sources_eos_attempts', fmt['n'] == len(raw) and fmt['source'] == sources and
                fmt['unresolved_reasons'] == reasons and fmt['eos'] == sum(r['ended_eos'] for r in raw) and
                fmt['strict_valid'] == sum(S.strict('O', r['suffix_text_raw'], r['ended_eos'])[0] == 'valid' for r in raw) and
                fmt['retry'] == sum(len(r['attempts']) > 1 for r in raw))
    targets = [root / 'eval/report.json', root / 'eval/per_patient.json', root / 'eval/observations.json']
    targets += sorted((root / 'gen/MAIN').glob('gen_worker*.jsonl'))
    targets += [root / 'gen/MAIN/completion.json', root / 'protocol/MAIN.json', root / 'lock/eval_lock.json']
    result = dict(all_pass=all(c['passed'] for c in checks), n=len(checks), n_pass=sum(c['passed'] for c in checks),
                  checks=checks, independent=independent, decision=dec, verified_files={str(f): sha(f) for f in targets},
                  note='best 지표별 최선값은 동일 배정의 동시 실현 가능성을 보장하지 않는다.')
    with (root / 'eval/verify.json').open('x') as f:
        json.dump(result, f, indent=1)
    print(result['n_pass'], '/', result['n'])
    raise SystemExit(0 if result['all_pass'] else 1)


if __name__ == '__main__':
    main()
