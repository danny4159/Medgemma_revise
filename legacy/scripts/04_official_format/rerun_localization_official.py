"""Re-runs localisation with MedGemma 1.5's OFFICIAL detection format.

Why this exists: the earlier evaluation used a prompt format I invented
("give [x_min,y_min,x_max,y_max]") and was interpreted against the MedGemma 1
technical report, which has no localisation capability. MedGemma 1.5 added
"Anatomical localization: bounding box-based localization ... in chest X-rays"
and reports IoU 38.0 on Chest ImaGenome. Its native format, discovered by
probing the model, is:

    prompt : Detect the {object}. Output a JSON list where each entry contains
             the 2D bounding box in "box_2d" and a text label in "label".
    output : ```json [{"box_2d": [y0, x0, y1, x1], "label": "..."}] ```
             coordinates on a 0-1000 scale, Y FIRST.

Validated against known geometry: on PA chest films the right lung box sits
consistently left of the left lung box, matching radiological convention.
"""
import json
import os
import re

os.environ.setdefault("HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache")
if "HF_TOKEN" not in os.environ:
    with open(os.path.expanduser("~/.cache/huggingface/token")) as f:
        os.environ["HF_TOKEN"] = f.read().strip()

import torch
from PIL import Image
from transformers import pipeline

ROOT = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_samples"
OUT = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_results/localization_official.jsonl"

DETECT = ('Detect the {obj}. Output a JSON list where each entry contains the 2D bounding '
          'box in "box_2d" and a text label in "label".')


def parse_boxes(text):
    """-> [(label, [x0,y0,x1,y1] normalised)] ; source is [y0,x0,y1,x1] on a 0-1000 scale."""
    out = []
    for m in re.finditer(r'\{[^{}]*\}', text):
        blob = m.group(0)
        b = re.search(r'"box_2d"\s*:\s*\[([^\]]+)\]', blob)
        if not b:
            continue
        try:
            v = [float(x) for x in b.group(1).split(",")]
        except ValueError:
            continue
        if len(v) != 4:
            continue
        scale = 1000.0 if max(v) > 1.5 else 1.0
        y0, x0, y1, x1 = [n / scale for n in v]
        lab = re.search(r'"label"\s*:\s*"([^"]*)"', blob)
        out.append(((lab.group(1) if lab else ""), [min(x0, x1), min(y0, y1),
                                                    max(x0, x1), max(y0, y1)]))
    return out


def iou(a, b):
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    ua = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def main():
    pipe = pipeline("image-text-to-text", model="google/medgemma-1.5-4b-it",
                    torch_dtype=torch.bfloat16, device="cuda")

    def detect(img, obj, mnt=256):
        msgs = [{"role": "user", "content": [
            {"type": "image", "image": img},
            {"type": "text", "text": DETECT.format(obj=obj)}]}]
        return pipe(text=msgs, max_new_tokens=mnt,
                    do_sample=False)[0]["generated_text"][-1]["content"]

    fout = open(OUT, "w")

    def rec(**kw):
        fout.write(json.dumps(kw, ensure_ascii=False) + "\n")
        fout.flush()

    # ---------- VinDr-CXR: real radiologist boxes, per finding class ----------
    vindr = json.load(open(f"{ROOT}/not_in_training/vindr_cxr/meta.json"))
    for r in vindr:
        img = Image.open(f"{ROOT}/not_in_training/vindr_cxr/{r['file']}").convert("RGB")
        W, H = r["orig_width"], r["orig_height"]
        # ground truth boxes grouped by class
        by_cls = {}
        for b in r["bounding_boxes_pixel_xyxy"]:
            by_cls.setdefault(b["class_name"], []).append(
                [b["x_min"]/W, b["y_min"]/H, b["x_max"]/W, b["y_max"]/H])
        for cls, gtboxes in by_cls.items():
            raw = detect(img, cls.lower())
            preds = parse_boxes(raw)
            best = max((max(iou(p, g) for g in gtboxes) for _, p in preds), default=0.0)
            rec(exp="vindr_finding", file=r["file"], query=cls, n_pred=len(preds),
                best_iou=best, gt_boxes=gtboxes,
                pred_boxes=[p for _, p in preds], raw=raw[:400])

    # ---------- DeepLesion: CT lesion boxes ----------
    dl = json.load(open(f"{ROOT}/not_in_training/deeplesion_ct/meta.json"))
    for r in dl:
        img = Image.open(f"{ROOT}/not_in_training/deeplesion_ct/{r['file']}").convert("RGB")
        x, y, w, h = r["bounding_boxes_normalized_xywh"][0]
        gt = [x, y, x+w, y+h]
        for q in ["lesion", f"{r['lesion_type']} lesion"]:
            raw = detect(img, q)
            preds = parse_boxes(raw)
            best = max((iou(p, gt) for _, p in preds), default=0.0)
            rec(exp="deeplesion_lesion", file=r["file"], query=q, n_pred=len(preds),
                best_iou=best, gt_boxes=[gt], pred_boxes=[p for _, p in preds], raw=raw[:400])

    # ---------- BraTS: brain MRI tumour box from the segmentation mask ----------
    import numpy as np
    brats = json.load(open(f"{ROOT}/not_in_training/brats2023/meta.json"))
    for r in brats:
        d = f"{ROOT}/not_in_training/brats2023"
        img = Image.open(f"{d}/{r['file']}").convert("RGB")
        m = np.array(Image.open(f"{d}/{r['seg_mask_file']}").convert("L"))
        ys, xs = np.nonzero(m > 0)
        hh, ww = m.shape
        gt = [xs.min()/ww, ys.min()/hh, (xs.max()+1)/ww, (ys.max()+1)/hh]
        for q in ["tumor", "brain tumor"]:
            raw = detect(img, q)
            preds = parse_boxes(raw)
            best = max((iou(p, gt) for _, p in preds), default=0.0)
            rec(exp="brats_tumor", file=r["file"], query=q, n_pred=len(preds),
                best_iou=best, gt_boxes=[gt], pred_boxes=[p for _, p in preds], raw=raw[:400])

    # ---------- synthetic marker: is the box image-dependent at all? ----------
    for name in ["top_left", "top_right", "bottom_left", "bottom_right"]:
        for ds in ["vindr_cxr", "chexpert"]:
            p = f"/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_results/diagnostics/marker_{ds}_{name}.png"
            if not os.path.exists(p):
                continue
            img = Image.open(p).convert("RGB")
            true_c = {"top_left": (0.17, 0.17), "top_right": (0.83, 0.17),
                      "bottom_left": (0.17, 0.83), "bottom_right": (0.83, 0.83)}[name]
            r_ = 0.09
            gt = [true_c[0]-r_, true_c[1]-r_, true_c[0]+r_, true_c[1]+r_]
            raw = detect(img, "bright white circular marker")
            preds = parse_boxes(raw)
            best = max((iou(p_, gt) for _, p_ in preds), default=0.0)
            rec(exp="marker", file=f"{ds}_{name}", query="white marker", n_pred=len(preds),
                best_iou=best, gt_boxes=[gt], pred_boxes=[p_ for _, p_ in preds], raw=raw[:300])

    fout.close()
    print(f"done -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
