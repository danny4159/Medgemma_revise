"""iter_094: 일반 정상문의 저장 판정 규약을 환자 유형별로 확인(읽기 전용)."""
import json
import sys
from pathlib import Path

R=Path(__file__).resolve().parent/'results'
refs=json.loads((R/'iter_090/semantic/V32_reference_v3.json').read_text())['rows']
want=[refs[int(i)]['id'] for i in sys.argv[1:]]
for e in (6,):
    d=R/f'iter_090/recovery/semantic/epoch{e}'
    txt={r['blind_id']:r['text'] for r in json.loads((d/'blinded.json').read_text())['records']}
    for x in json.loads((d/'eval/per_output.json').read_text()):
        if x['image_id'] in want and x['condition'].endswith('lr0.0002_report') and txt[x['blind_id']].startswith('No significant'):
            print(refs.index(next(r for r in refs if r['id']==x['image_id'])),x['condition'],repr(txt[x['blind_id']]),
                  [(c['finding'],c['polarity'],c['status'],c['refs']) for c in x['claims']],'contra',x['contradiction'])
