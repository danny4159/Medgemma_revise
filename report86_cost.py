"""stage 생성 비용 집계(CPU): 시스템별 요청 수·생성 초·p95·재시도·peak reserved VRAM·창(window) 처리량·로딩. 의미 평가 시간은 포함하지 않는다.
python report86_cost.py <stage> <out.json> [launch_name_prefix ...]
"""
import glob
import json
import sys

import numpy as np

from report86_common import R86, SYSTEMS, save, read_jsonl_complete


def main():
    stage, out = sys.argv[1], sys.argv[2]
    res = {'stage': stage, 'systems': {}}
    for s in SYSTEMS:
        dirs = sorted(glob.glob(str(R86 / stage / s / 'shard*')))
        recs, ev, loads = [], [], []
        for d in dirs:
            recs += read_jsonl_complete(d + '/outputs.jsonl')
            e = read_jsonl_complete(d + '/executions.jsonl')
            ev += [x for x in e if x['event'] in ('request_start', 'request_saved')]
            loads += [x['loading_s'] for x in e if x['event'] == 'start' and 'loading_s' in x]
        if not recs:
            continue
        secs = np.array([sum(a['runtime_s'] for a in r['attempts']) for r in recs])
        t0 = min(x['time'] for x in ev if x['event'] == 'request_start')
        t1 = max(x['time'] for x in ev if x['event'] == 'request_saved')
        res['systems'][s] = {'n_records': len(recs), 'n_shards': len(dirs), 'generation_s_sum': float(secs.sum()), 'generation_s_mean': float(secs.mean()),
                              'generation_s_p95': float(np.percentile(secs, 95)), 'generation_s_max': float(secs.max()),
                              'tokens_mean': float(np.mean([sum(a['n_new'] for a in r['attempts']) for r in recs])),
                              'requests_with_retry': sum(len(r['attempts']) > 1 for r in recs),
                              'final_non_eos': sum(not r['attempts'][-1]['ended_eos'] for r in recs),
                              'peak_reserved_gib_max': max(a['peak_mem_reserved_gb'] for r in recs for a in r['attempts']),
                              'loading_s': loads, 'window_s': t1 - t0, 'req_per_min_window': 60 * len(recs) / (t1 - t0),
                              'interrupted_requests': len({x['id'] for x in ev if x['event'] == 'request_start'}) - len({x['id'] for x in ev if x['event'] == 'request_saved'})}
    gpu = {}
    for pref in sys.argv[3:]:
        for f in glob.glob(str(R86 / 'launches' / f'{pref}_*' / 'resource.jsonl')):
            for ln in open(f):
                d = json.loads(ln)
                for g, (u, t) in d['smi'].items():
                    gpu.setdefault(pref, {})[g] = max(gpu.get(pref, {}).get(g, 0), u)
    res['gpu_max_used_mib_by_launch'] = gpu
    save(out, res)
    print(json.dumps(res, indent=1))


if __name__ == '__main__':
    main()
