"""효과·CI를 별도 루프와 quantile 수식으로 재계산한다."""
import argparse
import json
import math
from pathlib import Path
import numpy as np
from report86_common import save,sha

def quantile(values,q):
    values=sorted(values);x=(len(values)-1)*q;lo=int(x);hi=math.ceil(x)
    return values[lo]*(hi-x)+values[hi]*(x-lo) if hi!=lo else values[lo]

def verify(a):
    path=Path(a.effects).resolve();effect=json.loads(path.read_text())
    for p,h in effect['sources'].items():assert sha(p)==h
    vectors=next(Path(p) for p in effect['sources'] if p.endswith('/per_output.json'))
    rows=json.loads(vectors.read_text());differences=[];checked=0
    definite=None
    if getattr(a,'reference',None):
        reference=Path(a.reference).resolve();assert effect['sources'][str(reference)]==sha(reference)
        definite={atom['id'] for row in json.loads(reference.read_text())['rows'] for atom in row['atoms']
                  if atom['polarity']=='positive' and atom['certainty']=='definite'}
    def check(label,x,y):
        nonlocal checked
        checked+=1
        if x is None or y is None:
            if x!=y:differences.append([label,x,y])
        elif abs(float(x)-float(y))>1e-12:differences.append([label,x,y])
    for label,result in effect['comparisons'].items():
        left={r['patient']:r for r in rows if r['condition']==result['left']}
        right={r['patient']:r for r in rows if r['condition']==result['right']};assert set(left)==set(right)
        ids=sorted(left);ab=[i for i,p in enumerate(ids) if left[p]['abnormal']];normal=[i for i,p in enumerate(ids) if not left[p]['abnormal']]
        rng=np.random.default_rng(effect['seed']);n=effect['bootstrap']
        draws_ab=rng.integers(0,len(ab),(n,len(ab)));draws_normal=rng.integers(0,len(normal),(n,len(normal)))
        draws=[[ab[i] for i in aa]+[normal[i] for i in nn] for aa,nn in zip(draws_ab,draws_normal)]
        for name,stored in result['metrics'].items():
            metric,scope=name.rsplit('_',1)
            values=[]
            for p in ids:
                l,r=left[p][metric],right[p][metric]
                assert (l is None)==(r is None)
                values.append(float(l)-float(r) if l is not None and (scope=='all' or left[p]['abnormal']) else None)
            eligible=[x for x in values if x is not None];check(label+'/'+name+'/n',len(eligible),stored['n'])
            if not eligible:check(label+'/'+name,None,stored['difference']);continue
            point=math.fsum(eligible)/len(eligible);bootstrap=[];undefined=0
            for draw in draws:
                sample=[values[i] for i in draw if values[i] is not None]
                if sample:bootstrap.append(math.fsum(sample)/len(sample))
                else:undefined+=1
            check(label+'/'+name,point,stored['difference'])
            for q,v in zip((.025,.975),stored['ci95']):check(label+'/'+name+f'/q{q}',quantile(bootstrap,q),v)
            check(label+'/'+name+'/undefined',undefined,stored['undefined_replicates'])
        delta=[left[p]['strict_recall']-right[p]['strict_recall'] for p in ids if left[p]['abnormal'] and left[p]['strict_recall'] is not None]
        loo=min(math.fsum(delta[:i]+delta[i+1:])/(len(delta)-1) for i in range(len(delta)))
        check(label+'/loo',loo,result['leave_one_out_min'])
        if definite is not None:
            gain=[];loss=[];net=[]
            for p in ids:
                if not left[p]['abnormal'] or left[p]['strict_recall'] is None:continue
                sa={m['ref'] for m in left[p]['matches'] if m['status']=='strict'}&definite
                sb={m['ref'] for m in right[p]['matches'] if m['status']=='strict'}&definite
                if sa-sb:gain.append(p)
                if sb-sa:loss.append(p)
                if len(sa)>len(sb):net.append(p)
            assert gain==result['additional_recovery_patients'] and loss==result['lost_recovery_patients'] and net==result['net_recovery_patients']
            metrics=result['metrics']
            rules=dict(strict_recall_5pp=math.fsum(delta)/len(delta)>=.05,
                contradiction_all_3pp=metrics['contradiction_all']['difference']<=.03,
                contradiction_abnormal_3pp=metrics['contradiction_abnormal']['difference']<=.03,
                recovery_5patients=len(gain)>=5,leave_one_out_positive=loo>0,
                ambiguous_reference_sensitivity_positive=(metrics['no_ambiguous_reference_abnormal']['difference'] or 0)>0,
                ambiguous_match_sensitivity_positive=(metrics['no_ambiguous_match_abnormal']['difference'] or 0)>0)
            assert rules==result['criteria'] and all(rules.values())==result['all_criteria_met']
    output=dict(passed=not differences,checks=checked,differences=differences,
        sources={str(p):sha(p) for p in [path,vectors,Path(__file__)]},claimset_and_decision_checked=definite is not None,
        scope='환자 벡터 이후 통계의 독립 재계산; 의미 판정 임상 타당성은 별도')
    save(a.output,output);assert output['passed'],differences[:5];print('PASS independent effects',checked)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--effects',required=True);p.add_argument('--output',required=True);p.add_argument('--reference');verify(p.parse_args())
