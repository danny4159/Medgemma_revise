"""iter_078 기술 검사 (GPU 1장): Q 재현(V8 첫 4건 vs iter_077 저장 출력), I/D/L 입력 tensor 구성, 대상 tensor 불변성, EOS·메모리.
정답률은 gate가 아니다. 결과: results/iter_078/tests/tech_v2.json
"""
import json, os, sys, time

import sp75_vlm as V
import rf78_gen as G
import rf78_vlm as RV
import rf78_ref as R
from rsna_diag import generate

OUTF = 'results/iter_078/tests/tech_v2.json'
ADAPTER = 'results/iter_077/train/R_lr2e-4/epoch_16'
Q_V8 = 'results/iter_077/gen/V8/R_lr2e-4_ep16/gen_worker0.jsonl'
N = 4


def main():
    gpu = sys.argv[1]
    inh = os.environ.get('CUDA_VISIBLE_DEVICES', '').split(',')
    assert gpu in inh
    os.environ['CUDA_VISIBLE_DEVICES'] = gpu
    if os.path.exists(OUTF):
        sys.exit('exists')
    os.makedirs(os.path.dirname(OUTF), exist_ok=True)
    reqs, req_sha = G.load_requests('V8')
    reqs = reqs[:N]
    torch, proc, model = generate.load_model()
    dg = generate.load_adapter(torch, model, ADAPTER)
    env = generate.env_info(torch, proc, model)
    eos = env['eos_token_id']
    eos_ids = set(eos if isinstance(eos, list) else [eos])
    old = {json.loads(l)['id']: json.loads(l) for l in open(Q_V8)}
    res = {'adapter_digest': dg, 'expect_digest': '72417dc383a99d36b797f77d12d050124749abf370b220c70108cc51b88cfc2c', 'requests_sha256': req_sha, 'items': [], 'checks': {}}
    ok = {'adapter_digest_match': dg == res['expect_digest']}
    allq, alli, alld, alll = [], [], [], []
    for req in reqs:
        it = {'id': req['id']}
        tgt = V.load_images(req['query_images'])
        # 기존 경로(sp75_vlm.build_gen_inputs)와 새 Q 구성 대조
        old_inp = V.build_gen_inputs(proc, tgt, V.PROMPT_R)
        newq, roles_q = RV.build_inputs(proc, 'Q', None, None, tgt)
        it['Q_input_ids_equal_old_path'] = bool(torch.equal(old_inp['input_ids'], newq['input_ids']))
        it['Q_pixel_equal_old_path'] = bool(torch.equal(old_inp['pixel_values'], newq['pixel_values']))
        o = old[req['id']]
        it['old_pixel_hash_equal'] = o['input_pixel_sha256'] == [e['pixel_sha256_padded'] for e in req['query_images']]
        it['old_n_input_tokens'], it['new_n_input_tokens'] = o['n_input_tokens'], int(newq['input_ids'].shape[1])
        # Q 재생성 및 suffix 대조
        rq = G.run_one(torch, proc, model, req, 'Q', eos_ids)
        it['Q_suffix_equal_old'] = rq['suffix_ids'] == o['suffix_ids']
        it['Q_new_text'], it['Q_old_text'] = rq['text'], o['text']
        it['Q_peak_gb'] = rq['peak_mem_alloc_gb']
        # I/D/L 구조
        for cond in ('L', 'I', 'D'):
            inp, roles = G.make_inputs(proc, cond, req)
            pv = inp['pixel_values']
            n_exp = {'L': 3, 'I': 12, 'D': 12}[cond]
            c = {'n_images': int(pv.shape[0]), 'n_images_expected': n_exp, 'target_last3_pixel_equal_Q': bool(torch.equal(pv[-3:], old_inp['pixel_values'])),
                 'roles_last3_target': [r[0] for r in roles[-3:]] == ['target'] * 3, 'n_input_tokens': int(inp['input_ids'].shape[1])}
            if cond in ('I', 'D'):
                eq = []
                for j in range(3):
                    ri = V.load_images(req[cond][j]['images'])
                    single = V.build_gen_inputs(proc, ri, 'x')['pixel_values']
                    eq.append(bool(torch.equal(pv[3 * j:3 * j + 3], single)))
                c['ref_blocks_pixel_equal_single'] = eq
                c['ref_ids'] = [r['ref_id'] for r in req[cond]]
                c['ref_grades'] = [r['grade'] for r in req[cond]]
            else:
                c['ref_grades'] = [r['grade'] for r in req['I']]
            r1 = G.run_one(torch, proc, model, req, cond, eos_ids)
            c.update({'text': r1['text'], 'ended_eos': r1['ended_eos'], 'parse_valid': r1['parse_valid'], 'peak_alloc_gb': r1['peak_mem_alloc_gb'],
                      'peak_reserved_gb': r1['peak_mem_reserved_gb'], 'runtime_s': r1['runtime_s']})
            it[cond] = c
            if cond == 'I' and req is reqs[0]:
                it['I_prompt_decoded'] = proc.tokenizer.decode(inp['input_ids'][0].tolist(), skip_special_tokens=False)[:6000]
                it['L_prompt_note'] = 'see below'
            if cond == 'L' and req is reqs[0]:
                it['L_prompt_decoded'] = proc.tokenizer.decode(inp['input_ids'][0].tolist(), skip_special_tokens=False)[:3000]
        res['items'].append(it)
        allq.append(it['Q_suffix_equal_old'] and it['Q_input_ids_equal_old_path'] and it['Q_pixel_equal_old_path'] and it['old_pixel_hash_equal'] and it['old_n_input_tokens'] == it['new_n_input_tokens'])
        alli.append(all(it['I']['ref_blocks_pixel_equal_single']) and it['I']['target_last3_pixel_equal_Q'] and it['I']['n_images'] == 12 and it['I']['ended_eos'])
        alld.append(all(it['D']['ref_blocks_pixel_equal_single']) and it['D']['target_last3_pixel_equal_Q'] and it['D']['n_images'] == 12 and it['D']['ended_eos'])
        alll.append(it['L']['target_last3_pixel_equal_Q'] and it['L']['n_images'] == 3 and it['L']['ended_eos'])
    ok.update({'Q_reproduces_old_V8_first4': all(allq), 'I_structure_ok': all(alli), 'D_structure_ok': all(alld), 'L_structure_ok': all(alll)})
    res['checks'] = ok
    res['max_peak_alloc_gb_I'] = max(i['I']['peak_alloc_gb'] for i in res['items'])
    res['max_peak_reserved_gb_I'] = max(i['I']['peak_reserved_gb'] for i in res['items'])
    json.dump(res, open(OUTF, 'w'), indent=1)
    print(json.dumps(ok), res['max_peak_alloc_gb_I'], res['max_peak_reserved_gb_I'])


if __name__ == '__main__':
    main()
