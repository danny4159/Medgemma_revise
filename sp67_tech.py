"""iter_067 기술 검사(D): 후보 단일 token, forward vs generate 첫 단계 logits, 조건 간 영상 tensor 동일성, 최대 stack 메모리.
사용: CUDA_VISIBLE_DEVICES=<gpu> python sp67_tech.py <model> <requests> <out.json>"""
import json, sys
import numpy as np
import m65_run as M65
import sp67_run as R


def main():
    model, req, out = sys.argv[1:4]
    rows = M65.read_jsonl(req)
    torch, proc, m = M65.load_model(model)
    cids = R.cand_ids(proc)
    R.patch_vision(model, m)
    res = {'model': model, 'cand_ids': cids, 'cand_tokens': [proc.tokenizer.decode([c]) for c in cids], 'env': M65.env_info(model, torch, proc, m)}
    by = {}
    for r in rows:
        by.setdefault((r['patient'], r['ivd']), {})[r['cond']] = r
    # 1) 영상 tensor 동일성: S1/S2 영상 sha가 J의 앞/뒤 부분과 같은가 (환자·IVD 대표 6개 + 최대 stack)
    keys = sorted(by)[:: max(1, len(by) // 6)][:6]
    mx = max(by, key=lambda k: by[k]['J']['images'].__len__())
    if mx not in keys:
        keys.append(mx)
    eq = []
    for k in keys:
        g = by[k]
        s1 = M65.per_image_pixels(model, M65.build_inputs(model, proc, g['S1']))[0]
        s2 = M65.per_image_pixels(model, M65.build_inputs(model, proc, g['S2']))[0]
        j = M65.per_image_pixels(model, M65.build_inputs(model, proc, g['J']))[0]
        eq.append({'key': list(k), 'n1': len(s1), 'n2': len(s2), 'S1_eq_J_head': s1 == j[:len(s1)], 'S2_eq_J_tail': s2 == j[len(s1):], 'n_J': len(j)})
    res['tensor_equality'] = eq
    # 1b) vision chunk 동등성 (영상 수 <=24 요청에서 chunk 8 vs 24)
    small = min(by, key=lambda k: len(by[k]['J']['images']))
    row = by[small]['J']
    R.patch_vision(model, m, 8); a8 = R.score_one(model, torch, proc, m, cids, row)
    R.patch_vision(model, m, 64); a64 = R.score_one(model, torch, proc, m, cids, row)
    R.patch_vision(model, m, 8)
    res['chunk_equivalence'] = {'rid': row['rid'], 'n_images': len(row['images']), 'max_logit_diff': max(abs(x - y) for x, y in zip(a8['cand_logits'], a64['cand_logits'])),
                                'pred_equal': a8['pred'] == a64['pred']}
    # 2) forward vs generate 첫 단계
    cmp = []
    for k in keys:
        for c in ('S1', 'J', 'T'):
            row = by[k][c]
            rec = R.score_one(model, torch, proc, m, cids, row)
            inp = M65.build_inputs(model, proc, row)
            x = R.to_dev(torch, inp)
            with torch.no_grad():
                g = m.generate(**x, max_new_tokens=1, do_sample=False, output_scores=True, return_dict_in_generate=True)
            gl = g.scores[0][0].float()[cids].cpu()
            fl = torch.tensor(rec['cand_logits'])
            gp = torch.softmax(gl, -1); fp = torch.softmax(fl, -1)
            cmp.append({'rid': row['rid'], 'max_prob_diff': float((gp - fp).abs().max()), 'max_logit_diff': float((gl - fl).abs().max()),
                        'pred_equal': int(gp.argmax()) == int(fp.argmax()), 'gen_token_id': int(g.sequences[0, -1]), 'fwd_top_id': rec['top_token_id'],
                        'n_images': rec['n_images'], 'n_input_tokens': rec['n_input_tokens'], 'peak_alloc_gb': rec['peak_alloc_gb'], 'peak_reserved_gb': rec['peak_reserved_gb'],
                        't_forward_s': rec['t_forward_s'], 't_total_s': rec['t_total_s']})
    res['forward_vs_generate'] = cmp
    res['ok'] = (all(e['S1_eq_J_head'] and e['S2_eq_J_tail'] for e in eq) and all(c['max_prob_diff'] <= 1e-3 and c['pred_equal'] for c in cmp))
    import os
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(res, open(out, 'w'), indent=1)
    print('ok', res['ok'], 'max_prob_diff', max(c['max_prob_diff'] for c in cmp), 'peak_reserved', max(c['peak_reserved_gb'] for c in cmp))


if __name__ == '__main__':
    main()
