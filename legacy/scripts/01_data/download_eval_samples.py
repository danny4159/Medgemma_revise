import io
import json
import os

os.environ.setdefault("HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache")
if "HF_TOKEN" not in os.environ:
    with open(os.path.expanduser("~/.cache/huggingface/token")) as f:
        os.environ["HF_TOKEN"] = f.read().strip()

N = 10
OUT_ROOT = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_samples"


def save_image(img, path):
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.save(path, quality=95)


def dump_meta(records, out_dir):
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


# ---- Group A: datasets USED in MedGemma training (sample from TEST split only) ----

def fetch_vqa_rad():
    from datasets import load_dataset

    out_dir = os.path.join(OUT_ROOT, "used_in_training", "vqa_rad")
    os.makedirs(out_dir, exist_ok=True)
    ds = load_dataset("flaviagiammarino/vqa-rad", split="test", streaming=True)
    records = []
    for i, ex in enumerate(ds):
        if i >= N:
            break
        fname = f"{i:02d}.jpg"
        save_image(ex["image"], os.path.join(out_dir, fname))
        records.append({"file": fname, "question": ex["question"], "answer": ex["answer"]})
    dump_meta(records, out_dir)
    print(f"[vqa_rad] saved {len(records)} samples -> {out_dir}")


def fetch_slake():
    import json as _json

    import remotezip
    from huggingface_hub import hf_hub_download, hf_hub_url

    out_dir = os.path.join(OUT_ROOT, "used_in_training", "slake")
    os.makedirs(out_dir, exist_ok=True)

    test_json_path = hf_hub_download("BoKelvin/SLAKE", "test.json", repo_type="dataset")
    with open(test_json_path, encoding="utf-8") as f:
        test_items = _json.load(f)

    # keep English questions only, first N unique images
    seen_imgs = []
    for item in test_items:
        if item.get("q_lang") != "en":
            continue
        if item["img_name"] not in seen_imgs and len(seen_imgs) < N:
            seen_imgs.append(item["img_name"])
    picked = [
        item for item in test_items
        if item.get("q_lang") == "en" and item["img_name"] in seen_imgs
    ]

    url = hf_hub_url("BoKelvin/SLAKE", "imgs.zip", repo_type="dataset")
    headers = {"Authorization": f"Bearer {os.environ['HF_TOKEN']}"}
    rz = remotezip.RemoteZip(url, headers=headers)

    from PIL import Image

    records = []
    for idx, img_name in enumerate(seen_imgs):
        zpath = f"imgs/{img_name}"
        data = rz.read(zpath)
        img = Image.open(io.BytesIO(data))
        fname = f"{idx:02d}.jpg"
        save_image(img, os.path.join(out_dir, fname))
        qas = [p for p in picked if p["img_name"] == img_name]
        records.append(
            {
                "file": fname,
                "img_name": img_name,
                "qas": [{"question": q["question"], "answer": q["answer"]} for q in qas],
            }
        )
    dump_meta(records, out_dir)
    print(f"[slake] saved {len(records)} samples -> {out_dir}")


# ---- Group B: datasets NOT used in MedGemma training ----

def fetch_chexpert():
    from datasets import load_dataset

    out_dir = os.path.join(OUT_ROOT, "not_in_training", "chexpert")
    os.makedirs(out_dir, exist_ok=True)
    ds = load_dataset("danjacobellis/chexpert", split="train", streaming=True)
    label_cols = [
        "No Finding", "Enlarged Cardiomediastinum", "Cardiomegaly", "Lung Opacity",
        "Lung Lesion", "Edema", "Consolidation", "Pneumonia", "Atelectasis",
        "Pneumothorax", "Pleural Effusion", "Pleural Other", "Fracture", "Support Devices",
    ]
    records = []
    for i, ex in enumerate(ds):
        if i >= N:
            break
        fname = f"{i:02d}.jpg"
        save_image(ex["image"], os.path.join(out_dir, fname))
        labels = {k: ex.get(k) for k in label_cols if ex.get(k) not in (None, "", 0.0)}
        records.append({"file": fname, "sex": ex.get("Sex"), "age": ex.get("Age"), "labels": labels})
    dump_meta(records, out_dir)
    print(f"[chexpert] saved {len(records)} samples -> {out_dir}")


def fetch_kvasir_vqa():
    from datasets import load_dataset

    out_dir = os.path.join(OUT_ROOT, "not_in_training", "kvasir_vqa")
    os.makedirs(out_dir, exist_ok=True)
    ds = load_dataset("SimulaMet-HOST/Kvasir-VQA", split="raw", streaming=True)
    records = []
    for i, ex in enumerate(ds):
        if i >= N:
            break
        fname = f"{i:02d}.jpg"
        save_image(ex["image"], os.path.join(out_dir, fname))
        records.append({"file": fname, "question": ex["question"], "answer": ex["answer"], "source": ex.get("source")})
    dump_meta(records, out_dir)
    print(f"[kvasir_vqa] saved {len(records)} samples -> {out_dir}")


def fetch_nih_cxr14():
    from datasets import load_dataset

    out_dir = os.path.join(OUT_ROOT, "not_in_training", "nih_chestxray14")
    os.makedirs(out_dir, exist_ok=True)
    ds = load_dataset("Medserra/NIH-ChestXray14-Balanced", split="train", streaming=True)
    records = []
    for i, ex in enumerate(ds):
        if i >= N:
            break
        fname = f"{i:02d}.jpg"
        save_image(ex["image"], os.path.join(out_dir, fname))
        records.append(
            {
                "file": fname,
                "findings": ex.get("findings"),
                "view_position": ex.get("view_position"),
            }
        )
    dump_meta(records, out_dir)
    print(f"[nih_chestxray14] saved {len(records)} samples (community mirror, not official NIH release) -> {out_dir}")


if __name__ == "__main__":
    fetch_vqa_rad()
    fetch_slake()
    fetch_chexpert()
    fetch_kvasir_vqa()
    fetch_nih_cxr14()
