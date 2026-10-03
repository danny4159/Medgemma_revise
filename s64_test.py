"""iter_064 검사. cpu: 합성 자료·parser·JSONL 복구·통계. runtime: D(MedGemma)에서 저장 경계 강제 종료·torn tail·재개·동시 worker·protocol/원천 변조 거부.
사용: python s64_test.py cpu | runtime <gpu>
결과: results/iter_064/tests/{cpu,runtime}_tests.json (이미 있으면 거부)"""
import json, os, shutil, subprocess, sys, tempfile
import numpy as np
import s64_data as S, s64_run as R

OUT = 'results/iter_064/tests'
res = {'checks': [], 'fails': 0}


def chk(name, ok, **kw):
    res['checks'].append({'name': name, 'ok': bool(ok), **kw})
    if not ok:
        res['fails'] += 1


def cpu():
    # --- select_targets 합성
    fl = np.zeros((10, 10, 6), np.float32); mk = np.zeros((10, 10, 6), np.uint8)
    for z, n in enumerate([0, 5, 20, 20, 0, 1]):
        fl[:n, 0, z] = 1.0
    fl[:3, :3, 0] = 1; fl[:2, :2, 4] = 1  # nz(z0)=9+..., 비-mask slice z0/z4
    mk[:4, 0, 2] = 1; mk[:4, 0, 3] = 1; mk[0, 0, 1] = 1
    P, N, inf = S.select_targets(fl, mk)
    nz = [int((fl[:, :, k] != 0).sum()) for k in range(6)]
    chk('P tie -> smaller z', P == 2 and inf['area_P'] == 4, P=P)
    zero = [k for k in range(6) if k not in (1, 2, 3)]
    chk('N max-nonzero among mask-free', N == max(zero, key=lambda k: (nz[k], -k)) and inf['area_N'] == 0, N=N, nz=nz)
    fl2 = fl.copy(); P2, N2, _ = S.select_targets(fl2, np.zeros_like(mk))
    chk('no mask -> P None (ineligible)', P2 is None and N2 is not None)
    P3, N3, _ = S.select_targets(fl, np.ones_like(mk))
    chk('all slices annotated -> N None (ineligible)', N3 is None and P3 is not None)
    # --- 요청 구성
    rows = [{'case': 'c1', 'P': {'png': 'p.png', 'z': 1}, 'N': {'png': 'n.png', 'z': 2}}]
    reqs, lab = S.build_requests(rows)
    by = {r['rid']: r for r in reqs}
    chk('10 requests/case', len(reqs) == 10 and len(lab) == 10)
    chk('S single', by['c1__P__S']['images'] == ['p.png'] and by['c1__P__S']['k'] == 1)
    chk('R dup + k', by['c1__P__R2']['images'] == ['p.png', 'p.png'] and by['c1__P__R2']['k'] == 2 and by['c1__N__R1']['images'] == ['n.png', 'n.png'])
    chk('C order target first/second', by['c1__P__C1']['images'] == ['p.png', 'n.png'] and by['c1__P__C2']['images'] == ['n.png', 'p.png']
        and by['c1__N__C1']['images'] == ['n.png', 'p.png'] and by['c1__N__C2']['images'] == ['p.png', 'n.png'])
    chk('target at position k always', all(r['images'][r['k'] - 1] == ('p.png' if r['target'] == 'P' else 'n.png') for r in reqs))
    chk('labels P/N', lab['c1__P__S']['answer'] == 'PRESENT' and lab['c1__N__C2']['answer'] == 'ABSENT')
    chk('prompt has no case/path/answer', all('c1' not in r['prompt'] and 'png' not in r['prompt'] for r in reqs))
    # --- parser
    import msd56_run as M
    P_ = M.parse_answer
    chk('parser valid', P_('PRESENT') == 'PRESENT' and P_(' absent. ') == 'ABSENT' and P_('Absent.') == 'ABSENT')
    chk('parser invalid', P_('PRESENT or ABSENT') is None and P_('The lesion is PRESENT') is None and P_('') is None and P_('I cannot') is None)
    # --- JSONL
    d = tempfile.mkdtemp()
    p = f'{d}/w.jsonl'
    open(p, 'w').write('{"rid":"a"}\n{"rid":"b"}\n{"rid":"c"')
    chk('read ignores torn tail', [r['rid'] for r in R.read_jsonl(p)] == ['a', 'b'])
    dropped = R.repair_tail(p)
    chk('repair removes only torn tail + keeps copy', dropped == len('{"rid":"c"') and open(p).read() == '{"rid":"a"}\n{"rid":"b"}\n'
        and any('.corrupt_' in f for f in os.listdir(d)))
    open(p, 'w').write('{"rid":"a"}\n{"rid" BAD}\n{"rid":"c"}\n')
    try:
        R.repair_tail(p); ok = False
    except json.JSONDecodeError:
        ok = True
    chk('repair rejects mid-file corruption', ok and open(p).read().startswith('{"rid":"a"}\n{"rid" BAD}'))
    try:
        R.read_jsonl(p); ok = False
    except json.JSONDecodeError:
        ok = True
    chk('read rejects mid-file corruption', ok)
    # --- 평가기(paired bootstrap) 합성
    import s64_eval as E
    chk('balanced acc', abs(E.ba(np.array([1, 1, 0, 0]), np.array([1, 0, 0, 0])) - 0.75) < 1e-12)
    json.dump(res, open(f'{OUT}/cpu_tests.json', 'w'), indent=1)
    print('cpu fails', res['fails'], 'of', len(res['checks']))


def sh(cmd, env=None, check=False):
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def runtime(gpu):
    D = 'results/iter_064/D'
    base = ['python', 's64_run.py']
    common = ['--requests', f'results/iter_064/data/requests_D.jsonl', '--labels', 'results/iter_064/data/labels_D.json',
              '--target-manifest', 'results/iter_064/data/target_manifest_D.json']
    prot = f'{D}/protocol_medgemma_v2.json'
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(gpu))
    ref = {}
    for l in open(f'{D}/gen_A_medgemma/worker0.jsonl'):
        r = json.loads(l); ref[r['rid']] = r['attempts'][-1]['suffix_ids']
    out = f'{D}/gen_resume_medgemma_v2'
    assert not os.path.exists(out), 'exists'
    # 1) 3건 저장 직후 강제 종료
    r1 = sh(base + ['worker', '--model', 'medgemma', *common, '--protocol', prot, '--out-dir', out, '--worker', '0', '--die-after-write', '3'], env)
    chk('die-after-write exit 9', r1.returncode == 9, rc=r1.returncode)
    n1 = len(R.read_jsonl(f'{out}/worker0.jsonl'))
    chk('3 records saved before kill', n1 == 3, n=n1)
    # 2) 재시작 -> 2건 더 쓰고 torn tail로 종료 (stale claim 회수 포함)
    r2 = sh(base + ['worker', '--model', 'medgemma', *common, '--protocol', prot, '--out-dir', out, '--worker', '0', '--torn-after', '2'], env)
    raw = open(f'{out}/worker0.jsonl', 'rb').read()
    chk('torn tail present', r2.returncode == 9 and not raw.endswith(b'\n'), rc=r2.returncode)
    # 3) 동시 worker 2개로 재개 완료(복구 + claim 경합)
    jobs = [{'model': 'medgemma', 'gpu': int(gpu), 'workers': 2, 'protocol': prot, 'out_dir': out, 'tech': f'{D}/tech_medgemma_v2.json', 'peak_gb': 9}]
    json.dump(jobs, open(f'{D}/jobs_resume.json', 'w'))
    r3 = sh(base + ['launch', *common, '--jobs', f'{D}/jobs_resume.json'], env)
    chk('relaunch exit 0', r3.returncode == 0, tail=(r3.stdout + r3.stderr)[-300:])
    recs = []
    import glob
    for f in glob.glob(f'{out}/worker*.jsonl'):
        recs += R.read_jsonl(f)
    ids = [r['rid'] for r in recs]
    chk('no missing/duplicate after resume', len(ids) == 60 and len(set(ids)) == 60, n=len(ids), uniq=len(set(ids)))
    chk('torn bytes preserved as .corrupt_', len(glob.glob(f'{out}/worker0.jsonl.corrupt_*')) == 1)
    mism = [r['rid'] for r in recs if r['attempts'][-1]['suffix_ids'] != ref[r['rid']]]
    chk('suffix tokens == uninterrupted run', not mism, mismatches=len(mism))
    v = sh(base + ['verify', '--model', 'medgemma', *common, '--protocol', prot, '--out-dir', out], env)
    chk('verify passes after resume', v.returncode == 0, tail=v.stdout[-200:])
    # 4) 변조 거부: 요청 파일 사본(1줄 변경)·원천 파일 변조 모사(사본 protocol의 source hash 변경)
    t = tempfile.mkdtemp()
    rq = f'{t}/req.jsonl'
    lines = open(common[1]).read().splitlines()
    shutil.copy(common[1], rq)
    with open(rq, 'a') as f:
        f.write('\n')
    open(rq, 'w').write('\n'.join(lines[:-1]) + '\n')
    r4 = sh(base + ['worker', '--model', 'medgemma', '--requests', rq, '--labels', common[3], '--target-manifest', common[5], '--protocol', prot,
                    '--out-dir', f'{t}/o', '--worker', '0', '--limit', '1'], env)
    chk('worker rejects modified requests', r4.returncode != 0 and 'PROTOCOL MISMATCH' in (r4.stdout + r4.stderr), out=(r4.stdout + r4.stderr)[-200:])
    pj = json.load(open(prot)); pj['components']['source']['results/iter_056/data/cases.json'] = '0' * 64
    pp = f'{t}/p.json'; json.dump(pj, open(pp, 'w'))
    r5 = sh(base + ['worker', '--model', 'medgemma', *common, '--protocol', pp, '--out-dir', f'{t}/o2', '--worker', '0', '--limit', '1'], env)
    chk('worker rejects source-hash change', r5.returncode != 0 and 'PROTOCOL' in (r5.stdout + r5.stderr))
    pj = json.load(open(prot)); k = next(iter(pj['model_files'])); pj['model_files'][k]['sha256'] = '1' * 64
    json.dump(pj, open(pp, 'w'))
    r6 = sh(base + ['verify', '--model', 'medgemma', *common, '--protocol', pp, '--out-dir', out], env)
    chk('verify rejects model-file hash edit', r6.returncode != 0, out=(r6.stdout + r6.stderr)[-200:])
    # 5) 중간 손상 복구 거부(사본)
    od = f'{t}/mid'; os.makedirs(od)
    ls = open(f'{out}/worker0.jsonl').read().splitlines()
    open(f'{od}/worker0.jsonl', 'w').write(ls[0] + '\n{BAD}\n' + ls[1] + '\n')
    r7 = sh(base + ['worker', '--model', 'medgemma', *common, '--protocol', prot, '--out-dir', od, '--worker', '0', '--limit', '1'], env)
    chk('worker refuses mid-file corruption', r7.returncode != 0 and 'JSONDecodeError' in (r7.stdout + r7.stderr))
    json.dump(res, open(f'{OUT}/runtime_tests_v2.json', 'w'), indent=1)
    print('runtime fails', res['fails'], 'of', len(res['checks']))


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    if sys.argv[1] == 'cpu':
        assert not os.path.exists(f'{OUT}/cpu_tests.json'); cpu()
    else:
        assert not os.path.exists(f'{OUT}/runtime_tests_v2.json'); runtime(sys.argv[2])
    sys.exit(1 if res['fails'] else 0)
