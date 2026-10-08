"""iter_101 MedGemma 1.5 교정 생성기: 고정 요청 JSON을 text-only(영상 없음) 또는 image+text로 greedy 생성한다. 학습·LoRA 없음.

모델은 공식 AutoProcessor/AutoModelForImageTextToText(MedGemma 1.5 revision 고정, bf16, sdpa)를 그대로 쓴다. peft/adapter를 적용하지 않는다.
요청 한 건 = {id, ImageID, cond, image(경로 또는 None), file_sha256(또는 None), prompt}. image가 None이면 chat template에 text content만 넣는다
(빈 그림·검은 영상·가짜 image token 없음). image가 있으면 report90_gen과 같은 값 보존 RGB·정사각 padding(G.load_image)을 쓴다.

재사용 결함 보완(iter_090/100 계열): 실행 소스 sha256을 protocol에 포함해 소스 변경 시 resume 거부, completion 파일 변조 거부,
허용 GPU 집합 검사(worker와 launcher), launcher 단일 소유권, 시작 직전 nvidia-smi + 살아 있는 worker 예약(peak-현재점유+2GiB).
결과는 results/iter_101 아래에만 쓴다. 완료 요청은 worker별 JSONL에 fsync로 추가한다.
"""
import argparse
import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from report86_common import ROOT, SEED, sha, sha_obj, save, read_jsonl_complete, record_digest, base_path
from report101_cure import R101, isolated_env, smi_free, next_attempt, MARGIN_MIB

CAPS = [1024, 2048, 4096]
EXEC_SOURCES = ['report101_gen.py', 'report101_cure.py', 'report86_common.py', 'rsna_diag/generate.py', 'rsna_diag/geometry.py', 'pg43_run.py']
MODEL_REVISION = '91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b'


def protocol(requests, workers):
    reqs = json.loads(Path(requests).read_text())
    assert len({r['id'] for r in reqs}) == len(reqs)
    return {'requests_path': str(Path(requests).resolve()), 'requests_sha256': sha(requests), 'n_requests': len(reqs), 'workers': workers,
            'model_revision': MODEL_REVISION, 'base': base_path('M15'), 'adapter': None, 'seed': SEED, 'caps': CAPS, 'dtype': 'bfloat16',
            'attn': 'sdpa', 'do_pan_and_scan': False, 'decode': 'greedy do_sample=False',
            'source_sha256': {f: sha(ROOT / f) for f in EXEC_SOURCES}}


def load_own(path, expected, proto_digest, shard, workers, all_rows):
    mine = read_jsonl_complete(path)
    ids = [r['id'] for r in mine]
    assert len(ids) == len(set(ids)), 'duplicate id in own output'
    for r in mine:
        q = expected.get(r['id'])
        assert q is not None, f"record outside request set {r['id']}"
        assert all_rows.index(q) % workers == shard, 'record in wrong shard'
        assert r['protocol_digest'] == proto_digest and r['request_digest'] == sha_obj(q), 'protocol/request digest mismatch'
        assert r['record_digest'] == record_digest(r), 'record digest mismatch (tampered)'
        assert r['image_sha256'] == q['file_sha256'], 'image hash mismatch'
        assert (q['image'] is None) == (r['modality'] == 'text')
    return mine


def verify(out, requests, workers):
    """전 worker 출력의 전수 검증(요청 집합 일치·중복 없음·digest). completion이 있으면 파일 hash도 대조한다."""
    out = Path(out)
    proto = protocol(requests, workers)
    pd = sha_obj(proto)
    saved_proto = json.loads((out / 'protocol.json').read_text())
    assert saved_proto == json.loads(json.dumps(proto)), 'protocol on disk differs from current requests/sources'
    all_rows = json.loads(Path(requests).read_text())
    expected = {r['id']: r for r in all_rows}
    got = []
    for s in range(workers):
        f = out / f'worker_{s}.jsonl'
        if f.exists() and f.read_bytes() and not f.read_bytes().endswith(b'\n'):
            raise ValueError('torn tail requires owned repair')
        got += load_own(f, expected, pd, s, workers, all_rows)
    assert len({r['id'] for r in got}) == len(got)
    cp = out / 'completion.json'
    if cp.exists():
        c = json.loads(cp.read_text())
        assert c['n'] == len(got) == len(expected) and c['protocol_digest'] == pd
        assert c['files'] == {f'worker_{s}.jsonl': sha(out / f'worker_{s}.jsonl') for s in range(workers)}, 'completion hash mismatch (tampered)'
    return got, expected


def worker(a):
    out = Path(a.out).resolve()
    out.relative_to(R101)
    allowed = os.environ['CUDA_VISIBLE_DEVICES'].split(',')
    assert a.gpu in allowed, f'gpu {a.gpu} not in inherited CUDA_VISIBLE_DEVICES {allowed}'
    os.environ['CUDA_VISIBLE_DEVICES'] = a.gpu
    proto = protocol(a.requests, a.workers)
    pd = sha_obj(proto)
    assert json.loads((out / 'protocol.json').read_text()) == json.loads(json.dumps(proto)), 'protocol/source changed (before model load)'
    assert json.loads((out / 'mapping.json').read_text())['workers'] == a.workers
    all_rows = json.loads(Path(a.requests).read_text())
    expected = {r['id']: r for r in all_rows}
    rows = all_rows[a.shard::a.workers]
    for r in rows:
        if r['image'] is not None:
            assert sha(r['image']) == r['file_sha256'], f"input image changed {r['id']}"
    lock = (out / f'worker_{a.shard}.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    from pg43_run import repair_tail
    repair_tail(str(out / f'worker_{a.shard}.jsonl'))
    path = out / f'worker_{a.shard}.jsonl'
    old = load_own(path, expected, pd, a.shard, a.workers, all_rows)
    done = {r['id'] for r in old}
    todo = [r for r in rows if r['id'] not in done]
    if a.limit:
        todo = todo[:a.limit]
    if not todo:
        return 0
    import torch
    import transformers
    from rsna_diag import generate as G
    torch.set_num_threads(4)
    torch.manual_seed(SEED)
    t0 = time.monotonic()
    proc = transformers.AutoProcessor.from_pretrained(base_path('M15'), local_files_only=True)
    proc.image_processor.do_pan_and_scan = False
    model = transformers.AutoModelForImageTextToText.from_pretrained(base_path('M15'), local_files_only=True, dtype=torch.bfloat16,
                                                                     device_map={'': 0}, attn_implementation='sdpa').eval()
    assert not hasattr(model, 'peft_config') and not any('lora_' in n for n, _ in model.named_parameters()), 'adapter present'
    loading_s = time.monotonic() - t0
    eos = model.generation_config.eos_token_id
    eos = [eos] if isinstance(eos, int) else eos
    ev = (out / f'worker_{a.shard}.events.jsonl').open('a', buffering=1)
    ev.write(json.dumps({'event': 'start', 'time': time.time(), 'pid': os.getpid(), 'gpu': a.gpu, 'n_todo': len(todo), 'loading_s': loading_s,
                         'torch': torch.__version__, 'transformers': transformers.__version__}) + '\n')
    saved = 0
    with path.open('a') as f:
        for req in todo:
            t_req = time.monotonic()
            if req['image'] is None:
                inp = G.build_inputs_text(proc, req['prompt'])
                official = proc.apply_chat_template([{'role': 'user', 'content': [{'type': 'text', 'text': req['prompt']}]}],
                                                    add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors='pt', padding=True)
                assert 'pixel_values' not in inp, 'text-only input produced pixel_values'
                px = None
            else:
                image, _, px = G.load_image(req['image'])
                inp = G.build_inputs(proc, image, req['prompt'])
                official = proc.apply_chat_template([{'role': 'user', 'content': [{'type': 'image', 'image': image}, {'type': 'text', 'text': req['prompt']}]}],
                                                    add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors='pt', padding=True)
            assert set(inp) == set(official) and all(torch.equal(inp[k], official[k]) for k in inp)
            attempts = []
            for cap in CAPS:
                res = G.generate(torch, proc, model, inp, cap, eos)
                attempts.append(res)
                if res['ended_eos']:
                    break
            rec = {'id': req['id'], 'request_digest': sha_obj(req), 'protocol_digest': pd, 'modality': 'text' if req['image'] is None else 'image',
                   'image_sha256': req['file_sha256'], 'pixel_sha256': px, 'input_ids': inp['input_ids'][0].tolist(),
                   'text': proc.decode(res['suffix_ids'], skip_special_tokens=True), 'attempts': attempts, 'gpu': a.gpu, 'shard': a.shard,
                   'wall_s': time.monotonic() - t_req}
            rec['record_digest'] = record_digest(rec)
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
            saved += 1
            print(json.dumps({'shard': a.shard, 'saved': saved, 'of': len(todo), 'tokens': res['n_new'], 'seconds': round(res['runtime_s'], 1),
                              'peak_gib': round(res['peak_mem_reserved_gb'], 2)}), flush=True)
    ev.write(json.dumps({'event': 'end', 'time': time.time(), 'saved': saved}) + '\n')
    return 0


def launch(a):
    out = Path(a.out).resolve()
    out.relative_to(R101)
    out.mkdir(parents=True, exist_ok=True)
    allowed = os.environ['CUDA_VISIBLE_DEVICES'].split(',')
    with (out / 'launcher.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        proto = protocol(a.requests, a.workers)
        for path, value in [(out / 'protocol.json', proto), (out / 'mapping.json', {'workers': a.workers})]:
            if path.exists():
                assert json.loads(path.read_text()) == json.loads(json.dumps(value)), ('protocol/mapping changed', path.name)
            else:
                save(path, value)
        from pg43_run import repair_tail
        for s in range(a.workers):
            with (out / f'worker_{s}.lock').open('a') as wl:
                fcntl.flock(wl, fcntl.LOCK_EX | fcntl.LOCK_NB)
                repair_tail(str(out / f'worker_{s}.jsonl'))
        existing, expected = verify(out, a.requests, a.workers)
        pd = sha_obj(proto)
        if len(existing) == len(expected):
            if not (out / 'completion.json').exists():
                save(out / 'completion.json', {'n': len(existing), 'protocol_digest': pd,
                                               'files': {f'worker_{s}.jsonl': sha(out / f'worker_{s}.jsonl') for s in range(a.workers)}})
            return 0
        procs, logs = [], []
        attempt = next_attempt(out)
        start = time.monotonic()
        env = isolated_env()
        admission = []

        def stop(*args):
            raise KeyboardInterrupt('supervisor stopped; terminating owned children')
        signal.signal(signal.SIGTERM, stop)
        try:
            for s in range(a.workers):
                st = smi_free()
                apps = subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid,used_memory', '--format=csv,noheader,nounits'], text=True)
                actual = {int(x.split(',')[0]): int(x.split(',')[1]) for x in apps.splitlines() if x.strip()}
                choices = {g: st[g][0] - sum(max(0, a.peak_mib - actual.get(p.pid, 0)) + MARGIN_MIB for _, p, gg in procs if gg == g and p.poll() is None)
                           for g in allowed}
                gpu = max(choices, key=choices.get)
                admission.append({'shard': s, 'choices_free_mib': choices, 'chosen': gpu, 'need_mib': a.peak_mib + MARGIN_MIB, 'smi': st})
                assert choices[gpu] >= a.peak_mib + MARGIN_MIB, ('memory admission refused', choices)
                cmd = [sys.executable, str(ROOT / 'report101_gen.py'), 'worker', '--requests', a.requests, '--out', str(out), '--gpu', gpu,
                       '--shard', str(s), '--workers', str(a.workers)] + (['--limit', str(a.limit)] if a.limit else [])
                so = (out / f'launch{attempt}_worker{s}.stdout.log').open('x')
                se = (out / f'launch{attempt}_worker{s}.stderr.log').open('x')
                logs.extend([so, se])
                procs.append((s, subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=so, stderr=se), gpu))
                time.sleep(a.stagger)
            with (out / f'launch{attempt}_resource.jsonl').open('x') as rf:
                while any(p.poll() is None for _, p, _ in procs):
                    rf.write(json.dumps({'t': time.time(), 'smi': smi_free()}) + '\n')
                    rf.flush()
                    time.sleep(10)
            codes = {s: p.wait() for s, p, _ in procs}
        finally:
            for _, p, _ in procs:
                if p.poll() is None:
                    p.terminate()
            for _, p, _ in procs:
                p.wait()
            for f in logs:
                f.close()
        save(out / f'launch_{attempt:03}.json', dict(codes=codes, wall_s=time.monotonic() - start, mapping={s: g for s, _, g in procs},
                                                      protocol_digest=pd, allowed=allowed, admission=admission, peak_mib=a.peak_mib,
                                                      script_sha256=sha(__file__)))
        assert all(c == 0 for c in codes.values()), codes
        recs, expected = verify(out, a.requests, a.workers)
        if len(recs) == len(expected):
            save(out / 'completion.json', {'n': len(recs), 'protocol_digest': pd,
                                           'files': {f'worker_{s}.jsonl': sha(out / f'worker_{s}.jsonl') for s in range(a.workers)}})
        return 0 if len(recs) == len(expected) or a.limit else 2


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['worker', 'launch'])
    p.add_argument('--requests', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--workers', type=int, default=2)
    p.add_argument('--shard', type=int, default=0)
    p.add_argument('--gpu')
    p.add_argument('--limit', type=int, default=0)
    p.add_argument('--peak-mib', type=int, default=12000)
    p.add_argument('--stagger', type=float, default=15.0)
    a = p.parse_args()
    raise SystemExit(worker(a) if a.command == 'worker' else launch(a))
