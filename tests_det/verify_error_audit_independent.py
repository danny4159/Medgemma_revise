"""det_error_audit 주수치의 독립 재계산: 원시 raw_preds/SFT 응답에서 자체 IoU·itertools 열거 matching으로
범주 수와 R을 다시 구해 results/iter_036/full/analysis.json과 대조한다 (det17/29 x sft17, IoU0.3)."""
import itertools
import json
import sys

BASE = "/SSD1_1TB/home/milab/daniel/08_medgemma/research"
sys.path.insert(0, BASE)
from rsna_diag import det_compare as DC, det_lib as D, geometry as G, sft_eval as SE  # noqa: E402


def iou(a, b):
    ih = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iw = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ih * iw
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u > 0 else 0.0


def hits(pred, gt, thr):
    cands = [[p for p in range(len(pred)) if iou(pred[p], g) >= thr] + [None] for g in gt]
    best, bk = set(), None
    for combo in itertools.product(*cands):
        used = [c for c in combo if c is not None]
        if len(used) != len(set(used)):
            continue
        k = (len(used), sum(iou(pred[c], gt[gi]) for gi, c in enumerate(combo) if c is not None))
        if bk is None or k[0] > bk[0] or (k[0] == bk[0] and k[1] > bk[1] + 1e-12):
            bk, best = k, {gi for gi, c in enumerate(combo) if c is not None}
    return best


def main():
    gt, infer = D.load_gt_infer()
    ids = json.load(open(f"{BASE}/results/iter_010/manifests/confirm_ids.json"))
    pos = [i for i in ids if gt[i]["category"] == "opacity"]
    recs, _ = DC.load_stored(f"{DC.IT012}/confirm_sft_seed17", ids, ("concise",), DC.ADAPTERS[17], infer)
    sft = SE.parse_records(recs, ids, "concise", strict=True)
    saved = json.load(open(f"{BASE}/results/iter_036/full/analysis.json"))
    out = {}
    for dseed, sel, cdir in ((17, "seed17", "det17"), (29, "seed29", "det29")):
        thr = json.load(open(f"{BASE}/results/iter_035/select/{sel}/v400_selection.json"))["selected"]["threshold"]
        raw = json.load(open(f"{BASE}/results/iter_035/confirm800/{cdir}/raw_preds.json"))
        cnt = {"matching_competition": 0, "threshold_excluded": 0, "adjacent_localization_error": 0, "no_stored_candidate_coverage": 0}
        r_num = 0
        for i in pos:
            g = [b["yxyx_norm"] for b in gt[i]["boxes"]]
            r = raw[i]
            top, left, side = G.pad_offsets(*r["img_hw"])
            allc = [(G.canvas_to_norm(b, top, left, side), s) for b, s, l in zip(r["boxes_xyxy_px"], r["scores"], r["labels"]) if l == 1]
            selb = [b for b, s in allc if s >= thr]
            sb = sft[i]["boxes"] if sft[i]["status"] in ("valid_nonempty", "valid_empty") else []
            dh, sh = hits(selb, g, 0.3), hits(sb, g, 0.3)
            for gi in range(len(g)):
                if gi in sh and gi not in dh:
                    if any(iou(b, g[gi]) >= 0.3 for b in selb):
                        c = "matching_competition"
                    else:
                        m = max((iou(b, g[gi]) for b, _ in allc), default=0.0)
                        c = "threshold_excluded" if m >= 0.3 else "adjacent_localization_error" if m >= 0.1 else "no_stored_candidate_coverage"
                    cnt[c] += 1
                    r_num += c in ("adjacent_localization_error", "no_stored_candidate_coverage")
        s = saved["decomposition"][f"det{dseed}_vs_sft17_iou0.3"]["category_counts"]
        out[f"det{dseed}"] = {"independent": cnt, "saved": s, "match": cnt == s, "r_num": r_num,
                              "r_saved": saved["r_and_threshold_excluded"][f"det{dseed}_vs_sft17"]["r_numerator"]}
        out[f"det{dseed}"]["match"] = out[f"det{dseed}"]["match"] and r_num == out[f"det{dseed}"]["r_saved"]
    out["pass"] = all(v["match"] for v in out.values() if isinstance(v, dict))
    json.dump(out, open(f"{BASE}/results/iter_036/full/independent_verify.json", "w"), indent=1)
    print(json.dumps(out, indent=1))
    sys.exit(0 if out["pass"] else 1)


if __name__ == "__main__":
    main()
