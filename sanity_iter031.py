"""iter_031 sanity: D24 실제 입력에서 공식 chat_template 구성과 risk30/generate wrapper의 전체
tensor key/shape/dtype/value를 대조한다 (공통 key만 비교하지 않는다). adapter 활성/비활성(M0) 각각에서
seed17 원래 suffix가 output_scores=True 경로에서도 재현되는지, 그리고 M0(adapter 비활성)에서는
같은 입력이라도 다른 텍스트가 나올 수 있음(=adapter가 실제로 로드/적용됨)을 확인한다.

GPU 필요. 결과: results/iter_031/sanity/sanity.json
"""
import json
import os
import sys

os.environ.setdefault("HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
if len(sys.argv) > 1:
    os.environ["CUDA_VISIBLE_DEVICES"] = sys.argv[1]

import torch
import transformers

from rsna_diag import generate as G
from rsna_diag import risk30 as R30
from rsna_diag import risk30_source as RS

OUT = "results/iter_031/sanity/sanity.json"


def official_build_inputs(proc, image, prompt):
    """official notebook과 동일한 chat 구성(apply_chat_template)을 wrapper 없이 직접 호출한다."""
    msgs = [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": prompt}]}]
    return proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True, return_dict=True,
                                    return_tensors="pt")


def tensors_equal(report, name, a, b):
    ok_keys = set(a.keys()) == set(b.keys())
    report[f"{name}_same_keys"] = ok_keys
    report[f"{name}_keys_a"] = sorted(a.keys())
    report[f"{name}_keys_b"] = sorted(b.keys())
    per_key = {}
    for k in sorted(set(a.keys()) | set(b.keys())):
        if k not in a or k not in b:
            per_key[k] = "missing_in_one_side"
            continue
        va, vb = a[k], b[k]
        same_shape = tuple(va.shape) == tuple(vb.shape)
        same_dtype = va.dtype == vb.dtype
        same_value = bool(torch.equal(va, vb)) if same_shape and same_dtype else False
        per_key[k] = {"same_shape": same_shape, "same_dtype": same_dtype, "same_value": same_value,
                      "shape_a": list(va.shape), "shape_b": list(vb.shape), "dtype_a": str(va.dtype), "dtype_b": str(vb.dtype)}
    report[f"{name}_per_key"] = per_key
    report[f"{name}_all_equal"] = ok_keys and all(
        (isinstance(v, dict) and v["same_shape"] and v["same_dtype"] and v["same_value"]) for v in per_key.values())
    return report[f"{name}_all_equal"]


def main():
    sm = json.load(open("results/iter_030/source_manifest.json"))
    d24 = RS.select_d24(sm)
    items = d24["one_box"][:3] + d24["two_box"][:3]

    torch.manual_seed(0)
    proc = transformers.AutoProcessor.from_pretrained(G.MODEL_ID, revision=G.MODEL_REVISION)
    model = transformers.AutoModelForImageTextToText.from_pretrained(
        G.MODEL_ID, revision=G.MODEL_REVISION, dtype=torch.bfloat16, device_map="cuda")
    model.eval()

    from rsna_diag import prompts as P

    report = {"n_checked": 0, "cases": []}
    for it in items:
        image, aff, px_hash = G.load_image(it["image"])
        assert px_hash == it["expected_pixel_sha256"], f"pixel hash changed for {it['id']}"
        official = official_build_inputs(proc, image, P.CONCISE)
        wrapper = G.build_inputs(proc, image, P.CONCISE)
        case = {"id": it["id"]}
        case["tensors_identical"] = tensors_equal(case, "tensors", official, wrapper)
        report["cases"].append(case)
        report["n_checked"] += 1
    report["all_tensors_identical"] = all(c["tensors_identical"] for c in report["cases"])

    # adapter 활성/비활성에서 실제로 다른 응답이 나오는지 (adapter가 로드/적용됨을 확인)
    adapter_digest = G.load_adapter(torch, model, "results/iter_012/train/lr2e-4_s17/epoch_05")
    report["adapter_digest"] = adapter_digest
    report["adapter_digest_matches_manifest"] = adapter_digest == sm["adapter_digest_seed17"]

    env = G.env_info(torch, proc, model)
    eos_ids = set(env["eos_token_id"] if isinstance(env["eos_token_id"], list) else [env["eos_token_id"]])

    m0_diff_from_seed17 = []
    for it in items[:2]:
        image, aff, px_hash = G.load_image(it["image"])
        inp = G.build_inputs(proc, image, P.CONCISE)
        x = {k: (v.to("cuda", dtype=torch.bfloat16) if k == "pixel_values" else v.to("cuda")) for k, v in inp.items()}
        with torch.no_grad():
            out = model.generate(**x, max_new_tokens=min(len(it["seed17_suffix_ids"]) + 4, 1000), do_sample=False)
        n_in = x["input_ids"].shape[1]
        seq = out[0, n_in:].tolist()
        m0_diff_from_seed17.append({"id": it["id"], "adapter_enabled_suffix_matches_seed17": seq == it["seed17_suffix_ids"]})
    report["adapter_enabled_reproduces_seed17"] = m0_diff_from_seed17
    report["all_adapter_enabled_reproduce"] = all(r["adapter_enabled_suffix_matches_seed17"] for r in m0_diff_from_seed17)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(report, open(OUT, "w"), indent=1)
    print(json.dumps({k: v for k, v in report.items() if k not in ("cases",)}, indent=1))
    print("all_tensors_identical:", report["all_tensors_identical"])
    print("all_adapter_enabled_reproduce:", report["all_adapter_enabled_reproduce"])


if __name__ == "__main__":
    main()
