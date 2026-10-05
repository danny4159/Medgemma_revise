"""iter_075 MedGemma 3영상 grade 과제 입력·parser·loss.

- 공식 chat template(apply_chat_template)로 user content = [image x3, text]. 영상 순서 m1, c, p1. 답변 문자열은 '1'..'5' 하나.
- 학습 labels: assistant 본문 + <end_of_turn> 만 (generation prefix와 token 대조, pixel_values 대조). 후행 '\n'는 -100.
- loss: 공식 forward의 logits(전 위치)에서 float32 CE 합. 공식 model(**inp, labels=).loss와 같은 logits 기준으로 대조(check_loss).
- RSNA 고정 target/prompt/cap은 사용하지 않는다.
"""
import re

import numpy as np

from rsna_diag import generate as GEN

PROMPT_F = ('These are three adjacent sagittal T2-weighted slices of a lumbar spine MRI, shown in left-to-right order. '
            'A red rectangle on each slice marks the region of one intervertebral disc. '
            'What is the Pfirrmann grade (1 = bright homogeneous disc with clear nucleus/annulus distinction, '
            '5 = dark collapsed disc without distinction) of the marked intervertebral disc? Answer with a single digit from 1 to 5.')
PROMPT_R = ('These are three adjacent sagittal T2-weighted MRI crops of one lumbar intervertebral disc, shown in left-to-right order. '
            'What is the Pfirrmann grade (1 = bright homogeneous disc with clear nucleus/annulus distinction, '
            '5 = dark collapsed disc without distinction) of this intervertebral disc? Answer with a single digit from 1 to 5.')
PROMPTS = {'F': PROMPT_F, 'R': PROMPT_R}
MAX_NEW = 32
_PAT = re.compile(r'^[1-5]$')


def parse(text):
    """whole-string: 양끝 공백과 단일 종료 마침표만 허용. returns grade int 또는 None(invalid)."""
    t = text.strip()
    if t.endswith('.'):
        t = t[:-1].rstrip()
    return int(t) if _PAT.match(t) else None


def load_images(entry_list):
    """manifest의 입력 3장 -> PIL RGB(padded) 목록과 pixel hash 검증."""
    ims = []
    for e in entry_list:
        im, _, px = GEN.load_image(e['path'])
        if px != e['pixel_sha256_padded']:
            raise RuntimeError(f"pixel hash changed {e['path']}")
        ims.append(im)
    return ims


def msgs(ims, prompt, target=None):
    user = {'role': 'user', 'content': [{'type': 'image', 'image': im} for im in ims] + [{'type': 'text', 'text': prompt}]}
    return [user] + ([{'role': 'assistant', 'content': [{'type': 'text', 'text': target}]}] if target is not None else [])


def build_gen_inputs(proc, ims, prompt):
    return proc.apply_chat_template(msgs(ims, prompt), add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors='pt')


def build_example(proc, ims, prompt, target):
    import torch
    gen = build_gen_inputs(proc, ims, prompt)
    full = proc.apply_chat_template(msgs(ims, prompt, target), add_generation_prompt=False, tokenize=True, return_dict=True, return_tensors='pt')
    gi, fi = gen['input_ids'][0], full['input_ids'][0]
    n = gi.shape[0]
    if fi.shape[0] <= n or not torch.equal(fi[:n], gi):
        raise ValueError('generation prefix != training prefix')
    tail = proc.tokenizer.decode(fi[n:].tolist(), skip_special_tokens=False)
    if tail != target + '<end_of_turn>\n':
        raise ValueError(f'unexpected assistant tail {tail!r}')
    if not torch.equal(gen['pixel_values'], full['pixel_values']):
        raise ValueError('pixel_values differ')
    if full['pixel_values'].shape[0] != len(ims):
        raise ValueError(f"pixel_values images {full['pixel_values'].shape[0]} != {len(ims)}")
    labels = fi.clone()
    labels[:n] = -100
    labels[-1] = -100
    ex = {'input_ids': fi, 'attention_mask': full['attention_mask'][0], 'pixel_values': full['pixel_values'], 'labels': labels, 'n_prefix': n}
    if 'token_type_ids' in full:
        ex['token_type_ids'] = full['token_type_ids'][0]
    return ex


def collate(examples, pad_id):
    import torch
    L = max(e['input_ids'].shape[0] for e in examples)
    B = len(examples)
    ids = torch.full((B, L), pad_id, dtype=torch.long)
    att = torch.zeros((B, L), dtype=torch.long)
    lab = torch.full((B, L), -100, dtype=torch.long)
    has_tt = 'token_type_ids' in examples[0]
    tt = torch.zeros((B, L), dtype=torch.long) if has_tt else None
    for i, e in enumerate(examples):
        n = e['input_ids'].shape[0]
        ids[i, :n], att[i, :n], lab[i, :n] = e['input_ids'], e['attention_mask'], e['labels']
        if has_tt:
            tt[i, :n] = e['token_type_ids']
    out = {'input_ids': ids, 'attention_mask': att, 'labels': lab, 'pixel_values': torch.cat([e['pixel_values'] for e in examples], 0)}
    if has_tt:
        out['token_type_ids'] = tt
    if 'sample_pos' in examples[0]:
        out['sample_pos'] = torch.tensor([e['sample_pos'] for e in examples], dtype=torch.long)
    return out


def to_cuda(b):
    import torch
    out = {}
    for k, v in b.items():
        if k == 'sample_pos':
            continue
        out[k] = v.cuda()
    return out


def forward_logits(torch, model, batch):
    """공식 forward (labels 없음) -> logits[B,L,V] (모델 dtype). pixel_values는 bf16."""
    inp = {k: v for k, v in batch.items() if k != 'labels'}
    inp['pixel_values'] = inp['pixel_values'].to(torch.bfloat16)
    return model(**inp, use_cache=False).logits


def loss_sum(torch, model, batch):
    """official logits에서 float32 CE 합과 유효 token 수. (labels[:,1:] vs logits[:,:-1])"""
    logits = forward_logits(torch, model, batch)
    lab = batch['labels'][:, 1:]
    sel = lab != -100
    lg = logits[:, :-1][sel].float()
    return torch.nn.functional.cross_entropy(lg, lab[sel], reduction='sum'), int(sel.sum())


def check_loss(torch, model, batch):
    """독립 대조: (a) 공식 loss(labels 전달) (b) 같은 logits의 float32 CE mean (c) loss_sum/n. 반환 dict."""
    inp = {k: v for k, v in batch.items()}
    inp['pixel_values'] = inp['pixel_values'].to(torch.bfloat16)
    out = model(**inp, use_cache=False)
    logits = out.logits
    lab = batch['labels'][:, 1:]
    sel = lab != -100
    ce_f32 = torch.nn.functional.cross_entropy(logits[:, :-1][sel].float(), lab[sel], reduction='mean')
    ls, n = loss_sum(torch, model, batch)
    return {'official_loss': float(out.loss), 'logits_f32_ce_mean': float(ce_f32), 'loss_sum_over_n': float(ls) / n, 'n_valid_tokens': n,
            'n_valid_independent': int((batch['labels'][:, 1:] != -100).sum())}
