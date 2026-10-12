"""iter_123: 두 stage(같은 요청)의 출력 token/text 동일성과 처리량 비교. usage: mr123_compare_stages.py A B"""
import json, os, sys
import mr123_run as R

def load(st):
    d = {}
    for fn in sorted(os.listdir(R.GEN + st)):
        if fn.startswith('worker_'):
            for r in R.read_jsonl(R.GEN + st + '/' + fn):
                assert r['id'] not in d
                d[r['id']] = r
    return d

A, B = load(sys.argv[1]), load(sys.argv[2])
assert set(A) == set(B)
same_in = sum(A[k]['input_ids_sha'] == B[k]['input_ids_sha'] for k in A)
same_txt = sum(A[k]['text'] == B[k]['text'] for k in A)
same_state = sum(A[k]['state'] == B[k]['state'] for k in A)
def thr(D):
    t = [r['t_end'] for r in D.values()]
    first = min(r['t_end'] - r['wall_s'] for r in D.values())
    span = max(t) - first
    return dict(n=len(D), gen_span_s=span, req_per_min=len(D) / span * 60, mean_wall_s=sum(r['wall_s'] for r in D.values()) / len(D),
                peak_mem_mib=max(r['peak_mem_mib'] for r in D.values()), n_workers=len({r['wid'] for r in D.values()}))
out = dict(A=sys.argv[1], B=sys.argv[2], n=len(A), same_input_ids=same_in, same_text=same_txt, same_state=same_state, thr_A=thr(A), thr_B=thr(B))
json.dump(out, open(R.D.RES + f'tests/compare_{sys.argv[1]}_{sys.argv[2]}.json', 'w'), indent=1)
print(json.dumps(out, indent=1))
