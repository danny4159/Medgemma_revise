"""완료 판독을 조건명 없는 평가 ID로 연결한다. 모델 이름은 별도 mapping에 둔다."""
import argparse
import hashlib
import json
from pathlib import Path
from report90_numeric import OUT as ORIGINAL
OUT=ORIGINAL/'recovery'
from report86_common import save,sha
import report90_recovery_gen as S

def main(epoch):
    root=OUT/f'validation/epoch{epoch}';req=ORIGINAL/'data/V32/requests.json'
    names=(['base_report'] if epoch==2 else [])+[f'{m}_lr{lr:g}_report' for lr in (.0001,.0002) for m in ('R','G')]
    if epoch>=8:
        decision=json.loads((OUT/'decisions/expand_epoch12.json').read_text());assert decision['expand']
        names=[f'{m}_lr{lr:g}_report' for m,lr in decision['selected_lrs'].items()]
    refs=json.loads((ORIGINAL/'semantic/V32_reference_v3.json').read_text())['rows'];refby={r['id']:r for r in refs}
    mapping={};records=[];provenance={}
    for name in names:
        stage=root/name;proto=json.loads((stage/'protocol.json').read_text());w=json.loads((stage/'mapping.json').read_text())['workers']
        rows,expected=S.verify(stage,req,proto,w);assert len(rows)==32 and (stage/'completion.json').exists()
        provenance[str(stage/'completion.json')]=sha(stage/'completion.json')
        for row in rows:
            img=row['id'].removesuffix('|report');assert img in refby
            blind=hashlib.sha256(f'89017|{epoch}|{name}|{img}'.encode()).hexdigest()[:16];assert blind not in mapping
            mapping[blind]=dict(stage=str(stage),id=row['id'],record_digest=row['record_digest'])
            records.append(dict(blind_id=blind,image_id=img,text=row['text'],non_eos=not row['attempts'][-1]['ended_eos']))
    records.sort(key=lambda r:(list(refby).index(r['image_id']),r['blind_id']))
    dest=OUT/f'semantic/epoch{epoch}';save(dest/'private_mapping.json',mapping)
    save(dest/'blinded.json',dict(reference_sha=sha(ORIGINAL/'semantic/V32_reference_v3.json'),records=records,provenance=provenance,source_sha=sha(__file__)))
    for k in range(0,32,4):
        selected=refs[k:k+4];ids={r['id'] for r in selected};save(dest/f'part_{k//4:02}.json',dict(references=selected,outputs=[r for r in records if r['image_id'] in ids]))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--epoch',type=int,required=True);main(p.parse_args().epoch)
