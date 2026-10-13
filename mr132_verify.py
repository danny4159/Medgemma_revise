"""production 평가 함수를 부르지 않는 원 출력 순위·bootstrap 독립 검산."""
import argparse,re,itertools,numpy as np
from mr132_common import RES,read,save,sha,now

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('stage'); a=ap.parse_args(); stage=a.stage
    from mr132_run import verify_job
    rec=verify_job(RES/'gen'/stage,RES/'requests'/f'{stage}.json'); raw={r['id']:r for r in rec}
    labels=read(RES/'data'/f'{stage}_labels.json'); baseline=read(RES/'baseline/predictions.json'); report=read(RES/'eval'/f'{stage}_report.json'); per=read(RES/'eval'/f'{stage}_per_patient.json'); tables={p['id']:p for p in per}
    def first(r,score=False):
        if not r['eos']:return None
        l=r['text'].strip().splitlines()[0].strip() if r['text'].strip() else ''
        if score:
            if re.fullmatch(r'(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)',l):
                x=float(l); return x if 0<=x<=100 else None
            return None
        return l if l in ['A','B','TIE','UNKNOWN'] else None
    computed=[]; concord=[]; errors=[]; checks=[]
    for lab in labels:
        singles=[first(raw[lab['id']+'_single_'+str(i)],True) for i in range(3)]
        metrics={k:[] for k in report['metrics']}
        for i,j in itertools.combinations(range(3),2):
            preds=[]
            for p,q in [(i,j),(j,i)]:
                answer=first(raw[lab['id']+'_pair_'+str(p)+str(q)])
                preds.append(p if answer=='A' else q if answer=='B' else answer); errors.append(answer in [None,'UNKNOWN'])
            concord.append(preds[0]==preds[1] and preds[0] not in [None,'UNKNOWN'])
            gi,gj=lab['grades'][i],lab['grades'][j]
            if gi==gj:continue
            win=i if gi<gj else j
            metrics['direct'].append(sum(.5 if p=='TIE' else float(p==win) for p in preds)/2)
            metrics['direct_strict'].append(sum(float(p==win) for p in preds)/2)
            metrics['both_orders_correct'].append(float(preds==[win,win]))
            si,sj=singles[i],singles[j]; metrics['single'].append(0 if si is None or sj is None else .5 if si==sj else float((si<sj)==(gi<gj)))
            for k,vs in baseline['values'].items():
                x,y=[vs[lab['bids_names'][z]] for z in [i,j]]
                metrics[k].append(.5 if x==y else float((x<y)==(gi<gj)))
        vec={k:float(np.average(v)) if v else None for k,v in metrics.items()}
        checks.append(dict(name='patient_'+lab['id'],pass_=vec==tables[lab['id']]['values'] and singles==tables[lab['id']]['single_scores']))
        if metrics['direct']:computed.append(dict(stratum=lab['stratum'],v=vec))
    for k in report['metrics']:
        checks.append(dict(name='metric_'+k,pass_=abs(np.mean([p['v'][k] for p in computed])-report['metrics'][k])<1e-12))
    checks += [dict(name='consistency',pass_=abs(np.mean(concord)-report['order_consistency'])<1e-12),dict(name='errors',pass_=abs(np.mean(errors)-report['invalid_unknown_rate'])<1e-12)]
    rng=np.random.default_rng(132); boot={k:[] for k in report['comparisons']}
    for _ in range(10000):
        selected=[]
        for s in ['tie','nontie']:
            indices=[i for i,p in enumerate(computed) if p['stratum']==s]; selected.extend(rng.choice(indices,len(indices),replace=True).tolist())
        for key in boot:
            target=key[len('direct_minus_'):]; boot[key].append(np.mean([computed[i]['v']['direct']-computed[i]['v'][target] for i in selected]))
    for k,v in boot.items(): checks.append(dict(name='bootstrap_'+k,pass_=np.allclose(np.quantile(v,[.025,.975]),report['comparisons'][k]['ci95'],atol=1e-12,rtol=0)))
    deltas=report['comparisons']; expand=(deltas['direct_minus_single']['delta']>=.10 and deltas['direct_minus_'+baseline['selected_strongest']]['delta']>=.05 and np.mean(concord)>=.90 and np.mean(errors)<=.05)
    checks.append(dict(name='expand_contract',pass_=expand==report['expand']==read(RES/'eval'/f'{stage}_decision.json')['expand']))
    for c in checks:c['pass']=bool(c.pop('pass_'))
    save(RES/'eval'/f'{stage}_independent_verify.json',dict(created_at=now(),all_pass=all(c['pass'] for c in checks),checks=checks,report_sha256=sha(RES/'eval'/f'{stage}_report.json'),source_sha256=sha(__file__),raw_completion_sha256=sha(RES/'gen'/stage/'completion.json')))
    print('독립 검산',sum(c['pass'] for c in checks),'/',len(checks))
    if not all(c['pass'] for c in checks):raise RuntimeError('independent mismatch')
if __name__=='__main__':main()
