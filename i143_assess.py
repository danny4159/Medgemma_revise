"""사전 항목에 대한 수동 인용 판정표의 집계. 임상 자동 판정은 하지 않는다."""
import argparse
from pathlib import Path
import numpy as np
from i141_common import read,sha,digest,now
from i143_runtime import save
from i143_data import OUT
from i143_eval import paired_ci


def score(package,judgment):
    assert judgment['package_id']==package['package_id']
    atoms={a['id']:a for a in package['atoms']}
    states=judgment['atoms']; assert set(states)==set(atoms)
    text=package['text']; counts={k:0 for k in ['matched','unmatched','unresolved']}
    types={}
    incomplete=not package['eos'] or package['boundary']=='invalid_boundary'
    for aid,item in states.items():
        status=item['status']; assert status in counts
        quotes=item.get('quotes',[])
        assert all(q and q in text for q in quotes)
        if status=='matched': assert quotes and package['boundary']!='invalid_boundary'
        if package['boundary']=='invalid_boundary': assert status=='unresolved'
        if incomplete and status=='unmatched': status='unresolved'
        counts[status]+=1
        kind=atoms[aid]['type']; c=types.setdefault(kind,dict(matched=0,unmatched=0,unresolved=0))
        c[status]+=1
    contradictions=judgment['contradictions']
    for item in contradictions:
        assert item['atom_id'] in atoms and item['quote'] and item['quote'] in text
        assert item['reason']
    for item in judgment['internal_contradictions']:
        assert len(item['quotes'])==2 and all(q and q in text for q in item['quotes'])
        assert item['reason']
    n=len(atoms); lo=counts['matched']/n; hi=(counts['matched']+counts['unresolved'])/n
    contra=int(bool(contradictions)); internal=int(bool(judgment['internal_contradictions']))
    return dict(patient_id=package['patient_id'],recall=lo,recall_upper=hi,counts=counts,by_type=types,
                contradiction=contra,contradiction_upper=max(contra,int(incomplete or judgment['contradiction_unresolved'])),
                internal=internal,internal_upper=max(internal,int(incomplete or judgment['internal_unresolved'])),
                incomplete=incomplete)


def compare(a,b):
    assert [r['patient_id'] for r in a]==[r['patient_id'] for r in b]
    x=np.array([r['recall'] for r in a]); y=np.array([r['recall'] for r in b])
    xu=np.array([r['recall_upper'] for r in a]); yu=np.array([r['recall_upper'] for r in b])
    cl=np.array([r['contradiction'] for r in a])-np.array([r['contradiction_upper'] for r in b])
    cu=np.array([r['contradiction_upper'] for r in a])-np.array([r['contradiction'] for r in b])
    return dict(point=paired_ci(x,y),semantic_difference=[float((x-yu).mean()),float((xu-y).mean())],
                contradiction_difference=[float(cl.mean()),float(cu.mean())],
                lower_difference_ci=paired_ci(x,yu),upper_difference_ci=paired_ci(xu,y))


def packages(paths,dest):
    contract=read(OUT/'eval_contract.json'); refs={r['patient_id']:r['atoms'] for r in contract['rows']}
    output=[]; mapping={}; seen=set()
    for path in paths:
        r=read(path); key=(r['patient_id'],r['condition'],r['epoch'])
        assert key not in seen; seen.add(key)
        assert r['digest']==digest({k:v for k,v in r.items() if k!='digest'})
        pid=digest(dict(source_sha256=sha(path),salt='iter143_fixed_blinding'))[:16]
        mapping[pid]=dict(path=str(path),sha256=sha(path),condition=r['condition'],epoch=r['epoch'])
        output.append(dict(package_id=pid,patient_id=r['patient_id'],text=r['final_text'],
                           eos=r['eos'],boundary=r['boundary'],atoms=refs[r['patient_id']]))
    output.sort(key=lambda r:r['package_id'])
    save(dest/'packages.json',dict(created_at=now(),contract_sha256=sha(OUT/'eval_contract.json'),rows=output))
    save(dest/'mapping.json',mapping)


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--paths',nargs='+',required=True); p.add_argument('--dest',required=True)
    a=p.parse_args(); packages([Path(x) for x in a.paths],Path(a.dest))
