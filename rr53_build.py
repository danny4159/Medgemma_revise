"""iter_053 요청 생성 (CPU only). manifest_{D,E,F}.json(rr53_data.py build)에서 요청 파일을 만든다. 기존 파일 덮어쓰기 금지.

python rr53_build.py requests D|E|F
D: CheXpert D16 본조건 16/patient(R1×4, R2×4, T×4[R2 byte-identical·영상 없음], BJ, BT[BJ byte-identical·영상 없음], BI×2) = 256
   + CheXpert D16 oracle O2 image/text × 4 draft = 128 + PadChest D8 oracle O2 image/text × 4 draft = 64  (총 448)
E/F: 본조건만 16/patient (E 768, F 1680). 정답/오류 여부는 prompt·ID에 넣지 않는다 (oracle만 verified status를 prompt로 받는다).
"""
import json
import os
import sys
from collections import Counter

import rr53_spec as S
from rr53_data import OUT, file_sha, write_new
from rsna_diag import generate as G


def _px(cache, path):
    if path not in cache:
        cache[path] = G.load_image(path)[2]
    return cache[path]


def make_requests(rows, set_name, oracle, cache):
    """rows: manifest rows (q, image_meta). returns request rows."""
    reqs = []
    for m in rows:
        q = m["q"]
        fp = {i: q[i]["finding"] for i in S.IDS}
        img = m["image_meta"]["path"]
        fsha = m["image_meta"]["file_sha256"]
        px = _px(cache, img)
        base = dict(kind="rr53", patient=m["PatientID"], caps=S.CAPS, donor_patient=None, set=set_name)

        def add(cond, targets, prompt, modality, draft=None):
            psha = S.sha(prompt)
            rid = S.request_id("rr53", m["PatientID"], cond, targets, psha, px if modality == "image" else "text")
            reqs.append(dict(base, request_id=rid, cond=cond, targets=list(targets), prompt=prompt, prompt_sha256=psha, modality=modality, draft=draft,
                             image=img if modality == "image" else None, image_file_sha256=fsha if modality == "image" else None,
                             input_pixel_sha256=px if modality == "image" else None, order_key=S.sha(f"{S.SEED}|{rid}")[:16]))

        if oracle != "only":
            for code in S.DRAFT_CODES:
                items = S.draft_text(fp, code)
                add(f"R1_d{code}", S.IDS, S.prompt_R1(items), "image", code)
                add(f"R2_d{code}", S.IDS, S.prompt_R2(items), "image", code)
                add(f"T_d{code}", S.IDS, S.prompt_T(items), "text", code)
            add("BJ", S.IDS, S.prompt_BJ(fp), "image")
            add("BT", S.IDS, S.prompt_BT(fp), "text")
            for i in S.IDS:
                add(f"BI_{i}", [i], S.prompt_BI(fp[i], i), "image")
        if oracle in ("with", "only"):
            truth = [(i, q[i]["state"]) for i in S.IDS]
            for code in S.DRAFT_CODES:
                p = S.prompt_O2(S.draft_text(fp, code), truth)
                add(f"O_d{code}", S.IDS, p, "image", code)
                add(f"OT_d{code}", S.IDS, p, "text", code)
    return reqs


def build(stage):
    man = json.load(open(f"{OUT}/data/manifest_{stage}.json"))
    cache = {}
    if stage == "D":
        reqs = make_requests(man["rows"], "D", "with", cache)
        reqs += make_requests(man["pc_oracle_rows"], "pc_D8", "only", cache)
    else:
        reqs = make_requests(man["rows"], stage, "none", cache)
    ids = [r["request_id"] for r in reqs]
    assert len(ids) == len(set(ids))
    path = f"{OUT}/requests/requests_{stage}.jsonl"
    write_new(path, "".join(json.dumps(r, sort_keys=True) + "\n" for r in reqs))
    print(stage, len(reqs), dict(Counter(r["modality"] for r in reqs)), dict(Counter(r["cond"].split("_")[0] for r in reqs)))


if __name__ == "__main__":
    assert sys.argv[1] == "requests"
    build(sys.argv[2])
