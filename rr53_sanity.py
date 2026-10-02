"""iter_053 공식 입력 구성 검사 (processor만 로드, 모델/GPU 불필요).

운영 경로 G.build_inputs / G.build_inputs_text(apply_chat_template(tokenize=True))의 input_ids·pixel_values를, (a) 독립 디코드·중앙 square padding한 배열과
(b) chat template을 문자열로 렌더링한 뒤 processor(text=..., images=...)를 직접 호출한 결과와 대조한다. text-only는 pixel_values와 image token이 없어야 한다.
python rr53_sanity.py --stages D,E,F --out results/iter_053/tests/input_tensor.json   (기존 파일 덮어쓰기 금지)
"""
import argparse
import json
import os
import sys
import time

import numpy as np
from PIL import Image

from rr53_data import OUT
from rsna_diag import generate as G


def independent_padded(path):
    a = np.asarray(Image.open(path))
    assert a.dtype == np.uint8
    rgb = np.repeat(a[:, :, None], 3, axis=2) if a.ndim == 2 else a
    h, w = rgb.shape[:2]
    side = max(h, w)
    top, left = (side - h) // 2, (side - w) // 2
    out = np.zeros((side, side, 3), np.uint8)
    out[top:top + h, left:left + w] = rgb
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stages", default="D,E,F")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("refuse to overwrite")
    os.environ.setdefault("HF_HOME", G.HF_HOME)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    import torch
    import transformers
    proc = transformers.AutoProcessor.from_pretrained(G.MODEL_ID, revision=G.MODEL_REVISION)
    img_tok = proc.tokenizer.convert_tokens_to_ids("<image_soft_token>")  # <start_of_image> 1개 + 이 token 256개가 영상 자리
    assert img_tok is not None and img_tok != proc.tokenizer.unk_token_id
    checks = dict(n=0, image=0, text=0, pad_array_mismatch=0, ids_mismatch=0, pixel_mismatch=0, text_has_image=0, image_token_count_bad=0,
                  prompt_not_in_decoded=0, template_shape_bad=0)
    bad = []
    seen = set()
    t0 = time.time()
    for st in a.stages.split(","):
        rows = [json.loads(l) for l in open(f"{OUT}/requests/requests_{st}.jsonl")]
        for r in rows:
            key = (r["image"], r["prompt_sha256"], r["modality"])
            if key in seen:
                continue
            seen.add(key)
            checks["n"] += 1
            if r["modality"] == "image":
                checks["image"] += 1
                img, aff, px = G.load_image(r["image"])
                ind = independent_padded(r["image"])
                if not np.array_equal(np.asarray(img), ind) or px != r["input_pixel_sha256"]:
                    checks["pad_array_mismatch"] += 1
                    bad.append(("pad", r["request_id"]))
                prod = G.build_inputs(proc, img, r["prompt"])
                msgs = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": r["prompt"]}]}]
                txt = proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
                man = proc(text=txt, images=[Image.fromarray(ind)], return_tensors="pt", add_special_tokens=False)  # template 문자열이 이미 <bos>를 가진다
                if not torch.equal(prod["input_ids"], man["input_ids"]):
                    checks["ids_mismatch"] += 1
                    bad.append(("ids", r["request_id"]))
                if not torch.equal(prod["pixel_values"], man["pixel_values"]):
                    checks["pixel_mismatch"] += 1
                    bad.append(("pix", r["request_id"]))
                n_img = int((prod["input_ids"] == img_tok).sum())
                if n_img != proc.image_seq_length or tuple(prod["pixel_values"].shape) != (1, 3, 896, 896):
                    checks["image_token_count_bad"] += 1
                    bad.append(("imgtok", r["request_id"], n_img, tuple(prod["pixel_values"].shape)))
                ids = prod["input_ids"][0].tolist()
            else:
                checks["text"] += 1
                prod = G.build_inputs_text(proc, r["prompt"])
                msgs = [{"role": "user", "content": [{"type": "text", "text": r["prompt"]}]}]
                txt = proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
                man = proc(text=txt, return_tensors="pt", add_special_tokens=False)
                if not torch.equal(prod["input_ids"], man["input_ids"]):
                    checks["ids_mismatch"] += 1
                    bad.append(("ids_text", r["request_id"]))
                if "pixel_values" in prod or any(k.startswith("pixel") for k in prod) or int((prod["input_ids"] == img_tok).sum()) != 0:
                    checks["text_has_image"] += 1
                    bad.append(("text_image", r["request_id"]))
                ids = prod["input_ids"][0].tolist()
            dec = proc.tokenizer.decode(ids, skip_special_tokens=False)
            if r["prompt"] not in dec:
                checks["prompt_not_in_decoded"] += 1
                bad.append(("prompt", r["request_id"]))
            if not (dec.count("<start_of_turn>user") == 1 and dec.endswith("<start_of_turn>model\n") and "<end_of_turn>\n<start_of_turn>model\n" in dec):
                checks["template_shape_bad"] += 1
                bad.append(("template", r["request_id"]))
    passed = all(v == 0 for k, v in checks.items() if k not in ("n", "image", "text"))
    res = dict(passed=passed, checks=checks, bad=bad[:20], seconds=time.time() - t0, stages=a.stages, model_revision=G.MODEL_REVISION,
               transformers=transformers.__version__, torch=torch.__version__, chat_template_sha256=G.sha((proc.chat_template or "").encode()),
               image_seq_length=proc.image_seq_length, image_size=str(proc.image_processor.size))
    tmp = a.out + ".tmp"
    json.dump(res, open(tmp, "w"), indent=1)
    os.replace(tmp, a.out)
    print(json.dumps(res, indent=1))
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
