"""iter_081 고정 요청 실행. 기존 rf78의 실제 생성 함수를 재사용한다.

worker별 원자적 request JSON을 저장해 부분 JSONL의 동시 읽기를 제거한다.
claim은 flock이며 삭제하지 않는다. pending 파일은 완료로 세지 않고 보존한다.
"""
import argparse
import os
import time
import sys
import importlib.metadata
from pathlib import Path
import a81_common as C
import rf78_gen as G
import sp75_vlm as V
from rsna_diag import generate, queue_lock


def load_protocol(path):
    p = C.read(path)
    C.check_hashes(p['files'])
    if p['config'] != C.CONFIG:
        raise ValueError('config mismatch')
    if p['python'] != sys.executable or any(importlib.metadata.version(k) != v for k,v in p['environment'].items()):
        raise ValueError('runtime environment mismatch')
    reqs = C.read(p['requests_path'])
    selected = [r for r in reqs if r['cond'] in p['conds'] and (p['ids'] is None or r['id'] in p['ids'])]
    keys = [C.request_key(r) for r in selected]
    if keys != p['request_keys'] or len(set(keys)) != len(keys):
        raise ValueError('request digest/set mismatch')
    for r in selected:
        C.check_request(r)
    return p, selected


def records(out, p, reqs):
    by = {C.request_key(r): r for r in reqs}
    done = {}
    for f in sorted(Path(out).glob('worker*/records/*.json')):
        x = C.read(f); key = x.get('request_key')
        if key not in by or key in done:
            raise ValueError('unexpected/duplicate request record')
        r = by[key]
        if x.get('request') != r or x.get('protocol_digest') != C.digest(p):
            raise ValueError('request/protocol mismatch')
        if x.get('adapter_digest') != C.ADAPTER_DIGEST or x.get('config') != C.CONFIG:
            raise ValueError('adapter/config mismatch')
        if x['parsed'] != (V.parse(x['text']) if x['ended_eos'] else None):
            raise ValueError('parser mismatch')
        if x['n_images'] != len(r['images']) or x['n_new'] != len(x['suffix_ids']):
            raise ValueError('image/token count mismatch')
        if x['runtime_s'] < 0 or not x.get('env_digest'):
            raise ValueError('timing/environment missing')
        done[key] = x
    return done


def verify(protocol, out, complete=True):
    p, reqs = load_protocol(protocol)
    done = records(out, p, reqs)
    if complete and set(done) != set(p['request_keys']):
        raise ValueError(f'missing outputs {len(done)}/{len(reqs)}')
    return done


def inputs(proc, r):
    if r['cond'] == 'Q':
        return V.build_gen_inputs(proc, V.load_images(r['images']), V.PROMPT_R)
    return G.make_inputs(proc, r['cond'], r)[0]


def tech_check(torch, proc, reqs):
    checks = []
    qs = {r['id']: r for r in reqs if r['cond'] == 'Q'}
    for r in reqs:
        im = V.load_images(r['images'])
        official = proc.apply_chat_template([{'role': 'user', 'content':
                    [{'type': 'image', 'image': x} for x in im] + [{'type': 'text', 'text': r['prompt']}]}],
                    tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors='pt')
        actual = inputs(proc, r)
        assert set(official) == set(actual)
        assert all(torch.equal(official[k], actual[k]) for k in actual)
        n = actual['pixel_values'].shape[0] if 'pixel_values' in actual else 0
        assert n == (0 if r['cond'] == 'T' else 3)
        if r['cond'] == 'A' and r['id'] in qs:
            assert torch.equal(actual['pixel_values'], inputs(proc, qs[r['id']])['pixel_values'])
        checks.append({'id': r['id'], 'cond': r['cond'], 'keys': list(actual), 'images': n, 'equal': True})
    return checks


def worker(a):
    allowed = os.environ.get('CUDA_VISIBLE_DEVICES', '').split(',')
    if a.gpu not in allowed:
        raise ValueError('GPU outside inherited set')
    os.environ['CUDA_VISIBLE_DEVICES'] = a.gpu
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'
    p, reqs = load_protocol(a.protocol)
    root = Path(a.out); root.mkdir(parents=True, exist_ok=True)
    (root / 'claims').mkdir(exist_ok=True)
    info = queue_lock.my_info(worker=a.worker)
    lock, _, _ = queue_lock.try_lock(str(root / f'worker{a.worker}.lock'), info)
    if lock is None:
        raise ValueError('worker already owned')
    try:
        start = time.monotonic()
        torch, proc, model = generate.load_model()
        dg = generate.load_adapter(torch, model, C.ADAPTER)
        assert dg == C.ADAPTER_DIGEST
        env = generate.env_info(torch, proc, model)
        assert env['model_revision'] == C.CONFIG['model_revision']
        ep = root / f'worker{a.worker}' / f'env_{os.getpid()}.json'
        C.save(ep, {'env': env, 'logical_gpu': 0, 'physical_gpu': a.gpu, 'protocol_digest': C.digest(p)})
        ed = C.sha(ep)
        if a.tech:
            C.save(root / f'worker{a.worker}/tech_{os.getpid()}.json', {'passed': True, 'checks': tech_check(torch, proc, reqs)})
        eos = env['eos_token_id']; eos = set(eos if isinstance(eos, list) else [eos])
        n = 0
        for r in reqs:
            if a.limit is not None and n >= a.limit:
                break
            key = C.request_key(r)
            cl, _, _ = queue_lock.try_lock(str(root / 'claims' / (key + '.lock')), info)
            if cl is None:
                continue
            try:
                if key in records(root, p, reqs):
                    continue
                C.check_request(r)
                if r['cond'] == 'Q':
                    # 기존 Q 생성 함수와 동일 입력 경로.
                    rr = {'query_images': r['images']}
                else:
                    rr = r
                x = G.run_one(torch, proc, model, rr, r['cond'], eos)
                x.update(request_key=key, request=r, protocol_digest=C.digest(p), config=C.CONFIG,
                         adapter_digest=dg, env_digest=ed, env_path=str(ep), worker=a.worker,
                         physical_gpu=a.gpu, logical_gpu=0, saved_at=time.time())
                C.save(root / f'worker{a.worker}/records/{key}.json', x)
                n += 1
                print(f'{n} {r["id"]} {r["cond"]} saved', flush=True)
            finally:
                cl.release()
        C.save(root / f'worker{a.worker}/attempt_{os.getpid()}.json',
               {'new': n, 'wall_including_load_s': time.monotonic() - start, 'protocol_digest': C.digest(p), 'normal_exit': True})
    finally:
        lock.release()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--protocol', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--worker', type=int, required=True); ap.add_argument('--gpu', required=True)
    ap.add_argument('--limit', type=int); ap.add_argument('--tech', action='store_true')
    worker(ap.parse_args())
