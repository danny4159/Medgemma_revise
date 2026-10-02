"""실험 job만 집계한다. 변조 fixture의 복사본은 실행량으로 세지 않는다."""
import json
from collections import defaultdict
from mt52_prepare import ROOT,OUT,save,sha256_file
from mt52_d_report import union

def main():
    jobs=['pilot/P4_2w','pilot/P4_4w','pilot/D8_graph','pilot/D8_graph_v2','pilot/D24_caps2','tests/resume_current']
    rows=[];intervals=defaultdict(list);total=0;seconds=0.;unknown=0.
    for name in jobs:
        job=OUT/name;records=[json.loads(p.read_text()) for p in job.glob('records/*/*.json')]
        assert len({r['request_id'] for r in records})==len(records)
        n=len(records);runtime=sum(r['runtime'] for r in records);total+=n;seconds+=runtime
        attempt_rows=[];peak=defaultdict(float)
        for r in records:intervals[r['gpu']].append((r['t_start'],r['t_end']))
        for ad in sorted(job.glob('attempts/*')):
            completed={r['request_id'] for r in records if r['attempt']==ad.name}
            starts=[json.loads(p.read_text()) for p in ad.glob('*_start.json')]
            samples=[json.loads(s) for s in (ad/'resources.jsonl').read_text().splitlines()] if (ad/'resources.jsonl').exists() else []
            last=max((s['time'] for s in samples),default=0.)
            for s in samples:
                for line in s['gpu'].strip().splitlines():
                    g,mem,util=[x.strip() for x in line.split(',')];peak[g]=max(peak[g],float(mem))
            undone=[s for s in starts if s['request_id'] not in completed]
            low=sum(max(0,last-s['time']) for s in undone);unknown+=low
            attempt_rows.append({'attempt':ad.name,'committed':len(completed),'unfinished':len(undone),'unfinished_seconds_lower_bound':low,
                'observed_wall_span':last-min((s['time'] for s in samples),default=last),
                'load_seconds':sum(json.loads(p.read_text())['load_seconds'] for p in ad.glob('worker*_env.json'))})
        rows.append({'job':name,'committed_generations':n,'generation_runtime_sum':runtime,'sampled_GPU_peak_MiB':dict(peak),
            'max_record_reserved_GiB':max((r['peak_reserved_GiB'] for r in records),default=0),'attempts':attempt_rows})
    standalone=[json.loads((OUT/'sanity'/f'generate_{s}.json').read_text()) for s in ['two','longest']]
    save(OUT/'usage_ledger.json',{'jobs':rows,'job_generations':total,'standalone_sanity_generations':2,
        'completed_generation_seconds':seconds+sum(r['runtime'] for r in standalone),
        'job_GPU_union_seconds':{g:union(v) for g,v in intervals.items()},
        'unfinished_observed_seconds_lower_bound':unknown,
        'note':'Includes invalid initial F-index pilot and cap/restart overhead. No test-fixture copies. Interrupted request exact exit timestamps unavailable; lower bounds reported separately. Standalone sanity has duration but no absolute interval so excluded from union.',
        'source_sha256':sha256_file(__file__)})
    print('generations',total+2,'completed seconds',seconds+sum(r['runtime'] for r in standalone),'unfinished lower bound',unknown)

if __name__=='__main__':main()
