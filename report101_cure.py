"""iter_101 CURE 원출력 생성기 (환자당 3요청: grounded report + 좌/우 costophrenic angle Describe).

report95_gen/report95_launch의 모델 로딩·입력·생성 경로(NF4·bf16·공식 processor/chat template·CLAHE·greedy·cap 1024→2048→4096)를 유지한다.
iter_095 재사용 결함 보완:
 - 실행 소스 sha256을 scientific protocol에 포함: 소스가 바뀌면 resume 거부(모델 로딩 전).
 - 완료(completion) 파일 변조 거부: 재실행·launcher 시작 시 completion의 파일 hash를 다시 검증하고, 불일치면 실패.
 - launcher: 허용 GPU 집합 검사, launcher 단일 소유권(flock), 시작 직전 nvidia-smi 재확인 + 살아 있는 worker마다 (peak-현재점유+2GiB) 예약.
출력은 results/iter_101 아래에만 쓴다. stdout/stderr 로그 이름은 기존 파일 기준으로 attempt 번호를 정한다.
"""
import argparse
import fcntl
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

from report86_common import (ROOT, SEED, CAPS, sha, sha_obj, save, read_jsonl_complete, record_digest, adapter_path_C, base_path, CURE_PY, R85)

R101 = ROOT / 'results/iter_101'
DATA = R101 / 'data'
SYSTEM = 'C101'
FORMATS = [('G', 'Generate a grounded report.'), ('CL', 'Describe the left costophrenic angle.'),
           ('CR', 'Describe the right costophrenic angle.')]
EXEC_SOURCES = ['report101_cure.py', 'report86_common.py', 'rsna_diag/generate.py', 'rsna_diag/lora.py', 'rsna_diag/geometry.py', 'pg43_run.py']
MARGIN_MIB = 2048


def stage_rows(stage):
    return json.loads((DATA / f'inputs_{stage}.json').read_text()), {r['ImageID']: r for r in json.loads((DATA / f'raw_manifest_{stage}.json').read_text())}


def requests(stage):
    rows, _ = stage_rows(stage)
    out = [{'id': f"{r['ImageID']}|{SYSTEM}|{k}", 'ImageID': r['ImageID'], 'fmt': k, 'prompt': p} for r in rows for k, p in FORMATS]
    assert len({q['id'] for q in out}) == len(out)
    return out


def scientific_protocol(stage, nshards):
    reqs = requests(stage)
    return {'system': 'C', 'stage': stage, 'nshards': nshards, 'base': base_path('C'),
            'adapter_digest': sha(adapter_path_C() / 'adapter_model.safetensors'), 'seed': SEED, 'caps': CAPS, 'precision': 'nf4_bf16_clahe',
            'requests_sha256': sha_obj(reqs), 'n_requests': len(reqs), 'input_sha256': sha(DATA / f'inputs_{stage}.json'),
            'raw_sha256': sha(DATA / f'raw_manifest_{stage}.json'), 'selection_lock_sha256': sha(DATA / 'selection_lock.json'),
            'source_sha256': {f: sha(ROOT / f) for f in EXEC_SOURCES}}


def isolated_env():
    env = dict(os.environ)
    cache = R101 / 'runtime_cache'
    for key, name in {'HF_HOME': 'hf', 'HF_HUB_CACHE': 'hf/hub', 'HF_XET_CACHE': 'hf/xet', 'XDG_CACHE_HOME': 'xdg', 'TORCH_HOME': 'torch',
                      'TORCHINDUCTOR_CACHE_DIR': 'inductor', 'TRITON_CACHE_DIR': 'triton', 'CUDA_CACHE_PATH': 'cuda',
                      'MPLCONFIGDIR': 'matplotlib', 'TMPDIR': 'tmp'}.items():
        p = cache / name
        p.mkdir(parents=True, exist_ok=True)
        env[key] = str(p)
    env.update({'HF_HUB_OFFLINE': '1', 'TOKENIZERS_PARALLELISM': 'false', 'NO_ALBUMENTATIONS_UPDATE': '1'})
    return env


def shard_dir(out, s):
    return Path(out) / f'shard{s}'


def load_own(d, reqmap, sci_digest):
    mine = read_jsonl_complete(Path(d) / 'outputs.jsonl')
    ids = [r['id'] for r in mine]
    assert len(ids) == len(set(ids)), 'duplicate in own output'
    for r in mine:
        q = reqmap.get(r['id'])
        assert q is not None, f"record outside request set {r['id']}"
        assert r['protocol_digest'] == sci_digest, 'record protocol digest mismatch'
        assert r['record_digest'] == record_digest(r), 'record digest mismatch (tampered)'
        assert r['prompt'] == q['prompt'] and r['ImageID'] == q['ImageID'], 'record prompt/image mismatch'
    return mine


def verify_completion(d, reqmap, sci_digest):
    """completion이 있으면 파일 hash·요청 집합을 전수 재검증한다."""
    cp = Path(d) / 'completion.json'
    c = json.loads(cp.read_text())
    for name, h in c['files'].items():
        assert sha(Path(d) / name) == h, f'completion file hash differs: {d}/{name}'
    recs = load_own(d, reqmap, sci_digest)
    assert c['n_own_records'] == len(recs)
    return c, recs


def worker(a):
    out = Path(a.out).resolve()
    out.relative_to(R101)
    allowed = os.environ['CUDA_VISIBLE_DEVICES'].split(',')
    assert a.gpu in allowed, f'gpu {a.gpu} not in inherited CUDA_VISIBLE_DEVICES {allowed}'
    os.environ['CUDA_VISIBLE_DEVICES'] = a.gpu
    reqs = requests(a.stage)
    reqmap = {r['id']: r for r in reqs}
    rows, raw = stage_rows(a.stage)
    for row in rows:
        assert sha(row['image']) == row['file_sha256'], f"input image changed {row['ImageID']}"
        assert sha(raw[row['ImageID']]['raw_path']) == raw[row['ImageID']]['sha256'], 'raw image changed'
    sci = scientific_protocol(a.stage, a.nshards)
    sci_digest = sha_obj(sci)
    d = shard_dir(out, a.shard)
    d.mkdir(parents=True, exist_ok=True)
    lock = (d / 'worker.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    from pg43_run import repair_tail
    repair_tail(str(d / 'outputs.jsonl'))
    meta = {'scientific': sci, 'scientific_digest': sci_digest, 'stage': a.stage, 'shard': a.shard, 'nshards': a.nshards}
    mypath = d / 'scientific_protocol.json'
    if mypath.exists():
        assert json.loads(mypath.read_text()) == json.loads(json.dumps(meta)), 'resume: protocol/source/shard mismatch (before model load)'
    else:
        save(mypath, meta)
    my_rows = [r for i, r in enumerate(rows) if i % a.nshards == a.shard]
    my_imgs = {r['ImageID'] for r in my_rows}
    target = [q for q in reqs if q['ImageID'] in my_imgs]
    if (d / 'completion.json').exists():
        verify_completion(d, reqmap, sci_digest)  # 변조 시 AssertionError
        return 0
    mine = load_own(d, reqmap, sci_digest)
    assert all(r['ImageID'] in my_imgs for r in mine), 'own record belongs to another shard'
    done = {r['id'] for r in mine}
    todo = [q for q in target if q['id'] not in done]
    if a.limit:
        todo = todo[:a.limit]
    execution = {'event': 'start', 'time': time.time(), 'pid': os.getpid(), 'gpu_physical': a.gpu, 'python': sys.executable,
                 'n_todo': len(todo), 'n_target': len(target), 'cuda_visible_devices_set': os.environ['CUDA_VISIBLE_DEVICES']}
    events = (d / 'executions.jsonl').open('a', buffering=1)
    if todo:
        saved = generate(a, d, events, execution, todo, my_rows, rows, raw, sci_digest)
    finish(d, a, target, reqmap, sci_digest)
    return 0


def generate(a, d, events, execution, todo, my_rows, rows, raw, sci_digest):
    import numpy as np
    import torch
    from transformers import AutoProcessor, AutoModelForImageTextToText, BitsAndBytesConfig
    from peft import PeftModel
    from rsna_diag import generate as G
    torch.set_num_threads(4)
    torch.manual_seed(SEED)
    base = base_path('C')
    processor = AutoProcessor.from_pretrained(base, local_files_only=True)
    processor.tokenizer.padding_side = 'left'
    kw = dict(torch_dtype=torch.bfloat16, device_map={'': 0}, local_files_only=True, attn_implementation='sdpa',
              quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_use_double_quant=True, bnb_4bit_quant_type='nf4',
                                                     bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_quant_storage=torch.bfloat16))
    t0 = time.monotonic()
    model = AutoModelForImageTextToText.from_pretrained(base, **kw)
    ap = adapter_path_C()
    model = PeftModel.from_pretrained(model, str(ap), local_files_only=True)
    assert set(model.peft_config['default'].modules_to_save) == {'lm_head', 'embed_tokens'}
    model.eval()
    assert not any(m.training for m in model.modules())
    loading_s = time.monotonic() - t0
    sys.path.insert(0, str(R85 / 'official/minimal'))
    from vlm_research_kit.data.transforms_factory import create_image_transforms
    transform = create_image_transforms(use_model_specific_transforms=True, model_name='pil_with_augmentations', bbox_format='cxcywh',
                                        image_size=[448, 448], is_train=False,
                                        augmenter_override_params={'apply_clahe': True, 'clahe_clip_limit': [3., 3.]})
    eos = model.generation_config.eos_token_id
    eos = [eos] if isinstance(eos, int) else eos
    events.write(json.dumps({**execution, 'torch': torch.__version__, 'loading_s': loading_s}) + '\n')
    by_img = {}
    for q in todo:
        by_img.setdefault(q['ImageID'], []).append(q)
    saved = 0
    t_start = time.monotonic()
    with (d / 'outputs.jsonl').open('a', buffering=1) as f:
        for img in [r['ImageID'] for r in my_rows if r['ImageID'] in by_img]:
            rr = raw[img]
            im = transform(rr['raw_path'])['pixel_values']
            row = next(r for r in rows if r['ImageID'] == img)
            for q in by_img[img]:
                events.write(json.dumps({'event': 'request_start', 'id': q['id'], 'time': time.time()}) + '\n')
                inp = G.build_inputs(processor, im, q['prompt'])
                official = processor.apply_chat_template([{'role': 'user', 'content': [{'type': 'image', 'image': im}, {'type': 'text', 'text': q['prompt']}]}],
                                                         add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors='pt', padding=True)
                assert set(inp) == set(official) and all(torch.equal(inp[k], official[k]) for k in inp)
                attempts = []
                for cap in CAPS:
                    result = G.generate(torch, processor, model, inp, cap, eos)
                    attempts.append(result)
                    if result['ended_eos']:
                        break
                rec = {'id': q['id'], 'ImageID': img, 'fmt': q['fmt'], 'prompt': q['prompt'], 'protocol_digest': sci_digest,
                       'image_sha256': row['file_sha256'], 'text': processor.decode(result['suffix_ids'], skip_special_tokens=True),
                       'attempts': attempts, 'input_ids': inp['input_ids'][0].tolist(),
                       'pixel_sha256': hashlib.sha256(np.asarray(im).tobytes()).hexdigest(),
                       'exec': {'gpu': a.gpu, 'shard': a.shard, 'pid': os.getpid(), 'torch': torch.__version__}}
                rec['record_digest'] = record_digest(rec)
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
                saved += 1
                events.write(json.dumps({'event': 'request_saved', 'id': q['id'], 'time': time.time(), 'seconds': result['runtime_s'],
                                         'n_new': result['n_new'], 'attempts': len(attempts)}) + '\n')
                print(json.dumps({'saved': saved, 'of': len(todo), 'shard': a.shard, 'tokens': result['n_new'],
                                  'seconds': round(result['runtime_s'], 2)}), flush=True)
    allrecs = read_jsonl_complete(d / 'outputs.jsonl')
    events.write(json.dumps({'event': 'end', 'time': time.time(), 'saved': saved, 'wall_s': time.monotonic() - t_start,
                             'peak_reserved_gib_max': max(max(x['peak_mem_reserved_gb'] for x in r['attempts']) for r in allrecs)}) + '\n')
    return saved


def finish(d, a, target, reqmap, sci_digest):
    recs = load_own(d, reqmap, sci_digest)
    got = {r['id'] for r in recs}
    want = {q['id'] for q in target}
    cp = d / 'completion.json'
    if want <= got and not cp.exists():
        events = [json.loads(l) for l in (d / 'executions.jsonl').read_text().splitlines() if l]
        save(cp, {'stage': a.stage, 'shard': a.shard, 'nshards': a.nshards, 'n_own_records': len(recs), 'n_expected_in_shard': len(want),
                  'files': {'scientific_protocol.json': sha(d / 'scientific_protocol.json'), 'outputs.jsonl': sha(d / 'outputs.jsonl')},
                  'final_not_eos': sum(not r['attempts'][-1]['ended_eos'] for r in recs),
                  'executions': len([e for e in events if e['event'] == 'start']),
                  'generation_s_total': sum(sum(x['runtime_s'] for x in r['attempts']) for r in recs),
                  'cost_scope': 'generation seconds of records in this shard dir; loading/interrupted cost in executions.jsonl'})


def smi_free():
    raw = subprocess.check_output(['nvidia-smi', '--query-gpu=index,memory.free,memory.used,memory.total', '--format=csv,noheader,nounits'], text=True)
    return {x.split(',')[0].strip(): [int(v) for v in x.split(',')[1:]] for x in raw.splitlines()}


def next_attempt(out):
    nums = [int(m.group(1)) for p in Path(out).glob('launch*_worker*.stdout.log') for m in [re.match(r'launch(\d+)_worker', p.name)] if m]
    return max(nums) + 1 if nums else 0


def launch(a):
    out = Path(a.out).resolve()
    out.relative_to(R101)
    out.mkdir(parents=True, exist_ok=True)
    allowed = os.environ['CUDA_VISIBLE_DEVICES'].split(',')
    reqs = requests(a.stage)
    reqmap = {r['id']: r for r in reqs}
    with (out / 'launcher.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        sci = scientific_protocol(a.stage, a.workers)
        sd = sha_obj(sci)
        mp = out / 'mapping.json'
        want_map = {'stage': a.stage, 'workers': a.workers, 'scientific_digest': sd}
        if mp.exists():
            assert json.loads(mp.read_text()) == want_map, 'launcher mapping/protocol changed (source or inputs differ)'
        else:
            save(mp, want_map)
        # 완료 검증: 모든 shard completion이 있으면 hash를 재검증하고 종료
        if all((shard_dir(out, s) / 'completion.json').exists() for s in range(a.workers)):
            total = 0
            for s in range(a.workers):
                c, recs = verify_completion(shard_dir(out, s), reqmap, sd)
                total += len(recs)
            assert total == len(reqs)
            return 0
        procs, logs = [], []
        attempt = next_attempt(out)
        start = time.monotonic()
        env = isolated_env()

        def stop(*args):
            raise KeyboardInterrupt('supervisor stopped; terminating owned children')
        signal.signal(signal.SIGTERM, stop)
        admission = []
        try:
            for s in range(a.workers):
                if (shard_dir(out, s) / 'completion.json').exists():
                    continue
                st = smi_free()
                apps = subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid,used_memory', '--format=csv,noheader,nounits'], text=True)
                actual = {int(x.split(',')[0]): int(x.split(',')[1]) for x in apps.splitlines() if x.strip()}
                choices = {g: st[g][0] - sum(max(0, a.peak_mib - actual.get(p.pid, 0)) + MARGIN_MIB for _, p, gg in procs if gg == g and p.poll() is None)
                           for g in allowed}
                gpu = max(choices, key=choices.get)
                admission.append({'shard': s, 'choices_free_mib': choices, 'chosen': gpu, 'need_mib': a.peak_mib + MARGIN_MIB,
                                  'smi': st})
                assert choices[gpu] >= a.peak_mib + MARGIN_MIB, ('memory admission refused', choices)
                cmd = [str(CURE_PY), str(ROOT / 'report101_cure.py'), 'worker', '--stage', a.stage, '--out', str(out), '--gpu', gpu,
                       '--shard', str(s), '--nshards', str(a.workers)] + (['--limit', str(a.limit)] if a.limit else [])
                so = (out / f'launch{attempt}_worker{s}.stdout.log').open('x')
                se = (out / f'launch{attempt}_worker{s}.stderr.log').open('x')
                logs.extend([so, se])
                procs.append((s, subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=so, stderr=se), gpu))
                time.sleep(a.stagger)
            with (out / f'launch{attempt}_resource.jsonl').open('x') as rf:
                while any(p.poll() is None for _, p, _ in procs):
                    rf.write(json.dumps({'t': time.time(), 'smi': smi_free()}) + '\n')
                    rf.flush()
                    time.sleep(15)
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
                                                      scientific_digest=sd, allowed=allowed, admission=admission, peak_mib=a.peak_mib,
                                                      script_sha256=sha(__file__)))
        assert all(c == 0 for c in codes.values()), codes
        if all((shard_dir(out, s) / 'completion.json').exists() for s in range(a.workers)):
            save(out / 'completion.json', {'stage': a.stage, 'workers': a.workers, 'n': len(reqs), 'scientific_digest': sd,
                                           'files': {f'shard{s}/completion.json': sha(shard_dir(out, s) / 'completion.json') for s in range(a.workers)}})
            return 0
        return 0 if a.limit else 2


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['worker', 'launch'])
    p.add_argument('--stage', choices=['D4', 'S24'], required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--gpu')
    p.add_argument('--shard', type=int, default=0)
    p.add_argument('--nshards', type=int, default=1)
    p.add_argument('--workers', type=int, default=2)
    p.add_argument('--limit', type=int, default=0, help='통제된 중단 시험용: 이번 실행 저장 최대 요청 수')
    p.add_argument('--peak-mib', type=int, default=10100)
    p.add_argument('--stagger', type=float, default=20.0)
    a = p.parse_args()
    raise SystemExit(worker(a) if a.command == 'worker' else launch(a))
