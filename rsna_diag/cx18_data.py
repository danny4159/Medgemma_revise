"""iter_018 자료 gate: CheXpert validation HF parquet + MedAug valid.csv 연결, 단일 frontal 환자 선택, 4조합 층화, legacy dedup 점검.

- HF danjacobellis/chexpert validation parquet의 bytes sha256을 사전에 확인한 값과 대조한다 (변경되면 중단).
- MedAug Path(연구진 공개 CSV)를 정규화해 HF와 정확히 일대일 대응시키고, 최소 다섯 competition finding에 대해
  HF 2/3(absent/present) <-> CSV 0.0/1.0 대응을 전수 검증한다 (하나라도 불일치면 중단).
- 영상이 정확히 하나이고 frontal인 study만 선택한다. 동일 환자의 study가 둘 이상이면 study 이름으로 정렬해 첫 study만 쓴다.
- legacy/eval_samples의 chexpert 익명 샘플과 average-hash 거리로 근접 중복 후보를 점검한다 (임계 미만이면 중단; 값이 크면 통과).
사용: python -m rsna_diag.cx18_data build
"""
import argparse
import csv
import glob
import hashlib
import io
import json
import os
import re

import numpy as np
from PIL import Image

HF_PARQUET = "results/iter_018/source/chexpert_validation.parquet"
MEDAUG_CSV = "results/iter_018/source/medaug_valid.csv"
HF_PARQUET_SHA256 = "78a544b5bf0c98de2a1293e9de908e8f8857aebcad4819692314110472acf5b4"
HF_REVISION = "ca5a840e438b5d2d0fa07f560782f196b38a84aa"
IMG_DIR = "results/iter_018/manifests/images"
MANIFEST_PATH = "results/iter_018/manifests/infer_manifest.jsonl"
LABELS_PATH = "results/iter_018/manifests/labels.json"
SETS_PATH = "results/iter_018/manifests/sets.json"
PROVENANCE_PATH = "results/iter_018/manifests/provenance.json"
FINDINGS_CHECKED = ["Cardiomegaly", "Pleural Effusion", "Lung Opacity", "Edema", "Atelectasis", "Consolidation", "Pneumothorax"]
LEGACY_DIR = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_samples/not_in_training/chexpert"
DEDUP_HAMMING_THRESHOLD = 10  # 16x16 average hash = 256 bit; 관찰된 최소 실측 거리(29)보다 충분히 낮은 보수적 경보선
MIN_PER_CATEGORY = 24


class DataGateError(RuntimeError):
    pass


def sha(b):
    return hashlib.sha256(b).hexdigest()


def _norm_path(p):
    m = re.search(r"(CheXpert-v1\.0-small/.*)$", p)
    if not m:
        raise DataGateError(f"cannot normalize MedAug Path {p!r}")
    return m.group(1)


def load_sources():
    parq_sha = sha(open(HF_PARQUET, "rb").read())
    if parq_sha != HF_PARQUET_SHA256:
        raise DataGateError(f"HF validation parquet sha256 {parq_sha} differs from pinned {HF_PARQUET_SHA256}")
    import pandas as pd
    hf = pd.read_parquet(HF_PARQUET)
    rows = list(csv.DictReader(open(MEDAUG_CSV)))
    csv_by_path = {}
    for r in rows:
        norm = _norm_path(r["Path"])
        if norm in csv_by_path:
            raise DataGateError(f"duplicate Path in MedAug csv: {norm}")
        csv_by_path[norm] = r
    return hf, csv_by_path


def cross_check(hf, csv_by_path):
    """Path 전수 연결과 finding 값 대응(HF 2<->CSV 0.0=absent, HF 3<->CSV 1.0=present) 검증. validation에는 uncertain/unlabeled가 없어야 한다."""
    hf_paths = set(hf["Path"])
    missing_in_csv = sorted(hf_paths - set(csv_by_path))
    extra_in_csv = sorted(set(csv_by_path) - hf_paths)
    if missing_in_csv or extra_in_csv:
        raise DataGateError(f"Path mismatch: missing_in_csv={missing_in_csv[:5]} extra_in_csv={extra_in_csv[:5]}")
    for _, r in hf.iterrows():
        cr = csv_by_path[r["Path"]]
        for f in FINDINGS_CHECKED:
            hval = int(r[f])
            cval = float(cr[f])
            if hval not in (2, 3):
                raise DataGateError(f"{r['Path']} {f}: HF label {hval} not absent(2)/present(3) in validation")
            if (hval == 2 and cval != 0.0) or (hval == 3 and cval != 1.0):
                raise DataGateError(f"{r['Path']} {f}: HF={hval} CSV={cval} mismatch")
    return {"n_images": int(len(hf)), "findings_checked": FINDINGS_CHECKED}


def group_studies(hf):
    studies = {}
    for _, r in hf.iterrows():
        m = re.match(r"CheXpert-v1\.0-small/valid/(patient\d+)/(study\d+)/(view\d+_(frontal|lateral))\.jpg$", r["Path"])
        if not m:
            raise DataGateError(f"unexpected Path format: {r['Path']}")
        pid, study, view = m.group(1), m.group(2), m.group(3)
        studies.setdefault((pid, study), []).append((view, r))
    return studies


def select_single_frontal(studies):
    """정확히 영상 하나이고 frontal인 study만 선택한다. 동일 환자에 그런 study가 둘 이상이면 study명으로 정렬한 첫 study만 쓴다."""
    single_by_patient = {}
    for (pid, study), views in studies.items():
        if len(views) != 1:
            continue
        vname, r = views[0]
        if "frontal" not in vname:
            continue
        single_by_patient.setdefault(pid, []).append((study, vname, r))
    out, dropped_multi_study = {}, []
    for pid, items in single_by_patient.items():
        if len(items) > 1:
            dropped_multi_study.append(pid)
            items = sorted(items, key=lambda t: t[0])
        out[pid] = items[0]
    return out, dropped_multi_study


def ahash(im, size=16):
    im = im.convert("L").resize((size, size), Image.LANCZOS)
    arr = np.asarray(im, dtype=np.float64)
    return (arr > arr.mean()).astype(np.uint8)


def legacy_dedup_check(patient_images):
    """patient_images: {patient_id: jpeg bytes}. legacy chexpert 샘플과 average-hash 거리를 계산한다."""
    legacy_files = sorted(glob.glob(os.path.join(LEGACY_DIR, "*.jpg")))
    if not legacy_files:
        raise DataGateError(f"no legacy chexpert files found in {LEGACY_DIR}")
    hashes = {pid: ahash(Image.open(io.BytesIO(b))) for pid, b in patient_images.items()}
    out = []
    for lf in legacy_files:
        lh = ahash(Image.open(lf))
        best_pid, best_dist = None, None
        for pid, h in hashes.items():
            d = int((h != lh).sum())
            if best_dist is None or d < best_dist:
                best_pid, best_dist = pid, d
        out.append({"legacy_file": os.path.basename(lf), "best_match_patient": best_pid, "hamming_dist_256": best_dist,
                    "near_duplicate": best_dist < DEDUP_HAMMING_THRESHOLD})
    return out


def build(a):
    os.makedirs(IMG_DIR, exist_ok=True)
    if os.path.exists(MANIFEST_PATH):
        raise DataGateError(f"{MANIFEST_PATH} exists (not overwriting; delete manually if a rebuild is intended)")
    hf, csv_by_path = load_sources()
    cross = cross_check(hf, csv_by_path)
    studies = group_studies(hf)
    view_counts = {}
    for v in studies.values():
        view_counts[len(v)] = view_counts.get(len(v), 0) + 1
    single, dropped_multi_study = select_single_frontal(studies)
    patient_images, labels = {}, {}
    for pid, (study, vname, r) in single.items():
        img_bytes = r["image"]["bytes"]
        patient_images[pid] = img_bytes
        img_path = os.path.join(IMG_DIR, f"{pid}.jpg")
        with open(img_path, "wb") as f:
            f.write(img_bytes)
        arr = np.asarray(Image.open(io.BytesIO(img_bytes)))
        cm = "present" if int(r["Cardiomegaly"]) == 3 else "absent"
        pe = "present" if int(r["Pleural Effusion"]) == 3 else "absent"
        labels[pid] = {"path": r["Path"], "study": study, "view": vname, "ap_pa": int(r["AP/PA"]),
                       "cardiomegaly": cm, "pleural_effusion": pe, "category": f"{cm}_{pe}",
                       "file_sha256": sha(img_bytes), "pixel_sha256": sha(arr.tobytes())}
    dedup = legacy_dedup_check(patient_images)
    near_dupes = [d for d in dedup if d["near_duplicate"]]
    if near_dupes:
        raise DataGateError(f"legacy near-duplicate candidates found (manual review needed): {near_dupes}")
    cats = {}
    for pid, l in labels.items():
        cats.setdefault(l["category"], []).append(pid)
    counts = {c: len(v) for c, v in cats.items()}
    short = {c: counts.get(c, 0) for c in ("absent_absent", "present_absent", "absent_present", "present_present")
             if counts.get(c, 0) < MIN_PER_CATEGORY}
    if short:
        raise DataGateError(f"category below minimum {MIN_PER_CATEGORY}: {short}")
    from . import cx18_spec as CX
    splits = CX.split_patients(cats)
    with open(MANIFEST_PATH, "w") as f:
        for pid in sorted(labels):
            l = labels[pid]
            f.write(json.dumps({"id": pid, "split": l["category"], "image": os.path.join(IMG_DIR, f"{pid}.jpg"),
                                "file_sha256": l["file_sha256"], "pixel_sha256": l["pixel_sha256"]}) + "\n")
    json.dump(labels, open(LABELS_PATH, "w"), indent=1, sort_keys=True)
    json.dump(splits, open(SETS_PATH, "w"), indent=1, sort_keys=True)
    prov = {"hf_revision": HF_REVISION, "hf_parquet_sha256": HF_PARQUET_SHA256, "medaug_csv_sha256": sha(open(MEDAUG_CSV, "rb").read()),
            "cross_check": cross, "view_count_per_study": view_counts, "n_single_frontal": len(single),
            "dropped_multi_study_patients": dropped_multi_study, "category_counts": counts, "legacy_dedup": dedup,
            "n_patients_total": len(labels), "split_counts": {k: {c: len(v) for c, v in splits[k].items()} for k in splits}}
    json.dump(prov, open(PROVENANCE_PATH, "w"), indent=1, sort_keys=True, default=str)
    print(json.dumps({"n_patients": len(labels), "category_counts": counts, "view_count_per_study": view_counts,
                      "split_counts": prov["split_counts"]}))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("build")
    a = ap.parse_args()
    if a.cmd == "build":
        build(a)


if __name__ == "__main__":
    main()
