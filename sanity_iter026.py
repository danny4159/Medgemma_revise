"""iter_026 GPU 실행 전 sanity: (1) 독립 경로(tokenizer.apply_chat_template + processor.__call__)로 구성한 tensor를
generate.build_inputs와 대조 (2) B0 adapter digest 확인 (3) V/O/RD 8건 재생성 결정성 sanity (D 생성 후 실행).
사용: python sanity_iter026.py pre   (D 생성 전: tensor/adapter만)
     python sanity_iter026.py post  (D 생성 후: 8건 재생성 대조 추가)
"""
import glob
import json
import os
import sys

from rsna_diag import generate as G, roi23_data as D, roi23_spec as R, roi26_spec as R26, roi26_requests as Q

out = {"checks": []}


def add(name, ok, detail=None):
    out["checks"].append({"name": name, "pass": bool(ok), "detail": detail})
    print(("PASS" if ok else "FAIL"), name)


mode = sys.argv[1] if len(sys.argv) > 1 else "pre"

items, gts = D.load_val_pool()
d24, counts = D.select_d24(items, gts)

torch, proc, model = G.load_model()
env = G.env_info(torch, proc, model)
eos_ids = set(env["eos_token_id"] if isinstance(env["eos_token_id"], list) else [env["eos_token_id"]])

pid = d24[0]
img, aff, px = G.load_image(items[pid]["image"])
prompt = R26.v_prompt("TL")

inp_a = G.build_inputs(proc, img, prompt)

msgs = [{"role": "user", "content": [{"type": "image", "image": img}, {"type": "text", "text": prompt}]}]
text_b = proc.tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
inp_b = proc(text=text_b, images=[img], return_tensors="pt", add_special_tokens=False)

keys_common = sorted(set(inp_a.keys()) & set(inp_b.keys()))
add("independent_tensor_keys_overlap_nonempty", len(keys_common) > 0, keys_common)
for k in keys_common:
    same_shape = tuple(inp_a[k].shape) == tuple(inp_b[k].shape)
    same_val = same_shape and bool((inp_a[k] == inp_b[k]).all())
    add(f"independent_tensor_match_{k}", same_val,
        {"shape_a": list(inp_a[k].shape), "shape_b": list(inp_b[k].shape)})

if mode == "post":
    rows = []
    for name in ("D_V__M0", "D_V__B0", "D_O__M0", "D_O__B0"):
        rs = Q.load_rows(f"results/iter_026/requests/{name}.jsonl")
        rows += rs
    rows.sort(key=lambda r: (r["checkpoint"], r["request_id"]))
    m0_rows = [r for r in rows if r["checkpoint"] == "M0"][:4]
    b0_rows = [r for r in rows if r["checkpoint"] == "B0"][:4]
    stored = {}
    for name in ("D_V__M0", "D_V__B0", "D_O__M0", "D_O__B0"):
        for f in sorted(glob.glob(f"results/iter_026/gen/{name}/gen_worker*.jsonl")):
            for ln in open(f):
                if ln.strip():
                    r = json.loads(ln)
                    stored[r["request_id"]] = r

    def regen_and_check(rows_):
        for row in rows_:
            rec = G.run_request(torch, proc, model, eos_ids, {"id": row["id"], "image": row["image"],
                                                               "file_sha256": row["file_sha256"]},
                                 row["condition"], row["prompt"])
            old = stored.get(row["request_id"])
            if old is None:
                add(f"regen_{row['request_id']}_has_stored", False, row["request_id"])
                continue
            match = rec["suffix_ids"] == old["suffix_ids"] and rec["ended_eos"] == old["ended_eos"]
            add(f"regen_{row['request_id']}_matches_stored", match,
                {"ckpt": row["checkpoint"], "cond": row["condition"], "target": row["target"],
                 "new_ended_eos": rec["ended_eos"], "old_ended_eos": old["ended_eos"],
                 "new_n_out": rec["n_output_tokens"], "old_n_out": old["n_output_tokens"]})

    # M0 probes first, on the clean (no-adapter) model, before any adapter is ever loaded.
    regen_and_check(m0_rows)
    adg = G.load_adapter(torch, model, "results/iter_012/train/lr2e-4_s17/epoch_05")
    add("B0_adapter_digest_matches_pinned", adg == "e13f3c4461b826a060c90dfe4e4ee4c2ebac36a08f84be1a45a37495816cec11", adg)
    regen_and_check(b0_rows)
else:
    adg = G.load_adapter(torch, model, "results/iter_012/train/lr2e-4_s17/epoch_05")
    add("B0_adapter_digest_matches_pinned", adg == "e13f3c4461b826a060c90dfe4e4ee4c2ebac36a08f84be1a45a37495816cec11", adg)

os.makedirs("results/iter_026/sanity", exist_ok=True)
out["n"] = len(out["checks"])
out["n_pass"] = sum(1 for c in out["checks"] if c["pass"])
json.dump(out, open(f"results/iter_026/sanity/sanity_{mode}.json", "w"), indent=1, default=str)
print(f"{out['n_pass']}/{out['n']} passed")
