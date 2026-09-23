"""Tests candidate remedies for each diagnosed limitation.

R1  constrained-format collapse -> can chain-of-thought or a two-stage prompt recover
    the cell index that the model evidently "knows" in natural language?
R2  no coordinate output -> can localisation be recovered WITHOUT any grounding ability,
    by asking a presence question on image crops (sliding-window localisation)?
R3  how fine is the spatial information really? binary halves work at ~75%; does a
    3-way (thirds) question still beat chance? This decides prompt-fix vs fine-tuning.
R4  premise compliance -> does an explicit "say so if absent" guard stop fabrication?
R5  CT confusion -> does telling the model the modality repair its reading?
"""
import json
import os

os.environ.setdefault("HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache")
if "HF_TOKEN" not in os.environ:
    with open(os.path.expanduser("~/.cache/huggingface/token")) as f:
        os.environ["HF_TOKEN"] = f.read().strip()

import torch
from PIL import Image
from transformers import pipeline

OUT = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_results/remedies.jsonl"
WORK = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_results/diagnostics"
RAW = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_results/raw_outputs.jsonl"

GRID_LEGEND = (
    "The image is divided into a 3x3 grid of 9 equal cells numbered 1-9 in reading order "
    "(1=top-left, 2=top-center, 3=top-right, 4=middle-left, 5=center, 6=middle-right, "
    "7=bottom-left, 8=bottom-center, 9=bottom-right). "
)


def main():
    rows = [json.loads(l) for l in open(RAW)]
    grid_items = [r for r in rows if r["method"] == "1_grid"]
    desc_by_image = {r["image"]: r["output"] for r in rows if r["method"] == "3_desc"}

    pipe = pipeline("image-text-to-text", model="google/medgemma-1.5-4b-it",
                    torch_dtype=torch.bfloat16, device="cuda")

    def ask(image, text, mnt=128, history=None):
        content = [{"type": "image", "image": image}, {"type": "text", "text": text}]
        msgs = (history or []) + [{"role": "user", "content": content}]
        out = pipe(text=msgs, max_new_tokens=mnt, do_sample=False)
        return out[0]["generated_text"][-1]["content"].strip()

    fout = open(OUT, "w")

    def rec(**kw):
        fout.write(json.dumps(kw, ensure_ascii=False) + "\n")
        fout.flush()

    for n, it in enumerate(grid_items):
        img = Image.open(it["image"]).convert("RGB")
        gt = it["gt"]
        base = {"dataset": it["dataset"], "image": it["image"],
                "gt_cell": gt["cell"], "gt_bbox": gt["bbox_xyxy"]}

        # ---- R1a: chain of thought before committing to a cell number
        o = ask(img, GRID_LEGEND + "First describe in one sentence where the main lesion or "
                "abnormality lies (which side, how high). Then, on a new line, write "
                "'ANSWER: <cell number>'.", 160)
        rec(exp="R1a_cot", **base, output=o)

        # ---- R1b: two-stage, re-using the model's own free-text description as context
        prior = desc_by_image.get(it["image"], "")
        hist = [{"role": "user", "content": [{"type": "image", "image": img},
                                             {"type": "text", "text": "Describe the main abnormality "
                                              "in this image: what it is and where it is located."}]},
                {"role": "assistant", "content": [{"type": "text", "text": prior}]}]
        o = ask(img, GRID_LEGEND + "Based on the location you just described, which single cell "
                "contains it? Respond with only the cell number.", 64, history=hist)
        rec(exp="R1b_twostage", **base, output=o, prior=prior)

        # ---- R2: crop-based localisation (no grounding needed, just presence detection)
        W, H = img.size
        crops = {"left": (0, 0, W // 2, H), "right": (W // 2, 0, W, H),
                 "top": (0, 0, W, H // 2), "bottom": (0, H // 2, W, H)}
        for name, box in crops.items():
            c = img.crop(box)
            o = ask(c, "Is there a lesion or abnormality visible in this image? Answer only yes or no.", 64)
            rec(exp="R2_crop", **base, crop=name, output=o)

        # ---- R3: how fine is the spatial signal? thirds instead of halves
        o = ask(img, "Is the main lesion or abnormality in the LEFT third, CENTRE third, or RIGHT "
                "third of this image, as seen in the image frame? Answer with one word.", 96)
        rec(exp="R3_thirds_h", **base, output=o)
        o = ask(img, "Is the main lesion or abnormality in the UPPER third, MIDDLE third, or LOWER "
                "third of this image? Answer with one word.", 96)
        rec(exp="R3_thirds_v", **base, output=o)

        if (n + 1) % 5 == 0:
            print(f"  [{n+1}/{len(grid_items)}]", flush=True)

    # ---- R4: does a guard clause stop fabrication on contentless images?
    for nm in ["blank_grey", "pure_noise"]:
        im = Image.open(f"{WORK}/{nm}.png").convert("RGB")
        for tag, prompt in [
            ("bare", "Describe the findings in this chest X-ray."),
            ("guard", "Describe the findings in this chest X-ray. If this image is not a chest "
                      "X-ray, or shows no interpretable anatomy, say so explicitly instead of "
                      "describing findings."),
            ("neutral", "What does this image show? If it is not a medical image, say so."),
        ]:
            rec(exp="R4_guard", dataset=nm, image=nm, variant=tag, output=ask(im, prompt, 200))

    # ---- R5: does naming the modality repair CT reading?
    dl = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_samples/not_in_training/deeplesion_ct"
    meta = json.load(open(f"{dl}/meta.json"))
    for r in meta:
        im = Image.open(f"{dl}/{r['file']}").convert("RGB")
        for tag, prompt in [
            ("bare", "What is the single most likely lesion type or diagnosis visible in this "
                     "image? Respond with a short medical term only."),
            ("hinted", "This is an axial CT slice of the body. What is the single most likely "
                       "lesion type or diagnosis visible in it? Respond with a short medical term only."),
        ]:
            rec(exp="R5_ct_hint", dataset="deeplesion_ct", image=r["file"], variant=tag,
                gt_region=r["lesion_type"], output=ask(im, prompt, 64))

    fout.close()
    print(f"done -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
