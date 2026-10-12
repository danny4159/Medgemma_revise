"""iter_116 공식 방식 직접 generate 대조 (4건: 영상 2 + text-only 2). worker 경로(pg43_run/generate)를 import하지 않고
모델 카드 방식(processor.apply_chat_template → model.generate)과 독립 padding으로 입력 tensor·생성 token을 재현한다.
사용: CUDA_VISIBLE_DEVICES=<허용 GPU 하나> python ed116_directcheck.py <TECH 완료 dir> <출력 json>"""
import glob
import hashlib
import json
import os
import sys

import numpy as np
from PIL import Image

os.environ.setdefault("HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
import torch
import transformers

ID, REV = "google/medgemma-1.5-4b-it", "91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def indep_pad(path):
    a = np.asarray(Image.open(path).convert("RGB"))  # uint8 L→RGB 채널 복제
    h, w = a.shape[:2]
    side = max(h, w)
    canvas = np.zeros((side, side, 3), np.uint8)
    t, l = (side - h) // 2, (side - w) // 2
    canvas[t:t + h, l:l + w] = a
    return Image.fromarray(canvas), sha(canvas.tobytes())


def main(gen_dir, out):
    recs = {}
    for f in sorted(glob.glob(gen_dir + "/gen_worker*.jsonl")):
        for ln in open(f):
            r = json.loads(ln)
            recs[r["request_id"]] = r
    rows = [json.loads(l) for l in open("results/iter_116/requests/TECH.jsonl")]
    byk = {(r["patient"], r["cond"]): r for r in rows}
    pats = sorted({r["patient"] for r in rows})
    pick = [byk[(pats[0], "R")], byk[(pats[1], "N")], byk[(pats[0], "T")], byk[(pats[2], "T")]]
    proc = transformers.AutoProcessor.from_pretrained(ID, revision=REV)
    model = transformers.AutoModelForImageTextToText.from_pretrained(ID, revision=REV, dtype=torch.bfloat16, device_map="cuda").eval()
    eos = model.generation_config.eos_token_id
    eos = set(eos if isinstance(eos, list) else [eos])
    res = []
    for row in pick:
        rec = recs[row["request_id"]]
        content = [{"type": "text", "text": row["prompt"]}]
        pad_sha = None
        if row["modality"] == "image":
            img, pad_sha = indep_pad(row["image"])
            content = [{"type": "image", "image": img}] + content
        inputs = proc.apply_chat_template([{"role": "user", "content": content}], add_generation_prompt=True, tokenize=True,
                                          return_dict=True, return_tensors="pt").to(model.device, dtype=torch.bfloat16)
        ids = inputs["input_ids"][0].tolist()
        n_in = len(ids)
        with torch.no_grad():
            out_ids = model.generate(**inputs, max_new_tokens=row["caps"][0], do_sample=False)
        suffix = out_ids[0][n_in:].tolist()
        res.append(dict(request_id=row["request_id"], cond=row["cond"], modality=row["modality"],
                        has_pixel_values="pixel_values" in inputs, keys=sorted(inputs.keys()),
                        n_image_tokens=sum(t == model.config.image_token_index for t in ids),
                        input_ids_sha256_direct=sha(json.dumps(ids).encode()), input_ids_sha256_record=rec["input_ids_sha256"],
                        input_ids_equal=sha(json.dumps(ids).encode()) == rec["input_ids_sha256"],
                        indep_pad_pixel_sha256=pad_sha, record_pixel_sha256=rec["input_pixel_sha256"],
                        pixel_equal=(pad_sha == rec["input_pixel_sha256"]) if row["modality"] == "image" else (rec["input_pixel_sha256"] is None),
                        suffix_equal=suffix == rec["suffix_ids"], n_suffix_direct=len(suffix), n_suffix_record=len(rec["suffix_ids"]),
                        text_only_has_no_image=(row["modality"] != "text") or ("pixel_values" not in inputs and sum(t == model.config.image_token_index for t in ids) == 0)))
    ok = all(r["input_ids_equal"] and r["pixel_equal"] and r["suffix_equal"] and r["text_only_has_no_image"] for r in res)
    json.dump(dict(all_pass=ok, n=len(res), results=res, transformers=transformers.__version__, torch=torch.__version__,
                   cuda_visible_devices=os.environ.get("CUDA_VISIBLE_DEVICES")), open(out, "x"), indent=1)
    print("all_pass", ok)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
