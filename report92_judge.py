"""assistant 의미 판정 spec(prefix→판정)을 report90 judgments/part_XX.json 형식으로 변환한다.
판정 자체는 spec에 사람이 읽고 적은 것이며 여기서 자동 추정하지 않는다."""
import argparse
import importlib
import json
from pathlib import Path
from report86_common import save,sha

def M(ref,status,loc,attr,quote,amb=False):
    return dict(ref=ref,quote=quote,status=status,location=loc,attributes=attr,ambiguous=amb)

def C(finding,pol,status,quote,refs=(),note='',cert='definite'):
    return dict(finding=finding,polarity=pol,certainty=cert,status=status,quote=quote,refs=list(refs),note=note)

def G(quote,refs=(),note=''):
    """일반 음성문. 명시적 'no significant finding' atom이 있으면 supported, 아니면 unknown."""
    return C('significant abnormality','negative','supported' if refs else 'unknown',quote,refs,note)

def build(epoch,spec):
    root=Path(f'results/iter_090/recovery/semantic/epoch{epoch}');blinded=root/'blinded.json'
    d=json.loads(blinded.read_text());ids=[r['blind_id'] for r in d['records']];used=set();out=root/'judgments';out.mkdir(exist_ok=True)
    for k in range(8):
        part=json.loads((root/f'part_{k:02}.json').read_text());judgments=[]
        for o in part['outputs']:
            hits=[p for p in spec if o['blind_id'].startswith(p)];assert len(hits)==1,(o['blind_id'],hits)
            s=spec[hits[0]];used.add(hits[0])
            judgments.append(dict(blind_id=o['blind_id'],matches=s.get('m',[]),claims=s.get('c',[]),internal_conflicts=s.get('ic',[]),format_failure=False))
        content=dict(blinded_sha=sha(blinded),judgments=judgments);target=out/f'part_{k:02}.json'
        if target.exists():
            assert json.loads(target.read_text())==json.loads(json.dumps(content)),f'기존 {target.name} 내용 불일치'
            continue
        save(target,content)
    assert used==set(spec) and len(ids)==sum(len(json.loads((root/f'part_{k:02}.json').read_text())['outputs']) for k in range(8))
    print('wrote',len(used),'judgments')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--epoch',type=int,required=True);p.add_argument('--spec',required=True);a=p.parse_args()
    build(a.epoch,importlib.import_module(a.spec).SPEC)
