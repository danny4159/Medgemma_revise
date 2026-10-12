"""iter129 사전 고정 정규화 대조. sampling decision은 사용하지 않는다."""
from collections import Counter
from fractions import Fraction
import numpy as np
from mr128_eval import states, metrics, paired_ci


def decide(P, M, delta):
    gap=Fraction(*delta['mean_fraction'])
    positive=(gap>=Fraction('0.15') and delta['CI95'][0]>0 and M['BA']>=0.75
              and M['sensitivity']>=0.65 and M['specificity']>=0.65)
    negative=M['BA']<=0.60 and delta['CI95'][1]<0.15
    return dict(outcome='positive' if positive else 'negative' if negative else 'inconclusive',
                positive=bool(positive),negative=bool(negative),no_automatic_expansion=True,
                clinical_accuracy_claim=False)


def analyze(manifest, P, M):
    ids=[r['study_uid'] for r in manifest]
    if len(ids)!=40 or len(set(ids))!=40 or set(P)!=set(ids) or set(M)!=set(ids):
        raise ValueError('expected 40 patients with complete paired outputs')
    if len({r['patient_uid'] for r in manifest})!=40:raise ValueError('duplicate patient')
    rows=[]
    for r in manifest:
        s=r['study_uid'];row=dict(r)
        for c,records in [('P',P),('M',M)]:
            row[c],row[c+'_parse']=states(records[s]['text'],records[s]['eos'])
            row[c+'_eos']=records[s]['eos'];row[c+'_n_new']=records[s]['n_new']
        y='PRESENT' if r['label']=='positive' else 'ABSENT'
        row['P_correct']=row['P']==y;row['M_correct']=row['M']==y;rows.append(row)
    labels=[int(r['label']=='positive') for r in rows]
    scores={c:metrics(labels,[r[c] for r in rows]) for c in ['P','M']}
    for c in ['P','M']:
        scores[c].update(state_counts=dict(Counter(r[c] for r in rows)),
            parse_counts=dict(Counter(r[c+'_parse'] for r in rows)),
            eos_n=sum(r[c+'_eos'] for r in rows),tokens=sum(r[c+'_n_new'] for r in rows))
    delta=paired_ci(rows,'M','P')
    transitions={}
    for label in ['positive','negative']:
        rr=[r for r in rows if r['label']==label]
        transitions[label]=dict(state=dict(Counter(r['P']+' -> '+r['M'] for r in rr)),
             correct_to_wrong=sum(r['P_correct'] and not r['M_correct'] for r in rr),
             wrong_to_correct=sum(not r['P_correct'] and r['M_correct'] for r in rr))
    return dict(n=40,**scores,M_minus_P=delta,transitions=transitions,
                decision=decide(scores['P'],scores['M'],delta)),rows


def independent(rows,report):
    """공유 metric/bootstrap을 호출하지 않는 원시 상태의 별도 산술 검산."""
    y=np.array([r['label']=='positive' for r in rows])
    cp=np.array([r['P']==('PRESENT' if r['label']=='positive' else 'ABSENT') for r in rows])
    cm=np.array([r['M']==('PRESENT' if r['label']=='positive' else 'ABSENT') for r in rows])
    cells={}
    for i,r in enumerate(rows):cells.setdefault((r['batch_id'],r['label']),[]).append(i)
    rng=np.random.default_rng(125);values=[]
    for _ in range(10000):
        ix=np.concatenate([rng.choice(v,len(v),replace=True) for _,v in sorted(cells.items())])
        d=cm[ix].astype(float)-cp[ix].astype(float)
        values.append((d[y[ix]].mean()+d[~y[ix]].mean())/2)
    ci=np.quantile(values,[.025,.975]).tolist()
    expected={c:(v[y].mean()+v[~y].mean())/2 for c,v in [('P',cp),('M',cm)]}
    checks={c+'_BA':abs(expected[c]-report[c]['BA'])<1e-12 for c in expected}
    checks['CI95']=bool(np.allclose(ci,report['M_minus_P']['CI95'],atol=1e-12,rtol=0))
    checks['delta']=abs(expected['M']-expected['P']-report['M_minus_P']['mean'])<1e-12
    if not all(checks.values()):raise ValueError('independent arithmetic mismatch')
    return dict(passed=True,checks=checks,independent_CI95=ci)
