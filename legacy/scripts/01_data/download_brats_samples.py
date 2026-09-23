import json
import os

import nibabel as nib
import numpy as np
from huggingface_hub import hf_hub_download
from PIL import Image

os.environ.setdefault("HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache")
if "HF_TOKEN" not in os.environ:
    with open(os.path.expanduser("~/.cache/huggingface/token")) as f:
        os.environ["HF_TOKEN"] = f.read().strip()

REPO = "obi77/brats23-first-10-examples"
PREFIX = "ASNR-MICCAI-BraTS2023-GLI-Challenge-TrainingData"
OUT_DIR = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_samples/not_in_training/brats2023"
os.makedirs(OUT_DIR, exist_ok=True)

CASES = [
    "BraTS-GLI-00000-000", "BraTS-GLI-00002-000", "BraTS-GLI-00005-000",
    "BraTS-GLI-00006-000", "BraTS-GLI-00008-000", "BraTS-GLI-00008-001",
    "BraTS-GLI-00009-000", "BraTS-GLI-00011-000", "BraTS-GLI-00012-000",
    "BraTS-GLI-00014-000",
]

LABEL_NAMES = {1: "necrotic tumor core (NCR)", 2: "peritumoral edema (ED)", 3: "enhancing tumor (ET)"}


def window_to_uint8(slice_2d):
    lo, hi = np.percentile(slice_2d, 1), np.percentile(slice_2d, 99)
    if hi <= lo:
        hi = lo + 1
    clipped = np.clip(slice_2d, lo, hi)
    return ((clipped - lo) / (hi - lo) * 255).astype(np.uint8)


records = []
for idx, case in enumerate(CASES):
    t1c_path = hf_hub_download(REPO, f"{PREFIX}/{case}/{case}-t1c.nii.gz", repo_type="dataset")
    seg_path = hf_hub_download(REPO, f"{PREFIX}/{case}/{case}-seg.nii.gz", repo_type="dataset")

    t1c = nib.load(t1c_path).get_fdata()
    seg = nib.load(seg_path).get_fdata()

    # pick the axial slice with the largest tumor area
    tumor_per_slice = (seg > 0).sum(axis=(0, 1))
    z = int(np.argmax(tumor_per_slice))

    img_slice = np.rot90(t1c[:, :, z])
    seg_slice = np.rot90(seg[:, :, z])

    fname = f"{idx:02d}.jpg"
    Image.fromarray(window_to_uint8(img_slice)).convert("RGB").save(os.path.join(OUT_DIR, fname), quality=95)

    seg_fname = f"{idx:02d}_seg.png"
    Image.fromarray((seg_slice > 0).astype(np.uint8) * 255).save(os.path.join(OUT_DIR, seg_fname))

    labels_present = sorted(int(v) for v in np.unique(seg_slice) if v > 0)
    voxel_counts = {LABEL_NAMES.get(l, f"label_{l}"): int((seg_slice == l).sum()) for l in labels_present}

    records.append({
        "file": fname,
        "seg_mask_file": seg_fname,
        "case_id": case,
        "modality": "T1c (contrast-enhanced T1)",
        "axial_slice_index": z,
        "tumor_labels_present": voxel_counts,
    })
    print(f"[{case}] slice {z}, labels: {voxel_counts}")

with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
    json.dump(records, f, ensure_ascii=False, indent=2)

print(f"\nSaved {len(records)} BraTS cases -> {OUT_DIR}")
