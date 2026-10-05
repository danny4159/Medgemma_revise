"""iter_075 학습 재개·단일 소유권 검사. 기준 run(ref)과 (A) epoch 중간 step 중단 후 재개, (B) epoch checkpoint 저장 직후(validation 전) 중단 후 재개를 비교한다.
동시 실행 거부(같은 run-dir 두 번째 프로세스)도 확인한다. 결과: results/iter_075/tests/resume/ (존재하면 중단)."""
import json, os, subprocess, sys, time

BASE = 'results/iter_075/tests/resume'
COMMON = ['--variant', 'F', '--lr', '2e-4', '--epochs', '2', '--save-epochs', '1,2', '--seed', '17']


def cmd(run, gpu, extra=()):
    return [sys.executable, 'sp75_train.py', '--run-dir', f'{BASE}/{run}', '--gpu', gpu, *COMMON, *extra]


def log(run):
    return [json.loads(l) for l in open(f'{BASE}/{run}/train_log.jsonl')]


def main():
    if os.path.exists(BASE):
        sys.exit('exists')
    os.makedirs(BASE)
    res = {'rc': {}}
    # phase 1: ref(GPU0) || A 중단(GPU1)
    p_ref = subprocess.Popen(cmd('ref', '0'), stdout=open(f'{BASE}/ref.out', 'w'), stderr=subprocess.STDOUT)
    p_a = subprocess.Popen(cmd('A', '1', ['--stop-after-step', '3']), stdout=open(f'{BASE}/A1.out', 'w'), stderr=subprocess.STDOUT)
    res['rc']['A_stop'] = p_a.wait()
    # A 재개 (GPU1) 와 동시에 같은 run-dir에 두 번째 프로세스 -> 거부되어야 함
    p_a2 = subprocess.Popen(cmd('A', '1'), stdout=open(f'{BASE}/A2.out', 'w'), stderr=subprocess.STDOUT)
    time.sleep(20)
    p_dup = subprocess.Popen(cmd('A', '1'), stdout=open(f'{BASE}/A_dup.out', 'w'), stderr=subprocess.STDOUT)
    res['rc']['A_dup_concurrent'] = p_dup.wait()
    res['rc']['A_resume'] = p_a2.wait()
    res['rc']['ref'] = p_ref.wait()
    # phase 2: B 중단(epoch ckpt 직후) 후 재개 (GPU0)
    res['rc']['B_stop'] = subprocess.call(cmd('B', '0', ['--stop-after-epoch-ckpt', '1']), stdout=open(f'{BASE}/B1.out', 'w'), stderr=subprocess.STDOUT)
    res['B_val_before_resume'] = os.path.exists(f'{BASE}/B/epoch_01/val_ce.json')
    res['rc']['B_resume'] = subprocess.call(cmd('B', '0'), stdout=open(f'{BASE}/B2.out', 'w'), stderr=subprocess.STDOUT)
    # 비교
    lr, la, lb = log('ref'), log('A'), log('B')
    st = lambda L: {r['step']: r for r in L if 'loss' in r}
    sr, sa, sb = st(lr), st(la), st(lb)
    res['steps'] = {'ref': len(sr), 'A': len(sa), 'B': len(sb)}
    res['A_dup_steps_logged'] = len([r for r in la if 'loss' in r]) - len(sa)
    res['A_resume_events'] = [r for r in la if r.get('event') == 'resume']
    res['B_resume_events'] = [r for r in lb if r.get('event') == 'resume']
    res['max_abs_loss_diff_A_vs_ref'] = max(abs(sa[s]['loss'] - sr[s]['loss']) for s in sr)
    res['max_abs_loss_diff_B_vs_ref'] = max(abs(sb[s]['loss'] - sr[s]['loss']) for s in sr)
    res['batch_ids_equal_A'] = all(sa[s]['batch_ids'] == sr[s]['batch_ids'] and sa[s]['batch_token_sha'] == sr[s]['batch_token_sha'] for s in sr)
    res['batch_ids_equal_B'] = all(sb[s]['batch_ids'] == sr[s]['batch_ids'] and sb[s]['batch_token_sha'] == sr[s]['batch_token_sha'] for s in sr)
    res['rng_before_equal_A'] = all(sa[s]['rng_before'] == sr[s]['rng_before'] for s in sr)
    res['rng_before_equal_B'] = all(sb[s]['rng_before'] == sr[s]['rng_before'] for s in sr)
    ad = lambda r, e: json.load(open(f'{BASE}/{r}/epoch_{e:02d}/val_ce.json'))
    res['val_ce'] = {r: {e: ad(r, e)['val_ce'] for e in (1, 2)} for r in ('ref', 'A', 'B')}
    res['adapter_digest'] = {r: {e: ad(r, e)['adapter_digest'][:16] for e in (1, 2)} for r in ('ref', 'A', 'B')}
    res['dup_message'] = open(f'{BASE}/A_dup.out').read()[-200:]
    json.dump(res, open(f'{BASE}/resume_compare.json', 'w'), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == '__main__':
    main()
