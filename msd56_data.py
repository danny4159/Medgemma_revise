"""iter_056 MSD Task01_BrainTumour FLAIR 구간 자료: 선택·추출·구간/정답/조건 생성.

원칙
- 채널은 dataset.json(modality["0"]=="FLAIR")에서 읽는다. 정답=모든 비배경 label(1,2,3)의 합집합 (전부 tumour/oedema 계열; dataset.json labels).
- image·mask는 동일 함수(canonical RAS 재배열 + 동일 축 변환)로 처리한다. 구간은 FLAIR nonzero 범위만으로 정한다(mask 미사용).
- 렌더링: FLAIR volume 전체 min/max로 uint8 선형 정규화(구간별/slice별 재정규화 없음), 동일 RGB 3채널.
- 표시 방향: slice[k] = arr_RAS[::-1, :, k].T[::-1]  -> 행: anterior가 위, 열: patient right가 영상 왼쪽(radiological).
사용: python msd56_data.py select | extract | build
"""
import hashlib
import io
import json
import os
import random
import sys
import tarfile

import numpy as np

ROOT = "results/iter_056"
TAR = f"{ROOT}/source/Task01_BrainTumour.tar"
DATA = f"{ROOT}/data"
SEED = 56
N_D, N_E, N_SLAB, MIN_SLAB = 6, 48, 6, 8
VERSION = "msd56_data_v1"


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def training_ids():
    d = json.load(open(f"{ROOT}/source/dataset.json"))
    assert d["modality"]["0"] == "FLAIR", d["modality"]
    ids = []
    for e in d["training"]:
        assert e["image"].startswith("./imagesTr/") and e["label"].startswith("./labelsTr/")
        a, b = e["image"].rsplit("/", 1)[1], e["label"].rsplit("/", 1)[1]
        assert a == b and not a.startswith("._")
        ids.append(a[:-len(".nii.gz")])
    assert len(ids) == len(set(ids)) == 484
    return sorted(ids)


def case_paths(cid):
    return f"{DATA}/raw/{cid}_img.nii.gz", f"{DATA}/raw/{cid}_lbl.nii.gz"


def load_case(cid):
    """returns flair float32 (RAS canonical), mask uint8 (same), header info dict."""
    import nibabel as nib
    ip, lp = case_paths(cid)
    img, lbl = nib.load(ip), nib.load(lp)
    if img.shape[:3] != lbl.shape[:3] or not np.allclose(img.affine, lbl.affine, atol=1e-4):
        raise ValueError(f"{cid}: image/label grid mismatch {img.shape} {lbl.shape}")
    assert img.ndim == 4 and img.shape[3] == 4
    info = {"shape": list(img.shape), "label_shape": list(lbl.shape), "zooms": [float(z) for z in img.header.get_zooms()[:3]],
            "orig_axcodes": "".join(nib.aff2axcodes(img.affine)), "affine": img.affine.round(4).tolist(),
            "dtype": str(img.get_data_dtype())}
    can = nib.as_closest_canonical(img)
    canl = nib.as_closest_canonical(lbl)
    info["canon_axcodes"] = "".join(nib.aff2axcodes(can.affine))
    assert info["canon_axcodes"] == "RAS"
    flair = np.asarray(can.dataobj[..., 0], dtype=np.float32)
    mask = np.asarray(canl.dataobj).astype(np.uint8)
    if not np.isfinite(flair).all():
        raise ValueError(f"{cid}: non-finite FLAIR")
    return flair, mask, info


def nonzero_range(flair):
    nz = np.where((flair != 0).reshape(-1, flair.shape[2]).any(axis=0))[0]
    return int(nz[0]), int(nz[-1])


def make_slabs(z0, z1, n=N_SLAB):
    L = z1 - z0 + 1
    base, rem = divmod(L, n)
    out, s = [], z0
    for i in range(n):
        ln = base + (1 if i < rem else 0)
        out.append([s, s + ln - 1])
        s += ln
    assert out[-1][1] == z1
    return out


def render(flair, k, vmin, vmax):
    sl = flair[::-1, :, k].T[::-1]
    u = np.clip((sl - vmin) / (vmax - vmin), 0, 1) * 255.0
    g = np.round(u).astype(np.uint8)
    return np.repeat(g[:, :, None], 3, axis=2)


def mask_slice(mask, k):
    return (mask[::-1, :, k].T[::-1] > 0)


def equi(n, m):
    """양 끝 포함 결정적 등간격 m개 index (0..n-1), 중복 없어야 함."""
    idx = [int(round(i * (n - 1) / (m - 1))) for i in range(m)]
    assert len(set(idx)) == m, (n, m, idx)
    return idx


def conditions_for_slab(z0, z1, area):
    """area: slab 내 slice별 annotation voxel 수(단면적) list. returns dict cond -> absolute slice list (inferior->superior)."""
    n = z1 - z0 + 1
    dense = list(range(z0, z1 + 1))
    dense_note = "all"
    if n > 85:
        dense = [z0 + i for i in equi(n, 85)]
        dense_note = "equispaced85"
    u8 = [z0 + i for i in equi(n, 8)]
    if sum(area) > 0:
        order = sorted(range(n), key=lambda i: (-area[i], i))[:8]
        o8 = sorted(z0 + i for i in order)
    else:
        o8 = list(u8)
    return {"DENSE": dense, "U8": u8, "O8": o8}, dense_note


def cmd_select():
    os.makedirs(f"{DATA}/raw", exist_ok=True)
    ids = training_ids()
    t = tarfile.open(TAR)
    hashes = {}
    for cid in ids:
        for kind in ("images", "labels"):
            m = t.getmember(f"Task01_BrainTumour/{kind}Tr/{cid}.nii.gz")
            hashes[f"{kind}/{cid}"] = (sha256(t.extractfile(m).read()), m.size)
    img_dups = {}
    for k, (h, _) in hashes.items():
        if k.startswith("images/"):
            img_dups.setdefault(h, []).append(k)
    dup_groups = [v for v in img_dups.values() if len(v) > 1]
    order = list(ids)
    random.Random(SEED).shuffle(order)
    json.dump({"seed": SEED, "n_training": len(ids), "shuffled_order": order,
               "file_hashes": {k: {"sha256": h, "bytes": s} for k, (h, s) in hashes.items()},
               "duplicate_image_file_groups": dup_groups, "version": VERSION},
              open(f"{DATA}/case_order.json", "w"), indent=1)
    print("n", len(ids), "dup groups", dup_groups)


def extract_case(t, cid):
    ip, lp = case_paths(cid)
    for kind, p in (("images", ip), ("labels", lp)):
        if os.path.exists(p):
            continue
        b = t.extractfile(f"Task01_BrainTumour/{kind}Tr/{cid}.nii.gz").read()
        with open(p + ".part", "wb") as f:
            f.write(b)
        os.replace(p + ".part", p)


def cmd_extract():
    """고정 순서에서 FLAIR nonzero 범위만으로 적격(6 구간 각 >=8 slice)한 case를 D6, E48 순으로 채운다. mask는 정하는 데 사용하지 않는다."""
    co = json.load(open(f"{DATA}/case_order.json"))
    t = tarfile.open(TAR)
    chosen, skipped = [], []
    for cid in co["shuffled_order"]:
        if len(chosen) >= N_D + N_E:
            break
        extract_case(t, cid)
        flair, _, info = load_case(cid)
        z0, z1 = nonzero_range(flair)
        slabs = make_slabs(z0, z1)
        if min(b - a + 1 for a, b in slabs) < MIN_SLAB:
            skipped.append({"case": cid, "reason": f"slab<{MIN_SLAB}", "range": [z0, z1]})
            continue
        chosen.append({"case": cid, "split": "D" if len(chosen) < N_D else "E", "z_range": [z0, z1], "slabs": slabs,
                       "vmin": float(flair.min()), "vmax": float(flair.max()), "info": info,
                       "img_sha256": co["file_hashes"][f"images/{cid}"]["sha256"],
                       "lbl_sha256": co["file_hashes"][f"labels/{cid}"]["sha256"]})
    json.dump({"chosen": chosen, "skipped": skipped, "version": VERSION}, open(f"{DATA}/cases.json", "w"), indent=1)
    print("chosen", len(chosen), "skipped", len(skipped))


def cmd_build():
    """구간별 정답·coverage·조건별 slice 선택과 PNG 렌더, requests 원본(manifest) 생성. GT는 manifest_gt.json에만 둔다."""
    cs = json.load(open(f"{DATA}/cases.json"))["chosen"]
    os.makedirs(f"{DATA}/png", exist_ok=True)
    gt, inputs = [], {}
    for c in cs:
        flair, mask, _ = load_case(c["case"])
        ann = mask > 0
        for si, (a, b) in enumerate(c["slabs"]):
            area = [int(ann[:, :, k].sum()) for k in range(a, b + 1)]
            conds, dn = conditions_for_slab(a, b, area)
            tot = sum(area)
            row = {"case": c["case"], "split": c["split"], "slab": si, "z0": a, "z1": b, "n_slices": b - a + 1,
                   "present": bool(tot > 0), "ann_voxels": tot, "n_pos_slices": int(sum(x > 0 for x in area)),
                   "pos_slice_frac": float(sum(x > 0 for x in area)) / (b - a + 1), "max_slice_area": max(area),
                   "dense_note": dn, "cond": {}}
            for cn, sl in conds.items():
                ar = [area[k - a] for k in sl]
                row["cond"][cn] = {"slices": sl, "n": len(sl), "cov_pos_slices": int(sum(x > 0 for x in ar)),
                                   "cov_voxels": int(sum(ar)),
                                   "cov_max_area": max(ar),
                                   "cov_frac_voxels": (sum(ar) / tot) if tot else None,
                                   "cov_frac_pos_slices": (sum(x > 0 for x in ar) / row["n_pos_slices"]) if tot else None,
                                   "cov_frac_max_area": (max(ar) / max(area)) if tot else None,
                                   "missed_positive": bool(tot > 0 and sum(ar) == 0)}
            gt.append(row)
            for k in sorted({k for sl in conds.values() for k in sl}):
                p = f"{DATA}/png/{c['case']}_z{k:03d}.png"
                if not os.path.exists(p):
                    from PIL import Image
                    Image.fromarray(render(flair, k, c["vmin"], c["vmax"])).save(p + ".tmp.png")
                    os.replace(p + ".tmp.png", p)
                if p not in inputs:
                    inputs[p] = sha256(open(p, "rb").read())
    json.dump({"rows": gt, "version": VERSION}, open(f"{DATA}/gt_slabs.json", "w"), indent=1)
    json.dump(inputs, open(f"{DATA}/png_sha256.json", "w"), indent=1)
    print("slabs", len(gt), "pos", sum(r["present"] for r in gt), "pngs", len(inputs))


if __name__ == "__main__":
    {"select": cmd_select, "extract": cmd_extract, "build": cmd_build}[sys.argv[1]]()
