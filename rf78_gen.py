"""iter_078 참고 사례 조건 생성 worker (batch=1, bf16, greedy, 최대 32 new tokens, 후보 likelihood 없음).

- 입력: results/iter_078/data/refs_{split}.json (query grade 없음). cond = Q|L|I|D.
- request_id = sha(model_rev|adapter_digest|cond|id|query pixel|ref ids|ref pixel|ref grades|prompt digest|config digest)
- 출력 <out-dir>/gen_worker{K}.jsonl(append+fsync). 모든 worker 출력을 현재 요청에서 재계산한 request_id·입력 hash와 대조하고
  중복·집합 밖 record는 중단. id별 flock claim, worker flock lock, torn tail repair.
- --lock: 사전 잠금(코드·요청 파일 hash, adapter digest, cond/out-dir 등록)을 모두 확인.
사용: python rf78_gen.py --split V8 --cond I --adapter results/iter_077/train/R_lr2e-4/epoch_16 --out-dir D --worker K --gpu 0 [--max-requests N] [--ids ids.json] [--lock L]
"""
import argparse, glob, hashlib, json, os, sys, time

import sp75_gen as SG
import sp75_vlm as V
import rf78_vlm as RV
from rsna_diag import generate, queue_lock

RUNNER = 'rf78_gen_v1'
DATA = 'results/iter_078/data'
sha = SG.sha


def request_id(adapter_digest, cond, rid, f, prompt_dig, cfg_digest):
    s = json.dumps({'model': generate.MODEL_REVISION, 'adapter': adapter_digest or 'base', 'cond': cond, 'id': rid, 'f': f, 'prompt': prompt_dig, 'cfg': cfg_digest}, sort_keys=True)
    return sha(s)[:32]


def load_requests(split):
    p = f'{DATA}/refs_{split}.json'
    d = json.load(open(p))
    return d['requests'], sha(open(p, 'rb').read())


def load_imgs(entries):
    return V.load_images(entries)


def make_inputs(proc, cond, req):
    if cond in ('A', 'T', 'X'):
        imgs = [] if cond == 'T' else load_imgs(req['images'])
        return RV.build_inputs(proc, cond, None, req['automated_grade'], imgs)
    tgt = load_imgs(req['query_images'])
    refs = None
    grades = None
    if cond in ('I', 'D'):
        refs = [load_imgs(r['images']) for r in req[cond]]
    if cond in ('I', 'D', 'L'):
        grades = [r['grade'] for r in req['I' if cond == 'L' else cond]]
    return RV.build_inputs(proc, cond, refs, grades, tgt)


def run_one(torch, proc, model, req, cond, eos_ids):
    t_in = time.time()
    inp, roles = make_inputs(proc, cond, req)
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
    return {'suffix_ids': ids, 'text': text, 'raw': raw, 'ended_eos': bool(ended), 'n_new': len(ids), 'parsed': V.parse(text) if ended else None,
            'parse_valid': bool(ended and V.parse(text) is not None), 'n_input_tokens': n_in, 'n_images': int(x['pixel_values'].shape[0]) if 'pixel_values' in x else 0,
            'runtime_s': dt, 'prep_s': t0 - t_in, 'peak_mem_alloc_gb': torch.cuda.max_memory_allocated() / 2 ** 30, 'peak_mem_reserved_gb': torch.cuda.max_memory_reserved() / 2 ** 30}


def check_lock(a, adapter_digest, req_sha, files_extra=()):
    lock = json.load(open(a.lock))
    for f, h in lock['files'].items():
        if sha(open(f, 'rb').read()) != h:
            sys.exit(f'locked file changed: {f}')
    if lock['requests'].get(a.split) != req_sha:
        sys.exit('requests file hash differs from lock')
    if lock['adapter_digest'] != adapter_digest:
        sys.exit('adapter digest differs from lock')
    d = lock['dirs'].get(a.cond)
    if d is None or os.path.normpath(d) != os.path.normpath(a.out_dir) or a.split != lock['split']:
        sys.exit(f'cond/out-dir/split not registered in lock: {a.cond} {a.out_dir}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--split', required=True, choices=['V8', 'E24'])
    ap.add_argument('--cond', required=True, choices=['Q', 'L', 'I', 'D'])
    ap.add_argument('--adapter', required=True)
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--worker', type=int, required=True)
    ap.add_argument('--gpu', default=None)
    ap.add_argument('--max-requests', type=int, default=None)
    ap.add_argument('--ids', default=None)
    ap.add_argument('--lock', default=None)
    a = ap.parse_args()
    if a.split == 'E24' and not a.lock:
        sys.exit('E24 generation requires --lock')
    if a.gpu is not None:
        inh = os.environ.get('CUDA_VISIBLE_DEVICES', '').split(',')
        if a.gpu not in inh:
            sys.exit(f'gpu {a.gpu} not in inherited {inh}')
        os.environ['CUDA_VISIBLE_DEVICES'] = a.gpu
    reqs, req_sha = load_requests(a.split)
    if a.ids:
        keep = set(json.load(open(a.ids)))
        reqs = [r for r in reqs if r['id'] in keep]
    os.makedirs(a.out_dir, exist_ok=True)
    info = queue_lock.my_info(worker=a.worker)
    lk, own, _ = queue_lock.try_lock(os.path.join(a.out_dir, f'worker{a.worker}.lock'), info)
    if lk is None:
        sys.exit(f'worker {a.worker} already running {own}')
    try:
        work(a, reqs, req_sha, info)
    finally:
        lk.release()


def work(a, reqs, req_sha, info):
    torch, proc, model = generate.load_model()
    adapter_digest = generate.load_adapter(torch, model, a.adapter)
    if a.lock:
        check_lock(a, adapter_digest, req_sha)
    env = generate.env_info(torch, proc, model)
    pdig = RV.prompt_digest()
    cfg = {'runner': RUNNER, 'model_revision': generate.MODEL_REVISION, 'max_new_tokens': V.MAX_NEW, 'do_sample': False, 'dtype': env['dtype'], 'batch': 1,
           'chat_template_sha256': env['chat_template_sha256'], 'transformers': env['transformers'], 'torch': env['torch'], 'cond': a.cond,
           'eos_token_id': env['eos_token_id'], 'parser': 'whole-string [1-5] with optional trailing period; non-EOS invalid', 'preprocess': generate.PREPROC_VERSION}
    cdig = sha(json.dumps(cfg, sort_keys=True, default=str))
    eos = env['eos_token_id']
    eos_ids = set(eos if isinstance(eos, list) else [eos])
    by_id = {r['id']: r for r in reqs}
    env_path = os.path.join(a.out_dir, f'gen_worker{a.worker}.env.json')
    if not os.path.exists(env_path):
        json.dump({'env': env, 'config': cfg, 'config_digest': cdig, 'adapter': a.adapter, 'adapter_digest': adapter_digest, 'requests_sha256': req_sha, 'prompt_digest': pdig,
                   'split': a.split, 'cond': a.cond}, open(env_path, 'w'), indent=1, default=str)

    def rid_of(req):
        return request_id(adapter_digest, a.cond, req['id'], RV.request_fields(req, a.cond), pdig, cdig)

    def read_all():
        return {f: SG.read_jsonl(f) for f in sorted(glob.glob(os.path.join(a.out_dir, 'gen_worker*.jsonl')))}

    def validate(files):
        done, seen = {}, {}
        for fn, recs in files.items():
            for r in recs:
                req = by_id.get(r.get('id'))
                if req is None:
                    raise RuntimeError(f'unexpected record {r.get("id")} in {fn}')
                rid = rid_of(req)
                if r.get('request_id') != rid:
                    raise RuntimeError(f'request_id mismatch {r["id"]} in {fn} (model/adapter/prompt/config/input differs)')
                if rid in seen:
                    raise RuntimeError(f'duplicate request {r["id"]}: {seen[rid]} and {fn}')
                seen[rid] = fn
                if r.get('config_digest') != cdig or r.get('adapter_digest') != adapter_digest or r.get('cond') != a.cond or r.get('split') != a.split:
                    raise RuntimeError(f'config/adapter/cond digest mismatch {r["id"]}')
                if r.get('fields') != RV.request_fields(req, a.cond):
                    raise RuntimeError(f'input fields differ from request for {r["id"]}')
                done[r['id']] = r
        return done

    out = os.path.join(a.out_dir, f'gen_worker{a.worker}.jsonl')
    rep_tail = SG.repair_tail(out)
    if rep_tail:
        print('repaired torn tail', rep_tail, flush=True)
    done = validate(read_all())
    claim_dir = os.path.join(a.out_dir, 'claims')
    os.makedirs(claim_dir, exist_ok=True)
    log = open(out + '.log', 'a')
    n_new, t_start = 0, time.time()
    for req in reqs:
        if req['id'] in done:
            continue
        if a.max_requests is not None and n_new >= a.max_requests:
            log.write(json.dumps({'event': 'stop', 'new': n_new}) + '\n')
            break
        clk, prev, reclaimed = queue_lock.try_lock(os.path.join(claim_dir, req['id'] + '.claim'), info)
        if clk is None:
            continue
        try:
            done = validate(read_all())
            if req['id'] in done:
                continue
            rec = run_one(torch, proc, model, req, a.cond, eos_ids)
            rec.update({'id': req['id'], 'patient': req['patient'], 'ordinal': req['ordinal'], 'split': a.split, 'cond': a.cond, 'request_id': rid_of(req), 'config_digest': cdig,
                        'adapter_digest': adapter_digest, 'fields': RV.request_fields(req, a.cond), 'worker': a.worker, 'ts': time.time(), 'gpu_uuid': env.get('gpu_uuid'),
                        'reclaimed_claim': bool(reclaimed)})
            with open(out, 'a') as f:
                f.write(json.dumps(rec) + '\n')
                f.flush()
                os.fsync(f.fileno())
            done[req['id']] = rec
            n_new += 1
            log.write(json.dumps({'event': 'done', 'id': req['id'], 'text': rec['text'], 'parsed': rec['parsed'], 'runtime_s': round(rec['runtime_s'], 2), 'elapsed': round(time.time() - t_start, 1)}) + '\n')
            log.flush()
        finally:
            clk.release()
    print(f'worker {a.worker}: {n_new} new requests', flush=True)


if __name__ == '__main__':
    main()
