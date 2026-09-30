"""iter_039 정상 입력 대조: 공식 notebook 경로(pipeline image-text-to-text)와 wrapper(G.build_inputs)의 tensor 전체·생성 token 비교.
CUDA_VISIBLE_DEVICES=<gpu> python pg39_sanity.py IMAGE_PNG OUT_JSON
입력 영상은 8-bit PNG(변환 완료본). 문장은 합성 예시이며 환자 정보가 아니다.
"""
import json
import os
import sys

import numpy as np

import pg39_spec as S
from rsna_diag import generate as G

img_path, out = sys.argv[1], sys.argv[2]
if os.path.exists(out):
    sys.exit("output exists")
torch, proc, model = G.load_model()
env = G.env_info(torch, proc, model)
eos = env["eos_token_id"]
eos_ids = set(eos if isinstance(eos, list) else [eos])
sents = {"qA": "Nodular opacity in the right upper lobe.", "qB": "Cardiomegaly."}
plist = S.build_prompts(sents)
res = {"env": {k: env[k] for k in ("model_revision", "transformers", "torch", "dtype", "eos_token_id", "chat_template_sha256")}, "cases": []}
from transformers import pipeline
pipe = pipeline("image-text-to-text", model=model, processor=proc)
image, aff, pxs = G.load_image(img_path)
for cond, tg, prompt, caps in [plist[0], plist[2], plist[6]]:
    inp = G.build_inputs(proc, image, prompt)
    msgs = [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": prompt}]}]
    case = {"cond": cond, "tensor": {}}
    try:
        from transformers.pipelines.image_text_to_text import Chat
        ref = pipe.preprocess(Chat(msgs))
        ref = {k: v for k, v in ref.items() if k != 'text'}
    except Exception as e:  # 공식 pipeline API 차이 기록
        ref = None
        case["pipeline_preprocess_error"] = repr(e)[:300]
    if ref is not None:
        keys_eq = set(ref) == set(inp)
        case["keys_equal"] = keys_eq
        allok = keys_eq
        for k in sorted(set(ref) & set(inp)):
            a, b = ref[k].cpu(), inp[k].cpu()
            if k == 'pixel_values':
                case['pixel_values_dtype_pipeline_vs_wrapper_raw'] = [str(a.dtype), str(b.dtype)]
                b = b.to(a.dtype)
            same = a.shape == b.shape and a.dtype == b.dtype and bool((a == b).all())
            case["tensor"][k] = {"shape": list(a.shape), "dtype": str(a.dtype), "equal": same}
            allok &= same
        case["all_tensors_equal"] = allok
    # 생성: wrapper vs pipeline (같은 max_new_tokens)
    cap = 400
    a = G.generate(torch, proc, model, inp, cap, eos_ids)
    case["wrapper_n_new"] = a["n_new"]
    case["wrapper_ended_eos"] = a["ended_eos"]
    case["wrapper_last_token"] = a["suffix_ids"][-1] if a["suffix_ids"] else None
    o = pipe(text=msgs, max_new_tokens=cap, do_sample=False, return_full_text=False)
    ptxt = o[0]["generated_text"]
    wtxt = proc.tokenizer.decode(a["suffix_ids"], skip_special_tokens=True)
    case["pipeline_text_equals_wrapper_text_skip_special"] = ptxt.strip() == wtxt.strip()
    case["wrapper_text_head"] = wtxt[:80] if False else None
    res["cases"].append(case)
    print(cond, case.get("all_tensors_equal"), case["pipeline_text_equals_wrapper_text_skip_special"], flush=True)
res["pass"] = all(c.get("all_tensors_equal") and c["pipeline_text_equals_wrapper_text_skip_special"] for c in res["cases"])
json.dump(res, open(out, "w"), indent=1, default=str)
print("PASS" if res["pass"] else "FAIL")
