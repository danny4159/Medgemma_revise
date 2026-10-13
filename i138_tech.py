"""iter_138 기술 검사 (i136_tech 파생; gate는 원시 완료·출력에서만 재계산하는 단일 경로): boundary(thought/final 표식 확인), tensor(공식 processor 대조·입력 순서·target pixel 동일성), neg(변조·진입 거부),
resume(실제 SIGKILL 후 재개; iter_138에서는 알고리즘 불변이라 iter_137 기록을 gate가 재검증해 재사용), compare(구성 간 출력 정합성·처리량).
gate는 i138_gate.py 단일 구현이다.
기술 사례의 정답·정확도는 gate에 쓰지 않는다. prompt/문턱을 기술 출력으로 조정하지 않는다. 모든 결과는 results/iter_138/tests에 새 파일로 저장한다."""
import sys, os, json, subprocess, copy, time, fcntl, signal, argparse
from pathlib import Path
from i138_common import RES, HERE, sha, read, save, digest, now
from i138_spec import BASE_CONFIG, parse, split_final, START_TOKEN, END_TOKEN, STAGES
import i138_run as R

T = RES / 'tests'
TS = time.time_ns()
PY = sys.executable
_CNT = 0


def boundary():
    from transformers import AutoProcessor
    proc = AutoProcessor.from_pretrained(R.MODEL, local_files_only=True); tok = proc.tokenizer
    s, e = tok.convert_tokens_to_ids(START_TOKEN), tok.convert_tokens_to_ids(END_TOKEN)
    tpl = proc.chat_template if isinstance(proc.chat_template, str) else json.dumps(proc.chat_template)
    msgs = [dict(role='user', content=[dict(type='text', text='hi')])]
    rendered = proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
    # iter_136 저장 출력(읽기 전용): 구조 확인용. 정확도에 쓰지 않는다.
    import glob
    rs = [json.loads(l) for f in sorted(glob.glob(str(HERE / 'results/iter_136/jobs/main/worker*.jsonl'))) for l in open(f)]
    st = [split_final(r['tokens'], s, e)[0] for r in rs]
    ex = next(r for r in rs if split_final(r['tokens'], s, e)[0] == 'thought_final')
    fin = split_final(ex['tokens'], s, e)[1]
    ok = (tok.convert_ids_to_tokens(s) == START_TOKEN and tok.convert_ids_to_tokens(e) == END_TOKEN and s != e and START_TOKEN not in rendered and END_TOKEN not in rendered
          and all(x in st for x in ('no_marker', 'thought_final')) and 'invalid_boundary' not in st and tok.decode(fin, skip_special_tokens=True).strip() != '')
    save(T / 'boundary_check.json', dict(created_at=now(), passed=bool(ok), ids=dict(start_id=s, end_id=e), tokens=[START_TOKEN, END_TOKEN], chat_template_mentions_markers=START_TOKEN in tpl or END_TOKEN in tpl,
                                         generation_prompt_contains_markers=START_TOKEN in rendered, iter134_stored_status_counts={k: st.count(k) for k in set(st)},
                                         note='표식 id는 tokenizer mapping에서 읽었다(상수 가정 아님). generation prompt는 표식을 포함하지 않으므로 thought 시작은 모델 출력이다.'))
    print('boundary', ok, s, e)


def tensor(stage='technical'):
    import torch
    from PIL import Image
    from transformers import AutoProcessor
    proc = AutoProcessor.from_pretrained(R.MODEL, local_files_only=True); rr = R.requests(stage); out = []
    tok = proc.tokenizer; img_id = tok.convert_tokens_to_ids('<image_soft_token>'); pix = {}
    for r in rr:
        wrap = R.input_tensor(proc, r); n = len(r['images'])
        text = proc.apply_chat_template(R.messages(r), tokenize=False, add_generation_prompt=True)
        imgs = [Image.open(im['path']).convert('RGB') for im in r['images']]
        ind = proc(text=text, images=imgs or None, return_tensors='pt', add_special_tokens=False) if imgs else proc(text=text, return_tensors='pt', add_special_tokens=False)
        same_ids = bool(torch.equal(wrap['input_ids'], ind['input_ids']))
        same_pix = bool(torch.equal(wrap['pixel_values'], ind['pixel_values'])) if n else ('pixel_values' not in wrap and 'pixel_values' not in ind)
        n_img_tok = int((wrap['input_ids'] == img_id).sum())
        order_sensitive = None
        if n == 2 and r['images'][0]['sha256'] != r['images'][1]['sha256']:
            sw = copy.deepcopy(r); sw['images'].reverse(); order_sensitive = not torch.equal(wrap['pixel_values'], R.input_tensor(proc, sw)['pixel_values'])
        per_ok = True
        if n:
            per = [proc.image_processor(images=[im], return_tensors='pt')['pixel_values'] for im in imgs]
            per_ok = all(torch.equal(wrap['pixel_values'][i:i + 1], per[i]) for i in range(n))
            for i, ro in enumerate(r['roles']): pix.setdefault((r['patient'], ro), []).append(wrap['pixel_values'][i:i + 1].clone())
        decoded = tok.decode(wrap['input_ids'][0])
        leak = [s for s in [r['patient'], 'BRATS', 't2f', 'glioma', 'edema', 'annotation', 'mask', 'label'] if s in decoded]   # 'tumor'는 고정 질문 문구에 있으므로 제외
        out.append(dict(id=r['id'], same_input_ids=same_ids, same_pixel_values=same_pix, n_images=n, n_image_tokens=n_img_tok, input_len=int(wrap['input_ids'].shape[-1]),
                        order_sensitive=order_sensitive, per_image_pixel_match=per_ok, leak=leak, pixel_values_shape=list(wrap['pixel_values'].shape) if n else None,
                        png_size=[Image.open(im['path']).size for im in r['images']]))
    same_target = all(all(torch.equal(v[0], x) for x in v) for v in pix.values()) and all(len(v) == 2 for v in pix.values())
    # A/B 차이 검사: 같은 영상의 B input_ids는 A에서 연속 구간 하나(설명 요구 문장)만 제거한 것이어야 한다
    from i138_spec import EXPL
    byk = {}
    for r in rr: byk.setdefault((r['patient'], r['cond']), {})[r['iface']] = [int(x) for x in R.input_tensor(proc, r)['input_ids'][0]]
    span = []
    for k, d in sorted(byk.items()):
        a, b = d['A'], d['B']; p = 0
        while p < len(b) and a[p] == b[p]: p += 1
        q = 0
        while q < len(b) - p and a[-1 - q] == b[-1 - q]: q += 1
        removed = tok.decode(a[p:len(a) - q]); span.append(dict(key=list(k), len_A=len(a), len_B=len(b), removed_text=removed, ok=bool(len(a) - len(b) == len(a[p:len(a) - q]) > 0 and removed.strip() in EXPL.strip() and EXPL.strip().startswith(removed.strip()[:10]))))
    span_ok = all(s['ok'] for s in span) and len(span) == len(rr) // 2
    ok = (same_target and span_ok and all(o['same_input_ids'] and o['same_pixel_values'] and o['per_image_pixel_match'] and not o['leak'] and o['n_image_tokens'] == 256 * o['n_images']
                              and o['order_sensitive'] in (None, True) for o in out))
    save(T / ('tensor_check_%s.json' % stage), dict(created_at=now(), stage=stage, passed=bool(ok), same_target_pixels_across_conditions=bool(same_target), ab_prompt_span_ok=bool(span_ok), ab_spans=span, n_requests=len(out), rows=out)); print('tensor passed', ok, 'same_target', same_target)


def neg():
    import i138_eval as E
    rr = R.requests('technical'); path = R.request_file('technical'); res = {}

    def must_fail(name, fn, expect=None):
        """expect: 예외 문자열에 포함되어야 하는 의도한 거부 사유. 다른 사유(파일 충돌 등)의 실패는 rejected=False로 기록한다."""
        try: fn(); res[name] = dict(rejected=False)
        except BaseException as e:
            if isinstance(e, KeyboardInterrupt): raise
            msg = type(e).__name__ + ': ' + str(e)[:150]
            res[name] = dict(rejected=expect is None or expect in msg, error=msg, expected_reason=expect)
    tmp = T / ('neg_tmp_' + str(TS)); tmp.mkdir(parents=True, exist_ok=True)
    x = copy.deepcopy(rr); x[0]['prompt'] += ' extra'; save(tmp / 'tamper_prompt.json', x); must_fail('tampered_prompt', lambda: R.requests('technical', tmp / 'tamper_prompt.json'))
    x = copy.deepcopy(rr)
    if x[0]['images']: x[0]['images'][0]['sha256'] = '0' * 64
    x[0]['request_digest'] = digest({k: v for k, v in x[0].items() if k != 'request_digest'}); save(tmp / 'tamper_hash.json', x); must_fail('changed_input_hash', lambda: R.requests('technical', tmp / 'tamper_hash.json'))
    save(tmp / 'dup.json', [rr[0], rr[0]]); must_fail('duplicate_request_ids', lambda: R.requests('technical', tmp / 'dup.json'))
    cfg = R.config_for('technical'); proto = R.verify_protocol('technical')
    fake = dict(id='unknown__P', request_digest='a', protocol_sha256=proto, config_digest=digest(cfg), image_hashes=[]); must_fail('unknown_request_id_in_records', lambda: R.check_records([fake], rr, proto, cfg))
    rec = dict(id=rr[0]['id'], request_digest=rr[0]['request_digest'], protocol_sha256='bad', config_digest=digest(cfg), image_hashes=[im['sha256'] for im in rr[0]['images']]); must_fail('wrong_protocol_in_record', lambda: R.check_records([rec], rr, proto, cfg))
    lock = read(R.protocol_path('technical')); orig = R.protocol_path
    job = RES / ('jobs/neg_direct_' + str(TS)); job.mkdir(parents=True, exist_ok=True)

    def with_tamper(kind, entry):
        l = copy.deepcopy(lock)
        if kind == 'input': k = sorted(l['inputs'])[0]; l['inputs'][k] = '0' * 64
        if kind == 'code': k = [p for p in sorted(l['code']) if p.endswith('i138_tech.py')][0]; l['code'][k] = '0' * 64   # 기술 gate 생성 코드 변조
        if kind == 'code_gate': k = [p for p in sorted(l['code']) if p.endswith('i138_gate.py')][0]; l['code'][k] = '0' * 64
        if kind == 'code_eval': k = [p for p in sorted(l['code']) if p.endswith('i138_eval.py')][0]; l['code'][k] = '0' * 64
        global _CNT; _CNT += 1
        p = tmp / ('protocol_%s_%d.json' % (kind, _CNT)); save(p, l)
        R.protocol_path = lambda s, new=False: p
        try: entry()
        finally: R.protocol_path = orig
    ns = argparse.Namespace(stage='technical', workers=2, peak=9000, limit=0, job=str(job), worker=0, attempt='x', lock_fd=None)
    # launch·worker·eval 직접 진입 모두 변조된 protocol을 거부해야 한다
    for kind in ('input', 'code', 'code_eval', 'code_gate'):
        must_fail('launch_tampered_%s' % kind, lambda: with_tamper(kind, lambda: R.launch(ns)), 'protocol mismatch')
        j2 = RES / ('jobs/neg_worker_%s_%d' % (kind, TS)); j2.mkdir(parents=True, exist_ok=True)
        fdw = os.open(j2 / 'supervisor.lock', os.O_CREAT | os.O_RDWR, 0o600); fcntl.flock(fdw, fcntl.LOCK_EX)
        nsw = argparse.Namespace(stage='technical', workers=1, peak=9000, limit=0, job=str(j2), worker=0, attempt='x', lock_fd=fdw)
        must_fail('worker_tampered_%s' % kind, lambda: with_tamper(kind, lambda: R.worker(nsw)), 'protocol mismatch'); os.close(fdw)
        must_fail('eval_tampered_%s' % kind, lambda: with_tamper(kind, lambda: E.report(str(job), 'technical')), 'protocol mismatch')
    # main gate=false: gate 파일이 passed=False이면 config/launch/lock/eval/worker 모두 거부. main protocol은 아직 없으므로 technical 잠금 사본을 main으로 위장해 gate 검사 분기에 도달시킨다.
    gp = str(T / 'technical_gate.json'); real_read = R.read; fake_gate = dict(passed=False, main_max_new_tokens=1024)
    def patched(p, *a, **k): return fake_gate if str(p) == gp else real_read(p, *a, **k)
    import i138_lock as L
    mainlock = dict(copy.deepcopy(lock), stage='main'); mp = tmp / 'protocol_main_fake.json'; save(mp, mainlock)
    def gate_false(entry):
        R.read = patched; L.read = patched; R.protocol_path = lambda s, new=False: mp
        try: entry()
        finally: R.read = real_read; L.read = real_read; R.protocol_path = orig
    G = 'technical gate not passed'
    must_fail('config_main_gate_false', lambda: gate_false(lambda: R.config_for('main')), G)
    must_fail('launch_main_gate_false', lambda: gate_false(lambda: R.launch(argparse.Namespace(stage='main', workers=2, peak=9000, limit=0, job=str(RES / 'jobs/neg_main'), worker=0, attempt='x', lock_fd=None))), G)
    jm = RES / ('jobs/neg_worker_main_%d' % TS); jm.mkdir(parents=True, exist_ok=True); fdm = os.open(jm / 'supervisor.lock', os.O_CREAT | os.O_RDWR, 0o600); fcntl.flock(fdm, fcntl.LOCK_EX)
    must_fail('worker_main_gate_false', lambda: gate_false(lambda: R.worker(argparse.Namespace(stage='main', workers=1, peak=9000, limit=0, job=str(jm), worker=0, attempt='x', lock_fd=fdm))), G); os.close(fdm)
    must_fail('lock_main_gate_false', lambda: gate_false(lambda: L.main('main')), G)
    must_fail('eval_main_gate_false', lambda: gate_false(lambda: E.report(str(job), 'main')), G)
    must_fail('admission_over_capacity', lambda: R.admission(R.allowed()[0], 10 ** 6), 'admission')
    env = dict(os.environ, CUDA_VISIBLE_DEVICES='0')
    p = subprocess.run([PY, str(HERE / 'i138_run.py'), 'worker', '--job', str(job), '--stage', 'technical', '--worker', '0', '--attempt', 'x'], env=env, capture_output=True, text=True)
    res['worker_without_lock_fd'] = dict(rejected=p.returncode != 0, rc=p.returncode, stderr_tail=p.stderr[-200:])
    (job / 'supervisor.lock').write_text(''); fd = os.open(job / 'supervisor.lock', os.O_RDWR)
    p = subprocess.run([PY, str(HERE / 'i138_run.py'), 'worker', '--job', str(job), '--stage', 'technical', '--worker', '0', '--attempt', 'y', '--lock-fd', str(fd)], env=env, capture_output=True, text=True, pass_fds=(fd,))
    os.close(fd); res['worker_with_unheld_lock'] = dict(rejected=p.returncode != 0, rc=p.returncode, stderr_tail=p.stderr[-200:])
    job2 = RES / ('jobs/neg_dup_' + str(TS)); job2.mkdir(parents=True, exist_ok=True)
    fd2 = os.open(job2 / 'supervisor.lock', os.O_CREAT | os.O_RDWR, 0o600); fcntl.flock(fd2, fcntl.LOCK_EX)
    p = subprocess.run([PY, str(HERE / 'i138_run.py'), 'launch', '--job', str(job2), '--stage', 'technical'], env=dict(os.environ, CUDA_VISIBLE_DEVICES='0,1'), capture_output=True, text=True)
    os.close(fd2); res['duplicate_supervisor'] = dict(rejected=p.returncode != 0 and 'refuse launch' in p.stderr, rc=p.returncode, stderr_tail=p.stderr[-200:])
    jb = RES / ('jobs/neg_records_' + str(TS)); jb.mkdir(parents=True, exist_ok=True)
    (jb / 'worker0_a.jsonl').write_bytes(b'{"bad":\n{"also":1}\n'); must_fail('corrupt_middle_row', lambda: R.load_records(jb))
    res['all_rejected'] = all(v['rejected'] for v in res.values() if isinstance(v, dict))
    save(T / 'negative_tests.json', dict(created_at=now(), **res)); print({k: v['rejected'] for k, v in res.items() if isinstance(v, dict)})


def run_launch(stage, name, workers, extra=()):
    job = RES / 'jobs' / name
    t0 = time.monotonic()
    p = subprocess.run([PY, str(HERE / 'i138_run.py'), 'launch', '--job', str(job), '--stage', stage, '--workers', str(workers), *extra], env=dict(os.environ, CUDA_VISIBLE_DEVICES='0,1'))
    print(name, 'rc', p.returncode, 'wall', time.monotonic() - t0)
    return p.returncode


def resume(stage, name, kill_after=12):
    """실제 SIGKILL: launch(2 worker) 프로세스 그룹을 일부 record 저장 후 강제 종료하고 같은 job을 다시 launch해 완료한다."""
    job = RES / 'jobs' / name; job.mkdir(parents=True, exist_ok=True)
    n_expected = len(R.requests(stage))
    proc = subprocess.Popen([PY, str(HERE / 'i138_run.py'), 'launch', '--job', str(job), '--stage', stage, '--workers', '2'], env=dict(os.environ, CUDA_VISIBLE_DEVICES='0,1'), start_new_session=True,
                            stdout=open(job / 'first_launch.out', 'xb'), stderr=subprocess.STDOUT)
    t0 = time.monotonic(); n = 0
    while proc.poll() is None:
        n = sum(len(Path(p).read_bytes().splitlines()) for p in job.glob('worker*.jsonl'))
        if n >= kill_after: break
        time.sleep(0.2)
        if time.monotonic() - t0 > 3600: break
    killed = proc.poll() is None
    if killed: os.killpg(proc.pid, signal.SIGKILL)
    proc.wait(); time.sleep(3)
    raw = [(p.name, p.read_bytes()) for p in job.glob('worker*.jsonl')]
    torn = [name_ for name_, b in raw if b and not b.endswith(b'\n')]
    n_after_kill = sum(len(b.splitlines()) for _, b in raw)
    save(job / ('kill_record_%d.json' % TS), dict(killed_while_running=killed, lines_at_kill=n_after_kill, expected=n_expected, torn_tail_files=torn, completion_exists=(job / 'completion.json').exists(),
                                                  wall_before_kill_s=time.monotonic() - t0, workers=2))
    assert killed and 0 < n_after_kill < n_expected, 'kill did not occur mid-run'
    rc = run_launch(stage, name, 2)
    print('resume rc', rc, 'killed at', n_after_kill, 'torn', torn)
    return rc


def toks(job): return {r['id']: r['tokens'] for r in R.load_records(job)}


def compare(names):
    jobs = RES / 'jobs'; base = toks(jobs / names[0]); out = dict(created_at=now(), configs={})
    for name in names:
        j = jobs / name; rec = R.load_records(j); comp = read(j / 'completion.json'); t = toks(j)
        res = [read(p) for p in sorted(j.glob('result_*.json'))]; wall = sum(x['wall_s'] for x in res)
        killed = [read(p) for p in sorted(j.glob('kill_record_*.json'))]   # 중단 시도는 result 파일이 없으므로 kill_record의 wall을 비용 ledger에 합산한다
        interrupted_wall = float(sum(k['wall_before_kill_s'] for k in killed)); wall += interrupted_wall
        ex = [read(p) for p in j.glob('worker*_exit.json')]; gen_wall = max(e['wall_s'] for e in ex) if ex else None
        used = {}
        for rp in j.glob('resources_*.jsonl'):
            for l in open(rp):
                if l.strip():
                    for g in json.loads(l)['gpu']: used[g['index']] = max(used.get(g['index'], 0), int(g['used']))
        ws = sorted(r['wall_s'] for r in rec)
        out['configs'][name] = dict(n=len(rec), identical_tokens_to_first=all(t[k] == base[k] for k in base) and set(t) == set(base), launch_wall_s=wall, generation_wall_s=gen_wall,
                                    req_per_min_generation=len(rec) / gen_wall * 60 if gen_wall else None, req_per_min_incl_load=len(rec) / wall * 60,
                                    latency_p50=ws[len(ws) // 2], latency_p95=ws[int(0.95 * (len(ws) - 1))], max_peak_reserved_mib=max(r['peak_reserved_mib'] for r in rec), max_gpu_used_mib=used,
                                    all_eos=all(r['eos'] for r in rec), max_tokens=max(r['n_tokens'] for r in rec), returncodes=comp['returncodes'], load_s=[e['load_s'] for e in ex], n_results=len(res), n_interrupted_attempts=len(killed), interrupted_wall_s=interrupted_wall,
                                    kill_records=killed)
    save(T / ('compare_%s.json' % names[0]), out); print(json.dumps(out['configs'], indent=1)[:3000])


if __name__ == '__main__':
    fn = sys.argv[1]
    if fn == 'compare': compare(sys.argv[2:])
    elif fn == 'launch': sys.exit(run_launch(sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5:]))
    elif fn == 'resume': sys.exit(resume(sys.argv[2], sys.argv[3]))
    else: globals()[fn](*sys.argv[2:])
