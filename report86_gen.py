"""iter_086 생성 runner (D8/E96/E192x). report85_d8.py의 모델 로딩·입력·생성 경로를 유지한다.

변경점: 새 결과 경로, 검증된 계승 manifest, 과학적 protocol(모델 로딩 전 대조)과 execution 기록의 분리,
shard 분할, 계승 행 회귀 비교(--regress N). 모델·prompt·변환·정밀도·adapter·seed·cap은 report85_d8과 동일하다.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from report86_common import (ROOT, UP, R85, R86, STAGES, SYSTEMS, SEED, CAPS, B0_DIGEST, sha, sha_obj, save,
                             read_jsonl_complete, record_digest, scientific_protocol, expected_ids, prompts_for,
                             base_path, adapter_path_C)

EXEC_SOURCES = ['report86_gen.py', 'report86_common.py', 'rsna_diag/generate.py', 'rsna_diag/lora.py', 'rsna_diag/geometry.py']


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--stage', choices=list(STAGES), required=True)
    p.add_argument('--system', choices=SYSTEMS, required=True)
    p.add_argument('--gpu', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--shard', type=int, default=0)
    p.add_argument('--nshards', type=int, default=1)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--regress', type=int, default=0, help='계승 행 N개를 새 경로로 재생성해 token을 비교(출력은 --out, stage 출력 아님)')
    p.add_argument('--limit', type=int, default=0, help='이번 실행에서 저장할 최대 요청 수(통제된 중단 시험용)')
    p.add_argument('--regress-offset', type=int, default=0)
    a = p.parse_args()
    out = Path(a.out).resolve()
    out.relative_to(R86)
    assert 0 <= a.shard < a.nshards
    # ---- 모델 로딩 전: 입력·protocol·계승·소유권 검사 ----
    allowed = os.environ['CUDA_VISIBLE_DEVICES'].split(',')
    assert a.gpu in allowed, f'gpu {a.gpu} not in inherited CUDA_VISIBLE_DEVICES {allowed}'
    os.environ['CUDA_VISIBLE_DEVICES'] = a.gpu
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'
    os.environ['HF_HUB_OFFLINE'] = '1'
    st = STAGES[a.stage]
    all_rows = json.loads(st['inputs'].read_text())
    for row in all_rows:
        assert sha(row['image']) == row['file_sha256'], f"input image changed {row['ImageID']}"
    raw = {r['ImageID']: r for r in json.loads(st['raw'].read_text())}
    sci = scientific_protocol(a.system, a.stage)
    sci_digest = sha_obj(sci)
    inherited, inh_meta = {}, None
    if a.stage == 'D8':
        from report86_inherit import load_verified
        inherited, inh_meta = load_verified(a.system)
        assert inh_meta['protocol_sha256'] and not inh_meta['scientific_differences']
    out.mkdir(parents=True, exist_ok=a.resume)
    lock = (out / 'worker.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    from pg43_run import repair_tail
    repair_tail(str(out / 'outputs.jsonl'))
    mypath = out / 'scientific_protocol.json'
    meta = {'scientific': sci, 'scientific_digest': sci_digest, 'stage': a.stage, 'shard': a.shard, 'nshards': a.nshards,
            'mode': 'regress' if a.regress else 'generate'}
    if mypath.exists():
        assert a.resume, 'output dir already has a protocol; use --resume'
        old = json.loads(mypath.read_text())
        assert old == json.loads(json.dumps(meta)), 'resume: scientific protocol/shard/mode mismatch (detected before model load)'
    else:
        save(mypath, meta)
    # 이 shard의 대상 행
    rows = [r for i, r in enumerate(all_rows) if i % a.nshards == a.shard]
    exp_shard = expected_ids(rows, a.system)
    if a.regress:
        pool = sorted(inherited, key=lambda i: sha_obj(['regress86', i]))[a.regress_offset:a.regress_offset + a.regress]
        assert len(pool) == a.regress
        target_ids = set(pool)
    else:
        target_ids = exp_shard
    # 이미 완료된 id: 계승(검증됨) + 같은 stage·system의 모든 shard 디렉터리 출력(자신 포함)
    sibling = []
    if not a.regress:
        sibling_root = out.parent
        for d in sibling_root.glob('shard*'):
            if d.resolve() != out and (d / 'outputs.jsonl').exists():
                sibling += read_jsonl_complete(d / 'outputs.jsonl')
    mine = read_jsonl_complete(out / 'outputs.jsonl')
    for rec in mine:
        assert rec['id'] in target_ids and rec['protocol_digest'] == sci_digest and rec['record_digest'] == record_digest(rec), 'own record invalid'
    assert len(mine) == len({r['id'] for r in mine}), 'duplicate in own output'
    done = {r['id'] for r in mine}
    if not a.regress:
        done |= set(inherited) | {r['id'] for r in sibling}
    todo_ids = sorted(target_ids - done)
    if a.limit:
        todo_ids = todo_ids[:a.limit]
    execution = {'event': 'start', 'time': time.time(), 'pid': os.getpid(), 'gpu_physical': a.gpu, 'python': sys.executable,
                 'source_sha256': {f: sha(ROOT / f) for f in EXEC_SOURCES}, 'n_todo': len(todo_ids), 'n_inherited_skipped': len(set(inherited) & target_ids),
                 'cuda_visible_devices_set': os.environ['CUDA_VISIBLE_DEVICES'],
                 'cache_env': {k: os.environ.get(k) for k in ['HF_HOME', 'HF_HUB_CACHE', 'HF_XET_CACHE', 'TORCH_HOME', 'TMPDIR']}}
    if not todo_ids:
        with (out / 'executions.jsonl').open('a') as f:
            f.write(json.dumps({**execution, 'event': 'nothing_to_do'}) + '\n')
        print(json.dumps({'nothing_to_do': True, 'stage': a.stage, 'system': a.system, 'shard': a.shard}))
        finish(out, a, sci_digest, target_ids, regress=a.regress, inherited=inherited)
        return
    import numpy as np
    import torch
    from transformers import AutoProcessor, AutoModelForImageTextToText, BitsAndBytesConfig
    from rsna_diag import generate as G, lora
    torch.set_num_threads(4)
    torch.manual_seed(SEED)
    is15 = a.system in ['M15', 'B0']
    base = base_path(a.system)
    processor = AutoProcessor.from_pretrained(base, local_files_only=True)
    processor.tokenizer.padding_side = 'left'
    if is15:
        processor.image_processor.do_pan_and_scan = False
    kw = dict(torch_dtype=torch.bfloat16, device_map={'': 0}, local_files_only=True, attn_implementation='sdpa')
    if a.system in ['M1G', 'C']:
        kw['quantization_config'] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type='nf4', bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_quant_storage=torch.bfloat16)
    t0 = time.monotonic()
    model = AutoModelForImageTextToText.from_pretrained(base, **kw)
    adapter_digest = None
    if a.system == 'B0':
        blob = torch.load(ROOT / 'results/iter_012/train/lr2e-4_s17/epoch_05/adapter.pt', map_location='cpu', weights_only=True)
        cfg = blob['config']
        lora.apply_lora(model, cfg['r'], cfg['alpha'], 0.)
        own = {n: v for n, v in model.named_parameters() if 'lora_' in n}
        assert set(own) == set(blob['state'])
        assert all(own[n].shape == v.shape for n, v in blob['state'].items())
        lora.load_lora_state(model, blob['state'])
        adapter_digest = lora.state_digest(lora.lora_state_dict(model))
        assert adapter_digest == B0_DIGEST
    elif a.system == 'C':
        from peft import PeftModel
        ap = adapter_path_C()
        model = PeftModel.from_pretrained(model, str(ap), local_files_only=True)
        assert set(model.peft_config['default'].modules_to_save) == {'lm_head', 'embed_tokens'}
        adapter_digest = sha(ap / 'adapter_model.safetensors')
    assert adapter_digest == sci['adapter_digest'], 'adapter digest differs from pre-load protocol'
    model.eval()
    assert not any(m.training for m in model.modules())
    loading_s = time.monotonic() - t0
    transform = None
    if a.system in ['M1G', 'C']:
        sys.path.insert(0, str(R85 / 'official/minimal'))
        from vlm_research_kit.data.transforms_factory import create_image_transforms
        transform = create_image_transforms(use_model_specific_transforms=True, model_name='pil_with_augmentations',
            bbox_format='cxcywh', image_size=[448, 448], is_train=False,
            augmenter_override_params={'apply_clahe': True, 'clahe_clip_limit': [3., 3.]})
    prompts = dict(prompts_for(a.system))
    eos = model.generation_config.eos_token_id
    eos = [eos] if isinstance(eos, int) else eos
    execution.update({'torch': torch.__version__, 'loading_s': loading_s})
    events = (out / 'executions.jsonl').open('a', buffering=1)
    events.write(json.dumps(execution) + '\n')
    row_by_img = {r['ImageID']: r for r in all_rows}
    by_img = {}
    for rid in todo_ids:
        img, _, name = rid.split('|')
        by_img.setdefault(img, []).append(name)
    saved = 0
    t_start = time.monotonic()
    with (out / 'outputs.jsonl').open('a', buffering=1) as f:
        for img in [r['ImageID'] for r in rows if r['ImageID'] in by_img] if not a.regress else sorted(by_img):
            row = row_by_img[img]
            assert sha(row['image']) == row['file_sha256']
            if transform:
                rr = raw[img]
                assert sha(rr['raw_path']) == rr['sha256']
                im = transform(rr['raw_path'])['pixel_values']
                assert np.array_equal(np.asarray(im), np.asarray(transform(rr['raw_path'])['pixel_values']))
            else:
                im, _, _ = G.load_image(row['image'])
            for name in prompts_for_order(a.system, by_img[img]):
                prompt = prompts[name]
                rid = img + '|' + a.system + '|' + name
                events.write(json.dumps({'event': 'request_start', 'id': rid, 'time': time.time()}) + '\n')
                inp = G.build_inputs(processor, im, prompt)
                official = processor.apply_chat_template([{'role': 'user', 'content': [{'type': 'image', 'image': im}, {'type': 'text', 'text': prompt}]}],
                    add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors='pt', padding=True)
                assert set(inp) == set(official) and all(torch.equal(inp[k], official[k]) for k in inp)
                attempts = []
                for cap in CAPS:
                    result = G.generate(torch, processor, model, inp, cap, eos)
                    attempts.append(result)
                    if result['ended_eos']:
                        break
                rec = {'id': rid, 'ImageID': img, 'condition': name, 'protocol_digest': sci_digest,
                       'image_sha256': row['file_sha256'], 'text': processor.decode(result['suffix_ids'], skip_special_tokens=True),
                       'attempts': attempts, 'input_ids': inp['input_ids'][0].tolist(),
                       'pixel_sha256': hashlib.sha256(np.asarray(im).tobytes()).hexdigest(),
                       'exec': {'gpu': a.gpu, 'shard': a.shard, 'pid': os.getpid(), 'torch': torch.__version__}}
                rec['record_digest'] = record_digest(rec)
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
                saved += 1
                events.write(json.dumps({'event': 'request_saved', 'id': rid, 'time': time.time(), 'seconds': result['runtime_s'],
                                         'n_new': result['n_new'], 'attempts': len(attempts)}) + '\n')
                print(json.dumps({'saved': saved, 'of': len(todo_ids), 'system': a.system, 'shard': a.shard, 'tokens': result['n_new'],
                                  'seconds': round(result['runtime_s'], 2)}), flush=True)
    events.write(json.dumps({'event': 'end', 'time': time.time(), 'saved': saved, 'wall_s': time.monotonic() - t_start,
                             'peak_reserved_gib_max': max(max(a_['peak_mem_reserved_gb'] for a_ in r['attempts']) for r in read_jsonl_complete(out / 'outputs.jsonl'))}) + '\n')
    events.close()
    finish(out, a, sci_digest, target_ids, regress=a.regress, inherited=inherited)


def prompts_for_order(system, names):
    order = [n for n, _ in prompts_for(system)]
    return [n for n in order if n in set(names)]


def finish(out, a, sci_digest, target_ids, regress, inherited):
    recs = read_jsonl_complete(out / 'outputs.jsonl')
    got = {r['id'] for r in recs}
    if regress:
        diffs = []
        for r in recs:
            old = inherited[r['id']]
            same = r['attempts'][-1]['suffix_ids'] == old['attempts'][-1]['suffix_ids'] and r['input_ids'] == old['input_ids'] \
                and r['pixel_sha256'] == old['pixel_sha256']
            diffs.append({'id': r['id'], 'tokens_equal': r['attempts'][-1]['suffix_ids'] == old['attempts'][-1]['suffix_ids'],
                          'input_ids_equal': r['input_ids'] == old['input_ids'], 'pixel_equal': r['pixel_sha256'] == old['pixel_sha256'],
                          'n_new_old': old['attempts'][-1]['n_new'], 'n_new_new': r['attempts'][-1]['n_new'],
                          'old_gpu_seconds': sum(x['runtime_s'] for x in old['attempts']), 'new_seconds': sum(x['runtime_s'] for x in r['attempts']), 'equal': same})
        res = {'n': len(recs), 'n_equal': sum(d['equal'] for d in diffs), 'complete': got == target_ids, 'items': diffs,
               'exec': recs[0]['exec'] if recs else None}
        rp = out / f'regress_result_{int(time.time())}.json'
        save(rp, res)
        print(json.dumps({'regress_equal': res['n_equal'], 'of': res['n'], 'result': str(rp)}))
        return
    complete = target_ids <= (got | set(inherited))
    cp = out / 'completion.json'
    if complete and not cp.exists():
        events = read_jsonl_complete(out / 'executions.jsonl') if False else [json.loads(l) for l in (out / 'executions.jsonl').read_text().splitlines() if l]
        save(cp, {'stage': a.stage, 'system': a.system, 'shard': a.shard, 'nshards': a.nshards, 'n_own_records': len(recs),
                  'n_inherited_in_shard_scope': len(set(inherited) & target_ids), 'n_expected_in_shard': len(target_ids),
                  'files': {'scientific_protocol.json': sha(out / 'scientific_protocol.json'), 'outputs.jsonl': sha(out / 'outputs.jsonl')},
                  'final_not_eos': sum(not r['attempts'][-1]['ended_eos'] for r in recs),
                  'executions': len([e for e in events if e['event'] == 'start']),
                  'generation_s_total': sum(sum(x['runtime_s'] for x in r['attempts']) for r in recs),
                  'cost_scope': 'generation seconds of records in this shard dir; loading/interrupted cost in executions.jsonl'})


if __name__ == '__main__':
    main()
