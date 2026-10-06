"""분류 결과 점검용 출력(자료 점검, CPU). python report86_facts_show.py <abnormal|no_abnormal> <start> <end> [only_nondef]"""
import json
import sys
from collections import Counter

from report86_common import R86
import report86_facts as F

d = json.loads((R86 / 'E/enumeration.json').read_text())['ordered_candidates']
which, a, b = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
only = len(sys.argv) > 4
sel = [c for c in d if c['has_abnormal_flag'] == (which == 'abnormal')]
cnt = Counter()
elig = 0
for i, c in enumerate(sel):
    fx = F.facts_for(c)
    ok = F.eligible_abnormal(fx)
    elig += ok
    for x in fx:
        cnt[x['fact_class']] += 1
    if a <= i < b:
        for x in fx:
            if only and x['fact_class'] in ('pos_def', 'generic_normal'):
                continue
            print(f"#{i} {c['ImageID'][:8]} {x['fact_id']} {x['fact_class']:14s} {x['sentence_en'][:100]} | {x['class_reason']}")
print('class counts', dict(cnt), 'eligible_abnormal', elig, 'of', len(sel))
