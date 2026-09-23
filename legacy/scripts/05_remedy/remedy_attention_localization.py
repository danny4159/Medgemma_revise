"""Remedy: read the lesion location out of the model's attention, not its text.

Rationale chain (all from this project's own measurements):
  1. The 256 image tokens the LM receives DO carry position precisely
     (marker 16/16, err 0.069; inserted lesion 6/6, err 0.042-0.051).
  2. The text channel cannot report it: predicted box centres are no better than
     always guessing the image centre (VinDr 0.245 vs 0.265 baseline; DeepLesion
     0.245 vs 0.226, i.e. worse), and shrinking the boxes does not help.
  3. Therefore the information exists but the verbalisation path is broken.
  => Bypass the text channel: ask a question about the finding and read WHERE the
     language model attends over the 16x16 image-token grid.

Method
  - build a normal chat prompt: image + "Is there {finding} in this image?"
  - forward with output_attentions=True
  - locate the image-token span in the input via the image token id
  - take attention from the final prompt position (the one that generates the
    answer) to each image token, averaged over heads, for a chosen layer band
  - reshape to 16x16 -> saliency map -> peak and centroid as predicted location
  - score centre error against ground truth, and against the "always image centre"
    baseline that the text channel failed to beat

Control: the same readout is run with an IRRELEVANT query on the same image. If
attention localisation is real, the relevant query should localise better than the
irrelevant one; if both look the same, the map only reflects image saliency.
"""
import json
import os

os.environ.setdefault("HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache")
if "HF_TOKEN" not in os.environ:
    with open(os.path.expanduser("~/.cache/huggingface/token")) as f:
        os.environ["HF_TOKEN"] = f.read().strip()

import numpy as np
import torch
import transformers
from PIL import Image

ROOT = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_samples"
OUT = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_results/remedy_attention.jsonl"
MODEL_ID = "google/medgemma-1.5-4b-it"


def main():
    proc = transformers.AutoProcessor.from_pretrained(MODEL_ID, use_fast=True)
    model = transformers.AutoModelForImageTextToText.from_pretrained(
        MODEL_ID, dtype=torch.bfloat16, device_map="cuda", attn_implementation="eager")
    model.eval()

    img_tok_id = model.config.image_token_id if hasattr(model.config, "image_token_id") else None
    if img_tok_id is None:
        img_tok_id = proc.tokenizer.convert_tokens_to_ids("<image_soft_token>")
    print("image token id:", img_tok_id, flush=True)

    def saliency(image, question):
        msgs = [{"role": "user", "content": [
            {"type": "image", "image": image}, {"type": "text", "text": question}]}]
        inputs = proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True,
                                          return_dict=True, return_tensors="pt")
        inputs = {k: (v.to("cuda", dtype=torch.bfloat16) if k == "pixel_values"
                      else v.to("cuda")) for k, v in inputs.items()}
        with torch.no_grad():
            out = model(**inputs, output_attentions=True)
        ids = inputs["input_ids"][0]
        pos = (ids == img_tok_id).nonzero(as_tuple=True)[0]
        if pos.numel() == 0:
            return None
        att = out.attentions            # tuple(L) of (B, H, Q, K)
        L = len(att)
        maps = {}
        for name, layers in {"early": range(0, L // 3),
                             "mid": range(L // 3, 2 * L // 3),
                             "late": range(2 * L // 3, L)}.items():
            acc = None
            for li in layers:
                a = att[li][0].float()               # (H, Q, K)
                v = a[:, -1, :].mean(0)              # last query position, avg heads
                v = v[pos]                           # -> image tokens only
                acc = v if acc is None else acc + v
            m = (acc / max(1, len(list(layers)))).cpu().numpy()
            n = int(round(len(m) ** 0.5))
            maps[name] = m[: n * n].reshape(n, n)
        return maps

    def peak_and_centroid(m):
        n = m.shape[0]
        k = int(np.argmax(m))
        peak = ((k % n + 0.5) / n, (k // n + 0.5) / n)
        w = m - m.min()
        if w.sum() <= 0:
            return peak, peak
        ys, xs = np.mgrid[0:n, 0:n]
        cx = float((w * (xs + 0.5)).sum() / w.sum() / n)
        cy = float((w * (ys + 0.5)).sum() / w.sum() / n)
        return peak, (cx, cy)

    def gt_centre(boxes):
        return [((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) for b in boxes]

    fout = open(OUT, "w")
    IRRELEVANT = "What is the capital city of France?"

    # ---------------- VinDr: per-finding ----------------
    vindr = json.load(open(f"{ROOT}/not_in_training/vindr_cxr/meta.json"))
    for r in vindr:
        img = Image.open(f"{ROOT}/not_in_training/vindr_cxr/{r['file']}").convert("RGB")
        W, H = r["orig_width"], r["orig_height"]
        by = {}
        for b in r["bounding_boxes_pixel_xyxy"]:
            by.setdefault(b["class_name"], []).append(
                [b["x_min"] / W, b["y_min"] / H, b["x_max"] / W, b["y_max"] / H])
        for cls, boxes in by.items():
            maps = saliency(img, f"Is there {cls.lower()} in this image? Answer yes or no.")
            ctrl = saliency(img, IRRELEVANT)
            if maps is None:
                continue
            rec = {"dataset": "vindr_cxr", "file": r["file"], "query": cls,
                   "gt_centres": gt_centre(boxes)}
            for band in maps:
                p, c = peak_and_centroid(maps[band])
                rec[f"{band}_peak"] = p
                rec[f"{band}_centroid"] = c
                if ctrl is not None:
                    pc, cc = peak_and_centroid(ctrl[band])
                    rec[f"{band}_ctrl_peak"] = pc
                    rec[f"{band}_ctrl_centroid"] = cc
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fout.flush()

    # ---------------- DeepLesion + BraTS ----------------
    dl = json.load(open(f"{ROOT}/not_in_training/deeplesion_ct/meta.json"))
    for r in dl:
        img = Image.open(f"{ROOT}/not_in_training/deeplesion_ct/{r['file']}").convert("RGB")
        x, y, w, h = r["bounding_boxes_normalized_xywh"][0]
        maps = saliency(img, "Is there a lesion in this image? Answer yes or no.")
        ctrl = saliency(img, IRRELEVANT)
        if maps is None:
            continue
        rec = {"dataset": "deeplesion_ct", "file": r["file"], "query": "lesion",
               "gt_centres": [(x + w / 2, y + h / 2)]}
        for band in maps:
            p, c = peak_and_centroid(maps[band])
            rec[f"{band}_peak"] = p
            rec[f"{band}_centroid"] = c
            if ctrl is not None:
                pc, cc = peak_and_centroid(ctrl[band])
                rec[f"{band}_ctrl_peak"] = pc
                rec[f"{band}_ctrl_centroid"] = cc
        fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fout.flush()

    brats = json.load(open(f"{ROOT}/not_in_training/brats2023/meta.json"))
    for r in brats:
        d = f"{ROOT}/not_in_training/brats2023"
        img = Image.open(f"{d}/{r['file']}").convert("RGB")
        m = np.array(Image.open(f"{d}/{r['seg_mask_file']}").convert("L"))
        ys, xs = np.nonzero(m > 0)
        hh, ww = m.shape
        gt = ((xs.min() + xs.max()) / 2 / ww, (ys.min() + ys.max()) / 2 / hh)
        maps = saliency(img, "Is there a tumor in this image? Answer yes or no.")
        ctrl = saliency(img, IRRELEVANT)
        if maps is None:
            continue
        rec = {"dataset": "brats2023", "file": r["file"], "query": "tumor",
               "gt_centres": [gt]}
        for band in maps:
            p, c = peak_and_centroid(maps[band])
            rec[f"{band}_peak"] = p
            rec[f"{band}_centroid"] = c
            if ctrl is not None:
                pc, cc = peak_and_centroid(ctrl[band])
                rec[f"{band}_ctrl_peak"] = pc
                rec[f"{band}_ctrl_centroid"] = cc
        fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fout.flush()

    fout.close()
    print(f"done -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
