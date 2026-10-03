"""iter_063 실행 경로 검사 (실제 진입점 사용): 변조 거부 / 손상 tail·stale claim·비용 누락 복구 / 중복 완료 재확인.
사용: CUDA_VISIBLE_DEVICES=<gpu> python q63_test.py   (MedGemma D2 8건 사본으로 실제 worker를 재시작한다)
결과: results/iter_063/tests/run_path_tests.json (이미 있으면 중단)
"""
import json, os, shutil, subprocess, sys, glob
import q63_run as Q

T = 'results/iter_063/tests'
SRC = 'results/iter_063/gen_D2_medgemma'
REQ, LAB, PROT = 'results/iter_063/data/D2_requests.jsonl', 'results/iter_063/data/D2_labels.json', 'results/iter_063/D2_protocol_medgemma.json'


def run(args, **kw):
    return subprocess.run([sys.executable, 'q63_run.py'] + args, capture_output=True, text=True, **kw)


def main():
    out = f'{T}/run_path_tests.json'
    assert not os.path.exists(out), 'exists'
    os.makedirs(T, exist_ok=True)
    res = {}
    # 1) 변조 거부: 요청 파일 1바이트 변경 / labels 변경 / protocol model 불일치
    shutil.copy(REQ, f'{T}/req_tampered.jsonl')
    with open(f'{T}/req_tampered.jsonl', 'a') as f:
        f.write('\n')
    r = run(['verify', '--model', 'medgemma', '--requests', f'{T}/req_tampered.jsonl', '--labels', LAB, '--protocol', PROT, '--out-dir', SRC])
    res['tamper_requests_rejected'] = r.returncode != 0 and 'PROTOCOL MISMATCH' in (r.stdout + r.stderr)
    shutil.copy(LAB, f'{T}/lab_tampered.json')
    d = json.load(open(f'{T}/lab_tampered.json')); k = next(iter(d)); d[k]['gt_orig_index'] = (d[k]['gt_orig_index'] + 1) % 5
    json.dump(d, open(f'{T}/lab_tampered.json', 'w'))
    r = run(['verify', '--model', 'medgemma', '--requests', REQ, '--labels', f'{T}/lab_tampered.json', '--protocol', PROT, '--out-dir', SRC])
    res['tamper_labels_rejected'] = r.returncode != 0 and 'PROTOCOL MISMATCH' in (r.stdout + r.stderr)
    r = run(['verify', '--model', 'qwen', '--requests', REQ, '--labels', LAB, '--protocol', PROT, '--out-dir', SRC])
    res['wrong_model_protocol_rejected'] = r.returncode != 0
    # 2) 복구: 사본에서 (a) 마지막 record 줄 절단 (b) 다른 record의 비용 행 삭제 (c) 절단된 rid에 죽은 pid claim
    W = f'{T}/resume_md'
    assert not os.path.exists(W)
    shutil.copytree(SRC, W)
    for f in glob.glob(f'{W}/launch_*.json') + glob.glob(f'{W}/verify.json') + glob.glob(f'{W}/*.attempt_*.json'):
        os.remove(f)
    recs = [json.loads(l) for l in open(f'{W}/worker0.jsonl')]
    base = {r['rid']: r['attempts'][-1]['suffix_ids'] for r in recs}
    raw = open(f'{W}/worker0.jsonl').read().splitlines()
    cut_rid = recs[-1]['rid']
    open(f'{W}/worker0.jsonl', 'w').write('\n'.join(raw[:-1]) + '\n' + raw[-1][:200])  # 마지막 줄 절단(개행 없음)
    costs = [json.loads(l) for l in open(f'{W}/cost_worker0.jsonl')]
    nocost_rid = recs[3]['rid']
    open(f'{W}/cost_worker0.jsonl', 'w').write(''.join(json.dumps(c) + '\n' for c in costs if c['rid'] not in (nocost_rid, cut_rid)))
    open(f'{W}/claims/{cut_rid}.claim', 'w').write(json.dumps({'pid': 2 ** 22 - 3, 'worker': 0}))  # 죽은 pid
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=os.environ.get('Q63_TEST_GPU', '1'))
    r = subprocess.run([sys.executable, 'q63_run.py', 'worker', '--model', 'medgemma', '--requests', REQ, '--labels', LAB, '--protocol', PROT,
                        '--out-dir', W, '--worker', '0'], capture_output=True, text=True, env=env)
    res['worker_restart_rc'] = r.returncode
    after = [json.loads(l) for l in open(f'{W}/worker0.jsonl')]
    ids = [x['rid'] for x in after]
    res['n_records_after'] = len(ids)
    res['no_duplicates'] = len(ids) == len(set(ids)) == 8
    res['regenerated_token_match'] = {x['rid']: x['attempts'][-1]['suffix_ids'] == base[x['rid']] for x in after if x['rid'] == cut_rid}
    res['corrupt_tail_preserved'] = len(glob.glob(f'{W}/worker0.jsonl.corrupt_*')) == 1
    res['stale_claim_renamed'] = len(glob.glob(f'{W}/claims/{cut_rid}.claim.stale_*')) == 1
    cm = [json.loads(l) for l in open(f'{W}/cost_worker0.jsonl')]
    res['cost_missing_rows'] = [c['rid'] for c in cm if c.get('cost_missing')] == [nocost_rid]
    v = run(['verify', '--model', 'medgemma', '--requests', REQ, '--labels', LAB, '--protocol', PROT, '--out-dir', W])
    res['verify_after_resume_rc'] = v.returncode
    res['verify_cost_missing_reported'] = json.load(open(f'{W}/verify.json'))['cost_missing']
    # 3) 이미 완료된 요청 재확인: 완료 상태에서 worker를 다시 실행하면 새 생성 0
    n_before = len(after)
    r2 = subprocess.run([sys.executable, 'q63_run.py', 'worker', '--model', 'medgemma', '--requests', REQ, '--labels', LAB, '--protocol', PROT,
                         '--out-dir', W, '--worker', '1'], capture_output=True, text=True, env=env)
    n_after = sum(len(open(f).read().splitlines()) for f in glob.glob(f'{W}/worker*.jsonl'))
    res['second_worker_no_duplicate_generation'] = r2.returncode == 0 and n_after == n_before
    # 4) 손상 중간 줄은 strict 읽기에서 예외
    bad = f'{T}/bad_mid.jsonl'
    open(bad, 'w').write('{"a":1}\n{"a":\n{"a":3}\n')
    try:
        Q.read_jsonl(bad); res['strict_read_rejects_mid_corruption'] = False
    except json.JSONDecodeError:
        res['strict_read_rejects_mid_corruption'] = True
    res['all_pass'] = all(v is True or (isinstance(v, dict) and all(v.values())) for k, v in res.items()
                          if k not in ('worker_restart_rc', 'n_records_after', 'verify_after_resume_rc', 'verify_cost_missing_reported')) \
        and res['worker_restart_rc'] == 0 and res['verify_after_resume_rc'] == 0 and res['verify_cost_missing_reported'] == 1
    json.dump(res, open(out, 'w'), indent=1)
    print(json.dumps(res, indent=1))
    sys.exit(0 if res['all_pass'] else 1)


if __name__ == '__main__':
    main()
