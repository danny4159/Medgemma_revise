"""긴 응답 생성 중 이미 검증된 공통 prefix를 가려 의미 평가를 병행한다."""
import hashlib
import json
import time
from report90_numeric import OUT as ORIGINAL
from report86_common import save,sha
import report90_recovery_gen as S

def main():
    root=ORIGINAL/'recovery';stage=root/'validation/epoch2'
    refs=json.loads((ORIGINAL/'semantic/V32_reference_v3.json').read_text())['rows']
    records=[];by=[];digests={}
    for name in ['base_report']+[f'{m}_lr{lr:g}_report' for lr in (.0001,.0002) for m in ('R','G')]:
        p=stage/name;proto=json.loads((p/'protocol.json').read_text())
        rows,expected=S.verify(p,ORIGINAL/'data/V32/requests.json',proto,1)
        by.append((name,{r['id'].removesuffix('|report'):r for r in rows}))
    chosen=[]
    for ref in refs:
        if not all(ref['id'] in rows for _,rows in by):break
        chosen.append(ref)
    assert chosen
    for name,rows in by:
        for ref in chosen:
            r=rows[ref['id']];bid=hashlib.sha256(f'89017|2|{name}|{ref["id"]}'.encode()).hexdigest()[:16]
            records.append(dict(blind_id=bid,image_id=ref['id'],text=r['text'],non_eos=not r['attempts'][-1]['ended_eos']))
            digests[bid]=r['record_digest']
    records.sort(key=lambda r:(next(i for i,x in enumerate(refs) if x['id']==r['image_id']),r['blind_id']))
    dest=root/'semantic/epoch2_early'
    save(dest/'snapshot.json',dict(reference_sha=sha(ORIGINAL/'semantic/V32_reference_v3.json'),records=records,record_digests=digests,source_sha=sha(__file__),start_time=time.time(),scope='부분 출력 검증과 평가 초안; 전체 완료/평가 승인이 아님'))
    for k in range(0,len(chosen),4):
        selected=chosen[k:k+4];ids={r['id'] for r in selected}
        save(dest/f'part_{k//4:02}.json',dict(references=selected,outputs=[r for r in records if r['image_id'] in ids]))
    print('검증된 공통 prefix',len(chosen),'명',len(records),'판독; 최종 병합 때 원문 동일성 재확인 필수')

if __name__=='__main__':main()
