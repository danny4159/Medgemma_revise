"""iter_062 평가: 동일 E21 manifest에서 MedGemma(기존 E24 출력 재사용)와 Qwen2.5-VL의 T/J/S_mean/V,
모델 내 paired cluster bootstrap과 모델 간 효과 차이. 원시 답변에서만 계산.

사용: python q62_eval.py --out results/iter_062/eval/report.json
진입 시 검증: Qwen protocol 재계산·verify seal 일치·records의 digest, MedGemma E24 protocol/records 연결, 요청 행 동일성.
bootstrap: 모든 비교에 동일한 cluster 재표본(seed 61, 10,000회, rng를 비교마다 새로 생성)을 사용한다.
"""
import argparse, collections, glob, json, os, sys
import numpy as np
import mri61_spec as S
import mri61_parse as P
import q62_run as Q

NB = 10000
SEED = 61
COMMON = ('T', 'J', 'Smean', 'V')


def load_records(d):
    recs = {}
    for f in sorted(glob.glob(f'{d}/worker*.jsonl')):
        for r in Q.read_jsonl(f):
            assert r['rid'] not in recs, 'duplicate rid ' + r['rid']
            recs[r['rid']] = r
    return recs


def attempt_text(rec):
    return rec['attempts'][-1]['text'] if 'text' in rec['attempts'][-1] else None


def resp_table(rows, recs, labels, cost=None):
    resp = {}
    for rid, r in rows.items():
        rec = recs[rid]
        a = rec['attempts'][-1]
        letter = P.parse_v2(a['text'])
        strict = S.parse_answer(a['text']) is not None
        orig = S.letter_to_orig(letter, r['perm']) if letter else None
        gt = labels[r['cluster_id']]['gt_orig_index']
        resp[(r['cluster_id'], r['order'], r['cond'])] = {
            'orig': orig, 'valid': orig is not None, 'strict': strict, 'correct': int(orig == gt) if orig is not None else 0,
            'eos': bool(a['ended_eos']), 'retried': len(rec['attempts']) > 1, 'capped_final': (not a['ended_eos']),
            'in_tok': rec['n_input_tokens'], 'out_tok': sum(x['n_new'] for x in rec['attempts']),
            'gen_s': sum(x['runtime_s'] for x in rec['attempts']),
            'wall': (cost or {}).get(rid, rec.get('wall_monotonic_s'))}
    return resp


def per_cluster(resp, labels):
    per = {}
    for cid, lab in labels.items():
        K, opts = lab['K'], lab['options']
        d = {'K': K, 'source': lab['source'], 'unstated': lab['unstated_findings']}
        for o in 'FR':
            d[f'T_{o}'] = resp[(cid, o, 'T')]['correct']
            d[f'J_{o}'] = resp[(cid, o, 'J')]['correct']
            Ss = [resp[(cid, o, f'S{i + 1}')] for i in range(K)]
            d[f'Smean_{o}'] = float(np.mean([s['correct'] for s in Ss]))
            votes = collections.Counter(s['orig'] for s in Ss if s['valid'])
            if votes:
                mx = max(votes.values())
                pick = min([k for k, c in votes.items() if c == mx], key=lambda k: S.sha(opts[k]))
                d[f'V_{o}'] = int(pick == lab['gt_orig_index'])
            else:
                d[f'V_{o}'] = 0
            d[f'anyS_{o}'] = int(any(s['correct'] for s in Ss))
        for k in COMMON + ('anyS',):
            d[k] = (d[f'{k}_F'] + d[f'{k}_R']) / 2
        per[cid] = d
    return per


def boot_idx(n):
    return np.random.default_rng(SEED).integers(0, n, (NB, n))


def ci(diff_vec, idx):
    m = np.asarray(diff_vec, float)[idx].mean(1)
    return [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]


def effects(per, cids, idx_all, order=None):
    """cids: 사용 cluster 순서. order=None은 두 순서 평균, 'F'/'R'은 해당 순서."""
    g = (lambda c, k: per[c][k]) if order is None else (lambda c, k: per[c][f'{k}_{order}'])
    v = {k: np.array([g(c, k) for c in cids], float) for k in COMMON}
    out = {k: float(v[k].mean()) for k in COMMON}
    for name, (x, y) in {'J-T': ('J', 'T'), 'V-T': ('V', 'T'), 'V-J': ('V', 'J'), 'Smean-J': ('Smean', 'J'),
                         'Smean-T': ('Smean', 'T')}.items():
        d = v[x] - v[y]
        out[name] = {'est': float(d.mean()), 'ci95': ci(d, idx_all)}
    return out, v


def run(a):
    rows = {r['rid']: r for r in Q.read_jsonl(a.requests)}
    labels = json.load(open(a.labels))
    # ---- Qwen: protocol·completion seal·records
    pdig = Q.check_protocol(a.requests, a.labels, a.qwen_protocol)
    ver = json.load(open(f'{a.qwen_dir}/verify.json'))
    assert ver['n_problems'] == 0 and ver['protocol_digest'] == pdig, 'qwen verify seal invalid'
    for f, h in ver['record_file_sha256'].items():
        assert Q.sha_file(f) == h, 'qwen record file changed after seal ' + f
    qrecs = load_records(a.qwen_dir)
    assert set(qrecs) == set(rows), f'qwen incomplete {len(qrecs)}/{len(rows)}'
    for r in qrecs.values():
        assert r['protocol_digest'] == pdig
    cost = {}
    for f in glob.glob(f'{a.qwen_dir}/cost_worker*.jsonl'):
        for c in Q.read_jsonl(f):
            cost[c['rid']] = c['total_read_to_flush_s']
    # ---- MedGemma E24 재사용: 요청 행 동일성 + protocol
    e24_rows = {r['rid']: r for r in Q.read_jsonl(a.medgemma_requests)}
    for rid, r in rows.items():
        assert e24_rows[rid] == r, 'E21 row differs from E24 row'
    mp = json.load(open(a.medgemma_protocol))
    assert Q.sha_file(a.medgemma_requests) == mp['requests_sha256'], 'E24 requests changed'
    mver = json.load(open(f'{a.medgemma_dir}/verify.json'))
    assert mver['n_problems'] == 0
    mrecs_all = load_records(a.medgemma_dir)
    mrecs = {rid: mrecs_all[rid] for rid in rows}
    for r in mrecs.values():
        assert r['protocol_digest'] == mp['digest']
    elig = json.load(open(a.manifest))['E21_clusters']
    cids = list(elig)
    assert cids == list(labels), 'cluster order'
    n = len(cids)
    idx = boot_idx(n)

    models = {'MedGemma': (mrecs, None), 'Qwen2.5-VL-7B': (qrecs, cost)}
    pers, res = {}, {'n_clusters': n, 'n_requests': len(rows), 'bootstrap': {'seed': SEED, 'n': NB, 'unit': 'cluster'},
                     'qwen_protocol_digest': pdig, 'medgemma_protocol_digest': mp['digest'], 'models': {}}
    vecs = {}
    for name, (recs, cs) in models.items():
        resp = resp_table(rows, recs, labels, cs)
        per = per_cluster(resp, labels)
        pers[name] = per
        m = {}
        m['all'], vecs[(name, None)] = effects(per, cids, idx)
        for o in 'FR':
            m[f'order{o}'], vecs[(name, o)] = effects(per, cids, idx, o)
        m['anyS_posthoc_oracle'] = float(np.mean([per[c]['anyS'] for c in cids]))
        m['prior_note'] = 'class prior는 이번 비교에서 사용하지 않음(질문별 선택지 순열 후 정답 prior는 D에서만 계산한 iter_061 방식)'
        # 하위집단 기술통계
        for gname, sel in (('unstated6', [c for c in cids if per[c]['unstated']]), ('stated15', [c for c in cids if not per[c]['unstated']])):
            m[gname] = {'n': len(sel), **{k: float(np.mean([per[c][k] for c in sel])) for k in COMMON},
                        'J-T': float(np.mean([per[c]['J'] - per[c]['T'] for c in sel])),
                        'V-T': float(np.mean([per[c]['V'] - per[c]['T'] for c in sel]))}
        bysrc = collections.defaultdict(list)
        for c in cids:
            bysrc[per[c]['source']].append(c)
        m['by_source'] = {s: {'n': len(cs), **{k: float(np.mean([per[c][k] for c in cs])) for k in COMMON}} for s, cs in bysrc.items()}
        byK = collections.defaultdict(list)
        for c in cids:
            byK[per[c]['K']].append(c)
        m['by_K'] = {str(k): {'n': len(cs), **{kk: float(np.mean([per[c][kk] for c in cs])) for kk in COMMON}} for k, cs in sorted(byK.items())}
        # 형식·비용
        cond = collections.defaultdict(lambda: collections.defaultdict(list))
        for (cid, o, cd), v in resp.items():
            k = 'T' if cd == 'T' else 'J' if cd == 'J' else 'S'
            for f in ('valid', 'strict', 'eos', 'retried', 'capped_final', 'in_tok', 'out_tok', 'gen_s', 'wall'):
                cond[k][f].append(v[f])
        m['format_and_cost'] = {k: {'n_requests': len(v['valid']), 'invalid_rate': 1 - float(np.mean(v['valid'])),
                                    'strict_v1_valid_rate': float(np.mean(v['strict'])), 'eos_rate': float(np.mean(v['eos'])),
                                    'retry_rate': float(np.mean(v['retried'])), 'final_cap_hit_rate': float(np.mean(v['capped_final'])),
                                    'sum_in_tok': int(np.sum(v['in_tok'])), 'sum_out_tok': int(np.sum(v['out_tok'])),
                                    'sum_gen_s': float(np.sum(v['gen_s'])),
                                    'sum_wall_s': float(np.sum([w for w in v['wall'] if w is not None])) if any(w is not None for w in v['wall']) else None}
                                for k, v in cond.items()}
        # 원 선택지 답변 불일치(두 순서의 유효 답이 서로 다른 원 선택지)
        disc = collections.defaultdict(list)
        for (cid, o, cd), v in resp.items():
            if o == 'F':
                w = resp[(cid, 'R', cd)]
                if v['valid'] and w['valid']:
                    disc['T' if cd == 'T' else 'J' if cd == 'J' else 'S'].append(int(v['orig'] != w['orig']))
        m['order_answer_disagreement'] = {k: {'n_pairs': len(v), 'rate': float(np.mean(v)) if v else None} for k, v in disc.items()}
        m['per_cluster_all'] = {c: {k: pers[name][c][k] for k in ('T_F', 'T_R', 'J_F', 'J_R', 'Smean_F', 'Smean_R', 'V_F', 'V_R', 'K', 'source')} for c in cids}
        res['models'][name] = m
    # ---- 모델 간 차이(같은 bootstrap index)
    cross = {}
    for tag, o in (('both_orders', None), ('orderF', 'F'), ('orderR', 'R')):
        vq, vm = vecs[('Qwen2.5-VL-7B', o)], vecs[('MedGemma', o)]
        for name, (x, y) in {'J-T': ('J', 'T'), 'V-T': ('V', 'T'), 'V-J': ('V', 'J')}.items():
            dq, dm = vq[x] - vq[y], vm[x] - vm[y]
            d = dq - dm
            cross[f'{tag}:(Qwen {name}) - (MedGemma {name})'] = {'est': float(d.mean()), 'ci95': ci(d, idx)}
        for k in ('T', 'J', 'V', 'Smean'):
            d = vq[k] - vm[k]
            cross[f'{tag}:Qwen {k} - MedGemma {k}'] = {'est': float(d.mean()), 'ci95': ci(d, idx)}
    res['cross_model'] = cross
    # ---- 사전 기준의 기계적 평가(해석은 보고서에서)
    crit = {}
    for name in models:
        mm = res['models'][name]['all']
        fo, ro = res['models'][name]['orderF'], res['models'][name]['orderR']
        crit[name] = {
            'JT_ge10_ciLow_gt0': mm['J-T']['est'] >= 0.10 and mm['J-T']['ci95'][0] > 0,
            'VT_ge10_ciLow_gt0': mm['V-T']['est'] >= 0.10 and mm['V-T']['ci95'][0] > 0,
            'JT_ci_upper_lt10': mm['J-T']['ci95'][1] < 0.10, 'VT_ci_upper_lt10': mm['V-T']['ci95'][1] < 0.10,
            'VJ_ge10_ciLow_gt0': mm['V-J']['est'] >= 0.10 and mm['V-J']['ci95'][0] > 0,
            'SmeanJ_ge10_ciLow_gt0': mm['Smean-J']['est'] >= 0.10 and mm['Smean-J']['ci95'][0] > 0,
            'VJ_same_sign_both_orders': (fo['V-J']['est'] > 0) == (ro['V-J']['est'] > 0) and fo['V-J']['est'] != 0 and ro['V-J']['est'] != 0,
            'SmeanJ_same_sign_both_orders': (fo['Smean-J']['est'] > 0) == (ro['Smean-J']['est'] > 0) and fo['Smean-J']['est'] != 0 and ro['Smean-J']['est'] != 0,
            'V_gt_T': mm['V'] > mm['T'], 'Smean_gt_T': mm['Smean'] > mm['T'],
            'VJ_ge5': mm['V-J']['est'] >= 0.05}
    qc = res['cross_model']
    crit['Qwen2.5-VL-7B']['model_specific_positive'] = bool(
        (crit['Qwen2.5-VL-7B']['JT_ge10_ciLow_gt0'] and qc['both_orders:(Qwen J-T) - (MedGemma J-T)']['est'] > 0 and qc['both_orders:(Qwen J-T) - (MedGemma J-T)']['ci95'][0] > 0) or
        (crit['Qwen2.5-VL-7B']['VT_ge10_ciLow_gt0'] and qc['both_orders:(Qwen V-T) - (MedGemma V-T)']['est'] > 0 and qc['both_orders:(Qwen V-T) - (MedGemma V-T)']['ci95'][0] > 0))
    crit['negative_both_models'] = bool(all(crit[m]['JT_ci_upper_lt10'] and crit[m]['VT_ci_upper_lt10'] for m in models))
    res['criteria_mechanical'] = crit
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(res, open(a.out, 'w'), indent=1, default=float)
    for name in models:
        m = res['models'][name]
        print(name, {k: round(m['all'][k], 4) for k in COMMON}, {k: (round(m['all'][k]['est'], 4), [round(x, 3) for x in m['all'][k]['ci95']]) for k in ('J-T', 'V-T', 'V-J', 'Smean-J')})
    print('criteria', json.dumps(crit))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--requests', default='results/iter_062/data/E21_requests.jsonl')
    ap.add_argument('--labels', default='results/iter_062/data/E21_labels.json')
    ap.add_argument('--manifest', default='results/iter_062/data/selection_manifest.json')
    ap.add_argument('--qwen-dir', default='results/iter_062/gen_E21_qwen')
    ap.add_argument('--qwen-protocol', default='results/iter_062/E21_protocol.json')
    ap.add_argument('--medgemma-dir', default='results/iter_061/gen_E24')
    ap.add_argument('--medgemma-protocol', default='results/iter_061/E24_protocol.json')
    ap.add_argument('--medgemma-requests', default='results/iter_061/E24_requests.jsonl')
    ap.add_argument('--out', default='results/iter_062/eval/report.json')
    run(ap.parse_args())
