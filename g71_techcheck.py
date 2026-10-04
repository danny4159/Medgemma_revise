"""iter_071 기술 검사 (학습 전): LoRA 항등·source adapter 로드·assistant mask·공식 forward CE/gradient 대조·base 동결·mask 독립·F139 차단·비유한 거부.
결과: results/iter_071/tests/techcheck.json. 사용: python g71_techcheck.py
"""
import copy, hashlib, json, os, sys

import numpy as np

import g71_data as D
import g71_train as TR
from rsna_diag import generate as GEN, lora, sft_data
from rsna_diag import train as T

OUT = 'results/iter_071/tests/techcheck.json'
res = {}


def check(name, ok, **info):
    res[name] = {'pass': bool(ok), **info}
    print(('PASS ' if ok else 'FAIL ') + name, info, flush=True)


# --- CPU: mask 독립, F139, 비유한 ---
sp = D.load_split()
try:
    D.guard('7')
    check('F139_blocked', False)
except PermissionError:
    check('F139_blocked', True)
import sp67_data as S
orig = S.load_pair
def zero_mask_pair(pid, seq):
    d = orig(pid, seq)
    d = dict(d)
    d['L'] = np.zeros_like(d['L'])
    return d
S.load_pair = zero_mask_pair
rows0, info0 = D.build_patient('61', outdir='results/iter_071/tests/maskfree_images')
S.load_pair = orig
man = json.load(open(f'{D.DATA}/manifest.json'))
same = all(info0['images'][k]['file_sha256'] == man['patients']['61']['images'][k]['file_sha256'] for k in ('m1', 'c', 'p1'))
same_sel = info0['selected'] == man['patients']['61']['selected']
check('mask_does_not_affect_slice_or_pixels', same and same_sel, selected=info0['selected'])
try:
    V = np.random.rand(5, 8, 8).astype(np.float32)
    V[0, 0, 0] = np.nan
    D.render_slice(V, [1, 1, 1], 1)
    check('nonfinite_rejected', False)
except ValueError:
    check('nonfinite_rejected', True)

# --- GPU ---
import torch
rows = TR.load_items('T8')
check('train_examples', len(rows) == 48 and sum(r['category'] == 'vertebra' for r in rows) == 24, n=len(rows))
torch_, proc, model = GEN.load_model()
ex, tgt = TR.example(proc, rows[0])
labels = ex['labels']
tok = proc.tokenizer
lab_ids = labels[labels != -100].tolist()
check('assistant_mask', tok.decode(lab_ids) == tgt + '<end_of_turn>' and bool((labels[:ex['n_prefix']] == -100).all()), n_label_tokens=len(lab_ids), tgt=tgt[:80])
b = {k: (v.unsqueeze(0).cuda() if k in ('input_ids', 'attention_mask', 'labels', 'token_type_ids') else v.cuda()) for k, v in ex.items() if k != 'n_prefix'}
softcap = getattr(model.config.get_text_config(), 'final_logit_softcapping', None)
with torch.no_grad():
    inp = {k: v for k, v in b.items() if k != 'labels'}
    inp['pixel_values'] = inp['pixel_values'].to(torch.bfloat16)
    logits_base = model(**inp, use_cache=False).logits.float()[:, :-1][b['labels'][:, 1:] != -100].cpu()
    # 공식 forward CE (모델 전체 logits) 대 helper CE
    lab = b['labels'][:, 1:]
    full = model(**inp, use_cache=False).logits.float()[:, :-1]
    ce_official = torch.nn.functional.cross_entropy(full[lab != -100], lab[lab != -100], reduction='sum').item()
    ce_helper, n = T.assistant_loss_sum(torch, model, b, softcap)
check('helper_ce_equals_official_forward_ce', abs(ce_official - float(ce_helper)) / ce_official < 1e-4, official=ce_official, helper=float(ce_helper), n_tokens=n)
bd_before = lora.base_digest(model)
# D 초기 항등
names = lora.apply_lora(model, 16, 32, 0.05, seed=17)
model.eval()
with torch.no_grad():
    inp2 = {k: v for k, v in b.items() if k != 'labels'}
    inp2['pixel_values'] = inp2['pixel_values'].to(torch.bfloat16)
    logits_lora0 = model(**inp2, use_cache=False).logits.float()[:, :-1][b['labels'][:, 1:] != -100].cpu()
check('D_init_identity_logits', float((logits_base - logits_lora0).abs().max()) == 0.0, max_abs_diff=float((logits_base - logits_lora0).abs().max()), n_lora_modules=len(names),
      n_trainable=sum(p.numel() for p in lora.lora_params(model).values()))
# gradient: helper vs 공식 전체 logits CE의 B 행렬 gradient (A는 B=0이라 grad 0)
model.train()
model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False})
model.config.use_cache = False
pm = {n_: p for n_, p in model.named_parameters() if 'lora_B' in n_}
for p in model.parameters():
    p.grad = None
torch.manual_seed(0)
ls, nt = T.assistant_loss_sum(torch, model, b, softcap)
(ls / nt).backward()
g_h = {n_: p.grad.detach().clone() for n_, p in pm.items()}
for p in model.parameters():
    p.grad = None
torch.manual_seed(0)
inp3 = {k: v for k, v in b.items() if k != 'labels'}
inp3['pixel_values'] = inp3['pixel_values'].to(torch.bfloat16)
full = model(**inp3, use_cache=False).logits.float()[:, :-1]
lab = b['labels'][:, 1:]
lf = full
if softcap:
    pass  # HF logits에는 softcap이 이미 적용돼 있다
ce_o = torch.nn.functional.cross_entropy(lf[lab != -100], lab[lab != -100], reduction='sum') / nt
ce_o.backward()
rel = []
for n_, p in pm.items():
    num = (p.grad - g_h[n_]).norm().item()
    den = g_h[n_].norm().item() + 1e-12
    rel.append(num / den)
check('helper_grad_equals_official_grad', max(rel) < 0.05, max_rel=max(rel), median_rel=float(np.median(rel)), note='dropout RNG seeded equally; bf16 tolerance 5%')
for p in model.parameters():
    p.grad = None
# R: source adapter 로드 재현
blob = torch.load(TR.SOURCE_ADAPTER, map_location='cpu', weights_only=True)
dg = lora.state_digest(blob['state'])
lora.load_lora_state(model, blob['state'])
dg2 = lora.state_digest(lora.lora_state_dict(model))
check('R_source_adapter_load', dg == TR.SOURCE_DIGEST == dg2 and blob['config'] == {'r': 16, 'alpha': 32} and len(blob['state']) == 2 * len(names), digest=dg, n_tensors=len(blob['state']))
# base 동결: 한 optimizer step 후 base digest 불변
params = list(lora.lora_params(model).values())
opt = torch.optim.AdamW(params, lr=1e-4)
ls, nt = T.assistant_loss_sum(torch, model, b, softcap)
(ls / nt).backward()
opt.step()
bd_after = lora.base_digest(model)
check('base_frozen_after_step', bd_before == bd_after, digest=bd_after[:16])
check('lora_params_changed_after_step', lora.state_digest(lora.lora_state_dict(model)) != dg)
# 생성 prefix == 학습 prefix, pixel tensor 일치는 build_example 내부에서 강제됨 (모든 48개 예제에서 통과 확인)
for r in rows:
    TR.example(proc, r)
check('all_48_examples_prefix_pixel_consistent', True)
json.dump(res, open(OUT, 'w'), indent=1)
print('all pass:', all(v['pass'] for v in res.values()))
