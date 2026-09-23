"""Follow-up: is the top/bottom success real spatial perception, or anatomy-mediated inference?

E1 showed top/bottom = 12/16 (8/8 on chest X-rays) while left/right = 7/16 (chance).
A chest X-ray has a strong vertical anatomical gradient (apex -> diaphragm) but is
roughly left-right symmetric. So the model may be reasoning "the disc sits near the
diaphragm, therefore bottom" rather than reading off a coordinate.

E5 removes all anatomy: the same marker on a blank canvas. If top/bottom collapses to
chance there, the E1 result was anatomical inference, not spatial perception.
"""
import json
import os

os.environ.setdefault("HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache")
if "HF_TOKEN" not in os.environ:
    with open(os.path.expanduser("~/.cache/huggingface/token")) as f:
        os.environ["HF_TOKEN"] = f.read().strip()

import torch
from PIL import Image, ImageDraw
from transformers import pipeline

WORK = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_results/diagnostics"
OUT = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_results/diagnostics_followup.jsonl"
MODEL_ID = "google/medgemma-1.5-4b-it"

POSITIONS = [("top_left", 0.17, 0.17, 1), ("top_right", 0.83, 0.17, 3),
             ("bottom_left", 0.17, 0.83, 7), ("bottom_right", 0.83, 0.83, 9)]

PROMPTS = [
    ("E5_blank_grid",
     "The image is divided into a 3x3 grid of 9 equal cells numbered 1-9 in reading order "
     "(1=top-left, 2=top-center, 3=top-right, 4=middle-left, 5=center, 6=middle-right, "
     "7=bottom-left, 8=bottom-center, 9=bottom-right). A black circular marker has been drawn "
     "on this image. Which single cell contains the marker? Respond with only the cell number.", 64),
    ("E5_blank_lr",
     "A black circular marker has been drawn on this image. Is the marker in the LEFT half or "
     "the RIGHT half of the image? Answer only LEFT or RIGHT.", 16),
    ("E5_blank_tb",
     "A black circular marker has been drawn on this image. Is the marker in the TOP half or "
     "the BOTTOM half of the image? Answer only TOP or BOTTOM.", 16),
]


def main():
    os.makedirs(WORK, exist_ok=True)
    tasks = []
    for name, cx, cy, cell in POSITIONS:
        im = Image.new("RGB", (512, 512), (235, 235, 235))
        d = ImageDraw.Draw(im)
        x, y, r = int(cx * 512), int(cy * 512), int(512 * 0.09)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(0, 0, 0))
        p = f"{WORK}/blankmarker_{name}.png"
        im.save(p)
        for exp, prompt, mnt in PROMPTS:
            tasks.append({"exp": exp, "variant": name, "image": p, "prompt": prompt,
                          "max_new_tokens": mnt,
                          "gt": {"cell": cell, "lr": "left" if cx < 0.5 else "right",
                                 "tb": "top" if cy < 0.5 else "bottom"}})

    print(f"{len(tasks)} follow-up tasks", flush=True)
    pipe = pipeline("image-text-to-text", model=MODEL_ID, torch_dtype=torch.bfloat16, device="cuda")
    with open(OUT, "w") as f:
        for t in tasks:
            msgs = [{"role": "user", "content": [
                {"type": "image", "image": Image.open(t["image"]).convert("RGB")},
                {"type": "text", "text": t["prompt"]}]}]
            out = pipe(text=msgs, max_new_tokens=t["max_new_tokens"], do_sample=False)
            t2 = dict(t)
            t2["output"] = out[0]["generated_text"][-1]["content"].strip()
            f.write(json.dumps(t2, ensure_ascii=False) + "\n")
            f.flush()
            print(f"  {t['exp']:15s} {t['variant']:13s} -> {t2['output'][:50]!r}", flush=True)
    print(f"done -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
