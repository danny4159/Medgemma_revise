"""iter_125: batch x 후보라벨 층별 SHA256(seed125|patient) 순서 고정 후, 검토용 문장 출력. usage: python mr125_order.py N"""
import hashlib, json, sys

N = int(sys.argv[1]) if len(sys.argv) > 1 else 22
C = json.load(open('results/iter_125/data/candidates_raw.json'))
order = {}
for c in C:
    if c['pos'] and not c['neg']:
        lab = 'positive'
    elif c['neg'] and not c['pos']:
        lab = 'negative'
    else:
        continue
    c['cand_label'] = lab
    c['h'] = hashlib.sha256(f'125|{c["patient_uid"]}'.encode()).hexdigest()
    order.setdefault((c['batch_id'], lab), []).append(c)
res = {}
for k, v in sorted(order.items()):
    v.sort(key=lambda c: c['h'])
    res['|'.join(k)] = v
json.dump(res, open('results/iter_125/data/ordered_candidates.json', 'w'), indent=1)
S0 = int(sys.argv[2]) if len(sys.argv) > 2 else 0
ONLY = sys.argv[3] if len(sys.argv) > 3 else ''
for k, v in res.items():
    if ONLY not in k:
        continue
    print('=====', k, len(v))
    for i, c in enumerate(v[:N]):
        if i < S0:
            continue
        print(f'[{i}] {c["patient_uid"]} {c["study_uid"]} {c["series_id"]} {c["array_shape"]}')
        for sec, s in c['hits']:
            print('   ', sec[:3], s[:300])
