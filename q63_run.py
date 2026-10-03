"""iter_063 소견 삭제 QA runner (Qwen2.5-VL-7B / MedGemma 1.5, T/J × 두 선택지 순서).

q62_run.py(Qwen)·mri61_run.py(MedGemma)의 입력 경로를 따르되 이번 계획의 보완을 직접 구현한다.
 - protocol: 코드·요청·labels·manifest·원천 파일·영상·model/processor 파일·캡 설정을 구성요소별로 잠그고 worker/launch/verify/tech가 진입 시 재검증.
 - claim 획득 후 디스크의 최신 완료 상태를 다시 확인(종료 worker가 끝낸 요청의 중복 생성 방지).
 - 답변 저장 후 비용 저장 전 중단: 재시작 시 비용 누락을 cost_missing 행으로 명시(추정 금지). verify는 답변↔비용(rid, attempt_id, answer_sha) 대응을 검사.
 - JSONL은 worker 시작 시 손상 tail만 .corrupt_*로 보존·정리하고, 그 외 읽기는 strict(손상 시 예외).
 - worker 수와 GPU 수 분리 launch(jobs 파일), 시작 직전 nvidia-smi 여유 admission, 허용 GPU 집합 검사.
서브명령: lock | worker | launch | verify | tech
"""
import argparse, fcntl, glob, hashlib, json, os, subprocess, sys, time

MODELS = ('qwen', 'medgemma')
QPKGS = '/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/environments/qwen25vl_pkgs'
QCACHE = '/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/environments/qwen25vl_cache'
QFETCH = 'results/iter_062/env/qwen_fetch.json'
QID = 'Qwen/Qwen2.5-VL-7B-Instruct'
HFHOME = '/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache'
CAPS = [512, 2048]
MANIFEST = 'results/iter_063/data/selection_manifest.json'
COMMON_CODE = ['q63_run.py', 'q63_manifest.py', 'mri61_spec.py', 'mri61_parse.py']
CODE = {'qwen': COMMON_CODE, 'medgemma': COMMON_CODE + ['msd56_run.py']}


def _setup_env(model):
    os.environ['HF_HUB_OFFLINE'] = '1'
    if model == 'qwen':
        if QPKGS not in sys.path:
            sys.path.insert(0, QPKGS)
    else:
        os.environ.setdefault('HF_HOME', HFHOME)


def sha_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for ch in iter(lambda: f.read(1 << 22), b''):
            h.update(ch)
    return h.hexdigest()


def sha_s(x):
    return hashlib.sha256(x if isinstance(x, bytes) else x.encode()).hexdigest()


def read_jsonl(p):
    """strict: 손상 줄은 예외(정리는 repair_tail이 worker 시작 시 담당)."""
    out = []
    if not os.path.exists(p):
        return out
    for l in open(p):
        if l.strip():
            out.append(json.loads(l))
    return out


def repair_tail(path):
    if not os.path.exists(path):
        return 0
    raw = open(path, 'rb').read()
    good = []
    for l in raw.split(b'\n'):
        if not l.strip():
            continue
        try:
            json.loads(l)
            good.append(l)
        except json.JSONDecodeError:
            break
    clean = b''.join(g + b'\n' for g in good)
    if clean != raw:
        open(f'{path}.corrupt_{time.time_ns()}', 'wb').write(raw)
        tmp = path + '.tmp'
        with open(tmp, 'wb') as f:
            f.write(clean); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
        return len(raw) - len(clean)
    return 0


# ---------------- model info / protocol ----------------
def model_info(model):
    if model == 'qwen':
        fm = json.load(open(QFETCH))
        return {'id': QID, 'revision': fm['revision'], 'files': {k: v['sha256'] for k, v in fm['files'].items()}}
    import msd56_run as M
    snap = f'{HFHOME}/hub/models--google--medgemma-1.5-4b-it/snapshots/{M.MODEL_REVISION}'
    files = {}
    for f in sorted(os.listdir(snap)):
        p = os.path.join(snap, f)
        real = os.path.realpath(p)
        files[f] = os.path.basename(real) if os.path.getsize(real) > (1 << 28) else sha_file(real)
    return {'id': M.MODEL_ID, 'revision': M.MODEL_REVISION, 'files': files}


def components(model, requests, labels):
    _setup_env(model)
    rows = read_jsonl(requests)
    imgs = sorted({p for r in rows for p in r['images']})
    src = 'results/iter_061/data'
    return {'model_key': model, 'code': {f: sha_file(f) for f in CODE[model]}, 'requests': sha_file(requests), 'labels': sha_file(labels),
            'selection_manifest': sha_file(MANIFEST), 'source_eligible_qa': sha_file(f'{src}/eligible_qa.json'),
            'source_selection_lock': sha_file(f'{src}/selection_lock.json'),
            'orig_E21_requests': sha_file('results/iter_062/data/E21_requests.jsonl'),
            'orig_D3_requests': sha_file('results/iter_062/data/D3_requests.jsonl'),
            'images': {p: sha_file(p) for p in imgs}, 'model': model_info(model), 'caps': CAPS,
            'gen_spec': 'greedy do_sample=False, checkpoint generation_config 유지, max_new_tokens=cap'}


def digest(comp):
    return sha_s(json.dumps(comp, sort_keys=True))


def cmd_lock(a):
    comp = components(a.model, a.requests, a.labels)
    assert not os.path.exists(a.out), 'protocol already exists'
    d = digest(comp)
    json.dump({'digest': d, 'components': comp, 'requests_file': a.requests, 'labels_file': a.labels, 'model': a.model,
               'locked_at': time.strftime('%Y-%m-%dT%H:%M:%S')}, open(a.out, 'w'), indent=1)
    print('locked', d)


def check_protocol(model, requests, labels, protocol):
    p = json.load(open(protocol))
    assert p['model'] == model, 'protocol model mismatch'
    comp = components(model, requests, labels)
    if digest(comp) != p['digest'] or comp != p['components']:
        sys.exit('PROTOCOL MISMATCH in ' + str([k for k in comp if comp[k] != p['components'].get(k)]))
    return p['digest']


# ---------------- backends ----------------
def load_model(model):
    _setup_env(model)
    import torch, transformers
    torch.manual_seed(0)
    if model == 'qwen':
        rev = json.load(open(QFETCH))['revision']
        proc = transformers.AutoProcessor.from_pretrained(QID, revision=rev, cache_dir=QCACHE)
        m = transformers.Qwen2_5_VLForConditionalGeneration.from_pretrained(QID, revision=rev, cache_dir=QCACHE, dtype=torch.bfloat16, device_map='cuda')
        m.eval()
        return torch, proc, m
    import msd56_run as M
    return M.load_model()


def env_info(model, torch, proc, m):
    import transformers, PIL
    if model == 'medgemma':
        import msd56_run as M
        return M.env_info(torch, proc, m)
    import importlib.metadata as im
    return {'model_id': QID, 'model_revision': json.load(open(QFETCH))['revision'], 'transformers': transformers.__version__,
            'torch': torch.__version__, 'PIL': PIL.__version__, 'qwen_vl_utils': im.version('qwen-vl-utils'), 'dtype': str(m.dtype),
            'cuda_visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES'), 'gpu_name': torch.cuda.get_device_name(0),
            'gpu_uuid': str(torch.cuda.get_device_properties(0).uuid), 'generation_config': m.generation_config.to_dict(),
            'chat_template_sha256': sha_s(proc.chat_template or '')}


def open_images(row):
    from PIL import Image
    return [Image.open(p).convert('RGB') for p in row['images']]


def build_inputs(model, proc, row):
    ims = open_images(row)
    if model == 'medgemma':
        content = [{'type': 'image', 'image': im} for im in ims] + [{'type': 'text', 'text': row['prompt']}]
        return proc.apply_chat_template([{'role': 'user', 'content': content}], add_generation_prompt=True, tokenize=True,
                                        return_dict=True, return_tensors='pt')
    from qwen_vl_utils import process_vision_info
    msgs = [{'role': 'user', 'content': [{'type': 'image', 'image': im} for im in ims] + [{'type': 'text', 'text': row['prompt']}]}]
    text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    iis, _ = process_vision_info(msgs)
    return proc(text=[text], padding=True, return_tensors='pt', **({'images': iis} if iis else {}))


def image_token_id(model, m):
    return m.config.image_token_id if model == 'qwen' else m.config.image_token_index


def expected_img_tokens(model, inp, n_images):
    if model == 'medgemma':
        return 256 * n_images
    return int(sum(int(t * h * w) // 4 for t, h, w in inp['image_grid_thw'].tolist())) if n_images else 0


def generate(torch, m, inp, cap, eos_ids):
    x = {k: (v.to('cuda', dtype=torch.bfloat16) if k == 'pixel_values' else v.to('cuda')) for k, v in inp.items()}
    torch.cuda.synchronize(); torch.cuda.reset_peak_memory_stats()
    t0 = time.perf_counter()
    with torch.no_grad():
        out = m.generate(**x, max_new_tokens=cap, do_sample=False)
    torch.cuda.synchronize()
    dt = time.perf_counter() - t0
    ids = out[0, x['input_ids'].shape[1]:].tolist()
    return {'cap': cap, 'suffix_ids': ids, 'n_new': len(ids), 'ended_eos': bool(ids and ids[-1] in eos_ids), 'runtime_s': dt,
            'peak_mem_alloc_gb': torch.cuda.max_memory_allocated() / 2**30, 'peak_mem_reserved_gb': torch.cuda.max_memory_reserved() / 2**30}


def run_one(model, torch, proc, m, eos, row):
    t_start = time.perf_counter()
    inp = build_inputs(model, proc, row)
    ids = inp['input_ids'][0].tolist()
    n_img = sum(1 for t in ids if t == image_token_id(model, m))
    if n_img != expected_img_tokens(model, inp, len(row['images'])) or (len(row['images']) == 0) != ('pixel_values' not in inp):
        raise RuntimeError(f"input structure mismatch {row['rid']}: images={len(row['images'])} tok={n_img}")
    t_proc = time.perf_counter()
    attempts = []
    for cap in CAPS:
        g = generate(torch, m, inp, cap, eos)
        g['text'] = proc.decode(g['suffix_ids'], skip_special_tokens=True)
        attempts.append(g)
        if g['ended_eos']:
            break
    pv = inp['pixel_values'].float().numpy().tobytes() if 'pixel_values' in inp else None
    return {'rid': row['rid'], 'n_input_tokens': len(ids), 'n_image_tokens': n_img, 'n_images': len(row['images']),
            'input_ids_sha': sha_s(json.dumps(ids)), 'pixel_values_sha': sha_s(pv) if pv else None,
            'image_file_sha': [sha_file(p) for p in row['images']], 'attempts': attempts,
            'proc_s': t_proc - t_start, 'gen_attempts_s': time.perf_counter() - t_proc}, t_start


# ---------------- claims / worker ----------------
def pid_alive(pid):
    try:
        os.kill(pid, 0); return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def claim(claim_dir, rid, meta):
    p = f'{claim_dir}/{rid}.claim'
    for _ in range(2):
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, json.dumps(meta).encode()); os.close(fd)
            return True
        except FileExistsError:
            try:
                owner = json.load(open(p))
            except Exception:
                return False
            if pid_alive(owner.get('pid', -1)):
                return False
            try:
                os.rename(p, f'{p}.stale_{os.getpid()}_{time.time_ns()}')
            except FileNotFoundError:
                pass
    return False


def done_set(out_dir):
    d = set()
    for f in glob.glob(f'{out_dir}/worker*.jsonl'):
        d |= {r['rid'] for r in read_jsonl(f)}
    return d


def cmd_worker(a):
    pdig = check_protocol(a.model, a.requests, a.labels, a.protocol)
    rows = read_jsonl(a.requests)
    by = {r['rid']: r for r in rows}
    os.makedirs(f'{a.out_dir}/claims', exist_ok=True)
    lockf = open(f'{a.out_dir}/worker{a.worker}.lock', 'w')
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit('worker already running')
    out = f'{a.out_dir}/worker{a.worker}.jsonl'
    cost_out = f'{a.out_dir}/cost_worker{a.worker}.jsonl'
    dropped = repair_tail(out) + repair_tail(cost_out)
    for f in glob.glob(f'{a.out_dir}/worker*.jsonl'):
        for r in read_jsonl(f):
            if r.get('protocol_digest') != pdig or r['rid'] not in by:
                sys.exit(f'existing record incompatible with protocol: {f} {r.get("rid")}')
    # 답변은 있으나 비용이 없는 요청(저장 사이 중단): 추정하지 않고 cost_missing 으로 표시
    own = {r['rid']: r for r in read_jsonl(out)}
    have_cost = {c['rid'] for c in read_jsonl(cost_out)}
    with open(cost_out, 'a') as f:
        for rid, r in own.items():
            if rid not in have_cost:
                f.write(json.dumps({'rid': rid, 'attempt_id': r['attempt_id'], 'answer_sha': sha_s(r['attempts'][-1]['text']), 'cost_missing': True}) + '\n')
        f.flush(); os.fsync(f.fileno())
    tl = time.perf_counter()
    torch, proc, m = load_model(a.model)
    env = env_info(a.model, torch, proc, m)
    load_s = time.perf_counter() - tl
    eos_cfg = m.generation_config.eos_token_id
    eos = set(eos_cfg if isinstance(eos_cfg, list) else [eos_cfg])
    attempt = str(time.time_ns())
    json.dump({'attempt': attempt, 'env': env, 'load_s': load_s, 'pid': os.getpid(), 'dropped_tail_bytes': dropped,
               'n_done_at_start': len(done_set(a.out_dir)), 'gpu_env': os.environ.get('CUDA_VISIBLE_DEVICES')},
              open(f'{a.out_dir}/worker{a.worker}.attempt_{attempt}.json', 'w'), default=str)
    meta = {'worker': a.worker, 'pid': os.getpid(), 'attempt': attempt}
    n, t0 = 0, time.perf_counter()
    for row in rows:
        if a.limit and n >= a.limit:
            break
        if row['rid'] in done_set(a.out_dir):
            continue
        if not claim(f'{a.out_dir}/claims', row['rid'], meta):
            continue
        if row['rid'] in done_set(a.out_dir):  # claim 후 최신 완료 상태 재확인
            continue
        rec, ts = run_one(a.model, torch, proc, m, eos, row)
        rec.update({'protocol_digest': pdig, 'worker': a.worker, 'attempt_id': attempt})
        with open(out, 'a') as f:
            f.write(json.dumps(rec) + '\n'); f.flush(); os.fsync(f.fileno())
        t_end = time.perf_counter()
        with open(cost_out, 'a') as f:
            f.write(json.dumps({'rid': row['rid'], 'cond': row['cond'], 'attempt_id': attempt, 'answer_sha': sha_s(rec['attempts'][-1]['text']),
                                'total_read_to_flush_s': t_end - ts, 'n_attempts': len(rec['attempts']), 'in_tokens': rec['n_input_tokens'],
                                'out_tokens': [x['n_new'] for x in rec['attempts']], 'gen_s': [x['runtime_s'] for x in rec['attempts']]}) + '\n')
            f.flush(); os.fsync(f.fileno())
        n += 1
        print(f'w{a.worker} {n} {time.perf_counter() - t0:.0f}s', flush=True)
    print('worker done', n, time.perf_counter() - t0, flush=True)


# ---------------- launcher ----------------
def smi(q):
    o = subprocess.check_output(['nvidia-smi', f'--query-gpu=index,uuid,{q}', '--format=csv,noheader,nounits'], text=True)
    return {int(l.split(',')[0]): (l.split(',')[1].strip(), int(l.split(',')[2])) for l in o.strip().splitlines()}


def cmd_launch(a):
    """jobs: [{model, gpu, workers, protocol, out_dir, tech, peak_gb}]. 같은 requests/labels를 모두 사용."""
    jobs = json.load(open(a.jobs))
    allowed = os.environ.get('CUDA_VISIBLE_DEVICES')
    total, used = smi('memory.total'), smi('memory.used')
    need = {}
    for j in jobs:
        check_protocol(j['model'], a.requests, a.labels, j['protocol'])
        tj = json.load(open(j['tech']))
        if tj.get('fails', 1) != 0 or tj.get('requests_sha256') != sha_file(a.requests) or tj.get('protocol_digest') != json.load(open(j['protocol']))['digest']:
            sys.exit('tech gate failed/mismatch ' + j['out_dir'])
        if allowed:
            assert str(j['gpu']) in allowed.split(','), 'GPU outside allowed set'
        need[j['gpu']] = need.get(j['gpu'], 0) + j['workers'] * (j['peak_gb'] * 1024 + 2048)
    for g, n in need.items():
        assert total[g][1] - used[g][1] >= n, f'GPU{g} free {total[g][1] - used[g][1]} < need {n} MiB'
    t0 = time.perf_counter()
    ps, wl, locks = [], [], []
    for j in jobs:
        os.makedirs(j['out_dir'], exist_ok=True)
        ll = open(f"{j['out_dir']}/launcher.lock", 'w')
        try:
            fcntl.flock(ll, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            sys.exit('another launcher is running for ' + j['out_dir'])
        locks.append(ll)
        for lf in glob.glob(f"{j['out_dir']}/worker*.lock"):
            f = open(lf, 'w')
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                sys.exit(f'live worker holds {lf}')
            f.close()
        os.makedirs(f"{j['out_dir']}/claims", exist_ok=True)
        done = done_set(j['out_dir'])
        for c in glob.glob(f"{j['out_dir']}/claims/*.claim"):
            if os.path.basename(c)[:-6] not in done:
                os.rename(c, f'{c}.stale_launch_{time.time_ns()}')
        for w in range(j['workers']):
            env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(j['gpu']))
            cmd = [sys.executable, 'q63_run.py', 'worker', '--model', j['model'], '--requests', a.requests, '--labels', a.labels,
                   '--protocol', j['protocol'], '--out-dir', j['out_dir'], '--worker', str(w)]
            if a.limit:
                cmd += ['--limit', str(a.limit)]
            ps.append(subprocess.Popen(cmd, env=env, stdout=open(f"{j['out_dir']}/worker{w}.stdout.log", 'a'), stderr=subprocess.STDOUT))
            wl.append({'model': j['model'], 'out_dir': j['out_dir'], 'worker': w, 'gpu': j['gpu'], 'uuid': used[j['gpu']][0]})
    samples, rcs, tend = [], [None] * len(ps), [None] * len(ps)
    while any(r is None for r in rcs):
        time.sleep(2)
        rcs = [p.poll() for p in ps]
        for i, r in enumerate(rcs):
            if r is not None and tend[i] is None:
                tend[i] = time.perf_counter() - t0
        samples.append({g: u[1] for g, u in smi('memory.used').items()})
    comp = {'workers': wl, 'exit_codes': rcs, 'worker_end_s': tend, 'wall_monotonic_s': time.perf_counter() - t0,
            'peak_used_mib_all_gpus': {g: max(s[g] for s in samples) for g in samples[0]}, 'used_mib_before': {g: u[1] for g, u in used.items()}}
    for d in {j['out_dir'] for j in jobs}:
        json.dump(comp, open(f'{d}/launch_{time.time_ns()}.json', 'w'))
    print(comp)
    if any(rcs):
        sys.exit(1)


# ---------------- verify ----------------
def cmd_verify(a):
    pdig = check_protocol(a.model, a.requests, a.labels, a.protocol)
    rows = read_jsonl(a.requests)
    by = {r['rid']: r for r in rows}
    recs, files, problems = [], {}, []
    for f in sorted(glob.glob(f'{a.out_dir}/worker*.jsonl')):
        recs += read_jsonl(f); files[f] = sha_file(f)
    ids = [r['rid'] for r in recs]
    if len(ids) != len(set(ids)):
        problems.append('duplicate records')
    if set(ids) != set(by):
        problems.append(f'missing {len(set(by) - set(ids))} extra {len(set(ids) - set(by))}')
    for r in recs:
        q = by.get(r['rid'])
        if not q:
            continue
        if r['protocol_digest'] != pdig:
            problems.append('protocol digest ' + r['rid'])
        if r['n_images'] != len(q['images']) or (r['n_images'] == 0) != (r['n_image_tokens'] == 0):
            problems.append('image count/tokens ' + r['rid'])
        if r['image_file_sha'] != [sha_file(p) for p in q['images']]:
            problems.append('image file sha ' + r['rid'])
        if not r['attempts'] or any(x['cap'] not in CAPS for x in r['attempts']):
            problems.append('attempts ' + r['rid'])
    cost = {}
    for f in sorted(glob.glob(f'{a.out_dir}/cost_worker*.jsonl')):
        files[f] = sha_file(f)
        for c in read_jsonl(f):
            cost.setdefault(c['rid'], []).append(c)
    missing_cost = 0
    for r in recs:
        cs = [c for c in cost.get(r['rid'], []) if c['attempt_id'] == r['attempt_id'] and c['answer_sha'] == sha_s(r['attempts'][-1]['text'])]
        if len(cs) != 1:
            problems.append('cost link ' + r['rid'])
        elif cs[0].get('cost_missing'):
            missing_cost += 1
        elif cs[0]['n_attempts'] != len(r['attempts']):
            problems.append('cost attempts ' + r['rid'])
    lm = {os.path.basename(f): json.load(open(f))['exit_codes'] for f in glob.glob(f'{a.out_dir}/launch_*.json')}
    res = {'n_requests': len(rows), 'n_records': len(recs), 'problems': problems[:20], 'n_problems': len(problems), 'cost_missing': missing_cost,
           'protocol_digest': pdig, 'record_file_sha256': files, 'launch_exit_codes': lm, 'sealed_at': time.strftime('%Y-%m-%dT%H:%M:%S')}
    json.dump(res, open(f'{a.out_dir}/verify.json', 'w'), indent=1)
    print({k: v for k, v in res.items() if k != 'record_file_sha256'})
    if problems:
        sys.exit(1)


# ---------------- tech ----------------
def cmd_tech(a):
    """(1) 원문 대비 prompt 차이=삭제 문자열뿐, 영상·순열 동일 (2) adapter vs 공식 직접 호출 tensor (3) J가 원문 J와 동일 영상 tensor, T 영상 token 없음 (4) 누출 문자열."""
    _setup_env(a.model)
    import torch, transformers
    pdig = check_protocol(a.model, a.requests, a.labels, a.protocol)
    rows = read_jsonl(a.requests)
    man = json.load(open(MANIFEST))
    orig = {}
    for p in ('results/iter_062/data/E21_requests.jsonl', 'results/iter_062/data/D3_requests.jsonl'):
        for r in read_jsonl(p):
            orig[(r['cluster_id'], r['cond'], r['order'])] = r
    if a.model == 'qwen':
        proc = transformers.AutoProcessor.from_pretrained(QID, revision=json.load(open(QFETCH))['revision'], cache_dir=QCACHE)
        img_id = proc.tokenizer.convert_tokens_to_ids('<|image_pad|>')
    else:
        import msd56_run as M
        proc = transformers.AutoProcessor.from_pretrained(M.MODEL_ID, revision=M.MODEL_REVISION)
        img_id = None
    res, fails = [], 0
    for r in rows:
        o = orig[(r['cluster_id'], r['cond'], r['order'])]
        red = man['redaction'][str(r['qa_id'])]
        ok_text = (o['prompt'].replace(' ' + red['removed'], '', 1) == r['prompt'] and red['removed'] in o['prompt'] and red['removed'] not in r['prompt']
                   and o['images'] == r['images'] and o['perm'] == r['perm'] and r['prompt'].startswith(red['intro'] + ' ' + red['final']))
        inp = build_inputs(a.model, proc, r)
        inp_o = build_inputs(a.model, proc, o)
        # 공식 직접 호출
        ims = open_images(r)
        msgs = [{'role': 'user', 'content': [{'type': 'image', 'image': im} for im in ims] + [{'type': 'text', 'text': r['prompt']}]}]
        if a.model == 'qwen':
            from qwen_vl_utils import process_vision_info
            t2 = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
            iis, vis = process_vision_info(msgs)
            ref = proc(text=[t2], images=iis, videos=vis, padding=True, return_tensors='pt') if iis else proc(text=[t2], padding=True, return_tensors='pt')
        else:
            t2 = proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
            ref = proc(text=t2, images=ims, return_tensors='pt', add_special_tokens=False) if ims else proc(text=t2, return_tensors='pt', add_special_tokens=False)
        ok_ids = torch.equal(inp['input_ids'], ref['input_ids'])
        ok_pv = ('pixel_values' in inp) == ('pixel_values' in ref) and ('pixel_values' not in inp or torch.equal(inp['pixel_values'], ref['pixel_values']))
        ok_grid = a.model != 'qwen' or (('image_grid_thw' in inp) == ('image_grid_thw' in ref) and ('image_grid_thw' not in inp or torch.equal(inp['image_grid_thw'], ref['image_grid_thw'])))
        # 원문 J와 영상 입력 동일
        same_img = ('pixel_values' in inp) == ('pixel_values' in inp_o) and ('pixel_values' not in inp or torch.equal(inp['pixel_values'], inp_o['pixel_values']))
        if a.model == 'qwen' and 'image_grid_thw' in inp:
            same_img = same_img and torch.equal(inp['image_grid_thw'], inp_o['image_grid_thw'])
        ids = inp['input_ids'][0].tolist()
        if a.model == 'qwen':
            n_tok = sum(1 for t in ids if t == img_id)
            ok_n = n_tok == expected_img_tokens('qwen', inp, len(r['images']))
        else:
            n_tok = None
            ok_n = (len(r['images']) == 0) == ('pixel_values' not in inp) and ('pixel_values' not in inp or inp['pixel_values'].shape[0] == len(r['images']))
        ok_T = r['cond'] != 'T' or ('pixel_values' not in inp)
        text_all = proc.decode(ids)
        leak = [s for s in [str(r['cluster_id']), r['source']] + [os.path.basename(p) for p in r['images']] if s in text_all]
        ok = ok_text and ok_ids and ok_pv and ok_grid and same_img and ok_n and ok_T and not leak
        fails += not ok
        res.append({'rid': r['rid'], 'cond': r['cond'], 'order': r['order'], 'ok_text': ok_text, 'ok_ids': ok_ids, 'ok_pv': ok_pv, 'ok_grid': ok_grid,
                    'same_image_input_as_original': same_img, 'ok_structure': ok_n, 'ok_T_no_image': ok_T, 'leak': leak,
                    'n_input_tokens': int(inp['input_ids'].shape[1]), 'n_input_tokens_original': int(inp_o['input_ids'].shape[1])})
    out = {'requests_sha256': sha_file(a.requests), 'protocol_digest': pdig, 'model': a.model, 'n_checked': len(res), 'fails': fails, 'details': res,
           'max_input_tokens': max(x['n_input_tokens'] for x in res)}
    json.dump(out, open(a.out, 'w'), indent=1)
    print('tech fails', fails, 'of', len(res), 'max tokens', out['max_input_tokens'])
    if fails:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd', required=True)
    for n in ('lock', 'worker', 'verify', 'tech', 'launch'):
        p = sp.add_parser(n)
        p.add_argument('--requests', required=True); p.add_argument('--labels', required=True)
        if n != 'launch':
            p.add_argument('--model', required=True, choices=MODELS)
        if n in ('worker', 'verify', 'tech'):
            p.add_argument('--protocol', required=True)
        if n in ('worker', 'verify'):
            p.add_argument('--out-dir', required=True)
        if n == 'worker':
            p.add_argument('--worker', type=int, required=True); p.add_argument('--limit', type=int, default=0)
        if n in ('lock', 'tech'):
            p.add_argument('--out', required=True)
        if n == 'launch':
            p.add_argument('--jobs', required=True); p.add_argument('--limit', type=int, default=0)
    a = ap.parse_args()
    {'lock': cmd_lock, 'worker': cmd_worker, 'launch': cmd_launch, 'verify': cmd_verify, 'tech': cmd_tech}[a.cmd](a)


if __name__ == '__main__':
    main()
