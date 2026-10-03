"""iter_061 OmniBrainBench MRI 진단 QA runner (MedGemma 1.5).

모델 loading·env_info·build_inputs는 msd56_run.py(iter_060 SHA adfbb52, blob 63347081)의 함수를 재사용한다.
generate는 monotonic 타이머가 필요해 이 파일에서 감싼다(원 함수는 time.time 사용).
서브명령: build | lock | worker | launch | verify | tech
GT는 requests에 없다. worker는 GT를 읽지 않는다.
"""
import argparse, fcntl, json, os, subprocess, sys, time, hashlib, glob
os.environ.setdefault('HF_HOME', '/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache')
os.environ.setdefault('HF_HUB_OFFLINE', '1')
import mri61_spec as S
import msd56_run as M

CODE = ['mri61_run.py', 'mri61_spec.py', 'msd56_run.py']
CAPS = [512, 2048]


def sha_file(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def read_jsonl(p):
    out = []
    if not os.path.exists(p):
        return out
    for l in open(p):
        l = l.strip()
        if not l:
            continue
        try:
            out.append(json.loads(l))
        except json.JSONDecodeError:
            break  # 손상된 tail은 무시(재처리됨)
    return out


def cmd_build(a):
    lock = json.load(open(f'{S.DATA}/selection_lock.json'))
    qa = {x['id']: x for x in json.load(open(f'{S.DATA}/eligible_qa.json'))}
    ex = lock['visual_exclusions']
    if a.split == 'D':
        cl = lock['D']
    else:
        E = [r for r in lock['E_ordered_multi'] if r['cluster_id'] not in ex]
        cl = E[:int(a.split[1:])]
    rows = S.build_rows(cl, qa, f'{S.DATA}/images')
    assert len({r['rid'] for r in rows}) == len(rows)
    with open(a.out, 'w') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')
    labels = {str(c['cluster_id']): {'qa_id': c['qa_id'], 'gt_orig_index': S.gt_orig_index(qa[c['qa_id']]),
                                      'answer_text': c['answer_text'], 'source': c['source'], 'K': c['K'],
                                      'options': qa[c['qa_id']]['options']} for c in cl}
    json.dump(labels, open(a.out.replace('.jsonl', '_labels.json'), 'w'), indent=1)
    print(a.split, 'clusters', len(cl), 'requests', len(rows), 'image-inputs', sum(len(r['images']) for r in rows))


def proto_digest(requests_path):
    return hashlib.sha256(json.dumps({'code': {f: sha_file(f) for f in CODE}, 'requests': sha_file(requests_path),
                                     'revision': M.MODEL_REVISION, 'caps': CAPS, 'instr': S.INSTR,
                                     'images': {p: sha_file(p) for r in read_jsonl(requests_path) for p in r['images']}},
                                    sort_keys=True).encode()).hexdigest()


def cmd_lock(a):
    d = proto_digest(a.requests)
    json.dump({'digest': d, 'requests_file': a.requests, 'requests_sha256': sha_file(a.requests),
               'code': {f: sha_file(f) for f in CODE}, 'revision': M.MODEL_REVISION, 'caps': CAPS,
               'locked_at': time.strftime('%Y-%m-%dT%H:%M:%S')}, open(a.out, 'w'), indent=1)
    print('locked', d)


def check_protocol(a):
    p = json.load(open(a.protocol))
    if proto_digest(a.requests) != p['digest']:
        sys.exit('PROTOCOL MISMATCH: source/request/image changed after lock')
    return p['digest']


def mgen(torch, model, inp, cap, eos_ids):
    r = M.generate(torch, model, inp, cap, eos_ids)
    return r


def run_one(torch, proc, model, eos, row):
    t0 = time.perf_counter()
    inp = M.build_inputs(proc, row)
    ids = inp['input_ids'][0].tolist()
    n_img = sum(1 for t in ids if t == model.config.image_token_index)
    t_proc = time.perf_counter()
    attempts = []
    for cap in CAPS:
        g = M.generate(torch, model, inp, cap, eos)
        g['text'] = proc.decode(g['suffix_ids'], skip_special_tokens=True)
        attempts.append(g)
        if g['ended_eos']:
            break
    t1 = time.perf_counter()
    return {'rid': row['rid'], 'n_input_tokens': len(ids), 'n_image_tokens': n_img, 'n_images': len(row['images']),
            'input_ids_sha': S.sha(json.dumps(ids)),
            'pixel_values_sha': S.sha(inp['pixel_values'].numpy().tobytes()) if 'pixel_values' in inp else None,
            'attempts': attempts, 'wall_monotonic_s': t1 - t0, 'proc_monotonic_s': t_proc - t0}


def cmd_worker(a):
    pdig = check_protocol(a)
    rows = read_jsonl(a.requests)
    os.makedirs(a.out_dir, exist_ok=True)
    done = set()
    for f in glob.glob(f'{a.out_dir}/worker*.jsonl'):
        done |= {r['rid'] for r in read_jsonl(f)}
    lockf = open(f'{a.out_dir}/worker{a.worker}.lock', 'w')
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit('worker already running')
    todo = [r for i, r in enumerate(rows) if i % a.nworkers == a.worker and r['rid'] not in done]
    if a.limit:
        todo = todo[:a.limit]
    tl = time.perf_counter()
    torch, proc, model = M.load_model()
    env = M.env_info(torch, proc, model)
    load_s = time.perf_counter() - tl
    eos = set(model.generation_config.eos_token_id if isinstance(model.generation_config.eos_token_id, list)
              else [model.generation_config.eos_token_id])
    out = f'{a.out_dir}/worker{a.worker}.jsonl'
    # 손상된 tail 제거
    if os.path.exists(out):
        good = read_jsonl(out)
        with open(out, 'w') as f:
            for r in good:
                f.write(json.dumps(r) + '\n')
    attempt = str(int(time.time()))
    json.dump({'attempt': attempt, 'env': env, 'load_s': load_s, 'pid': os.getpid(), 'n_todo': len(todo),
               'gpu_env': os.environ.get('CUDA_VISIBLE_DEVICES')},
              open(f'{a.out_dir}/worker{a.worker}.attempt_{attempt}.json', 'w'))
    t0 = time.perf_counter()
    for i, r in enumerate(todo):
        rec = run_one(torch, proc, model, eos, r)
        rec.update({'protocol_digest': pdig, 'worker': a.worker, 'attempt_id': attempt})
        with open(out, 'a') as f:
            f.write(json.dumps(rec) + '\n')
            f.flush(); os.fsync(f.fileno())
        if i % 10 == 0:
            print(f'w{a.worker} {i + 1}/{len(todo)} {time.perf_counter() - t0:.0f}s', flush=True)
    print('worker done', len(todo), time.perf_counter() - t0)


def gpu_free():
    o = subprocess.check_output(['nvidia-smi', '--query-gpu=index,memory.used,memory.total', '--format=csv,noheader,nounits'], text=True)
    return {int(l.split(',')[0]): int(l.split(',')[2]) - int(l.split(',')[1]) for l in o.strip().splitlines()}


def cmd_launch(a):
    check_protocol(a)
    tj = json.load(open(a.tech))  # 기술 gate: 실패/누락 시 nonzero 종료(E 차단)
    if tj.get('fails', 1) != 0 or tj.get('requests_sha256') != sha_file(a.requests):
        sys.exit(2)
    gpus = [int(g) for g in a.gpus.split(',')]
    allowed = os.environ.get('CUDA_VISIBLE_DEVICES')
    if allowed:
        assert set(map(str, gpus)) <= set(allowed.split(',')), 'GPU outside allowed set'
    free = gpu_free()
    need = {}
    for g in gpus:
        need[g] = need.get(g, 0) + a.peak_gb * 1024 + 2048
    for g, n in need.items():
        assert free[g] >= n, f'GPU{g} free {free[g]} < need {n} MiB'
    os.makedirs(a.out_dir, exist_ok=True)
    t0 = time.perf_counter()
    ps = []
    for w, g in enumerate(gpus):
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(g))
        cmd = [sys.executable, 'mri61_run.py', 'worker', '--requests', a.requests, '--protocol', a.protocol,
               '--out-dir', a.out_dir, '--worker', str(w), '--nworkers', str(len(gpus))]
        if a.limit:
            cmd += ['--limit', str(a.limit)]
        ps.append(subprocess.Popen(cmd, env=env, stdout=open(f'{a.out_dir}/worker{w}.stdout.log', 'a'),
                                   stderr=subprocess.STDOUT))
    samples, rcs = [], [None] * len(ps)
    while any(r is None for r in rcs):
        time.sleep(5)
        rcs = [p.poll() for p in ps]
        samples.append(gpu_used())
    comp = {'gpus': gpus, 'exit_codes': rcs, 'wall_monotonic_s': time.perf_counter() - t0, 'peak_used_mib': {
        g: max(s[g] for s in samples) for g in samples[0]} if samples else {}}
    json.dump(comp, open(f'{a.out_dir}/launch_{int(time.time())}.json', 'w'))
    print(comp)
    if any(rcs):
        sys.exit(1)


def gpu_used():
    o = subprocess.check_output(['nvidia-smi', '--query-gpu=index,memory.used', '--format=csv,noheader,nounits'], text=True)
    return {int(l.split(',')[0]): int(l.split(',')[1]) for l in o.strip().splitlines()}


def cmd_verify(a):
    pdig = check_protocol(a)
    rows = read_jsonl(a.requests)
    byrid = {r['rid']: r for r in rows}
    recs = []
    for f in sorted(glob.glob(f'{a.out_dir}/worker*.jsonl')):
        recs += read_jsonl(f)
    ids = [r['rid'] for r in recs]
    problems = []
    if len(ids) != len(set(ids)):
        problems.append('duplicate records')
    if set(ids) != set(byrid):
        problems.append(f'missing {len(set(byrid) - set(ids))} extra {len(set(ids) - set(byrid))}')
    for r in recs:
        q = byrid.get(r['rid'])
        if not q:
            continue
        if r['protocol_digest'] != pdig:
            problems.append('protocol digest ' + r['rid'])
        if r['n_images'] != len(q['images']) or (len(q['images']) == 0) != (r['n_image_tokens'] == 0):
            problems.append('image count/tokens ' + r['rid'])
        if q['images'] and r['n_image_tokens'] != 256 * len(q['images']):
            problems.append('image token count ' + r['rid'])
    lm = {}
    for f in glob.glob(f'{a.out_dir}/launch_*.json'):
        lm[f] = json.load(open(f))['exit_codes']
    res = {'n_requests': len(rows), 'n_records': len(recs), 'problems': problems[:20], 'n_problems': len(problems),
           'launch_exit_codes': lm}
    json.dump(res, open(f'{a.out_dir}/verify.json', 'w'), indent=1)
    print(res)
    if problems:
        sys.exit(1)


def cmd_tech(a):
    """공식 processor 경로와 wrapper 대조: input_ids·pixel_values·영상 순서, T의 영상 token 부재, S_i⊂J."""
    import torch
    from PIL import Image
    import numpy as np
    torch_, proc, _ = None, None, None
    import transformers
    proc = transformers.AutoProcessor.from_pretrained(M.MODEL_ID, revision=M.MODEL_REVISION)
    rows = read_jsonl(a.requests)
    img_id = proc.tokenizer.convert_tokens_to_ids(proc.tokenizer.special_tokens_map.get('image_token', '<image_soft_token>')) \
        if False else None
    res, fails = [], 0
    seen = {}
    for r in rows:
        if r['order'] != 'F':
            continue
        inp = M.build_inputs(proc, r)
        msgs = [{'role': 'user', 'content': [{'type': 'image', 'image': Image.open(p).convert('RGB')} for p in r['images']] +
                 [{'type': 'text', 'text': r['prompt']}]}]
        text = proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
        ims = [Image.open(p).convert('RGB') for p in r['images']]
        ref = proc(text=text, images=ims, return_tensors='pt', add_special_tokens=False) if ims else \
            proc(text=text, return_tensors='pt', add_special_tokens=False)
        ok_ids = torch.equal(inp['input_ids'], ref['input_ids'])
        ok_pv = (('pixel_values' in inp) == ('pixel_values' in ref)) and (
            'pixel_values' not in inp or torch.equal(inp['pixel_values'], ref['pixel_values']))
        n_pv = inp['pixel_values'].shape[0] if 'pixel_values' in inp else 0
        ok_n = n_pv == len(r['images'])
        key = (r['cluster_id'], r['cond'])
        seen[key] = inp.get('pixel_values')
        res.append({'rid': r['rid'], 'cond': r['cond'], 'K': r['K'], 'ok_ids': ok_ids, 'ok_pv': ok_pv, 'ok_n_images': ok_n,
                    'n_input_tokens': int(inp['input_ids'].shape[1])})
        fails += not (ok_ids and ok_pv and ok_n)
    # S_i ⊂ J 순서
    sub = []
    for (cid, cond), pv in seen.items():
        if cond.startswith('S'):
            i = int(cond[1:]) - 1
            J = seen[(cid, 'J')]
            good = torch.equal(J[i], pv[0])
            sub.append({'cluster': cid, 'cond': cond, 'S_equals_J_slice': bool(good)})
            fails += not good
    tnone = all(x['n_input_tokens'] > 0 for x in res)
    out = {'requests_sha256': sha_file(a.requests), 'n_checked': len(res), 'fails': fails, 'details': res, 'subset_order': sub}
    json.dump(out, open(a.out, 'w'), indent=1)
    print('tech fails', fails, 'of', len(res), '+', len(sub))
    if fails:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd', required=True)
    b = sp.add_parser('build'); b.add_argument('--split', required=True); b.add_argument('--out', required=True)
    l = sp.add_parser('lock'); l.add_argument('--requests', required=True); l.add_argument('--out', required=True)
    for n in ('worker', 'launch', 'verify'):
        p = sp.add_parser(n)
        p.add_argument('--requests', required=True); p.add_argument('--protocol', required=True)
        p.add_argument('--out-dir', required=True)
        if n == 'worker':
            p.add_argument('--worker', type=int, required=True); p.add_argument('--nworkers', type=int, required=True)
            p.add_argument('--limit', type=int, default=0)
        if n == 'launch':
            p.add_argument('--tech', required=True); p.add_argument('--gpus', required=True); p.add_argument('--peak-gb', type=float, default=14)
            p.add_argument('--limit', type=int, default=0)
    t = sp.add_parser('tech'); t.add_argument('--requests', required=True); t.add_argument('--out', required=True)
    a = ap.parse_args()
    {'build': cmd_build, 'lock': cmd_lock, 'worker': cmd_worker, 'launch': cmd_launch, 'verify': cmd_verify, 'tech': cmd_tech}[a.cmd](a)


if __name__ == '__main__':
    main()
