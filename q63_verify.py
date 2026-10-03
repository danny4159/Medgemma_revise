"""iter_063 독립 재계산: 원시 JSONL·요청·labels에서 평가기 코드(q63_eval/mri61_parse) 없이 2×2·L/G/I·bootstrap·혼동표를 다시 계산해 report와 대조.
사용: python q63_verify.py --report results/iter_063/eval/report.json [--lenient] --out results/iter_063/eval/verify.json
"""
import argparse, collections, glob, hashlib, json, re, sys
import numpy as np

CL = None


def jl(p):
    return [json.loads(l) for l in open(p) if l.strip()]


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def parse(text, lenient):
    ls = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if not ls:
        return None
    last = ls[-1]
    m = re.fullmatch(r'ANSWER:\s*([A-E])', last)
    if m:
        return m.group(1)
    if len(re.findall(r'\\boxed\{', last)) == 1:
        m = re.fullmatch(r'(?:\*\*)?Final Answer:?(?:\*\*)?.*\\boxed\{\s*([A-E])\s*\}.*', last, flags=re.I)
        if m:
            return m.group(1)
    if lenient:
        m = re.fullmatch(r'\**\s*answer\s*:\s*\**\s*([A-E])\s*\**\.?', last, flags=re.I)
        if m:
            return m.group(1).upper()
    return None


def load(d):
    out = {}
    for f in sorted(glob.glob(f'{d}/worker*.jsonl')):
        for r in jl(f):
            assert r['rid'] not in out
            out[r['rid']] = r
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--report', required=True); ap.add_argument('--out', required=True); ap.add_argument('--lenient', action='store_true')
    a = ap.parse_args()
    rep = json.load(open(a.report))
    cl = list(json.load(open('results/iter_063/data/E10_labels.json')))
    labR = json.load(open('results/iter_063/data/E10_labels.json'))
    rowsR = {r['rid']: r for r in jl('results/iter_063/data/E10_requests.jsonl')}
    rowsO = {r['rid']: r for r in jl('results/iter_062/data/E21_requests.jsonl') if r['cluster_id'] in cl and r['cond'] in ('T', 'J')}
    src = {'qwen': {'O': 'results/iter_062/gen_E21_qwen', 'R': 'results/iter_063/gen_E10_qwen'},
           'medgemma': {'O': 'results/iter_061/gen_E24', 'R': 'results/iter_063/gen_E10_medgemma'}}
    out, maxdiff = {}, 0.0
    idx = np.random.default_rng(63).integers(0, 10, (10000, 10))
    for model, d in src.items():
        acc, conf = {}, collections.defaultdict(collections.Counter)
        for tag, rows in (('O', rowsO), ('R', rowsR)):
            recs = load(d[tag])
            for rid, q in rows.items():
                text = recs[rid]['attempts'][-1]['text']
                L = parse(text, a.lenient)
                orig = q['perm']['ABCDE'.index(L)] if L else None
                gt = labR[q['cluster_id']]['gt_orig_index']
                acc[(tag, q['cond'], q['order'], q['cluster_id'])] = int(orig == gt) if orig is not None else 0
                conf[(tag, q['cond'])][labR[q['cluster_id']]['options'][orig] if orig is not None else 'INVALID'] += 1
        v = lambda tag, cond: np.array([(acc[(tag, cond, 'F', c)] + acc[(tag, cond, 'R', c)]) / 2 for c in cl])
        OT, OJ, RT, RJ = v('O', 'T'), v('O', 'J'), v('R', 'T'), v('R', 'J')
        eff = {'L': OT - RT, 'G': RJ - RT, 'I': (RJ - RT) - (OJ - OT)}
        m = {}
        for k, x in eff.items():
            est, lo, hi = float(x.mean()), *[float(np.percentile(x[idx].mean(1), p)) for p in (2.5, 97.5)]
            r = rep['models'][model]['both'][k]
            maxdiff = max(maxdiff, abs(est - r['est']), abs(lo - r['ci95'][0]), abs(hi - r['ci95'][1]))
            m[k] = {'est': est, 'ci95': [lo, hi]}
        for nm, x in (('O_T', OT), ('O_J', OJ), ('R_T', RT), ('R_J', RJ)):
            maxdiff = max(maxdiff, abs(float(x.mean()) - rep['models'][model]['both']['acc'][nm]))
            m[nm] = float(x.mean())
        gts = collections.Counter(labR[c]['options'][labR[c]['gt_orig_index']] for c in cl)
        m['gt_class_counts'] = dict(gts)
        m['majority_class_prior_acc'] = max(gts.values()) / 10
        m['answer_distribution'] = {f'{t}_{c}': dict(v_) for (t, c), v_ in conf.items()}
        out[model] = m
    res = {'max_abs_diff_vs_report': maxdiff, 'match': maxdiff < 1e-9, 'parser': 'lenient' if a.lenient else 'v2', 'models': out}
    json.dump(res, open(a.out, 'w'), indent=1)
    print('max diff', maxdiff)
    sys.exit(0 if res['match'] else 1)


if __name__ == '__main__':
    main()
