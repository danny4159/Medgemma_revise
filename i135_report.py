"""iter_135: 감사 산출물 요약 출력 + followup_feasibility 작성 (읽기 전용 집계)."""
import json, collections
from pathlib import Path

O = Path('results/iter_135')
e = json.load(open(O / 'data_evidence.json'))
a = json.load(open(O / 'output_structure_audit.json'))
c = json.load(open(O / 'contradiction_candidates.json'))
print(e['n_cases'], e['n_technical'], e['n_main'])
print(json.dumps(e['linkage'], ensure_ascii=False, indent=1)[:2500])
print(e['mirror']['revision'], e['radgenome']['revision'])
for j in a:
    print(j, a[j]['n'], a[j]['totals'])
    for k, v in a[j]['by_condition'].items():
        print(' ', k, v)
print(collections.Counter((x['job'], x['id'].split('__')[1], x['strict_state']) for x in c))
