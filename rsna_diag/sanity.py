"""공식 예제 사용법 sanity (iter_009). 병변 성능 평가가 아니다.

1) 예제(RGBA)에 대해 notebook 원문 전처리(emulation)와 값 보존 전처리의 입력 차이를 기록한다.
2) 두 입력에 대해 공식 prompt(object_name='right clavicle')로 실제 생성하고, HF pipeline("image-text-to-text")
   호출과 우리 runner의 processed input·생성 텍스트를 대조한다.
3) RSNA development 1건에서도 pipeline vs runner를 대조한다.
사용: CUDA_VISIBLE_DEVICES=0 python -m rsna_diag.sanity
"""
import json
import os
import time

import numpy as np
from PIL import Image

from . import generate as G, geometry, overlay, parse as PA, prompts as P

OUT = "results/iter_009/sanity"
EX = "results/iter_009/source/official/Chest_Xray_PA_3-8-2010.png"


def strip(t):
    t = t.replace("<end_of_turn>", "").strip()
    return t


def run_pair(torch, proc, model, pipe, eos_ids, image, prompt, tag):
    inp = G.build_inputs(proc, image, prompt)
    a = G.generate(torch, proc, model, inp, 1000, eos_ids)
    text_runner = proc.tokenizer.decode(a["suffix_ids"], skip_special_tokens=False)
    msgs = [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": prompt}]}]
    out = pipe(text=msgs, max_new_tokens=1000, do_sample=False)
    text_pipe = out[0]["generated_text"][-1]["content"]
    # pipeline이 만든 processed input과 runner의 input 대조 (가능한 경우)
    pipe_inputs_equal = None
    try:
        from transformers.pipelines.image_text_to_text import Chat
        pi = pipe.preprocess(Chat(msgs))
        pipe_inputs_equal = {
            "input_ids_equal": bool((pi["input_ids"].cpu() == inp["input_ids"]).all()) if pi["input_ids"].shape == inp["input_ids"].shape else False,
            "pixel_values_equal_after_bf16_cast": bool((pi["pixel_values"].cpu().to(torch.bfloat16) == inp["pixel_values"].to(torch.bfloat16)).all()),
            "pipeline_pixel_dtype": str(pi["pixel_values"].dtype), "runner_pixel_dtype_before_cast": str(inp["pixel_values"].dtype),
            "pipeline_input_ids_len": int(pi["input_ids"].shape[-1]), "runner_input_ids_len": int(inp["input_ids"].shape[-1])}
    except Exception as e:  # pipeline 내부 API 차이: 실패를 기록하고 텍스트 대조는 계속한다
        pipe_inputs_equal = {"error": repr(e)[:300]}
    same = strip(text_runner) == strip(text_pipe) or strip(text_pipe) in strip(text_runner)
    return {"tag": tag, "n_input_tokens": int(inp["input_ids"].shape[1]), "runner_n_new": a["n_new"], "runner_ended_eos": a["ended_eos"],
            "runtime_s": a["runtime_s"], "peak_mem_alloc_gb": a["peak_mem_alloc_gb"],
            "runner_text_raw": text_runner, "pipeline_text": text_pipe,
            "text_equal_after_strip_or_substring": bool(same), "pipeline_vs_runner_inputs": pipe_inputs_equal,
            "parsed_runner": PA.parse_response(text_runner, a["ended_eos"]),
            "parsed_pipeline_text": PA.parse_response(text_pipe + "<end_of_turn>", True)}


def main():
    os.makedirs(OUT, exist_ok=True)
    torch, proc, model = G.load_model()
    import transformers  # HF_HUB_OFFLINE 설정(load_model) 이후에 import
    env = G.env_info(torch, proc, model)
    eos = env["eos_token_id"]
    eos_ids = set(eos if isinstance(eos, list) else [eos])
    pipe = transformers.pipeline("image-text-to-text", model=model, processor=proc)
    ex = Image.open(EX)
    arr = np.asarray(ex)
    emu, aff = geometry.notebook_pad_emulation(arr)
    pres = geometry.pad_square(geometry.to_uint8_rgb_preserving(arr))[0]
    diff = np.abs(emu.astype(int) - pres.astype(int))
    input_diff = {"shape_emulation": list(emu.shape), "shape_preserving": list(pres.shape),
                  "max_abs_diff": int(diff.max()), "mean_abs_diff": float(diff.mean()),
                  "frac_pixels_diff_gt0": float((diff > 0).mean()), "frac_pixels_diff_gt1": float((diff > 1).mean()),
                  "example_mode": ex.mode, "example_size": list(ex.size), "alpha_min": int(arr[..., 3].min()),
                  "pad_affine": list(aff), "note": "skimage 미설치(pip 불가)로 notebook 전처리는 numpy emulation이다. 원문 그대로의 실행이 아니다."}
    Image.fromarray(emu).save(f"{OUT}/example_notebook_emulation.png")
    Image.fromarray(pres).save(f"{OUT}/example_value_preserving.png")
    prompt_ex = P.official_long(target="right clavicle")
    recs = []
    for tag, a in (("example_notebook_emulation", emu), ("example_value_preserving", pres)):
        r = run_pair(torch, proc, model, pipe, eos_ids, Image.fromarray(a), prompt_ex, tag)
        pb = [b for b in r["parsed_runner"]["boxes"] if b]
        overlay.draw(f"{OUT}/example_{'notebook_emulation' if 'emulation' in tag else 'value_preserving'}.png", [], pb, 640, tag) \
            .save(f"{OUT}/overlay_{tag}.png")
        recs.append(r)
    # RSNA development 1건 (같은 입력 경로): pipeline vs runner
    it = [json.loads(ln) for ln in open("results/iter_009/manifests/infer_manifest.jsonl")]
    dev_it = [i for i in it if i["id"] == "dev_00000766"][0]
    img, aff2, px = G.load_image(dev_it["image"])
    allp = P.all_prompts()
    recs.append(run_pair(torch, proc, model, pipe, eos_ids, img, allp["concise"], "rsna_dev_dev_00000766_concise"))
    recs.append(run_pair(torch, proc, model, pipe, eos_ids, img, allp["official_long"], "rsna_dev_dev_00000766_official_long"))
    json.dump({"env": env, "input_diff": input_diff, "runs": recs, "ts": time.time()}, open(f"{OUT}/sanity.json", "w"), indent=1, default=str)
    for r in recs:
        print(r["tag"], "n_new", r["runner_n_new"], "eos", r["runner_ended_eos"], "text_equal", r["text_equal_after_strip_or_substring"],
              r["pipeline_vs_runner_inputs"], r["parsed_runner"]["status"], r["parsed_runner"]["boxes"])
    print(json.dumps(input_diff, indent=1))


if __name__ == "__main__":
    main()
