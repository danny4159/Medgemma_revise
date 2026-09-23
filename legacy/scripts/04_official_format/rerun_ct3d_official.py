"""CT re-test using MedGemma 1.5's OFFICIAL 3D pipeline.

The earlier CT conclusion ("MedGemma calls axial CT slices a chest X-ray") used a
single pre-windowed 8-bit PNG key slice. That is not how 1.5 is meant to receive CT.
Per the official notebook (google-health/medgemma,
notebooks/high_dimensional_ct_hugging_face.ipynb) the pipeline is:

  1. sample up to 85 slices uniformly across the volume
  2. window each slice with THREE Hounsfield windows into the R/G/B channels:
       R (-1024, 1024) wide   G (-135, 215) soft tissue   B (0, 80) brain
     each linearly normalised to 0-255
  3. one user turn: instruction text, then (image, "SLICE n") for every slice,
     then the query text
  4. processor.apply_chat_template(..., add_generation_prompt=True, tokenize=True,
     return_dict=True) -> model.generate(do_sample=False)

This script reproduces that exactly, and contrasts it with the single-slice input
I used before, on the same volumes.

Data: TotalSegmentator-CT-Lite (real CT NIfTI, Hounsfield units preserved),
pulled case-by-case out of a 22GB remote zip with HTTP range requests.
"""
import io
import json
import os

os.environ.setdefault("HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache")
if "HF_TOKEN" not in os.environ:
    with open(os.path.expanduser("~/.cache/huggingface/token")) as f:
        os.environ["HF_TOKEN"] = f.read().strip()

import nibabel as nib
import numpy as np
import torch
import transformers
from huggingface_hub import hf_hub_url
from PIL import Image

WORK = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_samples/not_in_training/ct3d"
OUT = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_results/ct3d_official.jsonl"
MAX_SLICE = 85
CASES = ["Images/s0338.nii.gz", "Images/s0147.nii.gz", "Images/s1394.nii.gz"]


def norm(vol, lo, hi):
    v = np.clip(vol, lo, hi).astype(np.float32)
    v -= lo
    v /= (hi - lo)
    return v * 255.0


def window_rgb(sl):
    """Official three-window RGB encoding of one CT slice (Hounsfield units in)."""
    clips = [(-1024, 1024), (-135, 215), (0, 80)]
    return np.round(np.stack([norm(sl, a, b) for a, b in clips], axis=-1), 0).astype(np.uint8)


def fetch_cases():
    import remotezip
    os.makedirs(WORK, exist_ok=True)
    url = hf_hub_url("YongchengYAO/TotalSegmentator-CT-Lite", "Images.zip", repo_type="dataset")
    rz = remotezip.RemoteZip(url, headers={"Authorization": f"Bearer {os.environ['HF_TOKEN']}"})
    paths = []
    for name in CASES:
        local = os.path.join(WORK, os.path.basename(name))
        if not os.path.exists(local):
            with open(local, "wb") as f:
                f.write(rz.read(name))
        paths.append(local)
        print(f"  got {local} ({os.path.getsize(local)/1e6:.1f} MB)", flush=True)
    return paths


def main():
    paths = fetch_cases()

    model_id = "google/medgemma-1.5-4b-it"
    kw = dict(dtype=torch.bfloat16, device_map="auto", offload_buffers=True)
    processor = transformers.AutoProcessor.from_pretrained(model_id, use_fast=True, **kw)
    model = transformers.AutoModelForImageTextToText.from_pretrained(model_id, **kw)
    print("model loaded", flush=True)

    def run(messages, max_new_tokens=400):
        inputs = processor.apply_chat_template(
            messages, add_generation_prompt=True, continue_final_message=False,
            return_tensors="pt", tokenize=True, return_dict=True)
        with torch.inference_mode():
            inputs = inputs.to(model.device, dtype=torch.bfloat16)
            seq = model.generate(**inputs, do_sample=False, max_new_tokens=max_new_tokens)
        resp = processor.post_process_image_text_to_text(seq, skip_special_tokens=True)[0]
        dec = processor.post_process_image_text_to_text(inputs["input_ids"],
                                                        skip_special_tokens=True)[0]
        i = resp.find(dec)
        if 0 <= i <= 2:
            resp = resp[i + len(dec):]
        return resp.strip()

    QUERIES = [
        ("modality", "What imaging modality is this? Answer with a short term only."),
        ("bodypart", "Which region of the body is shown? Answer with a short term only."),
        ("findings", "Describe the most notable findings. If the images do not permit a "
                     "confident read, say so."),
    ]

    fout = open(OUT, "w")
    for p in paths:
        case = os.path.basename(p).replace(".nii.gz", "")
        vol = nib.load(p).get_fdata()          # (X, Y, Z) Hounsfield units
        nz = vol.shape[2]
        idx = [int(round(i / MAX_SLICE * (nz - 1))) for i in range(1, min(MAX_SLICE, nz) + 1)]
        slices = [window_rgb(np.rot90(vol[:, :, z])) for z in idx]
        print(f"[{case}] volume {vol.shape}, using {len(slices)} slices, "
              f"HU range {vol.min():.0f}..{vol.max():.0f}", flush=True)

        # ---- A: official multi-slice 3D format
        instruction = ("You are an instructor teaching medical students. You are analyzing a "
                       "contiguous block of CT slices from a body scan. Please review the "
                       "slices provided below carefully.")
        for tag, q in QUERIES:
            content = [{"type": "text", "text": instruction}]
            for n, sl in enumerate(slices, 1):
                content.append({"type": "image", "image": Image.fromarray(sl)})
                content.append({"type": "text", "text": f"SLICE {n}"})
            content.append({"type": "text", "text": "\n\n" + q})
            out = run([{"role": "user", "content": content}])
            fout.write(json.dumps({"case": case, "mode": "official_3d", "n_slices": len(slices),
                                   "query": tag, "output": out}, ensure_ascii=False) + "\n")
            fout.flush()
            print(f"   [3D/{tag}] {out[:110]!r}", flush=True)

        # ---- B: the single mid slice, the way I did it before (control)
        mid = slices[len(slices)//2]
        for tag, q in QUERIES:
            content = [{"type": "image", "image": Image.fromarray(mid)},
                       {"type": "text", "text": q}]
            out = run([{"role": "user", "content": content}])
            fout.write(json.dumps({"case": case, "mode": "single_slice", "n_slices": 1,
                                   "query": tag, "output": out}, ensure_ascii=False) + "\n")
            fout.flush()
            print(f"   [1slice/{tag}] {out[:110]!r}", flush=True)

    fout.close()
    print(f"done -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
