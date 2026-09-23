"""Confirms the vertical/horizontal asymmetry with a larger, balanced sample.

E5 (n=4) suggested the model tracks TOP/BOTTOM but not LEFT/RIGHT, on a blank canvas
with no anatomy. This repeats the test over a 4x4 grid of marker positions (n=16 per
axis) so the asymmetry can be tested against chance.
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
OUT = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_results/diagnostics_axis.jsonl"

LR = ("A black circular marker has been drawn on this image. Is the marker in the LEFT half "
      "or the RIGHT half of the image? Answer only LEFT or RIGHT.")
TB = ("A black circular marker has been drawn on this image. Is the marker in the TOP half "
      "or the BOTTOM half of the image? Answer only TOP or BOTTOM.")


def main():
    os.makedirs(WORK, exist_ok=True)
    coords = [0.15, 0.35, 0.65, 0.85]
    tasks = []
    for cx in coords:
        for cy in coords:
            im = Image.new("RGB", (512, 512), (235, 235, 235))
            r = int(512 * 0.08)
            x, y = int(cx * 512), int(cy * 512)
            ImageDraw.Draw(im).ellipse([x - r, y - r, x + r, y + r], fill=(0, 0, 0))
            p = f"{WORK}/axis_{cx}_{cy}.png"
            im.save(p)
            gt = {"lr": "left" if cx < 0.5 else "right", "tb": "top" if cy < 0.5 else "bottom",
                  "cx": cx, "cy": cy}
            tasks.append({"exp": "E6_lr", "image": p, "prompt": LR, "gt": gt})
            tasks.append({"exp": "E6_tb", "image": p, "prompt": TB, "gt": gt})

    print(f"{len(tasks)} tasks", flush=True)
    pipe = pipeline("image-text-to-text", model="google/medgemma-1.5-4b-it",
                    torch_dtype=torch.bfloat16, device="cuda")
    with open(OUT, "w") as f:
        for t in tasks:
            msgs = [{"role": "user", "content": [
                {"type": "image", "image": Image.open(t["image"]).convert("RGB")},
                {"type": "text", "text": t["prompt"]}]}]
            out = pipe(text=msgs, max_new_tokens=16, do_sample=False)
            t2 = dict(t)
            t2["output"] = out[0]["generated_text"][-1]["content"].strip()
            f.write(json.dumps(t2, ensure_ascii=False) + "\n")
            f.flush()
    print("done", flush=True)


if __name__ == "__main__":
    main()
