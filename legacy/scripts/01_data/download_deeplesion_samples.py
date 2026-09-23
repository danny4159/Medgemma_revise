import json
import os

from huggingface_hub import hf_hub_download

os.environ.setdefault("HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache")
if "HF_TOKEN" not in os.environ:
    with open(os.path.expanduser("~/.cache/huggingface/token")) as f:
        os.environ["HF_TOKEN"] = f.read().strip()

REPO = "Voxel51/deeplesion-balanced-2k"
OUT_DIR = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_samples/not_in_training/deeplesion_ct"
os.makedirs(OUT_DIR, exist_ok=True)

LESION_TYPE_NAMES = {
    1: "bone", 2: "abdomen", 3: "mediastinum", 4: "liver",
    5: "lung", 6: "kidney", 7: "soft tissue", 8: "pelvis", -1: "unknown",
}

samples_path = hf_hub_download(REPO, "samples.json", repo_type="dataset")
with open(samples_path) as f:
    all_samples = json.load(f)["samples"]

# pick one sample per lesion_type to get 8 diverse body regions, then pad to 10
by_type = {}
for s in all_samples:
    lt = s.get("lesion_type", -1)
    if lt not in by_type:
        by_type[lt] = s

picked = list(by_type.values())[:10]
remaining = [s for s in all_samples if s not in picked]
while len(picked) < 10 and remaining:
    picked.append(remaining.pop(0))

records = []
for idx, s in enumerate(picked):
    filepath = s["filepath"]  # e.g. "data/041.png"
    local_path = hf_hub_download(REPO, filepath, repo_type="dataset")
    fname = f"{idx:02d}.png"
    out_path = os.path.join(OUT_DIR, fname)
    with open(local_path, "rb") as src, open(out_path, "wb") as dst:
        dst.write(src.read())

    dets = s.get("ground_truth", {}).get("detections", [])
    lt = s.get("lesion_type", -1)
    records.append({
        "file": fname,
        "source_file": filepath,
        "patient_index": s.get("patient_index"),
        "lesion_type": LESION_TYPE_NAMES.get(lt, f"type_{lt}"),
        "age": s.get("age"),
        "gender": s.get("gender"),
        "lesion_diameters_mm": s.get("lesion_diameters"),
        "dicom_window": s.get("dicom_window"),
        "num_bounding_boxes": len(dets),
        "bounding_boxes_normalized_xywh": [d["bounding_box"] for d in dets],
    })
    print(f"[{idx:02d}] patient {s.get('patient_index')} - {LESION_TYPE_NAMES.get(lt)} lesion, "
          f"diam={s.get('lesion_diameters')}mm")

with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
    json.dump(records, f, ensure_ascii=False, indent=2)

print(f"\nSaved {len(records)} DeepLesion CT samples -> {OUT_DIR}")
