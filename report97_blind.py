"""iter_097: 완료 판독을 조건명 없는 ID로 연결한다. 모델/조건 이름은 private_mapping에만 둔다.
각 stage는 completion과 요청·protocol 검증(report90_gen_safe.verify)을 통과해야 한다."""
import argparse
import hashlib
import json
from pathlib import Path
import report90_gen as C
import report90_recovery_gen as S
from report86_common import save,sha
from report97_train import OUT,ORIGINAL

BASE_SOURCES=list(C.SOURCES)  # 이전 iter 생성 stage의 protocol 코드 목록

def main(a):
    req=ORIGINAL/'data/V32/requests.json';refpath=ORIGINAL/'semantic/V32_reference_v3.json'
    refs=json.loads(refpath.read_text())['rows'];refby={r['id']:r for r in refs}
    mapping={};records=[];provenance={}
    for stage in [Path(x).resolve() for x in a.stages]:
        C.SOURCES=BASE_SOURCES+(['report97_gen.py'] if OUT in stage.resolve().parents else [])
        proto=json.loads((stage/'protocol.json').read_text());w=json.loads((stage/'mapping.json').read_text())['workers']
        rows,expected=S.verify(stage,req,proto,w);assert len(rows)==len(expected)==32 and (stage/'completion.json').exists()
        provenance[str(stage/'completion.json')]=sha(stage/'completion.json')
        for row in rows:
            img=row['id'].removesuffix('|report');assert img in refby
            blind=hashlib.sha256(f'97017|{a.name}|{stage.name}|{img}'.encode()).hexdigest()[:16];assert blind not in mapping
            mapping[blind]=dict(stage=str(stage),id=row['id'],record_digest=row['record_digest'])
            records.append(dict(blind_id=blind,image_id=img,text=row['text'],non_eos=not row['attempts'][-1]['ended_eos']))
    records.sort(key=lambda r:(list(refby).index(r['image_id']),r['blind_id']))
    dest=OUT/f'semantic/{a.name}';save(dest/'private_mapping.json',mapping)
    save(dest/'blinded.json',dict(reference_sha=sha(refpath),records=records,provenance=provenance,source_sha=sha(__file__)))
    for k in range(0,32,4):
        selected=refs[k:k+4];ids={r['id'] for r in selected}
        save(dest/f'part_{k//4:02}.json',dict(references=selected,outputs=[r for r in records if r['image_id'] in ids]))
    print(len(records),'blinded outputs ->',dest)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--stages',nargs='+',required=True);main(p.parse_args())
