"""사전 고정 내용 판정표의 근거 span 연결과 paired 지표를 계산한다. 임상 정답 생성기는 아니다."""
import argparse
from collections import Counter
import random
import numpy as np
from i141_common import HERE, RES, read, save, sha, now
from i141_spec import integrate
import i141_run as run


def packages():
    records=run.verify_job(RES/'jobs/main','main')
    patients=[x['patient_id'] for x in read(RES/'data_manifest.json')['rows'] if x['role']=='main']
    pairs=[(pid,c) for pid in patients for c in ['S','A']]
    random.Random(141).shuffle(pairs)
    references={x['patient_id']:x for x in read(RES/'reference_locked.json')['rows']}
    items,mapping=[],{}
    for i,(pid,cond) in enumerate(pairs):
        selected=[r for r in records if r['patient_id']==pid and r['condition']==cond]
        package=integrate(selected)
        qid=f'Q{i:02d}'
        mapping[qid]={'patient_id':pid,'condition':cond}
        items.append({'id':qid,'reference':references[pid], 'package':package,
                      'outputs':[{'id':r['id'].split('__')[0]+f'__part{j:03d}',
                                  'slice_indices':r['slice_indices'],'final_text':r['final_text'],'eos':r['eos'],
                                  'boundary_status':r['boundary_status'],'raw_text':r['text_marked']}
                                 for j,r in enumerate(sorted(selected,key=lambda x:x['slice_indices'][0]))],
                      'n_outputs':len(selected),'truncated_outputs':sum(not r['eos'] for r in selected),
                      'invalid_boundary_outputs':sum(r['boundary_status']=='invalid_boundary' for r in selected)})
        # 중복 제거의 source request ID에서도 조건 라벨을 숨긴다.
        for j,sent in enumerate(items[-1]['package']['sentences']):
            sent['request_id']=qid+f'__sentence{j:03d}'
    save(RES/'eval/blinded_packages.json',items)
    save(RES/'eval/condition_mapping.json',mapping)
    save(RES/'eval/package_provenance.json', {'created_at':now(),
         'main_completion_sha256':sha(RES/'jobs/main/completion.json'),
         'reference_sha256':sha(RES/'reference_locked.json'),
         'package_sha256':sha(RES/'eval/blinded_packages.json'),
         'blinding_scope':'condition labels removed; same assistant, not independent blinded clinician'})
    print({'packages':len(items),'model_outputs':len(records)})


def analyze():
    run.verify_job(RES/'jobs/main','main')
    packages={x['id']:x for x in read(RES/'eval/blinded_packages.json')}
    mapping=read(RES/'eval/condition_mapping.json')
    judgments=read(RES/'eval/judgments.json')
    assert set(judgments)==set(packages)
    rows=[]
    for qid,p in packages.items():
        j=judgments[qid]
        refs={a['id']:a for a in p['reference']['positive_atoms']}
        assert set(j['atoms'])==set(refs)
        text=p['package']['raw_concatenation']
        counts=Counter()
        evidence=[]
        for aid,a in j['atoms'].items():
            assert a['state'] in ['matched','contradicted','unmentioned','unresolved']
            counts[a['state']]+=1
            for quote in a.get('output_quotes',[]):
                assert quote and quote in text, '생성문 근거 없음: '+qid+' '+aid
                evidence.append({'atom_id':aid,'reference_span':refs[aid], 'output_quote':quote,
                                 'output_start':text.index(quote),'output_end':text.index(quote)+len(quote)})
            assert a['state'] not in ['matched','contradicted'] or a.get('output_quotes'), '확정 판정에는 원문 근거 필요'
        for field in ['reference_contradictions','internal_contradictions']:
            for item in j[field]:
                assert item['status'] in ['confirmed','unresolved']
                for quote in item['quotes']:
                    assert quote in text
        n=len(refs)
        truncated=p['truncated_outputs']>0 or p['invalid_boundary_outputs']>0
        unknown=counts['unresolved']+(counts['unmentioned'] if truncated else 0)
        contra=j['reference_contradictions']
        internal=j['internal_contradictions']
        row=dict(mapping[qid],blinded_id=qid,n_positive_atoms=n,states=dict(counts),
                 recall=counts['matched']/n if n else None,
                 recall_min=counts['matched']/n if n else None,
                 recall_max=(counts['matched']+unknown)/n if n else None,
                 reference_contradiction_min=int(any(x['status']=='confirmed' for x in contra)),
                 reference_contradiction_max=int(bool(contra)),
                 internal_contradiction_min=int(any(x['status']=='confirmed' for x in internal)),
                 internal_contradiction_max=int(bool(internal)),
                 unresolved_rate=counts['unresolved']/n if n else None,
                 truncated_outputs=p['truncated_outputs'], n_outputs=p['n_outputs'],
                 report_unverified_claims=j['report_unverified_claims'], evidence=evidence,
                 judgments=j)
        rows.append(row)
    systems={}
    for cond in ['S','A']:
        rr=[r for r in rows if r['condition']==cond]
        systems[cond]={'patients':len(rr),'recall_denominator_patients':sum(r['n_positive_atoms']>0 for r in rr),
                       'excluded_no_positive_atoms':sum(r['n_positive_atoms']==0 for r in rr)}
        for key in ['recall','recall_min','recall_max','reference_contradiction_min','reference_contradiction_max',
                    'internal_contradiction_min','internal_contradiction_max','unresolved_rate']:
            systems[cond][key]=float(np.mean([r[key] for r in rr if r[key] is not None]))
        systems[cond]['truncation_rate']=sum(r['truncated_outputs'] for r in rr)/sum(r['n_outputs'] for r in rr)
    delta=systems['A']['recall']-systems['S']['recall']
    dmin=systems['A']['recall_min']-systems['S']['recall_max']
    dmax=systems['A']['recall_max']-systems['S']['recall_min']
    cmin=systems['A']['reference_contradiction_min']-systems['S']['reference_contradiction_max']
    cmax=systems['A']['reference_contradiction_max']-systems['S']['reference_contradiction_min']
    if dmin>=0.05 and cmax<=0.05:
        decision='positive_exploration'
    elif dmax<0.05 or cmin>0.05:
        decision='negative_frozen_adjacent_advantage_not_established'
    else:
        decision='inconclusive'
    pairs=[]
    for pid in sorted(set(r['patient_id'] for r in rows)):
        s=next(r for r in rows if r['patient_id']==pid and r['condition']=='S')
        a=next(r for r in rows if r['patient_id']==pid and r['condition']=='A')
        pairs.append({'patient_id':pid,'recall_S':s['recall'],'recall_A':a['recall'],
                      'delta':a['recall']-s['recall'],'delta_range':[a['recall_min']-s['recall_max'],a['recall_max']-s['recall_min']]})
    rng=np.random.default_rng(141)
    values=np.array([p['delta'] for p in pairs])
    bootstrap=values[rng.integers(0,len(values),size=(10000,len(values)))].mean(1)
    report={'created_at':now(),'systems':systems,'delta_recall_A_minus_S':delta,'delta_recall_range':[dmin,dmax],
            'delta_reference_contradiction_range':[cmin,cmax], 'paired_patients':pairs,
            'exploratory_paired_bootstrap_95CI':np.quantile(bootstrap,[.025,.975]).tolist(),
            'bootstrap_used_as_new_gate':False,'decision':decision,'valid_experiment':True,
            'evaluation_scope':'explicit public DWI text agreement; assistant textual judgment, no clinical false-positive truth',
            'provenance':{str(p):sha(p) for p in [RES/'eval/judgments.json',RES/'eval/blinded_packages.json',RES/'reference_locked.json',RES/'jobs/main/completion.json']}}
    save(RES/'eval/per_patient.json',rows)
    save(RES/'eval/report.json',report)
    print({k:v for k,v in report.items() if k not in ['provenance','paired_patients']})


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=['packages','analyze'])
    a=p.parse_args()
    globals()[a.command]()
