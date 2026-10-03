"""iter_058: HD-GLIO foreground의 구간 OR 평가와 기존 U8(iter_056 출력)와의 paired 비교. CPU only.

python hdglio58_eval.py E results/iter_058/eval_E   (D도 동일 함수; D는 기술 검사용이며 E와 합치지 않는다)
- 정답은 iter_056 gt_slabs.json이며, raw label에서 구간 present를 독립 재계산해 대조한다(불일치면 중단).
- U8 답변은 msd57_analysis.load_split(iter_056 gen 검증 포함)에서 읽는다. 재분석이므로 새 생성 없음.
- bootstrap: case-cluster paired 10,000회, seed58, 모든 비교에 동일 재표집.
"""
import glob
import hashlib
import json
import os
import sys
import time

import nibabel as nib
import numpy as np

import msd57_analysis as A57

SRC = "results/iter_056"
HD = "results/iter_058/hd"
NS = 6
SEED, B = 58, 10000


def sha_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def atomic_write(path, obj):
    tmp = path + ".tmp"
    json.dump(obj, open(tmp, "w"), indent=1, default=int)
    os.replace(tmp, path)


def collect_pred(split, run):
    """shard별 pred를 모아 case->path. 중복/누락/잉여 검사."""
    cases = json.load(open(f"{HD}/{split}_cases.json"))
    got = {}
    for f in sorted(glob.glob(f"{HD}/run_{run}/*/pred/BRATS_*.nii.gz")):
        cid = os.path.basename(f)[:-len(".nii.gz")]
        if cid in got:
            raise RuntimeError(f"duplicate pred {cid}")
        got[cid] = f
    if sorted(got) != sorted(cases):
        raise RuntimeError(f"pred/case mismatch miss={set(cases) - set(got)} extra={set(got) - set(cases)}")
    rc = json.load(open(f"{HD}/run_{run}/launch.json"))["rc"]
    if any(v != 0 for v in rc.values()):
        raise RuntimeError(f"worker rc {rc}")
    man = json.load(open(f"{HD}/run_{run}/pred_manifest.json"))
    if sorted(man) != sorted(cases):
        raise RuntimeError("pred_manifest case set mismatch")
    for cid, f in got.items():
        if sha_file(f) != man[cid]["pred_sha256"]:
            raise RuntimeError(f"{cid}: pred file changed vs manifest")
        for s, h in man[cid]["input_sha256"].items():
            if sha_file(f"{HD}/input_{split}/{cid}_{s}.nii.gz") != h:
                raise RuntimeError(f"{cid}: input {s} changed vs manifest")
    return got


def hd_slab_table(split, run, gt_rows):
    preds = collect_pred(split, run)
    gt = {(g["case"], g["slab"]): g for g in gt_rows if g["split"] == split}
    rows, case_info = [], []
    for cid in sorted(preds):
        p = nib.load(preds[cid])
        i = nib.load(f"{HD}/input_{split}/{cid}_0003.nii.gz")
        if p.shape != i.shape[:3] or not np.allclose(p.affine, i.affine, atol=1e-4):
            raise RuntimeError(f"{cid}: pred grid != input grid")
        a = np.asarray(p.dataobj)
        if not set(np.unique(a).tolist()) <= {0, 1, 2}:
            raise RuntimeError(f"{cid}: unexpected labels")
        lbl = np.asarray(nib.load(f"{SRC}/data/raw/{cid}_lbl.nii.gz").dataobj) > 0
        pr = a > 0
        for s in range(NS):
            g = gt[(cid, s)]
            z0, z1 = g["z0"], g["z1"]
            gt_present = bool(lbl[:, :, z0:z1 + 1].any())
            if gt_present != g["present"] or int(lbl[:, :, z0:z1 + 1].sum()) != g["ann_voxels"]:
                raise RuntimeError(f"{cid} slab{s}: gt_slabs != raw label")
            hv = int(pr[:, :, z0:z1 + 1].sum())
            rows.append({"case": cid, "slab": s, "present": g["present"], "answer": "PRESENT" if hv > 0 else "ABSENT",
                         "ann_voxels": g["ann_voxels"], "hd_fg_voxels_in_slab": hv,
                         "hd_l1_in_slab": int((a[:, :, z0:z1 + 1] == 1).sum()), "hd_l2_in_slab": int((a[:, :, z0:z1 + 1] == 2).sum()),
                         "hd_in_gt_voxels": int((pr & lbl)[:, :, z0:z1 + 1].sum())})
        inter = int((pr & lbl).sum())
        case_info.append({"case": cid, "gt_voxels": int(lbl.sum()), "hd_voxels": int(pr.sum()), "hd_label1": int((a == 1).sum()),
                          "hd_label2": int((a == 2).sum()), "dice_union": 2 * inter / max(1, int(pr.sum() + lbl.sum())),
                          "hd_outside_gt_voxels": int(pr.sum() - inter), "gt_outside_hd_voxels": int(lbl.sum() - inter),
                          "pred_sha256": sha_file(preds[cid])})
    if len(rows) != len(gt):
        raise RuntimeError("row count != gt")
    return rows, case_info, preds


def sens(S):
    return S[..., 0].sum(-1) / S[..., 1].sum(-1)


def spec(S):
    return S[..., 2].sum(-1) / S[..., 3].sum(-1)


def cell_stats(A):
    S = A.sum(0).sum(0)
    tp, p, tn, n = S
    return {"TP": int(tp), "FN": int(p - tp), "TN": int(tn), "FP": int(n - tn), "P": int(p), "N": int(n),
            "sens": tp / p, "spec": tn / n, "BA": (tp / p + tn / n) / 2}


def run(split, run_name, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    gt_rows = json.load(open(f"{SRC}/data/gt_slabs.json"))["rows"]
    table, gt, _, _ = A57.load_split(split, gt_rows)
    u8 = [t for t in table if t["cond"] == "U8"]
    hd_rows, case_info, preds = hd_slab_table(split, run_name, gt_rows)
    cases = sorted({t["case"] for t in u8})
    if cases != sorted(c["case"] for c in case_info):
        raise RuntimeError("case sets differ")
    A = {"U8": A57.counts_by_case(u8, cases, lambda t: t["answer"]),
         "HD": A57.counts_by_case(hd_rows, cases, lambda t: t["answer"])}
    supp = A57.support_positions(A["U8"])
    rep = {"split": split, "note": "HD-GLIO uses 4 sequences+whole volume; U8 uses FLAIR 8 slices. Not a same-input comparison. E is repeated development data.",
           "n_cases": len(cases), "n_slabs": len(hd_rows), "support_positions": supp, "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    rep["point"] = {k: {**cell_stats(v), "BA_all": float(A57.ba_overall(v.sum(0)[None])[0]),
                        "BA_std": float(A57.ba_std(v.sum(0)[None], supp)[0]), "by_slab": A57.cell(v)} for k, v in A.items()}
    fns = {"HD.BA_all": lambda S: A57.ba_overall(S["HD"]), "U8.BA_all": lambda S: A57.ba_overall(S["U8"]),
           "HD-U8.BA_all": lambda S: A57.ba_overall(S["HD"]) - A57.ba_overall(S["U8"]),
           "HD-U8.sens": lambda S: sens(S["HD"]) - sens(S["U8"]), "HD-U8.spec": lambda S: spec(S["HD"]) - spec(S["U8"]),
           "HD-U8.BA_std": lambda S: A57.ba_std(S["HD"], supp) - A57.ba_std(S["U8"], supp),
           "HD.BA_std": lambda S: A57.ba_std(S["HD"], supp), "U8.BA_std": lambda S: A57.ba_std(S["U8"], supp)}
    ci = A57.cluster_boot_stats(A, fns, seed=SEED, b=B)
    rep["bootstrap"] = {"seed": SEED, "B": B, "unit": "case (6 slabs together), same draw for HD and U8", "ci95_lo_hi_nvalid": ci}
    d = {"BA_all": rep["point"]["HD"]["BA_all"] - rep["point"]["U8"]["BA_all"],
         "sens": rep["point"]["HD"]["sens"] - rep["point"]["U8"]["sens"], "spec": rep["point"]["HD"]["spec"] - rep["point"]["U8"]["spec"]}
    rep["diff_point"] = d
    # 오류 case 분포·겹침
    ur = {(t["case"], t["slab"]): t for t in u8}
    hr = {(t["case"], t["slab"]): t for t in hd_rows}
    err_u = {k for k, t in ur.items() if (t["answer"] == "PRESENT") != t["present"]}
    err_h = {k for k, t in hr.items() if (t["answer"] == "PRESENT") != t["present"]}
    cs = lambda s: sorted({k[0] for k in s})
    rep["errors"] = {"U8_slab_err": len(err_u), "HD_slab_err": len(err_h), "both_slab_err": len(err_u & err_h),
                     "U8_case_err": len(cs(err_u)), "HD_case_err": len(cs(err_h)), "both_case_err": len(set(cs(err_u)) & set(cs(err_h))),
                     "HD_FP": sorted(f"{c}:{s}" for c, s in err_h if not hr[(c, s)]["present"]),
                     "HD_FN": sorted(f"{c}:{s}" for c, s in err_h if hr[(c, s)]["present"]),
                     "FN_ann_voxels": {f"{c}:{s}": hr[(c, s)]["ann_voxels"] for c, s in sorted(err_h) if hr[(c, s)]["present"]},
                     "FP_hd_voxels": {f"{c}:{s}": hr[(c, s)]["hd_fg_voxels_in_slab"] for c, s in sorted(err_h) if not hr[(c, s)]["present"]},
                     "case_ge5_common": len(set(cs(err_u)) & set(cs(err_h))) >= 5}
    dsc = [c["dice_union"] for c in case_info]
    rep["aux_union_dice"] = {"mean": float(np.mean(dsc)), "median": float(np.median(dsc)), "min": float(np.min(dsc)),
                             "note": "auxiliary; not comparable to slab BA",
                             "hd_to_gt_voxel_ratio_mean": float(np.mean([c["hd_voxels"] / max(1, c["gt_voxels"]) for c in case_info]))}
    atomic_write(f"{out_dir}/report.json", rep)
    atomic_write(f"{out_dir}/per_slab_hd.json", hd_rows)
    atomic_write(f"{out_dir}/per_case_hd.json", case_info)
    print(json.dumps({"point": {k: {m: v[m] for m in ("sens", "spec", "BA", "BA_all", "BA_std")} for k, v in rep["point"].items()},
                      "diff": d, "ci": ci, "errors": {k: v for k, v in rep["errors"].items() if not isinstance(v, (list, dict))},
                      "dice": rep["aux_union_dice"]}, indent=1))


if __name__ == "__main__":
    split, run_name, out = sys.argv[1:4]
    run(split, run_name, out)
