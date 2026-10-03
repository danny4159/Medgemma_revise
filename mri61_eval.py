"""iter_061 평가: 원시 답변에서 T/J/S_mean/V 및 paired cluster bootstrap. 사용: python mri61_eval.py REQ LABELS GENDIR OUT [PRIOR_LABELS_JSON]"""
import glob, json, sys, collections
import numpy as np
import mri61_spec as S
from mri61_run import read_jsonl

req, labels_p, gdir, out = sys.argv[1:5]
prior_p = sys.argv[5] if len(sys.argv) > 5 else labels_p
rows = {r['rid']: r for r in read_jsonl(req)}
labels = json.load(open(labels_p))
recs = {}
for f in glob.glob(f'{gdir}/worker*.jsonl'):
    for r in read_jsonl(f):
        assert r['rid'] not in recs, 'dup'
        recs[r['rid']] = r
assert set(recs) == set(rows), f'incomplete {len(recs)}/{len(rows)}'

# prior (D에서만): 가장 빈번한 정답 문자열
pl = json.load(open(prior_p))
cnt = collections.Counter(v['answer_text'] for v in pl.values())
top = sorted(cnt.items(), key=lambda kv: (-kv[1], S.sha(kv[0])))[0][0]


def final(rec):
    a = rec['attempts'][-1]
    return a


import mri61_parse as P
strict_valid = [0]
resp = {}  # (cluster, order, cond) -> dict
for rid, rec in recs.items():
    r = rows[rid]
    a = final(rec)
    letter = P.parse_v2(a['text'])
    strict_valid[0] += S.parse_answer(a['text']) is not None
    orig = S.letter_to_orig(letter, r['perm']) if letter else None
    gt = labels[r['cluster_id']]['gt_orig_index']
    resp[(r['cluster_id'], r['order'], r['cond'])] = {
        'orig': orig, 'correct': int(orig == gt) if orig is not None else 0, 'valid': orig is not None,
        'eos': a['ended_eos'], 'retried': len(rec['attempts']) > 1, 'wall': rec['wall_monotonic_s'],
        'in_tok': rec['n_input_tokens'], 'out_tok': sum(x['n_new'] for x in rec['attempts']),
        'gen_s': sum(x['runtime_s'] for x in rec['attempts'])}

per = {}
for cid, lab in labels.items():
    K, opts = lab['K'], lab['options']
    d = {'K': K, 'source': lab['source']}
    for order in 'FR':
        T = resp[(cid, order, 'T')]
        J = resp[(cid, order, 'J')]
        d[f'T_{order}'] = T['correct']; d[f'J_{order}'] = J['correct']
        if K > 1:
            Ss = [resp[(cid, order, f'S{i + 1}')] for i in range(K)]
            d[f'Smean_{order}'] = float(np.mean([s['correct'] for s in Ss]))
            votes = collections.Counter(s['orig'] for s in Ss if s['valid'])
            if votes:
                mx = max(votes.values())
                cands = [o for o, c in votes.items() if c == mx]
                pick = min(cands, key=lambda o: S.sha(opts[o]))
                d[f'V_{order}'] = int(pick == lab['gt_orig_index'])
            else:
                d[f'V_{order}'] = 0
            d[f'anyS_{order}'] = int(any(s['correct'] for s in Ss))  # 사후 oracle
        # prior
        pick = opts.index(top) if top in opts else min(range(5), key=lambda o: S.sha(opts[o]))
        d[f'prior_{order}'] = int(pick == lab['gt_orig_index'])
    per[cid] = {k: (np.mean([d[f'{k}_F'], d[f'{k}_R']]) if f'{k}_F' in d else None) for k in ('T', 'J', 'Smean', 'V', 'anyS', 'prior')}
    per[cid].update({'K': K, 'source': lab['source'],
                     'T_F': d['T_F'], 'T_R': d['T_R'], 'J_F': d['J_F'], 'J_R': d['J_R']})
    if K > 1:
        per[cid].update({'Smean_F': d['Smean_F'], 'Smean_R': d['Smean_R'], 'V_F': d['V_F'], 'V_R': d['V_R']})

rng = np.random.default_rng(61)


def boot(a, b, n=10000):
    a, b = np.asarray(a, float), np.asarray(b, float)
    diff = a - b
    idx = rng.integers(0, len(diff), (n, len(diff)))
    m = diff[idx].mean(1)
    return float(diff.mean()), [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]


multi = [c for c, p in per.items() if p['K'] > 1]
single = [c for c, p in per.items() if p['K'] == 1]
res = {'strict_v1_valid_rate': strict_valid[0] / len(recs), 'n_clusters': len(per), 'n_multi': len(multi), 'n_single': len(single), 'prior_string': top, 'prior_count': dict(cnt)}
if multi:
    for k in ('T', 'J', 'Smean', 'V', 'prior', 'anyS'):
        res[f'{k}_multi'] = float(np.mean([per[c][k] for c in multi]))
    for name, (x, y) in {'J-T': ('J', 'T'), 'V-T': ('V', 'T'), 'J-V': ('J', 'V'), 'J-Smean': ('J', 'Smean'),
                         'V-J': ('V', 'J'), 'Smean-J': ('Smean', 'J'), 'Smean-T': ('Smean', 'T')}.items():
        res[name] = boot([per[c][x] for c in multi], [per[c][y] for c in multi])
    # 순서별 방향
    for o in 'FR':
        res[f'order{o}'] = {k: float(np.mean([per[c][f'{k}_{o}'] for c in multi])) for k in ('T', 'J', 'Smean', 'V')}
    res['discordant_clusters'] = {'J_vs_T': sum(1 for c in multi if per[c]['J'] != per[c]['T']),
                                  'V_vs_T': sum(1 for c in multi if per[c]['V'] != per[c]['T'])}
    bysrc = collections.defaultdict(list)
    for c in multi:
        bysrc[per[c]['source']].append(c)
    res['by_source'] = {s: {'n': len(cs), **{k: float(np.mean([per[c][k] for c in cs])) for k in ('T', 'J', 'Smean', 'V')}}
                        for s, cs in bysrc.items()}
if single:
    res['single'] = {'n': len(single), 'T': float(np.mean([per[c]['T'] for c in single])),
                     'I': float(np.mean([per[c]['J'] for c in single])),
                     'I-T': boot([per[c]['J'] for c in single], [per[c]['T'] for c in single])}
conds = collections.defaultdict(lambda: collections.defaultdict(list))
for (cid, order, cond), v in resp.items():
    k = 'T' if cond == 'T' else 'J' if cond == 'J' else 'S'
    for f in ('valid', 'eos', 'retried', 'wall', 'in_tok', 'out_tok', 'gen_s'):
        conds[k][f].append(v[f])
res['cost_and_format'] = {k: {'n_requests': len(v['valid']), 'invalid_rate': 1 - float(np.mean(v['valid'])),
                              'eos_rate': float(np.mean(v['eos'])), 'retry_rate': float(np.mean(v['retried'])),
                              'sum_wall_s': float(np.sum(v['wall'])), 'sum_gen_s': float(np.sum(v['gen_s'])),
                              'sum_in_tok': int(np.sum(v['in_tok'])), 'sum_out_tok': int(np.sum(v['out_tok']))}
                          for k, v in conds.items()}
res['per_cluster'] = per
json.dump(res, open(out, 'w'), indent=1, default=float)
print({k: v for k, v in res.items() if k not in ('per_cluster', 'cost_and_format')})
print(res['cost_and_format'])
