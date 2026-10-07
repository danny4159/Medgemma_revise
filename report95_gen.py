"""iter_095 생성 runner: CURE(MedGemma 1 base + 공식 adapter)로 고정 8영역의 공식 Describe / Locate and describe.

report86_gen의 모델 로딩·입력·생성 경로(NF4·bf16·공식 processor/chat template·CLAHE·greedy·cap 1024→2048→4096)를 유지한다.
변경: 새 결과 경로, 요청 manifest, 모델 로딩 전 protocol/요청/기존 행 검증, sibling 행 수용 제거(자기 shard 파일만 재개),
자기 행의 요청·digest 전수 검증, 완료 파일 덮어쓰기 거부, --regress(기존 Locate and describe token 회귀).
"""
import argparse
import fcntl
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from report95_common import (ROOT, R85, R86, R95, EXEC_SOURCES, SYSTEM, sha, sha_obj, save, read_jsonl_complete, record_digest,
                             requests, inputs_rows, scientific_protocol, old_C_records, CAPS, SEED)


def load_own(out, reqmap, sci_digest):
    """자기 shard의 완결 행 전수 검증. 하나라도 이상하면 예외."""
    mine = read_jsonl_complete(out / 'outputs.jsonl')
    ids = [r['id'] for r in mine]
    assert len(ids) == len(set(ids)), 'duplicate in own output'
    for r in mine:
        q = reqmap.get(r['id'])
        assert q is not None, f"own record outside request set {r['id']}"
        assert r['protocol_digest'] == sci_digest, 'own record protocol digest mismatch'
        assert r['record_digest'] == record_digest(r), 'own record digest mismatch (tampered)'
        assert r['prompt'] == q['prompt'] and r['ImageID'] == q['ImageID'], 'own record prompt/image mismatch'
    return mine


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--stage', choices=['D8', 'E32', 'E64'], required=True)
    p.add_argument('--gpu', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--shard', type=int, default=0)
    p.add_argument('--nshards', type=int, default=1)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--limit', type=int, default=0, help='이번 실행에서 저장할 최대 요청 수(통제된 중단 시험용)')
    a = p.parse_args()
    out = Path(a.out).resolve()
    out.relative_to(R95)
    assert 0 <= a.shard < a.nshards
    # ---- 모델 로딩 전 검사 ----
    allowed = os.environ['CUDA_VISIBLE_DEVICES'].split(',')
    assert a.gpu in allowed, f'gpu {a.gpu} not in inherited CUDA_VISIBLE_DEVICES {allowed}'
    os.environ['CUDA_VISIBLE_DEVICES'] = a.gpu
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'
    os.environ['HF_HUB_OFFLINE'] = '1'
    reqs = requests(a.stage)
    reqmap = {r['id']: r for r in reqs}
    rows, raw = inputs_rows(a.stage)
    for row in rows:
        assert sha(row['image']) == row['file_sha256'], f"input image changed {row['ImageID']}"
        assert sha(raw[row['ImageID']]['raw_path']) == raw[row['ImageID']]['sha256'], 'raw image changed'
    sci = scientific_protocol(a.stage)
    sci_digest = sha_obj(sci)
    out.mkdir(parents=True, exist_ok=a.resume)
    lock = (out / 'worker.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    from pg43_run import repair_tail
    repair_tail(str(out / 'outputs.jsonl'))
    meta = {'scientific': sci, 'scientific_digest': sci_digest, 'stage': a.stage, 'shard': a.shard, 'nshards': a.nshards}
    mypath = out / 'scientific_protocol.json'
    if mypath.exists():
        assert a.resume, 'output dir already has a protocol; use --resume'
        assert json.loads(mypath.read_text()) == json.loads(json.dumps(meta)), 'resume: protocol/shard mismatch (before model load)'
    else:
        save(mypath, meta)
    assert not (out / 'completion.json').exists() or a.resume, 'completed output exists'
    my_rows = [r for i, r in enumerate(rows) if i % a.nshards == a.shard]
    my_imgs = {r['ImageID'] for r in my_rows}
    target = [q for q in reqs if q['ImageID'] in my_imgs]
    mine = load_own(out, reqmap, sci_digest)
    assert all(r['ImageID'] in my_imgs for r in mine), 'own record belongs to another shard'
    done = {r['id'] for r in mine}
    todo = [q for q in target if q['id'] not in done]
    if a.limit:
        todo = todo[:a.limit]
    execution = {'event': 'start', 'time': time.time(), 'pid': os.getpid(), 'gpu_physical': a.gpu, 'python': sys.executable,
                 'source_sha256': {f: sha(ROOT / f) for f in EXEC_SOURCES}, 'n_todo': len(todo), 'n_target': len(target),
                 'cuda_visible_devices_set': os.environ['CUDA_VISIBLE_DEVICES'],
                 'cache_env': {k: os.environ.get(k) for k in ['HF_HOME', 'HF_HUB_CACHE', 'HF_XET_CACHE', 'TORCH_HOME', 'TMPDIR']}}
    events = (out / 'executions.jsonl').open('a', buffering=1)
    if not todo:
        events.write(json.dumps({**execution, 'event': 'nothing_to_do'}) + '\n')
        events.close()
        finish(out, a, sci_digest, target, reqmap)
        return
    import numpy as np
    import torch
    from transformers import AutoProcessor, AutoModelForImageTextToText, BitsAndBytesConfig
    from peft import PeftModel
    from rsna_diag import generate as G
    from report95_common import base_path, adapter_path_C
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
    assert sha(ap / 'adapter_model.safetensors') == sci['adapter_digest'], 'adapter digest differs from pre-load protocol'
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
    with (out / 'outputs.jsonl').open('a', buffering=1) as f:
        for img in [r['ImageID'] for r in my_rows if r['ImageID'] in by_img]:
            rr = raw[img]
            im = transform(rr['raw_path'])['pixel_values']
            assert np.array_equal(np.asarray(im), np.asarray(transform(rr['raw_path'])['pixel_values']))
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
                rec = {'id': q['id'], 'ImageID': img, 'fmt': q['fmt'], 'region': q['region'], 'prompt': q['prompt'],
                       'protocol_digest': sci_digest, 'image_sha256': row['file_sha256'],
                       'text': processor.decode(result['suffix_ids'], skip_special_tokens=True), 'attempts': attempts,
                       'input_ids': inp['input_ids'][0].tolist(), 'pixel_sha256': hashlib.sha256(np.asarray(im).tobytes()).hexdigest(),
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
    allrecs = read_jsonl_complete(out / 'outputs.jsonl')
    events.write(json.dumps({'event': 'end', 'time': time.time(), 'saved': saved, 'wall_s': time.monotonic() - t_start,
                             'peak_reserved_gib_max': max(max(x['peak_mem_reserved_gb'] for x in r['attempts']) for r in allrecs)}) + '\n')
    events.close()
    finish(out, a, sci_digest, target, reqmap)


def finish(out, a, sci_digest, target, reqmap):
    recs = load_own(out, reqmap, sci_digest)
    got = {r['id'] for r in recs}
    want = {q['id'] for q in target}
    cp = out / 'completion.json'
    if want <= got and not cp.exists():
        events = [json.loads(l) for l in (out / 'executions.jsonl').read_text().splitlines() if l]
        save(cp, {'stage': a.stage, 'shard': a.shard, 'nshards': a.nshards, 'n_own_records': len(recs), 'n_expected_in_shard': len(want),
                  'files': {'scientific_protocol.json': sha(out / 'scientific_protocol.json'), 'outputs.jsonl': sha(out / 'outputs.jsonl')},
                  'final_not_eos': sum(not r['attempts'][-1]['ended_eos'] for r in recs),
                  'executions': len([e for e in events if e['event'] == 'start']),
                  'generation_s_total': sum(sum(x['runtime_s'] for x in r['attempts']) for r in recs),
                  'cost_scope': 'generation seconds of records in this shard dir; loading/interrupted cost in executions.jsonl'})


if __name__ == '__main__':
    main()
