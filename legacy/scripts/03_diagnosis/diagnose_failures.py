"""Controlled experiments probing WHY MedGemma failed on the evaluation tasks.

H1  spatial answers are a fixed template, not perception
      -> E1 unmistakable synthetic marker at known positions
      -> E2 contentless images (flat grey / pure noise) still get confident answers
H2  the model has an affirmative ("finding is present") bias
      -> E3 absurd findings that cannot be in the image + negated phrasing
H3  answers come from medical priors rather than from the pixels
      -> E2 report on a noise image
H4  CT is misread as chest X-ray because of an X-ray-dominant prior
      -> E4 forced-choice modality question
"""
import json
import os

os.environ.setdefault("HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache")
if "HF_TOKEN" not in os.environ:
    with open(os.path.expanduser("~/.cache/huggingface/token")) as f:
        os.environ["HF_TOKEN"] = f.read().strip()

import numpy as np
import torch
from PIL import Image, ImageDraw
from transformers import pipeline

ROOT = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_samples"
WORK = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_results/diagnostics"
OUT = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_results/diagnostics.jsonl"
MODEL_ID = "google/medgemma-1.5-4b-it"

GRID_PROMPT = (
    "The image is divided into a 3x3 grid of 9 equal cells numbered 1-9 in reading order "
    "(1=top-left, 2=top-center, 3=top-right, 4=middle-left, 5=center, 6=middle-right, "
    "7=bottom-left, 8=bottom-center, 9=bottom-right). "
)
MARKER_GRID = GRID_PROMPT + (
    "A bright white circular marker has been drawn on this image. "
    "Which single cell contains the marker? Respond with only the cell number."
)
MARKER_BBOX = (
    "A bright white circular marker has been drawn on this image. Give its bounding box as "
    "normalized coordinates [x_min, y_min, x_max, y_max], each between 0.0 and 1.0, with "
    "(0.0, 0.0) at the top-left corner. Respond with only the four numbers in brackets."
)
MARKER_HALF = (
    "A bright white circular marker has been drawn on this image. Is the marker in the LEFT half "
    "or the RIGHT half of the image, as seen in the image frame? Answer only LEFT or RIGHT."
)
MARKER_TOPBOT = (
    "A bright white circular marker has been drawn on this image. Is the marker in the TOP half "
    "or the BOTTOM half of the image? Answer only TOP or BOTTOM."
)

# marker positions: normalized centre -> expected 3x3 cell
POSITIONS = [
    ("top_left", 0.17, 0.17, 1), ("top_right", 0.83, 0.17, 3),
    ("bottom_left", 0.17, 0.83, 7), ("bottom_right", 0.83, 0.83, 9),
]


def draw_marker(src_path, cx, cy, out_path):
    """Draw a large unmistakable white disc with a black ring at (cx, cy)."""
    im = Image.open(src_path).convert("RGB")
    W, H = im.size
    r = int(min(W, H) * 0.09)
    x, y = int(cx * W), int(cy * H)
    d = ImageDraw.Draw(im)
    d.ellipse([x - r - 4, y - r - 4, x + r + 4, y + r + 4], fill=(0, 0, 0))
    d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255))
    im.save(out_path)
    return [(x - r) / W, (y - r) / H, (x + r) / W, (y + r) / H]


def build():
    os.makedirs(WORK, exist_ok=True)
    tasks = []

    # ---------------- E1: synthetic marker at known positions ----------------
    bases = [
        ("brats2023", f"{ROOT}/not_in_training/brats2023/01.jpg"),
        ("deeplesion_ct", f"{ROOT}/not_in_training/deeplesion_ct/00.png"),
        ("vindr_cxr", f"{ROOT}/not_in_training/vindr_cxr/00.png"),
        ("chexpert", f"{ROOT}/not_in_training/chexpert/00.jpg"),
    ]
    for ds, src in bases:
        for name, cx, cy, cell in POSITIONS:
            p = f"{WORK}/marker_{ds}_{name}.png"
            box = draw_marker(src, cx, cy, p)
            for method, prompt, mnt in [
                ("E1_marker_grid", MARKER_GRID, 64),
                ("E1_marker_bbox", MARKER_BBOX, 48),
                ("E1_marker_half_lr", MARKER_HALF, 16),
                ("E1_marker_half_tb", MARKER_TOPBOT, 16),
            ]:
                tasks.append({"exp": method, "dataset": ds, "variant": name, "image": p,
                              "prompt": prompt, "max_new_tokens": mnt,
                              "gt": {"cell": cell, "bbox_xyxy": box,
                                     "lr": "left" if cx < 0.5 else "right",
                                     "tb": "top" if cy < 0.5 else "bottom"}})

    # ---------------- E2: contentless images ----------------
    flat = Image.new("RGB", (512, 512), (128, 128, 128))
    flat.save(f"{WORK}/blank_grey.png")
    rng = np.random.default_rng(0)
    Image.fromarray(rng.integers(0, 256, (512, 512, 3), dtype=np.uint8)).save(f"{WORK}/pure_noise.png")
    for nm in ["blank_grey", "pure_noise"]:
        p = f"{WORK}/{nm}.png"
        for method, prompt, mnt in [
            ("E2_void_grid", GRID_PROMPT + "Which single cell contains the main lesion or "
             "abnormality? Respond with only the cell number.", 64),
            ("E2_void_bbox", "Give the bounding box of the main lesion or abnormality as normalized "
             "coordinates [x_min, y_min, x_max, y_max]. Respond with only the four numbers.", 48),
            ("E2_void_report", "Describe the findings in this chest X-ray.", 200),
            ("E2_void_modality", "What imaging modality is this image? Answer with a short term only.", 24),
        ]:
            tasks.append({"exp": method, "dataset": nm, "variant": nm, "image": p,
                          "prompt": prompt, "max_new_tokens": mnt, "gt": {"note": "no content"}})

    # ---------------- E3: affirmative bias ----------------
    chex = json.load(open(f"{ROOT}/not_in_training/chexpert/meta.json"))
    ABSURD = ["a brain tumor", "dental caries", "a fractured femur"]
    for r in chex:
        img = f"{ROOT}/not_in_training/chexpert/{r['file']}"
        for a in ABSURD:
            tasks.append({"exp": "E3_absurd", "dataset": "chexpert", "variant": a, "image": img,
                          "prompt": f"Does this chest X-ray show {a}? Answer only yes or no.",
                          "max_new_tokens": 64, "gt": {"expected": "no"}})
        # negated phrasing of three real labels, to see whether answers stay consistent
        for lab in ["Cardiomegaly", "Pneumothorax", "Pleural Effusion"]:
            gold_present = lab in r["present"]
            tasks.append({"exp": "E3_negated", "dataset": "chexpert", "variant": lab, "image": img,
                          "prompt": f"Is this chest X-ray free of {lab}? Answer only yes or no.",
                          "max_new_tokens": 64,
                          "gt": {"present": gold_present, "expected": "no" if gold_present else "yes"}})

    # ---------------- E4: forced-choice modality ----------------
    MC = ("Which of these best describes this image? "
          "(A) chest radiograph / X-ray  (B) axial CT slice  (C) brain MRI  (D) endoscopy photograph. "
          "Answer with only the letter.")
    for ds, folder, ext, gold in [
        ("deeplesion_ct", "not_in_training/deeplesion_ct", "png", "B"),
        ("brats2023", "not_in_training/brats2023", "jpg", "C"),
        ("vindr_cxr", "not_in_training/vindr_cxr", "png", "A"),
    ]:
        for i in range(10):
            p = f"{ROOT}/{folder}/{i:02d}.{ext}"
            if not os.path.exists(p):
                continue
            tasks.append({"exp": "E4_modality_mc", "dataset": ds, "variant": f"{i:02d}", "image": p,
                          "prompt": MC, "max_new_tokens": 16, "gt": {"expected": gold}})
            tasks.append({"exp": "E4_modality_open", "dataset": ds, "variant": f"{i:02d}", "image": p,
                          "prompt": "What imaging modality is this image? Answer with a short term only.",
                          "max_new_tokens": 24, "gt": {"expected": gold}})
    return tasks


def main():
    tasks = build()
    print(f"{len(tasks)} diagnostic tasks", flush=True)
    pipe = pipeline("image-text-to-text", model=MODEL_ID, torch_dtype=torch.bfloat16, device="cuda")
    print("model loaded", flush=True)
    with open(OUT, "w") as f:
        for i, t in enumerate(tasks):
            image = Image.open(t["image"]).convert("RGB")
            msgs = [{"role": "user", "content": [
                {"type": "image", "image": image}, {"type": "text", "text": t["prompt"]}]}]
            out = pipe(text=msgs, max_new_tokens=t["max_new_tokens"], do_sample=False)
            t2 = dict(t)
            t2["output"] = out[0]["generated_text"][-1]["content"].strip()
            f.write(json.dumps(t2, ensure_ascii=False) + "\n")
            f.flush()
            if (i + 1) % 25 == 0:
                print(f"  [{i+1}/{len(tasks)}]", flush=True)
    print(f"done -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
