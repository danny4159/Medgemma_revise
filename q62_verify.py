"""iter_062 독립 재계산: q62_eval.py의 코드를 import하지 않고 원시 JSONL에서 점추정치와 bootstrap CI를 다시 계산해 report와 대조.
parser는 별도 정규식으로 구현한다(마지막 비공백 줄이 'ANSWER: X' 또는 Final Answer ... \\boxed{X}).
사용: python q62_verify.py --out results/iter_062/eval/verify.json
"""
import argparse, glob, hashlib, json, re, sys
import numpy as np


def H(s):
    return hashlib.sha256(s.encode()).hexdigest()


def letter(text):
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
    return None


def recs(d):
    out = {}
    for f in glob.glob(f'{d}/worker*.jsonl'):
        for l in open(f):
            if l.strip():
                r = json.loads(l)
                assert r['rid'] not in out
                out[r['rid']] = r
    return out


def main(a):
    rows = [json.loads(l) for l in open(a.requests) if l.strip()]
    labels = json.load(open(a.labels))
    rep = json.load(open(a.report))
    cids = list(labels)
    NB = 10000
    idx = np.random.default_rng(61).integers(0, len(cids), (NB, len(cids)))
    tab = {}
    for name, d in (('MedGemma', a.medgemma_dir), ('Qwen2.5-VL-7B', a.qwen_dir)):
        R = recs(d)
        ans = {}
        for r in rows:
            L = letter(R[r['rid']]['attempts'][-1]['text'])
            ans[(r['cluster_id'], r['order'], r['cond'])] = None if L is None else r['perm']['ABCDE'.index(L)]
        v = {k: [] for k in ('T', 'J', 'Smean', 'V')}
        per_order = {o: {k: [] for k in ('T', 'J', 'Smean', 'V')} for o in 'FR'}
        for c in cids:
            lab = labels[c]
            gt = lab['gt_orig_index']
            opts = lab['options']
            for o in 'FR':
                per_order[o]['T'].append(float(ans[(c, o, 'T')] == gt))
                per_order[o]['J'].append(float(ans[(c, o, 'J')] == gt))
                ss = [ans[(c, o, f"S{i + 1}")] for i in range(lab['K'])]
                per_order[o]['Smean'].append(sum(x == gt for x in ss) / len(ss))
                cnt = {}
                for x in ss:
                    if x is not None:
                        cnt[x] = cnt.get(x, 0) + 1
                if cnt:
                    m = max(cnt.values())
                    pick = sorted([k for k, n in cnt.items() if n == m], key=lambda k: H(opts[k]))[0]
                    per_order[o]['V'].append(float(pick == gt))
                else:
                    per_order[o]['V'].append(0.0)
        for k in v:
            v[k] = [(per_order['F'][k][i] + per_order['R'][k][i]) / 2 for i in range(len(cids))]
        tab[name] = {k: np.array(x) for k, x in v.items()}
    maxdiff, checks = 0.0, []
    def chk(name, got, want):
        nonlocal maxdiff
        d = abs(got - want)
        maxdiff = max(maxdiff, d)
        checks.append({'name': name, 'got': got, 'report': want, 'abs_diff': d})
    for name, t in tab.items():
        m = rep['models'][name]['all']
        for k in ('T', 'J', 'Smean', 'V'):
            chk(f'{name} {k}', float(t[k].mean()), m[k])
        for nm, (x, y) in {'J-T': ('J', 'T'), 'V-T': ('V', 'T'), 'V-J': ('V', 'J'), 'Smean-J': ('Smean', 'J')}.items():
            d = t[x] - t[y]
            mm = d[idx].mean(1)
            chk(f'{name} {nm} est', float(d.mean()), m[nm]['est'])
            chk(f'{name} {nm} lo', float(np.percentile(mm, 2.5)), m[nm]['ci95'][0])
            chk(f'{name} {nm} hi', float(np.percentile(mm, 97.5)), m[nm]['ci95'][1])
    q, g = tab['Qwen2.5-VL-7B'], tab['MedGemma']
    for nm, (x, y) in {'J-T': ('J', 'T'), 'V-T': ('V', 'T'), 'V-J': ('V', 'J')}.items():
        d = (q[x] - q[y]) - (g[x] - g[y])
        mm = d[idx].mean(1)
        key = f'both_orders:(Qwen {nm}) - (MedGemma {nm})'
        chk(key + ' est', float(d.mean()), rep['cross_model'][key]['est'])
        chk(key + ' lo', float(np.percentile(mm, 2.5)), rep['cross_model'][key]['ci95'][0])
        chk(key + ' hi', float(np.percentile(mm, 97.5)), rep['cross_model'][key]['ci95'][1])
    res = {'n_checks': len(checks), 'max_abs_diff': maxdiff, 'pass': maxdiff < 1e-9, 'checks': checks}
    json.dump(res, open(a.out, 'w'), indent=1)
    print('verify', len(checks), 'max diff', maxdiff, 'PASS' if res['pass'] else 'FAIL')
    if not res['pass']:
        sys.exit(1)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--requests', default='results/iter_062/data/E21_requests.jsonl')
    ap.add_argument('--labels', default='results/iter_062/data/E21_labels.json')
    ap.add_argument('--qwen-dir', default='results/iter_062/gen_E21_qwen')
    ap.add_argument('--medgemma-dir', default='results/iter_061/gen_E24')
    ap.add_argument('--report', default='results/iter_062/eval/report.json')
    ap.add_argument('--out', default='results/iter_062/eval/verify.json')
    main(ap.parse_args())
