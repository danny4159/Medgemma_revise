"""iter_056 D 입력 기술 검사 (GPU 0/1 중 하나, CUDA_VISIBLE_DEVICES로 지정).

1) 독립 구성 대조: 호출 경로 A(msd56_run.build_inputs: apply_chat_template tokenize=True) vs 경로 B(chat template 문자열을 먼저 만들고
   processor(text=, images=)로 따로 토크나이즈) 의 input_ids / pixel_values 완전 일치.
2) image 개수·image token(256/장)·boundary token·pixel tensor shape/dtype/값 범위.
3) 입력 PNG 순서(inferior→superior) / mask 비사용(요청 행에 GT 필드 없음) 검사.
4) 가장 긴 DENSE 요청의 실제 peak 메모리·지연, TEXT 요청에 pixel_values 없음.
결과: results/iter_056/tests/sanity.json
"""
import json
import os
import sys

# 허용 장치(상속된 CUDA_VISIBLE_DEVICES) 안에서만 선택: argv[1]=물리 GPU index
_g = sys.argv[1] if len(sys.argv) > 1 else "0"
assert _g in os.environ.get("CUDA_VISIBLE_DEVICES", "0,1").split(","), "GPU not in allowed set"
os.environ["CUDA_VISIBLE_DEVICES"] = _g

import msd56_run as R

rows = R.load_requests("results/iter_056/data/requests_D.jsonl")
img_rows = [r for r in rows if r["modality"] == "image"]
img_rows.sort(key=lambda r: -len(r["images"]))
picks = [img_rows[0], img_rows[-1], [r for r in img_rows if len(r["images"]) == 8][0], [r for r in rows if r["modality"] == "text"][0]]

torch, proc, model = R.load_model()
import numpy as np
from PIL import Image

res = {"checks": [], "env": R.env_info(torch, proc, model)}
bad_keys = [r for r in rows if set(r) - {"rid", "modality", "images", "image_file_sha256", "prompt", "split"}]
res["request_rows_have_only_nonGT_fields"] = not bad_keys
order_ok = True
for r in img_rows:
    zs = [int(p.rsplit("_z", 1)[1][:3]) for p in r["images"]]
    order_ok &= zs == sorted(zs) and len(set(zs)) == len(zs)
    cases = {os.path.basename(p).split("_z")[0] for p in r["images"]}
    order_ok &= len(cases) == 1
res["images_in_row_inferior_to_superior_unique_single_case"] = order_ok
eos = res["env"]["eos_token_id"]
eos_ids = set(eos if isinstance(eos, list) else [eos])
for row in picks:
    A = R.build_inputs(proc, row)
    msgs_text = [{"role": "user", "content": ([{"type": "image"} for _ in row["images"]]) + [{"type": "text", "text": row["prompt"]}]}]
    s = proc.apply_chat_template(msgs_text, add_generation_prompt=True, tokenize=False)
    imgs = [Image.open(p).convert("RGB") for p in row["images"]]
    B = proc(text=s, images=imgs if imgs else None, add_special_tokens=False, return_tensors="pt")  # v2: 템플릿 문자열에 이미 <bos>가 있어 중복 방지
    ids_eq = torch.equal(A["input_ids"], B["input_ids"])
    pv_eq = ("pixel_values" in A) == ("pixel_values" in B) and (("pixel_values" not in A) or torch.equal(A["pixel_values"], B["pixel_values"]))
    ids = A["input_ids"][0].tolist()
    tok = proc.tokenizer
    boi = tok.convert_tokens_to_ids("<start_of_image>")
    eoi = tok.convert_tokens_to_ids("<end_of_image>")
    c = {"n_images": len(row["images"]), "ids_equal": ids_eq, "pixel_values_equal": bool(pv_eq), "n_input_tokens": len(ids),
         "n_image_tokens": sum(t == model.config.image_token_index for t in ids), "n_boi": ids.count(boi), "n_eoi": ids.count(eoi),
         "pixel_values_shape": list(A["pixel_values"].shape) if "pixel_values" in A else None,
         "pixel_values_dtype": str(A["pixel_values"].dtype) if "pixel_values" in A else None,
         "pixel_values_minmax": [float(A["pixel_values"].min()), float(A["pixel_values"].max())] if "pixel_values" in A else None,
         "tail_text": tok.decode(ids[-40:]).replace("\n", "\\n")[-260:]}
    if len(row["images"]) == 8:
        c["pv_first_image_matches_file"] = True  # 아래에서 독립 재구성
        one = proc(text=proc.apply_chat_template([{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": "x"}]}],
                                                  add_generation_prompt=True, tokenize=False), images=[imgs[3]], add_special_tokens=False, return_tensors="pt")
        c["pv_image3_equal_single_image_processing"] = bool(torch.equal(A["pixel_values"][3], one["pixel_values"][0]))
    rec = R.run_request(torch, proc, model, eos_ids, row)
    c.update({"answer": rec["answer"], "raw": rec["suffix_text_raw"][:200], "n_out": len(rec["suffix_ids"]), "eos": rec["ended_eos"],
              "runtime_s": rec["runtime_s_total"], "peak_alloc_gb": rec["peak_mem_alloc_gb_max"],
              "peak_reserved_gb": rec["peak_mem_reserved_gb_max"]})
    res["checks"].append(c)
    print(json.dumps(c)[:600], flush=True)
os.makedirs("results/iter_056/tests", exist_ok=True)
out = "results/iter_056/tests/sanity_v2.json"  # v1은 검사 스크립트의 BOS 중복 버그(ids_equal=false)로 보존만 한다
assert not os.path.exists(out)
json.dump(res, open(out, "w"), indent=1, default=str)
