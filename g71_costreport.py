"""paired 비용 보고: block별 det/vlm 시간 비율(적재 포함·상주), 방향 일관성, VLM 답변 token 재현율. 결과: results/iter_071/eval/cost_report.json"""
import json

import numpy as np

import g71_eval as E

root = 'results/iter_071/cost'
rows = []
for b in (1, 2, 3, 4):
    v = json.load(open(f'{root}/block{b}_vlm/timing.json'))
    d = json.load(open(f'{root}/block{b}_det/timing.json'))
    rows.append({'block': b, 'gpu_env': v['gpu_env'], 'order': 'vlm->det' if b % 2 == 1 else 'det->vlm', 'vlm_total_s': v['t_total_incl_load'], 'det_total_s': d['t_total_incl_load'],
                 'ratio_total_det_over_vlm': d['t_total_incl_load'] / v['t_total_incl_load'], 'vlm_resident_s': v['t_resident'], 'det_resident_s': d['t_resident'],
                 'ratio_resident': d['t_resident'] / v['t_resident'], 'vlm_load_s': v['t_load_model'], 'det_load_s': d['t_load_model'], 'vlm_infer_s': v['t_infer'], 'det_infer_s': d['t_infer'],
                 'vlm_read_render_s': v['t_read_render'], 'det_read_render_s': d['t_read_render'], 'vlm_peak_gb': v['peak_gb'], 'det_peak_gb': d['peak_gb']})
ref = {r['id']: r for r in E.read_jsonl_dir('results/iter_071/gen/V8/T8_D_lr2e-4_e4')}
tok = []
for b in (1, 2, 3, 4):
    ans = json.load(open(f'{root}/block{b}_vlm/answers.json'))
    tok.append(sum(1 for i, a in ans.items() if ref[i]['suffix_ids'] == a['suffix_ids']) / len(ans))
rep = {'blocks': rows, 'ratio_total_range': [min(r['ratio_total_det_over_vlm'] for r in rows), max(r['ratio_total_det_over_vlm'] for r in rows)],
       'ratio_resident_range': [min(r['ratio_resident'] for r in rows), max(r['ratio_resident'] for r in rows)], 'all_blocks_det_cheaper': all(r['ratio_total_det_over_vlm'] < 1 for r in rows),
       'vlm_token_identical_fraction_vs_V8_run': tok, 'workload': '8 V8 patients x 3 slices x 2 queries = 48 requests; read T2 -> render PNG -> infer -> save answers; mask not read',
       'note': 'one process per block; both GPUs ran one block concurrently (GPU0 blocks 1,3; GPU1 blocks 2,4); det and vlm of a block sequential on the same GPU with alternating order'}
json.dump(rep, open('results/iter_071/eval/cost_report.json', 'w'), indent=1)
for r in rows:
    print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items() if k in ('block', 'gpu_env', 'order', 'vlm_total_s', 'det_total_s', 'ratio_total_det_over_vlm', 'ratio_resident', 'vlm_resident_s', 'det_resident_s', 'vlm_peak_gb', 'det_peak_gb')})
print(rep['ratio_total_range'], rep['ratio_resident_range'], tok)
