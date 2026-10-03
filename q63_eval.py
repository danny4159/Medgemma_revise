"""iter_063 평가: 원문(O, 기존 출력 재사용)·소견 삭제(R) × 텍스트(T)·공동 영상(J) 2×2, cluster 단위 paired.

L = A(O,T)-A(R,T), G = A(R,J)-A(R,T), I = G-[A(O,J)-A(O,T)]. 각 cluster는 두 선택지 순서의 정답률 평균.
bootstrap: cluster 재표본 seed63, 10,000회, 모든 비교에 동일 index. 1차 parser=parse_v2(변경 없음). --lenient 는 iter_062 사후 형식 민감도와 동일 정의의 보조 분석.
진입 시 검증: 신규 R protocol·verify seal·record 파일 hash·digest, 원문 출력의 기존 protocol/seal·요청 행 동일성·label 동일성.
사용: python q63_eval.py [--lenient] --out results/iter_063/eval/report.json
"""
import argparse, collections, glob, json, os, re
import numpy as np
import mri61_spec as S
import mri61_parse as P
import q63_run as Q

NB, SEED = 10000, 63
E_QA = [587, 658, 721, 740, 759, 782, 831, 1120, 1224, 1297]
LEN = re.compile(r'^\**\s*answer\s*:\s*\**\s*([A-E])\s*\**\.?$', re.I)


def parse_lenient(text):
    a = P.parse_v2(text)
    if a:
        return a
    ls = [l.strip() for l in text.strip().splitlines() if l.strip()]
    m = LEN.match(ls[-1]) if ls else None
    return m.group(1).upper() if m else None


def load_records(d):
    recs = {}
    for f in sorted(glob.glob(f'{d}/worker*.jsonl')):
        for r in Q.read_jsonl(f):
            assert r['rid'] not in recs, 'duplicate ' + r['rid']
            recs[r['rid']] = r
    return recs


def sealed(model, requests, labels, protocol, d):
    pdig = Q.check_protocol(model, requests, labels, protocol)
    ver = json.load(open(f'{d}/verify.json'))
    assert ver['n_problems'] == 0 and ver['protocol_digest'] == pdig, 'verify seal invalid'
    for f, h in ver['record_file_sha256'].items():
        assert Q.sha_file(f) == h, 'changed after seal ' + f
    recs = load_records(d)
    assert all(r['protocol_digest'] == pdig for r in recs.values())
    return recs


def correct_table(rows, recs, labels, parse):
    tab = {}
    for rid, r in rows.items():
        a = recs[rid]['attempts'][-1]
        letter = parse(a['text'])
        orig = S.letter_to_orig(letter, r['perm']) if letter else None
        gt = labels[r['cluster_id']]['gt_orig_index']
        tab[(r['cluster_id'], r['order'], r['cond'])] = {
            'orig': orig, 'valid': orig is not None, 'correct': int(orig == gt) if orig is not None else 0,
            'capped_final': not a['ended_eos'], 'retried': len(recs[rid]['attempts']) > 1,
            'out_tok': sum(x['n_new'] for x in recs[rid]['attempts'])}
    return tab


def boot_idx(n):
    return np.random.default_rng(SEED).integers(0, n, (NB, n))


def ci(v, idx):
    m = np.asarray(v, float)[idx].mean(1)
    return [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]


def run(a):
    parse = parse_lenient if a.lenient else P.parse_v2
    man = json.load(open(Q.MANIFEST))
    cl = man['info']['E10']['clusters']
    rowsR = {r['rid']: r for r in Q.read_jsonl(a.requests)}
    labR = json.load(open(a.labels))
    assert list(labR) == cl
    rowsO_all = {r['rid']: r for r in Q.read_jsonl('results/iter_062/data/E21_requests.jsonl')}
    labO = json.load(open('results/iter_062/data/E21_labels.json'))
    for c in cl:
        assert labO[c]['gt_orig_index'] == labR[c]['gt_orig_index'] and labO[c]['options'] == labR[c]['options']
    rowsO = {rid: r for rid, r in rowsO_all.items() if r['cluster_id'] in cl and r['cond'] in ('T', 'J')}
    assert len(rowsO) == 40
    idx = boot_idx(len(cl))
    res = {'n_clusters': len(cl), 'bootstrap': {'seed': SEED, 'n': NB, 'unit': 'cluster'}, 'parser': 'lenient' if a.lenient else 'parse_v2', 'models': {}}
    cfg = {'qwen': {'R': (a.qwen_dir, a.qwen_protocol), 'O': ('results/iter_062/gen_E21_qwen', 'results/iter_062/E21_protocol.json')},
           'medgemma': {'R': (a.medgemma_dir, a.medgemma_protocol), 'O': ('results/iter_061/gen_E24', 'results/iter_061/E24_protocol.json')}}
    for model, c in cfg.items():
        recsR = sealed(model, a.requests, a.labels, c['R'][1], c['R'][0])
        assert set(recsR) == set(rowsR)
        # 원문 출력: 기존 seal 검증(Qwen은 q62 protocol, MedGemma는 mri61 protocol)
        if model == 'qwen':
            import q62_run as Q62
            pd0 = Q62.check_protocol('results/iter_062/data/E21_requests.jsonl', 'results/iter_062/data/E21_labels.json', c['O'][1]) if False else None
            pO = json.load(open(c['O'][1]))
            ver = json.load(open(f"{c['O'][0]}/verify.json"))
            assert ver['n_problems'] == 0 and ver['protocol_digest'] == pO['digest']
            assert Q.sha_file('results/iter_062/data/E21_requests.jsonl') == pO['components']['requests']
            for f, h in ver['record_file_sha256'].items():
                assert Q.sha_file(f) == h
            recsO_all = load_records(c['O'][0])
            assert all(r['protocol_digest'] == pO['digest'] for r in recsO_all.values())
        else:
            pO = json.load(open(c['O'][1]))
            e24 = {r['rid']: r for r in Q.read_jsonl('results/iter_061/E24_requests.jsonl')}
            assert Q.sha_file('results/iter_061/E24_requests.jsonl') == pO['requests_sha256']
            ver = json.load(open(f"{c['O'][0]}/verify.json"))
            assert ver['n_problems'] == 0
            recsO_all = load_records(c['O'][0])
            assert all(r['protocol_digest'] == pO['digest'] for r in recsO_all.values())
            for rid, r in rowsO.items():
                assert e24[rid] == r, 'E21 row != E24 row'
        recsO = {rid: recsO_all[rid] for rid in rowsO}
        tO, tR = correct_table(rowsO, recsO, labO, parse), correct_table(rowsR, recsR, labR, parse)
        acc = {}
        for tag, tab in (('O', tO), ('R', tR)):
            for cond in ('T', 'J'):
                for o in 'FR':
                    for cid in cl:
                        acc[(tag, cond, o, cid)] = tab[(cid, o, cond)]['correct']

        def vec(tag, cond, o=None):
            f = lambda cid: acc[(tag, cond, 'F', cid)] if o == 'F' else acc[(tag, cond, 'R', cid)] if o == 'R' else (acc[(tag, cond, 'F', cid)] + acc[(tag, cond, 'R', cid)]) / 2
            return np.array([f(cid) for cid in cl], float)

        m = {}
        for name, o in (('both', None), ('orderF', 'F'), ('orderR', 'R')):
            OT, OJ, RT, RJ = vec('O', 'T', o), vec('O', 'J', o), vec('R', 'T', o), vec('R', 'J', o)
            L, G, I = OT - RT, RJ - RT, (RJ - RT) - (OJ - OT)
            m[name] = {'acc': {'O_T': float(OT.mean()), 'O_J': float(OJ.mean()), 'R_T': float(RT.mean()), 'R_J': float(RJ.mean())},
                       'L': {'est': float(L.mean()), 'ci95': ci(L, idx)}, 'G': {'est': float(G.mean()), 'ci95': ci(G, idx)},
                       'I': {'est': float(I.mean()), 'ci95': ci(I, idx)},
                       'O_J_minus_O_T': {'est': float((OJ - OT).mean()), 'ci95': ci(OJ - OT, idx)}}
        m['per_cluster'] = {cid: {f'{tag}_{cond}_{o}': acc[(tag, cond, o, cid)] for tag in 'OR' for cond in ('T', 'J') for o in 'FR'} for cid in cl}
        m['n_clusters_L_positive_G_positive'] = {'L>0': int(sum((vec('O', 'T') - vec('R', 'T')) > 0)), 'G>0': int(sum((vec('R', 'J') - vec('R', 'T')) > 0)),
                                                 'L<0': int(sum((vec('O', 'T') - vec('R', 'T')) < 0)), 'G<0': int(sum((vec('R', 'J') - vec('R', 'T')) < 0))}
        fmt = {}
        for tag, tab in (('O', tO), ('R', tR)):
            for cond in ('T', 'J'):
                v = [x for (cid, o, cd), x in tab.items() if cd == cond]
                fmt[f'{tag}_{cond}'] = {'n': len(v), 'invalid_rate': 1 - float(np.mean([x['valid'] for x in v])),
                                        'final_cap_hit_rate': float(np.mean([x['capped_final'] for x in v])),
                                        'retry_rate': float(np.mean([x['retried'] for x in v])), 'sum_out_tok': int(sum(x['out_tok'] for x in v))}
        m['format'] = fmt
        bysrc = collections.defaultdict(list)
        for cid in cl:
            bysrc[labR[cid]['source']].append(cid)
        m['by_source_descriptive'] = {s: {'n': len(cs), **{f'{tag}_{cond}': float(np.mean([(acc[(tag, cond, 'F', c_)] + acc[(tag, cond, 'R', c_)]) / 2 for c_ in cs]))
                                                          for tag in 'OR' for cond in ('T', 'J')}} for s, cs in bysrc.items()}
        # 사전 탐색 기준(L≥0.15, G≥0.15, I≥0.10, 두 순서 각각 L>0·G>0)
        b, F_, R_ = m['both'], m['orderF'], m['orderR']
        m['criteria'] = {'L_ge_0.15': b['L']['est'] >= 0.15, 'G_ge_0.15': b['G']['est'] >= 0.15, 'I_ge_0.10': b['I']['est'] >= 0.10,
                         'L_pos_both_orders': F_['L']['est'] > 0 and R_['L']['est'] > 0, 'G_pos_both_orders': F_['G']['est'] > 0 and R_['G']['est'] > 0}
        m['criteria']['exploratory_positive'] = all(m['criteria'].values())
        m['criteria']['text_dependence_only'] = m['criteria']['L_ge_0.15'] and not m['criteria']['G_ge_0.15']
        res['models'][model] = m
        print(model, {k: round(v, 3) for k, v in b['acc'].items()}, 'L', round(b['L']['est'], 3), b['L']['ci95'], 'G', round(b['G']['est'], 3), b['G']['ci95'], 'I', round(b['I']['est'], 3), b['I']['ci95'])
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    assert not os.path.exists(a.out), 'exists'
    json.dump(res, open(a.out, 'w'), indent=1)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--requests', default='results/iter_063/data/E10_requests.jsonl')
    ap.add_argument('--labels', default='results/iter_063/data/E10_labels.json')
    ap.add_argument('--qwen-dir', default='results/iter_063/gen_E10_qwen')
    ap.add_argument('--qwen-protocol', default='results/iter_063/E10_protocol_qwen.json')
    ap.add_argument('--medgemma-dir', default='results/iter_063/gen_E10_medgemma')
    ap.add_argument('--medgemma-protocol', default='results/iter_063/E10_protocol_medgemma.json')
    ap.add_argument('--lenient', action='store_true')
    ap.add_argument('--out', required=True)
    run(ap.parse_args())
