"""iter_027 GPU sanity: 공식 tensor 구성 완전 검증 (key set·shape·dtype·값) + V/RD 조건 포함 + B0 adapter + 재생성 대조.
iter_026 sanity_iter026.py는 tensor key 교집합만 확인했고(공통 key만) V_TL 프롬프트 1건만 검사했다. 이번은
key 전체 집합 일치·dtype까지 확인하고 실제 E200에서 쓰는 RD(reader) 조건도 포함한다. 실패 시 비정상 종료(exit 1)한다.
사용: python sanity_iter027.py"""
import glob
import json
import os
import sys

from rsna_diag import generate as G, roi23_data as D, roi26_data as D26, roi26_requests as Q, roi26_spec as R26

out = {"checks": []}
failed = False


def add(name, ok, detail=None):
    global failed
    out["checks"].append({"name": name, "pass": bool(ok), "detail": detail})
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        failed = True


items, gts = D.load_val_pool()
d24, counts = D.select_d24(items, gts)
pid = d24[0]
img, aff, px = G.load_image(items[pid]["image"])

torch, proc, model = G.load_model()
env = G.env_info(torch, proc, model)
eos_ids = set(env["eos_token_id"] if isinstance(env["eos_token_id"], list) else [env["eos_token_id"]])


def independent_build(prompt):
    msgs = [{"role": "user", "content": [{"type": "image", "image": img}, {"type": "text", "text": prompt}]}]
    text_b = proc.tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    return proc(text=text_b, images=[img], return_tensors="pt", add_special_tokens=False)


def full_tensor_check(tag, prompt):
    inp_a = G.build_inputs(proc, img, prompt)  # official: proc.apply_chat_template(...)
    inp_b = independent_build(prompt)  # 독립 재구성: tokenizer.apply_chat_template(tokenize=False) + proc(...)
    keys_a, keys_b = set(inp_a.keys()), set(inp_b.keys())
    add(f"{tag}_key_set_equal", keys_a == keys_b, {"a": sorted(keys_a), "b": sorted(keys_b)})
    for k in sorted(keys_a & keys_b):
        same_shape = tuple(inp_a[k].shape) == tuple(inp_b[k].shape)
        same_dtype = inp_a[k].dtype == inp_b[k].dtype
        same_val = same_shape and same_dtype and bool((inp_a[k] == inp_b[k]).all())
        add(f"{tag}_tensor_match_{k}", same_shape and same_dtype and same_val,
            {"shape_a": list(inp_a[k].shape), "shape_b": list(inp_b[k].shape),
             "dtype_a": str(inp_a[k].dtype), "dtype_b": str(inp_b[k].dtype)})


# V(direct) 조건: 실제 E200_extra V_M0/V_B0가 쓰는 prompt 경로
full_tensor_check("V_TL", R26.v_prompt("TL"))

# RD(reader) 조건: 실제 E200_extra RD_M0가 쓰는 prompt 경로 (proposal 목록 포함, 더 긴 prompt)
sample_boxes_i = [[100, 100, 200, 200], [700, 700, 800, 800]]
full_tensor_check("RD_TL", R26.rd_prompt("TL", sample_boxes_i))

# 기존 D 전체 bbox 출력에서 hash로 고른 M0/B0 각 4건 재현 sanity (이미 완료된 검사이나, 이번 코드 변경 이후 재확인)
# 주의(iter_026 sanity_iter026.py의 규약을 그대로 따른다): M0 probe는 adapter를 아직 로드하지 않은 "clean" 모델에서
# 먼저 실행해야 한다. adapter를 먼저 로드하면 M0(무적응) 재현이 실패한다.
rows = []
for name in ("D_V__M0", "D_V__B0", "D_O__M0", "D_O__B0"):
    rows += Q.load_rows(f"results/iter_026/requests/{name}.jsonl")
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
            {"ckpt": row["checkpoint"], "cond": row["condition"], "target": row["target"]})


regen_and_check(m0_rows)  # adapter 로드 전, clean base model에서 먼저 실행
adg = G.load_adapter(torch, model, "results/iter_012/train/lr2e-4_s17/epoch_05")
add("B0_adapter_digest_matches_pinned", adg == "e13f3c4461b826a060c90dfe4e4ee4c2ebac36a08f84be1a45a37495816cec11", adg)
regen_and_check(b0_rows)

os.makedirs("results/iter_027/sanity", exist_ok=True)
out["n"] = len(out["checks"])
out["n_pass"] = sum(1 for c in out["checks"] if c["pass"])
json.dump(out, open("results/iter_027/sanity/sanity.json", "w"), indent=1, default=str)
print(f"{out['n_pass']}/{out['n']} passed")
if failed:
    sys.exit(1)
