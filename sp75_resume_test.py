"""iter_076 학습 재개·단일 소유권·수치 재현 검사 (원 iter_075 resume 검사의 보완판; 새 결과 경로 results/iter_076/tests/resume, 존재하면 중단).

같은 장치·동일 초기 checkpoint(base 초기화, seed17)·같은 batch/RNG에서 연속 실행과 저장-복구 실행을 대조한다.
GPU0 체인(결정적 kernel): det_ref(연속) -> det_A(epoch 중간 step3 중단 후 재개 + 동시 중복 실행 거부) -> det_B(epoch checkpoint 직후, validation 전 중단 후 재개)
GPU1 체인(동시): det_ref_g1(결정적, 장치 교차 대조) -> nd_ref1, nd_ref2(비결정 기본 설정, 1 epoch, 연속 반복 간 차이 측정)
판정: 결정적 경로에서 A/B가 ref와 step별 loss·batch·RNG·checkpoint digest(adapter/optimizer/rng)·val_ce·adapter digest가 정확히 같아야 PASS.
비결정 반복의 차이는 별도 기록하며 허용오차를 넓혀 통과시키지 않는다. FAIL이면 비정상 종료 코드.
"""
import json, os, subprocess, sys, threading, time

BASE = 'results/iter_076/tests/resume'
COMMON = ['--variant', 'F', '--lr', '2e-4', '--seed', '17']
DET = ['--epochs', '2', '--save-epochs', '1,2', '--deterministic']
ND = ['--epochs', '1', '--save-epochs', '1']


def cmd(run, gpu, extra):
    return [sys.executable, 'sp75_train.py', '--run-dir', f'{BASE}/{run}', '--gpu', gpu, *COMMON, *extra]


def call(run, gpu, extra, tag):
    return subprocess.call(cmd(run, gpu, extra), stdout=open(f'{BASE}/{run}.{tag}.out', 'w'), stderr=subprocess.STDOUT)


def events(run):
    return [json.loads(l) for l in open(f'{BASE}/{run}/train_log.jsonl')]


def steps(L):
    out = {}
    for r in L:
        if 'loss' in r:
            if r['step'] in out:
                raise RuntimeError('duplicate logged step')   # 중복 step 허용 안 함
            out[r['step']] = r
    return out


def ckpts(L):
    return {r['step']: r['digests'] for r in L if r.get('event') == 'checkpoint'}


def val(run, e):
    return json.load(open(f'{BASE}/{run}/epoch_{e:02d}/val_ce.json'))


def compare(a_run, b_run, epochs):
    """a_run vs b_run: step별 loss/batch/RNG, checkpoint digest, val_ce, adapter digest 정확 일치 여부와 최초 불일치."""
    La, Lb = events(a_run), events(b_run)
    sa, sb = steps(La), steps(Lb)
    res = {'n_steps': [len(sa), len(sb)], 'same_step_set': sorted(sa) == sorted(sb)}
    first = None
    for s in sorted(set(sa) & set(sb)):
        if sa[s]['loss'] != sb[s]['loss'] and first is None:
            first = {'step': s, 'loss_a': sa[s]['loss'], 'loss_b': sb[s]['loss'], 'abs_diff': abs(sa[s]['loss'] - sb[s]['loss']), 'grad_norm_a': sa[s]['grad_norm'], 'grad_norm_b': sb[s]['grad_norm']}
    res['first_loss_mismatch'] = first
    res['max_abs_loss_diff'] = max(abs(sa[s]['loss'] - sb[s]['loss']) for s in set(sa) & set(sb))
    res['loss_exact_equal_all'] = all(sa[s]['loss'] == sb[s]['loss'] and sa[s]['grad_norm'] == sb[s]['grad_norm'] for s in set(sa) & set(sb))
    res['batch_ids_token_sha_equal'] = all(sa[s]['batch_ids'] == sb[s]['batch_ids'] and sa[s]['batch_token_sha'] == sb[s]['batch_token_sha'] for s in set(sa) & set(sb))
    res['rng_before_equal'] = all(sa[s]['rng_before'] == sb[s]['rng_before'] and sa[s]['opt_step_before'] == sb[s]['opt_step_before'] for s in set(sa) & set(sb))
    res['lr_equal'] = all(sa[s]['lr'] == sb[s]['lr'] for s in set(sa) & set(sb))
    ca, cb = ckpts(La), ckpts(Lb)
    res['checkpoint_digests_equal_common_steps'] = {str(s): ca[s] == cb[s] for s in sorted(set(ca) & set(cb))}
    res['val_ce'] = {str(e): [val(a_run, e)['val_ce'], val(b_run, e)['val_ce']] for e in epochs}
    res['val_ce_equal'] = all(val(a_run, e)['val_ce'] == val(b_run, e)['val_ce'] for e in epochs)
    res['adapter_digest_equal'] = all(val(a_run, e)['adapter_digest'] == val(b_run, e)['adapter_digest'] for e in epochs)
    return res


def chain0(res):
    res['rc']['det_ref'] = call('det_ref', '0', DET, 'run')
    # A: epoch 중간 checkpoint(step3) 직후 중단 -> 재개, 재개 중 동시 중복 실행은 거부되어야 함
    res['rc']['det_A_stop'] = call('det_A', '0', DET + ['--stop-after-step', '3'], 'stop')
    p = subprocess.Popen(cmd('det_A', '0', DET), stdout=open(f'{BASE}/det_A.resume.out', 'w'), stderr=subprocess.STDOUT)
    time.sleep(40)
    res['rc']['det_A_dup_concurrent'] = call('det_A', '0', DET, 'dup')
    res['rc']['det_A_resume'] = p.wait()
    # B: epoch checkpoint 저장 직후(validation 전) 중단 -> 재개에서 validation 복구
    res['rc']['det_B_stop'] = call('det_B', '0', DET + ['--stop-after-epoch-ckpt', '1'], 'stop')
    res['B_val_before_resume'] = os.path.exists(f'{BASE}/det_B/epoch_01/val_ce.json')
    res['rc']['det_B_resume'] = call('det_B', '0', DET, 'resume')


def chain1(res):
    res['rc']['det_ref_g1'] = call('det_ref_g1', '1', DET, 'run')
    res['rc']['nd_ref1'] = call('nd_ref1', '1', ND, 'run')
    res['rc']['nd_ref2'] = call('nd_ref2', '1', ND, 'run')


def main():
    if os.path.exists(BASE):
        sys.exit('exists')
    os.makedirs(BASE)
    res = {'rc': {}, 'gpu_env': os.environ.get('CUDA_VISIBLE_DEVICES')}
    t = [threading.Thread(target=chain0, args=(res,)), threading.Thread(target=chain1, args=(res,))]
    t0 = time.time()
    [x.start() for x in t]
    [x.join() for x in t]
    res['wall_s'] = time.time() - t0
    ok = {}
    ok['all_rc_expected'] = all(res['rc'][k] == 0 for k in ('det_ref', 'det_A_resume', 'det_B_resume', 'det_ref_g1', 'nd_ref1', 'nd_ref2')) and \
        res['rc']['det_A_stop'] == 5 and res['rc']['det_B_stop'] == 3 and res['rc']['det_A_dup_concurrent'] != 0
    if ok['all_rc_expected']:
        res['A_vs_ref'] = compare('det_A', 'det_ref', (1, 2))
        res['B_vs_ref'] = compare('det_B', 'det_ref', (1, 2))
        res['ref_g1_vs_ref'] = compare('det_ref_g1', 'det_ref', (1, 2))
        res['nondet_repeat_nd1_vs_nd2'] = compare('nd_ref1', 'nd_ref2', (1,))
        La = events('det_A')
        Lb = events('det_B')
        res['A_resume_events'] = [r for r in La if r.get('event') == 'resume']
        res['B_resume_events'] = [r for r in Lb if r.get('event') == 'resume']
        res['B_val_events'] = [r.get('epoch') for r in Lb if r.get('event') == 'val_ce']
        res['dup_message'] = open(f'{BASE}/det_A.dup.out').read()[-300:]
        for k in ('A_vs_ref', 'B_vs_ref'):
            r = res[k]
            ok[k] = bool(r['same_step_set'] and r['loss_exact_equal_all'] and r['batch_ids_token_sha_equal'] and r['rng_before_equal'] and r['lr_equal']
                         and all(r['checkpoint_digests_equal_common_steps'].values()) and r['val_ce_equal'] and r['adapter_digest_equal'])
        ok['resume_restored_equals_saved'] = all(e.get('restored_equals_saved') for e in res['A_resume_events'] + res['B_resume_events']) and len(res['A_resume_events']) == 1 and len(res['B_resume_events']) == 1
        ok['B_val_missing_before_resume_and_recovered'] = (res['B_val_before_resume'] is False) and res['B_val_events'] == [1, 2]
        ok['det_g1_vs_g0_info_only'] = res['ref_g1_vs_ref']['loss_exact_equal_all']   # 정보용(통과 조건 아님)
    res['PASS'] = bool(ok.get('all_rc_expected') and ok.get('A_vs_ref') and ok.get('B_vs_ref') and ok.get('resume_restored_equals_saved') and ok.get('B_val_missing_before_resume_and_recovered'))
    res['ok'] = ok
    json.dump(res, open(f'{BASE}/resume_compare.json', 'w'), indent=1)
    print(json.dumps({'PASS': res['PASS'], 'ok': ok, 'rc': res['rc']}, indent=1))
    sys.exit(0 if res['PASS'] else 1)


if __name__ == '__main__':
    main()
