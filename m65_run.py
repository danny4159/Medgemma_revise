"""iter_065 S/R/C target-slice runner (Qwen2.5-VL-7B / MedGemma 1.5). q63_run.py의 입력·backend 경로를 따르되 계획의 수정을 구현.

수정점(q63 대비)
 - JSONL: 소유 worker 시작 시 '개행 없는 마지막 행'만 .corrupt_*로 보존 후 제거. 중간 손상은 예외. 다른 worker 파일 읽기는 완결(개행) 행만 읽어
   기록 중인 꼬리 행과의 경합을 막고, 중간 손상은 예외.
 - 답변과 비용(attempt 시간·token)은 한 행(원자적 단일 write)에 저장 -> 답변↔비용 연결 누락이 구조적으로 없음.
 - claim 후 완료 상태 재확인, 종료 worker의 claim은 stale 처리. launcher는 out_dir 단위 flock.
 - protocol: 코드·요청·labels·target manifest·원천(cases/case_order/msd56_data)·영상·모델/processor 파일 '내용 hash'(lock 시 전체, worker는 stat 일치+소형 파일 내용,
   verify는 전체 재hash)·캡 설정을 잠그고 worker/launch/verify/tech 진입 시 재검증.
 - GPU: 허용 CUDA_VISIBLE_DEVICES 안에서만, 시작 직전 nvidia-smi 여유 admission.
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
COMMON_CODE = ['m65_run.py', 'm65_data.py', 'msd56_data.py']
CODE = {'qwen': COMMON_CODE, 'medgemma': COMMON_CODE + ['msd56_run.py']}
SRC_FILES = ['results/iter_056/data/cases.json', 'results/iter_056/data/case_order.json']
RUNNER = 'm65_run_v1'


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
    """완결(개행으로 끝난) 행만 strict 파싱. 개행 없는 꼬리는 기록 중/torn row라 무시(소유 worker만 repair_tail로 정리). 중간 손상은 예외."""
    out = []
    if not os.path.exists(p):
        return out
    raw = open(p, 'rb').read()
    lines = raw.split(b'\n')
    lines = lines[:-1]  # 마지막 조각은 개행으로 끝나지 않은 부분(빈 문자열이거나 torn)
    for l in lines:
        if l.strip():
            out.append(json.loads(l))
    return out


def repair_tail(path):
    """개행 없이 끝난 마지막 조각만 보존·제거. 완결 행의 손상은 예외로 알린다. returns 제거 bytes."""
    if not os.path.exists(path):
        return 0
    raw = open(path, 'rb').read()
    cut = raw.rfind(b'\n') + 1
    for l in raw[:cut].split(b'\n'):
        if l.strip():
            json.loads(l)  # 중간 손상 -> JSONDecodeError (복구 거부)
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
        n = os.write(fd, b)
        if n != len(b):
            raise IOError('short write')
        os.fsync(fd)
    finally:
        os.close(fd)


# ---------------- model info / protocol ----------------
def snapshot_dir(model):
    if model == 'qwen':
        return json.load(open(QFETCH))['snapshot_path']
    import msd56_run as M
    return f'{HFHOME}/hub/models--google--medgemma-1.5-4b-it/snapshots/{M.MODEL_REVISION}'


def model_files(model, full):
    snap = snapshot_dir(model)
    out = {}
    for f in sorted(os.listdir(snap)):
        real = os.path.realpath(os.path.join(snap, f))
        st = os.stat(real)
        ent = {'size': st.st_size, 'mtime_ns': st.st_mtime_ns}
        if full:
            ent['sha256'] = sha_file(real)
        out[f] = ent
    return out


def model_id_rev(model):
    if model == 'qwen':
        return QID, json.load(open(QFETCH))['revision']
    import msd56_run as M
    return M.MODEL_ID, M.MODEL_REVISION


def components(model, requests, labels, target_manifest, full_model_hash=False):
    _setup_env(model)
    rows = read_jsonl(requests)
    imgs = sorted({p for r in rows for p in r['images']})
    mid, rev = model_id_rev(model)
    mf = model_files(model, full_model_hash)
    comp = {'model_key': model, 'runner': RUNNER, 'code': {f: sha_file(f) for f in CODE[model]}, 'requests': sha_file(requests),
            'labels': sha_file(labels), 'target_manifest': sha_file(target_manifest),
            'source': {f: sha_file(f) for f in SRC_FILES}, 'images': {p: sha_file(p) for p in imgs},
            'model_id': mid, 'model_revision': rev, 'caps': CAPS,
            'gen_spec': 'greedy do_sample=False, checkpoint generation_config 유지, max_new_tokens=cap; cap512 비EOS만 2048 1회 재시도'}
    return comp, mf


def digest(comp, mf_full):
    return sha_s(json.dumps({'c': comp, 'm': {k: v.get('sha256') for k, v in mf_full.items()}}, sort_keys=True))


def cmd_lock(a):
    comp, mf = components(a.model, a.requests, a.labels, a.target_manifest, full_model_hash=True)
    assert not os.path.exists(a.out), 'protocol already exists'
    d = digest(comp, mf)
    json.dump({'digest': d, 'components': comp, 'model_files': mf, 'requests_file': a.requests, 'labels_file': a.labels,
               'target_manifest': a.target_manifest, 'model': a.model, 'locked_at': time.strftime('%Y-%m-%dT%H:%M:%S')},
              open(a.out, 'w'), indent=1)
    print('locked', d)


def check_protocol(model, requests, labels, target_manifest, protocol, full=False):
    p = json.load(open(protocol))
    assert p['model'] == model, 'protocol model mismatch'
    comp, mf = components(model, requests, labels, target_manifest, full_model_hash=full)
    if comp != p['components']:
        sys.exit('PROTOCOL MISMATCH in ' + str([k for k in comp if comp[k] != p['components'].get(k)]))
    for f, ent in p['model_files'].items():
        cur = mf.get(f)
        if cur is None or cur['size'] != ent['size'] or (full and cur['sha256'] != ent['sha256']):
            sys.exit('MODEL FILE MISMATCH ' + f)
        if not full and (cur['mtime_ns'] != ent['mtime_ns']):
            # mtime 변동은 내용 재hash로 확인한다(작은 파일은 즉시, 큰 파일은 stat+size만 신뢰하지 않고 전체 hash)
            real = os.path.realpath(os.path.join(snapshot_dir(model), f))
            if sha_file(real) != ent['sha256']:
                sys.exit('MODEL FILE CONTENT MISMATCH ' + f)
    if set(mf) != set(p['model_files']):
        sys.exit('MODEL FILE SET MISMATCH')
    if set(mf) != set(p['model_files']):
        sys.exit('MODEL FILE SET MISMATCH')
    if digest(p['components'], p['model_files']) != p['digest']:
        sys.exit('PROTOCOL DIGEST TAMPERED')
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


def per_image_pixels(model, inp):
    """영상별 처리 pixel tensor의 sha 목록과 (qwen) grid. 영상 순서 = placeholder 순서."""
    import numpy as np
    pv = inp['pixel_values'].float()
    if model == 'medgemma':
        return [sha_s(pv[i].numpy().tobytes()) for i in range(pv.shape[0])], None
    grids = inp['image_grid_thw'].tolist()
    out, s = [], 0
    for t, h, w in grids:
        n = int(t * h * w)
        out.append(sha_s(pv[s:s + n].numpy().tobytes()))
        s += n
    assert s == pv.shape[0]
    return out, grids


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
    if n_img != expected_img_tokens(model, inp, len(row['images'])):
        raise RuntimeError(f"input structure mismatch {row['rid']}: images={len(row['images'])} tok={n_img}")
    pxs, grids = per_image_pixels(model, inp)
    t_proc = time.perf_counter()
    attempts = []
    for cap in CAPS:
        g = generate(torch, m, inp, cap, eos)
        g['text'] = proc.decode(g['suffix_ids'], skip_special_tokens=True)
        attempts.append(g)
        if g['ended_eos']:
            break
    return {'rid': row['rid'], 'n_input_tokens': len(ids), 'n_image_tokens': n_img, 'n_images': len(row['images']),
            'input_ids_sha': sha_s(json.dumps(ids)), 'img_pixel_sha': pxs, 'img_grid_thw': grids,
            'image_file_sha': [sha_file(p) for p in row['images']], 'attempts': attempts,
            'proc_s': t_proc - t_start, 'gen_attempts_s': time.perf_counter() - t_proc,
            'total_read_to_flush_s': None}, t_start


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
    pdig = check_protocol(a.model, a.requests, a.labels, a.target_manifest, a.protocol)
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
    for f in glob.glob(f'{a.out_dir}/worker*.jsonl'):
        for r in read_jsonl(f):
            if r.get('protocol_digest') != pdig or r['rid'] not in by:
                sys.exit(f'existing record incompatible with protocol: {f} {r.get("rid")}')
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
        rec['total_read_to_flush_s'] = time.perf_counter() - ts
        rec.update({'protocol_digest': pdig, 'worker': a.worker, 'attempt_id': attempt, 'cond': row['cond'],
                    'answer_sha': sha_s(rec['attempts'][-1]['text'])})
        if a.die_after_write and n + 1 >= a.die_after_write:  # 시험용: 저장 후 즉시 강제 종료
            append_row(out, rec)
            os._exit(9)
        if a.torn_after and n + 1 >= a.torn_after:  # 시험용: 행 중간까지만 쓰고 종료(torn tail)
            b = (json.dumps(rec) + '\n').encode()
            with open(out, 'ab') as f:
                f.write(b[:len(b) // 2]); f.flush(); os.fsync(f.fileno())
            os._exit(9)
        t_sv = time.perf_counter()
        append_row(out, rec)
        append_row(f'{a.out_dir}/worker{a.worker}.cost', {'rid': row['rid'], 'save_s': time.perf_counter() - t_sv,
                                                           'read_to_saved_s': time.perf_counter() - ts})
        n += 1
        print(f'w{a.worker} {n} {time.perf_counter() - t0:.0f}s', flush=True)
    print('worker done', n, time.perf_counter() - t0, flush=True)


# ---------------- launcher ----------------
def smi(q):
    o = subprocess.check_output(['nvidia-smi', f'--query-gpu=index,uuid,{q}', '--format=csv,noheader,nounits'], text=True)
    return {int(l.split(',')[0]): (l.split(',')[1].strip(), int(l.split(',')[2])) for l in o.strip().splitlines()}


def cmd_launch(a):
    """jobs: [{model, gpu, workers, protocol, out_dir, tech, peak_gb}]. 같은 requests/labels/target_manifest를 모두 사용."""
    jobs = json.load(open(a.jobs))
    allowed = os.environ.get('CUDA_VISIBLE_DEVICES')
    total, used = smi('memory.total'), smi('memory.used')
    need = {}
    for j in jobs:
        check_protocol(j['model'], a.requests, a.labels, a.target_manifest, j['protocol'])
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
    prepared, widx = set(), {}
    for j in jobs:
        os.makedirs(j['out_dir'], exist_ok=True)
        if j['out_dir'] not in prepared:  # 같은 out_dir의 여러 job(GPU별 shard)은 하나의 launcher lock·claim 정리를 공유
            prepared.add(j['out_dir'])
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
        for _ in range(j['workers']):
            w = widx.get(j['out_dir'], 0)
            widx[j['out_dir']] = w + 1
            env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(j['gpu']))
            cmd = [sys.executable, 'm65_run.py', 'worker', '--model', j['model'], '--requests', a.requests, '--labels', a.labels,
                   '--target-manifest', a.target_manifest, '--protocol', j['protocol'], '--out-dir', j['out_dir'], '--worker', str(w)]
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
    pdig = check_protocol(a.model, a.requests, a.labels, a.target_manifest, a.protocol, full=True)
    rows = read_jsonl(a.requests)
    by = {r['rid']: r for r in rows}
    recs, files, problems = [], {}, []
    for f in sorted(glob.glob(f'{a.out_dir}/worker*.jsonl')):
        raw = open(f, 'rb').read()
        if raw and not raw.endswith(b'\n'):
            problems.append('torn tail in ' + f)
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
        if r['n_images'] != len(q['images']) or r['n_image_tokens'] == 0:
            problems.append('image count/tokens ' + r['rid'])
        if r['image_file_sha'] != [sha_file(p) for p in q['images']]:
            problems.append('image file sha ' + r['rid'])
        if not r['attempts'] or any(x['cap'] not in CAPS for x in r['attempts']) or r['answer_sha'] != sha_s(r['attempts'][-1]['text']):
            problems.append('attempts/answer sha ' + r['rid'])
        if r['cond'] != q['cond']:
            problems.append('cond ' + r['rid'])
    lm = {os.path.basename(f): json.load(open(f))['exit_codes'] for f in glob.glob(f'{a.out_dir}/launch_*.json')}
    res = {'n_requests': len(rows), 'n_records': len(recs), 'problems': problems[:20], 'n_problems': len(problems),
           'protocol_digest': pdig, 'record_file_sha256': files, 'launch_exit_codes': lm, 'sealed_at': time.strftime('%Y-%m-%dT%H:%M:%S')}
    json.dump(res, open(f'{a.out_dir}/verify.json', 'w'), indent=1)
    print({k: v for k, v in res.items() if k != 'record_file_sha256'})
    if problems:
        sys.exit(1)


# ---------------- tech ----------------
def cmd_tech(a):
    """(1) wrapper vs 공식 processor 직접 호출 tensor (2) 영상 token/grid·순서 (3) prompt 문자열(m65_data.prompt)·누출
    (4) 같은 png의 처리 tensor는 모든 요청에서 동일 (5) J = 같은 case/구간 F·T 목록의 z별 교차 (6) W/E 요청은 같은 구간·조건에서 동일 영상."""
    _setup_env(a.model)
    import torch, transformers
    pdig = check_protocol(a.model, a.requests, a.labels, a.target_manifest, a.protocol)
    rows = read_jsonl(a.requests)
    import m65_data as S
    if a.model == 'qwen':
        proc = transformers.AutoProcessor.from_pretrained(QID, revision=json.load(open(QFETCH))['revision'], cache_dir=QCACHE)
        img_id = proc.tokenizer.convert_tokens_to_ids('<|image_pad|>')
    else:
        import msd56_run as M
        proc = transformers.AutoProcessor.from_pretrained(M.MODEL_ID, revision=M.MODEL_REVISION)
        img_id = proc.tokenizer.convert_tokens_to_ids('<image_soft_token>')
        assert img_id == 262144, img_id
    fails, res, png_px, png_grid = 0, [], {}, {}
    inv = []
    for r in rows:
        inp = build_inputs(a.model, proc, r)
        ims = open_images(r)
        msgs = [{'role': 'user', 'content': [{'type': 'image', 'image': im} for im in ims] + [{'type': 'text', 'text': r['prompt']}]}]
        if a.model == 'qwen':
            from qwen_vl_utils import process_vision_info
            t2 = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
            iis, vis = process_vision_info(msgs)
            ref = proc(text=[t2], images=iis, videos=vis, padding=True, return_tensors='pt')
        else:
            t2 = proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
            ref = proc(text=t2, images=ims, return_tensors='pt', add_special_tokens=False)
        ok_ids = torch.equal(inp['input_ids'], ref['input_ids'])
        ok_pv = torch.equal(inp['pixel_values'], ref['pixel_values'])
        ok_grid = a.model != 'qwen' or torch.equal(inp['image_grid_thw'], ref['image_grid_thw'])
        pxs, grids = per_image_pixels(a.model, inp)
        ids = inp['input_ids'][0].tolist()
        text_all = proc.decode(ids)
        leak = [s for s in [r['case'], 'BRATS'] + [os.path.basename(p)[:-4] for p in r['images']] if s in text_all]
        n_tok = sum(1 for t in ids if t == img_id)
        ok_struct = len(pxs) == len(r['images']) and n_tok == expected_img_tokens(a.model, inp, len(ims))
        ok_prompt = r['prompt'] == S.prompt(r['cond'], r['q']) and r['prompt'] in text_all
        ok_n = len(r['images']) == (16 if r['cond'] == 'J' else 8)
        for i, p in enumerate(r['images']):
            if p in png_px and png_px[p] != pxs[i]:
                inv.append(('png tensor differs across requests', r['rid'], i))
            png_px[p] = pxs[i]
            if grids:
                png_grid[p] = grids[i]
        res.append({'rid': r['rid'], 'ok_ids': ok_ids, 'ok_pv': ok_pv, 'ok_grid': ok_grid, 'ok_struct': ok_struct, 'ok_prompt': ok_prompt,
                    'ok_nimg': ok_n, 'leak': leak, 'n_input_tokens': len(ids), 'n_images': len(ims)})
        if not (ok_ids and ok_pv and ok_grid and ok_struct and ok_prompt and ok_n and not leak):
            fails += 1
    by = {(r['case'], r['slab'], r['q'], r['cond']): r for r in rows}
    for r in rows:
        if r['cond'] == 'J':
            f, t = by[(r['case'], r['slab'], r['q'], 'F')]['images'], by[(r['case'], r['slab'], r['q'], 'T')]['images']
            if r['images'] != [x for pr in zip(f, t) for x in pr]:
                inv.append(('J interleave', r['rid']))
        if r['images'] != by[(r['case'], r['slab'], 'W' if r['q'] == 'E' else 'E', r['cond'])]['images']:
            inv.append(('W/E images differ', r['rid']))
    # 서로 다른 png(F vs T)의 처리 tensor는 구분되어야 한다(동일 영상 오배치 검출)
    # (파일 내용이 다른 png가 같은 tensor를 공유하면 오배치 의심. 파일 bytes가 같은 png끼리의 공유는 정상이며 허용: E36에서 근-빈 slice 2개가 byte 동일)
    by_tensor = {}
    for p, t in png_px.items():
        by_tensor.setdefault(t, set()).add(sha_file(p))
    share = sum(len(v) > 1 for v in by_tensor.values())
    if share:
        inv.append(('different-content png share tensor', share))
    fails += len(inv)
    out = {'requests_sha256': sha_file(a.requests), 'protocol_digest': pdig, 'model': a.model, 'n_checked': len(res), 'fails': fails,
           'invariance_failures': inv[:10], 'n_distinct_png': len(png_px),
           'token_len_by_cond': {c: sorted({v['n_input_tokens'] for v in res if v['rid'].endswith('__' + c)}) for c in S.CONDS},
           'details': res, 'max_input_tokens': max(x['n_input_tokens'] for x in res)}
    assert not os.path.exists(a.out)
    json.dump(out, open(a.out, 'w'), indent=1)
    print('tech fails', fails, 'of', len(res), 'distinct png', len(png_px), 'max tokens', out['max_input_tokens'])
    if fails:
        sys.exit(1)



def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd', required=True)
    for n in ('lock', 'worker', 'verify', 'tech', 'launch'):
        p = sp.add_parser(n)
        p.add_argument('--requests', required=True); p.add_argument('--labels', required=True); p.add_argument('--target-manifest', required=True)
        if n != 'launch':
            p.add_argument('--model', required=True, choices=MODELS)
        if n in ('worker', 'verify', 'tech'):
            p.add_argument('--protocol', required=True)
        if n in ('worker', 'verify'):
            p.add_argument('--out-dir', required=True)
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
