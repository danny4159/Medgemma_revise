"""iter_075 MedGemma 3영상 grade 생성 평가 worker (batch=1, bf16, greedy, 최대 32 new tokens) + 후보 grade sequence log-likelihood.

- 요청 = (variant F/R, adapter(None=base 또는 epoch dir), target id 목록). request_id = sha(model_rev|adapter_digest|variant|target|prompt_sha|config)
- 출력: <out-dir>/gen_worker{K}.jsonl (worker별 append+fsync). 기존 모든 worker 출력을 현재 입력(pixel hash)·adapter·prompt·config와 대조하고
  중복·충돌·집합 밖 record는 중단. 완료 요청은 건너뛴다(존재만이 아니라 provenance 일치가 있을 때만).
- 작업 소유권: id별 flock claim(rsna_diag.queue_lock). worker lock도 사용.
- GT grade는 읽지 않는다(manifest의 inputs만 사용).
- 후보 likelihood: prompt 뒤에 '<d><end_of_turn>' 전체 sequence의 log P (digit 1개 token + EOT).
사용: python sp75_gen.py --variant F --split V8 --positions supervised --adapter DIR|none --out-dir D --worker K --gpu 0 [--max-requests N]
"""
import argparse, glob, hashlib, json, os, sys, time

import sp75_data as D
import sp75_vlm as V
from rsna_diag import generate, lora, queue_lock

RUNNER = 'sp75_gen_v1'


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()


def request_id(adapter_digest, variant, tid, prompt_sha, cfg_digest):
    return sha(f'{generate.MODEL_REVISION}|{adapter_digest or "base"}|{variant}|{tid}|{prompt_sha}|{cfg_digest}')[:32]


def read_jsonl(p):
    out = []
    if os.path.exists(p):
        for ln in open(p):
            ln = ln.strip()
            if ln:
                out.append(json.loads(ln))
    return out


def select_rows(split, positions):
    man = D.load_manifest()
    rows = [r for r in man['rows'] if r['split'] == split and not r['excluded']]
    if positions != 'all':
        rows = [r for r in rows if r['position_set'] == positions]
    rows.sort(key=lambda r: (int(r['patient']), r['ordinal']))
    return rows


def cand_ids(tok):
    """'1'..'5' + <end_of_turn> token id 목록. digit은 단일 token이어야 한다."""
    ids = []
    eot = tok.convert_tokens_to_ids('<end_of_turn>')
    for d in '12345':
        t = tok(d, add_special_tokens=False)['input_ids']
        if len(t) != 1:
            raise RuntimeError(f'digit {d} not single token: {t}')
        ids.append((t[0], eot))
    return ids


def run_one(torch, proc, model, row, variant, eos_ids, cands):
    ims = V.load_images(row['inputs'][variant])
    inp = V.build_gen_inputs(proc, ims, V.PROMPTS[variant])
    x = {k: (v.cuda().to(torch.bfloat16) if k == 'pixel_values' else v.cuda()) for k, v in inp.items()}
    n_in = x['input_ids'].shape[1]
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    with torch.no_grad():
        out = model.generate(**x, max_new_tokens=V.MAX_NEW, do_sample=False)
    torch.cuda.synchronize()
    dt = time.time() - t0
    ids = out[0, n_in:].tolist()
    ended = len(ids) > 0 and ids[-1] in eos_ids
    text = proc.tokenizer.decode(ids, skip_special_tokens=True)
    raw = proc.tokenizer.decode(ids, skip_special_tokens=False)
    # 후보 sequence log-likelihood: 한 번의 prefix forward + 후보별 두 위치. 전체 prompt+candidate를 한 번씩 forward (5회, batch 1)
    lls = []
    with torch.no_grad():
        for d, eot in cands:
            ids2 = torch.cat([x['input_ids'], torch.tensor([[d, eot]], device='cuda')], 1)
            att = torch.ones_like(ids2)
            kw = {'input_ids': ids2, 'attention_mask': att, 'pixel_values': x['pixel_values'], 'use_cache': False}
            if 'token_type_ids' in x:
                kw['token_type_ids'] = torch.cat([x['token_type_ids'], torch.zeros((1, 2), dtype=x['token_type_ids'].dtype, device='cuda')], 1)
            lg = model(**kw).logits[0, n_in - 1:n_in + 1].float()   # 위치 n_in-1 -> digit, n_in -> EOT
            lp = torch.log_softmax(lg, dim=-1)
            lls.append(float(lp[0, d] + lp[1, eot]))
    return {'suffix_ids': ids, 'text': text, 'raw': raw, 'ended_eos': bool(ended), 'n_new': len(ids), 'parsed': V.parse(text) if ended else None,
            'parse_valid': bool(ended and V.parse(text) is not None), 'cand_loglik': lls, 'n_input_tokens': n_in, 'runtime_s': dt,
            'peak_mem_gb': torch.cuda.max_memory_allocated() / 2 ** 30}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--variant', choices=['F', 'R'], required=True)
    ap.add_argument('--split', required=True)
    ap.add_argument('--positions', default='supervised', choices=['supervised', 'held', 'all'])
    ap.add_argument('--adapter', default='none')
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--worker', type=int, required=True)
    ap.add_argument('--gpu', default=None)
    ap.add_argument('--max-requests', type=int, default=None)
    ap.add_argument('--ids', default=None, help='json list of target ids (subset)')
    a = ap.parse_args()
    if a.gpu is not None:
        inh = os.environ.get('CUDA_VISIBLE_DEVICES', '').split(',')
        if a.gpu not in inh:
            sys.exit(f'gpu {a.gpu} not in inherited {inh}')
        os.environ['CUDA_VISIBLE_DEVICES'] = a.gpu
    rows = select_rows(a.split, a.positions)
    if a.ids:
        keep = set(json.load(open(a.ids)))
        rows = [r for r in rows if r['id'] in keep]
    os.makedirs(a.out_dir, exist_ok=True)
    info = queue_lock.my_info(worker=a.worker)
    lk, own, _ = queue_lock.try_lock(os.path.join(a.out_dir, f'worker{a.worker}.lock'), info)
    if lk is None:
        sys.exit(f'worker {a.worker} already running {own}')
    try:
        work(a, rows, info)
    finally:
        lk.release()


def work(a, rows, info):
    torch, proc, model = generate.load_model()
    adapter_digest = None
    if a.adapter != 'none':
        adapter_digest = generate.load_adapter(torch, model, a.adapter)
    env = generate.env_info(torch, proc, model)
    prompt_sha = sha(V.PROMPTS[a.variant])
    cfg = {'runner': RUNNER, 'model_revision': generate.MODEL_REVISION, 'max_new_tokens': V.MAX_NEW, 'do_sample': False, 'dtype': env['dtype'],
           'chat_template_sha256': env['chat_template_sha256'], 'transformers': env['transformers'], 'torch': env['torch'], 'variant': a.variant,
           'prompt_sha256': prompt_sha, 'eos_token_id': env['eos_token_id'], 'parser': 'whole-string [1-5] with optional trailing period; non-EOS invalid'}
    cdig = sha(json.dumps(cfg, sort_keys=True, default=str))
    eos = env['eos_token_id']
    eos_ids = set(eos if isinstance(eos, list) else [eos])
    cands = cand_ids(proc.tokenizer)
    by_id = {r['id']: r for r in rows}
    env_path = os.path.join(a.out_dir, f'gen_worker{a.worker}.env.json')
    if not os.path.exists(env_path):
        json.dump({'env': env, 'config': cfg, 'config_digest': cdig, 'adapter': a.adapter, 'adapter_digest': adapter_digest, 'manifest_sha256': sha(open(f'{D.DATA}/manifest.json', 'rb').read())},
                  open(env_path, 'w'), indent=1, default=str)

    def read_all():
        return {f: read_jsonl(f) for f in sorted(glob.glob(os.path.join(a.out_dir, 'gen_worker*.jsonl')))}

    def validate(files):
        done, seen = {}, {}
        for fn, recs in files.items():
            for r in recs:
                row = by_id.get(r.get('id'))
                if row is None:
                    raise RuntimeError(f'unexpected record {r.get("id")} in {fn}')
                rid = request_id(adapter_digest, a.variant, r['id'], prompt_sha, cdig)
                if r.get('request_id') != rid:
                    raise RuntimeError(f'request_id mismatch {r["id"]} in {fn} (model/adapter/prompt/config differs)')
                if rid in seen:
                    raise RuntimeError(f'duplicate request {r["id"]}: {seen[rid]} and {fn}')
                seen[rid] = fn
                if r.get('config_digest') != cdig or r.get('adapter_digest') != adapter_digest:
                    raise RuntimeError(f'config/adapter digest mismatch {r["id"]}')
                want = [e['pixel_sha256_padded'] for e in row['inputs'][a.variant]]
                if r.get('input_pixel_sha256') != want:
                    raise RuntimeError(f'input pixel hash differs from manifest for {r["id"]}')
                done[r['id']] = r
        return done

    done = validate(read_all())
    out = os.path.join(a.out_dir, f'gen_worker{a.worker}.jsonl')
    claim_dir = os.path.join(a.out_dir, 'claims')
    os.makedirs(claim_dir, exist_ok=True)
    log = open(out + '.log', 'a')
    n_new, t_start = 0, time.time()
    for row in rows:
        if row['id'] in done:
            continue
        if a.max_requests is not None and n_new >= a.max_requests:
            log.write(json.dumps({'event': 'stop', 'new': n_new}) + '\n')
            break
        clk, prev, reclaimed = queue_lock.try_lock(os.path.join(claim_dir, row['id'] + '.claim'), info)
        if clk is None:
            continue
        try:
            done = validate(read_all())
            if row['id'] in done:
                continue
            rec = run_one(torch, proc, model, row, a.variant, eos_ids, cands)
            rec.update({'id': row['id'], 'patient': row['patient'], 'ordinal': row['ordinal'], 'split': row['split'], 'position_set': row['position_set'],
                        'variant': a.variant, 'request_id': request_id(adapter_digest, a.variant, row['id'], prompt_sha, cdig), 'config_digest': cdig,
                        'adapter_digest': adapter_digest, 'input_pixel_sha256': [e['pixel_sha256_padded'] for e in row['inputs'][a.variant]],
                        'input_file_sha256': [e['file_sha256'] for e in row['inputs'][a.variant]], 'worker': a.worker, 'ts': time.time(),
                        'gpu_uuid': env.get('gpu_uuid'), 'reclaimed_claim': bool(reclaimed)})
            with open(out, 'a') as f:
                f.write(json.dumps(rec) + '\n')
                f.flush()
                os.fsync(f.fileno())
            done[row['id']] = rec
            n_new += 1
            log.write(json.dumps({'event': 'done', 'id': row['id'], 'text': rec['text'], 'parsed': rec['parsed'], 'runtime_s': round(rec['runtime_s'], 2), 'elapsed': round(time.time() - t_start, 1)}) + '\n')
            log.flush()
        finally:
            clk.release()
    print(f'worker {a.worker}: {n_new} new requests', flush=True)


if __name__ == '__main__':
    main()
