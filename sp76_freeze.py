"""iter_076 동결 검사 (GPU 1장): LoRA parameter 객체와 비LoRA parameter를 정확히 분리하고 실제 update 전후 전체 byte digest를 비교한다.

PASS 조건(모두): 이름 정규화 충돌 없음, 비LoRA/LoRA parameter 수·numel·byte > 0, 비LoRA requires_grad=0, optimizer가 LoRA 전체만 포함(비LoRA 0),
3회 실제 optimizer update 후 비LoRA exact digest 불변 + LoRA digest 변화 + LoRA parameter 일부 값 변화, 이전 base_digest(정규화 이름) 도 불변.
또 iter_075 tech_F.json의 base_frozen digest(e3e19f4387647450)가 표준 빈 입력 SHA256(e3b0c44298fc1c14...)이 아님을 대조하고 현재 정확한 parameter 집합·byte 수를 기록한다.
결과 파일이 존재하면 중단. 실패(FAIL)이면 비정상 종료.
사용: python sp76_freeze.py --out results/iter_076/tests/freeze_check.json --gpu 0
"""
import argparse, hashlib, json, os, sys

import sp75_data as D
import sp75_vlm as V
from rsna_diag import generate, lora
from rsna_diag import train as T


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--gpu', default=None)
    a = ap.parse_args()
    if a.gpu is not None:
        inh = os.environ.get('CUDA_VISIBLE_DEVICES', '').split(',')
        if a.gpu not in inh:
            sys.exit(f'gpu {a.gpu} not in inherited {inh}')
        os.environ['CUDA_VISIBLE_DEVICES'] = a.gpu
    if os.path.exists(a.out):
        sys.exit('exists')
    import torch
    T.seed_all(torch, 17)
    man = D.load_manifest()
    rows = sorted([r for r in man['rows'] if r['split'] == 'T24' and r['position_set'] == 'supervised' and not r['excluded']], key=lambda r: (int(r['patient']), r['ordinal']))[:2]
    _, proc, model = generate.load_model()
    res = {'empty_sha256': hashlib.sha256(b'').hexdigest()}
    base_pre = lora.base_digest(model)
    res['iter075_style_base_digest_prefix'] = base_pre[:16]
    res['iter075_digest_equals_empty_input_sha256'] = base_pre == res['empty_sha256']
    res['iter075_recorded_digest_prefix_e3e19f4387647450_matches_now'] = base_pre[:16] == 'e3e19f4387647450'
    names = lora.apply_lora(model, 16, 32, 0.0, seed=17)
    params = list(lora.lora_params(model).values())
    opt = torch.optim.AdamW(params, lr=2e-4, weight_decay=0.01)
    res['split'] = lora.split_report(model, params)
    res['n_lora_targets'] = len(names)
    n0, c0, b0 = lora.exact_digest(model)
    l0, lc0, lb0 = lora.exact_digest(model, lora=True)
    res['non_lora'] = {'digest_before': n0[:16], 'n_params': c0, 'n_bytes': b0}
    res['lora_before'] = {'digest': l0[:16], 'n_params': lc0, 'n_bytes': lb0}
    snap0 = lora.lora_state_dict(model)
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False})
    model.config.use_cache = False
    model.train()
    losses = []
    for it in range(3):
        for r in rows:
            ex = V.build_example(proc, V.load_images(r['inputs']['F']), V.PROMPTS['F'], str(r['grade']))
            ls, n = V.loss_sum(torch, model, V.to_cuda(V.collate([ex], proc.tokenizer.pad_token_id)))
            (ls / (2 * len(rows))).backward()
            losses.append(float(ls) / n)
        gn = float(torch.nn.utils.clip_grad_norm_(params, 1.0))
        assert gn == gn and gn < float('inf')
        opt.step()
        opt.zero_grad(set_to_none=True)
    n1, c1, b1 = lora.exact_digest(model)
    l1, _, _ = lora.exact_digest(model, lora=True)
    snap1 = lora.lora_state_dict(model)
    res['non_lora']['digest_after'] = n1[:16]
    res['non_lora']['unchanged'] = n1 == n0 and (c1, b1) == (c0, b0)
    res['lora_after'] = {'digest': l1[:16], 'changed': l1 != l0, 'n_tensors_changed': sum(1 for k in snap0 if not torch.equal(snap0[k], snap1[k]))}
    base_post = lora.base_digest(model)
    res['iter075_style_base_digest_unchanged_after_lora_and_updates'] = base_pre == base_post
    res['losses'] = losses
    sp = res['split']
    res['checks'] = {'counts_positive': all(sp[k] > 0 for k in ('n_lora', 'n_non_lora', 'numel_lora', 'numel_non_lora', 'bytes_lora', 'bytes_non_lora')),
                     'non_lora_requires_grad_zero': sp['non_lora_requires_grad'] == 0 and sp['lora_requires_grad_false'] == 0,
                     'optimizer_only_lora': sp['optimizer_contains_non_lora'] == 0 and sp['optimizer_lora_covered'] and sp['optimizer_n_params'] == sp['n_lora'],
                     'non_lora_exact_digest_unchanged': res['non_lora']['unchanged'], 'lora_changed': res['lora_after']['changed'] and res['lora_after']['n_tensors_changed'] > 0,
                     'iter075_style_digest_unchanged': res['iter075_style_base_digest_unchanged_after_lora_and_updates'],
                     'finite_losses': all(x == x and abs(x) < 1e6 for x in losses)}
    res['PASS'] = all(res['checks'].values())
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    tmp = a.out + '.tmp'
    json.dump(res, open(tmp, 'w'), indent=1)
    os.replace(tmp, a.out)
    print(json.dumps({'PASS': res['PASS'], 'checks': res['checks'], 'split': sp, 'non_lora': res['non_lora'], 'e3e19f_vs_empty': [res['iter075_digest_equals_empty_input_sha256'],
                                                                                                                                res['iter075_recorded_digest_prefix_e3e19f4387647450_matches_now']]}, indent=1))
    sys.exit(0 if res['PASS'] else 1)


if __name__ == '__main__':
    main()
