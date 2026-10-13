"""기술 검사: tensor(공식 processor 대조·입력 순서·target pixel 동일성), neg(변조·진입 거부), compare(구성 간 출력 정합성·처리량), gate.
기술 사례의 정답·정확도는 gate에 쓰지 않는다. prompt/문턱을 기술 출력으로 조정하지 않는다."""
import sys, os, json, subprocess, copy, time, fcntl
from pathlib import Path
from i134_common import RES, HERE, sha, read, save, digest, now
from i134_spec import BASE_CONFIG, parse, STAGES
import i134_run as R

T = RES / 'tests'
TS = time.time_ns()
PY = sys.executable


def tensor():
    import torch
    from PIL import Image
    from transformers import AutoProcessor
    proc = AutoProcessor.from_pretrained(R.MODEL, local_files_only=True); rr = R.requests('technical'); out = []
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
        leak = [s for s in [r['patient'], r['patient'].split('-')[2], 't2f', 'glioma', 'edema', 'BraTS', 'annotation', 'mask'] if s in decoded]   # 'tumor'는 고정 질문 문구('tumor-like lesion')에 포함되어 제외
        out.append(dict(id=r['id'], same_input_ids=same_ids, same_pixel_values=same_pix, n_images=n, n_image_tokens=n_img_tok, input_len=int(wrap['input_ids'].shape[-1]),
                        order_sensitive=order_sensitive, per_image_pixel_match=per_ok, leak=leak, pixel_values_shape=list(wrap['pixel_values'].shape) if n else None))
    # 같은 영상(target pixels)이 단독·공동·복제에서 동일 tensor인가
    same_target = all(all(torch.equal(v[0], x) for x in v) for v in pix.values())
    ok = (same_target and all(o['same_input_ids'] and o['same_pixel_values'] and o['per_image_pixel_match'] and not o['leak'] and o['n_image_tokens'] == 256 * o['n_images']
                              and o['order_sensitive'] in (None, True) for o in out))
    save(T / 'tensor_check_v3.json', dict(note='tensor_check.json은 질문 문구의 tumor를 누설로 오탐한 검사 코드 오류(입력 결함 아님)로 보존', created_at=now(),passed=bool(ok), same_target_pixels_across_conditions=bool(same_target), n_requests=len(out), rows=out)); print('tensor passed', ok, 'same_target', same_target)


def neg():
    rr = R.requests('technical'); path = R.request_file('technical'); res = {}

    def must_fail(name, fn):
        try: fn(); res[name] = dict(rejected=False)
        except Exception as e: res[name] = dict(rejected=True, error=type(e).__name__ + ': ' + str(e)[:150])
    tmp = T / ('neg_tmp_' + str(TS)); tmp.mkdir(parents=True, exist_ok=True)
    x = copy.deepcopy(rr); x[0]['prompt'] += ' extra'; save(tmp / 'tamper_prompt.json', x); must_fail('tampered_prompt', lambda: R.requests('technical', tmp / 'tamper_prompt.json'))
    x = copy.deepcopy(rr); x[0]['images'] = x[0]['images'] or [dict(path='x', sha256='0')]
    if rr[0]['images']: x[0]['images'][0]['sha256'] = '0' * 64
    x[0]['request_digest'] = digest({k: v for k, v in x[0].items() if k != 'request_digest'}); save(tmp / 'tamper_hash.json', x); must_fail('changed_input_hash', lambda: R.requests('technical', tmp / 'tamper_hash.json'))
    save(tmp / 'dup.json', [rr[0], rr[0]]); must_fail('duplicate_request_ids', lambda: R.requests('technical', tmp / 'dup.json'))
    cfg = R.config_for('technical'); proto = R.verify_protocol('technical')
    fake = dict(id='unknown__P', request_digest='a', protocol_sha256=proto, config_digest=digest(cfg), image_hashes=[]); must_fail('unknown_request_id_in_records', lambda: R.check_records([fake], rr, proto, cfg))
    rec = dict(id=rr[0]['id'], request_digest=rr[0]['request_digest'], protocol_sha256='bad', config_digest=digest(cfg), image_hashes=[im['sha256'] for im in rr[0]['images']]); must_fail('wrong_protocol_in_record', lambda: R.check_records([rec], rr, proto, cfg))
    # protocol 변조: 잠긴 입력 hash를 바꾼 사본으로 verify_protocol 실패해야 함 (worker도 동일 함수 호출)
    lock = read(R.protocol_path('technical')); first = sorted(lock['inputs'])[0]; lock['inputs'][first] = '0' * 64
    save(tmp / 'protocol_tampered.json', lock); orig = R.protocol_path
    try:
        R.protocol_path = lambda s: tmp / 'protocol_tampered.json'; must_fail('tampered_locked_input', lambda: R.verify_protocol('technical'))
    finally: R.protocol_path = orig
    must_fail('admission_over_capacity', lambda: R.admission(R.allowed()[0], 10 ** 6))
    must_fail('main_without_gate_lock', lambda: R.verify_protocol('main'))
    env = dict(os.environ, CUDA_VISIBLE_DEVICES='0'); job = RES / ('jobs/neg_direct_' + str(TS)); job.mkdir(parents=True, exist_ok=True)
    p = subprocess.run([PY, str(HERE / 'i134_run.py'), 'worker', '--job', str(job), '--stage', 'technical', '--worker', '0', '--attempt', 'x'], env=env, capture_output=True, text=True)
    res['worker_without_lock_fd'] = dict(rejected=p.returncode != 0, rc=p.returncode, stderr_tail=p.stderr[-200:])
    (job / 'supervisor.lock').write_text(''); fd = os.open(job / 'supervisor.lock', os.O_RDWR)
    p = subprocess.run([PY, str(HERE / 'i134_run.py'), 'worker', '--job', str(job), '--stage', 'technical', '--worker', '0', '--attempt', 'y', '--lock-fd', str(fd)], env=env, capture_output=True, text=True, pass_fds=(fd,))
    os.close(fd); res['worker_with_unheld_lock'] = dict(rejected=p.returncode != 0, rc=p.returncode, stderr_tail=p.stderr[-200:])
    job2 = RES / ('jobs/neg_dup_' + str(TS)); job2.mkdir(parents=True, exist_ok=True)
    fd2 = os.open(job2 / 'supervisor.lock', os.O_CREAT | os.O_RDWR, 0o600); fcntl.flock(fd2, fcntl.LOCK_EX)
    p = subprocess.run([PY, str(HERE / 'i134_run.py'), 'launch', '--job', str(job2), '--stage', 'technical'], env=dict(os.environ, CUDA_VISIBLE_DEVICES='0,1'), capture_output=True, text=True)
    os.close(fd2); res['duplicate_supervisor'] = dict(rejected=p.returncode != 0 and 'refuse launch' in p.stderr, rc=p.returncode, stderr_tail=p.stderr[-200:])
    jb = RES / ('jobs/neg_records_' + str(TS)); jb.mkdir(parents=True, exist_ok=True)
    (jb / 'worker0_a.jsonl').write_bytes(b'{"bad":\n{"also":1}\n'); must_fail('corrupt_middle_row', lambda: R.load_records(jb))
    res['all_rejected'] = all(v['rejected'] for v in res.values() if isinstance(v, dict))
    save(T / 'negative_tests_v2.json', dict(created_at=now(), **res)); print({k: v['rejected'] for k, v in res.items() if isinstance(v, dict)})


def toks(job): return {r['id']: r['tokens'] for r in R.load_records(job)}


def compare(names):
    jobs = RES / 'jobs'; base = toks(jobs / names[0]); out = dict(created_at=now(), configs={})
    for name in names:
        j = jobs / name; rec = R.load_records(j); comp = read(j / 'completion.json'); t = toks(j)
        res = [read(p) for p in sorted(j.glob('result_*.json'))]; wall = sum(x['wall_s'] for x in res)
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
                                    all_eos=all(r['eos'] for r in rec), max_tokens=max(r['n_tokens'] for r in rec), returncodes=comp['returncodes'], load_s=[e['load_s'] for e in ex])
    save(T / ('compare_%s.json' % names[0]), out); print(json.dumps(out['configs'], indent=1)[:2500])


def gate(final_stage):
    """final_stage: 'technical'(1024) 또는 'technical2048'. 사전 기준: 기술 출력 모두 EOS 완결, 첫 줄 형식 유효율>=95%, 무결성·메모리 검사 통과."""
    t = read(T / 'tensor_check_v3.json'); n = read(T / 'negative_tests_v2.json')
    stages = ['technical'] if final_stage == 'technical' else ['technical', 'technical2048']
    jobs = RES / 'jobs'; names = {'technical': ['Tb_w2', 'Tb_w4', 'Tb_resume'], 'technical2048': ['Tb2048_w2']}
    cmp_ = {}
    for s in stages:
        for nm in names[s]: cmp_[nm] = read(jobs / nm / 'completion.json')
    cfgs = read(T / 'compare_Tb_w2.json')['configs']
    j = jobs / ('Tb_w2' if final_stage == 'technical' else 'Tb2048_w2'); rec = R.verify_job(j, final_stage)
    img = [r for r in rec if not r['id'].endswith('__NONE')]   # 주 평가 조건(영상 요청). NONE은 대조 관찰이며 BA에 쓰이지 않음 (i134_eval.py가 생성 전에 잠긴 decision 정의와 동일)
    valid = sum(parse(r['text'], r['eos']) is not None for r in img) / len(img); valid_all = sum(parse(r['text'], r['eos']) is not None for r in rec) / len(rec); all_eos = all(r['eos'] for r in rec)
    checks = dict(tensor=t['passed'], negative=n['all_rejected'], w4_identical=cfgs['Tb_w4']['identical_tokens_to_first'], resume_identical=cfgs['Tb_resume']['identical_tokens_to_first'],
                  complete_40=all(v['n'] == 40 for v in cfgs.values()), rc_zero=all(all(x == 0 for x in v['returncodes']) for v in cfgs.values()), all_eos=all_eos, first_line_valid_ge_95=valid >= 0.95)
    passed = all(checks.values())
    save(T / ('technical_gate_%s.json' % final_stage), dict(created_at=now(), final_stage=final_stage, passed=passed, checks=checks, valid_rate_image_requests=valid, valid_rate_all_incl_NONE=valid_all, n_non_eos=sum(not r['eos'] for r in rec),
                                                              main_max_new_tokens=R.config_for(final_stage)['max_new_tokens'], note='기술 정확도는 gate에 쓰지 않음. 유효율 95% gate의 범위(영상 요청 vs 전체)는 계획에 명시되지 않아 평가기 decision 정의(영상 요청)를 따르고, NONE 포함 값을 함께 기록(해석은 기술 출력을 본 뒤 확정했으므로 리뷰 대상)'))
    print(checks, 'valid', valid, 'passed', passed)


if __name__ == '__main__':
    fn = sys.argv[1]
    globals()[fn](*sys.argv[2:]) if len(sys.argv) > 2 and fn == 'gate' else (compare(sys.argv[2:]) if fn == 'compare' else globals()[fn]())
