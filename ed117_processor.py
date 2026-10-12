"""기존 직접 대조와 같은 TECH 4입력의 processor tensor 비교. 모델 생성 없음."""
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault('HF_HUB_OFFLINE', '1')
os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')
import torch
import transformers
from rsna_diag import generate as G
from ed116_directcheck import indep_pad


def main():
    from pg43_run import read_requests, read_records
    rows = read_requests('results/iter_116/requests/TECH.jsonl')
    byk = {(r['patient'], r['cond']): r for r in rows}
    pats = sorted({r['patient'] for r in rows})
    pick = [byk[pats[0], 'R'], byk[pats[1], 'N'], byk[pats[0], 'T'], byk[pats[2], 'T']]
    records = {r['request_id']: r for fn in Path('results/iter_116/gen/TECH_w2').glob('gen_worker*.jsonl') for r in read_records(fn)}
    proc = transformers.AutoProcessor.from_pretrained(G.MODEL_ID, revision=G.MODEL_REVISION, local_files_only=True)
    config = transformers.AutoConfig.from_pretrained(G.MODEL_ID, revision=G.MODEL_REVISION, local_files_only=True)
    result = []
    for row in pick:
        if row['modality'] == 'image':
            image, affine, px = G.load_image(row['image'])
            worker = G.build_inputs(proc, image, row['prompt'])
            independent_image, independent_sha = indep_pad(row['image'])
            content = [{'type': 'image', 'image': independent_image}, {'type': 'text', 'text': row['prompt']}]
            assert px == independent_sha == row['input_pixel_sha256']
        else:
            worker = G.build_inputs_text(proc, row['prompt'])
            content = [{'type': 'text', 'text': row['prompt']}]
        official = proc.apply_chat_template([{'role': 'user', 'content': content}], add_generation_prompt=True,
                                           tokenize=True, return_dict=True, return_tensors='pt')
        checks = {}
        for k in set(worker) | set(official):
            checks[k] = k in worker and k in official and worker[k].shape == official[k].shape and worker[k].dtype == official[k].dtype and torch.equal(worker[k], official[k])
        ids = worker['input_ids'][0].tolist()
        rec = records[row['request_id']]
        image_count = ids.count(config.image_token_index)
        checks['input_ids_equal_old_record'] = hashlib.sha256(json.dumps(ids).encode()).hexdigest() == rec['input_ids_sha256']
        checks['text_no_image_or_image_present'] = (image_count > 0 and 'pixel_values' in worker) if row['modality'] == 'image' else (
            image_count == 0 and not any(k.startswith('pixel') or 'image' in k for k in worker))
        checks['bf16_pixel_values_equal'] = row['modality'] != 'image' or torch.equal(worker['pixel_values'].to(torch.bfloat16), official['pixel_values'].to(torch.bfloat16))
        result.append(dict(request_id=row['request_id'], cond=row['cond'], checks=checks,
                           tensors={k: dict(shape=list(v.shape), dtype=str(v.dtype), sha256=hashlib.sha256(v.contiguous().numpy().tobytes()).hexdigest()) for k, v in worker.items()}))
    out = dict(all_pass=all(all(r['checks'].values()) for r in result), n=len(result), results=result,
               model_loaded=False, new_generate_requests=0, torch=torch.__version__, transformers=transformers.__version__,
               note='공식 processor CPU tensor 및 bf16 pixel cast 대조. 기존 padding hash 검사와 구분.')
    path = Path('results/iter_117/tests/processor.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        json.dump(out, f, indent=1)
    print('processor all_pass', out['all_pass'])
    raise SystemExit(0 if out['all_pass'] else 1)


if __name__ == '__main__':
    main()
