"""iter_075 독립 재계산: production metrics/eval을 import하지 않고 원시 출력에서 주지표와 paired bootstrap을 다시 계산한다.
(manifest의 grade와 원시 gen JSONL/예측 JSON만 사용; parser·metric·교환·prior를 별도 구현). 결과는 eval/independent_verify.json (존재하면 중단).
"""
import glob, hashlib, json, os, re, sys
import numpy as np

OUT = 'results/iter_075'
man = json.load(open(f'{OUT}/data/manifest.json'))
lock = json.load(open(f'{OUT}/eval/eval_lock.json'))
rep = json.load(open(f'{OUT}/eval/report.json'))
E = sorted([r for r in man['rows'] if r['split'] == 'E24' and not r['excluded']], key=lambda r: (int(r['patient']), r['ordinal']))
T = sorted([r for r in man['rows'] if r['split'] == 'T24' and r['position_set'] == 'supervised' and not r['excluded']], key=lambda r: (int(r['patient']), r['ordinal']))
grade = [r['grade'] for r in E]
held = [i for i, r in enumerate(E) if r['position_set'] == 'held']
sup = [i for i, r in enumerate(E) if r['position_set'] == 'supervised']


def parse(txt, ended):
    if not ended:
        return None
    t = txt.strip()
    if t.endswith('.'):
        t = t[:-1].rstrip()
    return int(t) if re.fullmatch(r'[1-5]', t) else None


def vlm_preds(d):
    recs = {}
    for f in glob.glob(d + '/gen_worker*.jsonl'):
        for ln in open(f):
            if ln.strip():
                r = json.loads(ln)
                assert r['id'] not in recs
                recs[r['id']] = r
    assert set(recs) == {r['id'] for r in E}, d
    return [parse(recs[r['id']]['text'], recs[r['id']]['ended_eos']) for r in E]


def jpreds(p):
    d = {x['id']: x['pred'] for x in json.load(open(p))['preds']}
    return [d[r['id']] for r in E]


def cs_mae(ix, pred):
    per = {g: [] for g in range(1, 6)}
    for i in ix:
        per[grade[i]].append(4.0 if pred[i] is None else abs(pred[i] - grade[i]))
    vals = [sum(v) / len(v) for v in per.values() if v]
    return sum(vals) / len(vals)


def median_of(dist):
    c = 0.0
    for g in range(1, 6):
        c += dist[g - 1]
        if c >= 0.5 - 1e-12:
            return g


def dist(rows):
    n = len(rows)
    return [sum(1 for r in rows if r['grade'] == g) / n for g in range(1, 6)]


systems = {n: vlm_preds(s['dir']) for n, s in lock['vlm'].items()}
for n, p in lock['json_systems'].items():
    systems[n] = jpreds(p)
od = {k: dist([r for r in T if r['ordinal'] == k]) for k in (1, 3, 5)}
od[2] = [(a + b) / 2 for a, b in zip(od[1], od[3])]
od[4] = [(a + b) / 2 for a, b in zip(od[3], od[5])]
systems['prior_ordinal'] = [median_of(od[r['ordinal']]) for r in E]
systems['prior_global'] = [median_of(dist(T))] * len(E)


def swapped(pred, ix):
    out = list(pred)
    by = {}
    for i in ix:
        by.setdefault(E[i]['ordinal'], []).append(i)
    for k, idx in by.items():
        idx = sorted(idx, key=lambda i: (hashlib.sha256(f'iter075-swap|{E[i]["patient"]}'.encode()).hexdigest(), E[i]['patient']))
        for j, i in enumerate(idx):
            out[i] = pred[idx[(j + 1) % len(idx)]]
    return out


res = {'systems': {}, 'max_abs_diff_vs_report': 0.0, 'bootstrap': {}}
for n, p in systems.items():
    v_h, v_s = cs_mae(held, p), cs_mae(sup, p)
    sw_h = cs_mae(held, swapped(p, held))
    res['systems'][n] = {'held': v_h, 'supervised': v_s, 'held_swap': sw_h}
    rv = rep['systems'][n]
    for a, b in ((v_h, rv['held']['class_std_mae']), (v_s, rv['supervised']['class_std_mae']), (sw_h, rv['held']['swap_class_std_mae'])):
        res['max_abs_diff_vs_report'] = max(res['max_abs_diff_vs_report'], abs(a - b))
# bootstrap: 환자 단위, seed 7501, 10000회 (held)
pids = sorted({E[i]['patient'] for i in held}, key=int)
by_p = {p: [i for i in held if E[i]['patient'] == p] for p in pids}


def boot(xa, xb, sub_ix):
    rng = np.random.default_rng(7501)
    pp = sorted({E[i]['patient'] for i in sub_ix}, key=int)
    byp = {p: [i for i in sub_ix if E[i]['patient'] == p] for p in pp}
    d = []
    for _ in range(10000):
        ch = rng.integers(0, len(pp), len(pp))
        ix = [i for c in ch for i in byp[pp[c]]]
        try:
            d.append(cs_mae(ix, xa) - cs_mae(ix, xb))
        except ZeroDivisionError:
            d.append(float('nan'))
    d = np.array(d)
    return {'point': cs_mae(sub_ix, xa) - cs_mae(sub_ix, xb), 'ci95': [float(np.nanpercentile(d, 2.5)), float(np.nanpercentile(d, 97.5))]}


for key, bt in rep['paired_bootstrap_patient_resampling'].items():
    if '_minus_swap' in key:
        n = key.replace('_minus_swap', '')
        xa, xb = systems[n], None
        # swap은 위치 집합 안에서 교환
        sw = list(systems[n])
        for ix in (held, sup):
            s_ = swapped(systems[n], ix)
            for i in ix:
                sw[i] = s_[i]
        xb = sw
    else:
        x, y = key.split('_minus_')
        xa, xb = systems[x], systems[y]
    for pname, ix in (('held', held), ('supervised', sup)):
        r = boot(xa, xb, ix)
        res['bootstrap'][f'{key}:{pname}'] = r
        res['max_abs_diff_vs_report'] = max(res['max_abs_diff_vs_report'], abs(r['point'] - bt[pname]['point']), abs(r['ci95'][0] - bt[pname]['ci95'][0]), abs(r['ci95'][1] - bt[pname]['ci95'][1]))
if os.path.exists(f'{OUT}/eval/independent_verify.json'):
    sys.exit('exists')
json.dump(res, open(f'{OUT}/eval/independent_verify.json', 'w'), indent=1)
print('max abs diff vs report', res['max_abs_diff_vs_report'])
