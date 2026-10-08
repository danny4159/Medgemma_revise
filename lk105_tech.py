"""iter_105 D4 기술 대조: worker 저장 출력 vs 래퍼 없는 공식 경로(processor.apply_chat_template + model.generate).

선택한 요청(영상 선택·텍스트 전용·PG 포함)에 대해
 1) 입력 tensor(input_ids, pixel_values, attention_mask 등)가 공식 호출과 동일한지,
 2) 텍스트 전용 입력에 image token과 pixel_values가 없는지,
 3) 공식 greedy generate의 suffix token이 저장된 attempt suffix와 일치하는지
를 확인해 새 결과 파일에 저장한다. 모델 정답률은 검사하지 않는다.
사용: CUDA_VISIBLE_DEVICES=<gpu> <python> lk105_tech.py --system S --stage D4 --gen-dir DIR --workers N --out FILE
"""
import argparse
import hashlib
import json
import os
import sys

import numpy as np

import lk105_run as R
import lk105_spec as S
from report86_common import sha_obj, read_jsonl_complete, save, CAPS

PICK = ["img-N-o0", "img-W-o1", "txt-C-o0", "txt-N-o1", "pg-S1", "pg-S2"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", required=True)
    ap.add_argument("--stage", default="D4")
    ap.add_argument("--gen-dir", required=True)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n-images", type=int, default=2)
    a = ap.parse_args()
    from rsna_diag import generate as G
    torch, processor, model = R.load_model(a.system)
    rows, raw = R.stage_rows(a.stage)
    recs = {}
    for k in range(a.workers):
        for r in read_jsonl_complete(R.shard_dir(a.gen_dir, a.system, k) / "outputs.jsonl"):
            recs[r["id"]] = r
    transform = None
    if a.system == "CURE":
        sys.path.insert(0, str(R.OFFICIAL_DIR.parent))
        from vlm_research_kit.data.transforms_factory import create_image_transforms
        transform = create_image_transforms(use_model_specific_transforms=True, model_name="pil_with_augmentations", bbox_format="cxcywh",
                                            image_size=[448, 448], is_train=False,
                                            augmenter_override_params={"apply_clahe": True, "clahe_clip_limit": [3., 3.]})
    eos = model.generation_config.eos_token_id
    eos = [eos] if isinstance(eos, int) else eos
    img_tok = processor.image_token_id
    checks = []
    for row in rows[:a.n_images]:
        iid = row["ImageID"]
        if a.system == "CURE":
            im = transform(raw[iid]["raw_path"])["pixel_values"]
        else:
            im, _, _ = G.load_image(row["image"])
        for key in PICK:
            rid = f"{iid}|{a.system}|{key}"
            rec = recs[rid]
            q = next(x for x in R.requests(a.stage, a.system) if x["id"] == rid)
            content = [{"type": "text", "text": q["prompt"]}]
            if q["modality"] == "image":
                content = [{"type": "image", "image": im}] + content
            official = processor.apply_chat_template([{"role": "user", "content": content}], add_generation_prompt=True, tokenize=True,
                                                     return_dict=True, return_tensors="pt", padding=True)
            same_ids = official["input_ids"][0].tolist() == rec["input_ids"]
            n_img = int((official["input_ids"] == img_tok).sum())
            has_pix = "pixel_values" in official
            dev = {k: (v.to("cuda", dtype=torch.bfloat16) if k == "pixel_values" else v.to("cuda")) for k, v in official.items()}
            with torch.no_grad():
                out = model.generate(**dev, max_new_tokens=rec["attempts"][-1]["cap"], do_sample=False)
            ids = out[0, dev["input_ids"].shape[1]:].tolist()
            # worker는 cap 래더를 쓰지만 저장된 마지막 attempt(EOS 도달)의 suffix는 같은 cap에서 같은 prefix를 가져야 한다
            stored = rec["attempts"][-1]["suffix_ids"]
            checks.append({"id": rid, "modality": q["modality"], "input_ids_equal": bool(same_ids), "n_image_tokens": n_img,
                           "has_pixel_values": bool(has_pix), "suffix_equal": ids == stored, "n_new": len(ids),
                           "pixel_sha256_equal": (hashlib.sha256(np.asarray(im).tobytes()).hexdigest() == rec["pixel_sha256"]) if q["modality"] == "image" else None,
                           "text_only_no_image": (n_img == 0 and not has_pix) if q["modality"] == "text" else None})
    ok = all(c["input_ids_equal"] and c["suffix_equal"] and (c["text_only_no_image"] in (None, True)) and (c["pixel_sha256_equal"] in (None, True))
             for c in checks)
    save(a.out, {"system": a.system, "stage": a.stage, "n_checks": len(checks), "all_pass": bool(ok), "checks": checks,
                 "torch": torch.__version__, "python": sys.executable})
    print(json.dumps({"system": a.system, "n": len(checks), "all_pass": ok}))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
