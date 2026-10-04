"""미완료 V4 gen 디렉터리의 F1@0.5 상한(미생성 항목을 모두 1.0으로 가정)과 현재 status를 출력. 사용: python g71_bound.py GEN_DIR"""
import sys

import numpy as np

import g71_eval as E
import g71_train as TR

rows = {r['id']: r for r in TR.load_items('V4')}
by = {r['id']: r for r in E.read_jsonl_dir(sys.argv[1])}
sc = {}
for i, row in rows.items():
    if i in by:
        st, b = E.parse_record(by[i], row['category'])
        sc[i] = E.score_item(st, b, [g['yxyx_norm'] for g in row['gt']])
    else:
        sc[i] = {'f1@0.5': 1.0, 'status': 'MISSING'}
pats = sorted({r['patient'] for r in rows.values()}, key=int)
print(len(by), 'upper bound', float(np.mean(list(E.per_patient(sc, pats).values()))))
print([sc[i]['status'] for i in by])
