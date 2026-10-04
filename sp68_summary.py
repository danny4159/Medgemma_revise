"""iter_068 요약 출력 + sklearn 독립 AUROC 교차검사. 사용: python sp68_summary.py results/iter_068/analysis/report.json"""
import json, sys


def roc_auc_score(y, sc):
    """독립 경로: 쌍 비교 O(n^2) 직접 계산(tie=0.5)."""
    pos = [s for s, t in zip(sc, y) if t]; neg = [s for s, t in zip(sc, y) if not t]
    return sum((a > b) + 0.5 * (a == b) for a in pos for b in neg) / (len(pos) * len(neg))


r = json.load(open(sys.argv[1]))
lab = {(p['patient'], i['k']): i['modic'] for p in json.load(open('results/iter_067/data/pairs_E12.json')) for i in p['ivd']}
out = {}
for m, v in r['models'].items():
    rows = [json.loads(l) for l in open(f'results/iter_067/gen_E12/{m}/worker0.jsonl')]
    s = [x for x in rows if x['cond'] == 'S1']
    ref = roc_auc_score([lab[(x['patient'], x['ivd'])] == 2 for x in s], [x['cand_probs'][2] for x in s])
    rk, ct = v['rank']['S1'], v['control']['S1']
    o = {'rank_auc_S1': ref, 'auc_S1': rk['auc_all'], 'auc_ci': rk['auc_all_ci95'], 'within_patient': rk['within_patient'], 'same_ordinal': [rk['same_ordinal_diffpatient'], rk['same_ordinal_ci95'], rk['same_ordinal_info']],
         'lopo': [rk['lopo_auc']['min'], rk['lopo_auc']['max']], 'resid': [ct['auc_resid'], ct['auc_resid_ci95']], 'nuisance': [ct['auc_nuisance'], ct['auc_nuisance_ci95']], 'support_only': ct['support_only'],
         'aux_auc': {k: [round(x['auc_all'], 3), [round(t, 2) for t in x['auc_all_ci95']]] for k, x in v['rank'].items()},
         'aux_resid': {k: round(x['auc_resid'], 3) for k, x in v['control'].items()},
         'thr': {k: [x['threshold'], x['D_BA'], x['E12_BA'], x['recall0'], x['recall2'], x['E12_BA_ci95']] for k, x in v['threshold'].items()},
         'pair': v['threshold_paired'], 'D_lopo': [v['threshold_D_lopo']['E12_BA_range'], v['threshold_D_lopo']['max_frac_changed'], {p: x['threshold'] for p, x in v['threshold_D_lopo']['per_left_out_D_patient'].items()}],
         'nested': {k: x['ci95'] for k, x in v['nested_bootstrap'].items() if isinstance(x, dict)}, 'nested_valid': v['nested_bootstrap']['valid'],
         'II_per_D_patient': v['D']['II_rows_per_patient'], 'support': v['support'], 'criteria': v['criteria_S1']}
    out[m] = o
    print(m, json.dumps(o, default=str))
