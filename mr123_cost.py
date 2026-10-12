"""iter_123: 전처리 비용(NIfTI 읽기→slice 렌더링, 저장 제외) 측정 + 생성 비용 요약. 결과: results/iter_123/eval/cost.json"""
import glob, json, os, time
import numpy as np
import mr123_data as D
import mr123_run as R

b = {}
for p in ['build_tech.json', 'build_explore.json']:
    b.update(json.load(open(D.RES + 'data/' + p)))
rows = []
for sid, info in b.items():
    if info.get('exclude') is not None:
        continue
    t0 = time.perf_counter()
    a, m, li = D.load_case(info['files']['img.nii.gz']['path'], info['files']['brain.nii.gz']['path'])
    lo, hi = D.brain_range(m)
    lv, hv = D.intensity_window(a, m)
    t1 = time.perf_counter()
    ks = sorted(set(info['W_idx']) | set(info['C_idx']))
    for k in ks:
        D.render_slice(a, k, lv, hv, li['canon_zooms'])
    t2 = time.perf_counter()
    rows.append(dict(study=sid, role=info['role'], read_s=t1 - t0, render_s=t2 - t1, n_slices_rendered=len(ks)))
rs = [r for r in rows if r['role'] == 'explore']
gen = {}
for st in ['explore']:
    recs = [r for fn in glob.glob(R.GEN + st + '/worker_*.jsonl') for r in R.read_jsonl(fn)]
    gen = dict(n=len(recs), sum_prep_s=sum(r['prep_s'] for r in recs), sum_gen_s=sum(r['gen_s'] for r in recs), model_load_s=sorted({round(r['load_s'], 1) for r in recs}),
               peak_mem_mib=max(r['peak_mem_mib'] for r in recs))
out = dict(preprocess_explore=dict(n=len(rs), mean_read_s=float(np.mean([r['read_s'] for r in rs])), mean_render_s=float(np.mean([r['render_s'] for r in rs]))),
           note='원 NIfTI 압축 해제 후 읽기→C/W 공통 slice 렌더링(저장 제외). ZIP 추출·PNG 저장·model load는 별도. 한 환자에서 C·W·P는 동일 PNG 재사용.',
           generation=gen, per_case=rows)
json.dump(out, open(D.RES + 'eval/cost.json', 'w'), indent=1)
print(json.dumps({k: v for k, v in out.items() if k != 'per_case'}, indent=1))
