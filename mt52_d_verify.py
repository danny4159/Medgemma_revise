"""Production parser/집계 없이 원시 D 답변·paired CI·비용을 재계산한다."""
import json
import re
from collections import defaultdict
import numpy as np
from mt52_prepare import ROOT,OUT,save,sha256_file

def swept(intervals):
    events=defaultdict(int)
    for a,b in intervals:events[a]+=1;events[b]-=1
    active=0;last=0.;value=0.
    for t,change in sorted(events.items()):
        if active:value+=t-last
        active+=change;last=t
    assert active==0
    return value

def main():
    path=OUT/'eval/D24_report.json';r=json.loads(path.read_text())
    cs=json.loads((OUT/'data/D_inference.json').read_text());truth={x['title']:x['correct_answer'] for x in json.loads((OUT/'audit/D_private.json').read_text())}
    raw={};digests={}
    for p in sorted((OUT/'pilot/D24_caps2/records').glob('*/*.json')):
        x=json.loads(p.read_text());key=(x['spec']['case'],x['spec']['stage']);assert key not in raw;raw[key]=x
        digests[str(p.relative_to(ROOT))]=sha256_file(p)
    expected={(c['case_key'],s) for c in cs for s in ['T','D','U','C','R','H','X']+[f'F{i:02d}' for i in range(len(c['images']))]}
    assert set(raw)==expected and digests==r['integrity']['raw_digests']
    vectors={s:[] for s in 'TDCRX'};invalid=[];non_eos=[]
    for (case,s),x in raw.items():
        assert x['eos']==bool(x['tokens'] and x['tokens'][-1] in [1,106])
        if not x['eos']:non_eos.append((case,s))
    for c in cs:
        for s in vectors:
            text=raw[c['case_key'],s]['text'];lines=[l.strip() for l in text.splitlines() if l.strip()]
            ans=None
            if lines and lines[-1] in ['Answer: '+a for a in 'ABCDE'] and sum(bool(re.match(r'(?i)^Answer\s*:',l)) for l in lines)==1:ans=lines[-1][-1]
            if ans is None:invalid.append((c['case_key'],s))
            vectors[s].append(int(ans==truth[c['case_key']]))
    assert vectors==r['vectors'] and len(non_eos)==len(r['integrity']['non_eos']) and len(invalid)==len(r['integrity']['invalid_final'])
    rng=np.random.default_rng(5202);boot={k:[] for k in r['comparisons']}
    for _ in range(20000):
        ids=rng.integers(0,24,24)
        for key in boot:
            a,b=key.split('-');boot[key].append(sum(vectors[a][i]-vectors[b][i] for i in ids)/24)
    for key,vals in boot.items():
        q=[2.5,97.5] if key=='D-T' else [.625,99.375]
        assert np.allclose(np.percentile(vals,q),r['comparisons'][key]['CI'],atol=1e-12,rtol=0)
    ints=defaultdict(list)
    for x in raw.values():ints[x['gpu']].append((x['t_start'],x['t_end']))
    total=sum(x['t_end']-x['t_start'] for x in raw.values())
    assert abs(total-r['actual_shared_execution']['runtime_sum'])<1e-6
    for g,v in ints.items():assert abs(swept(v)-r['actual_shared_execution']['gpu_interval_union'][g])<1e-6
    for s in vectors:
        cost=0.;it=ot=0
        for c in cs:
            stages=[s] if s in 'TD' else ['H','X'] if s=='X' else [f'F{i:02d}' for i in range(len(c['images']))]+['U',s]
            for stage in stages:
                x=raw[c['case_key'],stage];cost+=x['t_end']-x['t_start'];it+=len(x['input_tokens']);ot+=len(x['tokens'])
        assert abs(cost-r['cost_summary'][s]['generation_seconds'])<1e-6
        assert (it,ot)==(r['cost_summary'][s]['input_tokens'],r['cost_summary'][s]['output_tokens'])
    assert swept([(0,2),(1,3),(5,6)])==4 # overlapping workers counted once
    save(OUT/'eval/D24_independent_verify.json',{'status':'PASS','requests':len(raw),'cases':24,'paired_CIs':len(boot),
        'raw_digests':digests,'report_sha256':sha256_file(path),'verifier_sha256':sha256_file(__file__),
        'scope':'D exploration only; no E hypothesis validation','costs_verified':['shared once','C/R each include F/U','GPU interval sweep','input/output token sums']})
    print('PASS',len(raw),'5 paired CI and cost totals')

if __name__=='__main__':main()
