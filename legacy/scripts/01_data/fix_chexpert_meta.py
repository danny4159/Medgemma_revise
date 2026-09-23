import json
import os

os.environ.setdefault("HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache")
if "HF_TOKEN" not in os.environ:
    with open(os.path.expanduser("~/.cache/huggingface/token")) as f:
        os.environ["HF_TOKEN"] = f.read().strip()

from datasets import load_dataset

OUT_DIR = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_samples/not_in_training/chexpert"
N = 10

# CheXpert ClassLabel encoding: 0=unlabeled, 1=uncertain, 2=absent, 3=present
CODE = {0: "unlabeled", 1: "uncertain", 2: "absent", 3: "present"}
SEX = {0: "Male", 1: "Female"}
LABEL_COLS = [
    "No Finding", "Enlarged Cardiomediastinum", "Cardiomegaly", "Lung Opacity",
    "Lung Lesion", "Edema", "Consolidation", "Pneumonia", "Atelectasis",
    "Pneumothorax", "Pleural Effusion", "Pleural Other", "Fracture", "Support Devices",
]

ds = load_dataset("danjacobellis/chexpert", split="train", streaming=True)
records = []
for i, ex in enumerate(ds):
    if i >= N:
        break
    records.append({
        "file": f"{i:02d}.jpg",
        "sex": SEX.get(ex.get("Sex")),
        "age": ex.get("Age"),
        "view": "Frontal" if ex.get("Frontal/Lateral") == 0 else "Lateral",
        "present": [c for c in LABEL_COLS if ex.get(c) == 3],
        "absent": [c for c in LABEL_COLS if ex.get(c) == 2],
        "uncertain": [c for c in LABEL_COLS if ex.get(c) == 1],
        "raw_codes": {c: CODE.get(ex.get(c)) for c in LABEL_COLS},
    })
    print(f"[{i:02d}] present={records[-1]['present']} uncertain={records[-1]['uncertain']}")

with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
    json.dump(records, f, ensure_ascii=False, indent=2)
print(f"\nRewrote {OUT_DIR}/meta.json with decoded labels")
