"""Runs MedGemma over all evaluation tasks, appending raw outputs to a JSONL file."""
import argparse
import json
import os
import time

os.environ.setdefault("HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache")
if "HF_TOKEN" not in os.environ:
    with open(os.path.expanduser("~/.cache/huggingface/token")) as f:
        os.environ["HF_TOKEN"] = f.read().strip()

import torch
from PIL import Image
from transformers import pipeline

from eval_tasks import build_tasks

MODEL_ID = "google/medgemma-1.5-4b-it"
OUT_PATH = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_results/raw_outputs.jsonl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="only run the first N tasks")
    ap.add_argument("--out", default=OUT_PATH)
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    tasks = build_tasks()
    if args.limit:
        # sample across groups/methods rather than just the head of the list
        seen, sampled = set(), []
        for t in tasks:
            key = (t["dataset"], t["method"])
            if key not in seen:
                seen.add(key)
                sampled.append(t)
        tasks = sampled[: args.limit]

    # resume support: skip tasks already present in the output file
    done = set()
    if os.path.exists(args.out):
        with open(args.out) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    done.add((r["dataset"], r["method"], r["image"], r["prompt"]))
                except json.JSONDecodeError:
                    continue
    tasks = [t for t in tasks
             if (t["dataset"], t["method"], t["image"], t["prompt"]) not in done]

    print(f"{len(tasks)} tasks to run ({len(done)} already done)", flush=True)
    if not tasks:
        return

    pipe = pipeline("image-text-to-text", model=MODEL_ID, torch_dtype=torch.bfloat16, device="cuda")
    print("model loaded", flush=True)

    t_start = time.time()
    with open(args.out, "a") as fout:
        for i, t in enumerate(tasks):
            image = Image.open(t["image"]).convert("RGB")
            messages = [{"role": "user", "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": t["prompt"]},
            ]}]
            try:
                out = pipe(text=messages, max_new_tokens=t["max_new_tokens"], do_sample=False)
                answer = out[0]["generated_text"][-1]["content"].strip()
                err = None
            except Exception as e:
                answer, err = "", f"{type(e).__name__}: {e}"

            fout.write(json.dumps({
                "group": t["group"], "dataset": t["dataset"], "method": t["method"],
                "image": t["image"], "prompt": t["prompt"],
                "output": answer, "gt": t["gt"], "error": err,
            }, ensure_ascii=False) + "\n")
            fout.flush()

            if (i + 1) % 10 == 0 or i == 0:
                el = time.time() - t_start
                rate = el / (i + 1)
                print(f"[{i+1}/{len(tasks)}] {el:.0f}s elapsed, {rate:.2f}s/task, "
                      f"~{rate * (len(tasks) - i - 1) / 60:.1f}min left", flush=True)

    print(f"done in {(time.time() - t_start) / 60:.1f} min -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
