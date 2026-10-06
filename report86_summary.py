"""E 평가 report.json의 핵심 표를 한글 보고용 텍스트로 출력(읽기 전용). python report86_summary.py <report.json> [set]"""
import json
import sys

rep = json.load(open(sys.argv[1]))
setname = sys.argv[2] if len(sys.argv) > 2 else 'abnormal'
s = rep['summary'][setname]
print(setname, 'n=', s['n_patients'])
print('cond      rec_def rec_strict rec_incP rec_wideD | status D/P/N/U (pos_def n) | contra pats a_def/a_poss/b_neg/c_wrong | prec[lo,hi] S/C/V | non-EOS tok att')
for c, a in s['conditions'].items():
    st = a['status_counts_pos_def']
    cp = a['contra_components_patients']
    cl = a['claims']
    f = lambda x: 'NA' if x['mean'] is None else f"{x['mean']:.3f}"
    print(f"{c:6s}  {f(a['recall_def'])}  {f(a['recall_strict'])}  {f(a['recall_incl_possible'])}  {f(a['recall_wide_D'])} | {st['D']}/{st['P']}/{st['N']}/{st['U']} ({st['n_pos_def']}) | {cp['a_def']}/{cp['a_poss']}/{cp['b_neg_of_positive']}/{cp['c_wrong_loc']} | [{cl['precision_lower']:.2f},{cl['precision_upper']:.2f}] {cl['supported']}/{cl['contradicted']}/{cl['unverifiable']} | {a['final_non_eos_outputs']} {a['tokens_mean']:.0f} {a['attempts_total']}")
print('comparisons (diff [95% CI] n):')
for k, v in rep['comparisons'][setname].items():
    parts = []
    for m in ('recall_def', 'recall_strict', 'recall_incl_possible', 'contra_primary', 'contra_a_only', 'internal', 'xd', 'xp'):
        x = v[m]
        if x is None:
            continue
        ci = x['ci95']
        parts.append(f"{m}={x['diff']:+.3f}" + (f"[{ci[0]:+.3f},{ci[1]:+.3f}]" if ci else '') + f"(n{x['n']})")
    print(' ', k, ' '.join(parts))
