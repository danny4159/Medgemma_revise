"""생산 평가기를 호출하지 않고 원문 연결과 주 수치·bootstrap을 검산한다."""
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
RES=ROOT/'results/iter_142'
OLD=ROOT/'results/iter_141'

def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(4<<20),b''):
            h.update(b)
    return h.hexdigest()

def load(p):
    def unique(pairs):
        d={}
        for k,v in pairs:
            if k in d:
                raise ValueError(k)
            d[k]=v
        return d
    return json.loads(Path(p).read_text(),object_pairs_hook=unique)

def main():
    judges=load(RES/'eval/judgments.json')
    refs={r['patient_id']:r for r in load(OLD/'reference_locked.json')['rows']}
    inputs=[r for r in load(RES/'inference_inputs.json') if r['role']=='main']
    ids=[r['patient_id'] for r in inputs]
    assert len(ids)==6 and len(set(ids))==6 and set(judges)==set(ids)
    old={(r['patient_id'],r['condition']):r for r in load(OLD/'eval/per_patient.json')}
    report=load(RES/'eval/report.json')
    per={r['patient_id']:r for r in load(RES/'eval/per_patient.json')}
    computed=[]
    quotes=0
    for pid in ids:
        rec=load(RES/'jobs/main'/pid/'result.json')
        assert rec['status']=='ok' and rec['patient_id']==pid
        assert set(rec['actual_call'][0])=={'image','modal'} and rec['actual_call'][0]['modal']=='DWI'
        assert rec['seg_call']['ab']==[None] and rec['seg_call']['ana']==[None]
        for path,h in rec['outputs'].items():
            assert sha(path)==h
        final=judges[pid]['final']
        atoms=final['atoms']
        assert set(atoms)==set(a['id'] for a in refs[pid]['positive_atoms'])
        matched=sum(j['state']=='matched' for j in atoms.values())
        unknown=sum(j['state']=='unresolved' or (not rec['complete'] and j['state']=='unmentioned') for j in atoms.values())
        n=len(atoms)
        cc=final['reference_contradictions']
        values={'recall':matched/n,'recall_min':matched/n,'recall_max':(matched+unknown)/n,
            'reference_contradiction_min':int(any(j['status']=='confirmed' for j in cc)),
            'reference_contradiction_max':int(not rec['complete'] or bool(cc))}
        assert all(abs(per[pid][k]-v)<1e-12 for k,v in values.items())
        for mode,text in [('final',rec['report']),('raw',' '.join(s for g in rec['observations']['generation'] for s in g['decoded']))]:
            j=judges[pid][mode]
            for a in j['atoms'].values():
                assert a['state'] not in ('matched','contradicted') or a['quotes']
                for q in a['quotes']:
                    assert q and q in text
                    quotes+=1
            for field in ('reference_contradictions','internal_contradictions'):
                for item in j[field]:
                    assert item['quotes'] and all(q in text for q in item['quotes'])
                    quotes+=len(item['quotes'])
            for item in j['report_unverified']:
                assert item['quote'] in text
                quotes+=1
        computed.append(values)
    assert abs(report['recall']-sum(r['recall'] for r in computed)/6)<1e-12
    independent={}
    for c in ('S','A'):
        dif=np.array([r['recall']-old[(pid,c)]['recall'] for pid,r in zip(ids,computed)])
        rng=np.random.default_rng(142)
        boot=dif[rng.integers(0,6,(10000,6))].mean(axis=1)
        lo=sum(r['recall_min']-old[(pid,c)]['recall_max'] for pid,r in zip(ids,computed))/6
        hi=sum(r['recall_max']-old[(pid,c)]['recall_min'] for pid,r in zip(ids,computed))/6
        ci=np.percentile(boot,[2.5,97.5]).tolist()
        saved=report['comparisons'][c]
        assert abs(float(dif.mean())-saved['delta'])<1e-12
        assert np.allclose(ci,saved['bootstrap95'],atol=1e-12,rtol=0)
        assert np.allclose([lo,hi],saved['recall_range'],atol=1e-12,rtol=0)
        independent[c]={'delta':float(dif.mean()),'ci95':ci,'range':[lo,hi]}
    all_sources=load(RES/'asset_manifest.json')
    for p,h in all_sources['source_files'].items():
        assert sha(p)==h
    # 기존 141 평가를 계산하지 않고, 계획 잠금에 연결된 원 파일이 그대로인지 검사한다.
    protocol=load(RES/'protocol_main.json')
    for p,h in protocol['files'].items():
        assert sha(p)==h
    result={'all_pass':True,'patients':6,'quote_connections':quotes,'independent':independent,
       'source_sha256':sha(__file__),'meaning_scope':'산술·원문 연결 검증. 같은 assistant의 의미 판정에 대한 독립 전문의 검증은 아님',
       'verified_files':{str(p):sha(p) for p in [RES/'eval/report.json',RES/'eval/per_patient.json',RES/'eval/judgments.json',RES/'protocol_main.json']}}
    path=RES/'eval/independent_verification.json'
    with open(path,'x') as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print(result)

if __name__=='__main__':
    main()
