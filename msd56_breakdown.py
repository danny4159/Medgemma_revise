"""iter_056 사후 탐색 분해(사전 판정 규칙에 쓰지 않음): 구간 위치(slab index)별 prevalence·조건별 정답률, 위치-only in-sample 상한 prior,
양성 구간의 병변 크기·coverage 층별 민감도, FN/FP 사례 목록.  python msd56_breakdown.py EVAL_DIR
"""
import json
import sys

import numpy as np

d = sys.argv[1]
T = json.load(open(f"{d}/per_slab.json"))
conds = sorted({t["cond"] for t in T})
out = {"note": "post-hoc exploratory; E is development data"}
out["by_slab_index"] = {}
for s in range(6):
    row = {}
    for cn in conds:
        tt = [t for t in T if t["cond"] == cn and t["slab"] == s]
        P = [t for t in tt if t["present"]]
        N = [t for t in tt if not t["present"]]
        row[cn] = {"n": len(tt), "P": len(P), "N": len(N), "TP": sum(t["answer"] == "PRESENT" for t in P),
                   "TN": sum(t["answer"] == "ABSENT" for t in N)}
    out["by_slab_index"][s] = row
# 위치-only in-sample 상한: 각 slab index에서 다수 class를 예측
tt = [t for t in T if t["cond"] == conds[0]]
pos_pred = {}
for s in range(6):
    x = [t for t in tt if t["slab"] == s]
    pos_pred[s] = sum(t["present"] for t in x) >= len(x) / 2
P = [t for t in tt if t["present"]]
N = [t for t in tt if not t["present"]]
sens = np.mean([pos_pred[t["slab"]] for t in P])
spec = np.mean([not pos_pred[t["slab"]] for t in N])
out["position_only_insample_prior"] = {"pred_present_by_slab_index": {str(k): bool(v) for k, v in pos_pred.items()},
                                         "sens": float(sens), "spec": float(spec), "BA": float((sens + spec) / 2),
                                         "caveat": "E 자체에서 맞춘 in-sample 상한이며 실제 baseline 아님"}
# 병변 크기 분위
pos = [t for t in tt if t["present"]]
q = np.quantile([t["ann_voxels"] for t in pos], [0.25, 0.5, 0.75])
out["ann_voxels_quartiles_pos"] = q.tolist()
out["sens_by_voxel_quartile"] = {}
for cn in conds:
    if cn == "TEXT":
        continue
    pp = [t for t in T if t["cond"] == cn and t["present"]]
    bins = [(0, q[0]), (q[0], q[1]), (q[1], q[2]), (q[2], 1e12)]
    out["sens_by_voxel_quartile"][cn] = [{"range": [float(lo), float(hi)], "n": sum(lo < t["ann_voxels"] <= hi or (lo == 0 and t["ann_voxels"] <= hi) for t in pp),
                                          "TP": sum(((lo < t["ann_voxels"] <= hi) or (lo == 0 and t["ann_voxels"] <= hi)) and t["answer"] == "PRESENT" for t in pp)}
                                         for lo, hi in bins]
# FN / FP 사례 (DENSE)
for cn in ("DENSE", "U8", "O8"):
    c = [t for t in T if t["cond"] == cn]
    out[f"{cn}_FN"] = [{"case": t["case"], "slab": t["slab"], "ann_voxels": t["ann_voxels"], "n_pos_slices": t["n_pos_slices"],
                        "missed_by_selection": t["missed_positive"]} for t in c if t["present"] and t["answer"] != "PRESENT"]
    out[f"{cn}_FP_cases"] = sorted({t["case"] for t in c if (not t["present"]) and t["answer"] == "PRESENT"})
# 구간 단위 DENSE vs U8 불일치 중 coverage 손실과 일치하는 것
dn = {(t["case"], t["slab"]): t for t in T if t["cond"] == "DENSE"}
u8 = {(t["case"], t["slab"]): t for t in T if t["cond"] == "U8"}
o8 = {(t["case"], t["slab"]): t for t in T if t["cond"] == "O8"}
ok = lambda t: (t["answer"] == "PRESENT") == t["present"]
lost = [k for k in dn if dn[k]["present"] and ok(dn[k]) and not ok(u8[k])]
out["U8_loses_DENSE_correct_positive"] = {"n": len(lost), "of_which_selection_missed_all_annotation": sum(bool(u8[k]["missed_positive"]) for k in lost)}
lost_o = [k for k in dn if dn[k]["present"] and ok(dn[k]) and not ok(o8[k])]
out["O8_loses_DENSE_correct_positive"] = {"n": len(lost_o)}
out["answer_flips_DENSE_vs_U8_all"] = sum(dn[k]["answer"] != u8[k]["answer"] for k in dn)
out["answer_flips_U8_vs_O8_all"] = sum(u8[k]["answer"] != o8[k]["answer"] for k in dn)
out["U8_O8_identical_request_rows"] = sum(u8[k]["rid"] == o8[k]["rid"] for k in dn)
json.dump(out, open(f"{d}/breakdown.json", "w"), indent=1, default=int)
print(json.dumps(out, indent=1, default=int))
