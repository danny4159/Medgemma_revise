"""iter_058: E 수치 독립 재계산(평가 모듈 비사용). per_row_E.json(iter_057, U8 답변)과 per_slab_hd.json(HD-GLIO)만 읽고,
GT는 raw NIfTI label에서 직접 구간 present를 재계산한다. 쓰기는 results/iter_058/eval_E/verify.json.
"""
import json

import nibabel as nib
import numpy as np

E = "results/iter_058/eval_E"
gt_rows = {(g["case"], g["slab"]): g for g in json.load(open("results/iter_056/data/gt_slabs.json"))["rows"] if g["split"] == "E"}
u8 = {(r["case"], r["slab"]): r["answer"] for r in json.load(open("results/iter_057/analysis/per_row_E.json")) if r["cond"] == "U8"}
hd = {(r["case"], r["slab"]): r["answer"] for r in json.load(open(f"{E}/per_slab_hd.json"))}
cases = sorted({k[0] for k in gt_rows})
assert len(gt_rows) == len(u8) == len(hd) == 288 and len(cases) == 48
truth = {}
for cid in cases:
    lbl = np.asarray(nib.load(f"results/iter_056/data/raw/{cid}_lbl.nii.gz").dataobj) > 0
    for s in range(6):
        g = gt_rows[(cid, s)]
        truth[(cid, s)] = bool(lbl[:, :, g["z0"]:g["z1"] + 1].any())
assert all(truth[k] == gt_rows[k]["present"] for k in truth)


def tab(pred):
    arr = np.zeros((len(cases), 4))  # TP, P, TN, N
    for i, c in enumerate(cases):
        for s in range(6):
            t, a = truth[(c, s)], pred[(c, s)]
            arr[i, 1 if t else 3] += 1
            arr[i, 0 if t else 2] += (a == "PRESENT") if t else (a == "ABSENT")
    return arr


def ba(a):
    s = a.sum(0)
    return ((s[0] / s[1]) + (s[2] / s[3])) / 2


def sn(a):
    s = a.sum(0)
    return s[0] / s[1]


a_h, a_u = tab(hd), tab(u8)
rng = np.random.default_rng(1058)  # 평가 모듈과 다른 seed/구현: 값이 근사 일치하는지만 확인
d, ds = [], []
for _ in range(10000):
    ix = rng.integers(0, 48, 48)
    d.append(ba(a_h[ix]) - ba(a_u[ix]))
    ds.append(sn(a_h[ix]) - sn(a_u[ix]))
rep = {"BA_HD": ba(a_h), "BA_U8": ba(a_u), "diff": ba(a_h) - ba(a_u), "sens_HD": sn(a_h), "sens_U8": sn(a_u),
       "ci_diff_BA_indep_seed1058": [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))],
       "ci_diff_sens_indep_seed1058": [float(np.percentile(ds, 2.5)), float(np.percentile(ds, 97.5))],
       "gt_vs_raw_label_mismatch": 0}
main = json.load(open(f"{E}/report.json"))
rep["matches_report"] = {"BA_HD": bool(abs(rep["BA_HD"] - main["point"]["HD"]["BA_all"]) < 1e-12),
                         "BA_U8": bool(abs(rep["BA_U8"] - main["point"]["U8"]["BA_all"]) < 1e-12)}
assert all(rep["matches_report"].values())
json.dump(rep, open(f"{E}/verify.json", "w"), indent=1)
print(json.dumps(rep, indent=1))
