"""iter_067 독립 재계산: 원시 worker JSONL의 cand_logits에서 평가 모듈 import 없이 BA02를 다시 계산하고 report.json과 대조.
추가(사후 탐색, 사전 기준 아님): 0 vs II 행에서 p(C)(Modic II 후보 확률)의 AUROC — argmax가 퇴화(항상 같은 class)했을 때 순위 신호가 있는지 구분용.
사용: python sp67_verify.py <gen_root> <truth_labels.json> <report.json> <out.json>"""
import glob, json, math, sys


def softmax(v):
    m = max(v); e = [math.exp(x - m) for x in v]; s = sum(e)
    return [x / s for x in e]


def auroc(pos, neg):
    n = 0.0
    for p in pos:
        for q in neg:
            n += 1.0 if p > q else 0.5 if p == q else 0.0
    return n / (len(pos) * len(neg))


def main():
    gen, lab, rep, out = sys.argv[1:5]
    truth = {(p['patient'], i['k']): i['modic'] for p in json.load(open(lab)) for i in p['ivd']}
    report = json.load(open(rep))
    res = {}
    for model, r in report['models'].items():
        rows = {}
        for f in glob.glob(f'{gen}/{model}/worker*.jsonl'):
            for l in open(f):
                if l.endswith('\n') and l.strip():
                    x = json.loads(l); rows[x['rid']] = x
        by = {}
        for x in rows.values():
            by.setdefault(x['cond'], []).append(x)
        res[model] = {}
        for c, xs in by.items():
            name = {'RT1': 'R'}.get(c, c)
            hit = {0: [0, 0], 2: [0, 0]}
            for x in xs:
                y = truth[(x['patient'], x['ivd'])]
                if y in hit:
                    hit[y][0] += 1
                    hit[y][1] += int(max(range(4), key=lambda i: (x['cand_logits'][i], -i)) == y)
            ba = 0.5 * (hit[0][1] / hit[0][0] + hit[2][1] / hit[2][0])
            pC0 = [softmax(x['cand_logits'])[2] for x in xs if truth[(x['patient'], x['ivd'])] == 0]
            pC2 = [softmax(x['cand_logits'])[2] for x in xs if truth[(x['patient'], x['ivd'])] == 2]
            res[model][name] = {'BA02_indep': ba, 'BA02_report': r['cond'][name]['BA02'], 'diff': abs(ba - r['cond'][name]['BA02']),
                                'posthoc_AUROC_pC_II_vs_0_rowlevel': auroc(pC2, pC0), 'n_II': len(pC2), 'n_0': len(pC0)}
    json.dump(res, open(out, 'w'), indent=1)
    for m, d in res.items():
        print(m, {k: (round(v['BA02_indep'], 3), round(v['diff'], 12), round(v['posthoc_AUROC_pC_II_vs_0_rowlevel'], 3)) for k, v in d.items()})


if __name__ == '__main__':
    main()
