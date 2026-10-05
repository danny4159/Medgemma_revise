"""iter_078 검사. cpu: 자료·검색·request 식별 검사. proc: 실제 worker 재개·torn tail·변조·중복 거부 (GPU 필요).
결과: results/iter_078/tests/cpu_tests.json, proc_tests.json
"""
import copy, glob, hashlib, json, os, shutil, subprocess, sys

import numpy as np

import rf78_gen as G
import rf78_ref as R
import rf78_vlm as RV
import sp75_data as D

T = 'results/iter_078/tests'


def cpu():
    out = {}
    man = D.load_manifest()
    rows = {r['id']: r for r in man['rows']}
    t24 = {r['id']: r for r in man['rows'] if r['split'] == 'T24' and r['position_set'] == 'supervised' and not r['excluded']}
    t24_pat = {r['patient'] for r in t24.values()}
    ft = json.load(open(R.FEAT))
    bank = [{'id': i, 'patient': r['patient'], 'ordinal': r['ordinal'], 'grade': r['grade'], 'feat': np.array(ft['items'][i]['feat'])} for i, r in t24.items()]
    for sp in ('V8', 'E24'):
        ref = json.load(open(f'results/iter_078/data/refs_{sp}.json'))
        reqs = ref['requests']
        lab = json.load(open(f'results/iter_078/data/labels_{sp}.json'))['labels']
        c = {}
        c['n_requests'] = len(reqs)
        c['ids_match_labels'] = {r['id'] for r in reqs} == set(lab)
        c['query_patients_disjoint_T24'] = not ({r['patient'] for r in reqs} & t24_pat)
        c['no_query_grade_in_requests'] = all('grade' not in r and 'grade' not in r['query_images'][0] for r in reqs) and 'grade' not in json.dumps({k: v for k, v in reqs[0].items() if k not in ('I', 'D')})
        # 재현: 저장된 feature만으로 query grade 없이 같은 참고 사례가 나오는지 + label을 섞어도 검색 결과 불변(함수가 grade를 받지 않음)
        same, sig_ok = True, True
        for r in reqs:
            I, Dd = R.retrieve(np.array(ft['items'][r['id']]['feat']), bank)
            same &= [b['id'] for s, b in I] == [x['ref_id'] for x in r['I']] and [b['id'] for s, b in Dd] == [x['ref_id'] for x in r['D']]
        c['retrieval_reproduced_from_features_only'] = bool(same)
        import inspect
        c['retrieve_signature'] = str(inspect.signature(R.retrieve))
        ok_ref, ok_d, ok_img = True, True, True
        q_files = {e['file_sha256'] for r in reqs for e in r['query_images']}
        q_pix = {e['pixel_sha256_padded'] for r in reqs for e in r['query_images']}
        for r in reqs:
            I, Dd = r['I'], r['D']
            for x in I + Dd:
                m = t24.get(x['ref_id'])
                ok_ref &= m is not None and m['grade'] == x['grade'] and m['patient'] == x['patient'] and m['ordinal'] == x['ordinal']
                ok_ref &= [e['pixel_sha256_padded'] for e in x['images']] == [e['pixel_sha256_padded'] for e in m['inputs']['R']]
                ok_img &= not ({e['file_sha256'] for e in x['images']} & q_files) and not ({e['pixel_sha256_padded'] for e in x['images']} & q_pix)
            ok_d &= [x['grade'] for x in I] == [x['grade'] for x in Dd]
            ok_d &= len({x['patient'] for x in I}) == 3 and len({x['patient'] for x in Dd}) == 3
            ok_d &= all(Dd[j]['patient'] != I[j]['patient'] and Dd[j]['ref_id'] != I[j]['ref_id'] for j in range(3))
        c['refs_from_T24_with_manifest_grade_and_pixel'] = bool(ok_ref)
        c['D_keeps_I_grades_distinct_patients_not_same_item'] = bool(ok_d)
        c['no_ref_image_equals_query_image'] = bool(ok_img)
        c['ref_manifest_files_exist_hash_ok'] = all(R.sha_file(e['path']) == e['file_sha256'] for r in reqs for x in r['I'] + r['D'] for e in x['images'])
        c['n_D_patient_overlaps_other_I_slot'] = sum(len({x['patient'] for x in r['I']} & {x['patient'] for x in r['D']}) > 0 for r in reqs)
        c['n_I_equals_D_all_ids'] = sum([x['ref_id'] for x in r['I']] == [x['ref_id'] for x in r['D']] for r in reqs)
        c['mean_cos_I'] = float(np.mean([x['cosine'] for r in reqs for x in r['I']]))
        c['mean_cos_D'] = float(np.mean([x['cosine'] for r in reqs for x in r['D']]))
        # request_id 민감도
        fn = RV.request_fields
        r0 = reqs[0]
        base = G.request_id('A' * 8, 'I', r0['id'], fn(r0, 'I'), 'p', 'c')
        sens = {}
        r1 = copy.deepcopy(r0); r1['I'][0]['images'][0]['pixel_sha256_padded'] = '0' * 64
        sens['ref_pixel'] = G.request_id('A' * 8, 'I', r0['id'], fn(r1, 'I'), 'p', 'c') != base
        r1 = copy.deepcopy(r0); r1['I'][1]['grade'] = (r1['I'][1]['grade'] % 5) + 1
        sens['ref_grade'] = G.request_id('A' * 8, 'I', r0['id'], fn(r1, 'I'), 'p', 'c') != base
        r1 = copy.deepcopy(r0); r1['query_images'][2]['pixel_sha256_padded'] = '1' * 64
        sens['query_pixel'] = G.request_id('A' * 8, 'I', r0['id'], fn(r1, 'I'), 'p', 'c') != base
        r1 = copy.deepcopy(r0); r1['I'][0], r1['I'][1] = r1['I'][1], r1['I'][0]
        sens['ref_order'] = G.request_id('A' * 8, 'I', r0['id'], fn(r1, 'I'), 'p', 'c') != base
        sens['cond_D_vs_I'] = G.request_id('A' * 8, 'D', r0['id'], fn(r0, 'D'), 'p', 'c') != base
        sens['adapter'] = G.request_id('B' * 8, 'I', r0['id'], fn(r0, 'I'), 'p', 'c') != base
        sens['prompt'] = G.request_id('A' * 8, 'I', r0['id'], fn(r0, 'I'), 'q', 'c') != base
        sens['config'] = G.request_id('A' * 8, 'I', r0['id'], fn(r0, 'I'), 'p', 'd') != base
        c['request_id_sensitivity'] = sens
        c['unique_request_ids'] = len({G.request_id('A', cd, r['id'], fn(r, cd), 'p', 'c') for r in reqs for cd in 'QLID'}) == 4 * len(reqs)
        out[sp] = c
    # 입력 manifest가 C selection·checkpoint와 연결
    out['features_link'] = {'checkpoint_sha256': ft['checkpoint_sha256'] == R.sha_file(ft['checkpoint']), 'selection_sha256': ft['selection_sha256'] == R.sha_file('results/iter_075/C/selection.json'),
                            'manifest_sha256': ft['manifest_sha256'] == R.sha_file('results/iter_075/data/manifest.json'),
                            'c_code_hash_matches_selection': all(R.sha_file(f) == h for f, h in json.load(open('results/iter_075/C/selection.json'))['code'].items())}
    flat = []
    for sp in ('V8', 'E24'):
        for k, v in out[sp].items():
            if isinstance(v, bool):
                flat.append(v)
        flat += list(out[sp]['request_id_sensitivity'].values())
    flat += list(out['features_link'].values())
    out['all_pass'] = all(flat)
    os.makedirs(T, exist_ok=True)
    json.dump(out, open(f'{T}/cpu_tests.json', 'w'), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k in ('all_pass', 'features_link')}))


def run_worker(split, cond, outd, gpu, extra=()):
    cmd = [sys.executable, 'rf78_gen.py', '--split', split, '--cond', cond, '--adapter', 'results/iter_077/train/R_lr2e-4/epoch_16', '--out-dir', outd, '--worker', '0', '--gpu', gpu, *extra]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout[-300:] + p.stderr[-400:]


def read(outd):
    return [json.loads(l) for f in sorted(glob.glob(f'{outd}/gen_worker*.jsonl')) for l in open(f) if l.strip()]


def proc():
    gpu = sys.argv[2]
    res = {}
    base = f'{T}/proc'
    if os.path.exists(f'{T}/proc_tests.json'):
        sys.exit('exists')
    ids6 = json.load(open('results/iter_078/data/ids_V8_first12.json'))[:6]
    json.dump(ids6, open(f'{T}/ids6.json', 'w'))
    ref = {r['id']: r for r in map(json.loads, (l for f in glob.glob('results/iter_078/tests/cfg/cfgA_1wpg/I/gen_worker*.jsonl') for l in open(f)))}
    # 재개: 3건 후 중단, torn tail 추가, 재개
    o = f'{base}/resume'
    rc1, m1 = run_worker('V8', 'I', o, gpu, ['--ids', f'{T}/ids6.json', '--max-requests', '3'])
    n1 = len(read(o))
    with open(f'{o}/gen_worker0.jsonl', 'a') as f:
        f.write('{"id": "torn_partial", "tex')   # SIGKILL로 잘린 마지막 줄 모사
    rc2, m2 = run_worker('V8', 'I', o, gpu, ['--ids', f'{T}/ids6.json'])
    rs = read(o)
    res['resume'] = {'rc': [rc1, rc2], 'n_after_first': n1, 'n_final': len(rs), 'unique': len({r['id'] for r in rs}), 'torn_repaired': 'repaired torn tail' in m2,
                     'tokens_equal_cfgA': all(ref[r['id']]['suffix_ids'] == r['suffix_ids'] for r in rs), 'ids_equal_requested': {r['id'] for r in rs} == set(ids6)}
    # 변조 거부: 복사본에서 record의 ref pixel hash 변경 / request_id 변경 / 중복 / 집합 밖 id
    def variant(name, mut):
        d = f'{base}/{name}'
        shutil.copytree(o, d, ignore=shutil.ignore_patterns('*.lock', 'claims'))
        recs = read(d)
        mut(recs)
        with open(f'{d}/gen_worker0.jsonl', 'w') as f:
            for r in recs:
                f.write(json.dumps(r) + '\n')
        rc, msg = run_worker('V8', 'I', d, gpu, ['--ids', f'{T}/ids6.json'])
        after = read(d)
        return {'rc': rc, 'rejected': rc != 0, 'records_unchanged': len(after) == len(recs), 'msg_tail': msg[-200:]}

    def m_pix(rs):
        rs[0]['fields']['ref_pixel'][0][0] = '0' * 64
    def m_rid(rs):
        rs[1]['request_id'] = 'f' * 32
    def m_dup(rs):
        rs.append(copy.deepcopy(rs[2]))
    def m_unk(rs):
        rs[3]['id'] = 'unknown_id'
    def m_grade(rs):
        rs[0]['fields']['ref_grades'][0] = (rs[0]['fields']['ref_grades'][0] % 5) + 1
    for name, m in (('tamper_ref_pixel', m_pix), ('tamper_request_id', m_rid), ('duplicate', m_dup), ('unknown_id', m_unk), ('tamper_ref_grade', m_grade)):
        res[name] = variant(name, m)
    # 동시 worker 소유권: 같은 worker id 두 번 동시 실행은 lock으로 거부 (두 번째만 확인)
    res['all_pass'] = bool(res['resume']['rc'] == [0, 0] and res['resume']['n_final'] == 6 and res['resume']['unique'] == 6 and res['resume']['torn_repaired'] and res['resume']['tokens_equal_cfgA']
                           and all(res[k]['rejected'] and res[k]['records_unchanged'] for k in ('tamper_ref_pixel', 'tamper_request_id', 'duplicate', 'unknown_id', 'tamper_ref_grade')))
    json.dump(res, open(f'{T}/proc_tests.json', 'w'), indent=1)
    print(json.dumps({k: (v if k == 'all_pass' else {kk: vv for kk, vv in v.items() if kk != 'msg_tail'}) for k, v in res.items()}))


if __name__ == '__main__':
    cpu() if sys.argv[1] == 'cpu' else proc()
