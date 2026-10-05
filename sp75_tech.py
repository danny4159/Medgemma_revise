"""iter_075 동작 확인 (GPU): 3영상 chat template·pixel tensor·mask·loss 대조·LoRA 항등/동결/gradient/update·microbatch 비교.
사용: CUDA_VISIBLE_DEVICES=<gpu> python sp75_tech.py --out results/iter_075/tests/tech_F.json --variant F
결과 파일은 존재하면 덮어쓰지 않는다.
"""
import argparse, hashlib, json, os, sys, time

import numpy as np

import sp75_data as D
import sp75_vlm as V
from rsna_diag import generate, lora
from rsna_diag import train as T


def pick_min_cases(man, split='T24'):
    """grade 1-5를 각각 포함하는 최소 사례: 환자 ID(정수)·ordinal 순으로 처음 나오는 grade별 1개."""
    rows = sorted([r for r in man['rows'] if r['split'] == split and not r['excluded']], key=lambda r: (int(r['patient']), r['ordinal']))
    out = {}
    for r in rows:
        out.setdefault(r['grade'], r)
    return [out[g] for g in sorted(out)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--variant', choices=['F', 'R'], default='F')
    ap.add_argument('--gpu', default=None, help='상속된 CUDA_VISIBLE_DEVICES 안의 장치만 허용')
    a = ap.parse_args()
    if a.gpu is not None:
        inh = os.environ.get('CUDA_VISIBLE_DEVICES', '').split(',')
        if a.gpu not in inh:
            sys.exit(f'gpu {a.gpu} not in inherited {inh}')
        os.environ['CUDA_VISIBLE_DEVICES'] = a.gpu
    if os.path.exists(a.out):
        sys.exit('output exists; refusing to overwrite')
    import torch
    man = D.load_manifest()
    rows = pick_min_cases(man)
    assert [r['grade'] for r in rows] == [1, 2, 3, 4, 5]
    T.seed_all(torch, 17)
    _, proc, model = generate.load_model()
    res = {'variant': a.variant, 'cases': [r['id'] for r in rows], 'grades': [r['grade'] for r in rows]}
    tok = proc.tokenizer
    prompt = V.PROMPTS[a.variant]
    exs, ims_all = [], []
    for r in rows:
        ims = V.load_images(r['inputs'][a.variant])
        ims_all.append(ims)
        ex = V.build_example(proc, ims, prompt, str(r['grade']))
        exs.append(ex)
    ex0 = exs[0]
    img_tok_id = proc.tokenizer.convert_tokens_to_ids('<image_soft_token>') if '<image_soft_token>' in tok.get_vocab() else getattr(model.config, 'image_token_id', None)
    n_img_tok = int((ex0['input_ids'] == model.config.image_token_id).sum())
    res['input'] = {'n_tokens': [int(e['input_ids'].shape[0]) for e in exs], 'pixel_values_shape': list(ex0['pixel_values'].shape), 'image_token_id': int(model.config.image_token_id),
                    'n_image_tokens_case0': n_img_tok, 'n_label_tokens': [int((e['labels'] != -100).sum()) for e in exs],
                    'label_decode': [tok.decode(e['labels'][e['labels'] != -100].tolist(), skip_special_tokens=False) for e in exs]}
    res['input']['checks'] = {'three_images_pixel_values': ex0['pixel_values'].shape[0] == 3, 'image_tokens_3x_block': n_img_tok % 3 == 0 and n_img_tok > 0,
                              'labels_digit_plus_eot': all(d == f'{r["grade"]}<end_of_turn>' for d, r in zip(res['input']['label_decode'], rows))}
    # 영상 순서: 순서를 바꾼 입력은 pixel_values 순서가 바뀌어야 한다
    swapped = build = V.build_gen_inputs(proc, [ims_all[0][2], ims_all[0][1], ims_all[0][0]], prompt)
    orig = V.build_gen_inputs(proc, ims_all[0], prompt)
    res['order'] = {'pv0_orig_eq_pv2_swapped': bool(torch.equal(orig['pixel_values'][0], swapped['pixel_values'][2])),
                    'pv0_orig_ne_pv0_swapped': not bool(torch.equal(orig['pixel_values'][0], swapped['pixel_values'][0])),
                    'text_prompt_same_ids': bool(torch.equal(orig['input_ids'], swapped['input_ids']))}
    # 전처리 대조: 공식 processor 출력 vs 직접 image_processor
    ip = proc.image_processor
    direct = ip(images=ims_all[0], return_tensors='pt')['pixel_values']
    res['processor_direct_eq_chat'] = bool(torch.equal(direct, orig['pixel_values']))
    res['processor_size'] = str(getattr(ip, 'size', None))
    res['chat_template_text_head'] = proc.apply_chat_template(V.msgs(ims_all[0], prompt, '3'), tokenize=False)[:80]

    # LoRA 이전(base) loss와 LoRA 초기 loss 대조 (항등)
    model.eval()
    b0 = V.to_cuda(V.collate([exs[2]], tok.pad_token_id))
    with torch.no_grad():
        base_chk = V.check_loss(torch, model, b0)
    res['base_loss_check'] = base_chk
    base_dg_before = lora.base_digest(model) if True else None
    names = lora.apply_lora(model, 16, 32, 0.0, seed=17)   # dropout 0: 항등 대조용
    with torch.no_grad():
        lora_chk = V.check_loss(torch, model, b0)
        lg_base = None
    res['lora_init_loss_check'] = lora_chk
    res['lora_init_identity_abs_diff'] = abs(lora_chk['official_loss'] - base_chk['official_loss'])
    res['n_lora_targets'] = len(names)
    params = list(lora.lora_params(model).values())
    res['n_trainable'] = int(sum(p.numel() for p in params))
    res['all_trainable_are_lora'] = all('lora_' in n for n, p in model.named_parameters() if p.requires_grad)
    # gradient / update
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False})
    model.config.use_cache = False
    model.train()
    snap0 = lora.lora_state_dict(model)
    grads = {}
    for mb in (1, 5):
        for p in params:
            p.grad = None
        torch.cuda.reset_peak_memory_stats()
        t0 = time.time()
        tot_tok = sum(int((e['labels'] != -100).sum()) - 0 for e in exs) - 0
        ls_tot = 0.0
        for i in range(0, 5, mb):
            b = V.to_cuda(V.collate(exs[i:i + mb], tok.pad_token_id))
            ls, n = V.loss_sum(torch, model, b)
            # labels[:,1:] 유효 수 = labels!=-100 인 위치 수 - (첫 위치 라벨 불가) -> 동일
            (ls / tot_tok).backward()
            ls_tot += float(ls)
        torch.cuda.synchronize()
        dt = time.time() - t0
        g = torch.cat([p.grad.flatten().float().cpu() for p in params])
        grads[mb] = g
        res[f'micro{mb}'] = {'loss_mean': ls_tot / tot_tok, 'grad_norm': float(g.norm()), 'finite': bool(torch.isfinite(g).all()), 'sec_5_examples': dt,
                             'peak_gb': torch.cuda.max_memory_allocated() / 2 ** 30}
    res['grad_micro1_vs_micro5_rel_diff'] = float((grads[1] - grads[5]).norm() / grads[1].norm())
    # B=0 이므로 lora_A gradient=0, lora_B gradient>0 이 정상
    gA = float(torch.cat([p.grad.flatten().float().cpu() for n, p in model.named_parameters() if 'lora_A' in n]).norm())
    res['grad_norm_lora_A_at_init'] = gA
    # update
    opt = torch.optim.AdamW(params, lr=2e-4, weight_decay=0.01)
    for p in params:
        p.grad = None
    losses = []
    for it in range(30):
        tot_l = 0.0
        for i in range(5):
            b = V.to_cuda(V.collate(exs[i:i + 1], tok.pad_token_id))
            ls, n = V.loss_sum(torch, model, b)
            (ls / tot_tok).backward()
            tot_l += float(ls)
        gn = float(torch.nn.utils.clip_grad_norm_(params, 1.0))
        opt.step(); opt.zero_grad(set_to_none=True)
        losses.append(tot_l / tot_tok)
        assert np.isfinite(gn) and np.isfinite(tot_l)
    snap1 = lora.lora_state_dict(model)
    res['update'] = {'steps': 30, 'loss_first': losses[0], 'loss_last': losses[-1], 'lora_changed': any(not torch.equal(snap0[k], snap1[k]) for k in snap0),
                     'lora_digest_before': lora.state_digest(snap0)[:16], 'lora_digest_after': lora.state_digest(snap1)[:16]}
    res['base_frozen'] = {'digest_before_lora': base_dg_before[:16], 'digest_after_train': lora.base_digest(model)[:16]}
    res['base_frozen']['equal'] = res['base_frozen']['digest_before_lora'] == res['base_frozen']['digest_after_train']
    # 생성 확인 (과적합 사례는 일반화 근거가 아님)
    model.eval(); model.config.use_cache = True
    gens = []
    for r, ims in zip(rows, ims_all):
        inp = V.build_gen_inputs(proc, ims, prompt)
        x = {k: (v.cuda().to(torch.bfloat16) if k == 'pixel_values' else v.cuda()) for k, v in inp.items()}
        with torch.no_grad():
            out = model.generate(**x, max_new_tokens=V.MAX_NEW, do_sample=False)
        txt = tok.decode(out[0, x['input_ids'].shape[1]:], skip_special_tokens=True)
        gens.append({'id': r['id'], 'grade': r['grade'], 'text': txt, 'parsed': V.parse(txt)})
    res['overfit_generation'] = gens
    res['parser_tests'] = {t: V.parse(t) for t in ['3', ' 3 ', '3.', '3..', '33', 'Grade 3', '3 4', '', '6', '0', '3\n']}
    res['gpu'] = {'cvd': os.environ.get('CUDA_VISIBLE_DEVICES'), 'uuid': str(torch.cuda.get_device_properties(0).uuid)}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(res, open(a.out, 'w'), indent=1)
    print(json.dumps({k: res[k] for k in ('input', 'order', 'processor_direct_eq_chat', 'base_loss_check', 'lora_init_identity_abs_diff', 'grad_micro1_vs_micro5_rel_diff', 'update', 'base_frozen', 'micro1', 'micro5')}, indent=1, default=str))


if __name__ == '__main__':
    main()
