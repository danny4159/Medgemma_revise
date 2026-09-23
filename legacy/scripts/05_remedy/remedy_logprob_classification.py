"""Remedy: replace the generated yes/no with a calibrated score from token logits.

Problem being attacked (measured earlier in this project):
  CheXpert  accuracy .769  specificity .807  precision .267
  NIH       accuracy .780  specificity .832  precision .167
  and the precision was shown to be exactly what the base rate predicts
  (prevalence ~.10-.12). Decoding a single yes/no fixes one operating point, so
  there is no way to trade sensitivity for the specificity that precision needs.

Idea: the model already computes a distribution over the answer token. Read
  s = logP(yes) - logP(no)
instead of the sampled word. That yields a ranked score per (image, label), from
which an ROC curve and any operating point can be derived.

What this tests
  - AUC: is there discriminative signal at all, independent of threshold?
    (if AUC ~ .5 the model genuinely cannot tell, and no threshold will help)
  - the precision reachable at high-specificity thresholds vs the default point
  - threshold picked per dataset by leave-one-image-out, so the reported operating
    point is not fitted on the sample it is scored on
"""
import json
import os

os.environ.setdefault("HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache")
if "HF_TOKEN" not in os.environ:
    with open(os.path.expanduser("~/.cache/huggingface/token")) as f:
        os.environ["HF_TOKEN"] = f.read().strip()

import torch
import transformers
from PIL import Image

ROOT = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_samples"
OUT = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_results/remedy_logprob.jsonl"

CHEX = ["No Finding", "Enlarged Cardiomediastinum", "Cardiomegaly", "Lung Opacity",
        "Lung Lesion", "Edema", "Consolidation", "Pneumonia", "Atelectasis",
        "Pneumothorax", "Pleural Effusion", "Pleural Other", "Fracture", "Support Devices"]
NIH = ["Atelectasis", "Cardiomegaly", "Effusion", "Infiltration", "Mass", "Nodule",
       "Pneumonia", "Pneumothorax", "Consolidation", "Edema", "Emphysema", "Fibrosis",
       "Pleural_Thickening", "Hernia"]


def main():
    mid = "google/medgemma-1.5-4b-it"
    proc = transformers.AutoProcessor.from_pretrained(mid, use_fast=True)
    model = transformers.AutoModelForImageTextToText.from_pretrained(
        mid, dtype=torch.bfloat16, device_map="cuda")
    model.eval()
    tok = proc.tokenizer
    YES = [tok.encode(s, add_special_tokens=False)[0] for s in ["Yes", "yes", " Yes"]]
    NO = [tok.encode(s, add_special_tokens=False)[0] for s in ["No", "no", " No"]]

    def score(img, label):
        q = f"Does this chest X-ray show {label}? Answer only yes or no."
        msgs = [{"role": "user", "content": [
            {"type": "image", "image": img}, {"type": "text", "text": q}]}]
        inp = proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True,
                                       return_dict=True, return_tensors="pt")
        inp = {k: (v.to("cuda", dtype=torch.bfloat16) if k == "pixel_values" else v.to("cuda"))
               for k, v in inp.items()}
        with torch.no_grad():
            lg = model(**inp).logits[0, -1].float()
        lp = torch.log_softmax(lg, -1)
        s = (torch.logsumexp(lp[YES], 0) - torch.logsumexp(lp[NO], 0)).item()
        # also record what greedy decoding would have produced
        said = "yes" if lp[YES].max() > lp[NO].max() else "no"
        return s, said

    fout = open(OUT, "w")

    chex = json.load(open(f"{ROOT}/not_in_training/chexpert/meta.json"))
    for r in chex:
        img = Image.open(f"{ROOT}/not_in_training/chexpert/{r['file']}").convert("RGB")
        for lab in CHEX:
            if lab in r["uncertain"]:
                continue
            s, said = score(img, lab)
            fout.write(json.dumps({"dataset": "chexpert", "file": r["file"], "label": lab,
                                   "gt": int(lab in r["present"]), "score": s,
                                   "greedy": said}) + "\n")
        fout.flush()
        print(f"chexpert {r['file']} done", flush=True)

    nih = json.load(open(f"{ROOT}/not_in_training/nih_chestxray14/meta.json"))
    for r in nih:
        img = Image.open(f"{ROOT}/not_in_training/nih_chestxray14/{r['file']}").convert("RGB")
        present = [f for f in r["findings"].split("|") if f and f != "No Finding"]
        for lab in NIH:
            s, said = score(img, lab.replace("_", " "))
            fout.write(json.dumps({"dataset": "nih_chestxray14", "file": r["file"], "label": lab,
                                   "gt": int(lab in present), "score": s,
                                   "greedy": said}) + "\n")
        fout.flush()
        print(f"nih {r['file']} done", flush=True)

    fout.close()
    print(f"done -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
