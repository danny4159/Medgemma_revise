"""iter_094: 사례 검토용 출력. 환자별 reference atom과 가린 출력을 함께 보인다(모델·epoch 이름 비공개)."""
import json
import sys
from pathlib import Path

R=Path(__file__).resolve().parent/'results'
D=R/'iter_094/semantic/epoch1'
b=json.loads((D/'blinded.json').read_text())
refs=json.loads((R/'iter_090/semantic/V32_reference_v3.json').read_text())['rows']
lo,hi=int(sys.argv[1]),int(sys.argv[2])
for i,r in enumerate(refs[lo:hi],lo):
    print(f"## {i} {r['id'][:12]} abnormal={r['abnormal']}")
    for a in r['atoms']:
        print('  ',a['id'],a['finding'],a['polarity'],a['certainty'],a['location'],a['attributes'],'amb' if a.get('ambiguous') else '')
    for o in b['records']:
        if o['image_id']==r['id']:print('   OUT',o['blind_id'],repr(o['text']))
