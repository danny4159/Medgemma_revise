"""iter_095 보고용 요약 출력(읽기 전용)."""
import glob
import json

r = json.load(open('results/iter_095/eval/report_E32_v2.json'))
for k, v in r['compare'].items():
    if k.startswith('recall'):
        print(k, v and (round(v['mean'], 3), [round(x, 3) for x in v['ci95']]))
for b, v in r['bundles'].items():
    print(b, v['n_requests'], v['tokens_last_attempt'], round(v['generation_seconds_sum']),
          {k: round(x, 3) for k, x in v.items() if k.startswith('recall') or k.startswith('facts')})
print('coords', r['describe_spontaneous_coords'])
d = json.load(open('results/iter_095/tests/d8_check.json'))
print(d['w4']['req_per_min_generation_window'], d['w2']['req_per_min_generation_window'], d['w4']['smi_max_used_mib_per_gpu'])
for f in glob.glob('results/iter_095/launches/e32*/launch_result.json'):
    dd = json.load(open(f))
    print(dd['wall_s'], dd['returncodes'])
mx = {}
for l in open(glob.glob('results/iter_095/launches/e32*/resource.jsonl')[0]):
    for g, (u, t) in json.loads(l)['smi'].items():
        mx[g] = max(mx.get(g, 0), u)
print(mx)
