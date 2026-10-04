"""iter_065 CPU 검사: 자료 규칙(정답·coverage·J 교차·E12 순서·prompt 누출), 평가 진입 변조 거부, 정책 선택 규칙, 합성 count 정합.
사용: python m65_test.py OUT.json  (OUT은 존재하면 거부)"""
import json, os, shutil, sys, tempfile
import numpy as np
import m65_data as D
import m65_run as R
import m65_eval as E

RES = []


def chk(name, ok, info=None):
    RES.append({'name': name, 'ok': bool(ok), 'info': info})
    print(('PASS ' if ok else 'FAIL ') + name)


def expect_exit(fn):
    try:
        fn()
    except (SystemExit, AssertionError):
        return True
    return False


def main(out):
    assert not os.path.exists(out)
    # 1. slab_labels: 구간 정답 vs 관측 z coverage
    m = np.zeros((4, 4, 20), np.uint8)
    m[1, 1, 12] = 3   # E는 z=12에만
    m[2, 2, 5] = 1    # W는 z=5,12
    lab = D.slab_labels(m, 0, 19, [0, 5, 10, 15])
    chk('W present, E present but uncovered', lab['W'] and lab['E'] and lab['cov_W'] and not lab['cov_E'], lab)
    lab2 = D.slab_labels(m, 13, 19, [13, 15, 19])
    chk('empty slab -> ABSENT for both', not lab2['W'] and not lab2['E'])
    m2 = np.zeros((4, 4, 10), np.uint8); m2[0, 0, 3] = 2
    l3 = D.slab_labels(m2, 0, 9, [3])
    chk('label2 (non-enhancing) counts as W but not E', l3['W'] and not l3['E'])
    # 2. 요청: J 교차·W/E 동일 영상·prompt
    items = [{'case': 'X', 'slab': 0, 'F': [f'f{i}' for i in range(8)], 'T': [f't{i}' for i in range(8)]}]
    reqs = D.build_requests(items)
    by = {(r['q'], r['cond']): r for r in reqs}
    chk('6 requests per slab', len(reqs) == 6)
    chk('J interleaves F,T per z', by[('W', 'J')]['images'] == [x for i in range(8) for x in (f'f{i}', f't{i}')])
    chk('W/E same images per cond', all(by[('W', c)]['images'] == by[('E', c)]['images'] for c in 'FTJ'))
    chk('prompt has no case/GT leak', all('X__' not in r['prompt'] and 'BRATS' not in r['prompt'] for r in reqs))
    chk('prompt target differs by question', by[('W', 'F')]['prompt'] != by[('E', 'F')]['prompt'] and 'contrast-enhancing' in by[('E', 'T')]['prompt'])
    # 3. E12 순서 결정성 (실제 cases)
    ch = json.load(open(f"{D.SRC}/cases.json"))['chosen']
    e = [c['case'] for c in ch if c['split'] == 'E']
    o1, o2 = D.e_order(e), D.e_order(list(reversed(e)))
    chk('E order deterministic & permutation-invariant', o1 == o2 and sorted(o1) == sorted(e) and len(e) == 48)
    chk('E12/E36 disjoint cover E48', set(c['case'] for c in D.split_cases('E12')).isdisjoint(c['case'] for c in D.split_cases('E36'))
        and len(D.split_cases('E12')) == 12 and len(D.split_cases('E36')) == 36)
    # 4. 실제 생성 자료 정합: requests/labels/manifest 일관 (D, E12, E36)
    for sp in ('D', 'E12', 'E36'):
        reqs = R.read_jsonl(f'results/iter_065/data/requests_{sp}.jsonl')
        labs = json.load(open(f'results/iter_065/data/labels_{sp}.json'))
        tm = json.load(open(f'results/iter_065/data/target_manifest_{sp}.json'))['slabs']
        tmb = {(t['case'], t['slab']): t for t in tm}
        ok = set(r['rid'] for r in reqs) == set(labs) and len(reqs) == len(set(r['rid'] for r in reqs))
        for r in reqs:
            t = tmb[(r['case'], r['slab'])]
            ok &= labs[r['rid']]['answer'] == ('PRESENT' if t[r['q']] else 'ABSENT')
            ok &= labs[r['rid']]['coverage'] == t['cov_' + r['q']]
            ok &= [R.sha_file(p) for p in r['images']] == ([x for pr in zip(t['F_png_sha256'], t['T_png_sha256']) for x in pr] if r['cond'] == 'J'
                                                           else t[r['cond'] + '_png_sha256'])
        chk(f'{sp}: requests/labels/manifest/png hash consistent ({len(reqs)} requests)', ok)
    # 5. 평가기 count / BA 합성
    cn = {q: {c: np.zeros((2, 4)) for c in 'FTJ'} for q in E.QS}
    cn['W']['F'][:] = [[3, 1, 2, 2], [1, 1, 3, 1]]    # tp4,fn2,tn5,fp3 -> BA=.5*(4/6+5/8)
    x = E.policy_macro(cn, 'F/F', None)
    chk('BA formula', abs(E.ba_from(cn['W']['F'].sum(0)) - 0.5 * (4 / 6 + 5 / 8)) < 1e-12)
    cn2 = {q: {c: np.zeros((2, 4)) for c in 'FTJ'} for q in E.QS}
    cn2['W']['F'][0] = [1, 0, 1, 0]; cn2['E']['T'][0] = [1, 0, 1, 0]
    chk('class-missing resample -> nan', np.isnan(E.policy_macro(cn2, 'F/T', np.array([[1]]))[0]))
    # 6. 평가/실행 진입 변조 거부 (protocol 연결)
    td = tempfile.mkdtemp()
    P = 'results/iter_065/protocol/medgemma_D_v2.json'
    rq, lb, tm_ = 'results/iter_065/data/requests_D.jsonl', 'results/iter_065/data/labels_D.json', 'results/iter_065/data/target_manifest_D.json'
    chk('protocol accepts untouched inputs', R.check_protocol('medgemma', rq, lb, tm_, P) is not None)
    for nm, src in (('labels', lb), ('requests', rq), ('manifest', tm_)):
        tmp = os.path.join(td, nm)
        shutil.copy(src, tmp)
        with open(tmp, 'ab') as f:
            f.write(b' ')
        args = {'labels': lb, 'requests': rq, 'manifest': tm_}
        args[nm] = tmp
        chk(f'tampered {nm} rejected', expect_exit(lambda: R.check_protocol('medgemma', args['requests'], args['labels'], args['manifest'], P)))
    chk('wrong model protocol rejected', expect_exit(lambda: R.check_protocol('qwen', rq, lb, tm_, P)))
    # 7. 선택 규칙: 동률이면 비용, 다음 사전식
    pol = {'F/F': {'macro_BA': .7, 'cost_s': 5}, 'T/T': {'macro_BA': .7, 'cost_s': 4}, 'F/T': {'macro_BA': .6, 'cost_s': 4}, 'T/F': {'macro_BA': .6, 'cost_s': 4}}
    def pick(S):
        return sorted(S, key=lambda p: (-round(pol[p]['macro_BA'], 12), pol[p]['cost_s'], S.index(p)))[0]
    chk('tie -> lower cost; full tie -> lexicographic', pick(E.B_SET) == 'T/T' and pick(E.Q_SET) == 'F/T')
    nf = sum(not r['ok'] for r in RES)
    json.dump({'n': len(RES), 'fails': nf, 'results': RES}, open(out, 'w'), indent=1)
    print('fails', nf, 'of', len(RES))
    sys.exit(1 if nf else 0)


if __name__ == '__main__':
    main(sys.argv[1])
