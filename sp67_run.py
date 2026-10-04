"""iter_067 Modic 후보(A/B/C/D) 점수 runner. 공식 model.forward 마지막 위치 logits에서 후보 점수를 얻는다(custom lm_head·m66 helper 없음).
모델 로딩·공식 입력 구성·영상 tensor sha·읽기 함수는 m65_run(및 msd56_run.load_model)을 재사용하고 MSD 전용 CLI/비용 sidecar는 쓰지 않는다.
서브명령: requests | lock | worker | launch | tech
조건: S1(T1), S2(T2), J(T1 뒤 T2), R(선택 singleton 복제), T(text-only).
"""
import argparse, glob, hashlib, json, os, subprocess, sys, time

import m65_run as M65

OUT = 'results/iter_067'
CODE = ['sp67_run.py', 'sp67_data.py', 'm65_run.py', 'msd56_run.py', 'sp67_render.py']
OPT = ['A', 'B', 'C', 'D']
MODELS = ('medgemma', 'qwen')
Q = ('Which Modic endplate-change grade applies to the vertebral endplates adjacent to the intervertebral disc at the center of the images? '
     'Options: A. Modic 0 (no endplate change)  B. Modic I  C. Modic II  D. Modic III. Answer with a single letter.')
HEAD = 'Sagittal lumbar spine MRI slices, each cropped around one intervertebral disc at the image center (superior at top, anterior at left). '


def prompt_for(cond, n1, n2):
    if cond == 'S1':
        return HEAD + f'The {n1} images are consecutive sagittal slices of the T1-weighted sequence. ' + Q
    if cond == 'S2':
        return HEAD + f'The {n2} images are consecutive sagittal slices of the T2-weighted sequence. ' + Q
    if cond == 'J':
        return HEAD + f'The first {n1} images are consecutive sagittal slices of the T1-weighted sequence, followed by {n2} consecutive slices of the T2-weighted sequence of the same examination. ' + Q
    if cond in ('RT1', 'RT2'):
        s, n = ('T1', n1) if cond == 'RT1' else ('T2', n2)
        return HEAD + f'The first {n} images are consecutive sagittal slices of the {s}-weighted sequence, followed by an identical copy of the same {n} images (no other sequence is provided). ' + Q
    if cond == 'T':   # J와 동일 문구, 영상 없음
        return prompt_for('J', n1, n2)
    raise ValueError(cond)


def sha_s(x):
    return hashlib.sha256(x.encode()).hexdigest()


def build_requests(split, renders, pairs, conds, out):
    R = {r['patient']: r for r in renders}
    rows = []
    for p in pairs:
        pid = p['patient']
        for it in p['ivd']:
            k = str(it['k'])
            e1, e2 = R[pid]['seq']['t1']['ivd'][k], R[pid]['seq']['t2']['ivd'][k]
            p1, p2 = e1['paths'], e2['paths']
            h1, h2 = e1['png_sha256'], e2['png_sha256']
            for c in conds:
                im, sh = {'S1': (p1, h1), 'S2': (p2, h2), 'J': (p1 + p2, h1 + h2), 'RT1': (p1 + p1, h1 + h1), 'RT2': (p2 + p2, h2 + h2), 'T': ([], [])}[c]
                rows.append({'rid': f'{split}|{pid}|{k}|{c}', 'split': split, 'patient': pid, 'ivd': int(k), 'cond': c,
                             'images': im, 'img_sha': sh, 'prompt': prompt_for(c, len(p1), len(p2))})
    assert len({r['rid'] for r in rows}) == len(rows)
    with open(out, 'w') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')
    return rows


def cmd_requests(a):
    renders = json.load(open(a.render))
    pairs = json.load(open(a.pairs))
    keep = {r['patient'] for r in renders}
    pairs = [p for p in pairs if p['patient'] in keep]
    rows = build_requests(a.split, renders, pairs, a.conds.split(','), a.out)
    print(len(rows), 'requests ->', a.out)


# ---------------- protocol ----------------
def protocol_components(requests, labels):
    return {'code': {f: M65.sha_file(f) for f in CODE}, 'requests': M65.sha_file(requests), 'labels': M65.sha_file(labels),
            'candidates': OPT, 'qwen_fetch': M65.sha_file(M65.QFETCH)}


def cmd_lock(a):
    comp = protocol_components(a.requests, a.labels)
    if os.path.exists(a.out):
        raise SystemExit('protocol exists; refusing to overwrite')
    json.dump(comp, open(a.out, 'w'), indent=1)


def check_protocol(protocol, requests, labels):
    comp = protocol_components(requests, labels)
    old = json.load(open(protocol))
    bad = [k for k in comp if comp[k] != old.get(k)]
    if bad:
        raise SystemExit(f'protocol mismatch: {bad}')
    return M65.sha_s(json.dumps(old, sort_keys=True))


# ---------------- scoring ----------------
def cand_ids(proc):
    tok = proc.tokenizer
    ids = []
    for c in OPT:
        t = tok.encode(c, add_special_tokens=False)
        if len(t) != 1:
            raise RuntimeError(f'candidate {c} not a single token: {t}')
        ids.append(t[0])
    assert len(set(ids)) == 4
    return ids


VIS_CHUNK = int(os.environ.get('SP67_VIS_CHUNK', '8'))


def patch_vision(model, m, chunk=None):
    """영상별로 독립인 vision tower를 chunk 단위로 호출(메모리 절감). 영상 수·해상도·순서는 바꾸지 않는다."""
    chunk = chunk or VIS_CHUNK
    inner = m.model
    orig = getattr(inner, '_sp67_orig_gif', None) or inner.get_image_features
    inner._sp67_orig_gif = orig
    if model == 'medgemma':
        def gif(pixel_values, **kw):
            import torch
            outs = [orig(pixel_values[i:i + chunk], **kw) for i in range(0, pixel_values.shape[0], chunk)]
            head = outs[0]
            head.pooler_output = torch.cat([o.pooler_output for o in outs], 0)
            return head
    else:
        def gif(pixel_values, image_grid_thw, **kw):
            import torch
            sizes = [int(t * h * w) for t, h, w in image_grid_thw.tolist()]
            outs, s = [], 0
            for i in range(0, len(sizes), chunk):
                n = sum(sizes[i:i + chunk])
                o = orig(pixel_values[s:s + n], image_grid_thw[i:i + chunk], **kw)
                outs.append(o); s += n
            head = outs[0]
            if hasattr(head, 'pooler_output'):
                head.pooler_output = tuple(x for o in outs for x in o.pooler_output)
                return head
            return tuple(x for o in outs for x in o)
    inner.get_image_features = gif


def to_dev(torch, inp):
    return {k: (v.to('cuda', dtype=torch.bfloat16) if k == 'pixel_values' else v.to('cuda')) for k, v in inp.items()}


def score_one(model, torch, proc, m, cids, row):
    for p, h in zip(row['images'], row['img_sha']):
        if M65.sha_file(p) != h:
            raise RuntimeError(f'image hash mismatch {p}')
    t0 = time.perf_counter()
    inp = M65.build_inputs(model, proc, row)
    ids = inp['input_ids'][0].tolist()
    n_img = sum(1 for t in ids if t == M65.image_token_id(model, m))
    if n_img != M65.expected_img_tokens(model, inp, len(row['images'])):
        raise RuntimeError(f"input structure mismatch {row['rid']}")
    pxs, grids = M65.per_image_pixels(model, inp) if row['images'] else ([], None)
    x = to_dev(torch, inp)
    torch.cuda.synchronize(); torch.cuda.reset_peak_memory_stats()
    t1 = time.perf_counter()
    with torch.no_grad():
        out = m(**x, logits_to_keep=1)
    lg = out.logits[0, -1].float()
    torch.cuda.synchronize()
    t2 = time.perf_counter()
    cl = lg[cids].cpu().tolist()
    probs_full = torch.softmax(lg, -1)
    top = int(lg.argmax())
    mass = float(probs_full[cids].sum())
    c = torch.tensor(cl)
    p4 = torch.softmax(c, -1).tolist()
    return {'rid': row['rid'], 'split': row['split'], 'patient': row['patient'], 'ivd': row['ivd'], 'cond': row['cond'],
            'cand_logits': cl, 'cand_probs': p4, 'pred': OPT[int(c.argmax())], 'top_token_id': top,
            'top_token': proc.tokenizer.decode([top]), 'top_in_candidates': top in cids, 'cand_mass_full': mass,
            'n_input_tokens': len(ids), 'n_images': len(row['images']), 'n_image_tokens': n_img,
            'img_pixel_sha': pxs, 'input_ids_sha': M65.sha_s(json.dumps(ids)), 'img_grid_thw': grids,
            't_read_proc_s': t1 - t0, 't_forward_s': t2 - t1, 't_total_s': time.perf_counter() - t0,
            'peak_alloc_gb': torch.cuda.max_memory_allocated() / 2**30, 'peak_reserved_gb': torch.cuda.max_memory_reserved() / 2**30}


def done_ids(out_dir):
    d = set()
    for f in glob.glob(f'{out_dir}/worker*.jsonl'):
        for r in M65.read_jsonl(f):
            d.add(r['rid'])
    return d


def cmd_worker(a):
    pdig = check_protocol(a.protocol, a.requests, a.labels)
    rows = M65.read_jsonl(a.requests)
    mine = [r for i, r in enumerate(rows) if i % a.nworkers == a.widx]
    os.makedirs(a.out_dir, exist_ok=True)
    path = f'{a.out_dir}/worker{a.widx}.jsonl'
    lockp = f'{a.out_dir}/worker{a.widx}.lock'
    fd = os.open(lockp, os.O_CREAT | os.O_RDWR)
    import fcntl
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)   # 같은 worker slot의 동시 실행 거부
    removed = M65.repair_tail(path)
    done = done_ids(a.out_dir)
    todo = [r for r in mine if r['rid'] not in done]
    if a.limit:
        todo = todo[:a.limit]
    print(f'worker{a.widx}: mine={len(mine)} done={len(mine) - len(todo)} todo={len(todo)} repaired_bytes={removed}', flush=True)
    torch, proc, m = M65.load_model(a.model)
    patch_vision(a.model, m)
    cids = cand_ids(proc)
    env = M65.env_info(a.model, torch, proc, m)
    env['pid'] = os.getpid()
    json.dump({'env': env, 'protocol_digest': pdig, 'cand_ids': cids}, open(f'{a.out_dir}/worker{a.widx}.env.json', 'w'), indent=1)
    t0 = time.time()
    for i, r in enumerate(todo):
        rec = score_one(a.model, torch, proc, m, cids, r)
        rec['protocol_digest'] = pdig
        rec['worker'] = a.widx
        M65.append_row(path, rec)
        if i % 20 == 0:
            print(f'worker{a.widx} {i + 1}/{len(todo)} {time.time() - t0:.0f}s', flush=True)
    print(f'worker{a.widx} done', flush=True)


def smi_free():
    out = subprocess.run(['nvidia-smi', '--query-gpu=index,memory.used,memory.total', '--format=csv,noheader,nounits'], capture_output=True, text=True).stdout
    return {int(l.split(',')[0]): int(l.split(',')[2]) - int(l.split(',')[1]) for l in out.strip().splitlines()}


def cmd_launch(a):
    """a.assign: 'gpu:model:widx:nworkers' 쉼표 목록. 물리 GPU index를 CUDA_VISIBLE_DEVICES로 부여."""
    allowed = os.environ.get('CUDA_VISIBLE_DEVICES', '0,1').split(',')
    free = smi_free()
    procs = []
    need_gb = {'medgemma': a.need_mg, 'qwen': a.need_qw}
    used = {}
    for item in a.assign.split(','):
        gpu, model, widx, nw = item.split(':')
        if gpu not in allowed:
            raise SystemExit(f'gpu {gpu} not in allowed {allowed}')
        used[gpu] = used.get(gpu, 0) + need_gb[model] + 2
        if used[gpu] * 1024 > free[int(gpu)]:
            raise SystemExit(f'admission failed gpu {gpu}: need {used[gpu]} GiB free {free[int(gpu)]} MiB')
    for item in a.assign.split(','):
        gpu, model, widx, nw = item.split(':')
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=gpu, PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True')
        od = f'{a.out_root}/{model}'
        os.makedirs(od, exist_ok=True)
        cmd = [sys.executable, 'sp67_run.py', 'worker', '--model', model, '--requests', a.requests, '--labels', a.labels, '--protocol', a.protocol,
               '--out-dir', od, '--widx', widx, '--nworkers', nw]
        if a.limit:
            cmd += ['--limit', str(a.limit)]
        log = open(f'{od}/worker{widx}.log', 'a')
        procs.append((item, subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)))
    rcs = {item: p.wait() for item, p in procs}
    json.dump({'assign': a.assign, 'rcs': rcs, 'time': time.time()}, open(f'{a.out_root}/launch_{int(time.time())}.json', 'w'))
    print(rcs)
    if any(rcs.values()):
        raise SystemExit(1)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('requests'); p.add_argument('--split'); p.add_argument('--render'); p.add_argument('--pairs'); p.add_argument('--conds', default='S1,S2,J,T'); p.add_argument('--out')
    p = sub.add_parser('lock'); p.add_argument('--requests'); p.add_argument('--labels'); p.add_argument('--out')
    p = sub.add_parser('worker'); p.add_argument('--model', choices=MODELS); p.add_argument('--requests'); p.add_argument('--labels'); p.add_argument('--protocol')
    p.add_argument('--out-dir'); p.add_argument('--widx', type=int); p.add_argument('--nworkers', type=int); p.add_argument('--limit', type=int, default=0)
    p = sub.add_parser('launch'); p.add_argument('--assign'); p.add_argument('--requests'); p.add_argument('--labels'); p.add_argument('--protocol')
    p.add_argument('--out-root'); p.add_argument('--limit', type=int, default=0); p.add_argument('--need-mg', type=float, default=14); p.add_argument('--need-qw', type=float, default=20)
    a = ap.parse_args()
    {'requests': cmd_requests, 'lock': cmd_lock, 'worker': cmd_worker, 'launch': cmd_launch}[a.cmd](a)


if __name__ == '__main__':
    main()
