"""backend별 검증 완료 후 E 판독 512건을 모델명 없는 평가 묶음으로 만든다."""
import hashlib
import json
from pathlib import Path
from report86_common import save,sha,record_digest
from report90_numeric import OUT as ORIGINAL
OUT=ORIGINAL/'recovery'

def main():
    root=OUT/'final_generation';reference=OUT/'semantic/E_reference.json'
    contract=json.loads((root/'contract.json').read_text());assert contract['reference_sha']==sha(reference)
    refs=json.loads(reference.read_text())['rows'];refby={r['id']:r for r in refs};assert len(refby)==128
    records=[];mapping={};provenance={str(root/'contract.json'):sha(root/'contract.json')}
    for name in ['R_report','G_report','base_report','CURE_report']:
        stage=root/name;files=list(stage.glob('verified_attempt*.json'));assert files
        vf=max(files,key=lambda p:int(p.stem.split('attempt')[1]));v=json.loads(vf.read_text());assert v['passed'] and v['n']==128
        for p,h in v['sources'].items():assert sha(p)==h
        provenance[str(vf)]=sha(vf)
        rows=[json.loads(s) for f in sorted(stage.glob('worker_*.jsonl')) for s in f.read_text().splitlines()]
        assert len(rows)==128 and {r['id'] for r in rows}=={i+'|report' for i in refby}
        for row in rows:
            assert record_digest(row)==row['record_digest'];iid=row['id'].removesuffix('|report')
            bid=hashlib.sha256(f'89017|E|{name}|{iid}'.encode()).hexdigest()[:16];assert bid not in mapping
            mapping[bid]=dict(stage=str(stage),id=row['id'],record_digest=row['record_digest'])
            records.append(dict(blind_id=bid,image_id=iid,text=row['text'],non_eos=not row['attempts'][-1]['ended_eos']))
    ids=list(refby);records.sort(key=lambda r:(ids.index(r['image_id']),r['blind_id']))
    dest=OUT/'semantic/E';save(dest/'private_mapping.json',mapping)
    save(dest/'blinded.json',dict(reference_sha=sha(reference),records=records,provenance=provenance,source_sha=sha(__file__)))
    for k in range(0,128,4):
        selected=refs[k:k+4];chosen={r['id'] for r in selected}
        save(dest/f'part_{k//4:02}.json',dict(references=selected,outputs=[r for r in records if r['image_id'] in chosen]))
    print('E blinded',len(refs),'patients',len(records),'reports')

if __name__=='__main__':main()
