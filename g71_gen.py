"""iter_071 MedGemma 생성 worker (greedy, 공식 processor/chat template, cap 1000->2000->4000 재시도). 요청 단위 append·재개·provenance.

- 입력: patient group key(V4/V8/E24) x 3 slice x 2 category 요청. GT는 읽지 않는다 (manifest의 id/image/file hash만 사용).
- adapter: --adapter DIR(adapter.pt) 또는 없음(base). 요청 id = sha(model|adapter digest|group|item id|prompt sha).
- 다중 worker는 요청 index modulo로 겹치지 않게 나누고 worker별 gen_worker{k}.jsonl에 쓴다. 재개 시 모든 worker 파일을 현재 입력·adapter·prompt·protocol과 대조한다.
- protocol.json(코드·manifest·prompt·model·adapter digest)은 최초 worker가 O_EXCL로 만들고, 이후 worker는 동일해야 시작한다.
사용: python g71_gen.py --key V4 --adapter DIR --out-dir D --worker 0 --nworkers 2
"""
import argparse, glob, hashlib, json, os, sys, time

import g71_data as D
import g71_train as TR
from rsna_diag import generate as GEN, queue_lock

CODE = ['g71_gen.py', 'g71_data.py', 'rsna_diag/generate.py', 'rsna_diag/lora.py', 'rsna_diag/parse.py']


def sha_file(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def requests_for(key):
    rows = TR.load_items(key)
    return [{'id': r['id'], 'image': r['image'], 'file_sha256': r['file_sha256'], 'pixel_sha256_padded': r['pixel_sha256_padded'], 'category': r['category'],
             'split': key} for r in rows]


def repair_tail(path):
    """자기 worker 파일의 마지막 미완성 줄만 제거(원본은 .torn 사본으로 보존)."""
    if not os.path.exists(path):
        return 0
    data = open(path, 'rb').read()
    if not data or data.endswith(b'\n'):
        return 0
    cut = data.rfind(b'\n') + 1
    open(path + f'.torn.{int(time.time())}', 'wb').write(data[cut:])
    with open(path, 'wb') as f:
        f.write(data[:cut])
    return len(data) - cut


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--key', required=True)
    ap.add_argument('--adapter', default=None)
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--worker', type=int, required=True)
    ap.add_argument('--nworkers', type=int, default=1)
    ap.add_argument('--max-requests', type=int, default=None)
    ap.add_argument('--ids-file', default=None, help='요청 id 부분집합(테스트용)')
    a = ap.parse_args()
    items = requests_for(a.key)
    if a.ids_file:
        keep = set(json.load(open(a.ids_file)))
        items = [i for i in items if i['id'] in keep]
    os.makedirs(a.out_dir, exist_ok=True)
    lk, own, _ = queue_lock.try_lock(os.path.join(a.out_dir, f'worker{a.worker}.lock'), queue_lock.my_info(worker=a.worker))
    if lk is None:
        sys.exit(f'worker {a.worker} already running: {own}')
    try:
        run(a, items)
    finally:
        lk.release()


def run(a, items):
    torch, proc, model = GEN.load_model()
    adapter_digest = GEN.load_adapter(torch, model, a.adapter) if a.adapter else None
    env = GEN.env_info(torch, proc, model)
    prompts = {c: D.PROMPTS[c] for c in D.CATS}
    cdig, core = GEN.config_digest(env, prompts)
    proto = {'model_revision': GEN.MODEL_REVISION, 'adapter_digest': adapter_digest, 'adapter_dir': a.adapter, 'config_digest': cdig, 'prompts': {c: D.prompt_sha(c) for c in D.CATS},
             'key': a.key, 'n_requests_total': len(items), 'ids_sha': hashlib.sha256(json.dumps([i['id'] for i in items]).encode()).hexdigest(),
             'code': {f: sha_file(f) for f in CODE}, 'manifest_sha256': sha_file(f'{D.DATA}/manifest.json'), 'nworkers_note': 'worker assignment is by index modulo and may change on resume'}
    pp = os.path.join(a.out_dir, 'protocol.json')
    try:
        fd = os.open(pp, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, 'w') as f:
            json.dump(proto, f, indent=1)
    except FileExistsError:
        old = json.load(open(pp))
        for k in proto:
            if k != 'nworkers_note' and old.get(k) != proto[k]:
                sys.exit(f'protocol mismatch in {k}: existing run was made with different input/adapter/code')
    eos = env['eos_token_id']
    eos_ids = set(eos if isinstance(eos, list) else [eos])
    pdig = {c: D.prompt_sha(c) for c in D.CATS}
    by_id = {i['id']: i for i in items}
    out = os.path.join(a.out_dir, f'gen_worker{a.worker}.jsonl')
    n_torn = repair_tail(out)

    def read_all():
        recs = {}
        for f in sorted(glob.glob(os.path.join(a.out_dir, 'gen_worker*.jsonl'))):
            for ln in open(f):
                if not ln.strip():
                    continue
                r = json.loads(ln)
                it = by_id.get(r['id'])
                if it is None:
                    raise RuntimeError(f"unexpected record {r['id']} in {f}")
                rid = GEN.request_id(GEN.MODEL_REVISION, adapter_digest, a.key, r['id'], pdig[it['category']])
                if r['request_id'] != rid or r['config_digest'] != cdig or r['adapter_digest'] != adapter_digest:
                    raise RuntimeError(f"provenance mismatch for {r['id']} in {f}")
                if r['input_pixel_sha256'] != it['pixel_sha256_padded'] or r['image_file_sha256'] != it['file_sha256']:
                    raise RuntimeError(f"input changed for {r['id']} in {f}")
                if r['id'] in recs:
                    raise RuntimeError(f"duplicate record {r['id']}")
                recs[r['id']] = r
        return recs

    done = read_all()
    mine = [i for k, i in enumerate(items) if k % a.nworkers == a.worker]
    n_new, t0 = 0, time.time()
    log = open(out + '.log', 'a')
    log.write(json.dumps({'event': 'start', 'n_done_all': len(done), 'n_mine': len(mine), 'torn_bytes_removed': n_torn, 'ts': time.time()}) + '\n')
    log.flush()
    for it in mine:
        if it['id'] in done:
            continue
        if a.max_requests is not None and n_new >= a.max_requests:
            break
        rec = GEN.run_request(torch, proc, model, eos_ids, it, it['category'], prompts[it['category']])
        rec.update({'request_id': GEN.request_id(GEN.MODEL_REVISION, adapter_digest, a.key, it['id'], pdig[it['category']]), 'split': a.key, 'adapter_digest': adapter_digest,
                    'config_digest': cdig, 'worker': a.worker, 'ts': time.time(), 'gpu_uuid': env.get('gpu_uuid'), 'category': it['category']})
        with open(out, 'a') as f:
            f.write(json.dumps(rec) + '\n')
            f.flush()
            os.fsync(f.fileno())
        n_new += 1
        done[it['id']] = rec
        log.write(json.dumps({'event': 'done', 'id': it['id'], 'n_out': rec['n_output_tokens'], 'finish': rec['finish_reason'], 'runtime_s': round(rec['runtime_s_total'], 2),
                              'peak_gb': round(rec['peak_mem_alloc_gb_max'], 2), 'elapsed': round(time.time() - t0, 1)}) + '\n')
        log.flush()
    print(f'worker {a.worker}: {n_new} new requests', flush=True)


if __name__ == '__main__':
    main()
