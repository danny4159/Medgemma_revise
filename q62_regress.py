"""iter_062 회귀: iter_061 E24의 불변 provenance와 점수 보존 확인. 원 결과는 수정하지 않는다.
- mri61_run.proto_digest(E24 requests) == E24_protocol digest (원 코드·요청·영상 hash 불변)
- E24 verify.json 문제 0, 264 records
- 원시 E24 출력에서 mri61_eval과 동일 방식으로 T/J/V를 재계산해 저장 report와 일치
사용: python q62_regress.py
"""
import glob, json, os, sys
import numpy as np
import mri61_run as R61
import mri61_spec as S
import mri61_parse as P

P61 = 'results/iter_061'
OUT = 'results/iter_062/tests/regress_E24.json'
os.makedirs(os.path.dirname(OUT), exist_ok=True)
prot = json.load(open(f'{P61}/E24_protocol.json'))
res = {'protocol_digest_recomputed': R61.proto_digest(f'{P61}/E24_requests.jsonl'), 'protocol_digest_saved': prot['digest']}
res['protocol_ok'] = res['protocol_digest_recomputed'] == res['protocol_digest_saved']
ver = json.load(open(f'{P61}/gen_E24/verify.json'))
res['verify_n_records'], res['verify_n_problems'] = ver['n_records'], ver['n_problems']
rows = {r['rid']: r for r in R61.read_jsonl(f'{P61}/E24_requests.jsonl')}
labels = json.load(open(f'{P61}/E24_requests_labels.json'))
recs = {}
for f in glob.glob(f'{P61}/gen_E24/worker*.jsonl'):
    for r in R61.read_jsonl(f):
        recs[r['rid']] = r
corr = {}
for rid, r in rows.items():
    L = P.parse_v2(recs[rid]['attempts'][-1]['text'])
    o = S.letter_to_orig(L, r['perm']) if L else None
    corr[(r['cluster_id'], r['order'], r['cond'])] = (o, int(o == labels[r['cluster_id']]['gt_orig_index']) if o is not None else 0)
Ts, Js, Vs = [], [], []
for cid, lab in labels.items():
    t = np.mean([corr[(cid, o, 'T')][1] for o in 'FR'])
    j = np.mean([corr[(cid, o, 'J')][1] for o in 'FR'])
    vv = []
    for o in 'FR':
        votes = {}
        for i in range(lab['K']):
            x = corr[(cid, o, f'S{i + 1}')][0]
            if x is not None:
                votes[x] = votes.get(x, 0) + 1
        if votes:
            m = max(votes.values())
            pick = min([k for k, c in votes.items() if c == m], key=lambda k: S.sha(lab['options'][k]))
            vv.append(int(pick == lab['gt_orig_index']))
        else:
            vv.append(0)
    Ts.append(t); Js.append(j); Vs.append(np.mean(vv))
saved = json.load(open(f'{P61}/E24_report.json'))
res.update({'T_recomputed': float(np.mean(Ts)), 'J_recomputed': float(np.mean(Js)), 'V_recomputed': float(np.mean(Vs)),
            'T_saved': saved['T_multi'], 'J_saved': saved['J_multi'], 'V_saved': saved['V_multi']})
res['scores_ok'] = all(abs(res[k + '_recomputed'] - res[k + '_saved']) < 1e-12 for k in 'TJV')
json.dump(res, open(OUT, 'w'), indent=1)
print(res)
sys.exit(0 if res['protocol_ok'] and res['scores_ok'] and res['verify_n_problems'] == 0 else 1)
