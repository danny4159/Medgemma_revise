"""RSNA 감사 -> exclusion -> 결정적 train/validation/confirm split + reserve -> 영상/manifest (iter_010).

iter_009 대비 변경: 신규 gate(DICOM 표시 태그, mapping/ZIP 충돌 중단), 원본 hash를 provenance와 대조, iter_009의 380명과
과거 환자 167명 및 legacy NIH 10장 exact/near-duplicate 후보 환자를 제외, 3분할 + 미사용 reserve. GT는 추론 manifest와 분리한다.

사용: python -m rsna_diag.build_data
"""
import glob
import hashlib
import json
import os
import re

import numpy as np
from PIL import Image

from . import dicom_min, overlay, rsna_data as rd

RAW = "results/iter_009/source/raw"  # 보존된 원본 (읽기 전용)
ANN = f"{RAW}/pneumonia-challenge-annotations-adjudicated-kaggle_2018.json"
MAP = f"{RAW}/pneumonia-challenge-dataset-mappings_2018.json"
ZIP = f"{RAW}/pneumonia-challenge-dataset-adjudicated-kaggle_2018.zip"
OUT = "results/iter_010"
IT9 = "results/iter_009"
LEGACY_NIH = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_samples/not_in_training/nih_chestxray14/*.jpg"
NEAR_DUP_CORR = 0.97


def sha(b):
    return hashlib.sha256(b).hexdigest()


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 24), b""):
            h.update(blk)
    return h.hexdigest()


def verify_sources():
    """현재 파일의 size/sha256을 provenance.json과 대조한다. 불일치면 예외."""
    out = {}
    for p in (ANN, MAP, ZIP):
        prov = json.load(open(p + ".provenance.json"))
        cur = {"size": os.path.getsize(p), "sha256": sha_file(p)}
        ok = cur["size"] == prov["size"] and cur["sha256"] == prov["sha256"]
        out[os.path.basename(p)] = {"current": cur, "provenance": {k: prov[k] for k in ("size", "sha256", "url", "etag")}, "match": ok}
        if not ok:
            raise RuntimeError(f"source hash mismatch vs provenance: {p}")
    return out


def previous_patients():
    """이전 반복에서 열어 본/사용한 NIH 환자 (results/iter_003~008 json/jsonl 내 파일명·patient_id) + iter_009의 380명."""
    pats = {}
    pat = re.compile(r"(\d{8})_\d{3}\.png")
    for f in sorted(glob.glob("results/iter_00[3-8]/**/*.json*", recursive=True)):
        try:
            txt = open(f).read()
        except Exception:
            continue
        for m in pat.finditer(txt):
            pats.setdefault(m.group(1), set()).add(f)
    m5 = json.load(open("results/iter_005/nih_manifest.json"))
    for e in m5:
        pats.setdefault(str(e["patient_id"]).zfill(8), set()).add("results/iter_005/nih_manifest.json:patient_id")
    prev167 = set(json.load(open(f"{IT9}/manifests/exclusion_previous_nih_patients.json")))
    found = set(pats)
    if found != prev167:
        raise RuntimeError(f"previous-patient set differs from iter_009 record: +{sorted(found - prev167)[:5]} -{sorted(prev167 - found)[:5]}")
    gt9 = json.load(open(f"{IT9}/manifests/gt_manifest.json"))
    for g in gt9.values():
        pats.setdefault(g["patient"], set()).add(f"iter_009:{g['split']}")
    return {p: sorted(s) for p, s in pats.items()}, gt9


def thumb(arr):
    im = Image.fromarray(arr if arr.ndim == 2 else np.asarray(Image.fromarray(arr).convert("L")))
    t = np.asarray(im.resize((32, 32), Image.BOX), dtype=np.float64).ravel()
    t = t - t.mean()
    n = np.linalg.norm(t)
    return t / n if n > 0 else t


def legacy_thumbs():
    fs = sorted(glob.glob(LEGACY_NIH))
    assert len(fs) == 10
    return fs, np.stack([thumb(np.asarray(Image.open(f).convert("L"))) for f in fs])


def main():
    os.makedirs(f"{OUT}/data_audit", exist_ok=True)
    os.makedirs(f"{OUT}/manifests", exist_ok=True)
    os.makedirs(f"{OUT}/data/images", exist_ok=True)
    src = verify_sources()
    json.dump(src, open(f"{OUT}/data_audit/source_hash_check.json", "w"), indent=1)
    label, ann = rd.load_annotations(ANN)
    sop_map, dups = rd.load_mapping(MAP)
    rz = rd.RsnaZip(ZIP)
    recs, summary = rd.audit_all(label, ann, sop_map, dups, rz)
    excl, gt9 = previous_patients()
    json.dump(excl, open(f"{OUT}/manifests/exclusion_previous_patients.json", "w"), indent=1)

    # legacy 익명 NIH 10장 exact/near-duplicate 후보: 후보(환자별 선택) 영상 전체의 32x32 thumbnail 상관
    lf, lt = legacy_thumbs()
    choice, bias = rd.patient_choice(recs, set(excl))
    tcache = f"{OUT}/data_audit/thumbs32.npz"
    if os.path.exists(tcache):
        z = np.load(tcache, allow_pickle=True)
        tsop, tarr = list(z["sops"]), z["thumbs"]
    else:
        tsop, tl = [], []
        for p in sorted(choice):
            r = choice[p]
            _, arr = dicom_min.read_pixels(rz.read(r["sop"]))
            tsop.append(r["sop"])
            tl.append(thumb(arr))
        tarr = np.stack(tl)
        np.savez_compressed(tcache, sops=np.array(tsop), thumbs=tarr)
    corr = tarr @ lt.T  # (n_cand, 10)
    hit = np.argwhere(corr >= NEAR_DUP_CORR)
    legacy_hits = [{"legacy_file": os.path.basename(lf[j]), "sop": tsop[i], "corr": float(corr[i, j])} for i, j in hit]
    sop2pat = {r["sop"]: p for p, r in choice.items()}
    legacy_excl = sorted({sop2pat[h["sop"]] for h in legacy_hits})
    top = [{"legacy_file": os.path.basename(lf[j]), "max_corr": float(corr[:, j].max()), "sop": tsop[int(corr[:, j].argmax())]} for j in range(10)]
    if legacy_excl:  # 의심 환자 제외 후 재선택
        excl2 = set(excl) | set(legacy_excl)
        choice, bias = rd.patient_choice(recs, excl2)
    for p in legacy_excl:
        excl.setdefault(p, []).append("legacy_nih_near_duplicate_candidate")

    splits, pool_sizes, reserve = rd.make_split(choice)
    all_pats = [p for v in splits.values() for p in v]
    assert len(all_pats) == len(set(all_pats))
    summary["n_previous_patients_excluded_list"] = len(excl)
    summary["patient_choice"] = bias
    summary["eligible_patient_pool_sizes_after_exclusion"] = pool_sizes
    summary["reserve_sizes"] = {c: len(v) for c, v in reserve.items()}
    summary["legacy_nih_check"] = {"method": "32x32 BOX thumbnail, 0-mean unit-norm correlation, threshold %.2f" % NEAR_DUP_CORR,
                                   "n_candidates_compared": len(tsop), "hits": legacy_hits, "excluded_patients": legacy_excl,
                                   "per_legacy_image_max_corr": top,
                                   "note": "익명 파일명이라 환자 ID 대응은 불가. 다른 표시 변환·크롭 하의 중복과 모델 사전학습 노출은 미확인."}
    json.dump(summary, open(f"{OUT}/data_audit/audit_summary.json", "w"), indent=1)

    px9 = {g["pixel_sha256"]: i for i, g in gt9.items()}
    infer, gt, dedup = [], {}, {}
    for split, pats in splits.items():
        for p in pats:
            r = choice[p]
            meta, arr = dicom_min.read_pixels(rz.read(r["sop"]))
            assert arr.shape == (1024, 1024) and arr.dtype == np.uint8
            px = sha(arr.tobytes())
            dedup.setdefault(px, []).append(r["sop"])
            img_path = f"{OUT}/data/images/{r['sop']}.png"
            Image.fromarray(arr, "L").save(img_path)
            fid = f"{split[:3]}_{p}"
            infer.append({"id": fid, "split": split, "image": img_path, "pixel_sha256": px,
                          "file_sha256": sha(open(img_path, "rb").read())})
            gt[fid] = {"id": fid, "split": split, "patient": p, "sop": r["sop"], "img_id": r["img_id"],
                       "category": r["category"], "orig_labels": r["orig_labels"], "zip": rz.info(r["sop"]),
                       "boxes": rd.gt_entry(r), "pixel_sha256": px}
    dup_px = {k: v for k, v in dedup.items() if len(v) > 1}
    overlap9 = sorted(set(dedup) & set(px9))
    sops = [g["sop"] for g in gt.values()]
    sop9 = {g["sop"] for g in gt9.values()}
    checks = {"split_sizes": {k: len(v) for k, v in splits.items()},
              "unique_patients": len(all_pats), "unique_sop": len(set(sops)),
              "pairwise_patient_overlap": {f"{a}&{b}": len(set(splits[a]) & set(splits[b])) for a in splits for b in splits if a < b},
              "patient_overlap_with_previous_or_iter009": len(set(all_pats) & set(excl)),
              "sop_overlap_with_iter009": len(set(sops) & sop9),
              "decoded_pixel_overlap_with_iter009": len(overlap9),
              "duplicate_decoded_pixels_within": dup_px,
              "category_counts": {s: {c: sum(1 for g in gt.values() if g["split"] == s and g["category"] == c) for c in rd.PRIORITY}
                                  for s in splits},
              "reserve_positive_n": len(reserve[rd.CAT_POS])}
    assert not any(checks["pairwise_patient_overlap"].values()) and checks["patient_overlap_with_previous_or_iter009"] == 0
    assert checks["unique_sop"] == len(sops) and not dup_px and not overlap9 and checks["sop_overlap_with_iter009"] == 0
    for s, t in rd.SPLIT_TARGETS.items():
        assert checks["category_counts"][s] == t, (s, checks["category_counts"][s])
    json.dump(checks, open(f"{OUT}/data_audit/split_checks.json", "w"), indent=1)
    with open(f"{OUT}/manifests/infer_manifest.jsonl", "w") as f:
        for e in infer:
            f.write(json.dumps(e) + "\n")
    json.dump(gt, open(f"{OUT}/manifests/gt_manifest.json", "w"), indent=1)
    json.dump({c: v for c, v in reserve.items()}, open(f"{OUT}/manifests/reserve_patients.json", "w"), indent=1)
    for s, v in splits.items():
        json.dump([f"{s[:3]}_{p}" for p in v], open(f"{OUT}/manifests/{s}_ids.json", "w"))
    # train/validation overlay 검사용 montage (고정 순서 앞 16명 양성)
    os.makedirs(f"{OUT}/overlays", exist_ok=True)
    for s in ("train", "validation"):
        ids = [i for i in sorted(gt) if gt[i]["split"] == s and gt[i]["category"] == "opacity"][:16]
        ims = [overlay.draw(f"{OUT}/data/images/{gt[i]['sop']}.png", [b["yxyx_norm"] for b in gt[i]["boxes"]], [], 384, i) for i in ids]
        overlay.montage(ims, 4).save(f"{OUT}/overlays/{s}_positive_gt_first16.png")
    print(json.dumps(checks, indent=1))
    print(json.dumps({k: v for k, v in summary.items() if k != "dicom_tag_signatures"}, indent=1))


if __name__ == "__main__":
    main()
