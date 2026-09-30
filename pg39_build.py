"""iter_039 표본 선택 + 영상 추출/변환 + 요청 manifest 생성. 결과: results/iter_039/{data,requests}/ (Git 제외, private).

영상 규약(사전 고정, 모델 출력 전): PadChest-GR 영상은 16-bit PNG(I;16). 공식 notebook의 첫 변환은 skimage.util.img_as_ubyte이며
uint16->uint8은 우측 8-bit shift(v>>8)다. 그 규약을 그대로 쓴다(per-image min-max/contrast 조정 없음, flip/반전 없음).
변환 후 8-bit L PNG로 저장하고 rsna_diag.generate.load_image(값 보존 RGB 복제 + 중앙 square padding)를 그대로 통과시킨다.
"""
import hashlib
import io
import json
import os
import sys

import numpy as np
from PIL import Image

import pg39_data as D
import pg39_spec as S
from rsna_diag import generate as G
from rsna_diag import geometry

OUT = "results/iter_039"
CONVENTION = "uint16 -> uint8 by right shift 8 (skimage.util.img_as_ubyte equivalent); no window/min-max/flip"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def extract(z, idx, iid, img_dir):
    """zip member -> 원본 16-bit 배열 hash + 8-bit PNG 저장. returns meta dict."""
    zi = idx[iid]
    raw = z.read(zi)
    a = np.asarray(Image.open(io.BytesIO(raw)))
    if a.dtype != np.uint16 or a.ndim != 2:
        raise D.InputError(f"{iid}: unexpected image dtype/shape {a.dtype} {a.shape}")
    b = (a >> 8).astype(np.uint8)
    path = os.path.join(img_dir, iid)
    if not os.path.exists(path):
        tmp = path + f".{os.getpid()}.tmp.png"
        Image.fromarray(b).save(tmp)
        os.replace(tmp, path)
    h, w = a.shape
    return {"path": path, "zip_member": zi.filename, "zip_crc": zi.CRC, "raw_png_sha256": sha(raw),
            "u16_pixel_sha256": sha(a.tobytes()), "u8_pixel_sha256": sha(b.tobytes()), "h": int(h), "w": int(w),
            "u16_min": int(a.min()), "u16_max": int(a.max())}


def main():
    if os.path.exists(f"{OUT}/data/selection_lock.json"):
        sys.exit("selection_lock.json exists: refuse to rebuild (new attempt path required)")
    reports, m, links = D.load_inputs()
    rep_by_img = {r["ImageID"]: r for r in reports}
    z = D.open_image_zip()
    idx = D.zip_index(z)
    img_dir = f"{OUT}/data/images"
    os.makedirs(img_dir, exist_ok=True)
    pools, excl = {}, {}
    for sp in ("train", "validation"):
        pools[sp], excl[sp] = D.image_pool(reports, links, sp)
    missing_zip = {sp: [c["ImageID"] for c in pools[sp] if c["ImageID"] not in idx] for sp in pools}
    for sp in pools:
        pools[sp] = [c for c in pools[sp] if c["ImageID"] in idx]
    metas = {}
    banned = {"train": set(), "validation": set()}
    seen_pix = {}
    for it in range(50):  # 중복 pixel hash 제거 후 재선택(결정적)
        seltr = D.select(pools["train"], "train", [("D", 24), ("E", 288)], banned["train"])
        selva = D.select(pools["validation"], "validation", [("F", 120)], banned["validation"])
        order = [("D", seltr["D"]["chosen"]), ("E", seltr["E"]["chosen"]), ("F", selva["F"]["chosen"])]
        seen_pix = {}
        dup_found = False
        for name, chosen in order:
            for c in chosen:
                iid = c["ImageID"]
                if iid not in metas:
                    metas[iid] = extract(z, idx, iid, img_dir)
                key = metas[iid]["u16_pixel_sha256"]
                if key in seen_pix and seen_pix[key] != c["PatientID"]:
                    banned["train" if name != "F" else "validation"].add(c["PatientID"])
                    dup_found = True
                seen_pix[key] = seen_pix.get(key, c["PatientID"])
        if not dup_found:
            break
    else:
        sys.exit("could not resolve duplicate pixel hashes")
    # E96: 층별 E288 순서의 처음 min(q96,q288)
    e_chosen = seltr["E"]["chosen"]
    byst = {}
    for c in e_chosen:
        byst.setdefault(D.stratum(c), []).append(c)
    sizes = {k: len(v) for k, v in byst.items()}
    q96 = D.apportion(sizes, 96)
    e96_ids = {c["PatientID"] for k, v in byst.items() for c in v[:q96[k]]}
    manifest = []
    for name, chosen in order:
        for c in chosen:
            r = rep_by_img[c["ImageID"]]
            ids = D.assign_ids(c["ImageID"], c["i"], c["j"])
            meta = metas[c["ImageID"]]
            fs = {k: r["findings"][v] for k, v in ids.items()}
            top, left, side = geometry.pad_offsets(meta["h"], meta["w"])
            sub = name if name != "E" else ("E96" if c["PatientID"] in e96_ids else "E192")
            manifest.append({"set": name, "subset": sub, "split": c["split"], "PatientID": c["PatientID"],
                             "ImageID": c["ImageID"], "StudyID": c["StudyID"], "stratum": D.stratum(c), "image_meta": meta,
                             "pad_top_left_side": [top, left, side], "finding_index": ids,
                             "sentences": {k: f["sentence_en"] for k, f in fs.items()},
                             "gt_boxes_xyxy_norm": {k: f["boxes"] for k, f in fs.items()},
                             "extra_boxes_xyxy_norm": {k: f["extra_boxes"] for k, f in fs.items()},
                             "labels": {k: f["labels"] for k, f in fs.items()},
                             "locations": {k: f["locations"] for k, f in fs.items()}})
    os.makedirs(f"{OUT}/requests", exist_ok=True)
    mp = f"{OUT}/data/manifest_private.jsonl"
    with open(mp, "w") as f:
        for r in manifest:
            f.write(json.dumps(r) + "\n")
    # 요청 파일 (GT 미포함)
    rows_by = {"D": [], "E96": [], "E192": [], "F": []}
    for r in manifest:
        meta = r["image_meta"]
        for cond, targets, prompt, caps in S.build_prompts(r["sentences"]):
            psha = S.sha(prompt)
            rid = S.request_id(r["subset"], r["PatientID"], cond, targets, psha, meta["u8_pixel_sha256"])
            rows_by[r["subset"]].append({
                "request_id": rid, "kind": r["subset"], "patient": r["PatientID"], "image_id": r["ImageID"],
                "cond": cond, "targets": targets, "prompt": prompt, "prompt_sha256": psha, "caps": caps,
                "image": meta["path"], "image_file_sha256": sha(open(meta["path"], "rb").read()),
                "input_pixel_sha256": G.load_image(meta["path"])[2],
                "order_key": D.h(D.SEED, "order", r["PatientID"], cond, ",".join(targets))})
    for k, rows in rows_by.items():
        rows.sort(key=lambda x: x["order_key"])
        with open(f"{OUT}/requests/requests_{k}.jsonl", "w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
    summ = {"spec": D.SPEC, "convention": CONVENTION, "raw_inputs_sha256": links["inputs_sha256"],
            "exclusion_counts": excl, "missing_in_zip": {k: len(v) for k, v in missing_zip.items()},
            "sizes": {k: sum(1 for r in manifest if r["set"] == k) for k in ("D", "E", "F")},
            "subset_sizes": {k: sum(1 for r in manifest if r["subset"] == k) for k in ("D", "E96", "E192", "F")},
            "strata": {k: {s: sum(1 for r in manifest if r["set"] == k and r["stratum"] == s)
                           for s in sorted({r["stratum"] for r in manifest})} for k in ("D", "E", "F")},
            "pool_sizes": {k: len(v) for k, v in pools.items()}, "pixel_dup_banned": {k: len(v) for k, v in banned.items()},
            "n_requests": {k: len(v) for k, v in rows_by.items()}, "manifest_sha256": D.sha256_file(mp),
            "request_files_sha256": {k: D.sha256_file(f"{OUT}/requests/requests_{k}.jsonl") for k in rows_by},
            "e96_in_e288_quota_q96": q96, "select_quota_E": seltr["E"]["quota"], "select_quota_F": selva["F"]["quota"]}
    json.dump(summ, open(f"{OUT}/data/selection_summary.json", "w"), indent=1)
    json.dump({"manifest_sha256": summ["manifest_sha256"], "request_files_sha256": summ["request_files_sha256"]},
              open(f"{OUT}/data/selection_lock.json", "w"), indent=1)
    print(json.dumps({k: summ[k] for k in ("sizes", "subset_sizes", "n_requests", "strata", "pixel_dup_banned")}, indent=1))


if __name__ == "__main__":
    main()
