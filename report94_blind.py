"""iter_094: 신규 epoch1 R/G 64건을 조건명 없는 평가 ID로 연결(report90_recovery_blind의 형식 유지, 새 경로)."""
import hashlib
import json
from pathlib import Path
from report86_common import save,sha,sha_obj,record_digest

ROOT=Path(__file__).resolve().parent
R=ROOT/'results'
OUT=R/'iter_094/semantic/epoch1'
REF=R/'iter_090/semantic/V32_reference_v3.json'

def main():
    refs=json.loads(REF.read_text())['rows'];refby={r['id']:r for r in refs}
    mapping={};records=[];prov={}
    for m in 'RG':
        stage=R/f'iter_094/gen/{m}_epoch1'
        prov[str(stage/'completion.json')]=sha(stage/'completion.json')
        for line in (stage/'worker_0.jsonl').read_text().splitlines():
            row=json.loads(line);img=row['id'].removesuffix('|report');assert img in refby and row['record_digest']==record_digest(row)
            blind=hashlib.sha256(f'94017|1|{m}_lr0.0002_report|{img}'.encode()).hexdigest()[:16];assert blind not in mapping
            mapping[blind]=dict(stage=str(stage),id=row['id'],record_digest=row['record_digest'])
            records.append(dict(blind_id=blind,image_id=img,text=row['text'],non_eos=not row['attempts'][-1]['ended_eos']))
    records.sort(key=lambda r:(list(refby).index(r['image_id']),r['blind_id']))
    save(OUT/'private_mapping.json',mapping)
    save(OUT/'blinded.json',dict(reference_sha=sha(REF),records=records,provenance=prov,source_sha=sha(__file__)))
    for k in range(0,32,4):
        selected=refs[k:k+4];ids={r['id'] for r in selected};save(OUT/f'part_{k//4:02}.json',dict(references=selected,outputs=[r for r in records if r['image_id'] in ids]))

if __name__=='__main__':
    main()
