"""iter_123: 공식 apply_chat_template 경로와 수동 processor(text=, images=) 경로의 input_ids/pixel_values 동일성, 순서·placeholder·token 수 검사."""
import json, sys, hashlib
import torch
import mr123_run as R
from transformers import AutoProcessor

stage = sys.argv[1]
reqs = R.read_jsonl(R.GEN + stage + '/requests.jsonl')
proc = AutoProcessor.from_pretrained(R.MODEL, revision=R.REV, cache_dir=R.CACHE)
res = []
bad = 0
boi = proc.tokenizer.convert_tokens_to_ids('<start_of_image>') if '<start_of_image>' in proc.tokenizer.get_vocab() else None
img_tok = proc.tokenizer.convert_tokens_to_ids('<image_soft_token>')
for r in reqs:
    msgs = R.messages_for(r)
    a = proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors='pt')
    text = proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
    from PIL import Image
    imgs = [Image.open(p).convert('RGB') for p in r['paths']]
    b = proc(text=text, images=imgs, return_tensors='pt', add_special_tokens=False)
    ids_eq = bool(torch.equal(a['input_ids'], b['input_ids']))
    pv_eq = bool(torch.equal(a['pixel_values'], b['pixel_values']))
    n_img_tok = int((a['input_ids'] == img_tok).sum())
    # 이미지 순서: 개별 이미지 pixel_values가 파일 순서와 일치
    single = [proc(text='<start_of_image>', images=[im], return_tensors='pt')['pixel_values'][0] for im in imgs]
    order_ok = all(torch.equal(a['pixel_values'][i], single[i]) for i in range(len(imgs)))
    ok = ids_eq and pv_eq and order_ok and (n_img_tok == 256 * len(imgs))
    bad += (not ok)
    leak = any(k in text for k in [r['study_uid'], str(r['patient_uid']), '.png', r['label'], 'batch'])
    res.append(dict(id=r['id'], cond=r['cond'], ids_eq=ids_eq, pv_eq=pv_eq, order_ok=order_ok, n_img=len(imgs), n_img_tok=n_img_tok,
                    seq_len=int(a['input_ids'].shape[1]), pv_shape=list(a['pixel_values'].shape), leak_in_text=leak, ok=ok and not leak))
out = dict(stage=stage, n=len(res), n_ok=sum(x['ok'] for x in res), results=res, chat_template_head=text[:300])
json.dump(out, open(R.D.RES + f'tests/tensor_check_{stage}.json', 'w'), indent=1)
print(out['n'], out['n_ok'], res[0])
