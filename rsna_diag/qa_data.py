"""iter_015: 원본 Calculated label audit, D36/E180/E600/P60/P180 고정 split, 일반 inference manifest(정답 없음)와 별도 label 파일.

사용: python -m rsna_diag.qa_data --out results/iter_015/manifests
- 순서는 sha256(scope-v1|20260927|category|patient). D36은 validation, E는 confirm에서만 뽑는다. reserve는 읽지 않는다.
- P180 = 각 category 앞 60명 = E180 전체 (계획의 'E600에서 category별 60명'을 순서 접두어로 구현하면 E180과 같은 집합이다).
"""
import argparse
import hashlib
import json
import os

from . import qa_spec as S, rsna_data as R

RAW = "results/iter_009/source/raw"
ANN = f"{RAW}/pneumonia-challenge-annotations-adjudicated-kaggle_2018.json"
SEED_TAG = "scope-v1|20260927"
GT = "results/iter_010/manifests/gt_manifest.json"
MAN = "results/iter_010/manifests/infer_manifest.jsonl"
SIZES = {"D36": ("validation", 12), "E180": ("confirm", 60), "E600": ("confirm", 200)}


def order_key(category, patient):
    return hashlib.sha256(f"{SEED_TAG}|{category}|{patient}".encode()).hexdigest()


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def audit(gt):
    """gt_manifest의 validation/confirm 항목을 원본 annotation의 Calculated label·bbox와 SOP 단위로 대조한다. returns (report, problems)."""
    prov = json.load(open(ANN + ".provenance.json"))
    cur = sha_file(ANN)
    _, ann = R.load_annotations(ANN)
    probs, n, per_cat = [], 0, {}
    for i, g in gt.items():
        if g["split"] not in ("validation", "confirm"):
            continue
        n += 1
        a = ann.get(g["sop"])
        if a is None:
            probs.append((i, "sop_not_in_annotations"))
            continue
        cats = sorted(a["cats"])
        if cats != [g["category"]]:
            probs.append((i, f"category {g['category']} != Calculated {cats}"))
        if a["exclude"]:
            probs.append((i, "exclude_label"))
        if len(a["boxes"]) != len(g["boxes"]):
            probs.append((i, f"n_boxes {len(g['boxes'])} != {len(a['boxes'])}"))
        if g["category"] != "opacity" and (a["boxes"] or g["boxes"]):
            probs.append((i, "negative_with_box"))
        if g["category"] == "opacity" and not g["boxes"]:
            probs.append((i, "opacity_without_box"))
        k = (g["split"], g["category"])
        per_cat[f"{k[0]}/{k[1]}"] = per_cat.get(f"{k[0]}/{k[1]}", 0) + 1
    return {"annotation_sha256": cur, "provenance_sha256": prov.get("sha256"), "annotation_hash_match": cur == prov.get("sha256"),
            "n_checked": n, "n_problems": len(probs), "per_split_category": per_cat,
            "note": "NoOpacity/NotNormal(Calculated 'No Lung Opacity / Not Normal')과 Normal은 별도 category로 유지된다. NIH label로 정답을 대체하지 않는다."}, probs


def ranked(gt, split):
    by = {c: [] for c in S.CATEGORIES}
    for i, g in gt.items():
        if g["split"] == split:
            by[g["category"]].append(i)
    return {c: sorted(v, key=lambda i: order_key(c, gt[i]["patient"])) for c, v in by.items()}


def build(gt, man):
    val, conf = ranked(gt, "validation"), ranked(gt, "confirm")
    sets = {}
    for name, (split, n) in SIZES.items():
        pool = val if split == "validation" else conf
        sets[name] = {c: pool[c][:n] for c in S.CATEGORIES}
    sets["P60"] = {c: sets["E180"][c][:20] for c in S.CATEGORIES}
    sets["P180"] = {c: sets["E600"][c][:60] for c in S.CATEGORIES}
    sets["D12"] = {c: sets["D36"][c][:4] for c in S.CATEGORIES}
    return sets


def checks(sets, gt, man):
    """중복·교집합·pixel hash 충돌 검사. 문제가 있으면 예외."""
    flat = lambda s: [i for c in S.CATEGORIES for i in sets[s][c]]
    out = {}
    for s in sets:
        ids = flat(s)
        assert len(ids) == len(set(ids)), f"duplicate ids in {s}"
        out[s] = len(ids)
    assert set(flat("E180")) <= set(flat("E600")) and set(flat("P60")) <= set(flat("P180")) and set(flat("P60")) <= set(flat("E180"))
    assert set(flat("P180")) == set(flat("E180"))
    assert not set(flat("D36")) & set(flat("E600")), "D36/E overlap"
    mid = {m["id"]: m for m in man}
    pd, pe = {gt[i]["patient"] for i in flat("D36")}, {gt[i]["patient"] for i in flat("E600")}
    assert not pd & pe, "patient overlap D36/E600"
    ph = {mid[i]["pixel_sha256"] for i in flat("D36")} & {mid[i]["pixel_sha256"] for i in flat("E600")}
    assert not ph, "pixel hash overlap D36/E600"
    assert len({mid[i]["pixel_sha256"] for i in flat("E600")}) == len(flat("E600")), "duplicate pixel within E600"
    assert len({gt[i]["patient"] for i in flat("E600")}) == len(flat("E600")), "duplicate patient within E600"
    for s in ("D36", "E180", "E600"):
        for c in S.CATEGORIES:
            assert all(gt[i]["category"] == c and gt[i]["split"] == SIZES[s][0] for i in sets[s][c]), f"{s}/{c} mapping"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    gt = json.load(open(GT))
    man = [json.loads(ln) for ln in open(MAN) if ln.strip()]
    rep, probs = audit(gt)
    rep["problems_head"] = probs[:10]
    sets = build(gt, man)
    rep["set_sizes"] = checks(sets, gt, man)
    rep["order"] = f"sha256({SEED_TAG}|category|patient)"
    json.dump(rep, open(f"{a.out}/audit.json", "w"), indent=1)
    if probs or not rep["annotation_hash_match"]:
        raise SystemExit(f"audit failed: {len(probs)} problems; see {a.out}/audit.json")
    json.dump(sets, open(f"{a.out}/sets.json", "w"), indent=1)
    # 일반 inference manifest: 정답·category 없음. label 파일은 평가에서만 읽는다.
    mid = {m["id"]: m for m in man}
    used = sorted({i for s in ("D36", "E600") for c in S.CATEGORIES for i in sets[s][c]})
    with open(f"{a.out}/infer_manifest.jsonl", "w") as f:
        for i in used:
            m = mid[i]
            f.write(json.dumps({k: m[k] for k in ("id", "split", "image", "file_sha256", "pixel_sha256")}) + "\n")
    json.dump({i: {"category": gt[i]["category"], "patient": gt[i]["patient"], "boxes": gt[i]["boxes"]} for i in used},
              open(f"{a.out}/labels.json", "w"))
    print(json.dumps(rep["set_sizes"]), "audit ok")


if __name__ == "__main__":
    main()
