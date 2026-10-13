"""사전 의미 계약에 따라 작성한 새 판정표를 집계한다. 기존 판정은 읽기만 한다."""
from collections import Counter,defaultdict
import argparse
import numpy as np
from i142_common import *

def score(rec,ref,judgment,text_key='report'):
    text=rec[text_key]
    atoms={a['id']:a for a in ref['positive_atoms']}
    assert set(atoms)==set(judgment['atoms'])
    counts=Counter()
    types=defaultdict(Counter)
    evidence=[]
    for aid,j in judgment['atoms'].items():
        assert j['state'] in ('matched','contradicted','unmentioned','unresolved')
        assert j['state'] not in ('matched','contradicted') or j['quotes']
        counts[j['state']]+=1
        types[atoms[aid]['type']][j['state']]+=1
        for q in j['quotes']:
            assert q and q in text
            start=text.index(q)
            evidence.append({'atom_id':aid,'quote':q,'start':start,'end':start+len(q),'reference_span':atoms[aid]})
    for field in ('reference_contradictions','internal_contradictions'):
        for j in judgment[field]:
            assert j['status'] in ('confirmed','unresolved')
            assert j['quotes'] and all(q in text for q in j['quotes'])
    for j in judgment['report_unverified']:
        assert j['quote'] in text
    n=len(atoms)
    incomplete=not rec['complete']
    possible=counts['unresolved']+(counts['unmentioned'] if incomplete else 0)
    out={'patient_id':rec['patient_id'],'n':n,'states':dict(counts),'types':{t:dict(c) for t,c in types.items()},
         'recall':counts['matched']/n,'recall_min':counts['matched']/n,'recall_max':(counts['matched']+possible)/n,
         'incomplete':incomplete,'evidence':evidence,'judgment':judgment}
    for field in ('reference','internal'):
        jj=judgment[field+'_contradictions']
        out[field+'_contradiction_min']=int(any(j['status']=='confirmed' for j in jj))
        out[field+'_contradiction_max']=int(incomplete or bool(jj))
    return out

def compare(rows,old,condition):
    selected={r['patient_id']:r for r in old if r['condition']==condition}
    assert set(selected)==set(r['patient_id'] for r in rows)
    values=np.array([r['recall']-selected[r['patient_id']]['recall'] for r in rows])
    rng=np.random.default_rng(142)
    b=values[rng.integers(0,len(values),size=(10000,len(values)))].mean(1)
    return {'delta':float(values.mean()),'bootstrap95':np.quantile(b,[.025,.975]).tolist(),
       'recall_range':[float(np.mean([r['recall_min']-selected[r['patient_id']]['recall_max'] for r in rows])),
                       float(np.mean([r['recall_max']-selected[r['patient_id']]['recall_min'] for r in rows]))],
       'contradiction_range':[float(np.mean([r['reference_contradiction_min']-selected[r['patient_id']]['reference_contradiction_max'] for r in rows])),
                              float(np.mean([r['reference_contradiction_max']-selected[r['patient_id']]['reference_contradiction_min'] for r in rows]))]}

def decision(comparison,complete):
    lo,hi=comparison['recall_range']
    clo,chi=comparison['contradiction_range']
    if lo>=.05 and chi<=.05:
        return 'positive_development_recovery'
    if not complete:
        return 'inconclusive'
    if hi<.05 or clo>.05:
        return 'negative_current_RGv2_DWI'
    return 'inconclusive'

def main():
    protocol=verify_protocol(RES/'protocol_main.json')
    inputs=[r for r in read(RES/'inference_inputs.json') if r['role']=='main']
    refs={r['patient_id']:r for r in read(OLD/'reference_locked.json')['rows']}
    judgments=read(RES/'eval/judgments.json')
    assert set(judgments)==set(r['patient_id'] for r in inputs)
    rows=[]
    for r in inputs:
        rec=verify_result(RES/'jobs/main'/r['patient_id']/'result.json',protocol,r)
        rows.append(score(rec,refs[r['patient_id']],judgments[r['patient_id']]['final']))
    old=read(OLD/'eval/per_patient.json')
    comparisons={c:compare(rows,old,c) for c in ('S','A')}
    report={'created_at':now(),'n':len(rows),'recall':float(np.mean([r['recall'] for r in rows])),
        'recall_range':[float(np.mean([r['recall_min'] for r in rows])),float(np.mean([r['recall_max'] for r in rows]))],
        'comparisons':comparisons,'decision':decision(comparisons['S'],all(not r['incomplete'] for r in rows)),
        'reference_contradiction_range':[float(np.mean([r['reference_contradiction_min'] for r in rows])),float(np.mean([r['reference_contradiction_max'] for r in rows]))],
        'incomplete_patients':sum(r['incomplete'] for r in rows),
        'scope':'공개 DWI 항목과 새 출력의 제한적 문장 일치; 임상 FP·독립 일반화 미판정',
        'provenance':{str(p):sha(p) for p in [RES/'eval/judgments.json',OLD/'eval/per_patient.json',OLD/'eval/report.json',RES/'protocol_main.json']}}
    save(RES/'eval/per_patient.json',rows)
    save(RES/'eval/report.json',report)
    print(report)

if __name__=='__main__':
    main()
