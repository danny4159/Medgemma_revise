"""iter_077 CPU 회귀 검사: 단계 상태 재사용/stale 거부/실패 전파/소유권, GPU 메모리 예약, checkpoint 뒤 미커밋 로그, 생성 출력 중복·누락 검사.
결과: results/iter_077/tests/fixtures_sp77.json (존재하면 중단). 하나라도 실패하면 비정상 종료. GPU 불사용."""
import json, os, sys, tempfile, time

import sp75_train as TR
import sp77_pipeline as P
import sp77_stage as S

OUT = 'results/iter_077/tests/fixtures_sp77.json'
if os.path.exists(OUT):
    sys.exit('exists')
res, fails = {}, []


def chk(name, cond, info=None):
    res[name] = {'ok': bool(cond), 'info': info}
    if not cond:
        fails.append(name)


def raises(fn, exc=Exception):
    try:
        fn()
    except exc as e:
        return repr(e)[:160]
    return None


td = tempfile.TemporaryDirectory()
d = td.name
code = [os.path.join(d, 'code.py')]
open(code[0], 'w').write('x=1\n')
out1 = os.path.join(d, 'out1.txt')
cmd_ok = [sys.executable, '-c', f"open({out1!r},'w').write('v1')"]
st = S.run_stage(d + '/state', 'ok', cmd_ok, [out1], code)
chk('stage_completed_records_hashes', st['status'] == 'completed' and st['outputs'][out1] == S.sha_file(out1))
st2 = S.run_stage(d + '/state', 'ok', [sys.executable, '-c', 'import sys; sys.exit(9)'], [out1], code)
chk('completed_stage_reused_not_rerun', st2.get('reused') is True and st2['rc'] == 0)
open(out1, 'w').write('tampered')
chk('stale_when_output_changed', S.completed_valid(d + '/state', 'ok', code) is False)
open(out1, 'w').write('v1')
chk('valid_again_when_restored', S.completed_valid(d + '/state', 'ok', code) is True)
open(code[0], 'w').write('x=2\n')
chk('stale_when_code_changed', S.completed_valid(d + '/state', 'ok', code) is False)
e = raises(lambda: S.run_stage(d + '/state', 'bad', [sys.executable, '-c', 'import sys; sys.exit(3)'], [out1], code), S.StageFailed)
chk('child_rc_propagates_as_failure', e is not None and S.read_state(d + '/state', 'bad')['status'] == 'failed' and S.read_state(d + '/state', 'bad')['rc'] == 3, e)
e = raises(lambda: S.run_stage(d + '/state', 'nofile', [sys.executable, '-c', 'pass'], [os.path.join(d, 'never.txt')], code), S.StageFailed)
chk('missing_output_fails_even_with_rc0', e is not None and S.read_state(d + '/state', 'nofile')['status'] == 'failed', e)
e = raises(lambda: S.run_stage(d + '/state', 'vfail', cmd_ok, [out1], code, verify=lambda: (_ for _ in ()).throw(RuntimeError('incomplete'))), S.StageFailed)
chk('verify_failure_blocks_completion', e is not None and S.read_state(d + '/state', 'vfail')['status'] == 'failed' and 'incomplete' in e, e)
exp = S.run_stage(d + '/state', 'expect5', [sys.executable, '-c', 'import sys; sys.exit(5)'], [d + '/state/expect5.marker'] if False else [out1], code, expect_rc=5)
chk('expected_nonzero_rc_stage_completed', exp['status'] == 'completed' and exp['rc'] == 5 and S.completed_valid(d + '/state', 'expect5', code))
# 소유권: 현재(살아 있는) pid가 running으로 기록된 단계는 중복 시작을 거부한다
S._atomic({'status': 'running', 'pid': os.getpid(), 'pid_start': S._pid_start(os.getpid())}, d + '/state/owned.json')
e = raises(lambda: S.run_stage(d + '/state', 'owned', cmd_ok, [out1], code), S.StageFailed)
chk('live_owner_refused', e is not None and 'live pid' in e, e)
S._atomic({'status': 'running', 'pid': 2 ** 22 - 3, 'pid_start': '1'}, d + '/state/dead.json')
st3 = S.run_stage(d + '/state', 'dead', cmd_ok, [out1], code)
chk('dead_owner_rerun_and_stale_preserved', st3['status'] == 'completed' and os.path.exists(d + '/state/dead.stale.json'))

# ---- Reserver ----
TOT = 24576


def fake(used):
    return lambda: {g: {'used': used[g], 'total': TOT, 'uuid': 'u' + g} for g in used}


used = {'0': 100, '1': 100}
os.environ['CUDA_VISIBLE_DEVICES'] = '0,1'
r = P.Reserver(fake(used))
g1 = r.try_acquire('t1', 11947)
g2 = r.try_acquire('t2', 11947)
g3 = r.try_acquire('t3', 11947)
chk('train_one_per_gpu_by_reservation', {g1, g2} == {'0', '1'} and g3 is None, [g1, g2, g3])
r.release(g1, 't1')
used2 = dict(used)
chk('slot_reusable_after_release', r.try_acquire('t3', 11947) == g1)
r2 = P.Reserver(fake({'0': 14000, '1': 100}))
chk('other_process_usage_counted_and_least_loaded_first', r2.try_acquire('a', 11947) == '1' and r2.try_acquire('b', 11947) is None)
r3 = P.Reserver(fake({'0': 100, '1': 20000}))
chk('too_little_free_refused', r3.try_acquire('x', 11947) == '0' and r3.try_acquire('y', 11947) is None)
r4 = P.Reserver(fake({'0': 100, '1': 100}))
acc = [r4.try_acquire(f'g{i}', 8000) for i in range(5)]
chk('two_small_workers_per_gpu_when_margin_allows', acc[:4].count('0') == 2 and acc[:4].count('1') == 2 and acc[4] is None, acc)


def boom():
    raise RuntimeError('nvidia-smi failed')


r5 = P.Reserver(boom)
chk('smi_failure_is_not_free', raises(lambda: r5.try_acquire('z', 1000)) is not None)

# ---- run_jobs 실패 전파 및 후속 작업 비시작 ----
P.STATE, P.LEDGER = d + '/pstate', d + '/ledger.jsonl'
mark2 = os.path.join(d, 'second_started')
jobs = [{'name': 'j_fail', 'cmd': [sys.executable, '-c', 'import sys; sys.exit(7)', ], 'log': d + '/l1.log', 'outputs': [out1], 'est_mib': 20000},
        {'name': 'j_after', 'cmd': [sys.executable, '-c', f"open({mark2!r},'w').write('x')"], 'log': d + '/l2.log', 'outputs': [mark2], 'est_mib': 20000}]
rsv = P.Reserver(fake({'0': 100}))
os.environ['CUDA_VISIBLE_DEVICES'] = '0'
rsv = P.Reserver(fake({'0': 100}))
e = raises(lambda: P.run_jobs(jobs, 'test', rsv), SystemExit)
chk('run_jobs_failure_raises_and_blocks_dependents', e is not None and not os.path.exists(mark2) and S.read_state(d + '/pstate', 'j_fail')['status'] == 'failed', e)
os.environ['CUDA_VISIBLE_DEVICES'] = '0,1'
# 의도: j_after는 같은 GPU 예약 때문에 j_fail 종료 뒤에야 후보가 되지만 실패 후에는 시작하지 않는다.

# ---- 미커밋 로그 ----
rd = os.path.join(d, 'run')
os.makedirs(rd)
rows = [{'step': i, 'loss': 1.0} for i in (1, 2, 3)] + [{'event': 'checkpoint', 'step': 3}] + [{'step': 4, 'loss': 1.0}, {'step': 5, 'loss': 1.0}, {'event': 'checkpoint', 'step': 5}]
open(rd + '/train_log.jsonl', 'w').write('\n'.join(json.dumps(x) for x in rows) + '\n')
lf = open(rd + '/train_log.jsonl', 'a')
n = TR.quarantine_uncommitted(rd, 3, lf)
kept = [json.loads(l) for l in open(rd + '/train_log.jsonl')]
unc = [json.loads(l) for l in open(rd + '/train_log.uncommitted.jsonl')]
chk('uncommitted_tail_quarantined_and_preserved', n == 3 and [x.get('step') for x in kept if 'loss' in x] == [1, 2, 3] and len(unc) == 4 and unc[0]['event'] == 'quarantine' and sum('loss' in x for x in unc) == 2)
rd2 = os.path.join(d, 'run2')
os.makedirs(rd2)
open(rd2 + '/train_log.jsonl', 'w').write('\n'.join(json.dumps(x) for x in [{'step': 1, 'loss': 1.0}, {'step': 2, 'loss': 1.0}]) + '\n')
e = raises(lambda: TR.quarantine_uncommitted(rd2, 2, open(rd2 + '/train_log.jsonl', 'a')))
chk('missing_checkpoint_log_record_refuses_resume', e is not None and 'no committed checkpoint' in e, e)
rd3 = os.path.join(d, 'run3')
os.makedirs(rd3)
open(rd3 + '/train_log.jsonl', 'w').write('\n'.join(json.dumps(x) for x in [{'step': 1, 'loss': 1.0}, {'step': 1, 'loss': 1.0}, {'event': 'checkpoint', 'step': 1}]) + '\n')
e = raises(lambda: TR.quarantine_uncommitted(rd3, 1, open(rd3 + '/train_log.jsonl', 'a')))
chk('duplicate_committed_step_refuses_resume', e is not None and 'not contiguous' in e, e)

# ---- 생성 출력 완전성 검사 (gen_job.verify) ----
gd = os.path.join(d, 'gen')
os.makedirs(gd)
import sp75_data as D
ids = [r['id'] for r in D.load_manifest()['rows'] if r['split'] == 'V8' and not r['excluded'] and r['position_set'] == 'supervised']
job = P.gen_job('x', 'F', 'V8', 'supervised', 'none', gd, 1000)
open(gd + '/gen_worker0.jsonl', 'w').write('\n'.join(json.dumps({'id': i}) for i in ids[:-1]) + '\n')
chk('gen_missing_request_detected', raises(job['verify']) is not None)
open(gd + '/gen_worker0.jsonl', 'w').write('\n'.join(json.dumps({'id': i}) for i in ids + [ids[0]]) + '\n')
chk('gen_duplicate_request_detected', raises(job['verify']) is not None)
open(gd + '/gen_worker0.jsonl', 'w').write('\n'.join(json.dumps({'id': i}) for i in ids) + '\n')
chk('gen_complete_passes', raises(job['verify']) is None and len(ids) == 24)

td.cleanup()
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump({'n_checks': len(res), 'n_fail': len(fails), 'fails': fails, 'checks': res}, open(OUT, 'w'), indent=1)
print(len(res), 'checks', len(fails), 'fails', fails)
sys.exit(1 if fails else 0)
