"""iter_064 독립 재계산: s64_eval/msd56_run parser를 import하지 않고 원시 JSONL+labels에서 BA·sens·spec·L_* 점추정과 case paired bootstrap(seed64)을 재구현해 report와 대조.
사용: python s64_verify_eval.py <split> -> results/iter_064/<split>/independent_verify.json (존재 시 거부)"""
import glob, json, os, re, sys, random

split = sys.argv[1]
ROOT = f'results/iter_064/{split}'
out = {'split': split, 'models': {}, 'max_abs_diff': 0.0}
lab = json.load(open(f'results/iter_064/data/labels_{split}.json'))
assert not os.path.exists(f'{ROOT}/independent_verify.json')


def parse(t):
    t = t.replace('<end_of_turn>', '').strip()
    t = re.sub(r'[\s.!?,;:]+$', '', t).strip().upper()
    return t if t in ('PRESENT', 'ABSENT') else None


for m in ('qwen', 'medgemma'):
    rep = json.load(open(f'{ROOT}/report_{m}.json'))
    pc = {}  # (case,cond,target)->correct
    inval = 0
    for f in glob.glob(f'{ROOT}/gen_{m}/worker*.jsonl'):
        for l in open(f):
            r = json.loads(l)
            p = parse(r['attempts'][-1]['text'])
            inval += p is None
            pc[(lab[r['rid']]['case'], lab[r['rid']]['cond'], lab[r['rid']]['target'])] = int(p == lab[r['rid']]['answer'])
    cases = sorted({k[0] for k in pc})
    assert len(pc) == 10 * len(cases)

    def grp(cs, cl):
        se = sum(pc[(c, k, 'P')] for c in cl for k in cs) / (len(cs) * len(cl))
        sp = sum(pc[(c, k, 'N')] for c in cl for k in cs) / (len(cs) * len(cl))
        return se, sp

    G = {'S': ['S'], 'R': ['R1', 'R2'], 'C': ['C1', 'C2'], 'R1': ['R1'], 'R2': ['R2'], 'C1': ['C1'], 'C2': ['C2']}
    ba = lambda g, cl: sum(grp(G[g], cl)) / 2
    res = {'invalid_total': inval, 'groups': {}, 'diffs': {}}
    mx = 0.0
    for g in G:
        se, sp = grp(G[g], cases)
        res['groups'][g] = {'BA': (se + sp) / 2, 'sens': se, 'spec': sp}
        d = abs(res['groups'][g]['BA'] - rep['primary_invalid_as_wrong']['groups'][g]['BA'])
        d = max(d, abs(se - rep['primary_invalid_as_wrong']['groups'][g]['sens']), abs(sp - rep['primary_invalid_as_wrong']['groups'][g]['spec']))
        mx = max(mx, d)
    P = {'L_count': ('S', 'R'), 'L_content': ('R', 'C'), 'L_total': ('S', 'C'), 'L_content_pos1': ('R1', 'C1'), 'L_content_pos2': ('R2', 'C2')}
    for k, (a, b) in P.items():
        pt = ba(a, cases) - ba(b, cases)
        mx = max(mx, abs(pt - rep['primary_invalid_as_wrong']['diffs'][k]['point']))
        res['diffs'][k] = {'point': pt}
    # bootstrap(독립 구현: numpy 없이; seed 체계가 달라 CI는 동일 난수가 아니라 근사 일치만 확인)
    rnd = random.Random(64)
    n = len(cases)
    bs = {k: [] for k in P}
    for _ in range(4000):
        cl = [cases[rnd.randrange(n)] for _ in range(n)]
        for k, (a, b) in P.items():
            bs[k].append(ba(a, cl) - ba(b, cl))
    for k in P:
        v = sorted(bs[k])
        lo, hi = v[int(0.025 * len(v))], v[int(0.975 * len(v)) - 1]
        res['diffs'][k]['ci95_indep'] = [lo, hi]
        rc = rep['primary_invalid_as_wrong']['diffs'][k]['ci95']
        res['diffs'][k]['ci_report'] = rc
        res['diffs'][k]['ci_max_abs_gap'] = max(abs(lo - rc[0]), abs(hi - rc[1]))
    res['max_abs_diff_point_estimates'] = mx
    res['invalid_matches_report'] = inval == sum(v['invalid'] for v in rep['format'].values())
    out['models'][m] = res
    out['max_abs_diff'] = max(out['max_abs_diff'], mx)
json.dump(out, open(f'{ROOT}/independent_verify.json', 'w'), indent=1)
print('max point diff', out['max_abs_diff'], {m: {k: round(v['ci_max_abs_gap'], 3) for k, v in r['diffs'].items()} for m, r in out['models'].items()})
