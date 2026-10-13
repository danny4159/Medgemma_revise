"""고정 parser의 환자별 순위 평가와 층화 paired bootstrap."""
import argparse,numpy as np
from mr132_common import RES,read,save,sha,now
from mr132_spec import parse,pair_value,expansion,PAIRS,ACQS

def compute(stage,records):
    labels=read(RES/'data'/f'{stage}_labels.json'); baseline=read(RES/'baseline/predictions.json'); by={r['id']:r for r in records}
    patients=[]; details=[]; consistent=[]; invalid=[]
    for lab in labels:
        ident=lab['id']; grades=lab['grades']; single=[]
        for i in range(3):
            rec=by[f'{ident}_single_{i}']; single.append(parse(rec['text'],'single',rec['eos']))
        pp={'single':[],'direct':[],'direct_strict':[],'both_orders_correct':[]}
        pp.update({name:[] for name in baseline['values']})
        for i,j in PAIRS:
            preds=[]; raws=[]
            for first,second in [(i,j),(j,i)]:
                rec=by[f'{ident}_pair_{first}{second}']; p=parse(rec['text'],'pair',rec['eos']); raws.append(p)
                canonical=first if p=='A' else second if p=='B' else p
                preds.append(canonical); invalid.append(p is None or p=='UNKNOWN')
            same=all(p not in [None,'UNKNOWN'] for p in preds) and preds[0]==preds[1]; consistent.append(same)
            d=dict(patient=ident,pair=[i,j],grades=[grades[i],grades[j]],grade_gap=abs(grades[i]-grades[j]),order_predictions=preds,raw_predictions=raws,consistent=same)
            if grades[i]!=grades[j]:
                winner=i if grades[i]<grades[j] else j
                dv=np.mean([pair_value(p,winner) for p in preds]); st=np.mean([pair_value(p,winner,True) for p in preds])
                sv=0 if single[i] is None or single[j] is None else .5 if single[i]==single[j] else float((single[i]<single[j])==(grades[i]<grades[j]))
                d.update(direct=float(dv),direct_strict=float(st),single=sv,both_orders_correct=float(all(p==winner for p in preds)))
                for k in pp:
                    if k in d: pp[k].append(d[k])
                    else:
                        vv=baseline['values'][k]; a,b=[vv[lab['bids_names'][z]] for z in [i,j]]
                        pp[k].append(.5 if a==b else float((a<b)==(grades[i]<grades[j])))
            details.append(d)
        patients.append(dict(id=ident,stratum=lab['stratum'],grades=grades,n_nontied=len(pp['direct']),single_scores=single,values={k:float(np.mean(v)) if v else None for k,v in pp.items()}))
    valid=[p for p in patients if p['n_nontied']]; systems=list(valid[0]['values']); vals={k:np.array([p['values'][k] for p in valid]) for k in systems}
    rng=np.random.default_rng(132); indices=[]
    for b in range(10000):
        sel=[]
        for s in ['tie','nontie']:
            group=np.array([i for i,p in enumerate(valid) if p['stratum']==s]); sel.extend(rng.choice(group,len(group),replace=True).tolist())
        indices.append(sel)
    indices=np.array(indices,dtype=int)
    comparisons={}
    for target in ['single',baseline['selected_strongest']]:
        diff=vals['direct']-vals[target]; arr=diff[indices].mean(axis=1)
        comparisons['direct_minus_'+target]=dict(delta=float(diff.mean()),ci95=np.quantile(arr,[.025,.975]).tolist())
    error=float(np.mean(invalid)); consistency=float(np.mean(consistent))
    delta_s=comparisons['direct_minus_single']['delta']; delta_i=comparisons['direct_minus_'+baseline['selected_strongest']]['delta']
    report=dict(stage=stage,created_at=now(),n_patients=len(patients),n_primary_patients=len(valid),n_excluded_all_tied=len(patients)-len(valid),n_nontied_pairs=sum(p['n_nontied'] for p in patients),metrics={k:float(v.mean()) for k,v in vals.items()},strata={s:{k:float(np.mean([p['values'][k] for p in valid if p['stratum']==s])) for k in systems} for s in ['tie','nontie']},comparisons=comparisons,order_consistency=consistency,invalid_unknown_rate=error,single_invalid_rate=float(np.mean([v is None for p in patients for v in p['single_scores']])),selected_iqm=baseline['selected_strongest'],breakdown={tag:dict(n=len(group),direct=float(np.mean([d['direct'] for d in group])) if group else None,single=float(np.mean([d['single'] for d in group])) if group else None) for tag,group in [(str(g),[d for d in details if d['grade_gap']==g]) for g in [1,2]]+[('headmotion_pair',[d for d in details if d['pair']==[1,2] and d['grade_gap']>0])]},tie_pairs=[d for d in details if d['grade_gap']==0],cost=dict(individual_request_s=sum(r['wall_s'] for r in records if r['kind']=='single'),direct_request_s=sum(r['wall_s'] for r in records if r['kind']=='pair'),individual_tokens=sum(r['n_tokens'] for r in records if r['kind']=='single'),direct_tokens=sum(r['n_tokens'] for r in records if r['kind']=='pair'),iqm_generation='未測定'),expand=expansion(delta_s,delta_i,consistency,error))
    report['cost']['iqm_generation']='미측정'
    return report,patients,details

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('stage',choices=['technical','development','holdout']); a=ap.parse_args()
    from mr132_run import verify_job,verify_protocol
    verify_protocol(); records=verify_job(RES/'gen'/a.stage,RES/'requests'/f'{a.stage}.json')
    report,patients,details=compute(a.stage,records); out=RES/'eval'; out.mkdir(exist_ok=True)
    save(out/f'{a.stage}_report.json',report); save(out/f'{a.stage}_per_patient.json',patients); save(out/f'{a.stage}_pairs.json',details)
    positive=report['expand']; ci_positive=all(v['ci95'][0]>0 for v in report['comparisons'].values())
    save(out/f'{a.stage}_decision.json',dict(expand=positive,branch='positive_exploration' if positive and ci_positive else 'precision_supplement' if positive else 'no_expansion',report_sha256=sha(out/f'{a.stage}_report.json'),reason='사전 효과 크기·순서·오류율 조건 적용',scope='현재 frozen MR-ART 품질 비교; MRI 전체 미판정'))
    print(report['metrics'],report['comparisons'],'consistency',report['order_consistency'],'error',report['invalid_unknown_rate'],'expand',positive)

if __name__=='__main__': main()
