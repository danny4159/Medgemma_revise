"""iter_065 독립 재계산: 원시 worker*.jsonl + labels에서 m65_eval을 import하지 않고 per-question×cond BA, 정책 macro BA, 점추정 차이,
case bootstrap(같은 seed·NumPy 방식이 아닌 별도 구현: 정수 index를 case 단위 Python 루프로 뽑음) CI 일부를 재현하고 report와 대조.
사용: python m65_verify_eval.py REPORT.json GEN_DIR LABELS OUT.json"""
import glob, json, re, sys, os
import numpy as np


def parse(t):
    t = t.replace('<end_of_turn>', '').strip()
    t = re.sub(r'[\s.!?,;:]+$', '', t).strip().upper()
    return {'PRESENT': 1, 'ABSENT': 0}.get(t)


def main(rep_p, gdir, lab_p, out):
    assert not os.path.exists(out)
    rep, lab = json.load(open(rep_p)), json.load(open(lab_p))
    rows = {}
    for f in sorted(glob.glob(f'{gdir}/worker*.jsonl')):
        for l in open(f):
            if l.strip():
                r = json.loads(l)
                assert r['rid'] not in rows
                rows[r['rid']] = r
    assert set(rows) == set(lab)
    cells = {}
    for rid, r in rows.items():
        L = lab[rid]
        p = parse(r['attempts'][-1]['text'])
        gt = 1 if L['answer'] == 'PRESENT' else 0
        k = (L['q'], L['cond'])
        cells.setdefault(k, {}).setdefault(L['case'], []).append((gt, p))

    def ba(k, cases):
        tp = fn = tn = fp = 0
        for c in cases:
            for gt, p in cells[k][c]:
                if gt == 1:
                    tp += p == 1; fn += p != 1
                else:
                    tn += p == 0; fp += p != 0
        return None if (tp + fn == 0 or tn + fp == 0) else 0.5 * (tp / (tp + fn) + tn / (tn + fp))
    cases = sorted({c for k in cells for c in cells[k]})
    bad = []
    for q in 'WE':
        for c in 'FTJ':
            v = ba((q, c), cases)
            if abs(v - rep['per_question_cond'][f'{q}_{c}']['BA']) > 1e-12:
                bad.append(('BA', q, c, v))
    pols = {'F/F': 'FF', 'F/T': 'FT', 'T/F': 'TF', 'T/T': 'TT', 'J/J': 'JJ'}
    for p, (cw, ce) in pols.items():
        m = 0.5 * (ba(('W', cw), cases) + ba(('E', ce), cases))
        if abs(m - rep['policies'][p]['macro_BA']) > 1e-12:
            bad.append(('macro', p, m))
    sel = rep['selection']
    sl = lambda p: tuple(p.split('/'))

    def macro(p, cs):
        a, b = ba(('W', sl(p)[0]), cs), ba(('E', sl(p)[1]), cs)
        return None if a is None or b is None else 0.5 * (a + b)
    pt = macro(sel['Q'], cases) - macro(sel['B'], cases)
    if abs(pt - rep['diffs']['Q-B_macro']['point']) > 1e-12:
        bad.append(('Q-B point', pt))
    # 별도 bootstrap (Python RandomState, 2,000 rep; 구현 독립성 확인용이며 CI는 근사 대조)
    rs = np.random.RandomState(65)
    ds = []
    for _ in range(2000):
        cs = [cases[i] for i in rs.randint(0, len(cases), len(cases))]
        a, b = macro(sel['Q'], cs), macro(sel['B'], cs)
        if a is not None and b is not None:
            ds.append(a - b)
    ci = [float(np.percentile(ds, 2.5)), float(np.percentile(ds, 97.5))]
    ref = rep['diffs']['Q-B_macro']['ci95']
    ci_close = max(abs(ci[0] - ref[0]), abs(ci[1] - ref[1])) < 0.03
    res = {'n_records': len(rows), 'mismatches': bad, 'Q-B_point_recomputed': pt, 'Q-B_ci_independent_2000rep': ci,
           'Q-B_ci_report': ref, 'ci_within_0.03': bool(ci_close)}
    json.dump(res, open(out, 'w'), indent=1)
    print(res)
    sys.exit(1 if bad or not ci_close else 0)


if __name__ == '__main__':
    main(*sys.argv[1:5])
