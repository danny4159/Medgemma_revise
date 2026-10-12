"""고정 report-agreement BA·층화 환자 bootstrap·calibration/판정. 생성 전 잠금용."""
from fractions import Fraction
import numpy as np
from mr123_run import parse

SEED = 125
BOOTSTRAPS = 10000


def states(text,eos):
    if not eos:return 'INVALID','truncated'
    return parse(text)


def metrics(labels,predictions):
    labels=np.asarray(labels,dtype=int);p=np.asarray(predictions)
    if len(labels)!=len(p) or not set(labels)<=set([0,1]) or not len(labels):raise ValueError('label/prediction array')
    pos=labels==1;neg=labels==0
    sensitivity=float(np.mean(p[pos]=='PRESENT')) if pos.any() else None
    specificity=float(np.mean(p[neg]=='ABSENT')) if neg.any() else None
    correct=(pos&(p=='PRESENT'))|(neg&(p=='ABSENT'))
    exact=(Fraction(int(np.sum(p[pos]=='PRESENT')),int(pos.sum()))+Fraction(int(np.sum(p[neg]=='ABSENT')),int(neg.sum())))/2 if pos.any() and neg.any() else None
    return dict(BA=float(exact) if exact is not None else None,BA_fraction=[exact.numerator,exact.denominator] if exact is not None else None,
         sensitivity=sensitivity,specificity=specificity,accuracy=float(correct.mean()),
         positive_n=int(pos.sum()),negative_n=int(neg.sum()),correct_n=int(correct.sum()),
         uncertain_n=int(np.sum(p=='UNCERTAIN')),invalid_n=int(np.sum(p=='INVALID')))


def auroc(labels,scores):
    y=np.asarray(labels,int);s=np.asarray(scores,float)
    if not np.isfinite(s).all() or len(s)!=len(y):raise ValueError('finite scores')
    pos=s[y==1];neg=s[y==0]
    if not len(pos) or not len(neg):return None
    return float(np.mean((pos[:,None]>neg[None,:])+0.5*(pos[:,None]==neg[None,:])))


def calibrate(rows):
    """calibration 집단만 전달. 후보·>=·동률 규칙은 protocol.json에 사전 고정."""
    if any(r['role']!='calib' for r in rows):raise ValueError('calibration-only')
    y=[int(r['label']=='positive') for r in rows];s=np.asarray([r['S'] for r in rows],float)
    if not np.isfinite(s).all() or len(set(y))!=2:raise ValueError('calibration data')
    values=np.unique(s);thresholds=[0.0]+[(float(a)+float(b))/2 for a,b in zip(values,values[1:])]+[float(np.nextafter(values[-1],np.inf))]
    candidates=[]
    for t in thresholds:
        pred=np.where(s>=t,'PRESENT','ABSENT');m=metrics(y,pred)
        candidates.append(dict(threshold=t,**m))
    chosen=max(candidates,key=lambda r:(r['BA'],r['specificity'],r['threshold']))
    return dict(chosen=chosen,candidates=candidates,operator='>=',calibration_n=len(rows),
         calibration_ids=[r['study_uid'] for r in rows],AUROC=auroc(y,s))


def paired_ci(rows,first,second):
    """batch×label 내 고정 크기 환자 재표집. 두 시스템에 동일 index 적용."""
    if not rows:raise ValueError('empty bootstrap')
    y=np.asarray([int(r['label']=='positive') for r in rows])
    a=np.asarray([r[first] for r in rows]);b=np.asarray([r[second] for r in rows])
    if len(set(y))!=2:raise ValueError('both labels required')
    cells={}
    for i,r in enumerate(rows):cells.setdefault((r['batch_id'],r['label']),[]).append(i)
    rng=np.random.default_rng(SEED);samples=[]
    for _ in range(BOOTSTRAPS):
        ix=np.concatenate([rng.choice(v,len(v),replace=True) for _,v in sorted(cells.items())])
        samples.append(metrics(y[ix],a[ix])['BA']-metrics(y[ix],b[ix])['BA'])
    ma=metrics(y,a);mb=metrics(y,b);exact=Fraction(*ma['BA_fraction'])-Fraction(*mb['BA_fraction'])
    return dict(mean=float(exact),mean_fraction=[exact.numerator,exact.denominator],
         CI95=np.quantile(samples,[0.025,0.975]).tolist(),seed=SEED,replicates=BOOTSTRAPS,
         strata={str(k):len(v) for k,v in cells.items()},unit='patient')


def decision(U,A,S,delta_A_U,complete_S,A_cost,S_cost):
    fraction=lambda m:Fraction(*m['BA_fraction']) if m.get('BA_fraction') else Fraction(str(m['BA']))
    gap=Fraction(*delta_A_U['mean_fraction']) if delta_A_U.get('mean_fraction') else Fraction(str(delta_A_U['mean']))
    positive=(gap>=Fraction('0.15') and delta_A_U['CI95'][0]>0 and A['BA']>=0.75
              and A['sensitivity']>=0.65 and A['specificity']>=0.65)
    sufficient=(complete_S and S is not None and S['BA']>=0.80 and fraction(A)-fraction(S)<Fraction('0.05')
                and A_cost is not None and S_cost is not None and A_cost>S_cost)
    negative=U['BA']<=0.60 and A['BA']<=0.60
    if sufficient:investment='단순 대안 이후 현재 이진 과제 VLM 방법 투자 보류'
    elif negative:investment='현재 frozen 설계 종료'
    elif positive:investment='제한된 sampling 관찰 보존; 독립 확인/방법 진입은 GPT의 별도 판단'
    else:investment='근거 부족으로 현재 설계 보류'
    return dict(positive_sampling_observation=bool(positive),simple_alternative_sufficient=bool(sufficient),
         negative_frozen_design=bool(negative),investment=investment,
         no_automatic_expansion=True,clinical_accuracy_claim=False)
