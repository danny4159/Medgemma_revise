"""고정 E24 네 조건과 투자 판단을 바꾸는 R/G 사례를 가려 재점검한다."""
import json
from report90_numeric import OUT as ORIGINAL
from report86_common import save,sha
OUT=ORIGINAL/'recovery'

def main():
    stage=OUT/'semantic/E';vf=stage/'eval/verification.json';v=json.loads(vf.read_text());assert v['passed']
    for p,h in v['sources'].items():assert sha(p)==h
    per=json.loads((stage/'eval/per_output.json').read_text());by={}
    for row in per:by.setdefault(row['image_id'],{})[row['condition']]=row
    fixed=OUT/'data/E128/recheck24.json';fixed_ids={r['id'] for r in json.loads(fixed.read_text())};assert len(fixed_ids)==24
    related={}
    for iid,conditions in by.items():
        r,g=conditions['R_report'],conditions['G_report']
        rs={m['ref'] for m in r['matches'] if m['status']=='strict'};gs={m['ref'] for m in g['matches'] if m['status']=='strict'}
        reasons=[]
        if rs!=gs:reasons.append('회복 원자 집합 차이')
        if r['contradiction']!=g['contradiction']:reasons.append('명시 모순 차이')
        if r['internal_contradiction']!=g['internal_contradiction']:reasons.append('내부 모순 차이')
        if reasons:related[iid]=reasons
    reference=OUT/'semantic/E_reference.json';refs=json.loads(reference.read_text())['rows']
    raw=json.loads((stage/'blinded.json').read_text());bid={r['blind_id']:r for r in raw['records']}
    chosen=[];records=[]
    for ref in refs:
        iid=ref['id']
        if iid not in fixed_ids and iid not in related:continue
        chosen.append(ref)
        conditions=by[iid] if iid in fixed_ids else {k:by[iid][k] for k in ['R_report','G_report']}
        records.extend(bid[r['blind_id']] for r in conditions.values())
    records.sort(key=lambda r:(next(i for i,x in enumerate(refs) if x['id']==r['image_id']),r['blind_id']))
    root=OUT/'semantic/E_recheck'
    save(root/'selection.json',dict(fixed24=sorted(fixed_ids),decision_related=related,expected_blind_ids=[r['blind_id'] for r in records],
        sources={str(p):sha(p) for p in [fixed,reference,stage/'blinded.json',stage/'eval/per_output.json',vf]},source_sha=sha(__file__),
        scope='assistant 재점검. 전문의 또는 독립 평가자 합의가 아님.'))
    for k in range(0,len(chosen),4):
        group=chosen[k:k+4];ids={r['id'] for r in group}
        save(root/f'part_{k//4:02}.json',dict(references=group,outputs=[r for r in records if r['image_id'] in ids]))
    print('recheck',len(chosen),'patients',len(records),'readings; human-readable judgments still required')

if __name__=='__main__':main()
