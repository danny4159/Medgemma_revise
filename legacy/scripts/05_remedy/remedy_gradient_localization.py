"""Remedy 2: gradient saliency over image tokens (raw attention already failed).

Why gradients rather than attention: raw attention is a known-poor saliency proxy
(attention sinks dominate), and indeed in this project its peak was identical for a
lesion question and for "What is the capital of France?". Gradients measure what the
answer actually DEPENDS on, which is the quantity of interest here:

  does the model's yes/no answer about a finding depend on where that finding is?

Method
  - forward image + "Is there {finding} in this image? Answer yes or no."
  - take the logit of the "Yes" token at the answer position
  - backprop to the projected image embeddings (the 256 tokens the LM reads)
  - saliency per token = L2 norm of grad, or |grad . activation| (both computed)
  - reshape 16x16 -> peak / centroid -> compare centre error to GT

Controls
  - the same readout with an irrelevant question (capital of France)
  - the "always image centre" baseline that the text box channel failed to beat
If the relevant query does not localise better than both, the LM's answer does not
use lesion position, despite that position being present in the tokens.
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
OUT = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_results/remedy_gradient.jsonl"
MODEL_ID = "google/medgemma-1.5-4b-it"


def main():
    proc = transformers.AutoProcessor.from_pretrained(MODEL_ID, use_fast=True)
    model = transformers.AutoModelForImageTextToText.from_pretrained(
        MODEL_ID, dtype=torch.bfloat16, device_map="cuda")
    model.eval()
    tok = proc.tokenizer
    yes_id = tok.encode("Yes", add_special_tokens=False)[0]
    img_tok_id = getattr(model.config, "image_token_id", None) or \
        tok.convert_tokens_to_ids("<image_soft_token>")

    lm = model.model.language_model
    embed = lm.embed_tokens if hasattr(lm, "embed_tokens") else model.get_input_embeddings()

    def sal(image, question):
        msgs = [{"role": "user", "content": [
            {"type": "image", "image": image}, {"type": "text", "text": question}]}]
        inputs = proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True,
                                          return_dict=True, return_tensors="pt")
        ids = inputs["input_ids"].to("cuda")
        pix = inputs["pixel_values"].to("cuda", dtype=torch.bfloat16)
        pos = (ids[0] == img_tok_id).nonzero(as_tuple=True)[0]
        if pos.numel() == 0:
            return None

        # build inputs_embeds so we can differentiate w.r.t. the image tokens
        with torch.no_grad():
            vt = model.model.vision_tower(pixel_values=pix).last_hidden_state
            feats = model.model.multi_modal_projector(vt)[0]        # (256, D)
        txt = embed(ids)[0].clone()                                  # (T, D)
        feats = feats.detach().clone().requires_grad_(True)
        merged = txt.clone()
        merged[pos] = feats.to(merged.dtype)
        merged = merged.unsqueeze(0)

        out = model.model.language_model(inputs_embeds=merged)
        h = out.last_hidden_state[:, -1, :]
        logits = model.lm_head(h) if hasattr(model, "lm_head") else model.get_output_embeddings()(h)
        score = logits[0, yes_id]
        model.zero_grad(set_to_none=True)
        score.backward()

        g = feats.grad.detach().float()                              # (256, D)
        gnorm = g.norm(dim=-1).cpu().numpy()
        gxa = (g * feats.detach().float()).sum(-1).abs().cpu().numpy()
        n = int(round(len(gnorm) ** 0.5))
        return {"gnorm": gnorm[: n * n].reshape(n, n),
                "gxa": gxa[: n * n].reshape(n, n)}

    def pc(m):
        n = m.shape[0]
        k = int(np.argmax(m))
        peak = ((k % n + 0.5) / n, (k // n + 0.5) / n)
        w = m - m.min()
        if w.sum() <= 0:
            return peak, peak
        ys, xs = np.mgrid[0:n, 0:n]
        return peak, (float((w * (xs + .5)).sum() / w.sum() / n),
                      float((w * (ys + .5)).sum() / w.sum() / n))

    IRR = "What is the capital city of France?"
    fout = open(OUT, "w")

    def emit(ds, f, q, gts, image, question):
        m = sal(image, question)
        c = sal(image, IRR)
        if m is None:
            return
        rec = {"dataset": ds, "file": f, "query": q, "gt_centres": gts}
        for kind in ["gnorm", "gxa"]:
            p, ct = pc(m[kind])
            rec[f"{kind}_peak"], rec[f"{kind}_centroid"] = p, ct
            if c is not None:
                p2, c2 = pc(c[kind])
                rec[f"{kind}_ctrl_peak"], rec[f"{kind}_ctrl_centroid"] = p2, c2
        fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fout.flush()

    vindr = json.load(open(f"{ROOT}/not_in_training/vindr_cxr/meta.json"))
    for r in vindr:
        img = Image.open(f"{ROOT}/not_in_training/vindr_cxr/{r['file']}").convert("RGB")
        W, H = r["orig_width"], r["orig_height"]
        by = {}
        for b in r["bounding_boxes_pixel_xyxy"]:
            by.setdefault(b["class_name"], []).append(
                ((b["x_min"] + b["x_max"]) / 2 / W, (b["y_min"] + b["y_max"]) / 2 / H))
        for cls, cs in by.items():
            emit("vindr_cxr", r["file"], cls, cs, img,
                 f"Is there {cls.lower()} in this image? Answer yes or no.")

    dl = json.load(open(f"{ROOT}/not_in_training/deeplesion_ct/meta.json"))
    for r in dl:
        img = Image.open(f"{ROOT}/not_in_training/deeplesion_ct/{r['file']}").convert("RGB")
        x, y, w, h = r["bounding_boxes_normalized_xywh"][0]
        emit("deeplesion_ct", r["file"], "lesion", [(x + w / 2, y + h / 2)], img,
             "Is there a lesion in this image? Answer yes or no.")

    brats = json.load(open(f"{ROOT}/not_in_training/brats2023/meta.json"))
    for r in brats:
        d = f"{ROOT}/not_in_training/brats2023"
        img = Image.open(f"{d}/{r['file']}").convert("RGB")
        m = np.array(Image.open(f"{d}/{r['seg_mask_file']}").convert("L"))
        ys, xs = np.nonzero(m > 0)
        hh, ww = m.shape
        emit("brats2023", r["file"], "tumor",
             [((xs.min() + xs.max()) / 2 / ww, (ys.min() + ys.max()) / 2 / hh)], img,
             "Is there a tumor in this image? Answer yes or no.")

    fout.close()
    print(f"done -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
