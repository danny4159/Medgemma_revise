"""iter_062 Qwen2.5-VL-7B-Instruct MRI QA runner (T/J/S_i, 두 선택지 순서).

mri61_run.py(MedGemma, 수정 없이 보존)의 실행 구조를 따르되 이번 계획의 보완을 현재 경로에 직접 구현한다.
 - protocol: 코드·prompt·parser·labels·선택 manifest·원 annotation·영상 hash·model/processor revision·generation 설정을 구성요소별로 잠금.
   worker/launch/verify/tech 모두 진입 시 재검증(불일치 시 어떤 구성요소인지 출력하고 종료).
 - launcher 배타성(flock) + 요청 claim(O_EXCL) + worker별 출력 + 손상 tail 보존(.corrupt_*) 후 복구.
 - worker 수와 GPU 수 분리(--workers-per-gpu), 시작 직전 nvidia-smi 여유 기반 admission.
 - 저장 포함 timing: 입력 읽기→답변 flush/fsync 완료까지를 cost_worker*.jsonl sidecar에 기록(loading은 attempt json).
서브명령: lock | worker | launch | verify | tech
GT는 requests에 없으며 worker는 GT를 읽지 않는다.
"""
import argparse, fcntl, glob, hashlib, json, os, subprocess, sys, time
PKGS = '/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/environments/qwen25vl_pkgs'
if PKGS not in sys.path:
    sys.path.insert(0, PKGS)
os.environ['HF_HUB_OFFLINE'] = '1'
import mri61_spec as S
import mri61_parse as P

MODEL_ID = 'Qwen/Qwen2.5-VL-7B-Instruct'
CACHE = '/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/environments/qwen25vl_cache'
FETCH = 'results/iter_062/env/qwen_fetch.json'
DATA = 'results/iter_062/data'
CAPS = [512, 2048]
CODE = ['q62_run.py', 'mri61_spec.py', 'mri61_parse.py']
GEN_SPEC = {'do_sample': False, 'note': 'checkpoint generation_config(repetition_penalty 등) 유지, max_new_tokens=cap'}


def sha_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for ch in iter(lambda: f.read(1 << 22), b''):
            h.update(ch)
    return h.hexdigest()


def sha_s(x):
    return hashlib.sha256(x if isinstance(x, bytes) else x.encode()).hexdigest()


def revision():
    return json.load(open(FETCH))['revision']


def read_jsonl(p, strict=False):
    """정상 prefix만 반환. 손상 줄에서 중단. (rows, n_bad_tail_bytes)"""
    out = []
    if not os.path.exists(p):
        return out
    for l in open(p):
        if not l.strip():
            continue
        try:
            out.append(json.loads(l))
        except json.JSONDecodeError:
            if strict:
                raise
            break
    return out


# ---------------- protocol ----------------
def components(requests, labels):
    rows = read_jsonl(requests)
    fm = json.load(open(FETCH))
    imgs = sorted({p for r in rows for p in r['images']})
    return {'code': {f: sha_file(f) for f in CODE}, 'requests': sha_file(requests), 'labels': sha_file(labels),
            'selection_manifest': sha_file(f'{DATA}/selection_manifest.json'),
            'source_eligible_qa': sha_file(f'{S.DATA}/eligible_qa.json'),
            'source_selection_lock': sha_file(f'{S.DATA}/selection_lock.json'),
            'images': {p: sha_file(p) for p in imgs},
            'model': {'id': MODEL_ID, 'revision': fm['revision'],
                      'weights_files': {k: v['sha256'] for k, v in fm['files'].items()}},
            'caps': CAPS, 'instr_sha': sha_s(S.INSTR), 'gen_spec': GEN_SPEC}


def digest(comp):
    return sha_s(json.dumps(comp, sort_keys=True))


def cmd_lock(a):
    comp = components(a.requests, a.labels)
    d = digest(comp)
    assert not os.path.exists(a.out), 'protocol already exists'
    json.dump({'digest': d, 'components': comp, 'requests_file': a.requests, 'labels_file': a.labels,
               'locked_at': time.strftime('%Y-%m-%dT%H:%M:%S')}, open(a.out, 'w'), indent=1)
    print('locked', d)


def check_protocol(requests, labels, protocol):
    p = json.load(open(protocol))
    comp = components(requests, labels)
    if digest(comp) != p['digest'] or comp != p['components']:
        diff = [k for k in comp if comp[k] != p['components'].get(k)]
        sys.exit(f'PROTOCOL MISMATCH in {diff}')
    return p['digest']


# ---------------- model ----------------
def load_model():
    import torch, transformers
    torch.manual_seed(0)
    rev = revision()
    proc = transformers.AutoProcessor.from_pretrained(MODEL_ID, revision=rev, cache_dir=CACHE)
    model = transformers.Qwen2_5_VLForConditionalGeneration.from_pretrained(
        MODEL_ID, revision=rev, cache_dir=CACHE, dtype=torch.bfloat16, device_map='cuda')
    model.eval()
    return torch, proc, model


def env_info(torch, proc, model):
    import transformers, PIL, importlib.metadata as im
    gc = model.generation_config
    return {'model_id': MODEL_ID, 'model_revision': revision(), 'transformers': transformers.__version__,
            'torch': torch.__version__, 'PIL': PIL.__version__, 'qwen_vl_utils': im.version('qwen-vl-utils') if True else None,
            'dtype': str(model.dtype), 'cuda_visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES'),
            'gpu_name': torch.cuda.get_device_name(0), 'gpu_uuid': str(torch.cuda.get_device_properties(0).uuid),
            'generation_config': gc.to_dict(), 'chat_template_sha256': sha_s(proc.chat_template or ''),
            'image_processor': proc.image_processor.to_dict(),
            'attn_implementation': getattr(model.config, '_attn_implementation', None)}


def open_images(row):
    from PIL import Image
    return [Image.open(p).convert('RGB') for p in row['images']]


def build_inputs(proc, row, ims=None):
    """모델 카드 경로: apply_chat_template(tokenize=False) + process_vision_info + processor."""
    from qwen_vl_utils import process_vision_info
    ims = open_images(row) if ims is None else ims
    content = [{'type': 'image', 'image': im} for im in ims] + [{'type': 'text', 'text': row['prompt']}]
    msgs = [{'role': 'user', 'content': content}]
    text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    image_inputs, video_inputs = process_vision_info(msgs)
    kw = {'images': image_inputs} if image_inputs else {}
    inp = proc(text=[text], padding=True, return_tensors='pt', **kw)
    return inp, text


def generate(torch, model, inp, cap, eos_ids):
    x = {k: (v.to('cuda', dtype=torch.bfloat16) if k == 'pixel_values' else v.to('cuda')) for k, v in inp.items()}
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    t0 = time.perf_counter()
    with torch.no_grad():
        out = model.generate(**x, max_new_tokens=cap, do_sample=False)
    torch.cuda.synchronize()
    dt = time.perf_counter() - t0
    ids = out[0, x['input_ids'].shape[1]:].tolist()
    ended = len(ids) > 0 and ids[-1] in eos_ids
    return {'cap': cap, 'suffix_ids': ids, 'n_new': len(ids), 'ended_eos': bool(ended), 'runtime_s': dt,
            'peak_mem_alloc_gb': torch.cuda.max_memory_allocated() / 2**30,
            'peak_mem_reserved_gb': torch.cuda.max_memory_reserved() / 2**30}


def merge_len(grid):
    return int(sum(int(t * h * w) // 4 for t, h, w in grid))


def run_one(torch, proc, model, eos, row):
    t_start = time.perf_counter()
    ims = open_images(row)
    inp, text = build_inputs(proc, row, ims)
    ids = inp['input_ids'][0].tolist()
    n_img = sum(1 for t in ids if t == model.config.image_token_id)
    grid = inp['image_grid_thw'].tolist() if 'image_grid_thw' in inp else []
    if (len(row['images']) == 0) != (n_img == 0) or n_img != merge_len(grid) or len(grid) != len(row['images']):
        raise RuntimeError(f"input structure mismatch {row['rid']}: img={len(row['images'])} tok={n_img} grid={grid}")
    t_proc = time.perf_counter()
    attempts = []
    for cap in CAPS:
        g = generate(torch, model, inp, cap, eos)
        g['text'] = proc.decode(g['suffix_ids'], skip_special_tokens=True)
        attempts.append(g)
        if g['ended_eos']:
            break
    return {'rid': row['rid'], 'n_input_tokens': len(ids), 'n_image_tokens': n_img, 'n_images': len(row['images']),
            'image_grid_thw': grid, 'input_ids_sha': sha_s(json.dumps(ids)),
            'pixel_values_sha': sha_s(inp['pixel_values'].float().numpy().tobytes()) if 'pixel_values' in inp else None,
            'image_file_sha': [sha_file(p) for p in row['images']], 'attempts': attempts,
            'proc_s': t_proc - t_start, 'gen_attempts_s': time.perf_counter() - t_proc}, t_start


# ---------------- files / claims ----------------
def repair_tail(path):
    """손상된(불완전) 줄이 있으면 원본을 .corrupt_<ts>로 보존하고 정상 prefix만 원자적으로 재작성."""
    if not os.path.exists(path):
        return 0
    raw = open(path, 'rb').read()
    good, n = [], 0
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
        open(f'{path}.corrupt_{int(time.time() * 1000)}', 'wb').write(raw)
        tmp = path + '.tmp'
        with open(tmp, 'wb') as f:
            f.write(clean)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
        return len(raw) - len(clean)
    return 0


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
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
            # 소유 프로세스가 죽은 claim: 원자적으로 치우고 재시도(rename 승자만 진행)
            try:
                os.rename(p, f"{p}.stale_{os.getpid()}_{time.time_ns()}")
            except FileNotFoundError:
                pass
    return False


def done_set(out_dir):
    d = set()
    for f in glob.glob(f'{out_dir}/worker*.jsonl'):
        d |= {r['rid'] for r in read_jsonl(f)}
    return d


def cmd_worker(a):
    pdig = check_protocol(a.requests, a.labels, a.protocol)
    rows = read_jsonl(a.requests)
    by = {r['rid']: r for r in rows}
    os.makedirs(f'{a.out_dir}/claims', exist_ok=True)
    lockf = open(f'{a.out_dir}/worker{a.worker}.lock', 'w')
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit('worker already running')
    out = f'{a.out_dir}/worker{a.worker}.jsonl'
    dropped = repair_tail(out)
    done = done_set(a.out_dir)
    # 이전 worker 기록이 현재 protocol/요청과 다르면 재개 거부
    for f in glob.glob(f'{a.out_dir}/worker*.jsonl'):
        for r in read_jsonl(f):
            if r.get('protocol_digest') != pdig or r['rid'] not in by:
                sys.exit(f'existing record incompatible with protocol: {f} {r.get("rid")}')
    tl = time.perf_counter()
    torch, proc, model = load_model()
    env = env_info(torch, proc, model)
    load_s = time.perf_counter() - tl
    eos_cfg = model.generation_config.eos_token_id
    eos = set(eos_cfg if isinstance(eos_cfg, list) else [eos_cfg])
    attempt = str(time.time_ns())
    json.dump({'attempt': attempt, 'env': env, 'load_s': load_s, 'pid': os.getpid(), 'dropped_tail_bytes': dropped,
               'n_done_at_start': len(done), 'gpu_env': os.environ.get('CUDA_VISIBLE_DEVICES')},
              open(f'{a.out_dir}/worker{a.worker}.attempt_{attempt}.json', 'w'), default=str)
    meta = {'worker': a.worker, 'pid': os.getpid(), 'attempt': attempt}
    n = 0
    t0 = time.perf_counter()
    for row in rows:
        if row['rid'] in done or (a.limit and n >= a.limit):
            continue
        if not claim(f'{a.out_dir}/claims', row['rid'], meta):
            continue
        rec, ts = run_one(torch, proc, model, eos, row)
        rec.update({'protocol_digest': pdig, 'worker': a.worker, 'attempt_id': attempt})
        with open(out, 'a') as f:
            f.write(json.dumps(rec) + '\n')
            f.flush(); os.fsync(f.fileno())
        t_end = time.perf_counter()
        with open(f'{a.out_dir}/cost_worker{a.worker}.jsonl', 'a') as f:
            f.write(json.dumps({'rid': row['rid'], 'cond': row['cond'], 'K': row['K'], 'attempt_id': attempt,
                                'total_read_to_flush_s': t_end - ts,
                                'n_attempts': len(rec['attempts']),
                                'in_tokens': rec['n_input_tokens'],
                                'out_tokens': [x['n_new'] for x in rec['attempts']],
                                'gen_s': [x['runtime_s'] for x in rec['attempts']]}) + '\n')
            f.flush(); os.fsync(f.fileno())
        n += 1
        if n % 10 == 1:
            print(f'w{a.worker} {n} {time.perf_counter() - t0:.0f}s', flush=True)
    print('worker done', n, time.perf_counter() - t0, flush=True)


# ---------------- launcher ----------------
def smi(q):
    o = subprocess.check_output(['nvidia-smi', f'--query-gpu=index,uuid,{q}', '--format=csv,noheader,nounits'], text=True)
    return {int(l.split(',')[0]): (l.split(',')[1].strip(), int(l.split(',')[2])) for l in o.strip().splitlines()}


def cmd_launch(a):
    check_protocol(a.requests, a.labels, a.protocol)
    tj = json.load(open(a.tech))  # 기술 gate
    if tj.get('fails', 1) != 0 or tj.get('requests_sha256') != sha_file(a.requests) or tj.get('protocol_digest') != json.load(open(a.protocol))['digest']:
        sys.exit('tech gate failed/mismatch')
    os.makedirs(a.out_dir, exist_ok=True)
    ll = open(f'{a.out_dir}/launcher.lock', 'w')
    try:
        fcntl.flock(ll, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit('another launcher is running')
    gpus = [int(g) for g in a.gpus.split(',')]
    allowed = os.environ.get('CUDA_VISIBLE_DEVICES')
    if allowed:
        assert set(map(str, gpus)) <= set(allowed.split(',')), 'GPU outside allowed set'
    free = {g: tot[1] for g, tot in smi('memory.total').items()}
    used = {g: u[1] for g, u in smi('memory.used').items()}
    uuid = {g: u[0] for g, u in smi('memory.used').items()}
    need = {}
    for g in gpus:
        need[g] = need.get(g, 0) + a.workers_per_gpu * (a.peak_gb * 1024 + 2048)
    for g, n in need.items():
        assert free[g] - used[g] >= n, f'GPU{g} free {free[g] - used[g]} < need {n} MiB'
    # 실행 중 worker가 없는지 확인 후 죽은 claim 정리(rename으로 보존)
    for lf in glob.glob(f'{a.out_dir}/worker*.lock'):
        f = open(lf, 'w')
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            sys.exit(f'live worker holds {lf}')
        f.close()
    os.makedirs(f'{a.out_dir}/claims', exist_ok=True)
    done = done_set(a.out_dir)
    for c in glob.glob(f'{a.out_dir}/claims/*.claim'):
        if os.path.basename(c)[:-6] not in done:
            os.rename(c, f'{c}.stale_launch_{time.time_ns()}')
    t0 = time.perf_counter()
    ps, wl = [], []
    w = 0
    for g in gpus:
        for _ in range(a.workers_per_gpu):
            env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(g))
            cmd = [sys.executable, 'q62_run.py', 'worker', '--requests', a.requests, '--labels', a.labels,
                   '--protocol', a.protocol, '--out-dir', a.out_dir, '--worker', str(w)]
            if a.limit:
                cmd += ['--limit', str(a.limit)]
            ps.append(subprocess.Popen(cmd, env=env, stdout=open(f'{a.out_dir}/worker{w}.stdout.log', 'a'), stderr=subprocess.STDOUT))
            wl.append({'worker': w, 'gpu': g, 'uuid': uuid[g]})
            w += 1
    samples, rcs = [], [None] * len(ps)
    while any(r is None for r in rcs):
        time.sleep(3)
        rcs = [p.poll() for p in ps]
        samples.append({g: u[1] for g, u in smi('memory.used').items()})
    comp = {'workers': wl, 'exit_codes': rcs, 'wall_monotonic_s': time.perf_counter() - t0,
            'peak_used_mib_all_gpus': {g: max(s[g] for s in samples) for g in samples[0]} if samples else {},
            'used_mib_before': used, 'workers_per_gpu': a.workers_per_gpu}
    json.dump(comp, open(f'{a.out_dir}/launch_{time.time_ns()}.json', 'w'))
    print(comp)
    if any(rcs):
        sys.exit(1)


def cmd_verify(a):
    pdig = check_protocol(a.requests, a.labels, a.protocol)
    rows = read_jsonl(a.requests)
    by = {r['rid']: r for r in rows}
    recs, files = [], {}
    for f in sorted(glob.glob(f'{a.out_dir}/worker*.jsonl')):
        rr = read_jsonl(f)
        recs += rr
        files[f] = sha_file(f)
    problems = []
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
        if r['n_images'] != len(q['images']) or r['n_images'] != len(r['image_grid_thw']) or (r['n_images'] == 0) != (r['n_image_tokens'] == 0):
            problems.append('image count/tokens ' + r['rid'])
        if r['n_image_tokens'] != merge_len(r['image_grid_thw']):
            problems.append('image token count ' + r['rid'])
        if r['image_file_sha'] != [sha_file(p) for p in q['images']]:
            problems.append('image file sha ' + r['rid'])
        if not r['attempts'] or any(x['cap'] not in CAPS for x in r['attempts']):
            problems.append('attempts ' + r['rid'])
    cost_ids = set()
    for f in glob.glob(f'{a.out_dir}/cost_worker*.jsonl'):
        cost_ids |= {c['rid'] for c in read_jsonl(f)}
    if set(ids) - cost_ids:
        problems.append(f'cost sidecar missing {len(set(ids) - cost_ids)}')
    lm = {}
    for f in glob.glob(f'{a.out_dir}/launch_*.json'):
        lm[os.path.basename(f)] = json.load(open(f))['exit_codes']
    res = {'n_requests': len(rows), 'n_records': len(recs), 'problems': problems[:20], 'n_problems': len(problems),
           'protocol_digest': pdig, 'record_file_sha256': files, 'launch_exit_codes': lm,
           'sealed_at': time.strftime('%Y-%m-%dT%H:%M:%S')}
    json.dump(res, open(f'{a.out_dir}/verify.json', 'w'), indent=1)
    print({k: v for k, v in res.items() if k != 'record_file_sha256'})
    if problems:
        sys.exit(1)


# ---------------- tech ----------------
def cmd_tech(a):
    """adapter vs 모델 카드 직접 호출 대조: input_ids·pixel_values·image_grid_thw, T 영상 token 부재, S_i⊂J, 누출 문자열 부재."""
    import torch, transformers
    from qwen_vl_utils import process_vision_info
    proc = transformers.AutoProcessor.from_pretrained(MODEL_ID, revision=revision(), cache_dir=CACHE)
    pdig = check_protocol(a.requests, a.labels, a.protocol)
    rows = read_jsonl(a.requests)
    labels = json.load(open(a.labels))
    img_id = proc.tokenizer.convert_tokens_to_ids('<|image_pad|>')
    res, fails, cache = [], 0, {}
    for r in rows:
        inp, text = build_inputs(proc, r)
        # 모델 카드 예제를 그대로 옮긴 독립 호출
        ims = open_images(r)
        msgs = [{'role': 'user', 'content': [{'type': 'image', 'image': im} for im in ims] + [{'type': 'text', 'text': r['prompt']}]}]
        t2 = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        iis, vis = process_vision_info(msgs)
        ref = proc(text=[t2], images=iis, videos=vis, padding=True, return_tensors='pt') if iis else proc(text=[t2], padding=True, return_tensors='pt')
        ok_ids = torch.equal(inp['input_ids'], ref['input_ids'])
        ok_grid = ('image_grid_thw' in inp) == ('image_grid_thw' in ref) and ('image_grid_thw' not in inp or torch.equal(inp['image_grid_thw'], ref['image_grid_thw']))
        ok_pv = ('pixel_values' in inp) == ('pixel_values' in ref) and ('pixel_values' not in inp or torch.equal(inp['pixel_values'], ref['pixel_values']))
        n_tok = int((inp['input_ids'] == img_id).sum())
        grid = inp['image_grid_thw'].tolist() if 'image_grid_thw' in inp else []
        ok_n = (n_tok == merge_len(grid)) and len(grid) == len(r['images']) and ((len(r['images']) == 0) == ('pixel_values' not in inp))
        # 누출 문자열: 파일명·cluster·source·정답 문자열이 chat text에 없어야 함(정답 텍스트는 선택지로는 존재하므로 'ANSWER_TEXT' 대신 파일명/id만 검사)
        leak = [s for s in [r['cluster_id'], r['source']] + [os.path.basename(p) for p in r['images']] if s in text]
        # source 이름이 질문 본문에 자연히 포함되지 않는지 확인(PubMedVision 등)
        ok_leak = not leak
        key = (r['cluster_id'], r['cond'], r['order'])
        cache[key] = inp
        res.append({'rid': r['rid'], 'cond': r['cond'], 'order': r['order'], 'K': r['K'], 'ok_ids': ok_ids, 'ok_grid': ok_grid,
                    'ok_pv': ok_pv, 'ok_structure': ok_n, 'ok_no_leak': ok_leak, 'n_input_tokens': int(inp['input_ids'].shape[1]),
                    'n_image_tokens': n_tok, 'grid': grid})
        fails += not (ok_ids and ok_grid and ok_pv and ok_n and ok_leak)
    sub = []
    for (cid, cond, order), inp in cache.items():
        if cond.startswith('S'):
            i = int(cond[1:]) - 1
            J = cache[(cid, 'J', order)]
            g = J['image_grid_thw'].tolist()
            off = sum(int(t * h * w) for t, h, w in g[:i])
            n = int(g[i][0] * g[i][1] * g[i][2])
            good = torch.equal(J['pixel_values'][off:off + n], inp['pixel_values']) and inp['image_grid_thw'].tolist() == [g[i]]
            sub.append({'cluster': cid, 'cond': cond, 'order': order, 'S_equals_J_slice': bool(good)})
            fails += not good
    # 두 순서에서 영상 입력이 동일(prompt만 다름)
    ord_ok = 0
    for (cid, cond, order), inp in cache.items():
        if order == 'F':
            o = cache[(cid, cond, 'R')]
            same = ('pixel_values' in inp) == ('pixel_values' in o) and ('pixel_values' not in inp or torch.equal(inp['pixel_values'], o['pixel_values']))
            ord_ok += same
            fails += not same
    out = {'requests_sha256': sha_file(a.requests), 'protocol_digest': pdig, 'n_checked': len(res), 'fails': fails,
           'subset_order': sub, 'order_pixel_equal': ord_ok, 'details': res,
           'max_input_tokens': max(x['n_input_tokens'] for x in res)}
    json.dump(out, open(a.out, 'w'), indent=1)
    print('tech fails', fails, 'of', len(res), '+', len(sub), '+', ord_ok, 'max tokens', out['max_input_tokens'])
    if fails:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd', required=True)
    l = sp.add_parser('lock'); l.add_argument('--requests', required=True); l.add_argument('--labels', required=True); l.add_argument('--out', required=True)
    for n in ('worker', 'launch', 'verify', 'tech'):
        p = sp.add_parser(n)
        p.add_argument('--requests', required=True); p.add_argument('--labels', required=True); p.add_argument('--protocol', required=True)
        if n != 'tech':
            p.add_argument('--out-dir', required=True)
        if n == 'worker':
            p.add_argument('--worker', type=int, required=True); p.add_argument('--limit', type=int, default=0)
        if n == 'launch':
            p.add_argument('--tech', required=True); p.add_argument('--gpus', required=True); p.add_argument('--workers-per-gpu', type=int, default=1)
            p.add_argument('--peak-gb', type=float, default=18); p.add_argument('--limit', type=int, default=0)
        if n == 'tech':
            p.add_argument('--out', required=True)
    a = ap.parse_args()
    {'lock': cmd_lock, 'worker': cmd_worker, 'launch': cmd_launch, 'verify': cmd_verify, 'tech': cmd_tech}[a.cmd](a)


if __name__ == '__main__':
    main()
