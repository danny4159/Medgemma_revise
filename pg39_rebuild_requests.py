"""iter_039: D 형식 수정(long_v2) 후 요청 파일을 manifest에서 다시 만든다 (영상 재추출 없음, 기존 v1 파일은 보존).
python pg39_rebuild_requests.py  -> results/iter_039/requests_v2/requests_{D,E96,E192,F}.jsonl (존재하면 거부)
"""
import json
import os
import sys

import pg39_data as D
import pg39_run as R
import pg39_spec as S
from rsna_diag import generate as G

OUT = "results/iter_039/requests_v2"
if os.path.exists(OUT) and os.listdir(OUT):
    sys.exit("requests_v2 exists")
os.makedirs(OUT, exist_ok=True)
man = [json.loads(l) for l in open("results/iter_039/data/manifest_private.jsonl")]
old = {}
for k in ("D", "E96", "E192", "F"):
    for l in open(f"results/iter_039/requests/requests_{k}.jsonl"):
        r = json.loads(l)
        old[(r["patient"], r["cond"], tuple(r["targets"]))] = r
pix = {}
rows_by = {k: [] for k in ("D", "E96", "E192", "F")}
n_same = n_changed = 0
for r in man:
    meta = r["image_meta"]
    if meta["path"] not in pix:
        pix[meta["path"]] = (R.file_sha(meta["path"]), G.load_image(meta["path"])[2])
    fsha, psx = pix[meta["path"]]
    for cond, targets, prompt, caps in S.build_prompts(r["sentences"]):
        psha = S.sha(prompt)
        o = old[(r["PatientID"], cond, tuple(targets))]
        assert o["input_pixel_sha256"] == psx and o["image_file_sha256"] == fsha
        n_same += o["prompt_sha256"] == psha
        n_changed += o["prompt_sha256"] != psha
        rid = S.request_id(r["subset"], r["PatientID"], cond, targets, psha, meta["u8_pixel_sha256"])
        rows_by[r["subset"]].append({
            "request_id": rid, "kind": r["subset"], "patient": r["PatientID"], "image_id": r["ImageID"], "cond": cond,
            "targets": targets, "prompt": prompt, "prompt_sha256": psha, "caps": caps, "image": meta["path"],
            "image_file_sha256": fsha, "input_pixel_sha256": psx,
            "order_key": D.h(D.SEED, "order", r["PatientID"], cond, ",".join(targets))})
for k, rows in rows_by.items():
    rows.sort(key=lambda x: x["order_key"])
    with open(f"{OUT}/requests_{k}.jsonl", "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
print({k: len(v) for k, v in rows_by.items()}, "prompt unchanged", n_same, "changed", n_changed)
json.dump({"unchanged": n_same, "changed": n_changed,
           "sha256": {k: D.sha256_file(f"{OUT}/requests_{k}.jsonl") for k in rows_by}}, open(f"{OUT}/summary.json", "w"), indent=1)
