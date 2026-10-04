"""비용 측정 프로세스의 답변이 평가 경로의 출력과 같은지 확인. 사용: python g71_costcheck.py det|vlm COST_DIR [GEN_DIR_for_vlm]"""
import json, sys

import numpy as np

import g71_det_stage as DS
import g71_eval as E

kind, cdir = sys.argv[1], sys.argv[2]
ans = json.load(open(f'{cdir}/answers.json'))
if kind == 'det':
    lock = json.load(open('results/iter_071/decide/e24_lock.json'))
    pj = json.load(open('results/iter_071/det/T8_lr0.005/infer_V8_e16.json'))
    items, _ = DS.preds_to_items(pj, 'V8', 0.85)
    mx, n = 0.0, 0
    for i, (st, bx) in items.items():
        a = ans[i]['boxes']
        assert len(a) == len(bx), f'box count differs for {i}'
        for u, v in zip(a, bx):
            mx = max(mx, max(abs(p - q) for p, q in zip(u, v)))
        n += 1
    print('items', n, 'max box coordinate diff (norm 0-1000 units)', mx)
else:
    recs = {r['id']: r for r in E.read_jsonl_dir(sys.argv[3])}
    same = sum(1 for i, a in ans.items() if recs[i]['suffix_ids'] == a['suffix_ids'])
    print('items', len(ans), 'identical greedy token sequences', same)
