"""iter_058: 네 sequence + HD-GLIO 예측(빨강 채움: label1 노랑/label2 빨강) + GT 외곽(초록) overlay.
python hdglio58_overlay.py RUN_DIR_GLOB_OUT SPLIT RUN CASE OUT.png [z]"""
import glob
import sys

import nibabel as nib
import numpy as np
from PIL import Image

SRC = "results/iter_056"
HD = "results/iter_058/hd"


def disp(a2):
    return a2[::-1, :].T[::-1]


def norm(sl):
    v = sl[sl > 0]
    hi = np.percentile(v, 99.5) if v.size else 1.0
    return (np.clip(sl / hi, 0, 1) * 255).astype(np.uint8)


def main():
    split, run, cid, out = sys.argv[1:5]
    pf = glob.glob(f"{HD}/run_{run}/*/pred/{cid}.nii.gz")[0]
    pred = np.asarray(nib.load(pf).dataobj)
    gt = np.asarray(nib.load(f"{SRC}/data/raw/{cid}_lbl.nii.gz").dataobj) > 0
    z = int(sys.argv[5]) if len(sys.argv) > 5 else int(np.argmax(((pred > 0) | gt).sum((0, 1))))
    tiles = []
    for suf, nm in (("0000", "T1"), ("0001", "T1c"), ("0002", "T2"), ("0003", "FLAIR")):
        v = np.asarray(nib.load(f"{HD}/input_{split}/{cid}_{suf}.nii.gz").dataobj)[:, :, z]
        g = np.repeat(disp(norm(v))[:, :, None], 3, axis=2).astype(np.float32)
        p = disp(pred[:, :, z])
        for lab, col in ((1, (255, 220, 0)), (2, (255, 0, 0))):
            m = p == lab
            g[m] = 0.55 * g[m] + 0.45 * np.array(col)
        gm = disp(gt[:, :, z])
        pad = np.pad(gm, 1)
        inner = pad[1:-1, 1:-1] & pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:]
        edge = gm & ~inner
        g[edge] = (0, 255, 0)
        tiles.append(g.astype(np.uint8))
    Image.fromarray(np.concatenate(tiles, axis=1)).save(out)
    print(cid, "z", z, "gt vox in z", int(gt[:, :, z].sum()), "pred vox in z", int((pred[:, :, z] > 0).sum()))


if __name__ == "__main__":
    main()
