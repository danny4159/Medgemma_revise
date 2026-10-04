"""iter_070 cost / mask-overlap / determinism summary from saved raw outputs."""
import glob
import json

import nibabel as nib
import numpy as np

M = 'results/iter_070/main/'
seal = json.load(open(M + 'seal.json'))
dice = {}
for c in seal['cases']:
    a = np.asarray(nib.load(f'{M}masks/{c}-t2f_ab.nii.gz').dataobj) > 0
    g = np.asarray(nib.load(f'{M}gt/{c}_gt_whole.nii.gz').dataobj) > 0
    dice[c] = round(float(2 * (a & g).sum() / max(a.sum() + g.sum(), 1)), 4)
rows = []
for f in sorted(glob.glob(M + 'results/*.json')):
    r = json.load(open(f))
    rows.append((r['case'], r['cond'], r['case_wall_s'], r['seg_s_case'], r['attempts'][0]['wall_s'], r['peak_reserved_MiB']))
P = [x for x in rows if x[1] == 'P']
G = [x for x in rows if x[1] == 'G']
L = json.load(open(M + 'launch_result.json'))
T = [json.load(open(f)) for f in glob.glob('results/iter_070/tech/results/*__G.json')]
single = float(np.mean([t['case_wall_s'] for t in T]) * 15)
cost = {'main_wall_s_4workers': L['wall_s'], 'peak_gpu_used_MiB_per_gpu': L['peak_gpu_used_MiB'],
        'mean_seg_s': float(np.mean([x[3] for x in P])), 'mean_report_wall_s_P': float(np.mean([x[4] for x in P])),
        'mean_report_wall_s_G': float(np.mean([x[4] for x in G])), 'max_torch_reserved_MiB': max(x[5] for x in rows),
        'single_worker_tech_case_wall_s': [t['case_wall_s'] for t in T], 'single_worker_est_15cases_s': single,
        'speedup_est_vs_single': single / L['wall_s'],
        'dice_pred_vs_gt_whole': dice, 'dice_mean': float(np.mean(list(dice.values()))), 'dice_min': min(dice.values())}
det = {}
for c in ['BraTS-GLI-00012-000', 'BraTS-GLI-00456-000']:
    for k in 'PG':
        a = json.load(open(f'results/iter_070/tech/results/{c}__{k}.json'))['attempts'][0]['report']
        b = json.load(open(f'{M}results/{c}__{k}.json'))['attempts'][0]['report']
        det[f'{c}__{k}'] = a == b
cost['tech_vs_main_text_identical'] = det
json.dump(cost, open('results/iter_070/eval/cost.json', 'w'), indent=1)
print(json.dumps(cost, indent=1))
