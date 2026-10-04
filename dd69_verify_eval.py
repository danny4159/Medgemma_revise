"""iter_069 독립 재계산: 원시 worker*.jsonl 텍스트와 labels.json 만으로 confusion/BA를 별도 구현으로 계산해 report_main.json과 대조.
dd69_eval/dd69_spec 의 parser·gt 함수를 import 하지 않는다. 결과 results/iter_069/eval/independent_verify.json (x 모드)."""
import glob
import json
import re
import sys

LAB = json.load(open('results/iter_069/data/labels.json'))
rep = json.load(open('results/iter_069/eval/report_main.json'))
SETS = {'SD': {'HIGH', 'NOT_HIGH', 'UNCERTAIN'}, 'SA': {'LOW', 'NOT_LOW', 'UNCERTAIN'}}


def norm(t):
    t = re.sub(r'<end_of_turn>', '', t).strip()
    t = re.sub(r'[\s.!?,;:]+$', '', t).strip().upper()
    return t


out, ok = {}, True
for model in ('medgemma', 'qwen'):
    rows = {}
    for f in glob.glob(f'results/iter_069/gen/main_{model}/worker*.jsonl'):
        for line in open(f):
            r = json.loads(line)
            rows[r['rid']] = r
    assert len(rows) == 140
    conf = {}
    per = {}
    for rid, r in rows.items():
        m = re.fullmatch(r'c(\d+)_(\w+)', rid)
        case, cond = m.group(1), m.group(2)
        a = norm(r['attempts'][-1]['text'])
        allowed = SETS.get(cond, {'YES', 'NO', 'UNCERTAIN'})
        a = a if a in allowed else 'INVALID'
        lab = LAB[case]['label']
        g = 'HIGH' if cond == 'SD' else (('LOW' if lab == 'LOW' else 'NOT_LOW') if cond == 'SA' else ('YES' if lab == 'LOW' else 'NO'))
        conf.setdefault(cond, {})
        k = f'gt={g}|ans={a}'
        conf[cond][k] = conf[cond].get(k, 0) + 1
        per[(case, cond)] = (a, g)

    def ba(cond_fn):
        tp = tn = np_ = nn = 0
        for case, v in LAB.items():
            c = cond_fn(case)
            if v['label'] == 'LOW':
                np_ += 1; tp += c
            else:
                nn += 1; tn += c
        return 0.5 * (tp / np_ + tn / nn)
    res = {}
    for cond in ('SA', 'A', 'T', 'O'):
        res[cond] = ba(lambda c, cond=cond: 1.0 if per[(c, cond)][0] == per[(c, cond)][1] else 0.0)
    res['J'] = ba(lambda c: 0.5 * ((per[(c, 'J_DA')][0] == per[(c, 'J_DA')][1]) + (per[(c, 'J_AD')][0] == per[(c, 'J_AD')][1])))

    def rule(c):
        sd, sa = per[(c, 'SD')][0], per[(c, 'SA')][0]
        if sd in ('UNCERTAIN', 'INVALID') or sa in ('UNCERTAIN', 'INVALID'):
            return 0.0
        pred = 'YES' if (sd == 'HIGH' and sa == 'LOW') else 'NO'
        return 1.0 if pred == per[(c, 'A')][1] else 0.0
    res['rule'] = ba(rule)
    a = rep['models'][model]['all_20']
    cmp = {'confusion_equal': all(conf[c] == {k.replace('INVALID', 'INVALID'): v for k, v in a['confusion'][c].items()} for c in conf)}
    cmp['BA_max_abs_diff'] = max(abs(res[k] - a['conds'][k]['BA']) for k in res)
    cmp['pass'] = cmp['confusion_equal'] and cmp['BA_max_abs_diff'] < 1e-12
    ok &= cmp['pass']
    out[model] = {'BA_independent': res, 'confusion_independent': conf, 'compare': cmp}
    print(model, cmp)
with open('results/iter_069/eval/independent_verify.json', 'x') as f:
    json.dump(out, f, indent=1)
sys.exit(0 if ok else 1)
