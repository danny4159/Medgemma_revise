"""iter_040 사전 분할·잠금 (CPU only, 모델 미사용). 결과: results/iter_040/{data,requests}/ (Git 제외, private).

- 학습 T305: iter_039 train pool(922명 규칙 재현)에서 D24·E288 환자를 제외한 나머지의 층별 비례 절반(seed 20260930).
- 평가: V96 = 기존 E96(개발 자료), V48 = V96의 층별 비례 절반(LR·checkpoint 선택용), H192 = 기존 E192 (조건부 pilot 평가, 요청은 decision 뒤에만 생성).
- F120·test는 사용하지 않는다. iter_039 결과·이미지는 읽기만 하고 새 경로에만 쓴다.
- 영상 변환 규약은 iter_039와 동일 (pg39_build.extract).
"""
import hashlib
import json
import os
import sys
from collections import Counter

import pg39_build as B39
import pg39_data as D
import pg39_spec as S
from rsna_diag import generate as G
from rsna_diag import geometry, metrics

OUT = "results/iter_040"
M39 = "results/iter_039/data/manifest_private.jsonl"
REQ39 = "results/iter_039/requests_v2/requests_{}.jsonl"
SEED = D.SEED


def sha_file(p):
    return D.sha256_file(p)


def load_m39():
    return [json.loads(l) for l in open(M39)]


def v48_split(e96_rows):
    """V96의 층별 비례 절반. 층 내 순서는 sha256(seed|V48|PatientID). returns set(PatientID)."""
    by = {}
    for r in e96_rows:
        by.setdefault(r["stratum"], []).append(r)
    sizes = {k: len(v) for k, v in by.items()}
    q = D.apportion(sizes, len(e96_rows) // 2)
    keep = set()
    for k, v in by.items():
        v.sort(key=lambda r: D.h(SEED, "V48", r["PatientID"]))
        keep |= {r["PatientID"] for r in v[:q[k]]}
    return keep, q


def contrast_eligible(gtA_canvas, gtB_canvas):
    return metrics_cross(gtA_canvas, gtB_canvas) < 0.1


def metrics_cross(a, b):
    return S.cross_iou_max(a, b)


def build_train(reports, links, z, idx, m39):
    banned = {r["PatientID"] for r in m39 if r["set"] in ("D", "E")}
    pool, excl = D.image_pool(reports, links, "train")
    n_pool = len(pool)
    pool = [c for c in pool if c["ImageID"] in idx]
    n_zip_ok = len(pool)
    rem = [c for c in pool if c["PatientID"] not in banned]
    old_pix = {r["image_meta"]["u16_pixel_sha256"]: r["PatientID"] for r in m39}
    img_dir = f"{OUT}/data/images"
    os.makedirs(img_dir, exist_ok=True)
    metas, extra_banned = {}, set()
    for _ in range(50):
        sel = D.select(rem, "train", [("T", 305)], extra_banned)["T"]
        seen, dup = {}, False
        for c in sel["chosen"]:
            iid = c["ImageID"]
            if iid not in metas:
                metas[iid] = B39.extract(z, idx, iid, img_dir)
            key = metas[iid]["u16_pixel_sha256"]
            if (key in old_pix and old_pix[key] != c["PatientID"]) or (key in seen and seen[key] != c["PatientID"]):
                extra_banned.add(c["PatientID"])
                dup = True
            seen.setdefault(key, c["PatientID"])
        if not dup:
            break
    else:
        sys.exit("could not resolve duplicate pixel hashes")
    return sel, metas, {"n_pool": n_pool, "n_pool_in_zip": n_zip_ok, "n_remaining_after_D_E": len(rem),
                        "pixel_dup_extra_banned": len(extra_banned), "exclusion_counts": excl}


def train_rows(sel, metas, rep_by_img):
    rows = []
    for c in sel["chosen"]:
        r = rep_by_img[c["ImageID"]]
        ids = D.assign_ids(c["ImageID"], c["i"], c["j"])
        meta = metas[c["ImageID"]]
        fs = {k: r["findings"][v] for k, v in ids.items()}
        top, left, side = geometry.pad_offsets(meta["h"], meta["w"])
        gt = {k: S.gt_to_canvas(f["boxes"], meta["h"], meta["w"]) for k, f in fs.items()}
        rows.append({"set": "T", "subset": "T305", "split": "train", "PatientID": c["PatientID"], "ImageID": c["ImageID"],
                     "StudyID": c["StudyID"], "stratum": D.stratum(c), "image_meta": meta, "pad_top_left_side": [top, left, side],
                     "finding_index": ids, "sentences": {k: f["sentence_en"] for k, f in fs.items()},
                     "gt_boxes_xyxy_norm": {k: f["boxes"] for k, f in fs.items()},
                     "gt_canvas_yxyx": gt, "labels": {k: f["labels"] for k, f in fs.items()},
                     "cross_iou_max": S.cross_iou_max(gt["qA"], gt["qB"]),
                     "contrast_eligible": S.cross_iou_max(gt["qA"], gt["qB"]) < 0.1})
    return rows


def main():
    if os.path.exists(f"{OUT}/data/selection_lock.json"):
        sys.exit("selection_lock.json exists: refuse to rebuild (new attempt path required)")
    m39 = load_m39()
    reports, m, links = D.load_inputs()
    rep_by_img = {r["ImageID"]: r for r in reports}
    z = D.open_image_zip()
    idx = D.zip_index(z)
    sel, metas, info = build_train(reports, links, z, idx, m39)
    trows = train_rows(sel, metas, rep_by_img)
    # 평가 manifest (iter_039 행 그대로, subset 표기만 추가)
    e96 = [r for r in m39 if r["subset"] == "E96"]
    v48_ids, v48_q = v48_split(e96)
    erows = []
    for r in m39:
        if r["subset"] in ("E96", "E192"):
            rr = dict(r)
            rr["eval_set"] = "V96" if r["subset"] == "E96" else "H192"
            rr["is_V48"] = r["PatientID"] in v48_ids
            erows.append(rr)
    os.makedirs(f"{OUT}/data", exist_ok=True)
    tp, ep = f"{OUT}/data/manifest_train_private.jsonl", f"{OUT}/data/manifest_eval_private.jsonl"
    with open(tp, "w") as f:
        for r in trows:
            f.write(json.dumps(r) + "\n")
    with open(ep, "w") as f:
        for r in erows:
            f.write(json.dumps(r) + "\n")
    # 분리 검사: 환자·영상·pixel hash
    def keyset(rows, fn):
        return {fn(r) for r in rows}
    all_sets = {"T305": trows, "V96": [r for r in erows if r["eval_set"] == "V96"], "H192": [r for r in erows if r["eval_set"] == "H192"],
                "D24": [r for r in m39 if r["subset"] == "D"], "F120": [r for r in m39 if r["subset"] == "F"]}
    sep = {}
    names = list(all_sets)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            sep[f"{a}&{b}"] = {"patient": len(keyset(all_sets[a], lambda r: r["PatientID"]) & keyset(all_sets[b], lambda r: r["PatientID"])),
                               "image": len(keyset(all_sets[a], lambda r: r["ImageID"]) & keyset(all_sets[b], lambda r: r["ImageID"])),
                               "u16_pixel": len(keyset(all_sets[a], lambda r: r["image_meta"]["u16_pixel_sha256"]) &
                                                keyset(all_sets[b], lambda r: r["image_meta"]["u16_pixel_sha256"])),
                               "study": len(keyset(all_sets[a], lambda r: r["StudyID"]) & keyset(all_sets[b], lambda r: r["StudyID"]))}
    within = {a: {"n": len(v), "unique_patient": len(keyset(v, lambda r: r["PatientID"])),
                  "unique_u16_pixel": len(keyset(v, lambda r: r["image_meta"]["u16_pixel_sha256"]))} for a, v in all_sets.items()}
    # 대조 적용 범위
    el = [r["contrast_eligible"] for r in trows]
    dist = {"n_eligible": int(sum(el)), "n": len(trows),
            "by_stratum": {s: {"n": sum(1 for r in trows if r["stratum"] == s), "eligible": sum(1 for r in trows if r["stratum"] == s and r["contrast_eligible"])}
                           for s in sorted({r["stratum"] for r in trows})},
            "n_boxes_pair_eligible": dict(Counter(sum(len(r["gt_canvas_yxyx"][k]) for k in ("qA", "qB")) for r in trows if r["contrast_eligible"])),
            "n_boxes_pair_all": dict(Counter(sum(len(r["gt_canvas_yxyx"][k]) for k in ("qA", "qB")) for r in trows))}
    # 문장 사전 규칙 검사 (눈가림 수동 검토는 수행하지 않았다: 규칙 기반 점검만)
    sent_audit = {"n_sentences": 2 * len(trows), "non_ascii": sum(not s.isascii() for r in trows for s in r["sentences"].values()),
                  "len_chars_min_max": [min(len(s) for r in trows for s in r["sentences"].values()),
                                        max(len(s) for r in trows for s in r["sentences"].values())],
                  "temporal_re_matches": sum(bool(D.TEMPORAL_RE.search(s)) for r in trows for s in r["sentences"].values()),
                  "identical_sentence_pairs": sum(r["sentences"]["qA"].strip().lower() == r["sentences"]["qB"].strip().lower() for r in trows)}
    summ = {"spec": dict(D.SPEC, T="T305: D.select(train pool minus D24/E288 patients, ('T',305)) largest-remainder proportional per stratum"),
            "train_pool": info, "T_quota": sel["quota"], "T_stratum_before": sel["stratum_sizes_before"],
            "T_n": len(trows), "V96_n": len(all_sets["V96"]), "V48_n": sum(r["is_V48"] for r in all_sets["V96"]), "V48_quota": v48_q,
            "H192_n": len(all_sets["H192"]), "separation": sep, "within": within, "contrast_eligibility": dist, "sentence_rule_audit": sent_audit,
            "manifest_train_sha256": sha_file(tp), "manifest_eval_sha256": sha_file(ep), "iter039_manifest_sha256": sha_file(M39),
            "raw_inputs_sha256": links["inputs_sha256"],
            "convention": B39.CONVENTION, "note": "F120/test unused; H192 requests are generated only after a decision artifact"}
    json.dump(summ, open(f"{OUT}/data/selection_summary.json", "w"), indent=1)
    json.dump({"manifest_train_sha256": summ["manifest_train_sha256"], "manifest_eval_sha256": summ["manifest_eval_sha256"],
               "iter039_manifest_sha256": summ["iter039_manifest_sha256"]}, open(f"{OUT}/data/selection_lock.json", "w"), indent=1)
    print(json.dumps({k: summ[k] for k in ("T_n", "V96_n", "V48_n", "H192_n", "train_pool", "separation", "within", "contrast_eligibility",
                                            "sentence_rule_audit")}, indent=1)[:5000])


if __name__ == "__main__":
    main()
