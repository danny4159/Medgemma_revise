"""D8 처리량 비교 집계: 같은 24개 계승 CURE 요청을 GPU당 1 worker(A)와 GPU당 2 worker(B)로 재생성한 실행을 비교한다.
생성 구간 = 첫 request_start ~ 마지막 request_saved(모델 로딩 제외). 로딩은 별도 보고. token 동등성은 계승 행과 비교한 값이다.
python report86_tput.py <out.json> <label=glob_of_dirs> [...]
"""
import glob
import json
import sys

from report86_common import R86, save, read_jsonl_complete


def summarize(dirs):
    ev, recs, loads, peaks = [], [], [], []
    for d in dirs:
        e = read_jsonl_complete(d + '/executions.jsonl')
        ev += [x for x in e if x['event'] in ('request_start', 'request_saved')]
        loads += [x['loading_s'] for x in e if x['event'] == 'start' and 'loading_s' in x]
        r = read_jsonl_complete(d + '/outputs.jsonl')
        recs += r
        peaks += [a['peak_mem_reserved_gb'] for x in r for a in x['attempts']]
        rr = sorted(glob.glob(d + '/regress_result_*.json'))
        assert len(rr) == 1, d
    t0 = min(x['time'] for x in ev if x['event'] == 'request_start')
    t1 = max(x['time'] for x in ev if x['event'] == 'request_saved')
    res_eq = []
    for d in dirs:
        res_eq += [i['equal'] for i in json.load(open(sorted(glob.glob(d + '/regress_result_*.json'))[0]))['items']]
    secs = sorted(sum(a['runtime_s'] for a in x['attempts']) for x in recs)
    return {'dirs': [d.split('/')[-1] for d in dirs], 'n_requests': len(recs), 'window_s': t1 - t0, 'req_per_min': 60 * len(recs) / (t1 - t0),
            'loading_s': loads, 'tokens_equal_to_inherited': sum(res_eq), 'of': len(res_eq),
            'p50_s': secs[len(secs) // 2], 'p95_s': secs[int(0.95 * (len(secs) - 1))], 'max_s': secs[-1],
            'peak_reserved_gib_max': max(peaks)}


if __name__ == '__main__':
    out = sys.argv[1]
    res = {}
    for a in sys.argv[2:]:
        label, g = a.split('=')
        res[label] = summarize(sorted(glob.glob(g)))
    save(out, res)
    print(json.dumps(res, indent=1))
