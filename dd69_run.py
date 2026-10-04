"""iter_069 실행기: 두 모델(Qwen2.5-VL-7B / MedGemma 1.5) x 7(+R) 조건 요청 생성.

m65_run.py 의 backend 함수(load_model/env_info/build_inputs/generate/per_image_pixels 등)와 JSONL 유틸만 호출한다.
MSD 전용 cmd_tech·자료 구성·protocol 경로는 사용하지 않는다 (이 파일이 새 protocol/worker/launch/verify/tech 를 구현).

 - 답변·attempt 비용은 한 행(단일 write)에 저장. 저장 직후 시간은 별도 .cost 행에 기록(누락 시 verify가 보고).
 - protocol: 코드·요청 3종·labels·cases·build_manifest·영상·모델 revision/파일·cap·환경 버전을 잠그고 worker/launch/verify/tech 에서 재검증.
 - worker: out_dir 단위 per-worker flock, 원자적 claim, 소유 worker만 개행 없는 꼬리 행 보존/제거, 다른 worker 파일은 완결 행만 읽음.
 - launch: 상속된 CUDA_VISIBLE_DEVICES 안에서만 GPU 지정, 시작 직전 nvidia-smi 여유(worker당 peak+2GiB) admission.
서브명령: lock | tech | worker | launch | verify
"""
import argparse, fcntl, glob, hashlib, json, os, re, subprocess, sys, time

import m65_run as B

MODELS = B.MODELS
CAPS = B.CAPS
RUNNER = 'dd69_run_v1'
CODE = {'qwen': ['dd69_run.py', 'dd69_spec.py', 'dd69_fetch.py', 'dd69_build.py', 'dd69_cases.py', 'm65_run.py'],
        'medgemma': ['dd69_run.py', 'dd69_spec.py', 'dd69_fetch.py', 'dd69_build.py', 'dd69_cases.py', 'm65_run.py', 'msd56_run.py']}
DATA = 'results/iter_069/data'
REQ = {'main': f'{DATA}/requests_main.jsonl', 'R': f'{DATA}/requests_R.jsonl', 'tech': f'{DATA}/requests_tech.jsonl'}
LABELS, CASES, BMAN = f'{DATA}/labels.json', f'{DATA}/cases_private.json', f'{DATA}/build_manifest.json'
OUT_ROOT = os.path.realpath('results/iter_069')


def safe_out(p):
    """결과는 results/iter_069 아래로만 쓴다 (경로 이탈·symlink 구성요소 거부)."""
    ap = os.path.abspath(p)
    if os.path.commonpath([os.path.realpath(ap), OUT_ROOT]) != OUT_ROOT:
        sys.exit('write path outside results/iter_069: ' + p)
    cur = OUT_ROOT
    for part in os.path.relpath(ap, OUT_ROOT).split(os.sep):
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            sys.exit('symlink in write path: ' + cur)
    return ap


def components(model, full):
    B._setup_env(model)
    reqs = {k: B.sha_file(v) for k, v in REQ.items()}
    imgs = sorted({p for v in REQ.values() for r in B.read_jsonl(v) for p in r['images']})
    mid, rev = B.model_id_rev(model)
    mf = B.model_files(model, full)
    comp = {'model_key': model, 'runner': RUNNER, 'code': {f: B.sha_file(f) for f in CODE[model]}, 'requests': reqs,
            'labels': B.sha_file(LABELS), 'cases': B.sha_file(CASES), 'build_manifest': B.sha_file(BMAN),
            'images': {p: B.sha_file(p) for p in imgs}, 'model_id': mid, 'model_revision': rev, 'caps': CAPS,
            'gen_spec': 'greedy do_sample=False, checkpoint generation_config 유지, max_new_tokens=cap; cap512 비EOS만 2048 1회 재시도'}
    return comp, mf


def digest(comp, mf):
    return B.sha_s(json.dumps({'c': comp, 'm': {k: v.get('sha256') for k, v in mf.items()}}, sort_keys=True))


def cmd_lock(a):
    comp, mf = components(a.model, True)
    out = safe_out(a.out)
    if os.path.exists(out):
        sys.exit('protocol already exists')
    d = digest(comp, mf)
    with open(out, 'x') as f:
        json.dump({'digest': d, 'components': comp, 'model_files': mf, 'model': a.model, 'locked_at': time.strftime('%Y-%m-%dT%H:%M:%S')}, f, indent=1)
    print('locked', d)


def check_protocol(model, protocol, full=False):
    p = json.load(open(protocol))
    if p['model'] != model:
        sys.exit('protocol model mismatch')
    comp, mf = components(model, full)
    if comp != p['components']:
        sys.exit('PROTOCOL MISMATCH in ' + str([k for k in comp if comp[k] != p['components'].get(k)]))
    if set(mf) != set(p['model_files']):
        sys.exit('MODEL FILE SET MISMATCH')
    for f, ent in p['model_files'].items():
        cur = mf[f]
        if cur['size'] != ent['size'] or (full and cur['sha256'] != ent['sha256']):
            sys.exit('MODEL FILE MISMATCH ' + f)
        if not full and cur['mtime_ns'] != ent['mtime_ns'] and B.sha_file(os.path.realpath(os.path.join(B.snapshot_dir(model), f))) != ent['sha256']:
            sys.exit('MODEL FILE CONTENT MISMATCH ' + f)
    if digest(p['components'], p['model_files']) != p['digest']:
        sys.exit('PROTOCOL DIGEST TAMPERED')
    return p['digest']


def req_in_protocol(requests, protocol):
    p = json.load(open(protocol))
    if B.sha_file(requests) not in p['components']['requests'].values():
        sys.exit('requests file is not locked in protocol')


# ---------------- 실제 입력 구성 (backend: m65_run.build_inputs) ----------------
def run_one(model, torch, proc, m, eos, row):
    t_start = time.perf_counter()
    inp = B.build_inputs(model, proc, row)
    ids = inp['input_ids'][0].tolist()
    n_img = sum(1 for t in ids if t == B.image_token_id(model, m))
    ni = len(row['images'])
    if ni == 0:
        pxs, grids, exp = [], None, 0
        if 'pixel_values' in inp:
            raise RuntimeError('text-only request produced pixel_values ' + row['rid'])
    else:
        pxs, grids = B.per_image_pixels(model, inp)
        exp = B.expected_img_tokens(model, inp, ni)
    if n_img != exp or len(pxs) != ni:
        raise RuntimeError(f"input structure mismatch {row['rid']}: images={ni} tok={n_img}")
    t_proc = time.perf_counter()
    attempts = []
    for cap in CAPS:
        g = B.generate(torch, m, inp, cap, eos)
        g['text'] = proc.decode(g['suffix_ids'], skip_special_tokens=True)
        attempts.append(g)
        if g['ended_eos']:
            break
    rec = {'rid': row['rid'], 'cond': row['cond'], 'case': row['case'], 'n_input_tokens': len(ids), 'n_image_tokens': n_img, 'n_images': ni,
           'input_ids_sha': B.sha_s(json.dumps(ids)), 'img_pixel_sha': pxs, 'img_grid_thw': grids,
           'image_file_sha': [B.sha_file(p) for p in row['images']], 'attempts': attempts,
           'proc_s': t_proc - t_start, 'gen_attempts_s': time.perf_counter() - t_proc}
    return rec, t_start


def done_set(out_dir):
    return B.done_set(out_dir)


def cmd_worker(a):
    out_dir = safe_out(a.out_dir)
    req_in_protocol(a.requests, a.protocol)
    pdig = check_protocol(a.model, a.protocol)
    rows = B.read_jsonl(a.requests)
    by = {r['rid']: r for r in rows}
    os.makedirs(f'{out_dir}/claims', exist_ok=True)
    lockf = open(f'{out_dir}/worker{a.worker}.lock', 'w')
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit('worker already running')
    out = f'{out_dir}/worker{a.worker}.jsonl'
    dropped = B.repair_tail(out)
    for f in glob.glob(f'{out_dir}/worker*.jsonl'):
        for r in B.read_jsonl(f):  # 중간 손상은 예외
            if r.get('protocol_digest') != pdig or r['rid'] not in by or r.get('runner') != RUNNER:
                sys.exit(f'existing record incompatible with protocol/requests: {f} {r.get("rid")}')
    tl = time.perf_counter()
    torch, proc, m = B.load_model(a.model)
    env = B.env_info(a.model, torch, proc, m)
    load_s = time.perf_counter() - tl
    eos_cfg = m.generation_config.eos_token_id
    eos = set(eos_cfg if isinstance(eos_cfg, list) else [eos_cfg])
    attempt = str(time.time_ns())
    with open(f'{out_dir}/worker{a.worker}.attempt_{attempt}.json', 'w') as f:
        json.dump({'attempt': attempt, 'env': env, 'load_s': load_s, 'pid': os.getpid(), 'dropped_tail_bytes': dropped,
                   'n_done_at_start': len(done_set(out_dir)), 'gpu_env': os.environ.get('CUDA_VISIBLE_DEVICES'),
                   'gpu_uuid': str(torch.cuda.get_device_properties(0).uuid)}, f, default=str)
    meta = {'worker': a.worker, 'pid': os.getpid(), 'attempt': attempt}
    n, t0 = 0, time.perf_counter()
    for row in rows:
        if a.limit and n >= a.limit:
            break
        if row['rid'] in done_set(out_dir):
            continue
        if not B.claim(f'{out_dir}/claims', row['rid'], meta):
            continue
        if row['rid'] in done_set(out_dir):
            continue
        rec, ts = run_one(a.model, torch, proc, m, eos, row)
        rec['total_read_to_save_start_s'] = time.perf_counter() - ts
        rec.update({'protocol_digest': pdig, 'runner': RUNNER, 'worker': a.worker, 'attempt_id': attempt,
                    'answer_sha': B.sha_s(rec['attempts'][-1]['text'])})
        if a.die_after_write and n + 1 >= a.die_after_write:  # 시험용: 저장 후 즉시 강제 종료
            B.append_row(out, rec)
            os._exit(9)
        if a.torn_after and n + 1 >= a.torn_after:  # 시험용: 행 중간까지만 쓰고 종료
            b = (json.dumps(rec) + '\n').encode()
            with open(out, 'ab') as f:
                f.write(b[:len(b) // 2]); f.flush(); os.fsync(f.fileno())
            os._exit(9)
        t_sv = time.perf_counter()
        B.append_row(out, rec)
        B.append_row(f'{out_dir}/worker{a.worker}.cost', {'rid': row['rid'], 'save_s': time.perf_counter() - t_sv,
                                                           'read_to_saved_s': time.perf_counter() - ts})
        n += 1
        print(f'w{a.worker} {n} {time.perf_counter() - t0:.0f}s', flush=True)
    print('worker done', n, time.perf_counter() - t0, flush=True)


# ---------------- launcher ----------------
def cmd_launch(a):
    """jobs: [{model, gpu, workers, protocol, out_dir, requests, tech, peak_gb}]."""
    jobs = json.load(open(a.jobs))
    allowed = os.environ.get('CUDA_VISIBLE_DEVICES')
    total, used = B.smi('memory.total'), B.smi('memory.used')
    need = {}
    for j in jobs:
        safe_out(j['out_dir'])
        req_in_protocol(j['requests'], j['protocol'])
        pd = check_protocol(j['model'], j['protocol'])
        if j.get('tech'):
            tj = json.load(open(j['tech']))
            if tj.get('fails', 1) != 0 or tj.get('protocol_digest') != pd or tj.get('model') != j['model'] or \
                    tj.get('requests_sha256', {}).get('main') != B.sha_file(REQ['main']):
                sys.exit('tech gate failed/mismatch ' + j['out_dir'])
        if allowed:
            assert str(j['gpu']) in allowed.split(','), 'GPU outside allowed set'
        need[j['gpu']] = need.get(j['gpu'], 0) + j['workers'] * (j['peak_gb'] * 1024 + 2048)
    for g, n in need.items():
        assert total[g][1] - used[g][1] >= n, f'GPU{g} free {total[g][1] - used[g][1]} < need {n} MiB'
    t0 = time.perf_counter()
    ps, wl, locks, prepared, widx = [], [], [], set(), {}
    for j in jobs:
        od = safe_out(j['out_dir'])
        os.makedirs(od, exist_ok=True)
        if od not in prepared:
            prepared.add(od)
            ll = open(f'{od}/launcher.lock', 'w')
            try:
                fcntl.flock(ll, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                sys.exit('another launcher is running for ' + od)
            locks.append(ll)
            for lf in glob.glob(f'{od}/worker*.lock'):
                f = open(lf, 'w')
                try:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    sys.exit(f'live worker holds {lf}')
                f.close()
            os.makedirs(f'{od}/claims', exist_ok=True)
            done = done_set(od)
            for c in glob.glob(f'{od}/claims/*.claim'):
                if os.path.basename(c)[:-6] not in done:
                    os.rename(c, f'{c}.stale_launch_{time.time_ns()}')
        for _ in range(j['workers']):
            w = widx.get(od, 0)
            widx[od] = w + 1
            env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(j['gpu']))
            cmd = [sys.executable, 'dd69_run.py', 'worker', '--model', j['model'], '--requests', j['requests'], '--protocol', j['protocol'],
                   '--out-dir', od, '--worker', str(w)]
            if a.limit:
                cmd += ['--limit', str(a.limit)]
            ps.append(subprocess.Popen(cmd, env=env, stdout=open(f'{od}/worker{w}.stdout.log', 'a'), stderr=subprocess.STDOUT))
            wl.append({'model': j['model'], 'out_dir': od, 'worker': w, 'gpu': j['gpu'], 'uuid': used[j['gpu']][0]})
    samples, rcs, tend = [], [None] * len(ps), [None] * len(ps)
    while any(r is None for r in rcs):
        time.sleep(2)
        rcs = [p.poll() for p in ps]
        for i, r in enumerate(rcs):
            if r is not None and tend[i] is None:
                tend[i] = time.perf_counter() - t0
        samples.append({g: u[1] for g, u in B.smi('memory.used').items()})
    comp = {'workers': wl, 'exit_codes': rcs, 'worker_end_s': tend, 'wall_monotonic_s': time.perf_counter() - t0,
            'peak_used_mib_all_gpus': {g: max(s[g] for s in samples) for g in samples[0]}, 'used_mib_before': {g: u[1] for g, u in used.items()},
            'CUDA_VISIBLE_DEVICES': allowed}
    for d in prepared:
        with open(f'{d}/launch_{time.time_ns()}.json', 'w') as f:
            json.dump(comp, f)
    print(comp)
    if any(rcs):
        sys.exit(1)


# ---------------- verify ----------------
def cmd_verify(a):
    out_dir = safe_out(a.out_dir)
    req_in_protocol(a.requests, a.protocol)
    pdig = check_protocol(a.model, a.protocol, full=True)
    rows = B.read_jsonl(a.requests)
    by = {r['rid']: r for r in rows}
    recs, files, problems = [], {}, []
    for f in sorted(glob.glob(f'{out_dir}/worker*.jsonl')):
        raw = open(f, 'rb').read()
        if raw and not raw.endswith(b'\n'):
            problems.append('torn tail in ' + f)
        recs += B.read_jsonl(f); files[f] = B.sha_file(f)
    ids = [r['rid'] for r in recs]
    if len(ids) != len(set(ids)):
        problems.append('duplicate records')
    if set(ids) != set(by):
        problems.append(f'missing {len(set(by) - set(ids))} extra {len(set(ids) - set(by))}')
    for r in recs:
        q = by.get(r['rid'])
        if not q:
            continue
        if r['protocol_digest'] != pdig or r.get('runner') != RUNNER:
            problems.append('protocol digest ' + r['rid'])
        if r['n_images'] != len(q['images']) or (r['n_images'] and r['n_image_tokens'] == 0) or (not r['n_images'] and r['n_image_tokens'] != 0):
            problems.append('image count/tokens ' + r['rid'])
        if r['image_file_sha'] != [B.sha_file(p) for p in q['images']]:
            problems.append('image file sha ' + r['rid'])
        if not r['attempts'] or any(x['cap'] not in CAPS for x in r['attempts']) or r['answer_sha'] != B.sha_s(r['attempts'][-1]['text']):
            problems.append('attempts/answer sha ' + r['rid'])
        if r['cond'] != q['cond'] or r['case'] != q['case']:
            problems.append('cond/case ' + r['rid'])
    cost_ids = []
    for f in glob.glob(f'{out_dir}/worker*.cost'):
        cost_ids += [x['rid'] for x in B.read_jsonl(f)]
    cost_missing = sorted(set(ids) - set(cost_ids))
    lm = {os.path.basename(f): json.load(open(f))['exit_codes'] for f in glob.glob(f'{out_dir}/launch_*.json')}
    nonEOS = [r['rid'] for r in recs if not r['attempts'][-1]['ended_eos']]
    res = {'n_requests': len(rows), 'n_records': len(recs), 'problems': problems[:20], 'n_problems': len(problems),
           'cost_rows_missing': cost_missing[:20], 'n_cost_missing': len(cost_missing), 'n_final_non_eos': len(nonEOS), 'final_non_eos': nonEOS[:20],
           'protocol_digest': pdig, 'requests_sha256': B.sha_file(a.requests), 'record_file_sha256': files, 'launch_exit_codes': lm,
           'sealed_at': time.strftime('%Y-%m-%dT%H:%M:%S')}
    vp = f'{out_dir}/verify.json'
    if os.path.exists(vp):
        os.rename(vp, f'{vp}.prev_{time.time_ns()}')
    with open(vp, 'w') as f:
        json.dump(res, f, indent=1)
    print({k: v for k, v in res.items() if k != 'record_file_sha256'})
    if problems:
        sys.exit(1)


# ---------------- tech ----------------
FORBID = ('restricted', 'restriction', 'hyperintense', 'hyperintensity', 'hypointense', 'hypointensity', 'low', 'high', 'adc', 'dwi', 'signal',
          'infarct', 'infarction', 'tumor', 'tumour', 'abscess', 'carcinoma', 'cancer', 'malignant', 'cytotoxic', 'oedema', 'edema')


def cmd_tech(a):
    """(1) wrapper vs 공식 processor 직접 구성 tensor (2) 영상 token/grid·순서 (3) prompt 재구성·누출 (4) 같은 영상 처리 tensor 동일
    (5) J_DA/J_AD 순서 반전·R 복제 (6) 텍스트 전용 요청은 pixel_values 없음. processor만 사용(GPU 불필요)."""
    import dd69_spec as S
    B._setup_env(a.model)
    import torch, transformers
    pdig = check_protocol(a.model, a.protocol)
    cases = {c['case']: c for c in json.load(open(CASES))['cases']}
    sets = {k: B.read_jsonl(v) for k, v in REQ.items()}
    if a.model == 'qwen':
        proc = transformers.AutoProcessor.from_pretrained(B.QID, revision=json.load(open(B.QFETCH))['revision'], cache_dir=B.QCACHE)
        img_id = proc.tokenizer.convert_tokens_to_ids('<|image_pad|>')
    else:
        import msd56_run as M
        proc = transformers.AutoProcessor.from_pretrained(M.MODEL_ID, revision=M.MODEL_REVISION)
        img_id = proc.tokenizer.convert_tokens_to_ids('<image_soft_token>')
        assert img_id == 262144, img_id
    single = {}
    def single_px(path):
        if path not in single:
            inp = B.build_inputs(a.model, proc, {'images': [path], 'prompt': 'x', 'rid': 'single'})
            single[path] = B.per_image_pixels(a.model, inp)[0][0]
        return single[path]
    fails, res, inv = 0, [], []
    for name, rows in sets.items():
        for r in rows:
            c = cases[r['case']]
            inp = B.build_inputs(a.model, proc, r)
            ims = B.open_images(r)
            msgs = [{'role': 'user', 'content': [{'type': 'image', 'image': im} for im in ims] + [{'type': 'text', 'text': r['prompt']}]}]
            if a.model == 'qwen':
                from qwen_vl_utils import process_vision_info
                t2 = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
                iis, vis = process_vision_info(msgs)
                kw = {'images': iis, 'videos': vis} if iis else {}
                ref = proc(text=[t2], padding=True, return_tensors='pt', **kw)
            else:
                t2 = proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
                ref = proc(text=t2, images=ims, return_tensors='pt', add_special_tokens=False) if ims else proc(text=t2, return_tensors='pt', add_special_tokens=False)
            ok_ids = torch.equal(inp['input_ids'], ref['input_ids'])
            ok_pv = ('pixel_values' in inp) == ('pixel_values' in ref) and (not ims or torch.equal(inp['pixel_values'], ref['pixel_values']))
            ok_grid = a.model != 'qwen' or not ims or torch.equal(inp['image_grid_thw'], ref['image_grid_thw'])
            ids = inp['input_ids'][0].tolist()
            text_all = proc.decode(ids)
            n_tok = sum(1 for t in ids if t == img_id)
            if ims:
                pxs, grids = B.per_image_pixels(a.model, inp)
                ok_struct = len(pxs) == len(ims) and n_tok == B.expected_img_tokens(a.model, inp, len(ims))
                ok_order = pxs == [single_px(p) for p in r['images']]
            else:
                ok_struct = n_tok == 0 and 'pixel_values' not in inp
                ok_order = True
            exp_prompt = S.prompt(r['cond'], c['target'], c['label'] if r['cond'] == 'O' else None)
            ok_prompt = r['prompt'] == exp_prompt and r['prompt'] in text_all
            if r['cond'] != 'O':
                lk = [w for w in FORBID if re.search(r'\b' + w + r'\b', c['target'].lower())]
            else:
                lk = []
            leak = [s for s in [c['dwi']['caption'], c['adc']['caption'], c['title']] if s and s in text_all] + lk
            res.append({'set': name, 'rid': r['rid'], 'ok_ids': ok_ids, 'ok_pv': ok_pv, 'ok_grid': ok_grid, 'ok_struct': ok_struct,
                        'ok_order': ok_order, 'ok_prompt': ok_prompt, 'leak': leak, 'n_input_tokens': len(ids), 'n_images': len(ims)})
            if not (ok_ids and ok_pv and ok_grid and ok_struct and ok_order and ok_prompt and not leak):
                fails += 1
    byk = {(r['case'], r['cond']): r for r in sets['main']}
    for n, c in cases.items():
        d, ad = os.path.relpath(os.path.join('results/iter_069', c['dwi']['remote_path'])), os.path.relpath(os.path.join('results/iter_069', c['adc']['remote_path']))
        exp = {'SD': [d], 'SA': [ad], 'A': [ad], 'J_DA': [d, ad], 'J_AD': [ad, d], 'T': [], 'O': []}
        for k, v in exp.items():
            if byk[(n, k)]['images'] != v:
                inv.append(('image list', n, k))
        if single_px(d) == single_px(ad):
            inv.append(('DWI and ADC processed tensors identical', n))
    for r in sets['R']:
        if len(set(r['images'])) != 1 or len(r['images']) != 2:
            inv.append(('R not duplicate', r['rid']))
    fails += len(inv)
    out = {'requests_sha256': {k: B.sha_file(v) for k, v in REQ.items()}, 'protocol_digest': pdig, 'model': a.model, 'n_checked': len(res),
           'fails': fails, 'invariance_failures': inv[:10], 'max_input_tokens': max(x['n_input_tokens'] for x in res),
           'transformers': transformers.__version__, 'torch': torch.__version__, 'details': res}
    op = safe_out(a.out)
    with open(op, 'x') as f:
        json.dump(out, f, indent=1)
    print('tech fails', fails, 'of', len(res), 'max tokens', out['max_input_tokens'])
    if fails:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd', required=True)
    for n in ('lock', 'worker', 'verify', 'tech', 'launch'):
        p = sp.add_parser(n)
        if n != 'launch':
            p.add_argument('--model', required=True, choices=MODELS)
        if n in ('worker', 'verify', 'tech'):
            p.add_argument('--protocol', required=True)
        if n in ('worker', 'verify'):
            p.add_argument('--out-dir', required=True); p.add_argument('--requests', required=True)
        if n == 'worker':
            p.add_argument('--worker', type=int, required=True); p.add_argument('--limit', type=int, default=0)
            p.add_argument('--die-after-write', type=int, default=0); p.add_argument('--torn-after', type=int, default=0)
        if n in ('lock', 'tech'):
            p.add_argument('--out', required=True)
        if n == 'launch':
            p.add_argument('--jobs', required=True); p.add_argument('--limit', type=int, default=0)
    a = ap.parse_args()
    {'lock': cmd_lock, 'worker': cmd_worker, 'launch': cmd_launch, 'verify': cmd_verify, 'tech': cmd_tech}[a.cmd](a)


if __name__ == '__main__':
    main()
