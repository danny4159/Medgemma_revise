"""D24 탐색 점수·비용 장부. E 본 가설 판정을 생성하지 않는다."""
import json
from collections import defaultdict
import numpy as np
from mt52_prepare import ROOT,OUT,save,sha256_file
from mt52_spec import parse
from mt52_verify import verify

def union(intervals):
    total=0.;end=None
    for a,b in sorted(intervals):
        assert b>=a
        total+=b-max(a,end) if end is not None and b>end else b-a if end is None else 0
        end=max(end,b) if end is not None else b
    return total

def report():
    job=OUT/'pilot/D24_caps2';audit=verify(job)
    cs=json.loads((OUT/'data/D_inference.json').read_text());truth={r['title']:r['correct_answer'] for r in json.loads((OUT/'audit/D_private.json').read_text())}
    allr=[json.loads(p.read_text()) for p in sorted((job/'records').glob('*/*.json'))]
    by={(r['spec']['case'],r['spec']['stage']):r for r in allr};vectors={s:[] for s in ['T','D','C','R','X']};costs=defaultdict(list);rows=[]
    for c in cs:
        key=c['case_key'];n=len(c['images']);row={'case':key,'truth':truth[key],'n_images':n,'outputs':{}}
        for s in vectors:
            r=by[key,s];ans=parse(r['text']);correct=int(ans==truth[key]);vectors[s].append(correct)
            row['outputs'][s]={'answer':ans,'correct':correct,'eos':r['eos'],'input_tokens':len(r['input_tokens']),'output_tokens':len(r['tokens'])}
            stages=[s] if s in ('T','D') else [f'F{i:02d}' for i in range(n)]+['U',s] if s in ('C','R') else ['H','X']
            rs=[by[key,x] for x in stages]
            costs[s].append({'case':key,'requests':len(rs),'generation_seconds':sum(x['runtime'] for x in rs),
                'elapsed_span_seconds':max(x['t_end'] for x in rs)-min(x['t_start'] for x in rs),
                'input_tokens':sum(len(x['input_tokens']) for x in rs),'output_tokens':sum(len(x['tokens']) for x in rs),
                'peak_reserved_GiB':max(x['peak_reserved_GiB'] for x in rs)})
        rows.append(row)
    comparisons={}
    inds=np.random.default_rng(5202).integers(0,len(cs),(20000,len(cs)))
    for a,b in [('D','C'),('R','C'),('D','R'),('D','X'),('D','T')]:
        delta=np.array(vectors[a])-np.array(vectors[b]);q=[2.5,97.5] if b=='T' else [.625,99.375]
        comparisons[a+'-'+b]={'difference':float(delta.mean()),'CI':np.percentile(delta[inds].mean(1),q).tolist(),
            'CI_level':.95 if b=='T' else .9875,'discordant':int(np.count_nonzero(delta)),
            'a_only':int((delta==1).sum()),'b_only':int((delta==-1).sum()),'scope':'D24 exploratory only'}
    intervals=defaultdict(list)
    for r in allr:intervals[r['gpu']].append((r['t_start'],r['t_end']))
    attempts=[]
    for ad in sorted((job/'attempts').iterdir()):
        resources=[json.loads(x) for x in (ad/'resources.jsonl').read_text().splitlines()] if (ad/'resources.jsonl').exists() else []
        completed=[r for r in allr if r['attempt']==ad.name];done={r['request_id'] for r in completed}
        starts=[json.loads(p.read_text()) for p in ad.glob('*_start.json')];unfinished=[x for x in starts if x['request_id'] not in done]
        last=max((r['time'] for r in resources),default=0)
        attempts.append({'attempt':ad.name,'committed':len(completed),'started':len(starts),'unfinished':len(unfinished),
            'unfinished_observed_seconds_lower_bound':sum(max(0,last-x['time']) for x in unfinished),
            'last_resource_time':last,'first_resource_time':min((r['time'] for r in resources),default=0),
            'load_seconds':sum(json.loads(p.read_text())['load_seconds'] for p in ad.glob('worker*_env.json')),
            'completion':json.loads((ad/'completion.json').read_text()) if (ad/'completion.json').exists() else None})
    costs_summary={s:{'generation_seconds':sum(x['generation_seconds'] for x in rs),'input_tokens':sum(x['input_tokens'] for x in rs),
        'output_tokens':sum(x['output_tokens'] for x in rs),'elapsed_span_p50':float(np.median([x['elapsed_span_seconds'] for x in rs])),
        'elapsed_span_p95':float(np.percentile([x['elapsed_span_seconds'] for x in rs],95))} for s,rs in costs.items()}
    result={'scope':'D24 development exploration; E data gate failed, hypothesis untested','integrity':audit,
        'accuracy':{s:{'correct':sum(v),'n':len(v),'accuracy':sum(v)/len(v)} for s,v in vectors.items()},
        'comparisons':comparisons,'vectors':vectors,'per_case':rows,'deployment_costs':dict(costs),'cost_summary':costs_summary,
        'actual_shared_execution':{'requests':len(allr),'runtime_sum':sum(r['runtime'] for r in allr),
            'gpu_interval_union':{g:union(v) for g,v in intervals.items()},'attempts':attempts,
            'note':'F/U actually counted once. Deployment C and R each include F/U. Elapsed spans include interruptions and intervening shared DAG stages; not isolated deployment latency. Unfinished work is a lower bound, not exact device time.'},
        'technical_gate_pass':not audit['non_eos'],'E_run':False,
        'sources':{str(p.relative_to(ROOT)):sha256_file(p) for p in [ROOT/'mt52_d_report.py',ROOT/'mt52_verify.py',ROOT/'mt52_spec.py',OUT/'audit/D_private.json',OUT/'audit/data_gate.json']}}
    save(OUT/'eval/D24_report.json',result)
    print(result['accuracy']);print('nonEOS',len(audit['non_eos']),'invalid',len(audit['invalid_final']))

if __name__=='__main__':report()
