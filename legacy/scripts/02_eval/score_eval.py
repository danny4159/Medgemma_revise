"""Scores the raw MedGemma outputs produced by run_eval.py."""
import json
import re
import string
from collections import Counter, defaultdict

RAW = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_results/raw_outputs.jsonl"
OUT = "/SSD1_1TB/home/milab/daniel/08_medgemma/legacy/eval_results/scores.json"

# ---------------------------------------------------------------- text utils

def normalize(s):
    s = s.lower()
    s = "".join(ch for ch in s if ch not in set(string.punctuation))
    s = re.sub(r"\b(a|an|the)\b", " ", s)
    return " ".join(s.split())


def token_f1(pred, gold):
    p, g = normalize(pred).split(), normalize(gold).split()
    if not p or not g:
        return float(p == g)
    common = Counter(p) & Counter(g)
    n = sum(common.values())
    if n == 0:
        return 0.0
    prec, rec = n / len(p), n / len(g)
    return 2 * prec * rec / (prec + rec)


def first_yes_no(text):
    m = re.search(r"\b(yes|no)\b", text.lower())
    return m.group(1) if m else None


# ------------------------------------------------- label synonyms for keyword scoring

SYNONYMS = {
    # CheXpert / NIH chest findings
    "no finding": ["no finding", "normal", "unremarkable", "no acute", "clear lung", "within normal limits"],
    "enlarged cardiomediastinum": ["enlarged cardiomediastinum", "widened mediastinum", "mediastinal widening"],
    "cardiomegaly": ["cardiomegaly", "enlarged heart", "heart is enlarged", "cardiac enlargement",
                     "increased cardiac silhouette", "enlarged cardiac silhouette"],
    "lung opacity": ["opacity", "opacities", "opacification"],
    "lung lesion": ["lung lesion", "pulmonary lesion", "nodule", "mass"],
    "edema": ["edema", "oedema", "vascular congestion", "pulmonary congestion"],
    "consolidation": ["consolidation", "consolidative"],
    "pneumonia": ["pneumonia", "infection", "infectious"],
    "atelectasis": ["atelectasis", "atelectatic", "collapse", "volume loss"],
    "pneumothorax": ["pneumothorax"],
    "pleural effusion": ["pleural effusion", "effusion", "blunting of the costophrenic"],
    "effusion": ["effusion", "pleural effusion", "blunting of the costophrenic"],
    "pleural other": ["pleural thickening", "pleural abnormality"],
    "pleural_thickening": ["pleural thickening"],
    "fracture": ["fracture", "fractured"],
    "support devices": ["support device", "catheter", "tube", "line", "pacemaker",
                        "sternotomy", "wires", "port", "picc", "lead"],
    "infiltration": ["infiltrate", "infiltration"],
    "mass": ["mass"],
    "nodule": ["nodule", "nodular"],
    "emphysema": ["emphysema", "emphysematous", "hyperinflation"],
    "fibrosis": ["fibrosis", "fibrotic", "scarring", "reticular"],
    "hernia": ["hernia", "herniation", "hiatal"],
    # VinDr-CXR finding names
    "aortic enlargement": ["aortic enlargement", "aortic dilat", "ectatic aorta", "aneurysm",
                           "tortuous aorta", "widened aorta", "unfolded aorta"],
    "calcification": ["calcification", "calcified"],
    "ild": ["interstitial", "ild", "reticular", "fibrosis", "honeycomb"],
    "nodule/mass": ["nodule", "mass", "nodular"],
    "pleural thickening": ["pleural thickening"],
    "pulmonary fibrosis": ["fibrosis", "fibrotic", "scarring", "reticular"],
    "other lesion": ["lesion"],
    "mediastinal shift": ["mediastinal shift", "shift of the mediastinum", "tracheal deviation"],
    "rib fracture": ["rib fracture", "fracture"],
    "lung cavity": ["cavity", "cavitary", "cavitation"],
    "lung cyst": ["cyst", "cystic"],
    "enlarged pa": ["pulmonary artery", "enlarged pa"],
    "clavicle fracture": ["clavicle fracture", "clavicular fracture", "fracture"],
    # BraTS
    "glioma": ["glioma", "glioblastoma", "gbm", "astrocytoma"],
    "brain tumor": ["tumor", "tumour", "neoplasm", "mass", "lesion"],
    # DeepLesion body regions
    "abdomen": ["abdomen", "abdominal"],
    "soft tissue": ["soft tissue"],
    "lung": ["lung", "pulmonary"],
    "kidney": ["kidney", "renal"],
    "bone": ["bone", "osseous", "vertebra", "spine", "rib"],
    "mediastinum": ["mediastinum", "mediastinal", "lymph node"],
    "pelvis": ["pelvis", "pelvic"],
    "liver": ["liver", "hepatic"],
    "unknown": [],
}


def mentions(text, label):
    """Does free text mention this label (via its synonym list)?"""
    t = text.lower()
    for kw in SYNONYMS.get(label.lower(), [label.lower()]):
        if kw in t:
            return True
    return False


# ---------------------------------------------------------------- spatial utils

def parse_cell(text):
    # prefer the digit that follows the word "cell" so a restated legend
    # ("1=top-left, ...") cannot be mistaken for the answer
    m = re.search(r"cell\s*\**\s*([1-9])", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"\b([1-9])\b", text)
    return int(m.group(1)) if m else None


def parse_bbox(text):
    nums = re.findall(r"-?\d*\.?\d+", text)
    if len(nums) < 4:
        return None
    b = [float(x) for x in nums[:4]]
    if max(b) > 1.5:  # model answered in pixels; cannot normalize reliably
        return None
    x0, y0, x1, y1 = b
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    return [x0, y0, x1, y1]


def iou(a, b):
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def location_words(bbox, radiological):
    """Location terms implied by a normalized bbox.

    In radiological convention the image's left side is the patient's RIGHT side,
    so the horizontal term is flipped for X-ray / CT / MRI.
    """
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    if cx < 0.4:
        side = "right" if radiological else "left"
    elif cx > 0.6:
        side = "left" if radiological else "right"
    else:
        side = "central"
    vert = "upper" if cy < 0.4 else ("lower" if cy > 0.6 else "middle")
    return side, vert


VERT_SYN = {
    "upper": ["upper", "superior", "apical", "apex", "top", "frontal lobe"],
    "middle": ["middle", "mid", "central", "hilar", "center"],
    "lower": ["lower", "inferior", "base", "basal", "bottom", "temporal lobe"],
}
SIDE_SYN = {
    "left": ["left"],
    "right": ["right"],
    "central": ["central", "midline", "center", "middle"],
}


# ---------------------------------------------------------------- scoring

def main():
    rows = [json.loads(l) for l in open(RAW)]
    results = {}

    # ------------------------------ Group 1: free-text QA
    g1 = defaultdict(list)
    for r in rows:
        if r["group"] == "G1":
            g1[r["dataset"]].append(r)
    results["G1"] = {}
    for ds, rs in g1.items():
        f1s = [token_f1(r["output"], r["gt"]["answer"]) for r in rs]
        ems = [float(normalize(r["output"]) == normalize(r["gt"]["answer"])) for r in rs]
        closed = [r for r in rs if normalize(r["gt"]["answer"]) in ("yes", "no")]
        closed_acc = [float(first_yes_no(r["output"]) == normalize(r["gt"]["answer"])) for r in closed]
        results["G1"][ds] = {
            "n": len(rs),
            "token_f1": round(sum(f1s) / len(f1s), 4),
            "exact_match": round(sum(ems) / len(ems), 4),
            "n_closed_yesno": len(closed),
            "closed_accuracy": round(sum(closed_acc) / len(closed_acc), 4) if closed_acc else None,
        }

    # ------------------------------ Group 2
    results["G2"] = {}
    for ds in ["chexpert", "nih_chestxray14"]:
        ds_rows = [r for r in rows if r["dataset"] == ds]
        entry = {}

        # Method A: parse the comma-separated selection
        a_rows = [r for r in ds_rows if r["method"] == "A_multilabel"]
        tp = fp = fn = 0
        per_image = []
        for r in a_rows:
            labels = r["gt"]["label_set"]
            out_l = r["output"].lower()
            pred = {l for l in labels if l.lower() in out_l}
            gold = set(r["gt"]["present"])
            tp += len(pred & gold); fp += len(pred - gold); fn += len(gold - pred)
            per_image.append({"pred": sorted(pred), "gold": sorted(gold)})
        entry["A_multilabel"] = {
            "n": len(a_rows),
            "micro_precision": round(tp / (tp + fp), 4) if tp + fp else 0.0,
            "micro_recall": round(tp / (tp + fn), 4) if tp + fn else 0.0,
            "micro_f1": round(2 * tp / (2 * tp + fp + fn), 4) if tp else 0.0,
            "examples": per_image[:4],
        }

        # Method B: forced yes/no per label (uncertain labels excluded)
        b_rows = [r for r in ds_rows if r["method"] == "B_binary"]
        tp = tn = fp = fn = unparsed = skipped = 0
        for r in b_rows:
            lab = r["gt"]["label"]
            if lab in r["gt"].get("uncertain", []):
                skipped += 1
                continue
            gold = "yes" if lab in r["gt"]["present"] else "no"
            pred = first_yes_no(r["output"])
            if pred is None:
                unparsed += 1
                continue
            if gold == "yes":
                tp += pred == "yes"; fn += pred == "no"
            else:
                tn += pred == "no"; fp += pred == "yes"
        total = tp + tn + fp + fn
        entry["B_binary"] = {
            "n": len(b_rows), "n_scored": total, "n_unparsed": unparsed,
            "n_skipped_uncertain": skipped,
            "accuracy": round((tp + tn) / total, 4) if total else None,
            "sensitivity_recall": round(tp / (tp + fn), 4) if tp + fn else None,
            "specificity": round(tn / (tn + fp), 4) if tn + fp else None,
            "precision": round(tp / (tp + fp), 4) if tp + fp else None,
            "confusion": {"tp": tp, "fn": fn, "tn": tn, "fp": fp},
        }

        # Method C: open-ended report, keyword matched
        c_rows = [r for r in ds_rows if r["method"] == "C_openended"]
        tp = fp = fn = 0
        for r in c_rows:
            labels = r["gt"]["label_set"]
            pred = {l for l in labels if mentions(r["output"], l)}
            gold = set(r["gt"]["present"])
            tp += len(pred & gold); fp += len(pred - gold); fn += len(gold - pred)
        entry["C_openended"] = {
            "n": len(c_rows),
            "micro_precision": round(tp / (tp + fp), 4) if tp + fp else 0.0,
            "micro_recall": round(tp / (tp + fn), 4) if tp + fn else 0.0,
            "micro_f1": round(2 * tp / (2 * tp + fp + fn), 4) if tp else 0.0,
        }
        results["G2"][ds] = entry

    # ------------------------------ Group 3
    results["G3"] = {}
    for ds in ["brats2023", "deeplesion_ct", "vindr_cxr"]:
        ds_rows = [r for r in rows if r["dataset"] == ds]
        entry = {}

        # 1) grid cell
        g_rows = [r for r in ds_rows if r["method"] == "1_grid"]
        hits, any_hits, unparsed, preds = 0, 0, 0, []
        for r in g_rows:
            pred = parse_cell(r["output"])
            preds.append(pred)
            if pred is None:
                unparsed += 1
                continue
            hits += pred == r["gt"]["cell"]
            any_hits += pred in r["gt"].get("all_cells", [r["gt"]["cell"]])
        n = len(g_rows)
        gt_cells = [r["gt"]["cell"] for r in g_rows]
        # lesions cluster near the image centre, so "always answer 5" is the honest
        # baseline to beat, not uniform random over 9 cells
        center_baseline = sum(c == 5 for c in gt_cells) / n if n else None
        majority_cell, majority_n = Counter(gt_cells).most_common(1)[0] if gt_cells else (None, 0)
        entry["1_grid"] = {
            "n": n, "n_unparsed": unparsed,
            "accuracy_main_lesion": round(hits / n, 4) if n else None,
            "accuracy_any_lesion": round(any_hits / n, 4) if n else None,
            "random_baseline": round(1 / 9, 4),
            "always_center_baseline": round(center_baseline, 4) if center_baseline is not None else None,
            "majority_cell_baseline": round(majority_n / n, 4) if n else None,
            "majority_cell": majority_cell,
            "predicted_cells": preds,
            "gt_cells": gt_cells,
        }

        # 2) direct bbox -> IoU (with a whole-image baseline for comparison)
        b_rows = [r for r in ds_rows if r["method"] == "2_bbox"]
        ious, base_ious, unparsed = [], [], 0
        for r in b_rows:
            box = parse_bbox(r["output"])
            gtb = r["gt"]["bbox_xyxy"]
            base_ious.append(iou([0.0, 0.0, 1.0, 1.0], gtb))
            if box is None:
                unparsed += 1
                continue
            ious.append(iou(box, gtb))
        entry["2_bbox"] = {
            "n": len(b_rows), "n_parsed": len(ious), "n_unparsed": unparsed,
            "mean_iou": round(sum(ious) / len(ious), 4) if ious else None,
            "iou@0.5": round(sum(i >= 0.5 for i in ious) / len(ious), 4) if ious else None,
            "iou@0.3": round(sum(i >= 0.3 for i in ious) / len(ious), 4) if ious else None,
            "whole_image_baseline_iou": round(sum(base_ious) / len(base_ious), 4) if base_ious else None,
            "per_sample_iou": [round(i, 4) for i in ious],
        }

        # 3) free-text description -> location keyword match
        d_rows = [r for r in ds_rows if r["method"] == "3_desc"]
        rad_side = vert_ok = img_side = 0
        for r in d_rows:
            out = r["output"].lower()
            s_rad, v = location_words(r["gt"]["bbox_xyxy"], radiological=True)
            s_img, _ = location_words(r["gt"]["bbox_xyxy"], radiological=False)
            rad_side += any(k in out for k in SIDE_SYN[s_rad])
            img_side += any(k in out for k in SIDE_SYN[s_img])
            vert_ok += any(k in out for k in VERT_SYN[v])
        n = len(d_rows)
        entry["3_desc"] = {
            "n": n,
            "side_accuracy_radiological": round(rad_side / n, 4) if n else None,
            "side_accuracy_image_frame": round(img_side / n, 4) if n else None,
            "vertical_accuracy": round(vert_ok / n, 4) if n else None,
        }

        # 4) lesion name
        n_rows = [r for r in ds_rows if r["method"] == "4_name"]
        name_hits = 0
        details = []
        for r in n_rows:
            ok = any(mentions(r["output"], nm) for nm in r["gt"]["names"])
            name_hits += ok
            details.append({"output": r["output"][:80], "gt": r["gt"]["names"], "hit": ok})
        entry["4_name"] = {
            "n": len(n_rows),
            "name_accuracy": round(name_hits / len(n_rows), 4) if n_rows else None,
            "details": details,
        }

        # also score lesion names mentioned in the free-text descriptions
        desc_name_hits = sum(
            any(mentions(r["output"], nm) for nm in r["gt"]["names"]) for r in d_rows
        )
        entry["3_desc"]["name_accuracy_in_description"] = (
            round(desc_name_hits / len(d_rows), 4) if d_rows else None
        )

        results["G3"][ds] = entry

    with open(OUT, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
