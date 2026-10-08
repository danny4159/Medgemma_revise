"""iter_101 기술 검사(교정 생성 경로): text-only/image+text 공식 입력 대조, adapter 부재, 무패치 공식 generate와 저장 출력 token 대조.

공식 경로 = AutoProcessor.apply_chat_template + model.generate(do_sample=False) (rsna_diag.generate.generate와 같은 호출).
저장 출력(D4_w2)과 token이 갈리면 첫 차이 위치를 그대로 기록한다(성공으로 바꾸지 않는다).
사용: python report101_tech.py <gpu> <D4 gen dir> <requests.json> <out.json>
"""
import json
import os
import sys
from pathlib import Path

from report86_common import ROOT, base_path, save, read_jsonl_complete

R101 = ROOT / 'results/iter_101'


def first_diff(a, b):
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    return None if len(a) == len(b) else min(len(a), len(b))


def main():
    gpu, gen, reqf, outf = sys.argv[1:5]
    allowed = os.environ['CUDA_VISIBLE_DEVICES'].split(',')
    assert gpu in allowed, (gpu, allowed)
    os.environ['CUDA_VISIBLE_DEVICES'] = gpu
    os.environ['HF_HUB_OFFLINE'] = '1'
    import torch
    import transformers
    from rsna_diag import generate as G
    reqs = {r['id']: r for r in json.loads(Path(reqf).read_text())}
    gen = Path(gen)
    mp = json.loads((gen / 'mapping.json').read_text())
    saved = {}
    for s in range(mp['workers']):
        for r in read_jsonl_complete(gen / f'worker_{s}.jsonl'):
            saved[r['id']] = r
    proc = transformers.AutoProcessor.from_pretrained(base_path('M15'), local_files_only=True)
    proc.image_processor.do_pan_and_scan = False
    model = transformers.AutoModelForImageTextToText.from_pretrained(base_path('M15'), local_files_only=True, dtype=torch.bfloat16,
                                                                     device_map={'': 0}, attn_implementation='sdpa').eval()
    res = {'adapter_check': {'has_peft_config': hasattr(model, 'peft_config'), 'n_lora_params': sum('lora_' in n for n, _ in model.named_parameters()),
                             'n_trainable': sum(p.requires_grad for p in model.parameters())},
           'transformers': transformers.__version__, 'torch': torch.__version__}
    img_tok = model.config.image_token_index
    eos = model.generation_config.eos_token_id
    eos = [eos] if isinstance(eos, int) else eos
    pick = [k for k in sorted(saved) if k.endswith('|T')][:2] + [k for k in sorted(saved) if k.endswith('|V')][:1] + [k for k in sorted(saved) if k.endswith('|W')][:1]
    out = {}
    for k in pick:
        q = reqs[k]
        if q['image'] is None:
            wrap = G.build_inputs_text(proc, q['prompt'])
            off = proc.apply_chat_template([{'role': 'user', 'content': [{'type': 'text', 'text': q['prompt']}]}], add_generation_prompt=True,
                                           tokenize=True, return_dict=True, return_tensors='pt', padding=True)
        else:
            image, _, _ = G.load_image(q['image'])
            wrap = G.build_inputs(proc, image, q['prompt'])
            off = proc.apply_chat_template([{'role': 'user', 'content': [{'type': 'image', 'image': image}, {'type': 'text', 'text': q['prompt']}]}],
                                           add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors='pt', padding=True)
        same_keys = set(wrap) == set(off)
        tensors_equal = same_keys and all(torch.equal(wrap[x], off[x]) for x in wrap)
        n_img = int((off['input_ids'] == img_tok).sum())
        dev = {x: (v.to('cuda', dtype=torch.bfloat16) if x == 'pixel_values' else v.to('cuda')) for x, v in off.items()}
        ref = saved[k]['attempts'][0]['suffix_ids']
        with torch.no_grad():
            g = model.generate(**dev, max_new_tokens=len(ref), do_sample=False)
        toks = g[0, dev['input_ids'].shape[1]:].tolist()
        out[k] = {'modality': 'text' if q['image'] is None else 'image', 'keys': sorted(off), 'same_keys': same_keys, 'tensors_equal': tensors_equal,
                  'has_pixel_values': 'pixel_values' in off, 'n_image_tokens_in_input': n_img, 'n_input_tokens': int(off['input_ids'].shape[1]),
                  'input_ids_equal_saved': off['input_ids'][0].tolist() == saved[k]['input_ids'], 'saved_len': len(ref), 'official_len': len(toks),
                  'first_diff_vs_saved': first_diff(toks, ref), 'tokens_equal_saved': toks == ref,
                  'image_source': q.get('image_source_ImageID')}
    res['per_request'] = out
    res['summary'] = {'all_tensors_equal': all(v['tensors_equal'] for v in out.values()),
                      'text_only_has_no_image': all(not v['has_pixel_values'] and v['n_image_tokens_in_input'] == 0 for v in out.values() if v['modality'] == 'text'),
                      'image_has_image_tokens': all(v['has_pixel_values'] and v['n_image_tokens_in_input'] > 0 for v in out.values() if v['modality'] == 'image'),
                      'all_tokens_equal_saved': all(v['tokens_equal_saved'] for v in out.values()),
                      'all_input_ids_equal_saved': all(v['input_ids_equal_saved'] for v in out.values())}
    save(outf, res)
    print(json.dumps(res['summary']), json.dumps(res['adapter_check']))


if __name__ == '__main__':
    main()
