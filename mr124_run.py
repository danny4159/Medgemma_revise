"""iter_124: Qwen2.5-VL-7B-Instruct frozen 추론 (MR-RATE W 입력 8장, iter_123 prompt/parse 재사용). iter_123 경로에는 읽기만 한다.
서브명령: requests | lock | tech | worker | launch | verify
 - 요청: iter_123 W 요청(PNG 8장·순서·prompt)을 그대로 사용, 적격성 잠금(eligibility_lock.json)의 적격 23명 + 기술 4명.
 - JSONL: 소유 worker 시작 시 개행 없는 마지막 조각만 .corrupt_*로 보존·제거, 중간 손상은 예외. 다른 파일은 완결 행만 strict 파싱.
 - 답변+비용은 한 행에 원자적으로 기록. 고정 shard(index % n_workers)로 중복 할당 없음. worker별 flock, launcher는 out_dir flock.
 - protocol: 코드·요청·적격성 잠금·모델 파일 내용 hash·gen 설정을 잠그고 worker/launch/verify 진입 시 재검증.
"""
import argparse, fcntl, glob, hashlib, json, os, subprocess, sys, time

import mr123_run as R  # PROMPT / parse 재사용 (GEN 경로는 사용하지 않음)

QPKGS = '/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/environments/qwen25vl_pkgs'
QCACHE = '/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/environments/qwen25vl_cache'
QFETCH = 'results/iter_062/env/qwen_fetch.json'
QID = 'Qwen/Qwen2.5-VL-7B-Instruct'
QREV = 'cc594898137f460bfe9f0759e9844b3ce807cfb5'
OUTROOT = 'results/iter_124/'
DATA = OUTROOT + 'data/'
LOCK_ELIG = DATA + 'eligibility_lock.json'
CODE = ['mr124_run.py', 'mr123_run.py', 'mr123_data.py']
SRC123 = {'explore': 'results/iter_123/gen/explore/requests.jsonl', 'tech': 'results/iter_123/gen/tech/requests.jsonl'}
RUNNER = 'mr124_run_v1'
GEN_SPEC = 'greedy do_sample=False, checkpoint generation_config 유지(repetition_penalty 1.05 포함), max_new_tokens=cap, 이미지 해상도 기본(896x896 무축소)'


def sha_s(x):
    return hashlib.sha256(x if isinstance(x, bytes) else x.encode()).hexdigest()


def sha_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for ch in iter(lambda: f.read(1 << 22), b''):
            h.update(ch)
    return h.hexdigest()


def setup_env():
    os.environ['HF_HUB_OFFLINE'] = '1'
    if QPKGS not in sys.path:
        sys.path.insert(0, QPKGS)


# ---------------- jsonl ----------------
def read_jsonl(p):
    """완결(개행 종료) 행만 strict 파싱. 개행 없는 꼬리는 기록 중/torn row라 무시. 중간 손상은 예외."""
    if not os.path.exists(p):
        return []
    raw = open(p, 'rb').read()
    return [json.loads(l) for l in raw.split(b'\n')[:-1] if l.strip()]


def repair_tail(path):
    if not os.path.exists(path):
        return 0
    raw = open(path, 'rb').read()
    cut = raw.rfind(b'\n') + 1
    for l in raw[:cut].split(b'\n'):
        if l.strip():
            json.loads(l)
    if cut == len(raw):
        return 0
    open(f'{path}.corrupt_{time.time_ns()}', 'wb').write(raw[cut:])
    with open(path, 'r+b') as f:
        f.truncate(cut); f.flush(); os.fsync(f.fileno())
    return len(raw) - cut


def append_row(path, obj):
    b = (json.dumps(obj) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT)
    try:
        if os.write(fd, b) != len(b):
            raise IOError('short write')
        os.fsync(fd)
    finally:
        os.close(fd)


# ---------------- requests ----------------
def build_requests(stage):
    """stage: explore(적격 23명) | tech(기술 4명). iter_123의 W 요청을 읽어 새 id로 재구성."""
    el = json.load(open(LOCK_ELIG))
    assert el['proceed'] and not el['qwen_outputs_exist_at_lock']
    src = [r for r in R.read_jsonl(SRC123[stage]) if r['cond'] == 'W']
    if stage == 'explore':
        want = [r['study_uid'] for r in el['rows'] if r['eligible']]
        order = {r['study_uid']: r['hash124'] for r in el['rows']}
    else:
        L = json.load(open('results/iter_123/data/selection_lock.json'))
        tech = [m for m in L['manifest'] if m['role'] == 'tech']
        order = {m['study_uid']: sha_s(f"124|{m['patient_uid']}|{m['study_uid']}") for m in tech}
        want = []
        for lab in ('positive', 'negative'):
            c = sorted([m for m in tech if m['label'] == lab], key=lambda m: order[m['study_uid']])
            want += [m['study_uid'] for m in c[:2]]
    by = {r['study_uid']: r for r in src}
    out = []
    for sid in sorted(want, key=lambda s: order[s]):
        r = by[sid]
        assert r['prompt'] == R.PROMPT.format(n=8, order='ordered from inferior to superior') and len(r['paths']) == 8
        out.append(dict(id=sha_s('|'.join(['124', 'qwen', r['id'], QREV]))[:20], orig_id=r['id'], study_uid=sid, patient_uid=r['patient_uid'],
                        cond='W', paths=r['paths'], png_sha256=r['png_sha256'], slice_idx=r['slice_idx'], prompt=r['prompt'],
                        label=r['label'], batch_id=r['batch_id'], stage=stage, model=QID, revision=QREV))
    return out


def cmd_requests(a):
    p = f'{OUTROOT}gen/{a.stage}/requests.jsonl'
    assert not os.path.exists(p), 'requests 잠금 존재'
    rows = build_requests(a.stage)
    for r in rows:
        assert [sha_file(x) for x in r['paths']] == r['png_sha256'], 'PNG hash 불일치'
    assert len({r['id'] for r in rows}) == len(rows)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')
    print(len(rows), 'requests', sha_file(p))


# ---------------- protocol ----------------
def snapshot_dir():
    return json.load(open(QFETCH))['snapshot_path']


def model_files(full):
    snap = snapshot_dir()
    out = {}
    for f in sorted(os.listdir(snap)):
        real = os.path.realpath(os.path.join(snap, f))
        st = os.stat(real)
        e = {'size': st.st_size}
        if full:
            e['sha256'] = sha_file(real)
        out[f] = e
    return out


def components(requests):
    rows = read_jsonl(requests)
    q = json.load(open(QFETCH))
    assert q['revision'] == QREV
    return {'runner': RUNNER, 'code': {f: sha_file(f) for f in CODE}, 'requests': sha_file(requests), 'eligibility_lock': sha_file(LOCK_ELIG),
            'images': {p: sha_file(p) for r in rows for p in r['paths']}, 'model_id': QID, 'model_revision': QREV,
            'fetch_record_files': {k: v['sha256'] for k, v in q['files'].items()}, 'gen_spec': GEN_SPEC}


def digest(comp, mf):
    return sha_s(json.dumps({'c': comp, 'm': {k: v['sha256'] for k, v in mf.items()}}, sort_keys=True))


def cmd_lock(a):
    comp = components(a.requests)
    mf = model_files(True)
    for k, v in mf.items():  # 기존 fetch 기록과 대조
        assert comp['fetch_record_files'].get(k) == v['sha256'], 'model file hash != qwen_fetch.json: ' + k
    assert not os.path.exists(a.out)
    d = digest(comp, mf)
    json.dump({'digest': d, 'components': comp, 'model_files': mf, 'requests_file': a.requests, 'locked_at': time.strftime('%Y-%m-%dT%H:%M:%S')},
              open(a.out, 'w'), indent=1)
    print('locked', d)


def check_protocol(requests, protocol, full=False):
    p = json.load(open(protocol))
    comp = components(requests)
    if comp != p['components']:
        sys.exit('PROTOCOL MISMATCH ' + str([k for k in comp if comp[k] != p['components'].get(k)]))
    mf = model_files(full)
    if set(mf) != set(p['model_files']):
        sys.exit('MODEL FILE SET MISMATCH')
    for f, e in p['model_files'].items():
        if mf[f]['size'] != e['size'] or (full and mf[f]['sha256'] != e['sha256']):
            sys.exit('MODEL FILE MISMATCH ' + f)
    if digest(p['components'], p['model_files']) != p['digest']:
        sys.exit('PROTOCOL DIGEST TAMPERED')
    return p['digest']


# ---------------- model / inputs ----------------
def load_model():
    setup_env()
    import torch, transformers
    torch.manual_seed(0)
    proc = transformers.AutoProcessor.from_pretrained(QID, revision=QREV, cache_dir=QCACHE)
    m = transformers.Qwen2_5_VLForConditionalGeneration.from_pretrained(QID, revision=QREV, cache_dir=QCACHE, dtype=torch.bfloat16, device_map='cuda')
    m.eval()
    return torch, proc, m


def messages(row):
    from PIL import Image
    content = []
    for i, p in enumerate(row['paths']):
        content.append({'type': 'text', 'text': f'Image {i + 1}:'})
        content.append({'type': 'image', 'image': Image.open(p).convert('RGB')})
    content.append({'type': 'text', 'text': row['prompt']})
    return [{'role': 'user', 'content': content}]


def build_inputs(proc, row):
    """공식 모델 카드 경로: apply_chat_template(tokenize=False) + qwen_vl_utils.process_vision_info + processor."""
    from qwen_vl_utils import process_vision_info
    msgs = messages(row)
    text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    imgs, vids = process_vision_info(msgs)
    return proc(text=[text], images=imgs, videos=vids, padding=True, return_tensors='pt')


def per_image_sha(inp):
    pv = inp['pixel_values'].float()
    out, s = [], 0
    for t, h, w in inp['image_grid_thw'].tolist():
        n = int(t * h * w)
        out.append(sha_s(pv[s:s + n].numpy().tobytes()))
        s += n
    assert s == pv.shape[0]
    return out


def generate(torch, m, inp_list, cap):
    x = {k: (torch.cat([i[k] for i in inp_list]) if k in ('pixel_values', 'image_grid_thw') else torch.cat([i[k] for i in inp_list]))
         for k in inp_list[0].keys()}
    x = {k: (v.to('cuda', dtype=torch.bfloat16) if k == 'pixel_values' else v.to('cuda')) for k, v in x.items()}
    torch.cuda.synchronize(); torch.cuda.reset_peak_memory_stats()
    t0 = time.perf_counter()
    with torch.no_grad():
        out = m.generate(**x, max_new_tokens=cap, do_sample=False)
    torch.cuda.synchronize()
    return out[:, x['input_ids'].shape[1]:].tolist(), time.perf_counter() - t0, torch.cuda.max_memory_allocated() / 2**30


def finish(proc, ids, eos):
    ended = any(t in eos for t in ids)
    cut = next((i for i, t in enumerate(ids) if t in eos), len(ids))
    ids = ids[:cut + 1] if ended else ids
    text = proc.decode([t for t in ids if t not in eos], skip_special_tokens=True)
    return ids, ended, text


# ---------------- worker ----------------
def shard(rows, wid, nw):
    return [r for i, r in enumerate(rows) if i % nw == wid]


def done_set(out_dir):
    d = set()
    for f in glob.glob(f'{out_dir}/worker*.jsonl'):
        d |= {r['id'] for r in read_jsonl(f)}
    return d


def cmd_worker(a):
    pdig = check_protocol(a.requests, a.protocol)
    rows = read_jsonl(a.requests)
    mine = shard(rows, a.worker, a.n_workers)
    os.makedirs(a.out_dir, exist_ok=True)
    lockf = open(f'{a.out_dir}/worker{a.worker}.lock', 'w')
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit('worker already running')
    out = f'{a.out_dir}/worker{a.worker}.jsonl'
    dropped = repair_tail(out)
    ids = {r['id'] for r in rows}
    for f in glob.glob(f'{a.out_dir}/worker*.jsonl'):
        for r in read_jsonl(f):
            if r.get('protocol_digest') != pdig or r['id'] not in ids or r.get('cap') != a.cap:
                sys.exit(f'기존 record가 protocol/cap과 호환되지 않음: {f} {r.get("id")}')
    tl = time.perf_counter()
    torch, proc, m = load_model()
    load_s = time.perf_counter() - tl
    eos_cfg = m.generation_config.eos_token_id
    eos = set(eos_cfg if isinstance(eos_cfg, list) else [eos_cfg])
    import transformers, PIL, importlib.metadata as im
    attempt = str(time.time_ns())
    json.dump({'attempt': attempt, 'load_s': load_s, 'pid': os.getpid(), 'dropped_tail_bytes': dropped, 'cap': a.cap, 'batch': a.batch,
               'transformers': transformers.__version__, 'torch': torch.__version__, 'PIL': PIL.__version__, 'qwen_vl_utils': im.version('qwen-vl-utils'),
               'cuda_visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES'), 'gpu_name': torch.cuda.get_device_name(0),
               'generation_config': m.generation_config.to_dict(), 'chat_template_sha256': sha_s(proc.chat_template or ''), 'n_done_at_start': len(done_set(a.out_dir))},
              open(f'{a.out_dir}/worker{a.worker}.attempt_{attempt}.json', 'w'), default=str)
    n, t0 = 0, time.perf_counter()
    todo = [r for r in mine if r['id'] not in done_set(a.out_dir)]
    for i in range(0, len(todo), a.batch):
        grp = todo[i:i + a.batch]
        ts = time.perf_counter()
        inps = [build_inputs(proc, r) for r in grp]
        if len({i_['input_ids'].shape[1] for i_ in inps}) != 1:
            raise RuntimeError('batch 내 길이가 달라 padding 필요: 지원하지 않음')
        tp = time.perf_counter()
        gen, gs, peak = generate(torch, m, inps, a.cap)
        for r, inp, g in zip(grp, inps, gen):
            ids, ended, text = finish(proc, g, eos)
            st, code = R.parse(text)
            rec = dict(id=r['id'], orig_id=r['orig_id'], study_uid=r['study_uid'], cond='W', stage=r['stage'], text=text, state=st, parse_code=code,
                       eos=bool(ended), n_new=len(ids), cap=a.cap, prompt_tokens=int(inp['input_ids'].shape[1]),
                       n_image_tokens=int((inp['input_ids'] == m.config.image_token_id).sum()), image_grid_thw=inp['image_grid_thw'].tolist(),
                       input_ids_sha=sha_s(inp['input_ids'][0].numpy().tobytes()), img_pixel_sha=per_image_sha(inp),
                       suffix_ids_sha=sha_s(json.dumps(ids)), answer_sha=sha_s(text), image_file_sha=[sha_file(p) for p in r['paths']],
                       protocol_digest=pdig, worker=a.worker, attempt_id=attempt, batch=a.batch, prep_s=tp - ts, gen_s=gs, peak_mem_alloc_gb=peak,
                       load_s=load_s)
            if a.die_after and n + 1 >= a.die_after:
                append_row(out, rec); os._exit(9)
            rec['read_to_save_s'] = time.perf_counter() - ts  # PNG 읽기~answer 행 write 직전 (batch>1이면 batch 전체 구간; fsync 수 ms는 미포함)
            append_row(out, rec)
            n += 1
        print(f'w{a.worker} {n}/{len(todo)} {time.perf_counter() - t0:.0f}s', flush=True)
    print('worker done', n, time.perf_counter() - t0, flush=True)


# ---------------- launcher ----------------
def smi(q):
    o = subprocess.check_output(['nvidia-smi', f'--query-gpu=index,uuid,{q}', '--format=csv,noheader,nounits'], text=True)
    return {int(l.split(',')[0]): (l.split(',')[1].strip(), int(l.split(',')[2])) for l in o.strip().splitlines()}


def cmd_launch(a):
    check_protocol(a.requests, a.protocol)
    allowed = os.environ.get('CUDA_VISIBLE_DEVICES')
    gpus = [int(g) for g in a.gpus.split(',')]
    if allowed:
        assert all(str(g) in allowed.split(',') for g in gpus), 'GPU outside allowed set'
    total, used = smi('memory.total'), smi('memory.used')
    per = {g: gpus.count(g) for g in set(gpus)}
    for g, k in per.items():
        need = k * (a.peak_gb * 1024 + 2048)
        assert total[g][1] - used[g][1] >= need, f'GPU{g} free {total[g][1] - used[g][1]} < need {need} MiB'
    os.makedirs(a.out_dir, exist_ok=True)
    ll = open(f'{a.out_dir}/launcher.lock', 'w')
    try:
        fcntl.flock(ll, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit('another launcher running')
    for lf in glob.glob(f'{a.out_dir}/worker*.lock'):
        f = open(lf, 'w')
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            sys.exit('live worker holds ' + lf)
        f.close()
    t0, ps, wl = time.perf_counter(), [], []
    for w, g in enumerate(gpus):
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(g))
        cmd = [sys.executable, 'mr124_run.py', 'worker', '--requests', a.requests, '--protocol', a.protocol, '--out-dir', a.out_dir, '--worker', str(w),
               '--n-workers', str(len(gpus)), '--cap', str(a.cap), '--batch', str(a.batch)]
        ps.append(subprocess.Popen(cmd, env=env, stdout=open(f'{a.out_dir}/worker{w}.stdout.log', 'a'), stderr=subprocess.STDOUT))
        wl.append({'worker': w, 'gpu': g, 'uuid': used[g][0]})
    samples, rcs = [], [None] * len(ps)
    while any(r is None for r in rcs):
        time.sleep(2)
        rcs = [p.poll() for p in ps]
        samples.append({g: u[1] for g, u in smi('memory.used').items()})
    comp = {'workers': wl, 'exit_codes': rcs, 'wall_monotonic_s': time.perf_counter() - t0, 'cap': a.cap, 'batch': a.batch,
            'peak_used_mib_all_gpus': {g: max(s[g] for s in samples) for g in samples[0]}, 'used_mib_before': {g: u[1] for g, u in used.items()}}
    json.dump(comp, open(f'{a.out_dir}/launch_{time.time_ns()}.json', 'w'))
    print(comp)
    if any(rcs):
        sys.exit(1)


# ---------------- verify ----------------
def cmd_verify(a):
    pdig = check_protocol(a.requests, a.protocol, full=True)
    rows = read_jsonl(a.requests)
    by = {r['id']: r for r in rows}
    recs, files, problems = [], {}, []
    for f in sorted(glob.glob(f'{a.out_dir}/worker*.jsonl')):
        raw = open(f, 'rb').read()
        if raw and not raw.endswith(b'\n'):
            problems.append('torn tail ' + f)
        recs += read_jsonl(f); files[f] = sha_file(f)
    got = [r['id'] for r in recs]
    if len(got) != len(set(got)):
        problems.append('duplicate records')
    if set(got) != set(by):
        problems.append(f'missing {len(set(by) - set(got))} extra {len(set(got) - set(by))}')
    for r in recs:
        q = by.get(r['id'])
        if not q:
            continue
        if r['protocol_digest'] != pdig:
            problems.append('protocol ' + r['id'])
        if r['image_file_sha'] != q['png_sha256'] or r['image_file_sha'] != [sha_file(p) for p in q['paths']]:
            problems.append('image sha ' + r['id'])
        if r['answer_sha'] != sha_s(r['text']) or (r['state'], r['parse_code']) != R.parse(r['text']):
            problems.append('answer/parse ' + r['id'])
        if r['cap'] != a.cap or r['n_image_tokens'] != 8 * 1024 or len(r['img_pixel_sha']) != 8:
            problems.append('cap/image tokens ' + r['id'])
    lm = {os.path.basename(f): json.load(open(f))['exit_codes'] for f in glob.glob(f'{a.out_dir}/launch_*.json')}
    if not lm or any(c for v in lm.values() for c in v):
        problems.append(f'launch exit codes {lm}')
    res = {'n_requests': len(rows), 'n_records': len(recs), 'n_problems': len(problems), 'problems': problems[:20], 'n_eos': sum(r['eos'] for r in recs),
           'protocol_digest': pdig, 'record_file_sha256': files, 'launch_exit_codes': lm, 'sealed_at': time.strftime('%Y-%m-%dT%H:%M:%S')}
    assert not os.path.exists(a.out), 'verify output exists'
    json.dump(res, open(a.out, 'w'), indent=1)
    print({k: v for k, v in res.items() if k != 'record_file_sha256'})
    if problems:
        sys.exit(1)


# ---------------- tech ----------------
def cmd_tech(a):
    """공식 경로(process_vision_info) vs HF 기본 chat-template 경로(PIL 직접) tensor 대조, 영상별 PNG 순서, 누출 문자열, parser 재현."""
    setup_env()
    import torch, transformers
    pdig = check_protocol(a.requests, a.protocol)
    rows = read_jsonl(a.requests)
    proc = transformers.AutoProcessor.from_pretrained(QID, revision=QREV, cache_dir=QCACHE)
    res, fails = [], 0
    for r in rows:
        inp = build_inputs(proc, r)
        ref = proc.apply_chat_template(messages(r), add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors='pt')
        ok_ids = torch.equal(inp['input_ids'], ref['input_ids'])
        ok_pv = torch.equal(inp['pixel_values'], ref['pixel_values'])
        ok_grid = torch.equal(inp['image_grid_thw'], ref['image_grid_thw'])
        # 영상 k의 tensor == PNG k 단독 처리 결과 (순서 검증)
        from PIL import Image
        order_ok = True
        for k, (p, sh) in enumerate(zip(r['paths'], per_image_sha(inp))):
            one = proc.image_processor(images=[Image.open(p).convert('RGB')], return_tensors='pt')
            order_ok &= sha_s(one['pixel_values'].float().numpy().tobytes()) == sh
        ids = inp['input_ids'][0].tolist()
        n_img = sum(1 for t in ids if t == proc.tokenizer.convert_tokens_to_ids('<|image_pad|>'))
        txt = proc.decode(ids)
        order_txt = [txt.find(f'Image {i + 1}:') for i in range(8)]
        ok_txt = order_txt == sorted(order_txt) and min(order_txt) >= 0 and r['prompt'] in txt
        leak = [s for s in [r['study_uid'], str(r['patient_uid']), r['label'], r['batch_id']] if s in txt]
        grids = inp['image_grid_thw'].tolist()
        ok = ok_ids and ok_pv and ok_grid and order_ok and ok_txt and not leak and n_img == 8 * 1024 and all(g == [1, 64, 64] for g in grids)
        fails += not ok
        res.append({'id': r['id'], 'ok_ids': ok_ids, 'ok_pv': ok_pv, 'ok_grid': ok_grid, 'order_ok': order_ok, 'ok_text_order': ok_txt, 'leak': leak,
                    'n_input_tokens': len(ids), 'n_image_tokens': n_img, 'grids': grids[:1], 'ok': ok})
    out = {'requests_sha256': sha_file(a.requests), 'protocol_digest': pdig, 'n_checked': len(res), 'fails': fails, 'details': res}
    assert not os.path.exists(a.out)
    json.dump(out, open(a.out, 'w'), indent=1)
    print('tech fails', fails, 'of', len(res), 'tokens', res[0]['n_input_tokens'])
    if fails:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd', required=True)
    p = sp.add_parser('requests'); p.add_argument('--stage', required=True, choices=['explore', 'tech'])
    p = sp.add_parser('lock'); p.add_argument('--requests', required=True); p.add_argument('--out', required=True)
    for n in ('tech', 'worker', 'launch', 'verify'):
        p = sp.add_parser(n); p.add_argument('--requests', required=True); p.add_argument('--protocol', required=True)
        if n == 'tech':
            p.add_argument('--out', required=True)
        if n in ('worker', 'launch', 'verify'):
            p.add_argument('--out-dir', required=True); p.add_argument('--cap', type=int, default=512)
        if n == 'verify':
            p.add_argument('--out', required=True)
        if n in ('worker', 'launch'):
            p.add_argument('--batch', type=int, default=1)
        if n == 'worker':
            p.add_argument('--worker', type=int, required=True); p.add_argument('--n-workers', type=int, default=1)
            p.add_argument('--die-after', type=int, default=0)
        if n == 'launch':
            p.add_argument('--gpus', required=True); p.add_argument('--peak-gb', type=float, required=True)
    a = ap.parse_args()
    {'requests': cmd_requests, 'lock': cmd_lock, 'tech': cmd_tech, 'worker': cmd_worker, 'launch': cmd_launch, 'verify': cmd_verify}[a.cmd](a)


if __name__ == '__main__':
    main()
