"""iter_025 D768 실행 전 GPU sanity: (1) M0/B0 concise bbox 재생성 대 iter_024 D24_bbox 저장 record 토큰 대조
(환경/adapter 로딩이 이전과 동일하게 동작하는지), (2) text-only 입력 구성에 pixel_values가 없음을 실제 모델/processor로 확인.
사용: python sanity_iter025.py -> results/iter_025/sanity/sanity.json
"""
import glob
import json
import os

os.environ.setdefault("ROI25_RUN_ROOT", "results/iter_025")

from rsna_diag import generate as G, roi23_data as D, roi23_spec as R, prompts as P  # noqa: E402

out = {"checks": []}


def add(name, ok, detail=None):
    out["checks"].append({"name": name, "pass": bool(ok), "detail": detail})
    print(("PASS" if ok else "FAIL"), name)


items, gts = D.load_val_pool()
opac = sorted([i for i, g in gts.items() if g["category"] == "opacity"])
prim, _ = D.opacity_with_margin(gts, opac)
layers = {t: [] for t in R.TARGETS}
for i in prim:
    q = R.largest_box_quadrant(gts[i]["boxes"])
    layers[q].append(i)
for q in layers:
    layers[q].sort(key=lambda i: R.d24_order_key(i))
probe_ids = [layers[q][0] for q in R.TARGETS]
print("probe patients (one per quadrant, D24 order):", probe_ids)

old_recs = {}
for ck in ("M0", "B0"):
    for f in sorted(glob.glob(f"results/iter_024/gen/D24_bbox__{ck}/gen_worker*.jsonl")):
        for ln in open(f):
            if ln.strip():
                r = json.loads(ln)
                if r.get("prompt_name") == "bbox_concise":
                    old_recs[(ck, r["id"])] = r

torch, proc, model = G.load_model()
eos = G.env_info(torch, proc, model)["eos_token_id"]
eos_ids = set(eos if isinstance(eos, list) else [eos])

# tensor sanity: text-only chat has no pixel_values, image chat does
img, aff, px = G.load_image(items[probe_ids[0]]["image"])
inp_img = G.build_inputs(proc, img, P.CONCISE)
inp_txt = G.build_inputs_text(proc, "This is a text-only sanity prompt.")
add("image_chat_has_pixel_values", "pixel_values" in inp_img, list(inp_img.keys()))
add("text_only_chat_has_no_pixel_values", "pixel_values" not in inp_txt, list(inp_txt.keys()))
decoded = proc.tokenizer.decode(inp_txt["input_ids"][0].tolist())
add("text_only_input_ids_decode_contains_prompt_text", "text-only sanity prompt" in decoded, decoded[-200:])

for ck in ("M0", "B0"):
    adapter_dir = None if ck == "M0" else "results/iter_012/train/lr2e-4_s17/epoch_05"
    if adapter_dir:
        adg = G.load_adapter(torch, model, adapter_dir)
        add(f"{ck}_adapter_digest_matches_pinned",
            adg == "e13f3c4461b826a060c90dfe4e4ee4c2ebac36a08f84be1a45a37495816cec11", adg)
    for pid in probe_ids:
        rec = G.run_request(torch, proc, model, eos_ids, items[pid], "concise_sanity", P.CONCISE)
        old = old_recs.get((ck, pid))
        if old is None:
            add(f"{ck}_{pid}_has_old_record", False, "no iter_024 D24_bbox record found")
            continue
        match = rec["suffix_ids"] == old["suffix_ids"] and rec["ended_eos"] == old["ended_eos"]
        add(f"{ck}_{pid}_greedy_tokens_match_iter024", match,
            {"new_ended_eos": rec["ended_eos"], "old_ended_eos": old["ended_eos"],
             "new_n_out": rec["n_output_tokens"], "old_n_out": old["n_output_tokens"],
             "new_text": rec["suffix_text_raw"][:200], "old_text": old["suffix_text_raw"][:200]})

os.makedirs("results/iter_025/sanity", exist_ok=True)
out["n"] = len(out["checks"])
out["n_pass"] = sum(1 for c in out["checks"] if c["pass"])
json.dump(out, open("results/iter_025/sanity/sanity.json", "w"), indent=1, default=str)
print(f"{out['n_pass']}/{out['n']} passed")
