"""iter_082: 고정 저장 출력의 오류 검토 순위 분석. GPU 호출 없음."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import numpy as np
from sp75_metrics import class_std_mae

ROOT = Path('results/iter_082/verified')
NAMES = ['posterior_ge2', 'expected_abs', 'entropy', 'one_minus_max', 'one_minus_margin']
RULES = dict(seed=8201, n_boot=10000, rates=[0.25, 0.1, 0.5], rounding=12,
             salt='iter082-review-v1|', patient_order='numeric', occurrence='draw index after ID hash',
             auroc='lexicographic risk, half credit for equal risk; excludes hash',
             average_precision='threshold-grouped noninterpolated AP; excludes hash')

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def read(p):
    return json.loads(Path(p).read_text())

def save(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode()
    # hard-link publication is atomic and refuses concurrent/existing output.
    tmp = p.with_name(p.name+f'.{os.getpid()}.tmp')
    with tmp.open('xb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.link(tmp, p)
    finally:
        tmp.unlink()

def scores(r):
    p = np.asarray(r['probs'], float)
    assert p.shape == (5,) and np.isfinite(p).all() and (p >= 0).all() and abs(p.sum()-1) <= 1e-5
    c = int(np.argmax(p))+1
    assert c == r['C']
    dist = np.abs(np.arange(1, 6)-c)
    top = sorted(p, reverse=True)
    vals = [sum(p[dist >= 2]), sum(p*dist), -sum(x*math.log(x) for x in p if x > 0), 1-top[0], 1-(top[0]-top[1])]
    return dict(zip(NAMES, [round(float(x), 12) for x in vals]))

def risk(r, name, baseline):
    s = scores(r)
    if name == 'D':
        return (abs(r['Q']-r['C']), s[baseline])
    if name == 'Db':
        return (int(r['Q'] != r['C']), s[baseline])
    return (s[name],)

def key(r, name, baseline):
    return (*(-x for x in risk(r, name, baseline)), hashlib.sha256((RULES['salt']+r['id']).encode()).hexdigest(), r.get('occurrence', 0))

def rank(rows, name, baseline):
    return sorted(rows, key=lambda r: key(r, name, baseline))

def error(r):
    return abs(r['C']-r['grade'])

def select(rows, split):
    assert split == 'V8', 'selection must use V8 only'
    vals = {}
    for n in NAMES:
        top = rank(rows, n, n)[:math.ceil(.25*len(rows))]
        vals[n] = [sum(error(r)>=2 for r in top), sum(error(r)>0 for r in top), sum(error(r) for r in top)]
    return max(NAMES, key=lambda n: tuple(vals[n])), vals

def capture(rows, name, baseline, rate=.25):
    rr = rank(rows, name, baseline)
    k = math.ceil(rate*len(rows))
    top = rr[:k]
    return sum(error(r)>=2 for r in top)

def table(rows, name, baseline, rate):
    rr = rank(rows, name, baseline)
    k = math.ceil(rate*len(rows))
    top, rest = rr[:k], rr[k:]
    boundary = risk(rr[k-1], name, baseline)
    strict = [r for r in rr if risk(r,name,baseline)>boundary]
    tied = [r for r in rr if risk(r,name,baseline)==boundary]
    slots = k-len(strict)
    out = dict(n=len(rows), k=k, ids=[r['id'] for r in top], patients=sorted({r['patient'] for r in top},key=int),
               unreviewed_mae=float(np.mean([error(r) for r in rest])) if rest else None,
               q_wrong_c_correct_ids=[r['id'] for r in top if r['Q']!=r['grade'] and r['C']==r['grade']],
               boundary_tie_ids=[r['id'] for r in tied], boundary_slots=slots)
    for label, threshold in [('e2',2),('e1',1)]:
        total = sum(error(r)>=threshold for r in rows)
        got = sum(error(r)>=threshold for r in top)
        fixed = sum(error(r)>=threshold for r in strict)
        t = sum(error(r)>=threshold for r in tied)
        out[label] = dict(total=total, captured=got, precision=got/k, recall=got/total if total else None,
                          missed=total-got, tie_min=fixed+max(0,slots-(len(tied)-t)), tie_max=fixed+min(slots,t))
    out['groups'] = {field:{str(v):dict(total=sum(r[field]==v for r in rows), reviewed=sum(r[field]==v for r in top),
                                      e2_captured=sum(r[field]==v and error(r)>=2 for r in top))
                            for v in sorted({r[field] for r in rows})} for field in ['grade','ordinal']}
    return out

def discrimination(rows, name, baseline, threshold):
    pos = [r for r in rows if error(r)>=threshold]
    neg = [r for r in rows if error(r)<threshold]
    if not pos or not neg:
        return dict(auroc=None, average_precision=None, reason='single event class')
    auc = sum((risk(a,name,baseline)>risk(b,name,baseline))+.5*(risk(a,name,baseline)==risk(b,name,baseline)) for a in pos for b in neg)/(len(pos)*len(neg))
    groups = sorted({risk(r,name,baseline) for r in rows}, reverse=True)
    tp = n = 0
    ap = 0.
    for g in groups:
        batch = [r for r in rows if risk(r,name,baseline)==g]
        plus = sum(error(r)>=threshold for r in batch)
        tp += plus
        n += len(batch)
        ap += plus/len(pos)*tp/n
    return dict(auroc=auc, average_precision=ap)

def load_inputs():
    source = read('results/iter_081/data/source_audit.json')
    completion = read('results/iter_081/completion.json')
    assert source['passed'] and completion['passed']
    paths = ['results/iter_075/data/manifest.json','results/iter_078/features.json','results/iter_081/data/source_audit.json']
    seals = [completion['files'],source['source_files']]
    for split in ['V8','E24']:
        pp = f'results/iter_081/protocol_{split}.json'
        assert sha(pp)==completion['files'][pp]
        paths.append(pp)
        proto = read(pp)
        seals.append(proto['files'])
        paths.extend([f'results/iter_081/data/baseline_{split}.json',f'results/iter_078/data/labels_{split}.json'])
    expected = {}
    for p in paths:
        values = {s[p] for s in seals if p in s}
        assert len(values)==1, ('missing/conflicting preserved hash',p)
        expected[p]=values.pop()
        assert sha(p)==expected[p], p
    manifest = read(paths[0])['rows']
    features = read(paths[1])['items']
    result = {}
    for split,n,npats,ords in [('V8',24,8,[1,3,5]),('E24',47,24,[2,4])]:
        rows=read(f'results/iter_081/data/baseline_{split}.json')
        assert len(rows)==n and len({r['id'] for r in rows})==n and len({r['patient'] for r in rows})==npats
        eligible = [r for r in manifest if r['split']==split and r['ordinal'] in ords and r['excluded'] is None]
        assert {r['id'] for r in eligible}=={r['id'] for r in rows}
        labels=read(f'results/iter_078/data/labels_{split}.json')['labels']
        assert set(labels)=={r['id'] for r in rows}
        rawpath=rows[0]['Q_source']
        envpath=rawpath.replace('.jsonl','.env.json')
        for p in [rawpath,envpath]:
            assert sha(p)==source['source_files'][p]
            expected[p]=sha(p)
        env=read(envpath)
        raw={}
        allowed={r['id'] for r in rows}
        for line in Path(rawpath).read_text().splitlines():
            r=json.loads(line)
            if r['id'] in allowed:
                assert r['id'] not in raw
                raw[r['id']]=r
        assert set(raw)==allowed
        for r in rows:
            m=next(x for x in eligible if x['id']==r['id'])
            f=features[r['id']]
            q=raw[r['id']]
            for field in ['grade','patient','ordinal']:
                assert r[field]==m[field]==labels[r['id']][field]
            assert f['probs']==r['probs'] and f['pred']==r['C']
            assert f['patient']==r['patient'] and f['ordinal']==r['ordinal'] and f['split']==split
            scores(r)
            assert q['ended_eos'] and re.fullmatch(r'[1-5]\.?',q['text'].strip())
            assert int(q['text'].strip()[0])==r['Q']==q['parsed'] and q['parse_valid']
            assert q['suffix_ids']==r['Q_suffix_ids'] and q['request_id']==r['Q_request_id']
            assert q['suffix_ids'][-1] in env['env']['eos_token_id'] and q['n_new']<=32
            assert q['config_digest']==env['config_digest'] and q['adapter_digest']==env['adapter_digest']
            assert q['patient']==r['patient'] and q['ordinal']==r['ordinal'] and q['split']==split
            assert q['input_file_sha256']==f['input_file_sha256']==[x['file_sha256'] for x in m['inputs']['R']]
            assert q['input_pixel_sha256']==[x['pixel_sha256_padded'] for x in m['inputs']['R']]
        result[split]=rows
    assert not {r['patient'] for r in result['V8']} & {r['patient'] for r in result['E24']}
    blob=hashlib.sha1(b'blob '+str(Path('sp75_metrics.py').stat().st_size).encode()+b'\0'+Path('sp75_metrics.py').read_bytes()).hexdigest()
    assert blob=='7d7b1c9f1027c05f94c923d5cc38aec58f276f51'
    regression={s:{model:class_std_mae([r['grade'] for r in rr],[r[model] for r in rr])[0] for model in ['Q','C']} for s,rr in result.items()}
    assert sum(error(r)>=2 for r in result['E24'])==7
    assert abs(regression['E24']['Q']-.776904761904762)<1e-10
    assert abs(regression['E24']['C']-.7761904761904762)<1e-10
    expected['results/iter_081/completion.json']=sha('results/iter_081/completion.json')
    return result, expected, regression

def bootstrap(rows, baseline, n=10000, progress=False):
    rng=np.random.default_rng(8201)
    pids=sorted({r['patient'] for r in rows},key=int)
    by={p:[r for r in rows if r['patient']==p] for p in pids}
    # Cache label-independent keys, preserving occurrence as final tie-break.
    bk={r['id']:key(r,baseline,baseline)[:-1] for r in rows}
    dk={r['id']:key(r,'D',baseline)[:-1] for r in rows}
    samples=[]
    started=time.monotonic()
    timing={}
    for i in range(n):
        chosen=rng.integers(0,len(pids),len(pids))
        rr=[(r,occ) for occ,idx in enumerate(chosen) for r in by[pids[idx]]]
        k=math.ceil(.25*len(rr))
        b=sorted(rr,key=lambda x:(*bk[x[0]['id']],x[1]))[:k]
        d=sorted(rr,key=lambda x:(*dk[x[0]['id']],x[1]))[:k]
        delta=sum(error(r)>=2 for r,o in d)-sum(error(r)>=2 for r,o in b)
        total=sum(error(r)>=2 for r,o in rr)
        samples.append(dict(n=len(rr),k=k,events=total,count_diff=delta,recall_diff=delta/total if total else None))
        if i==199:
            elapsed=time.monotonic()-started
            timing=dict(first200_s=elapsed,remaining_estimate_s=elapsed/200*(n-200))
            if progress:
                print(json.dumps(timing),flush=True)
    count=[x['count_diff'] for x in samples]
    recall=[x['recall_diff'] for x in samples if x['recall_diff'] is not None]
    return dict(samples=samples,count_ci95=np.percentile(count,[2.5,97.5]).tolist(),
                recall_ci95=np.percentile(recall,[2.5,97.5]).tolist() if recall else None,
                undefined_recall=n-len(recall),timing={**timing,'total_s':time.monotonic()-started})

def main():
    started=time.monotonic()
    inputs, hashes, regression=load_inputs()
    files=['review82_analysis.py','review82_verify.py','test_review82.py','sp75_metrics.py','../agent/runs/iter_082/plan.md','../agent/runs/iter_082/plan.json']
    protocol=dict(inputs=hashes,code={p:sha(p) for p in files},rules=RULES,python=sys.executable,numpy=np.__version__,new_model_calls=0)
    # Completed phases may only be reused with exact input/code/rule identity.
    if (ROOT/'completion.json').exists():
        assert read(ROOT/'protocol.json')==protocol
        for p,h in read(ROOT/'completion.json')['files'].items():
            assert sha(p)==h
        print('완료 산출물 재검증 통과'); return
    if (ROOT/'protocol.json').exists():
        assert read(ROOT/'protocol.json')==protocol
    else:
        save(ROOT/'protocol.json',protocol)
    baseline, selection_scores=select(inputs['V8'],'V8')
    selection=dict(split='V8',baseline=baseline,scores=selection_scores,protocol_sha256=sha(ROOT/'protocol.json'))
    if (ROOT/'selection.json').exists():
        assert read(ROOT/'selection.json')==selection
    else:
        save(ROOT/'selection.json',selection)
    # A partial analysis is never silently overwritten; use preserved phase artifacts for inspection.
    out={}
    ranklists={}
    for split,rows in inputs.items():
        out[split]={}
        ranklists[split]={}
        for name in NAMES+['D','Db']:
            ranklists[split][name]=[dict(id=r['id'],patient=r['patient'],risk=list(risk(r,name,baseline))) for r in rank(rows,name,baseline)]
            out[split][name]={'budgets':{str(rate):table(rows,name,baseline,rate) for rate in RULES['rates']},
                              'discrimination':{e:discrimination(rows,name,baseline,t) for e,t in [('e2',2),('e1',1)]}}
    rows=inputs['E24']
    boot=bootstrap(rows,baseline,progress=True)
    loo=[]
    for p in sorted({r['patient'] for r in rows},key=int):
        subset=[r for r in rows if r['patient']!=p]
        loo.append(dict(removed=p,n=len(subset),k=math.ceil(.25*len(subset)),diff=capture(subset,'D',baseline)-capture(subset,baseline,baseline)))
    tb=out['E24'][baseline]['budgets']['0.25']; td=out['E24']['D']['budgets']['0.25']
    extra=[r for r in rows if r['id'] in set(td['ids'])-set(tb['ids']) and error(r)>=2]
    lost=[r for r in rows if r['id'] in set(tb['ids'])-set(td['ids']) and error(r)>=2]
    diff=td['e2']['captured']-tb['e2']['captured']
    checks=dict(at_least_two=diff>=2,additional_two_patients=len({r['patient'] for r in extra})>=2,
                beats_all_c=all(td['e2']['captured']>out['E24'][n]['budgets']['0.25']['e2']['captured'] for n in NAMES),
                loo_nonnegative=all(x['diff']>=0 for x in loo),tie_robust=td['e2']['tie_min']-tb['e2']['tie_max']>0)
    decision='positive' if all(checks.values()) else ('negative' if diff<=0 else 'inconclusive')
    event_differences={}
    for event,threshold in [('e2',2),('e1',1)]:
        left=[r for r in rows if r['id'] in set(td['ids'])-set(tb['ids']) and error(r)>=threshold]
        right=[r for r in rows if r['id'] in set(tb['ids'])-set(td['ids']) and error(r)>=threshold]
        event_differences[event]=dict(net=len(left)-len(right),d_only_ids=[r['id'] for r in left],b_only_ids=[r['id'] for r in right],d_only_patients=sorted({r['patient'] for r in left},key=int),b_only_patients=sorted({r['patient'] for r in right},key=int))
    report=dict(event_differences=event_differences,baseline=baseline,regression=regression,tables=out,leave_one_patient_out=loo,
                count_diff=diff,recall_diff=diff/7,checks=checks,decision=decision,
                d_only_e2=extra,b_only_e2=lost,comparisons={n:td['e2']['captured']-out['E24'][n]['budgets']['0.25']['e2']['captured'] for n in NAMES},
                posthoc_best_c_capture=max(out['E24'][n]['budgets']['0.25']['e2']['captured'] for n in NAMES),
                count_ci95=boot['count_ci95'],recall_ci95=boot['recall_ci95'],undefined_recall=boot['undefined_recall'],
                bootstrap_timing=boot['timing'],analysis_wall_s=time.monotonic()-started,
                limitation='반복 개발 자료·oracle ROI·단일 checkpoint; 독립 확인과 온라인 비용 및 VLM 고유 효용 미검증')
    for name,obj in [('ranks.json',ranklists),('bootstrap.json',boot),('report.json',report)]:
        save(ROOT/name,obj)
    print(json.dumps({k:report[k] for k in ['baseline','count_diff','count_ci95','decision','checks']},ensure_ascii=False))

if __name__=='__main__':
    main()
