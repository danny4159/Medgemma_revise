"""iter_100 생성 경로 검사: (1) 재개/worker 수가 다른 실행 간 token 정합성, (2) 래퍼(LoRA 장착, 항등 초기화)와 공식 무패치 모델의 greedy 출력 비교.

(2)는 GPU 하나를 쓴다. 공식 경로는 processor.apply_chat_template + model.generate(do_sample=False, use_cache 기본값).
bf16 kernel/cache 경로 차이로 token이 갈릴 수 있으며, 갈리면 첫 차이 위치를 그대로 기록한다(성공으로 바꾸지 않는다).
"""
import json
import os
import sys
from pathlib import Path

from report86_common import read_jsonl_complete, save, sha

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results" / "iter_100"


def recs(d, w):
    r = []
    for s in range(w):
        r += read_jsonl_complete(OUT / "gen" / d / f"worker_{s}.jsonl")
    return dict((x["id"], x) for x in r)


def first_diff(a, b):
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    return None if len(a) == len(b) else min(len(a), len(b))


def main():
    base, res = recs("D8_w2", 2), recs("D8_resume", 2)
    cmp1 = dict((k, dict(input_ids_equal=res[k]["input_ids"] == base[k]["input_ids"],
                         tokens_equal=[a["suffix_ids"] for a in res[k]["attempts"]] == [a["suffix_ids"] for a in base[k]["attempts"]],
                         text_equal=res[k]["text"] == base[k]["text"])) for k in res)
    out = dict(resume_vs_w2=dict(n=len(cmp1), all_equal=all(all(v.values()) for v in cmp1.values()), detail=cmp1))
    # (2) 공식 무패치 모델 대조
    os.environ["CUDA_VISIBLE_DEVICES"] = sys.argv[1]
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor
    from report86_common import base_path
    from rsna_diag import generate as G
    proc = AutoProcessor.from_pretrained(base_path("M15"), local_files_only=True)
    proc.image_processor.do_pan_and_scan = False
    model = AutoModelForImageTextToText.from_pretrained(base_path("M15"), local_files_only=True, dtype=torch.bfloat16,
                                                        device_map={"": 0}, attn_implementation="sdpa").eval()
    reqs = dict((r["id"], r) for r in json.loads((OUT / "data" / "D8" / "requests.json").read_text()))
    pick = [k for k in sorted(base) if k.endswith("|N")][:2] + [k for k in sorted(base) if k.endswith("|T")][:1]
    eos = model.generation_config.eos_token_id
    eos = [eos] if isinstance(eos, int) else eos
    off = {}
    for k in pick:
        image, _, _ = G.load_image(reqs[k]["image"])
        inp = proc.apply_chat_template([dict(role="user", content=[dict(type="image", image=image), dict(type="text", text=reqs[k]["prompt"])])],
                                       add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors="pt", padding=True).to("cuda:0")
        inp["pixel_values"] = inp["pixel_values"].to(torch.bfloat16)
        ref = base[k]["attempts"][0]["suffix_ids"]
        with torch.no_grad():
            g = model.generate(**inp, max_new_tokens=len(ref), do_sample=False)
        toks = g[0, inp["input_ids"].shape[1]:].tolist()
        off[k] = dict(wrapper_len=len(ref), official_len=len(toks), input_ids_equal=inp["input_ids"][0].tolist() == base[k]["input_ids"],
                      first_diff=first_diff(toks, ref), tokens_equal=toks == ref[:len(toks)] and len(toks) <= len(ref))
    out["official_vs_wrapper"] = off
    out["note"] = "공식 경로는 generate 기본 use_cache. 첫 차이는 bf16 kernel/cache 경로 차이일 수 있어 원인을 단정하지 않는다."
    save(OUT / "tech" / "gencheck.json", out)
    print(json.dumps(dict(resume_equal=out["resume_vs_w2"]["all_equal"], official=dict((k[-8:], (v["input_ids_equal"], v["first_diff"])) for k, v in off.items()))))


if __name__ == "__main__":
    main()
