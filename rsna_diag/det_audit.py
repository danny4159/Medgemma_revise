"""train2400+validation400+confirm800(=3600명) 전체 file/pixel hash 및 분할 중복 감사.
iter_033 data_audit.json은 60명 표본만 재계산했다; 이번에는 전체를 재계산한다. default env, torch 불필요.
원본: results/iter_034/data_audit_full.py (sha256 59dd08cf...). iter_035: 출력 경로를 iter_035로 바꾸고,
detector 학습·평가 manifest(train2400_full/V100/V400/D32/L64/D24)가 iter_010 분할의 부분집합인지와
iter_034 감사 결과와의 불변성을 함께 기록한다. 기존 결과 파일은 덮어쓰지 않는다."""
import hashlib
import json
import os

import numpy as np
from PIL import Image

BASE = "/SSD1_1TB/home/milab/daniel/08_medgemma/research"
IT010 = f"{BASE}/results/iter_010/manifests"
OUT = f"{BASE}/results/iter_035/data"


def main():
    gt = json.load(open(f"{IT010}/gt_manifest.json"))
    train_ids = json.load(open(f"{IT010}/train_ids.json"))
    val_ids = json.load(open(f"{IT010}/validation_ids.json"))
    confirm_ids = json.load(open(f"{IT010}/confirm_ids.json"))
    infer = {}
    with open(f"{IT010}/infer_manifest.jsonl") as f:
        for line in f:
            r = json.loads(line)
            infer[r["id"]] = r

    all_ids = train_ids + val_ids + confirm_ids
    overlaps = {
        "train_val": sorted(set(train_ids) & set(val_ids)),
        "train_confirm": sorted(set(train_ids) & set(confirm_ids)),
        "val_confirm": sorted(set(val_ids) & set(confirm_ids)),
    }
    dup_within = len(all_ids) - len(set(all_ids))

    hash_mismatches = []
    missing_gt = []
    missing_infer = []
    pixel_hash_all = {}
    n_checked = 0
    for pid in all_ids:
        if pid not in gt:
            missing_gt.append(pid)
            continue
        if pid not in infer:
            missing_infer.append(pid)
            continue
        rec = infer[pid]
        path = f"{BASE}/{rec['image']}"
        with open(path, "rb") as f:
            data = f.read()
        file_sha = hashlib.sha256(data).hexdigest()
        arr = np.array(Image.open(path))
        pixel_sha = hashlib.sha256(arr.tobytes()).hexdigest()
        pixel_hash_all[pid] = pixel_sha
        n_checked += 1
        if file_sha != rec.get("file_sha256"):
            hash_mismatches.append({"id": pid, "kind": "file", "expected": rec.get("file_sha256"), "got": file_sha})
        if pixel_sha != gt[pid].get("pixel_sha256"):
            hash_mismatches.append({"id": pid, "kind": "pixel", "expected": gt[pid].get("pixel_sha256"), "got": pixel_sha})

    # cross-split decoded-pixel duplicate check across the FULL 3600 (not just a sample)
    by_pixel = {}
    id_to_split = {}
    for pid in train_ids:
        id_to_split[pid] = "train"
    for pid in val_ids:
        id_to_split[pid] = "validation"
    for pid in confirm_ids:
        id_to_split[pid] = "confirm"
    for pid, h in pixel_hash_all.items():
        by_pixel.setdefault(h, []).append(pid)
    dup_pixel_groups = {h: ids for h, ids in by_pixel.items() if len(ids) > 1}
    cross_split_dup = {h: ids for h, ids in dup_pixel_groups.items()
                        if len(set(id_to_split[i] for i in ids)) > 1}

    issues = []
    if any(overlaps.values()):
        issues.append("patient id overlap across splits")
    if dup_within:
        issues.append(f"{dup_within} duplicate ids within the concatenated 3600 list")
    if hash_mismatches:
        issues.append(f"{len(hash_mismatches)} file/pixel hash mismatches")
    if missing_gt or missing_infer:
        issues.append(f"missing_gt={len(missing_gt)} missing_infer={len(missing_infer)}")
    if cross_split_dup:
        issues.append(f"{len(cross_split_dup)} cross-split decoded-pixel duplicate groups")
    if dup_pixel_groups and not cross_split_dup:
        issues.append(f"{len(dup_pixel_groups)} within-split decoded-pixel duplicate groups (not cross-split)")

    mans = {}
    for nm, p in (("train2400_full", f"{BASE}/results/iter_033/data/train2400_full.json"), ("V100", f"{BASE}/results/iter_033/data/V100.json"),
                  ("D32", f"{BASE}/results/iter_033/data/D32.json"), ("L64", f"{BASE}/results/iter_033/data/L64.json"),
                  ("V400", f"{BASE}/results/iter_034/data/V400.json"), ("D24", f"{BASE}/results/iter_035/data/D24.json")):
        mids = json.load(open(p))["ids"]
        mans[nm] = {"n": len(mids), "n_unique": len(set(mids)),
                    "subset_of": [s for s, ss in (("train", train_ids), ("validation", val_ids), ("confirm", confirm_ids)) if set(mids) <= set(ss)]}
    issues += [f"manifest {k} not within a single split" for k, v in mans.items() if len(v["subset_of"]) != 1 or v["n"] != v["n_unique"]]
    if set(json.load(open(f"{BASE}/results/iter_033/data/train2400_full.json"))["ids"]) != set(train_ids):
        issues.append("train2400_full != iter_010 train ids")
    prev = json.load(open(f"{BASE}/results/iter_034/data/data_audit_full_3600.json"))
    result = {
        "detector_manifests": mans,
        "iter034_audit_same_counts": {k: prev.get(k) == v for k, v in (("n_checked", n_checked), ("duplicate_pixel_groups_total", len(dup_pixel_groups)))},
        "n_train": len(train_ids), "n_validation": len(val_ids), "n_confirm": len(confirm_ids),
        "n_total": len(all_ids), "n_checked": n_checked,
        "overlaps": {k: len(v) for k, v in overlaps.items()},
        "overlap_ids": overlaps,
        "duplicate_ids_within_concat": dup_within,
        "hash_mismatches": hash_mismatches,
        "missing_gt": missing_gt, "missing_infer": missing_infer,
        "duplicate_pixel_groups_total": len(dup_pixel_groups),
        "cross_split_duplicate_pixel_groups": cross_split_dup,
        "sop_linkage_note": "infer_manifest.jsonl에는 SOPInstanceUID 등 DICOM 식별자 필드가 없어 "
                             "환자 ID(파일명 기반) 외의 SOP 수준 연결 여부는 이번 감사에서 검증하지 못했다 (미검증 범위).",
        "issues": issues, "ok": len(issues) == 0,
    }
    with open(f"{OUT}/data_audit_full_3600.json", "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k not in ("overlap_ids", "hash_mismatches", "cross_split_duplicate_pixel_groups")}, indent=2))


if __name__ == "__main__":
    main()
