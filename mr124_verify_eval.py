"""iter_124 독립 검산(Qwen 탐색 출력 생성 이후 작성 — 사전 잠금 아님). mr124_eval/mr124_run/mr123_run을 import하지 않고 원시 JSONL·정답 표만으로 재계산.
usage: python mr124_verify_eval.py   # results/iter_124/eval/verify_independent.json (없을 때만)"""
import glob, json, os, re
import numpy as np

lk = json.load(open('results/iter_124/data/eligibility_lock.json'))
lab = {r['study_uid']: (r['label'], r['batch_id']) for r in lk['rows'] if r['eligible']}
req = [json.loads(l) for l in open('results/iter_124/gen/explore/requests.jsonl')]
q, m = {}, {}
for f in glob.glob('results/iter_124/gen/explore/main/worker*.jsonl'):
    for l in open(f):
        r = json.loads(l); q[r['study_uid']] = r
for f in glob.glob('results/iter_123/gen/explore/worker_m*.jsonl'):
    for l in open(f):
        r = json.loads(l)
        if r['cond'] == 'W':
            m[r['study_uid']] = r


def first_state(t):
    lines = [x for x in (t or '').strip().split('\n') if x.strip()]
    if not lines:
        return 'INVALID'
    f = re.sub(r'[^A-Za-z ]', ' ', lines[0])
    found = [s for s in ('PRESENT', 'ABSENT', 'UNCERTAIN') if re.search(r'\b' + s + r'\b', f, re.I)]
    return found[0] if len(found) == 1 else 'INVALID'


def ba(st):
    pos = [st[s] == 'PRESENT' for s in lab if lab[s][0] == 'positive']
    neg = [st[s] == 'ABSENT' for s in lab if lab[s][0] == 'negative']
    return (np.mean(pos) + np.mean(neg)) / 2, np.mean(pos), np.mean(neg)


assert set(q) == set(lab) == {r['study_uid'] for r in req} and len(req) == 23 and set(m) >= set(lab)
sq = {s: first_state(q[s]['text']) for s in lab}
sm = {s: first_state(m[s]['text']) for s in lab}
res = {'n': len(lab), 'qwen_states': {k: sum(v == k for v in sq.values()) for k in ('PRESENT', 'ABSENT', 'UNCERTAIN', 'INVALID')},
       'medgemma_states': {k: sum(v == k for v in sm.values()) for k in ('PRESENT', 'ABSENT', 'UNCERTAIN', 'INVALID')},
       'qwen_BA_sens_spec': [float(x) for x in ba(sq)], 'medgemma_BA_sens_spec': [float(x) for x in ba(sm)],
       'stored_state_matches_reparse_qwen': all(q[s]['state'] == sq[s] for s in lab), 'stored_state_matches_reparse_medgemma': all(m[s]['state'] == sm[s] for s in lab),
       'qwen_all_eos': all(q[s]['eos'] for s in lab), 'qwen_max_new_tokens_used': max(q[s]['n_new'] for s in lab),
       'qwen_explanations_sample': {s: q[s]['text'][:160] for s in list(lab)[:3]}}
rep = json.load(open('results/iter_124/eval/report.json'))
res['matches_report'] = (abs(rep['qwen']['BA'] - res['qwen_BA_sens_spec'][0]) < 1e-12 and abs(rep['medgemma_w']['BA'] - res['medgemma_BA_sens_spec'][0]) < 1e-12)
p = 'results/iter_124/eval/verify_independent.json'
assert not os.path.exists(p)
json.dump(res, open(p, 'w'), indent=1)
print(json.dumps(res, indent=1))
