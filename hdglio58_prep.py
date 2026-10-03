"""iter_058: MSD Task01 4D NIfTI -> HD-GLIO 입력(채널 분리). 원본 label은 사용하지 않는다.

MSD dataset.json modality: 0 FLAIR, 1 T1w, 2 t1gd, 3 T2w
HD-GLIO 파일 규약: _0000 T1, _0001 T1c, _0002 T2, _0003 FLAIR
iter_056 cases.json의 case 목록/순서/split을 변경하지 않는다.
사용: python hdglio58_prep.py [D|E|DE]
"""
import hashlib
import json
import os
import sys

import nibabel as nib
import numpy as np

SRC = "results/iter_056"
OUT = "results/iter_058/hd"
MSD_TO_HD = {0: 1, 1: 3, 2: 0, 3: 2}  # HD index -> MSD channel: T1<-1, T1c<-2, T2<-3, FLAIR<-0 (아래 HD_CH 참고)
HD_CH = {"0000": 1, "0001": 2, "0002": 3, "0003": 0}  # HD suffix -> MSD channel
MODALITY = {"0": "FLAIR", "1": "T1w", "2": "t1gd", "3": "T2w"}


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def prep_case(c, out_dir):
    cid = c["case"]
    ip = f"{SRC}/data/raw/{cid}_img.nii.gz"
    got = sha256_file(ip)
    assert got == c["img_sha256"], (cid, got)
    img = nib.load(ip)
    assert img.ndim == 4 and img.shape[3] == 4
    assert "".join(nib.aff2axcodes(img.affine)) == "RAS"
    assert np.allclose(img.affine, np.eye(4), atol=1e-4), (cid, img.affine)
    data = np.asarray(img.dataobj)
    assert np.isfinite(data).all()
    rec = {"case": cid, "split": c["split"], "img_sha256": got, "shape": list(img.shape), "channels": {}}
    os.makedirs(out_dir, exist_ok=True)
    nz = []
    for suf, ch in HD_CH.items():
        vol = data[..., ch].astype(np.float32)
        p = f"{out_dir}/{cid}_{suf}.nii.gz"
        if not os.path.exists(p):
            h = img.header.copy()
            h.set_data_dtype(np.float32)
            nib.save(nib.Nifti1Image(vol, img.affine, h), p + ".tmp.nii.gz")
            os.replace(p + ".tmp.nii.gz", p)
        nz.append(vol != 0)
        rec["channels"][suf] = {"msd_channel": ch, "msd_name": {0: "FLAIR", 1: "T1w", 2: "t1gd", 3: "T2w"}[ch],
                                "sha256": sha256_file(p), "nonzero_frac": float((vol != 0).mean()),
                                "min": float(vol.min()), "max": float(vol.max())}
    # 비뇌 영역 0 / 공통 지지 영역 일치도
    u = np.logical_or.reduce(nz)
    i = np.logical_and.reduce(nz)
    rec["nonzero_union_frac"] = float(u.mean())
    rec["nonzero_all_frac"] = float(i.mean())
    rec["corners_zero"] = bool(all(not v[0, 0, 0] for v in nz))
    return rec


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "DE"
    cs = json.load(open(f"{SRC}/data/cases.json"))["chosen"]
    recs = []
    for c in cs:
        if c["split"] in which:
            recs.append(prep_case(c, f"{OUT}/input_{c['split']}"))
            print(recs[-1]["case"], recs[-1]["nonzero_union_frac"], recs[-1]["nonzero_all_frac"], flush=True)
    tag = f"prep_{which}.json"
    json.dump({"records": recs, "mapping_note": "HD _0000 T1<-MSD ch1(T1w), _0001 T1c<-ch2(t1gd), _0002 T2<-ch3(T2w), _0003 FLAIR<-ch0",
               "msd_modality": MODALITY}, open(f"{OUT}/{tag}", "w"), indent=1)


if __name__ == "__main__":
    main()
