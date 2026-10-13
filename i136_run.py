"""iter_136 추론 실행기 (i134_run 파생). 변경점: 0~2장 가변 영상 요청, 단계별 max_new_tokens(technical 1024 / technical2048 / main=gate 기록값),
worker 직접 진입에서도 code·gates·inputs 전체 hash 검사, worker 시작 직전 GPU admission(상속 허용 집합·worker당 2GiB 여유·이미 기동한 worker의 예약 합산),
감독기 flock 보유 검증, 자원(GPU/CPU/RAM/디스크 I/O) 로그. 결과는 results/iter_136 아래 job 디렉터리에만 쓴다."""
import argparse, os, sys, time, json, fcntl, subprocess
from pathlib import Path
from i136_common import RES, read, save, sha, digest, now
from i136_spec import BASE_CONFIG, TOKENS, STAGES, FORBIDDEN_IN_PROMPT, START_TOKEN, END_TOKEN, split_final

MODEL = Path(__file__).resolve().parent.parent / 'hf_cache/models--google--medgemma-1.5-4b-it/snapshots' / BASE_CONFIG['revision']
MARGIN_MIB = 2048
def protocol_path(stage, new=False):
    """원 잠금 protocol_lock_<stage>.json과 생성 전 보정본 protocol_lock_<stage>_a<N>.json 중 가장 최신. new=True면 다음 저장 경로."""
    cur = sorted(RES.glob('protocol_lock_%s.json' % stage)) + sorted(RES.glob('protocol_lock_%s_a*.json' % stage), key=lambda p: int(p.stem.rsplit('_a', 1)[1]))
    if new: return RES / ('protocol_lock_%s.json' % stage if not cur else 'protocol_lock_%s_a%d.json' % (stage, len(cur)))
    return cur[-1]
def request_file(stage): return RES / 'requests' / ('technical.json' if stage.startswith('technical') else 'main.json')


def config_for(stage):
    if stage in TOKENS: n = TOKENS[stage]
    else:
        g = read(RES / 'tests/technical_gate.json'); assert g.get('passed') is True, 'technical gate not passed'; n = g['main_max_new_tokens']
    return dict(BASE_CONFIG, max_new_tokens=n)


def boundary_ids(tok):
    """tokenizer의 실제 mapping에서 thought 표식 id를 읽고 잠긴 tests/boundary_check.json과 일치해야 한다 (ID 상수 가정 금지)."""
    ids = dict(start_id=tok.convert_tokens_to_ids(START_TOKEN), end_id=tok.convert_tokens_to_ids(END_TOKEN))
    assert tok.convert_ids_to_tokens(ids['start_id']) == START_TOKEN and tok.convert_ids_to_tokens(ids['end_id']) == END_TOKEN
    locked = read(RES / 'tests/boundary_check.json')
    assert locked['passed'] is True and locked['ids'] == ids, 'boundary ids differ from locked check'
    return ids


def smi():
    s = subprocess.check_output(['nvidia-smi', '--query-gpu=index,uuid,memory.total,memory.used,memory.free,utilization.gpu', '--format=csv,noheader,nounits'], text=True)
    return [dict(zip(['index', 'uuid', 'total', 'used', 'free', 'utilization'], [x.strip() for x in line.split(',')])) for line in s.strip().splitlines()]


def allowed():
    raw = os.environ.get('CUDA_VISIBLE_DEVICES')
    if raw is None: raise RuntimeError('CUDA_VISIBLE_DEVICES must be explicit')
    ids = [i.strip() for i in raw.split(',')]; assert ids and all(i.isdigit() for i in ids)
    assert set(ids) <= {r['index'] for r in smi()}
    return ids


def verify_protocol(stage, models=False):
    """launch·worker 모두 호출. code·gates·inputs를 항상 전체 검사. main은 technical gate가 protocol에 잠겨 있고 passed=True여야 한다."""
    lock = read(protocol_path(stage)); cfg = config_for(stage)
    assert lock['config'] == cfg and lock['stage'] == stage, 'config/stage mismatch'
    for p, h in {**lock['code'], **lock['gates'], **lock['inputs']}.items():
        if sha(p) != h: raise ValueError('protocol mismatch: ' + p)
    for p, r in lock['model_files'].items():
        assert Path(p).stat().st_size == r['bytes']
        if models and sha(p) != r['sha256']: raise ValueError('model mismatch')
    if stage == 'main':
        gp = str(RES / 'tests/technical_gate.json'); assert gp in lock['gates'], 'technical gate not locked'
        assert read(gp).get('passed') is True
    return sha(protocol_path(stage))


def requests(stage, path=None):
    path = path or request_file(stage); rr = read(path); ids = [r['id'] for r in rr]; assert len(set(ids)) == len(ids)
    for r in rr:
        assert digest({k: v for k, v in r.items() if k != 'request_digest'}) == r['request_digest']
        assert r['kind'] == 'single' and len(r['images']) == len(r['roles']) <= 2
        for im in r['images']: assert sha(im['path']) == im['sha256']
        assert not any(s in r['prompt'] for s in FORBIDDEN_IN_PROMPT)
    return rr


def load_records(job, repair=False):
    fd = os.open(Path(job) / 'records.lock', os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX if repair else fcntl.LOCK_SH)
    try: return _load_records(job, repair)
    finally: os.close(fd)


def _load_records(job, repair=False):
    records = []
    for p in sorted(Path(job).glob('worker*.jsonl')):
        raw = p.read_bytes(); lines = raw.splitlines(keepends=True); good = 0
        for i, line in enumerate(lines):
            try:
                if not line.endswith(b'\n'): raise ValueError('uncommitted tail')
                r = json.loads(line)
            except Exception:
                if i != len(lines) - 1 or not repair: raise ValueError('corrupt JSONL: ' + str(p))
                save(p.with_name(p.name + '.tail_' + str(time.time_ns()) + '.json'), dict(bytes_hex=raw[good:].hex(), source_sha256=sha(p), reason='last uncommitted row'))
                with open(p, 'r+b') as f: f.truncate(good); f.flush(); os.fsync(f.fileno())
                break
            assert r['record_digest'] == digest({k: v for k, v in r.items() if k != 'record_digest'})
            records.append(r); good += len(line)
    assert len({r['id'] for r in records}) == len(records), 'duplicate result'
    return records


def check_records(records, rr, proto, cfg):
    expected = {r['id']: r for r in rr}
    for r in records:
        req = expected[r['id']]   # 요청 밖 id는 KeyError
        assert r['request_digest'] == req['request_digest'] and r['protocol_sha256'] == proto and r['config_digest'] == digest(cfg)
        assert r['image_hashes'] == [im['sha256'] for im in req['images']]


def verify_job(job, stage, complete=True):
    proto = verify_protocol(stage); rr = requests(stage); cfg = config_for(stage); rec = load_records(job); check_records(rec, rr, proto, cfg)
    if complete:
        c = read(Path(job) / 'completion.json'); assert c['n_records'] == len(rr) == len(rec) and c['protocol_sha256'] == proto and c['requests_sha256'] == sha(request_file(stage))
        assert c['config'] == cfg and all(x == 0 for x in c['returncodes'])
        assert {r['id'] for r in rec} == {r['id'] for r in rr}
        assert all(sha(p) == h for p, h in c['files'].items()) and set(c['files']) == {str(p) for p in Path(job).glob('worker*.jsonl')}
    return rec


def messages(req):
    from PIL import Image
    content = [dict(type='text', text=req['prompt'])]
    for n, im in enumerate(req['images']):   # v2: 'Image n:' 라벨 텍스트 제거 (첫 기술 실행에서 모델이 라벨을 첫 줄에 따라 써 형식 오류 유발; 정답 내용과 무관한 형식 수정)
        content.append(dict(type='image', image=Image.open(im['path']).convert('RGB')))
    return [dict(role='user', content=content)]


def input_tensor(proc, req):
    return proc.apply_chat_template(messages(req), add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors='pt')


def admission(gpu, peak, reserved_others=0):
    """worker 시작 직전: 해당 물리 GPU의 실제 free에서 이미 기동한 worker의 예약(peak+margin)을 이중 계산 없이 반영한다.
    (이미 로딩을 마친 worker의 점유는 nvidia-smi free에 이미 반영되므로 reserved_others는 로딩 중인 worker용)"""
    row = next(r for r in smi() if r['index'] == gpu); free = int(row['free'])
    if free - reserved_others < peak + MARGIN_MIB: raise RuntimeError('admission gpu%s: free %d - reserved %d < %d' % (gpu, free, reserved_others, peak + MARGIN_MIB))
    return dict(gpu=gpu, uuid=row['uuid'], free=free, need=peak + MARGIN_MIB)


def worker(args):
    assert args.lock_fd is not None
    job = Path(args.job); st = os.fstat(args.lock_fd); lp = job / 'supervisor.lock'
    assert st.st_ino == lp.stat().st_ino, 'lock fd is not job supervisor.lock'
    probe = os.open(lp, os.O_RDWR)
    try: fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB); raise RuntimeError('supervisor flock not held')
    except BlockingIOError: pass
    finally: os.close(probe)
    proto = verify_protocol(args.stage, models=False); cfg = config_for(args.stage); rr = requests(args.stage); claims = job / 'claims'
    import torch, numpy as np
    from transformers import AutoProcessor, AutoModelForImageTextToText
    torch.manual_seed(cfg['seed']); np.random.seed(cfg['seed']); torch.set_num_threads(4)
    proc = AutoProcessor.from_pretrained(MODEL, local_files_only=True)
    bid = boundary_ids(proc.tokenizer)
    adm = admission(os.environ['CUDA_VISIBLE_DEVICES'], args.peak)   # 직접 진입도 admission 통과 필요 (launcher는 사전 예약 기록)
    t_load = time.monotonic()
    model = AutoModelForImageTextToText.from_pretrained(MODEL, local_files_only=True, dtype=torch.bfloat16, device_map={'': 'cuda:0'}, attn_implementation='sdpa').eval()
    load_s = time.monotonic() - t_load
    (job / ('worker%s_%s.ready' % (args.worker, args.attempt))).write_text(now())
    done = {r['id'] for r in load_records(job)}; start = time.monotonic(); count = 0
    out = job / ('worker%s_%s.jsonl' % (args.worker, args.attempt))
    with open(out, 'xb') as f:
        while True:
            req = None
            for cand in rr:
                if cand['id'] in done: continue
                p = claims / (cand['id'] + '.json')
                try: fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                except FileExistsError: continue
                with os.fdopen(fd, 'w') as c: json.dump(dict(pid=os.getpid(), worker=args.worker, request_digest=cand['request_digest']), c)
                current = {r['id'] for r in load_records(job)}
                if cand['id'] in current: p.unlink(); done.update(current); continue
                req = cand; break
            if req is None: break
            torch.cuda.reset_peak_memory_stats(); t = time.monotonic()
            inputs = input_tensor(proc, req).to(model.device, dtype=torch.bfloat16)
            input_len = inputs['input_ids'].shape[-1]
            with torch.inference_mode(): generated = model.generate(**inputs, max_new_tokens=cfg['max_new_tokens'], do_sample=False)
            torch.cuda.synchronize(); elapsed = time.monotonic() - t
            tokens = generated[0, input_len:].tolist(); eosids = model.generation_config.eos_token_id; eosids = [eosids] if isinstance(eosids, int) else eosids
            stop = next((n + 1 for n, v in enumerate(tokens) if v in eosids), len(tokens)); tokens = tokens[:stop]
            status, fin = split_final(tokens, bid['start_id'], bid['end_id']); text = proc.decode(tokens, skip_special_tokens=True)
            rec = dict(id=req['id'], kind=req['kind'], request_digest=req['request_digest'], protocol_sha256=proto, config_digest=digest(cfg),
                       image_hashes=[im['sha256'] for im in req['images']], text=text, text_marked=proc.decode(tokens, skip_special_tokens=False), tokens=tokens, n_tokens=len(tokens),
                       boundary_status=status, boundary_ids=bid, final_text=proc.decode(fin, skip_special_tokens=True), raw_first_line=(text.strip().splitlines() or [''])[0],
                       eos=bool(tokens and tokens[-1] in eosids), wall_s=elapsed, input_len=input_len, n_image_tokens=int((inputs['input_ids'] == model.config.image_token_id).sum()) if hasattr(model.config, 'image_token_id') else None,
                       peak_allocated_mib=torch.cuda.max_memory_allocated() / 1024 ** 2, peak_reserved_mib=torch.cuda.max_memory_reserved() / 1024 ** 2,
                       worker=args.worker, gpu=os.environ['CUDA_VISIBLE_DEVICES'], completed_at=now())
            rec['record_digest'] = digest(rec)
            recordfd = os.open(job / 'records.lock', os.O_CREAT | os.O_RDWR, 0o600); fcntl.flock(recordfd, fcntl.LOCK_EX)
            try: f.write((json.dumps(rec, sort_keys=True) + '\n').encode()); f.flush(); os.fsync(f.fileno())
            finally: os.close(recordfd)
            with open(job / ('timing_w%s_%s.jsonl' % (args.worker, args.attempt)), 'a') as tf: tf.write(json.dumps(dict(id=req['id'], read_to_saved_s=time.monotonic() - t)) + '\n'); tf.flush(); os.fsync(tf.fileno())
            done.add(req['id']); count += 1; (claims / (req['id'] + '.json')).unlink()
            del inputs, generated
            if args.limit and count >= args.limit: break
    save(job / ('worker%s_%s_exit.json' % (args.worker, args.attempt)), dict(completed=count, wall_s=time.monotonic() - start, load_s=load_s, returncode=0, admission=adm))


def _diskstats():
    out = {}
    for l in Path('/proc/diskstats').read_text().splitlines():
        x = l.split()
        if x[2] in ('sda', 'sdb'): out[x[2]] = dict(read_sectors=int(x[5]), write_sectors=int(x[9]))
    return out


def launch(args):
    stage = args.stage; proto = verify_protocol(stage, models=True); cfg = config_for(stage); rr = requests(stage); job = Path(args.job); job.mkdir(parents=True, exist_ok=True)
    fd = os.open(job / 'supervisor.lock', os.O_CREAT | os.O_RDWR, 0o600)
    try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: os.close(fd); raise RuntimeError('active supervisor/children; refuse launch')
    children = []; logs = []; started = time.monotonic()
    try:
        if (job / 'completion.json').exists(): verify_job(job, stage); print('검증된 완료 재사용'); return
        existing = load_records(job, repair=True); check_records(existing, rr, proto, cfg)
        (job / 'claims').mkdir(exist_ok=True)
        stale = list((job / 'claims').glob('*.json'))
        if stale:
            save(job / ('stale_claims_%d.json' % time.time_ns()), {str(p): read(p) for p in stale})
            for p in stale: p.unlink()
        attempt = str(time.time_ns()); ids = allowed(); free = {r['index']: int(r['free']) for r in smi()}; ids.sort(key=lambda g: -free[g])
        mapping = [ids[i % len(ids)] for i in range(args.workers)]
        for g in ids:   # 사전 admission (전체 동시 worker 합계)
            required = mapping.count(g) * (args.peak + MARGIN_MIB)
            if free[g] < required: raise RuntimeError('memory admission %s: free %d < %d' % (g, free[g], required))
        save(job / ('launch_%s.json' % attempt), dict(created_at=now(), stage=stage, requests_sha256=sha(request_file(stage)), protocol_sha256=proto, config=cfg, mapping=mapping,
                                                      allowed_ids=ids, gpu_uuid={r['index']: r['uuid'] for r in smi()}, memory_before=smi(), estimated_peak_mib=args.peak, worker_margin_mib=MARGIN_MIB, existing=len(existing)))
        io0 = _diskstats(); t_start = time.monotonic()
        for i, gpu in enumerate(mapping):
            env = dict(os.environ, CUDA_VISIBLE_DEVICES=gpu, TOKENIZERS_PARALLELISM='false', OMP_NUM_THREADS='4', HF_HUB_OFFLINE='1')
            log = open(job / ('worker%d_%s.log' % (i, attempt)), 'xb'); logs.append(log)
            cmd = [sys.executable, str(Path(__file__).resolve()), 'worker', '--job', str(job), '--stage', stage, '--worker', str(i), '--attempt', attempt, '--lock-fd', str(fd),
                   '--limit', str(args.limit), '--peak', str(args.peak)]
            children.append(subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, pass_fds=(fd,)))
            ready = job / ('worker%d_%s.ready' % (i, attempt)); t0 = time.monotonic()   # 다음 worker 시작 전 로딩 완료 대기(메모리 재확인 목적)
            while not ready.exists():
                if children[-1].poll() is not None: raise RuntimeError('worker %d exited before ready: rc=%s' % (i, children[-1].returncode))
                if time.monotonic() - t0 > 900: raise RuntimeError('worker ready timeout')
                time.sleep(2)
        with open(job / ('resources_%s.jsonl' % attempt), 'x') as resources:
            while any(c.poll() is None for c in children):
                resources.write(json.dumps(dict(time=now(), gpu=smi(), cpu_load=os.getloadavg(), memory=Path('/proc/meminfo').read_text().splitlines()[:3], disk=_diskstats())) + '\n'); resources.flush()
                if any(c.poll() not in [None, 0] for c in children):
                    for c in children:
                        if c.poll() is None: c.terminate()
                    break
                time.sleep(5)
        rc = [c.wait() for c in children]; rec = load_records(job); check_records(rec, rr, proto, cfg)
        save(job / ('result_%s.json' % attempt), dict(returncodes=rc, n_records=len(rec), n_expected=len(rr), wall_s=time.monotonic() - started, process_wall_s=time.monotonic() - t_start,
                                                      disk_io_start=io0, disk_io_end=_diskstats(), resources=str(job / ('resources_%s.jsonl' % attempt))))
        if any(rc): raise RuntimeError('child failed: ' + str(rc))
        if len(rec) == len(rr):
            assert {r['id'] for r in rec} == {r['id'] for r in rr}
            save(job / 'completion.json', dict(created_at=now(), config=cfg, protocol_sha256=proto, requests_sha256=sha(request_file(stage)), n_records=len(rec), returncodes=rc,
                                               files={str(p): sha(p) for p in job.glob('worker*.jsonl')}, attempt=attempt))
        elif not args.limit: raise RuntimeError('incomplete generation')
        print('생성', len(rec), '/', len(rr), 'rc', rc, 'wall', time.monotonic() - started)
    finally:
        for c in children:
            if c.poll() is None: c.terminate()
        for c in children:
            try: c.wait(timeout=30)
            except subprocess.TimeoutExpired: c.kill(); c.wait()
        for f in logs: f.close()
        os.close(fd)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('command', choices=['launch', 'worker', 'verify']); ap.add_argument('--job', required=True)
    ap.add_argument('--stage', choices=STAGES, required=True); ap.add_argument('--workers', type=int, default=2); ap.add_argument('--peak', type=int, default=9000)
    ap.add_argument('--limit', type=int, default=0); ap.add_argument('--worker', type=int, default=0); ap.add_argument('--attempt'); ap.add_argument('--lock-fd', type=int); args = ap.parse_args()
    job = Path(args.job).resolve()
    assert str(job).startswith(str(RES) + '/'), 'job must be under results/iter_136'
    args.job = str(job)
    if args.command == 'worker': worker(args)
    elif args.command == 'launch': launch(args)
    else: print('검증', len(verify_job(args.job, args.stage)))


if __name__ == '__main__':
    main()
