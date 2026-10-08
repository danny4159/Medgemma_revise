"""iter_097 R→G 분기 판정. 사전 기준(plan.md Evaluation)을 그대로 구현한다. 결과를 보고 문턱을 바꾸지 않는다.
입력: 같은 조건명 가림 batch의 per_output.json (R 신규, base, 고LR R 2종). 출력: results/iter_097/decisions/*.json"""
import argparse
import json
from pathlib import Path
import numpy as np
from report86_common import save,sha
from report97_train import OUT

MIN_DIFF=0.05;MIN_NET=3;MAX_CONTRA_INC=1;BOOT=10000;SEED=97017

def by_condition(per):
    out={}
    for x in per:out.setdefault(x['condition'],{})[x['image_id']]=x
    return out

def recall_vec(cond,ids,key='strict_recall'):return np.array([cond[i][key] for i in ids],float)

def contra_patients(cond,conservative):
    n=0
    for x in cond.values():
        hit=x['contradiction'] or x['internal_contradiction']
        if conservative:hit=hit or any(c['status']=='unknown' and c.get('note','').startswith('POSSIBLE_CONTRA') for c in x['claims'])
        n+=bool(hit)
    return n

def compare(new,old):
    ids=sorted(i for i,x in new.items() if x['abnormal'] and x['strict_recall'] is not None);assert ids==sorted(i for i,x in old.items() if x['abnormal'] and x['strict_recall'] is not None)
    a=recall_vec(new,ids);b=recall_vec(old,ids);d=a-b
    inc=int((d>1e-12).sum());dec=int((d<-1e-12).sum());net=inc-dec
    loo=[float(np.delete(d,k).mean()) for k in range(len(d))]
    rng=np.random.default_rng(SEED);boots=[float(d[rng.integers(0,len(d),len(d))].mean()) for _ in range(BOOT)]
    # 보수: 신규는 모호하지 않은 대응만, 비교군은 모든 strict 대응 인정
    cons=recall_vec(new,ids,'no_ambiguous_match')-recall_vec(old,ids,'strict_recall')
    cons_inc=int((cons>1e-12).sum());cons_dec=int((cons<-1e-12).sum())
    c_new=contra_patients(new,False);c_old=contra_patients(old,False);cc_new=contra_patients(new,True);cc_old=contra_patients(old,False)
    checks=dict(diff_ge_5pp=float(d.mean())>=MIN_DIFF-1e-12,net_ge_3=net>=MIN_NET,loo_positive=all(x>0 for x in loo),
        contra_inc_le_1=c_new-c_old<=MAX_CONTRA_INC,
        conservative_pass=float(cons.mean())>=MIN_DIFF-1e-12 and cons_inc-cons_dec>=MIN_NET and (cc_new-cc_old)<=MAX_CONTRA_INC)
    return dict(n_recall_patients=len(ids),new_mean=float(a.mean()),old_mean=float(b.mean()),diff=float(d.mean()),
        ci95=[float(np.percentile(boots,2.5)),float(np.percentile(boots,97.5))],increased=inc,decreased=dec,net=net,loo_min=min(loo),loo_max=max(loo),
        contra_new=c_new,contra_old=c_old,conservative=dict(diff=float(cons.mean()),increased=cons_inc,decreased=cons_dec,contra_new_with_possible=cc_new,contra_old=cc_old),
        type_only_diff=float(recall_vec(new,ids,'type_recall').mean()-recall_vec(old,ids,'type_recall').mean()),
        checks=checks,passed=all(checks.values()),per_patient=[dict(image_id=i,new=float(x),old=float(y)) for i,x,y in zip(ids,a,b)])

def main(a):
    per=json.loads(Path(a.per_output).read_text());conds=by_condition(per)
    new=conds[a.new];result={}
    for name in a.comparators:result[name]=compare(new,conds[name])
    verdict=all(r['passed'] for r in result.values())
    save(a.output,dict(new=a.new,comparators=a.comparators,results=result,r_passes_possibility_criterion=verdict,
        thresholds=dict(min_diff=MIN_DIFF,min_net=MIN_NET,max_contra_inc=MAX_CONTRA_INC,bootstrap=BOOT,seed=SEED),
        sources={str(a.per_output):sha(a.per_output),__file__:sha(__file__)},
        scope='V32 개발 자료 탐색 투자 문턱; 임상 비열등성·독립 확인 아님. CI 하한>0 은 hard gate 아님.'))
    print(json.dumps({k:{x:v[x] for x in ('new_mean','old_mean','diff','increased','decreased','contra_new','contra_old','passed')} for k,v in result.items()}),flush=True)
    print('R passes possibility criterion:',verdict)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--per-output',dest='per_output',required=True);p.add_argument('--new',required=True)
    p.add_argument('--comparators',nargs='+',required=True);p.add_argument('--output',required=True);main(p.parse_args())
