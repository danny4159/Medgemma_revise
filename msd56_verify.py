"""iter_056 독립 재계산: (1) 구간 정답을 NIfTI mask에서 직접(요청·gt_slabs 코드 경로 미사용) 재계산, (2) 원시 응답 text를 별도 정규식으로
해석, (3) 조건별 confusion/BA/sens/spec/invalid와 paired BA 차이를 재계산하고 evaluator report와 대조, (4) 입력 PNG가 raw FLAIR slice와
일치하는지(영상-slice 대응) 표본 확인.
사용: python msd56_verify.py --split E --gen-dirs ... --report results/iter_056/eval_E/report.json --out results/iter_056/eval_E/verify.json
"""
import argparse
import glob
import json
import os
import re

import nibabel as nib
import numpy as np
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument("--split", required=True)
ap.add_argument("--gen-dirs", required=True)
ap.add_argument("--report", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--conds", default="DENSE,U8,O8,TEXT")
a = ap.parse_args()
conds = a.conds.split(",")
D = "results/iter_056/data"
cases = [c for c in json.load(open(f"{D}/cases.json"))["chosen"] if c["split"] == a.split]
cmap = json.load(open(f"{D}/cond_map_{a.split}.json"))
reqs = {}
for ln in open(f"{D}/requests_{a.split}.jsonl"):
    r = json.loads(ln)
    reqs[r["rid"]] = r
recs = {}
for d in a.gen_dirs.split(","):
    for fn in glob.glob(os.path.join(d, "gen_worker*.jsonl")):
        for ln in open(fn):
            if ln.endswith("\n") and ln.strip():
                r = json.loads(ln)
                assert r["rid"] not in recs
                recs[r["rid"]] = r
assert set(recs) == set(reqs), "record/request set mismatch"
# (1) 정답 직접 재계산
truth, mism = {}, 0
for c in cases:
    lab = nib.load(f"{D}/raw/{c['case']}_lbl.nii.gz")
    assert "".join(nib.aff2axcodes(lab.affine)) == "RAS"  # native가 RAS이므로 재배열 불필요
    m = np.asarray(lab.dataobj) > 0
    for si, (z0, z1) in enumerate(c["slabs"]):
        truth[(c["case"], si)] = bool(m[:, :, z0:z1 + 1].any())
gts = {(r["case"], r["slab"]): r for r in json.load(open(f"{D}/gt_slabs.json"))["rows"] if r["split"] == a.split}
mism = sum(1 for k, v in truth.items() if gts[k]["present"] != v)
# (4) PNG-raw slice 대응 표본: 각 case의 무작위(고정 seed) 3 slice
rng = np.random.default_rng(1)
png_bad = 0
n_png = 0
for c in cases[:12]:
    img = nib.load(f"{D}/raw/{c['case']}_img.nii.gz")
    arr = np.asarray(img.dataobj[..., 0], dtype=np.float32)
    for z in rng.choice(np.arange(c["z_range"][0], c["z_range"][1] + 1), 3, replace=False):
        p = f"{D}/png/{c['case']}_z{int(z):03d}.png"
        if not os.path.exists(p):
            continue
        sl = arr[:, :, int(z)]                      # native RAS: x(R), y(A)
        exp = np.round(np.clip((sl.T[::-1, ::-1] - c["vmin"]) / (c["vmax"] - c["vmin"]), 0, 1) * 255).astype(np.uint8)
        got = np.asarray(Image.open(p).convert("L"))
        n_png += 1
        png_bad += int(not np.array_equal(exp, got))


# (2) 별도 해석
def ans(txt):
    t = txt.replace("<end_of_turn>", "").strip().rstrip(".!?,;: \n").strip().upper()
    return t if t in ("PRESENT", "ABSENT") else None


rows = []
for c in cmap:
    if c["cond"] not in conds:
        continue
    r = recs[c["rid"]]
    rows.append((c["case"], c["slab"], c["cond"], truth[(c["case"], c["slab"])], ans(r["suffix_text_raw"]), ans(r["suffix_text_raw"]) == r["answer"]))
parser_disagree = sum(1 for x in rows if not x[5])
rep = json.load(open(a.report))
out = {"truth_mismatch_vs_gt_slabs": mism, "n_slabs": len(truth), "png_slices_checked": n_png, "png_mismatch": png_bad,
       "parser_disagreements_vs_eval": parser_disagree, "cond": {}, "paired": {}, "match_report": True}


def stat(rr):
    P = [x for x in rr if x[3]]
    N = [x for x in rr if not x[3]]
    tp = sum(1 for x in P if x[4] == "PRESENT")
    tn = sum(1 for x in N if x[4] == "ABSENT")
    return tp, len(P), tn, len(N)


for cn in conds:
    rr = [x for x in rows if x[2] == cn]
    tp, P, tn, N = stat(rr)
    ba = (tp / P + tn / N) / 2
    out["cond"][cn] = {"TP": tp, "P": P, "TN": tn, "N": N, "BA": ba, "inv": sum(1 for x in rr if x[4] is None)}
    e = rep["cond"][cn]
    ok = e["TP"] == tp and e["TN"] == tn and abs(e["BA"] - ba) < 1e-12
    out["match_report"] &= ok
for x, y in (("DENSE", "TEXT"), ("O8", "TEXT"), ("U8", "TEXT"), ("U8", "DENSE"), ("O8", "DENSE"), ("O8", "U8")):
    if x in conds and y in conds:
        d = out["cond"][x]["BA"] - out["cond"][y]["BA"]
        out["paired"][f"{x}-{y}"] = d
        out["match_report"] &= abs(d - rep["paired"][f"{x}-{y}"]["BA_diff"]) < 1e-12
# 독립 bootstrap (다른 seed, 벡터화): BA와 paired 차이 95% 구간 비교
cs = sorted({x[0] for x in rows})
idx = {cn: {c: [x for x in rows if x[2] == cn and x[0] == c] for c in cs} for cn in conds}
rng = np.random.default_rng(777)


def cnt(cn):
    return np.array([[sum(1 for x in idx[cn][c] if x[3] and x[4] == "PRESENT"), sum(1 for x in idx[cn][c] if x[3]),
                      sum(1 for x in idx[cn][c] if (not x[3]) and x[4] == "ABSENT"), sum(1 for x in idx[cn][c] if not x[3])] for c in cs], float)


cc = {cn: cnt(cn) for cn in conds}
picks = rng.integers(0, len(cs), (10000, len(cs)))


def ba_b(cn):
    s = np.stack([cc[cn][picks[:, j]] for j in range(len(cs))], 0).sum(0)  # (10000,4)
    with np.errstate(divide="ignore", invalid="ignore"):
        return (s[:, 0] / s[:, 1] + s[:, 2] / s[:, 3]) / 2


boot = {cn: ba_b(cn) for cn in conds}
out["boot_ci95"] = {cn: [float(np.nanpercentile(v, 2.5)), float(np.nanpercentile(v, 97.5))] for cn, v in boot.items()}
out["boot_paired_ci95"] = {k: [float(np.nanpercentile(boot[k.split('-')[0]] - boot[k.split('-')[1]], 2.5)),
                                float(np.nanpercentile(boot[k.split('-')[0]] - boot[k.split('-')[1]], 97.5))] for k in out["paired"]}
out["ok"] = bool(out["match_report"] and mism == 0 and png_bad == 0 and parser_disagree == 0)
json.dump(out, open(a.out, "w"), indent=1)
print(json.dumps(out, indent=1))
