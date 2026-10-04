"""iter_069 report_main.json 요약 출력(읽기 전용)."""
import json
import sys

d = json.load(open(sys.argv[1]))
for m, v in d['models'].items():
    a = v['all_20']
    print('==', m, 'SD sensitivity(HIGH)', round(a['sd_sensitivity_HIGH'], 3), 'n', a['n_cases'], a['n_low'], a['n_not_low'])
    for c in ['SD', 'SA', 'A', 'J_DA', 'J_AD', 'T', 'O']:
        print(' ', c, a['confusion'][c])
    print('  rule', a['rule_confusion'])
    for k, x in a['conds'].items():
        print('  BA', k, round(x['BA'], 3), 'recL/N', round(x['recall_LOW'], 3), round(x['recall_NOT_LOW'], 3), 'CI', [round(y, 3) for y in x['BA_CI95']], 'excl', x['boot_excluded_single_class'])
    for k, x in a['contrasts'].items():
        print('  diff', k, round(x['diff'], 3), [round(y, 3) for y in x['CI95']], 'excl', x['boot_excluded_single_class'])
    print('  cost', a['cost'])
    print('  cost per req', {k: round(x, 3) for k, x in a['cost_s_mean_per_request'].items()})
    print('  inv/unc', a['invalid_uncertain'])
    print('  order disagreement', a['order_disagreement_J'])
    n = v['excluding_tech_cases']
    print('  excl tech BA', {k: round(x['BA'], 3) for k, x in n['conds'].items()}, 'n', n['n_cases'], n['n_low'], n['n_not_low'])
    print('  decision', a['decision'])
