"""iter_123: MedGemma 1.5 frozen 추론 요청 구성/worker/parser. 조건 C(중앙8), W(넓은8), P1/P2(W를 inferior4/superior4로 분할).
usage:
  python mr123_run.py requests <stage> <build_json> [<build_json>...]   # 요청 파일 생성(출력 전 잠금)
  python mr123_run.py worker <stage> <worker_id> <max_new_tokens> [--limit N] [--batch B]
"""
import hashlib, json, os, re, sys, time
import mr123_data as D

MODEL = 'google/medgemma-1.5-4b-it'
REV = '91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b'
CACHE = '/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache'
GEN = D.RES + 'gen/'
STATES = ['PRESENT', 'ABSENT', 'UNCERTAIN']

PROMPT = ('You are shown {n} axial FLAIR MRI slices from one brain MRI examination, {order}. '
          'Question: Is there evidence of pathological hyperintense signal on FLAIR in the periventricular white matter in the images shown? '
          'Answer on the first line with exactly one word: PRESENT, ABSENT, or UNCERTAIN. '
          'Then give a brief justification (at most two sentences).')


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def make_requests(builds):
    reqs = []
    for b in builds:
        for sid, info in b.items():
            if info.get('exclude') is not None:
                continue
            W = info['W_idx']
            conds = {'C': (info['C_idx'], 'ordered from inferior to superior'), 'W': (W, 'ordered from inferior to superior'),
                     'P1': (W[:4], 'ordered from inferior to superior (lower half of the covered range)'),
                     'P2': (W[4:], 'ordered from inferior to superior (upper half of the covered range)')}
            for c, (idx, order) in conds.items():
                paths = [info['pngs'][str(k)]['path'] for k in idx]
                hs = [info['pngs'][str(k)]['sha256'] for k in idx]
                prompt = PROMPT.format(n=len(idx), order=order)
                rid = sha('|'.join([str(info['patient_uid']), c, ','.join(hs), prompt, REV]))[:20]
                reqs.append(dict(id=rid, patient_uid=info['patient_uid'], study_uid=sid, cond=c, slice_idx=idx, paths=paths, png_sha256=hs,
                                 prompt=prompt, model=MODEL, revision=REV, label=info['label'], batch_id=info['batch_id'], role=info['role']))
    return reqs


def messages_for(r):
    from PIL import Image
    content = []
    for i, p in enumerate(r['paths']):
        content.append({'type': 'text', 'text': f'Image {i + 1}:'})
        content.append({'type': 'image', 'image': Image.open(p).convert('RGB')})
    content.append({'type': 'text', 'text': r['prompt']})
    return [{'role': 'user', 'content': content}]


def parse(text):
    """첫 줄의 단일 상태. return (state, code). state in PRESENT/ABSENT/UNCERTAIN/INVALID"""
    t = (text or '').strip()
    lines = [l for l in t.split('\n') if l.strip()]
    if not lines:
        return 'INVALID', 'empty'
    first = re.sub(r'[*_`#>\-:.\[\]()"]', ' ', lines[0]).strip()
    found = [s for s in STATES if re.search(r'\b' + s + r'\b', first, re.I)]
    if len(found) == 1:
        strict = re.fullmatch(r'\s*' + found[0] + r'\s*', first, re.I) is not None
        return found[0], 'ok_strict' if strict else 'ok_loose'
    if len(found) > 1:
        return 'INVALID', 'multi_state'
    if re.search(r'cannot|unable|can\'?t|not able|I am sorry|sorry', t[:300], re.I):
        return 'INVALID', 'refusal'
    return 'INVALID', 'no_state'


def agg_P(s1, s2):
    if 'PRESENT' in (s1, s2):
        return 'PRESENT'
    if s1 == 'ABSENT' and s2 == 'ABSENT':
        return 'ABSENT'
    return 'UNCERTAIN'


def read_jsonl(p):
    out = []
    if not os.path.exists(p):
        return out
    with open(p, 'rb') as f:
        data = f.read()
    for line in data.split(b'\n'):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            break  # torn tail
    return out


def repair_tail(p):
    if not os.path.exists(p):
        return
    with open(p, 'rb') as f:
        data = f.read()
    good = 0
    pos = 0
    for line in data.split(b'\n'):
        end = pos + len(line) + 1
        if line.strip():
            try:
                json.loads(line)
            except Exception:
                break
        good = min(end, len(data))
        pos = end
    if good < len(data):
        with open(p, 'rb+') as f:
            f.truncate(good)


def done_ids(stage):
    d = GEN + stage
    ids = set()
    if os.path.isdir(d):
        for fn in os.listdir(d):
            if fn.startswith('worker_') and fn.endswith('.jsonl'):
                ids |= {r['id'] for r in read_jsonl(os.path.join(d, fn))}
    return ids


def worker(stage, wid, max_new, limit=None, batch=1):
    import torch
    from transformers import AutoProcessor, AutoModelForImageTextToText
    reqs = read_jsonl(GEN + stage + '/requests.jsonl')
    out_p = GEN + stage + f'/worker_{wid}.jsonl'
    repair_tail(out_p)
    cdir = GEN + stage + '/claims'
    os.makedirs(cdir, exist_ok=True)
    t0 = time.perf_counter()
    proc = AutoProcessor.from_pretrained(MODEL, revision=REV, cache_dir=CACHE)
    model = AutoModelForImageTextToText.from_pretrained(MODEL, revision=REV, cache_dir=CACHE, torch_dtype=torch.bfloat16, device_map={'': 0})
    model.eval()
    load_s = time.perf_counter() - t0
    print(json.dumps(dict(event='loaded', wid=wid, load_s=load_s, gpu=os.environ.get('CUDA_VISIBLE_DEVICES'))), flush=True)
    done = done_ids(stage)
    n = 0
    f = open(out_p, 'a')
    pending = [r for r in reqs if r['id'] not in done]
    while pending:
        group = []
        for r in pending:
            if len(group) >= batch:
                break
            try:
                fd = os.open(os.path.join(cdir, r['id'] + '.claim'), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, f'{wid}:{os.getpid()}'.encode()); os.close(fd)
                group.append(r)
            except FileExistsError:
                continue
        pending = [r for r in pending if r not in group and r['id'] not in done]
        if not group:
            break
        ts = time.perf_counter()
        msgs = [messages_for(r) for r in group]
        if batch == 1:
            inp = proc.apply_chat_template(msgs[0], add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors='pt')
        else:
            proc.tokenizer.padding_side = 'left'
            inp = proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors='pt', padding=True)
        inp = inp.to(model.device)
        inp['pixel_values'] = inp['pixel_values'].to(torch.bfloat16)
        plen = inp['input_ids'].shape[1]
        te = time.perf_counter()
        with torch.inference_mode():
            gen = model.generate(**inp, max_new_tokens=max_new, do_sample=False)
        tg = time.perf_counter()
        eos_ids = set([proc.tokenizer.eos_token_id] + ([model.generation_config.eos_token_id] if isinstance(model.generation_config.eos_token_id, int) else list(model.generation_config.eos_token_id or [])))
        for i, r in enumerate(group):
            new = gen[i, plen:].tolist()
            ended = any(t in eos_ids for t in new)
            while new and new[-1] == proc.tokenizer.pad_token_id:
                new.pop()
            text = proc.tokenizer.decode(new, skip_special_tokens=True)
            st, code = parse(text)
            rec = dict(id=r['id'], study_uid=r['study_uid'], cond=r['cond'], text=text, state=st, parse_code=code, eos=bool(ended),
                       n_new=len(new), prompt_tokens=int((inp['attention_mask'][i]).sum()), max_new=max_new, wid=wid, batch=batch,
                       prep_s=te - ts, gen_s=tg - te, wall_s=tg - ts, n_img=len(r['paths']), t_end=time.time(),
                       peak_mem_mib=torch.cuda.max_memory_allocated() / 2 ** 20, load_s=load_s, input_ids_sha=hashlib.sha256(inp['input_ids'][i].cpu().numpy().tobytes()).hexdigest())
            f.write(json.dumps(rec) + '\n')
        f.flush(); os.fsync(f.fileno())
        n += len(group)
        if limit and n >= limit:
            break
    f.close()
    print(json.dumps(dict(event='done', wid=wid, n=n)), flush=True)


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'requests':
        stage = sys.argv[2]
        builds = [json.load(open(p)) for p in sys.argv[3:]]
        reqs = make_requests(builds)
        d = GEN + stage
        os.makedirs(d, exist_ok=True)
        p = d + '/requests.jsonl'
        assert not os.path.exists(p), 'requests 잠금 존재'
        assert len({r['id'] for r in reqs}) == len(reqs)
        with open(p, 'w') as f:
            for r in reqs:
                f.write(json.dumps(r) + '\n')
        print(len(reqs), 'requests', hashlib.sha256(open(p, 'rb').read()).hexdigest())
    elif cmd == 'worker':
        stage, wid, mx = sys.argv[2], sys.argv[3], int(sys.argv[4])
        lim = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else None
        bs = int(sys.argv[sys.argv.index('--batch') + 1]) if '--batch' in sys.argv else 1
        worker(stage, wid, mx, lim, bs)
