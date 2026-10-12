"""iter_117 한정 복구: 원 자산 확인 → 새 평가 잠금 → MAIN 감독 → 검증 봉인.

생성 pg43_run과 모든 기존 산출물을 변경하지 않는다. 원 평가·관찰 규약을
본생성 이전에 잠그고 실제 실행 경로에서 확인한다.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import ed116_build as BUILD
import ed116_link as LINK
import ed116_spec as SPEC
import ed116_eval as EV
import pg43_run as RUN
from ed117_verify import sha

ROOT = Path('results/iter_117')
SOURCE_SHA = '66cd4542720d0efe69b2fbbdfabbe24ebe0253a0'
PLAN116 = '../agent/runs/iter_116/plan.md'
PLANHASH = 'be752099da4cd90c2b14fe16ac4659b054de1cb114111364c8dcf8b93a46d009'
REQ = 'results/iter_116/requests/MAIN.jsonl'
PROTO = str(ROOT / 'protocol/MAIN.json')
GEN = str(ROOT / 'gen/MAIN')
CODE = list(dict.fromkeys(BUILD.EVAL_CODE + ['ed116_verify.py', 'ed116_directcheck.py', 'ed116_baselines.py',
    'ed116_verify_selection.py', 'ed117_run.py', 'ed117_verify.py', 'ed117_analyze.py', 'ed117_processor.py', 'test_ed117.py']))


def read(p):
    return json.loads(Path(p).read_text())


def write(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x') as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)


def event(name, **kw):
    ROOT.mkdir(exist_ok=True)
    with (ROOT / 'events.jsonl').open('a') as f:
        f.write(json.dumps(dict(event=name, epoch=time.time(), **kw)) + '\n')


def technical_gate(recs, ids):
    # 원 문턱과 원 완전성 검사를 유지. T의 응답 성공만 보조 조건으로 분리한다.
    old = EV.tech_gate(recs, ids)
    required = {c: old['per_condition'][c]['passes'] for c in 'NER'}
    complete = len(ids) == 12 and len(recs) == 48 and len({(r['patient'], r['cond']) for r in recs}) == 48
    complete = complete and all(old['per_condition'][c]['n_missing'] == 0 and old['per_condition'][c]['n_records'] == 12 for c in 'NERT')
    return dict(run=bool(complete and all(required.values())), per_condition=old['per_condition'],
                min_resolved_required=6, required_response_conditions=list('NER'), all_four_inputs_complete=complete,
                auxiliary_T=True, original_gate_run=old['run'])


def prepare():
    t0 = time.monotonic()
    assert sha(PLAN116) == PLANHASH
    original = read('results/iter_116/RESULT_MANIFEST.json')
    inputs = {}
    def check(p, expected=None):
        current = sha(p)
        if expected is not None and current != expected:
            raise RuntimeError(f'출처 hash 변경: {p}')
        inputs[str(p)] = current
    for p, h in read('results/iter_116/lock/eval_lock.json')['files'].items():
        check(p, h)
    for p, h in original['outputs'].items():
        check(p, h)
    prov = read('results/iter_116/provenance/provenance.json')
    paths = dict(sets=LINK.SETS, labels=LINK.LABELS, infer=LINK.INFER, det_lock=LINK.DET_LOCK,
                 det_sel=LINK.DET_SEL, sft_reuse=LINK.SFT_REUSE, det_raw=LINK.DET_DIR + '/raw_preds.json',
                 det_completion=LINK.DET_DIR + '/completion.json')
    for k, p in paths.items():
        check(p, prov['inputs'][k])
    for stage, d in prov['O'].items():
        check(LINK.O_PROTO[stage], d['protocol']['protocol_sha256'])
        check(LINK.O_REQ[stage], d['requests_sha256'])
        for fn, h in d['worker_files'].items():
            check(LINK.O_STAGES[stage] + '/' + fn, h)
    check(LINK.SFT_PROTO, prov['SFT']['protocol']['protocol_sha256'])
    for fn, h in prov['SFT']['worker_files'].items():
        check(LINK.SFT_DIR + '/' + fn, h)
    # 기존 검증된 protocol의 입력은 불변 hash 근거를 연결한다. 전수 임상/코드 감사를 반복하지 않는다.
    for p in [LINK.SFT_PROTO, *LINK.O_PROTO.values()]:
        locked = read(p)['locked']
        for f, h in locked['files'].items():
            if not f.endswith('.py'):
                check(f, h)
    sel = read('results/iter_116/lock/selection.json')
    rows = read('results/iter_116/provenance/ledger_nogt.json')['rows']
    assert SPEC.select(rows) == {k: sel[k] for k in SPEC.select(rows)}
    req = RUN.read_requests(REQ)
    group_of = {**{i: 'mismatch' for i in sel['mismatch']}, **{i: 'control' for i in sel['control']}}
    expected = BUILD.make_rows(rows, sel['mismatch'] + sel['control'], 'MAIN', group_of)
    assert req == expected and len(req) == 696
    assert len({r['patient'] for r in req}) == 174
    source_code = {}
    for f in list(dict.fromkeys(BUILD.EVAL_CODE + ['ed116_directcheck.py', 'ed116_verify_selection.py', 'ed116_baselines.py'])):
        blob = subprocess.run(['git', 'show', SOURCE_SHA + ':' + f], capture_output=True, check=True).stdout
        assert blob == Path(f).read_bytes(), f
        source_code[f] = sha(f)
    # 실제 가중치 내용 대조. 원 캐시에 쓰지 않는다.
    weights = read('results/iter_116/lock/weights_check.json')
    for name, d in weights['files'].items():
        path = Path(weights['snapshot']) / name
        assert path.stat().st_size == d['size'] and sha(path) == d['sha256'], name
    techs = {}
    for stage, reqname in [('TECH_w2', 'TECH'), ('TECH_w4', 'TECH'), ('RESUME8', 'RESUME8')]:
        techs[stage] = RUN.verify_completion('results/iter_116/gen/' + stage,
            'results/iter_116/requests/' + reqname + '.jsonl', 'results/iter_116/protocol/protocol_' + reqname + '.json')
    a = {r['request_id']: r['suffix_ids'] for r in techs['TECH_w2']}
    b = {r['request_id']: r['suffix_ids'] for r in techs['TECH_w4']}
    assert a == b and len(a) == 48
    for r in techs['RESUME8']:
        assert r['suffix_ids'] == a[r['request_id']]
    gate = technical_gate(techs['TECH_w2'], sel['tech'])
    assert gate['run']
    assert {c: gate['per_condition'][c]['n_resolved'] for c in 'NERT'} == dict(N=12, E=9, R=9, T=5)
    write(ROOT / 'tech/gate.json', gate)
    write(ROOT / 'reuse_manifest.json', dict(original_source_sha=SOURCE_SHA, original_plan_sha256=PLANHASH,
        original_plan=PLAN116, current_plan_sha256=sha('../agent/runs/iter_117/plan.md'), inputs=inputs, source_code=source_code,
        source_generation_protocol='results/iter_116/protocol/protocol_TECH.json',
        source_tech_counts={k: len(v) for k, v in techs.items()}, generation_sources_unchanged=True,
        required_checks='원 출력 hash·현재 입력·원 요청 재구성·TECH 완료/동등성·전체 가중치 hash 통과',
        elapsed_s=time.monotonic() - t0, new_generate_requests=0))
    event('prepare_complete', wall_s=time.monotonic() - t0)
    print('재사용 입력과 TECH 확인 완료. 본요청 696, gate=True')


def verify_lock():
    lock = read(ROOT / 'lock/eval_lock.json')
    for p, h in lock['files'].items():
        if sha(p) != h:
            raise RuntimeError(f'평가 잠금 불일치 {p}')
    for p, h in read(ROOT / 'reuse_manifest.json')['inputs'].items():
        if sha(p) != h:
            raise RuntimeError(f'현재 원본 불일치 {p}')
    return lock


def lock():
    tests = ['tests/fixtures_inherited.json', 'tests/fixtures_amendment.json', 'tests/processor.json']
    for p in tests:
        d = read(ROOT / p)
        assert d.get('all_pass', d.get('n_pass') == d.get('n')) is True, p
    assert read(ROOT / 'tech/gate.json')['run'] is True
    inputs = read(ROOT / 'reuse_manifest.json')['inputs']
    paths = list(dict.fromkeys(CODE + list(inputs) + [str(ROOT / x) for x in tests] +
        [str(ROOT / 'reuse_manifest.json'), str(ROOT / 'tech/gate.json'), PLAN116,
         '../agent/runs/iter_117/plan.md', '../agent/runs/iter_117/plan.json']))
    t = time.time()
    d = dict(locked_at_epoch=t, locked_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(t)),
             files={p: sha(p) for p in paths}, original_plan_sha256=PLANHASH, original_source_sha=SOURCE_SHA,
             amendment='T 응답 성공만 보조 조건으로 분리; 원 사건·성능 부등식·parser·표본 유지',
             observation_contract=dict(strata=['mismatch_Kcorrect', 'mismatch_Kwrong', 'control_Kcorrect', 'control_Kwrong'],
                 policies=list(EV.POL), paired=['R_vs_N', 'R_vs_E'], categories=['opacity', 'normal', 'not_normal_no_opacity'],
                 new_numeric_gates=False),
             best_range_note='개별 지표별 best는 동시에 실현 가능한 성공의 증명이 아니며 불확정 후보이다.')
    write(ROOT / 'lock/eval_lock.json', d)
    RUN.make_protocol(REQ, PROTO, gate=str(ROOT / 'tech/gate.json'),
                      lock=[str(ROOT / 'lock/eval_lock.json'), *CODE, *inputs],
                      extra=dict(iteration=117, original_plan_sha256=PLANHASH, original_source_sha=SOURCE_SHA,
                                 source_tech_protocol_sha256=sha('results/iter_116/protocol/protocol_TECH.json')))
    verify_lock()
    event('evaluation_locked', locked_at_utc=d['locked_at_utc'])
    print('사전 평가 잠금', d['locked_at_utc'])


def launch():
    verify_lock()
    t0 = time.monotonic()
    write(ROOT / 'execution_start.json', dict(epoch=time.time(), pid=os.getpid(), python=sys.executable,
        inherited_cuda_visible_devices=os.environ.get('CUDA_VISIBLE_DEVICES'), protocol_sha256=sha(PROTO),
        expected_requests=696, expected_patients=174, peak_gb_assumed=9.0,
        worker_choice='기존 TECH 48요청에서 2→4worker wall 105.43→60.30초, token 48/48 같음. peak 8.268GiB에 여유를 둔 9GiB admission.'))
    allowed = RUN.allowed_gpus()
    free = RUN.gpu_free_mib()
    workers = 4 if all(free[g] >= 2 * 11 * 1024 for g in allowed) and len(allowed) == 2 else 2
    root_log = ROOT / 'launch'
    root_log.mkdir(exist_ok=True)
    def stop(proc):
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
    for attempt in range(2):
        with (root_log / f'attempt{attempt}.stdout').open('x') as out, (root_log / f'attempt{attempt}.stderr').open('x') as err:
            cmd = [sys.executable, '-u', 'pg43_run.py', 'launch', '--requests', REQ, '--protocol', PROTO,
                   '--out-dir', GEN, '--workers', str(workers), '--peak-gb', '9']
            proc = subprocess.Popen(cmd, stdout=out, stderr=err, start_new_session=True)
            event('launch', child_pid=proc.pid, workers=workers, argv=cmd, free_mib=RUN.gpu_free_mib())
            unsafe = False
            try:
                with (root_log / f'monitor{attempt}.jsonl').open('x') as log:
                    while proc.poll() is None:
                        try:
                            proc.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            pass
                        data = subprocess.run(['nvidia-smi', '--query-gpu=index,memory.used,memory.free,utilization.gpu',
                                               '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True).stdout
                        live = subprocess.run(['nvidia-smi', '--query-compute-apps=gpu_uuid,pid,used_memory',
                                               '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True).stdout
                        log.write(json.dumps(dict(epoch=time.time(), gpu=data, processes=live,
                            cpu_load=os.getloadavg(), meminfo=Path('/proc/meminfo').read_text())) + '\n')
                        log.flush()
                        free_now = RUN.gpu_free_mib()
                        if proc.poll() is None and any(free_now[g] < (workers // len(allowed)) * 2048 for g in allowed):
                            unsafe = True
                            event('safety_margin_stop', free_mib=free_now, workers=workers)
                            stop(proc)
                            break
            except BaseException:
                stop(proc)
                raise
            rc = proc.wait()
            event('launch_exit', child_pid=proc.pid, exit_code=rc, workers=workers, safety_stop=unsafe)
        if rc == 0 and not unsafe:
            recs = RUN.verify_completion(GEN, REQ, PROTO)
            assert len(recs) == 696
            event('main_complete', wall_s=time.monotonic() - t0)
            print('MAIN 완료 696요청', flush=True)
            return
        if workers == 4 and (unsafe or any('OutOfMemory' in f.read_text() for f in Path(GEN).glob('worker*.stderr'))):
            # 우리 프로세스의 부분 결과/claim을 보존한 채 같은 protocol으로 재개한다.
            workers = 2
            event('lower_concurrency_resume', reason='OOM 또는 worker당 2GiB 여유 부족')
        else:
            raise RuntimeError(f'MAIN 실행 실패 rc={rc}; 원 로그와 부분 결과 보존')
    raise RuntimeError('안전 동시성 복구 후에도 완료되지 않음')


def seal():
    verify_lock()
    recs = RUN.verify_completion(GEN, REQ, PROTO)
    v = read(ROOT / 'eval/verify.json')
    assert v['all_pass'] is True
    for p, h in v['verified_files'].items():
        assert sha(p) == h, p
    files = list(v['verified_files']) + [str(ROOT / 'eval/verify.json'), str(ROOT / 'reuse_manifest.json'),
        str(ROOT / 'execution_start.json'), str(ROOT / 'tech/gate.json')]
    files += [str(p) for p in (ROOT / 'tests').glob('*.json')]
    write(ROOT / 'completion.json', dict(complete=True, epoch=time.time(), n_records=len(recs), n_patients=174,
        original_source_sha=SOURCE_SHA, original_plan_sha256=PLANHASH,
        files={p: sha(p) for p in files}, verifier_sha256=sha(ROOT / 'eval/verify.json'),
        performance_label=read(ROOT / 'eval/report.json')['decision']['label'], new_training=False))
    event('sealed')
    print('검증 대상 digest와 현재 원본 재확인 후 봉인 완료')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('command', choices=['prepare', 'lock', 'launch', 'seal'])
    a = ap.parse_args()
    globals()[a.command]()
