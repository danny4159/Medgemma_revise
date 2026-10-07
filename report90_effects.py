"""검증된 E 환자 벡터의 사전 층화 paired bootstrap과 고정 판정 조건."""
import argparse
import json
from pathlib import Path
import numpy as np
from report86_common import save,sha

METRICS=['strict_recall','type_recall','possible_only','no_ambiguous_reference','no_ambiguous_match',
         'contradiction','internal_contradiction','non_eos','format_failure']

def compare(rows,left,right,definite,seed=89017,repeats=10000):
    by={c:{r['patient']:r for r in rows if r['condition']==c} for c in (left,right)}
    assert all(len(by[c])==sum(r['condition']==c for r in rows) for c in by)
    assert set(by[left])==set(by[right]);patients=sorted(by[left])
    flag=np.array([by[left][p]['abnormal'] for p in patients],bool)
    assert all(by[left][p]['abnormal']==by[right][p]['abnormal'] for p in patients)
    strata=[np.flatnonzero(flag),np.flatnonzero(~flag)];assert all(len(s) for s in strata)
    rng=np.random.default_rng(seed)
    draws=np.concatenate([s[rng.integers(0,len(s),(repeats,len(s)))] for s in strata],axis=1)
    results={}
    for metric in METRICS:
        for scope in (['abnormal'] if metric in METRICS[:5] else ['all','abnormal']):
            valid=flag.copy() if scope=='abnormal' else np.ones(len(patients),bool)
            delta=np.full(len(patients),np.nan)
            for i,p in enumerate(patients):
                a,b=by[left][p][metric],by[right][p][metric]
                assert (a is None)==(b is None)
                if valid[i] and a is not None:delta[i]=float(a)-float(b)
            n=int(np.isfinite(delta).sum())
            if not n:
                results[f'{metric}_{scope}']=dict(n=0,difference=None,ci95=None);continue
            values=delta[draws];counts=np.isfinite(values).sum(axis=1)
            boot=np.nansum(values,axis=1)[counts>0]/counts[counts>0]
            point=float(np.nanmean(delta));ci=np.quantile(boot,[.025,.975]).tolist()
            results[f'{metric}_{scope}']=dict(n=n,difference=point,ci95=ci,undefined_replicates=int((counts==0).sum()),
                bootstrap_replicates=repeats,observed_zero_variation=bool(np.ptp(boot)==0))
    gain=[];net=[];loss=[];deltas=[]
    for p in patients:
        a,b=by[left][p],by[right][p]
        if not a['abnormal'] or a['strict_recall'] is None:continue
        sa={m['ref'] for m in a['matches'] if m['status']=='strict'}&definite
        sb={m['ref'] for m in b['matches'] if m['status']=='strict'}&definite
        if sa-sb:gain.append(p)
        if sb-sa:loss.append(p)
        if len(sa)>len(sb):net.append(p)
        deltas.append(a['strict_recall']-b['strict_recall'])
    loo=[float((sum(deltas)-d)/(len(deltas)-1)) for d in deltas] if len(deltas)>1 else []
    criteria=dict(strict_recall_5pp=results['strict_recall_abnormal']['difference']>=.05,
        contradiction_all_3pp=results['contradiction_all']['difference']<=.03,
        contradiction_abnormal_3pp=results['contradiction_abnormal']['difference']<=.03,
        recovery_5patients=len(gain)>=5,leave_one_out_positive=bool(loo) and min(loo)>0,
        ambiguous_reference_sensitivity_positive=(results['no_ambiguous_reference_abnormal']['difference'] or 0)>0,
        ambiguous_match_sensitivity_positive=(results['no_ambiguous_match_abnormal']['difference'] or 0)>0)
    return dict(left=left,right=right,n=len(patients),abnormal_n=int(flag.sum()),metrics=results,
        additional_recovery_patients=gain,net_recovery_patients=net,lost_recovery_patients=loss,
        leave_one_out_min=min(loo) if loo else None,criteria=criteria,all_criteria_met=all(criteria.values()),
        ci_includes_zero=results['strict_recall_abnormal']['ci95'][0]<=0<=results['strict_recall_abnormal']['ci95'][1])

def main(a):
    stage=Path(a.stage).resolve();reference=Path(a.reference).resolve();verify=stage/'eval/verification.json'
    v=json.loads(verify.read_text());assert v['passed'] and not v['differences']
    for p,h in v['sources'].items():assert sha(p)==h
    path=stage/'eval/per_output.json';assert v['sources'][str(path)]==sha(path)
    refs=json.loads(reference.read_text())['rows'];assert len(refs)==128 and sum(r['abnormal'] for r in refs)==96
    definite={at['id'] for r in refs for at in r['atoms'] if at['polarity']=='positive' and at['certainty']=='definite'}
    rows=json.loads(path.read_text());conditions={r['condition'] for r in rows}
    assert conditions=={a.r,a.g,a.base,a.cure} and len(rows)==512
    results={label:compare(rows,l,r,definite) for label,l,r in [('G-R',a.g,a.r),('R-base',a.r,a.base),('G-base',a.g,a.base),('CURE-base',a.cure,a.base)]}
    save(a.output,dict(comparisons=results,primary='G-R',seed=89017,bootstrap=10000,
        sources={str(p):sha(p) for p in [path,reference,verify,Path(__file__)]},
        scope='조건부 표본·단일 seed·assistant 의미 평가. 참고 시스템 간 순위는 위치 학습의 효과가 아님.'))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--reference',required=True);p.add_argument('--output',required=True)
    p.add_argument('--r',default='R_report');p.add_argument('--g',default='G_report');p.add_argument('--base',default='base_report');p.add_argument('--cure',default='CURE_report');main(p.parse_args())
