"""detector E24 점수의 독립 재계산(g71_det_stage/det_match를 쓰지 않음): 원시 후보 json -> score>=thr, label 분리, pixel->padded 정규화 좌표, Kuhn matching F1.
사용: python g71_verify_det.py INFER_JSON KEY THR OUT.json"""
import json, sys

import numpy as np

import g71_data as D
import g71_train as TR
from g71_verify import f1, tp_scipy

pj, key, thr, out = json.load(open(sys.argv[1])), sys.argv[2], float(sys.argv[3]), sys.argv[4]
rows = TR.load_items(key)
per = {'0.5': {}, '0.3': {}}
for r in rows:
    p = pj['preds'][f"{r['patient']}_{D.OFF_NAME[r['offset']]}"]
    h, w = p['img_hw']
    side = max(h, w)
    top = (side - h) // 2 if h < w else 0
    left = (side - w) // 2 if w < h else 0
    lab = 1 if r['category'] == 'vertebra' else 2
    pred = []
    for b, s, l in zip(p['boxes_xyxy_px'], p['scores'], p['labels']):
        if l == lab and s >= thr:
            pred.append([(b[1] + top) * 1000.0 / side, (b[0] + left) * 1000.0 / side, (b[3] + top) * 1000.0 / side, (b[2] + left) * 1000.0 / side])
    gt = [g['yxyx_norm'] for g in r['gt']]
    for t in (0.5, 0.3):
        per[str(t)].setdefault(r['patient'], []).append(f1(tp_scipy(pred, gt, t), len(pred), len(gt)))
ind = {t: {p: float(np.mean(v)) for p, v in d.items()} for t, d in per.items()}
rep = json.load(open('results/iter_071/eval/E24_per_patient.json')) if key == 'E24' else None
res = {'indep_mean_f1@0.5': float(np.mean(list(ind['0.5'].values()))), 'indep_mean_f1@0.3': float(np.mean(list(ind['0.3'].values())))}
if rep:
    pats = rep['M8']['patients']
    res['max_abs_diff_vs_report'] = {t: max(abs(ind[t[-3:]][p] - v) for p, v in zip(pats, rep['M8'][f'f1@{t[-3:]}'])) for t in ('f1@0.5', 'f1@0.3')}
json.dump(res, open(out, 'w'), indent=1)
print(res)
