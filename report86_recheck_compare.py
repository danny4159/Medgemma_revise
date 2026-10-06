"""2차 눈가림 재판정(고정 24명) 대 1차(judgments_E96_v2) 일치도(intra-rater, 전문의 검토 아님).
python report86_recheck_compare.py <stage> <pass1.txt> <parts_dir> <out.json>
상태(D/P/N/U) 일치, 위치 접미사 일치, 출력 단위 지표 일치, 환자 평균 지표 차이를 계산한다."""
import json
import sys
from pathlib import Path

import numpy as np

from report86_common import R86, save
import report86_eval as E
from report86_view import load as load_stage

stage, p1, parts, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
rows, reads, refs = load_stage(stage)
sample = json.loads((R86 / stage / 'recheck_sample.json').read_text())['patients']
ids = {x['ImageID'] for x in sample}
t2 = '\n'.join(f.read_text() for f in sorted(parts.glob('rpart*.txt')))
j1 = E.parse_judgments(p1.read_text(), rows, refs)
j2 = E.parse_judgments(t2, rows, refs, subset=True)
assert set(j2) == ids, (len(j2), len(ids))

pairs, mets = [], ['recall_def', 'recall_strict', 'recall_incl_possible', 'contra_primary', 'internal', 'xd', 'xp']
n_st = n_agree = n_loc = n_loc_agree = 0
conf = {}
per = {m: [] for m in mets}
per_cond = {}
for img in j2:
    pm1 = {m: [] for m in mets}
    pm2 = {m: [] for m in mets}
    for cond in j2[img]:
        a, b = j1[img][cond], j2[img][cond]
        for fid in a['facts']:
            sa, sb = a['facts'][fid], b['facts'][fid]
            n_st += 1
            n_agree += sa['s'] == sb['s']
            conf[f"{sa['s']}->{sb['s']}"] = conf.get(f"{sa['s']}->{sb['s']}", 0) + 1
            if sa['s'] == 'D' and sb['s'] == 'D':
                n_loc += 1
                n_loc_agree += sa['loc'] == sb['loc']
        o1, o2 = E.per_output(img, cond, a, refs, reads), E.per_output(img, cond, b, refs, reads)
        for m in mets:
            if o1[m] is not None:
                pm1[m].append(o1[m])
                pm2[m].append(o2[m])
                per_cond.setdefault((cond, m), []).append((o1[m], o2[m]))
    for m in mets:
        if pm1[m]:
            per[m].append((float(np.mean(pm1[m])), float(np.mean(pm2[m]))))

res = {'n_patients': len(j2), 'n_fact_judgments': n_st, 'status_agreement': n_agree / n_st if n_st else None,
       'status_transition_counts': dict(sorted(conf.items())), 'loc_agreement_among_both_D': (n_loc_agree / n_loc if n_loc else None), 'n_both_D': n_loc,
       'patient_level_mean_pass1_vs_pass2': {}, 'by_condition_mean_pass1_vs_pass2': {}}
for m in mets:
    arr = np.array(per[m])
    res['patient_level_mean_pass1_vs_pass2'][m] = {'n': len(arr), 'pass1': float(arr[:, 0].mean()), 'pass2': float(arr[:, 1].mean()),
                                                  'mean_abs_diff': float(np.abs(arr[:, 0] - arr[:, 1]).mean()),
                                                  'exact_equal_patients': int((np.abs(arr[:, 0] - arr[:, 1]) < 1e-12).sum())}
for (cond, m), v in sorted(per_cond.items()):
    a = np.array(v, float)
    res['by_condition_mean_pass1_vs_pass2'].setdefault(cond, {})[m] = {'pass1': float(a[:, 0].mean()), 'pass2': float(a[:, 1].mean()), 'n_outputs': len(a)}
res['note'] = 'intra-rater(동일 assistant, 눈가림·재독); 전문의 검토·독립 평가자 일치도가 아님'
save(out, res)
print(json.dumps({k: res[k] for k in ('n_patients', 'n_fact_judgments', 'status_agreement', 'status_transition_counts', 'loc_agreement_among_both_D', 'n_both_D')}, indent=1))
print(json.dumps(res['patient_level_mean_pass1_vs_pass2'], indent=1))
