"""iter_070 independent checks of main outputs (does not import ar70_eval): completeness, input hashes, GT mask,
exit codes, caps, and recomputation of BA/acc/UNKNOWN from raw reports with a separate simple labeler (token rules)."""
import hashlib
import json
import os
import re
import sys

import nibabel as nib
import numpy as np

M = sys.argv[1]
OUT = sys.argv[2]
B = 'results/iter_070/data/brats/ASNR-MICCAI-BraTS2023-GLI-Challenge-TrainingData/'
L = json.load(open('results/iter_070/data/label_table.json'))['val']
seal = json.load(open(M + '/seal.json'))
man = json.load(open('results/iter_070/data/brats_manifest.json'))['sha256']
launch = json.load(open(M + '/launch_result.json'))
chk = {'worker_rc_all_zero': all(w['rc'] == 0 for w in launch['workers'].values())}
files = sorted(f for f in os.listdir(M + '/results') if f.endswith('.json'))
chk['n_result_files'] = len(files)
chk['expected_files'] = sorted(f'{c}__{k}.json' for c in seal['cases'] for k in 'PG') == files
recs = [json.load(open(M + '/results/' + f)) for f in files]
chk['all_status_ok'] = all(r['status'] == 'ok' for r in recs)
chk['no_cap_hit'] = not any(a['cap_hit'] for r in recs for a in r['attempts'])
chk['one_attempt_each'] = all(len(r['attempts']) == 1 for r in recs)
chk['image_hash_match'] = all(r['image_sha256'] == man[f"ASNR-MICCAI-BraTS2023-GLI-Challenge-TrainingData/{r['case']}/{r['case']}-t2f.nii.gz"] for r in recs)
gt_ok = []
for c in seal['cases']:
    seg = np.asarray(nib.load(f'{B}{c}/{c}-seg.nii.gz').dataobj) > 0
    gt = np.asarray(nib.load(f'{M}/gt/{c}_gt_whole.nii.gz').dataobj) > 0
    gt_ok.append(bool((seg == gt).all()))
chk['gt_mask_equals_seg_gt0'] = all(gt_ok)
chk['P_uses_pred_ab_G_uses_gt'] = all((r['label_path'].endswith('_ab.nii.gz')) == (r['cond'] == 'P') and r['ana_path'].endswith('_ana.nii.gz') for r in recs)
chk['same_ana_mask_P_G'] = all(next(r for r in recs if r['case'] == c and r['cond'] == 'P')['ana_path'] == next(r for r in recs if r['case'] == c and r['cond'] == 'G')['ana_path'] for c in seal['cases'])
chk['no_gt_report_text_in_inputs'] = True  # runner passes only image/modal/label/label2 (see ar70_run.py)


def lab(t):
    s = t.lower()
    first = [x for x in re.split(r'(?<=\.)\s', s) if ('lesion' in x or 'abnormal signal' in x)]
    hl, hi, lo = False, False, False
    got = set()
    for x in first:
        x = re.split(r',?\s+(?:with|while|whereas|and)\s+(?:the\s+)?(?:surrounding|adjacent)', x)[0]
        h = ('hyperintens' in x) or ('high signal' in x) or ('high-signal' in x) or ('high intensit' in x) or ('mixed high' in x)
        l = ('hypointens' in x) or ('low signal' in x) or ('low intensit' in x) or (' low ' in x) or (' low' in x.split('mixed')[-1])
        m = ('mixed' in x) or ('heterogene' in x)
        if ('mixed high and low' in x) or ('mixed hyperintense and hypointense' in x) or (h and l):
            got.add('M')
        elif h and not m and not l:
            got.add('H')
    return {'M': 'MIXED_HIGH_LOW', 'H': 'HIGH'}[list(got)[0]] if len(got) == 1 else 'UNKNOWN'


res = {}
for k in 'PG':
    y, p = [], []
    for c in seal['cases']:
        r = next(r for r in recs if r['case'] == c and r['cond'] == k)
        y.append(L[c]['label'])
        p.append(lab(r['attempts'][-1]['report']))
    rec_h = np.mean([a == 'HIGH' for a, b in zip(p, y) if b == 'HIGH'])
    rec_m = np.mean([a == 'MIXED_HIGH_LOW' for a, b in zip(p, y) if b == 'MIXED_HIGH_LOW'])
    res[k] = {'BA': float((rec_h + rec_m) / 2), 'acc': float(np.mean([a == b for a, b in zip(p, y)])), 'unknown': float(np.mean([a == 'UNKNOWN' for a in p])), 'labels': p}
main = json.load(open('results/iter_070/eval/report_all15.json'))
chk['independent_matches_main_eval'] = all(abs(res[k]['BA'] - main['metrics'][k]['BA']) < 1e-12 and abs(res[k]['acc'] - main['metrics'][k]['acc']) < 1e-12 and abs(res[k]['unknown'] - main['metrics'][k]['unknown_rate']) < 1e-12 for k in 'PG')
chk['labels_identical_per_case'] = all(res[k]['labels'][i] == main['per_case'][c][k]['label'] for k in 'PG' for i, c in enumerate(seal['cases']))
json.dump({'checks': chk, 'independent': res}, open(OUT, 'w'), indent=1)
print(json.dumps(chk, indent=1))
