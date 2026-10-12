"""iter_123: 독립 검산 (mr123_run/mr123_eval를 import하지 않음). 원시 worker jsonl·requests·selection_lock에서 BA/CI/전환/비용 재계산."""
import glob, json, re, sys, random
import numpy as np

stage = sys.argv[1]
G = f'results/iter_123/gen/{stage}/'
reqs = [json.loads(l) for l in open(G + 'requests.jsonl')]
recs = {}
for fn in glob.glob(G + 'worker_*.jsonl'):
    for l in open(fn):
        l = l.strip()
        if l:
            r = json.loads(l)
            assert r['id'] not in recs
            recs[r['id']] = r
assert set(recs) == {q['id'] for q in reqs}
lock = json.load(open('results/iter_123/data/selection_lock.json'))
lab_by_study = {m['study_uid']: m['label'] for m in lock['manifest']}

def state(text):
    ls = [l for l in text.split('\n') if l.strip()]
    if not ls:
        return 'INVALID'
    f = re.sub(r'[^A-Za-z ]', ' ', ls[0]).upper().split()
    hit = {w for w in f if w in ('PRESENT', 'ABSENT', 'UNCERTAIN')}
    return hit.pop() if len(hit) == 1 else 'INVALID'

pt = {}
for q in reqs:
    assert lab_by_study[q['study_uid']] == q['label']
    pt.setdefault(q['study_uid'], {'label': q['label'], 'batch': q['batch_id']})[q['cond']] = state(recs[q['id']]['text'])
for p in pt.values():
    a, b = p['P1'], p['P2']
    p['P'] = 'PRESENT' if 'PRESENT' in (a, b) else ('ABSENT' if a == b == 'ABSENT' else 'UNCERTAIN')
ids = sorted(pt)
lab = np.array([pt[i]['label'] == 'positive' for i in ids])
def corr(c):
    return np.array([(pt[i][c] == 'PRESENT') if pt[i]['label'] == 'positive' else (pt[i][c] == 'ABSENT') for i in ids])
res = {}
for c in ['C', 'W', 'P']:
    k = corr(c)
    res[c] = dict(sens=float(k[lab].mean()), spec=float(k[~lab].mean()), BA=float(0.5 * (k[lab].mean() + k[~lab].mean())),
                  n_present=sum(pt[i][c] == 'PRESENT' for i in ids), n_absent=sum(pt[i][c] == 'ABSENT' for i in ids))
rng = np.random.default_rng(122)
def boot(a, b):
    ka, kb = corr(a), corr(b)
    pos, neg = np.where(lab)[0], np.where(~lab)[0]
    ds = []
    for _ in range(10000):
        ip, ineg = rng.choice(pos, len(pos)), rng.choice(neg, len(neg))
        ds.append(0.5 * (ka[ip].mean() - kb[ip].mean() + ka[ineg].mean() - kb[ineg].mean()))
    return dict(diff=float(0.5 * (ka[lab].mean() - kb[lab].mean() + ka[~lab].mean() - kb[~lab].mean())), ci=[float(np.percentile(ds, 2.5)), float(np.percentile(ds, 97.5))])
res['P-W'], res['W-C'] = boot('P', 'W'), boot('W', 'C')
# 비용 (요청 합)
cost = {}
for c in ['C', 'W', 'P']:
    rs = [recs[q['id']] for q in reqs if (q['cond'] == c or (c == 'P' and q['cond'] in ('P1', 'P2')))]
    cost[c] = dict(n_requests=len(rs), sum_wall_s=sum(r['wall_s'] for r in rs), prompt_tokens=sum(r['prompt_tokens'] for r in rs),
                   output_tokens=sum(r['n_new'] for r in rs), mean_wall_per_patient_s=sum(r['wall_s'] for r in rs) / len(ids))
res['cost'] = cost
res['all_eos'] = all(r['eos'] for r in recs.values())
res['n'] = len(ids)
# 보고서 정답 span과 요청 prompt 비누출: prompt에 label/보고 문구 없음
res['prompt_leak'] = any(re.search(r'report|positive|negative label|batch', q['prompt'], re.I) for q in reqs)
json.dump(res, open(f'results/iter_123/tests/verify_{stage}.json', 'w'), indent=1)
print(json.dumps(res, indent=1))
