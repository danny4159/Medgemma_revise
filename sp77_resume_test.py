"""iter_077 학습 재개·단일 소유권·수치 재현 검사 (결과: results/iter_077/tests/resume; 단계 상태: results/iter_077/state).

결정적 설정(--deterministic = use_deterministic_algorithms + 기본 SDPA; sp77_sdpa_probe 근거)에서 같은 장치(GPU0)·같은 초기 상태·batch·RNG로
 ref   : 중단 없는 연속 2 epoch
 A     : step4 직후(마지막 checkpoint는 step3: 미커밋 step4 로그 구간) 중단 -> 재개(재개 중 동시 중복 실행은 거부되어야 함)
 B     : epoch1 checkpoint 직후, validation 전 중단 -> 재개에서 validation 복구
를 실행하고 step별 loss·grad_norm·batch/token hash·RNG·LR, checkpoint digest, val_ce, adapter digest를 정확 비교한다.
GPU1 보조: ref_g1 (다른 장치 연속 실행; 정보용, 통과 조건 아님). 임의 tolerance 없음. 비교 집합이 비거나 step 집합이 다르면 FAIL.
각 단계는 sp77_stage 상태 파일로 기록·재사용되며, 자식 실패/예외는 부모의 비정상 종료로 전달된다.
"""
import json, os, subprocess, sys, threading, time

import sp77_stage as S

OUT = 'results/iter_077'
BASE = f'{OUT}/tests/resume'
STATE = f'{OUT}/state'
COMMON = ['--variant', 'F', '--lr', '2e-4', '--seed', '17']
DET = ['--epochs', '2', '--save-epochs', '1,2', '--deterministic']
CODE = ['sp75_train.py', 'sp75_vlm.py', 'sp75_data.py', 'rsna_diag/train.py', 'rsna_diag/lora.py', 'rsna_diag/generate.py', 'rsna_diag/queue_lock.py', 'sp77_stage.py', 'sp77_resume_test.py']
errs = []


def cmd(run, gpu, extra):
    return [sys.executable, 'sp75_train.py', '--run-dir', f'{BASE}/{run}', '--gpu', gpu, *COMMON, *extra]


def fin(run):
    return [f'{BASE}/{run}/epoch_02/val_ce.json', f'{BASE}/{run}/freeze_end.json']


def stage(name, run, gpu, extra, outputs, expect_rc=0):
    return S.run_stage(STATE, name, cmd(run, gpu, extra), outputs, CODE, gpu=gpu, log=f'{BASE}/{name}.out', expect_rc=expect_rc)


def guarded(fn):
    def w(*a):
        try:
            fn(*a)
        except BaseException as e:   # 스레드 안에서 오류를 잃지 않는다
            errs.append(repr(e))
    return w


def chain0():
    stage('ref', 'ref', '0', DET, fin('ref'))
    stage('A_stop', 'A', '0', DET + ['--stop-after-step', '4', '--allow-uncommitted-stop'], [f'{BASE}/A_stop.out'], expect_rc=5)
    res_err = []

    def resume():
        try:
            stage('A_resume', 'A', '0', DET, fin('A'))
        except BaseException as e:
            res_err.append(repr(e))
    t = threading.Thread(target=resume)
    t.start()
    for _ in range(300):    # A_resume이 lock을 잡고 'resumed' 로그를 낼 때까지 대기 후 동시 중복 실행을 시도
        time.sleep(2)
        if os.path.exists(f'{BASE}/A_resume.out') and 'resumed step=' in open(f'{BASE}/A_resume.out').read():
            break
    stage('A_dup_concurrent', 'A', '0', DET, [f'{BASE}/A_dup_concurrent.out'], expect_rc=1)
    t.join()
    if res_err:
        raise RuntimeError(res_err[0])
    stage('B_stop', 'B', '0', DET + ['--stop-after-epoch-ckpt', '1'], [f'{BASE}/B_stop.out'], expect_rc=3)
    json.dump({'B_val_before_resume': os.path.exists(f'{BASE}/B/epoch_01/val_ce.json')}, open(f'{BASE}/B_before_resume.json.tmp', 'w'))
    if not os.path.exists(f'{BASE}/B_before_resume.json'):
        os.replace(f'{BASE}/B_before_resume.json.tmp', f'{BASE}/B_before_resume.json')
    stage('B_resume', 'B', '0', DET, fin('B'))


def chain1():
    stage('ref_g1', 'ref_g1', '1', DET, fin('ref_g1'))


def events(run):
    return [json.loads(l) for l in open(f'{BASE}/{run}/train_log.jsonl') if l.strip()]


def steps(L):
    out = {}
    for r in L:
        if 'loss' in r:
            if r['step'] in out:
                raise RuntimeError('duplicate logged step')
            out[r['step']] = r
    return out


def val(run, e):
    return json.load(open(f'{BASE}/{run}/epoch_{e:02d}/val_ce.json'))


def compare(a_run, b_run, epochs):
    La, Lb = events(a_run), events(b_run)
    sa, sb = steps(La), steps(Lb)
    common = sorted(set(sa) & set(sb))
    res = {'n_steps': [len(sa), len(sb)], 'same_step_set': sorted(sa) == sorted(sb), 'n_common': len(common)}
    first = None
    for s in common:
        if (sa[s]['loss'] != sb[s]['loss'] or sa[s]['grad_norm'] != sb[s]['grad_norm']) and first is None:
            first = {'step': s, 'loss_a': sa[s]['loss'], 'loss_b': sb[s]['loss'], 'abs_diff': abs(sa[s]['loss'] - sb[s]['loss'])}
    res['first_loss_mismatch'] = first
    res['max_abs_loss_diff'] = max(abs(sa[s]['loss'] - sb[s]['loss']) for s in common) if common else None
    res['loss_exact_equal_all'] = bool(common) and all(sa[s]['loss'] == sb[s]['loss'] and sa[s]['grad_norm'] == sb[s]['grad_norm'] for s in common)
    res['batch_ids_token_sha_equal'] = bool(common) and all(sa[s]['batch_ids'] == sb[s]['batch_ids'] and sa[s]['batch_token_sha'] == sb[s]['batch_token_sha'] for s in common)
    res['rng_before_equal'] = bool(common) and all(sa[s]['rng_before'] == sb[s]['rng_before'] and sa[s]['opt_step_before'] == sb[s]['opt_step_before'] for s in common)
    res['lr_equal'] = bool(common) and all(sa[s]['lr'] == sb[s]['lr'] for s in common)
    ca = {r['step']: r['digests'] for r in La if r.get('event') == 'checkpoint'}
    cb = {r['step']: r['digests'] for r in Lb if r.get('event') == 'checkpoint'}
    cc = sorted(set(ca) & set(cb))
    res['checkpoint_steps_common'] = cc
    res['checkpoint_digests_equal_common_steps'] = {str(s): ca[s] == cb[s] for s in cc}
    res['val_ce'] = {str(e): [val(a_run, e)['val_ce'], val(b_run, e)['val_ce']] for e in epochs}
    res['val_ce_equal'] = all(val(a_run, e)['val_ce'] == val(b_run, e)['val_ce'] for e in epochs)
    res['adapter_digest_equal'] = all(val(a_run, e)['adapter_digest'] == val(b_run, e)['adapter_digest'] for e in epochs)
    res['val_tokens_equal'] = all(val(a_run, e)['val_tokens'] == val(b_run, e)['val_tokens'] for e in epochs)
    res['ok'] = bool(res['same_step_set'] and res['n_common'] == 18 and res['loss_exact_equal_all'] and res['batch_ids_token_sha_equal'] and res['rng_before_equal'] and res['lr_equal']
                     and len(cc) >= 6 and all(res['checkpoint_digests_equal_common_steps'].values()) and res['val_ce_equal'] and res['adapter_digest_equal'] and res['val_tokens_equal'])
    return res


def main():
    os.makedirs(BASE, exist_ok=True)
    t = [threading.Thread(target=guarded(chain0)), threading.Thread(target=guarded(chain1))]
    t0 = time.time()
    [x.start() for x in t]
    [x.join() for x in t]
    res = {'wall_s': time.time() - t0, 'errors': errs, 'gpu_env': os.environ.get('CUDA_VISIBLE_DEVICES')}
    ok = {'no_stage_errors': not errs}
    if not errs:
        res['A_vs_ref'], res['B_vs_ref'] = compare('A', 'ref', (1, 2)), compare('B', 'ref', (1, 2))
        res['ref_g1_vs_ref_info_only'] = compare('ref_g1', 'ref', (1, 2))
        La, Lb = events('A'), events('B')
        res['A_resume_events'] = [r for r in La if r.get('event') == 'resume']
        res['B_resume_events'] = [r for r in Lb if r.get('event') == 'resume']
        res['B_val_events'] = [r.get('epoch') for r in Lb if r.get('event') == 'val_ce']
        res['B_val_before_resume'] = json.load(open(f'{BASE}/B_before_resume.json'))['B_val_before_resume']
        res['dup_message_tail'] = open(f'{BASE}/A_dup_concurrent.out').read()[-300:]
        unc = f'{BASE}/A/train_log.uncommitted.jsonl'
        res['A_uncommitted_rows_preserved'] = [json.loads(l) for l in open(unc) if l.strip()][:1] if os.path.exists(unc) else None
        ok['A_vs_ref'], ok['B_vs_ref'] = res['A_vs_ref']['ok'], res['B_vs_ref']['ok']
        ok['A_restored_equals_saved_and_tail_quarantined'] = len(res['A_resume_events']) == 1 and res['A_resume_events'][0].get('restored_equals_saved') is True and res['A_resume_events'][0].get('quarantined_rows') == 1
        ok['B_resume_restored'] = len(res['B_resume_events']) == 1 and res['B_resume_events'][0].get('restored_equals_saved') is True
        ok['B_val_missing_before_resume_and_recovered'] = res['B_val_before_resume'] is False and res['B_val_events'] == [1, 2]
        ok['dup_rejected_by_lock'] = 'owned by live process' in res['dup_message_tail']
        res['ref_g1_exact_info'] = res['ref_g1_vs_ref_info_only']['loss_exact_equal_all']
    res['ok'] = ok
    res['PASS'] = bool(ok and all(ok.values()))
    json.dump(res, open(f'{BASE}/resume_compare.json.tmp', 'w'), indent=1)
    os.replace(f'{BASE}/resume_compare.json.tmp', f'{BASE}/resume_compare.json')
    print(json.dumps({'PASS': res['PASS'], 'ok': ok, 'errors': errs}, indent=1))
    sys.exit(0 if res['PASS'] else 1)


if __name__ == '__main__':
    main()
