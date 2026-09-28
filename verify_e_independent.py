import json
import numpy as np

rows = json.load(open('results/iter_028/E_eval/e_table.json'))
y = np.array([r['y'] for r in rows])
n_pos, n_neg = int(y.sum()), int(len(y) - y.sum())
print('n_pos', n_pos, 'n_neg', n_neg)

for name in ('entropy', 'token_nll', 'ptrue_b0'):
    s = np.array([r[name] for r in rows])
    order = np.argsort(s)
    ranks = np.empty(len(s))
    ranks[order] = np.arange(1, len(s) + 1)
    sv = s[order]
    i = 0
    while i < len(sv):
        j = i
        while j + 1 < len(sv) and sv[j + 1] == sv[i]:
            j += 1
        if j > i:
            avg = (i + 1 + j + 1) / 2.0
            ranks[order[i:j + 1]] = avg
        i = j + 1
    R_pos = ranks[y == 1].sum()
    auc_mw = (R_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
    k = int(round(len(s) * 0.2))
    top_idx = np.argsort(-s)[:k]
    captured = int(y[top_idx].sum())
    print(name, 'independent AUROC (Mann-Whitney)=', auc_mw, 'independent capture@20 (no tie split)=',
          captured / n_pos, 'k=', k)
