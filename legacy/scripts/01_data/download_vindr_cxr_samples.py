import json
import os

import pandas as pd
from huggingface_hub import hf_hub_download

os.environ.setdefault("HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache")
if "HF_TOKEN" not in os.environ:
    with open(os.path.expanduser("~/.cache/huggingface/token")) as f:
        os.environ["HF_TOKEN"] = f.read().strip()

REPO = "sunday-hao/vindr-cxr-testset"
OUT_DIR = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_samples/not_in_training/vindr_cxr"
os.makedirs(OUT_DIR, exist_ok=True)

csv_path = hf_hub_download(REPO, "test.csv", repo_type="dataset")
df = pd.read_csv(csv_path)

# drop "No finding" rows, keep images with real abnormality boxes, pick 10 diverse classes
abn = df[df["class_name"] != "No finding"]
picked_ids = []
for cls, group in abn.groupby("class_name"):
    img_id = group.iloc[0]["image_id"]
    if img_id not in picked_ids:
        picked_ids.append(img_id)
    if len(picked_ids) >= 10:
        break

records = []
for idx, img_id in enumerate(picked_ids[:10]):
    local_png = hf_hub_download(REPO, f"{img_id}.png", repo_type="dataset")
    fname = f"{idx:02d}.png"
    with open(local_png, "rb") as src, open(os.path.join(OUT_DIR, fname), "wb") as dst:
        dst.write(src.read())

    rows = df[df["image_id"] == img_id]
    boxes = [
        {
            "class_name": r["class_name"],
            "x_min": r["x_min"], "y_min": r["y_min"],
            "x_max": r["x_max"], "y_max": r["y_max"],
        }
        for _, r in rows.iterrows() if r["class_name"] != "No finding"
    ]
    records.append({
        "file": fname,
        "image_id": img_id,
        "orig_width": int(rows.iloc[0]["width"]),
        "orig_height": int(rows.iloc[0]["height"]),
        "bounding_boxes_pixel_xyxy": boxes,
    })
    print(f"[{idx:02d}] {img_id} - {len(boxes)} box(es): {[b['class_name'] for b in boxes]}")

with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
    json.dump(records, f, ensure_ascii=False, indent=2)

print(f"\nSaved {len(records)} VinDr-CXR samples -> {OUT_DIR}")
