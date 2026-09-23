"""MR (BraTS) re-test with MedGemma 1.5's multi-slice 3D input format.

Gap being closed: every earlier BraTS result used ONE axial t1c slice. MedGemma 1.5
supports "three-dimensional volume representations of CT and MRI", and the official
CT notebook shows the message layout: instruction text, then (image, "SLICE n") for
each sampled slice, then the query.

MRI has no Hounsfield scale, so the CT three-window RGB trick does not apply. Slices
are instead windowed per-volume on the 1st/99th percentile of non-zero voxels and
replicated across RGB — the same normalisation used to build the 2D samples, so the
only variable versus the earlier run is 1 slice vs many.

Also closes a second gap: t1n / t2f / t2w were never downloaded, so only t1c had
been seen. Here all four sequences are compared on the same case.
"""
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
from huggingface_hub import hf_hub_download
from PIL import Image

REPO = "obi77/brats23-first-10-examples"
PREFIX = "ASNR-MICCAI-BraTS2023-GLI-Challenge-TrainingData"
OUT = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_results/mr3d_official.jsonl"
CASES = ["BraTS-GLI-00000-000", "BraTS-GLI-00002-000", "BraTS-GLI-00005-000"]
MAX_SLICE = 85


def win(sl):
    nz = sl[sl > 0]
    lo, hi = (np.percentile(nz, 1), np.percentile(nz, 99)) if nz.size else (0, 1)
    if hi <= lo:
        hi = lo + 1
    v = (np.clip(sl, lo, hi) - lo) / (hi - lo) * 255.0
    return np.stack([v] * 3, axis=-1).astype(np.uint8)


def main():
    model_id = "google/medgemma-1.5-4b-it"
    kw = dict(dtype=torch.bfloat16, device_map="auto", offload_buffers=True)
    processor = transformers.AutoProcessor.from_pretrained(model_id, use_fast=True, **kw)
    model = transformers.AutoModelForImageTextToText.from_pretrained(model_id, **kw)
    print("model loaded", flush=True)

    def run(messages, mnt=400):
        inputs = processor.apply_chat_template(
            messages, add_generation_prompt=True, continue_final_message=False,
            return_tensors="pt", tokenize=True, return_dict=True)
        with torch.inference_mode():
            inputs = inputs.to(model.device, dtype=torch.bfloat16)
            seq = model.generate(**inputs, do_sample=False, max_new_tokens=mnt)
        resp = processor.post_process_image_text_to_text(seq, skip_special_tokens=True)[0]
        dec = processor.post_process_image_text_to_text(inputs["input_ids"],
                                                        skip_special_tokens=True)[0]
        i = resp.find(dec)
        if 0 <= i <= 2:
            resp = resp[i + len(dec):]
        return resp.strip()

    QUERIES = [
        ("modality", "What imaging modality is this? Answer with a short term only."),
        ("tumor_present", "Is there a tumor visible? Answer yes or no, then name the most "
                          "likely tumor type in a few words."),
        ("findings", "Describe the most notable findings. If the images do not permit a "
                     "confident read, say so."),
    ]
    INSTR = ("You are an instructor teaching medical students. You are analyzing a contiguous "
             "block of MRI slices from a brain scan. Please review the slices provided below "
             "carefully.")

    fout = open(OUT, "w")
    for case in CASES:
        # ---- all four sequences, single mid-tumour slice each
        segp = hf_hub_download(REPO, f"{PREFIX}/{case}/{case}-seg.nii.gz", repo_type="dataset")
        seg = nib.load(segp).get_fdata()
        zc = int(np.argmax((seg > 0).sum(axis=(0, 1))))

        for seq_name in ["t1c", "t1n", "t2f", "t2w"]:
            p = hf_hub_download(REPO, f"{PREFIX}/{case}/{case}-{seq_name}.nii.gz",
                                repo_type="dataset")
            vol = nib.load(p).get_fdata()
            img = Image.fromarray(win(np.rot90(vol[:, :, zc])))
            for tag, q in QUERIES:
                out = run([{"role": "user", "content": [
                    {"type": "image", "image": img}, {"type": "text", "text": q}]}])
                fout.write(json.dumps({"case": case, "mode": "single_slice", "sequence": seq_name,
                                       "query": tag, "output": out}, ensure_ascii=False) + "\n")
                fout.flush()
                print(f"[{case}/{seq_name}/1slice/{tag}] {out[:90]!r}", flush=True)

        # ---- official multi-slice 3D on t1c
        p = hf_hub_download(REPO, f"{PREFIX}/{case}/{case}-t1c.nii.gz", repo_type="dataset")
        vol = nib.load(p).get_fdata()
        nz = vol.shape[2]
        idx = [int(round(i / MAX_SLICE * (nz - 1))) for i in range(1, min(MAX_SLICE, nz) + 1)]
        # skip empty slices at the head/tail of the skull
        slices = [win(np.rot90(vol[:, :, z])) for z in idx if vol[:, :, z].max() > 0]
        print(f"[{case}] volume {vol.shape} -> {len(slices)} slices", flush=True)
        for tag, q in QUERIES:
            content = [{"type": "text", "text": INSTR}]
            for n, sl in enumerate(slices, 1):
                content.append({"type": "image", "image": Image.fromarray(sl)})
                content.append({"type": "text", "text": f"SLICE {n}"})
            content.append({"type": "text", "text": "\n\n" + q})
            out = run([{"role": "user", "content": content}])
            fout.write(json.dumps({"case": case, "mode": "official_3d", "sequence": "t1c",
                                   "n_slices": len(slices), "query": tag,
                                   "output": out}, ensure_ascii=False) + "\n")
            fout.flush()
            print(f"[{case}/3D/{tag}] {out[:110]!r}", flush=True)

    fout.close()
    print(f"done -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
