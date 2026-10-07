"""iter_094: 신규 출력과 같은 환자·같은 문장인 저장 판정(epoch2/6)을 보여 판정 규약의 일관성을 점검한다(읽기 전용)."""
import json
from pathlib import Path

R=Path(__file__).resolve().parent/'results'
new=json.loads((R/'iter_094/semantic/epoch1/blinded.json').read_text())['records']
stored={}
for e in (2,6):
    d=R/f'iter_090/recovery/semantic/epoch{e}'
    txt={r['blind_id']:r['text'] for r in json.loads((d/'blinded.json').read_text())['records']}
    for x in json.loads((d/'eval/per_output.json').read_text()):
        stored.setdefault((x['image_id'],txt[x['blind_id']]),[]).append((e,x['condition'],x))
seen=set()
for o in new:
    k=(o['image_id'],o['text'])
    if k in seen or o['text'].startswith('No significant'):continue
    seen.add(k)
    print('##',o['image_id'][:12],repr(o['text']))
    for e,c,x in stored.get(k,[])[:2]:
        print('   stored',e,c,'matches',[(m['ref'],m['status'],m['location'],m['attributes']) for m in x['matches']],'claims',[(c_['finding'],c_['polarity'],c_['status'],c_['refs']) for c_ in x['claims']])
