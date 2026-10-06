"""enumeration.json의 후보 reference 문장을 읽기 쉽게 출력(자료 점검용, CPU). python report86_show.py <abnormal|no_abnormal> <start> <end>"""
import json
import sys

from report86_common import R86

d = json.loads((R86 / 'E/enumeration.json').read_text())['ordered_candidates']
which, a, b = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
sel = [c for c in d if c['has_abnormal_flag'] == (which == 'abnormal')][a:b]
for i, c in enumerate(sel, a):
    print(f"#{i} {c['ImageID'][:8]} prev={'Y' if c['PreviousImageID'] else 'N'}")
    for f in c['findings']:
        print(f"   [{'A' if f.get('abnormal') else 'n'}] {f['sentence_en']} | labels={f.get('labels')} loc={f.get('locations')} prog={f.get('progression')} boxes={len(f.get('boxes', []))}")
