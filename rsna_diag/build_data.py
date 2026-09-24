"""RSNA 감사 -> exclusion manifest -> 결정적 split -> 영상/manifest 저장 (iter_009). GT는 추론 manifest와 분리한다.

사용: python -m rsna_diag.build_data
"""
import glob
import hashlib
import json
import os
import re

import numpy as np
from PIL import Image

from . import dicom_min, rsna_data as rd

RAW = "results/iter_009/source/raw"
ANN = f"{RAW}/pneumonia-challenge-annotations-adjudicated-kaggle_2018.json"
MAP = f"{RAW}/pneumonia-challenge-dataset-mappings_2018.json"
ZIP = f"{RAW}/pneumonia-challenge-dataset-adjudicated-kaggle_2018.zip"
OUT = "results/iter_009"


def previous_patients():
    """이전 반복에서 열어 본/사용한 NIH 환자 (results/iter_003~007 json/jsonl 내 파일명·patient_id)."""
    pats, srcs = {}, {}
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
        p = str(e["patient_id"]).zfill(8)
        pats.setdefault(p, set()).add("results/iter_005/nih_manifest.json:patient_id")
    return {p: sorted(s) for p, s in pats.items()}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    os.makedirs(f"{OUT}/data_audit", exist_ok=True)
    os.makedirs(f"{OUT}/manifests", exist_ok=True)
    os.makedirs(f"{OUT}/data/images", exist_ok=True)
    label, ann = rd.load_annotations(ANN)
    sop_map, dups = rd.load_mapping(MAP)
    rz = rd.RsnaZip(ZIP)
    recs, summary = rd.audit_all(label, ann, sop_map, dups, rz)
    excl = previous_patients()
    json.dump({p: s for p, s in excl.items()}, open(f"{OUT}/manifests/exclusion_previous_nih_patients.json", "w"), indent=1)
    choice, bias = rd.patient_choice(recs, set(excl))
    dev, ev, pool_sizes = rd.make_split(choice)
    assert not (set(dev) & set(ev))
    summary["n_previous_patients_excluded_list"] = len(excl)
    summary["n_previous_patients_in_rsna_eligible"] = len({r["patient"] for r in recs.values() if not r["reasons"]} & set(excl))
    summary["patient_choice"] = bias
    summary["eligible_patient_pool_sizes"] = pool_sizes
    summary["legacy_eval_samples_note"] = ("legacy/eval_samples/not_in_training/nih_chestxray14 10장은 익명 파일명이라 "
                                           "환자 ID를 확인할 수 없어 exclusion에 포함하지 못했다 (미확인 범위)")
    json.dump(summary, open(f"{OUT}/data_audit/audit_summary.json", "w"), indent=1)

    infer, gt, dedup = [], {}, {}
    for split, pats in (("development", dev), ("independent_eval", ev)):
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
    checks = {"dev_n": len(dev), "eval_n": len(ev), "patient_overlap_dev_eval": len(set(dev) & set(ev)),
              "patient_overlap_with_previous": len((set(dev) | set(ev)) & set(excl)),
              "duplicate_decoded_pixels": dup_px, "unique_patients": len(set(dev) | set(ev)),
              "category_counts": {s: {c: sum(1 for g in gt.values() if g["split"] == s and g["category"] == c)
                                      for c in rd.PRIORITY} for s in ("development", "independent_eval")}}
    assert checks["patient_overlap_dev_eval"] == 0 and checks["patient_overlap_with_previous"] == 0 and not dup_px
    json.dump(checks, open(f"{OUT}/data_audit/split_checks.json", "w"), indent=1)
    with open(f"{OUT}/manifests/infer_manifest.jsonl", "w") as f:
        for e in infer:
            f.write(json.dumps(e) + "\n")
    json.dump(gt, open(f"{OUT}/manifests/gt_manifest.json", "w"), indent=1)
    print(json.dumps(checks, indent=1))
    print(json.dumps({k: v for k, v in summary.items() if k != "dicom_tag_signatures"}, indent=1))


if __name__ == "__main__":
    main()
