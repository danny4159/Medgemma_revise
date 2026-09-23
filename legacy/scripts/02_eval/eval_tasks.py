"""Builds the full evaluation task list (prompts + ground truth) for all datasets."""
import json
import os

import numpy as np
from PIL import Image

ROOT = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_samples"

CHEXPERT_LABELS = [
    "No Finding", "Enlarged Cardiomediastinum", "Cardiomegaly", "Lung Opacity",
    "Lung Lesion", "Edema", "Consolidation", "Pneumonia", "Atelectasis",
    "Pneumothorax", "Pleural Effusion", "Pleural Other", "Fracture", "Support Devices",
]
NIH_LABELS = [
    "Atelectasis", "Cardiomegaly", "Effusion", "Infiltration", "Mass", "Nodule",
    "Pneumonia", "Pneumothorax", "Consolidation", "Edema", "Emphysema", "Fibrosis",
    "Pleural_Thickening", "Hernia",
]

# ground-truth answers in these sets are single words / short phrases, so the model is
# asked to match that format or token-F1 penalises it for verbosity alone
SHORT_ANSWER = "\nAnswer with a single word or a short phrase only, with no explanation."

GRID_PROMPT = (
    "The image is divided into a 3x3 grid of 9 equal cells numbered 1-9 in reading order "
    "(1=top-left, 2=top-center, 3=top-right, 4=middle-left, 5=center, 6=middle-right, "
    "7=bottom-left, 8=bottom-center, 9=bottom-right). "
    "Which single cell contains the main lesion or abnormality? "
    "Respond with only the cell number."
)
BBOX_PROMPT = (
    "Give the bounding box of the main lesion or abnormality as normalized coordinates "
    "in the format [x_min, y_min, x_max, y_max], where each value is between 0.0 and 1.0 "
    "and (0.0, 0.0) is the top-left corner of the image. "
    "Respond with only the four numbers in brackets."
)
DESC_PROMPT = (
    "Describe the main abnormality in this image: what it is and where it is located. "
    "Answer in one or two sentences."
)
NAME_PROMPT = (
    "What is the single most likely lesion type or diagnosis visible in this image? "
    "Respond with a short medical term only, no explanation."
)


def norm_bbox_to_cell(bbox_xyxy):
    """Center of a normalized xyxy box -> 3x3 grid cell number (1-9)."""
    cx = (bbox_xyxy[0] + bbox_xyxy[2]) / 2
    cy = (bbox_xyxy[1] + bbox_xyxy[3]) / 2
    col = min(int(cx * 3), 2)
    row = min(int(cy * 3), 2)
    return row * 3 + col + 1


def bbox_from_mask(mask_path):
    """Binary mask PNG -> normalized xyxy bbox of the foreground."""
    m = np.array(Image.open(mask_path).convert("L"))
    ys, xs = np.nonzero(m > 0)
    h, w = m.shape
    return [xs.min() / w, ys.min() / h, (xs.max() + 1) / w, (ys.max() + 1) / h]


def build_tasks():
    tasks = []

    # ---------------- Group 1: datasets that already ship free-text QA ----------------
    vqa_rad = json.load(open(f"{ROOT}/used_in_training/vqa_rad/meta.json"))
    for r in vqa_rad:
        tasks.append({
            "group": "G1", "dataset": "vqa_rad", "method": "qa",
            "image": f"{ROOT}/used_in_training/vqa_rad/{r['file']}",
            "prompt": r["question"] + SHORT_ANSWER,
            "gt": {"answer": r["answer"]}, "max_new_tokens": 48,
        })

    slake = json.load(open(f"{ROOT}/used_in_training/slake/meta.json"))
    for r in slake:
        for qa in r["qas"]:
            tasks.append({
                "group": "G1", "dataset": "slake", "method": "qa",
                "image": f"{ROOT}/used_in_training/slake/{r['file']}",
                "prompt": qa["question"] + SHORT_ANSWER,
                "gt": {"answer": qa["answer"]}, "max_new_tokens": 48,
            })

    kvasir = json.load(open(f"{ROOT}/not_in_training/kvasir_vqa/meta.json"))
    for r in kvasir:
        tasks.append({
            "group": "G1", "dataset": "kvasir_vqa", "method": "qa",
            "image": f"{ROOT}/not_in_training/kvasir_vqa/{r['file']}",
            "prompt": r["question"] + SHORT_ANSWER,
            "gt": {"answer": r["answer"]}, "max_new_tokens": 48,
        })

    # ---------------- Group 2: image-level classification labels only ----------------
    chexpert = json.load(open(f"{ROOT}/not_in_training/chexpert/meta.json"))
    for r in chexpert:
        img = f"{ROOT}/not_in_training/chexpert/{r['file']}"
        gt = {"present": r["present"], "absent": r["absent"], "uncertain": r["uncertain"],
              "label_set": CHEXPERT_LABELS}
        # Method A: multi-label selection from a fixed list
        tasks.append({
            "group": "G2", "dataset": "chexpert", "method": "A_multilabel", "image": img,
            "prompt": ("From the following list, select ALL findings visible in this chest X-ray: "
                       + ", ".join(CHEXPERT_LABELS)
                       + ". Respond with only a comma-separated list of the selected findings."),
            "gt": gt, "max_new_tokens": 96,
        })
        # Method B: one forced yes/no question per label
        for lab in CHEXPERT_LABELS:
            tasks.append({
                "group": "G2", "dataset": "chexpert", "method": "B_binary", "image": img,
                "prompt": f"Does this chest X-ray show {lab}? Answer only yes or no.",
                "gt": {**gt, "label": lab}, "max_new_tokens": 64,
            })
        # Method C: open-ended report, scored by keyword matching
        tasks.append({
            "group": "G2", "dataset": "chexpert", "method": "C_openended", "image": img,
            "prompt": "Describe the findings in this chest X-ray.",
            "gt": gt, "max_new_tokens": 200,
        })

    nih = json.load(open(f"{ROOT}/not_in_training/nih_chestxray14/meta.json"))
    for r in nih:
        img = f"{ROOT}/not_in_training/nih_chestxray14/{r['file']}"
        present = [f for f in r["findings"].split("|") if f and f != "No Finding"]
        gt = {"present": present, "absent": [l for l in NIH_LABELS if l not in present],
              "uncertain": [], "label_set": NIH_LABELS}
        tasks.append({
            "group": "G2", "dataset": "nih_chestxray14", "method": "A_multilabel", "image": img,
            "prompt": ("From the following list, select ALL findings visible in this chest X-ray: "
                       + ", ".join(NIH_LABELS)
                       + ". Respond with only a comma-separated list of the selected findings."),
            "gt": gt, "max_new_tokens": 96,
        })
        for lab in NIH_LABELS:
            tasks.append({
                "group": "G2", "dataset": "nih_chestxray14", "method": "B_binary", "image": img,
                "prompt": f"Does this chest X-ray show {lab.replace('_', ' ')}? Answer only yes or no.",
                "gt": {**gt, "label": lab}, "max_new_tokens": 64,
            })
        tasks.append({
            "group": "G2", "dataset": "nih_chestxray14", "method": "C_openended", "image": img,
            "prompt": "Describe the findings in this chest X-ray.",
            "gt": gt, "max_new_tokens": 200,
        })

    # ---------------- Group 3: spatial (box / mask) labels ----------------
    # BraTS: bbox derived from the saved segmentation mask
    brats = json.load(open(f"{ROOT}/not_in_training/brats2023/meta.json"))
    for r in brats:
        img = f"{ROOT}/not_in_training/brats2023/{r['file']}"
        box = bbox_from_mask(f"{ROOT}/not_in_training/brats2023/{r['seg_mask_file']}")
        gt = {"bbox_xyxy": box, "cell": norm_bbox_to_cell(box),
              "names": ["glioma", "glioblastoma", "brain tumor", "tumor", "neoplasm", "mass"],
              "tumor_labels": r["tumor_labels_present"]}
        for method, prompt, mnt in [
            ("1_grid", GRID_PROMPT, 64), ("2_bbox", BBOX_PROMPT, 48),
            ("3_desc", DESC_PROMPT, 150), ("4_name", NAME_PROMPT, 24),
        ]:
            tasks.append({"group": "G3", "dataset": "brats2023", "method": method,
                          "image": img, "prompt": prompt, "gt": gt, "max_new_tokens": mnt})

    # DeepLesion: normalized xywh boxes
    dl = json.load(open(f"{ROOT}/not_in_training/deeplesion_ct/meta.json"))
    for r in dl:
        img = f"{ROOT}/not_in_training/deeplesion_ct/{r['file']}"
        x, y, w, h = r["bounding_boxes_normalized_xywh"][0]
        box = [x, y, x + w, y + h]
        gt = {"bbox_xyxy": box, "cell": norm_bbox_to_cell(box),
              "names": [r["lesion_type"]], "lesion_type": r["lesion_type"]}
        for method, prompt, mnt in [
            ("1_grid", GRID_PROMPT, 64), ("2_bbox", BBOX_PROMPT, 48),
            ("3_desc", DESC_PROMPT, 150), ("4_name", NAME_PROMPT, 24),
        ]:
            tasks.append({"group": "G3", "dataset": "deeplesion_ct", "method": method,
                          "image": img, "prompt": prompt, "gt": gt, "max_new_tokens": mnt})

    # VinDr-CXR: pixel xyxy boxes normalized by original image size
    vindr = json.load(open(f"{ROOT}/not_in_training/vindr_cxr/meta.json"))
    for r in vindr:
        img = f"{ROOT}/not_in_training/vindr_cxr/{r['file']}"
        W, H = r["orig_width"], r["orig_height"]
        boxes = [[b["x_min"] / W, b["y_min"] / H, b["x_max"] / W, b["y_max"] / H]
                 for b in r["bounding_boxes_pixel_xyxy"]]
        # largest box = "main" lesion for single-box prompts
        main = max(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
        names = sorted({b["class_name"] for b in r["bounding_boxes_pixel_xyxy"]})
        gt = {"bbox_xyxy": main, "all_bboxes_xyxy": boxes,
              "cell": norm_bbox_to_cell(main),
              "all_cells": sorted({norm_bbox_to_cell(b) for b in boxes}),
              "names": names}
        for method, prompt, mnt in [
            ("1_grid", GRID_PROMPT, 64), ("2_bbox", BBOX_PROMPT, 48),
            ("3_desc", DESC_PROMPT, 150), ("4_name", NAME_PROMPT, 24),
        ]:
            tasks.append({"group": "G3", "dataset": "vindr_cxr", "method": method,
                          "image": img, "prompt": prompt, "gt": gt, "max_new_tokens": mnt})

    return tasks


if __name__ == "__main__":
    tasks = build_tasks()
    from collections import Counter
    print("total tasks:", len(tasks))
    for k, v in sorted(Counter((t["group"], t["dataset"], t["method"]) for t in tasks).items()):
        print(f"  {k}: {v}")
