"""Production 순위/선택/통계를 호출하지 않는 독립 재계산 및 완료 봉인."""
import hashlib
import json
import math
from pathlib import Path
import re
import time
import numpy as np

BASE=Path('results/iter_082/verified')
NAMES=['posterior_ge2','expected_abs','entropy','one_minus_max','one_minus_margin']

def load(p):
    return json.loads(Path(p).read_text())

def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def independent_scores(r):
    probs=r['probs']; c=probs.index(max(probs))+1
    ordered=sorted(probs)
    return [round(v,12) for v in [sum(v for i,v in enumerate(probs,1) if abs(i-c)>=2),
           sum(v*abs(i-c) for i,v in enumerate(probs,1)),sum(-v*np.log(v) for v in probs if v),
           1-max(probs),1-ordered[-1]+ordered[-2]]]

def order(rows, method, selected):
    def sortkey(r):
        s=independent_scores(r)
        tail=s[selected]
        if method=='D': v=[abs(r['Q']-r['C']),tail]
        elif method=='Db': v=[int(r['Q']!=r['C']),tail]
        else: v=[s[NAMES.index(method)]]
        return tuple(-x for x in v)+(hashlib.sha256(('iter082-review-v1|'+r['id']).encode()).hexdigest(),r.get('occurrence',0))
    return sorted(rows,key=sortkey)

def major(r): return abs(r['C']-r['grade'])>=2

def main():
    start=time.monotonic()
    protocol=load(BASE/'protocol.json')
    for group in ['inputs','code']:
        for p,h in protocol[group].items(): assert digest(p)==h,p
    report=load(BASE/'report.json'); ranks=load(BASE/'ranks.json'); sel=load(BASE/'selection.json')
    assert sel['protocol_sha256']==digest(BASE/'protocol.json')
    manifest=load('results/iter_075/data/manifest.json')['rows']
    features=load('results/iter_078/features.json')['items']
    data={}; regress={}
    for split,n in [('V8',24),('E24',47)]:
        baseline=load(f'results/iter_081/data/baseline_{split}.json')
        ids={r['id'] for r in baseline}; assert len(ids)==n
        wanted=[r for r in manifest if r['id'] in ids]; assert len(wanted)==n
        rawfile=baseline[0]['Q_source']; raw={}
        for line in Path(rawfile).read_text().splitlines():
            q=json.loads(line)
            if q['id'] in ids:
                assert q['id'] not in raw
                raw[q['id']]=q
        records=[]
        for m in wanted:
            q=raw[m['id']]; f=features[m['id']]
            match=re.fullmatch(r'\s*([1-5])\.?\s*',q['text'])
            assert match and q['ended_eos']
            r={k:m[k] for k in ['id','patient','ordinal','grade']}
            r.update(Q=int(match[1]),C=f['probs'].index(max(f['probs']))+1,probs=f['probs'])
            old=next(b for b in baseline if b['id']==m['id'])
            assert all(old[k]==v for k,v in r.items())
            assert old['Q_suffix_ids']==q['suffix_ids'] and old['Q_request_id']==q['request_id']
            records.append(r)
        data[split]=records
        regress[split]={}
        for model in ['Q','C']:
            vals=[np.mean([abs(r[model]-g) for r in records if r['grade']==g]) for g in range(1,6) if any(r['grade']==g for r in records)]
            regress[split][model]=float(np.mean(vals))
            assert abs(regress[split][model]-report['regression'][split][model])<1e-12
    v=data['V8']; candidate=[]
    for name in NAMES:
        top=order(v,name,0)[:6]
        candidate.append((sum(major(r) for r in top),sum(r['C']!=r['grade'] for r in top),sum(abs(r['C']-r['grade']) for r in top)))
    selected=max(range(5),key=lambda i:candidate[i])
    assert NAMES[selected]==sel['baseline']==report['baseline']
    assert {name:list(candidate[i]) for i,name in enumerate(NAMES)}==sel['scores']
    checked=0
    for split,rows in data.items():
        for name in NAMES+['D','Db']:
            ranked=order(rows,name,selected)
            assert [r['id'] for r in ranked]==[r['id'] for r in ranks[split][name]]
            for rate in [.25,.1,.5]:
                k=math.ceil(len(rows)*rate); top=ranked[:k]; t=report['tables'][split][name]['budgets'][str(rate)]
                assert [r['id'] for r in top]==t['ids'] and k==t['k']
                for event,threshold in [('e2',2),('e1',1)]:
                    total=sum(abs(r['C']-r['grade'])>=threshold for r in rows)
                    count=sum(abs(r['C']-r['grade'])>=threshold for r in top)
                    assert count==t[event]['captured'] and total==t[event]['total']
                    assert count/k==t[event]['precision'] and (count/total if total else None)==t[event]['recall']
                    score_by_id={x['id']:tuple(x['risk']) for x in ranks[split][name]}
                    edge=score_by_id[top[-1]['id']]
                    above=[r for r in rows if score_by_id[r['id']]>edge]
                    tied=[r for r in rows if score_by_id[r['id']]==edge]
                    needed=k-len(above)
                    fixed=sum(abs(r['C']-r['grade'])>=threshold for r in above)
                    flags=sorted(int(abs(r['C']-r['grade'])>=threshold) for r in tied)
                    assert fixed+sum(flags[:needed])==t[event]['tie_min']
                    assert fixed+sum(flags[-needed:])==t[event]['tie_max']
                checked+=1
            # AUROC by all ordered positive/negative pairs; AP by grouped recall increments.
            values={x['id']:tuple(x['risk']) for x in ranks[split][name]}
            for event,threshold in [('e2',2),('e1',1)]:
                positive=[r for r in rows if abs(r['C']-r['grade'])>=threshold]
                negative=[r for r in rows if abs(r['C']-r['grade'])<threshold]
                expected=report['tables'][split][name]['discrimination'][event]
                auc=np.mean([1. if values[a['id']]>values[b['id']] else .5 if values[a['id']]==values[b['id']] else 0. for a in positive for b in negative])
                previous_recall=0.; ap=0.
                for value in sorted(set(values.values()),reverse=True):
                    included=[r for r in rows if values[r['id']]>=value]
                    tp=sum(abs(r['C']-r['grade'])>=threshold for r in included)
                    recall=tp/len(positive)
                    ap+=(recall-previous_recall)*tp/len(included)
                    previous_recall=recall
                assert abs(auc-expected['auroc'])<1e-12 and abs(ap-expected['average_precision'])<1e-12

    e=data['E24']; assert sum(major(r) for r in e)==7
    # Integer positions represent the fixed risk ordering; this differs from the production key-sort bootstrap.
    b_order={r['id']:i for i,r in enumerate(order(e,NAMES[selected],selected))}
    d_order={r['id']:i for i,r in enumerate(order(e,'D',selected))}
    patients=sorted({r['patient'] for r in e},key=int)
    groups=[[r for r in e if r['patient']==p] for p in patients]
    rng=np.random.default_rng(8201); deltas=[]; recalls=[]; samples=[]
    for iteration in range(10000):
        draw=rng.integers(0,len(patients),size=len(patients))
        expanded=[(r,occ) for occ,j in enumerate(draw) for r in groups[j]]
        k=(len(expanded)+3)//4
        bt=sorted(expanded,key=lambda x:(b_order[x[0]['id']],x[1]))[:k]
        dt=sorted(expanded,key=lambda x:(d_order[x[0]['id']],x[1]))[:k]
        delta=int(sum(major(r) for r,o in dt)-sum(major(r) for r,o in bt))
        count=sum(major(r) for r,o in expanded)
        deltas.append(delta)
        if count: recalls.append(delta/count)
        samples.append(dict(n=len(expanded),k=k,events=count,count_diff=delta,recall_diff=delta/count if count else None))
    stored=load(BASE/'bootstrap.json')
    assert samples==stored['samples']
    for field,values in [('count_ci95',deltas),('recall_ci95',recalls)]:
        ci=np.quantile(values,[.025,.975]).tolist() if values else None
        assert ci==report[field]==stored[field]
    assert 10000-len(recalls)==stored['undefined_recall']==report['undefined_recall']
    for row in report['leave_one_patient_out']:
        subset=[r for r in e if r['patient']!=row['removed']]; k=math.ceil(len(subset)/4)
        diff=sum(major(r) for r in order(subset,'D',selected)[:k])-sum(major(r) for r in order(subset,NAMES[selected],selected)[:k])
        assert diff==row['diff'] and len(subset)==row['n'] and k==row['k']
    assert len(report['leave_one_patient_out'])==24
    bt=order(e,NAMES[selected],selected)[:12]; dt=order(e,'D',selected)[:12]
    bonly={r['id'] for r in bt}-{r['id'] for r in dt}
    donly={r['id'] for r in dt}-{r['id'] for r in bt}
    for event,threshold in [('e2',2),('e1',1)]:
        detail=report['event_differences'][event]
        di={r['id'] for r in e if r['id'] in donly and abs(r['C']-r['grade'])>=threshold}
        bi={r['id'] for r in e if r['id'] in bonly and abs(r['C']-r['grade'])>=threshold}
        assert di==set(detail['d_only_ids']) and bi==set(detail['b_only_ids']) and len(di)-len(bi)==detail['net']
    delta=sum(major(r) for r in dt)-sum(major(r) for r in bt)
    assert delta==report['count_diff']
    additional={r['patient'] for r in e if r['id'] in donly and major(r)}
    robust=report['tables']['E24']['D']['budgets']['0.25']['e2']['tie_min']>report['tables']['E24'][NAMES[selected]]['budgets']['0.25']['e2']['tie_max']
    positive=delta>=2 and len(additional)>=2 and all(sum(major(r) for r in dt)>sum(major(r) for r in order(e,name,selected)[:12]) for name in NAMES) and all(x['diff']>=0 for x in report['leave_one_patient_out']) and robust
    assert report['decision']==('positive' if positive else 'negative' if delta<=0 else 'inconclusive')
    # Output publication helpers do not perform any ranking or numerical evaluation.
    from review82_analysis import save
    result=dict(passed=True,source_linked_rows=71,checked_budget_tables=checked,bootstrap_replicates_equal=10000,
                regression=regress,count_ci95=report['count_ci95'],recall_ci95=report['recall_ci95'],wall_s=time.monotonic()-start,
                inputs={str(p):digest(p) for p in [BASE/'protocol.json',BASE/'selection.json',BASE/'report.json',BASE/'ranks.json',BASE/'bootstrap.json']})
    save(BASE/'verification.json',result)
    tests=load(BASE/'tests.json'); assert tests['passed']
    for p,h in tests['code'].items(): assert digest(p)==h
    files={str(p):digest(p) for p in BASE.glob('*.json')}
    save(BASE/'completion.json',dict(passed=True,files=files,scope='V8 24 / E24 47; bootstrap 10000; 신규 모델 호출 0; 독립 확인 없음'))
    print(json.dumps({k:v for k,v in result.items() if k!='inputs'},ensure_ascii=False))

if __name__=='__main__': main()
