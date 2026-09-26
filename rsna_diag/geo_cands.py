"""iter_014 후보(pseudo-box) manifest. 사용: python -m rsna_diag.geo_cands --out-dir results/iter_014/candidates

train 2,400 전체의 양성 환자 GT box(sft_data.target_boxes의 정렬 순서 = 학습 target의 box index)마다 4개 후보를 결정적으로 만들고
확보율·GIoU·변위·면적비·token 길이 분포를 GT box 크기 삼분위(train 기준)별로 보고한다. 4개를 못 얻으면 준비 gate 중단.
U/G가 같은 manifest를 쓴다 (환자 ID·box index·고정 seed로 RNG).
"""
import argparse
import hashlib
import json
import os

import numpy as np

from . import coord_loss as CL, geo_loss as GL, sft_data

GT = "results/iter_010/manifests/gt_manifest.json"
TRAIN_IDS = "results/iter_010/manifests/train_ids.json"


def build(gt, ids, tok=None):
    man, fails, stats = {}, [], []
    for pid in ids:
        if gt[pid]["category"] != "opacity":
            continue
        boxes = sft_data.target_boxes([b["yxyx_norm"] for b in gt[pid]["boxes"]])
        ent = []
        for b, gb in enumerate(boxes):
            try:
                cands, n = GL.gen_candidates(pid, b, gb)
            except GL.GeoError as e:
                fails.append({"id": pid, "box": b, "gt": gb, "error": str(e)})
                continue
            recs = [GL.cand_record(gb, c) for c in cands]
            ent.append({"gt": gb, "cands": recs, "n_proposals": n})
            stats.append((pid, b, gb, n, recs))
        man[pid] = ent
    return man, fails, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    gt = json.load(open(GT))
    ids = sorted(json.load(open(TRAIN_IDS)))
    man, fails, stats = build(gt, ids)
    os.makedirs(a.out_dir, exist_ok=True)
    rep = {"seed_tag": GL.SEED_TAG, "k": GL.K_CAND, "giou_min": GL.GIOU_MIN, "shift_frac": GL.SHIFT_FRAC, "scale_range": GL.SCALE_RANGE,
           "max_proposals": GL.MAX_PROPOSALS, "grid": "1/1000 integer (R-VLM original: 1/100)", "n_patients": len(man), "n_boxes": len(stats), "n_failed_boxes": len(fails),
           "failed": fails}
    if fails:
        json.dump(rep, open(os.path.join(a.out_dir, "candidate_report_FAILED.json"), "w"), indent=1)
        raise SystemExit(f"candidate gate FAILED: {len(fails)} boxes lack {GL.K_CAND} candidates (see candidate_report_FAILED.json)")
    areas = np.array([(g[2] - g[0]) * (g[3] - g[1]) / 1e6 for _, _, g, _, _ in stats])
    edges = [float(np.quantile(areas, 1 / 3)), float(np.quantile(areas, 2 / 3))]
    tier = np.digitize(areas, edges)
    rep["box_area_tertile_edges"] = edges

    def dist(x):
        x = np.asarray(x, float)
        return {"mean": float(x.mean()), "min": float(x.min()), "q05": float(np.quantile(x, .05)), "median": float(np.median(x)), "q95": float(np.quantile(x, .95)), "max": float(x.max())}

    by = {}
    for t, name in enumerate(("small", "medium", "large")):
        sel = [s for s, k in zip(stats, tier) if k == t]
        by[name] = {"n_boxes": len(sel), "acceptance_rate": dist([4 / s[3] for s in sel]), "n_proposals": dist([s[3] for s in sel]),
                    "giou": dist([c["giou"] for s in sel for c in s[4]]), "area_ratio": dist([c["area_ratio"] for s in sel for c in s[4]]),
                    "disp_units": dist([c["disp"] for s in sel for c in s[4]]),
                    "r_weight": dist([1 + GL.GAMMA * np.log(c["giou"]) for s in sel for c in s[4]])}
    rep["by_gt_box_size"] = by
    # token 길이 (span n_bm vs n_b): tokenizer 필요
    from transformers import AutoTokenizer
    from . import generate
    tok = AutoTokenizer.from_pretrained("google/medgemma-1.5-4b-it", revision=generate.MODEL_REVISION)
    dig = CL.digit_ids(tok)
    lens = {"same": 0, "cand_longer": 0, "cand_shorter": 0}
    dl = []
    for pid in list(man)[:]:
        tgt = sft_data.target_text([b["yxyx_norm"] for b in gt[pid]["boxes"]])
        ids_, spans = GL.box_token_spans(tok, tgt, dig)
        for b, e in enumerate(man[pid]):
            assert e["gt"] == json.loads(tgt)[b]["box_2d"]
            nb = spans[b][1] - spans[b][0] + 1
            for c in e["cands"]:
                ctext = GL.replace_box_text(tgt, b, c["box"])
                cids, cs = GL.box_token_spans(tok, ctext, dig)
                nbm = cs[b][1] - cs[b][0] + 1
                dl.append(nbm - nb)
                lens["same" if nbm == nb else "cand_longer" if nbm > nb else "cand_shorter"] += 1
    rep["token_span_length"] = {"cand_vs_gt": lens, "delta_dist": dist(dl), "note": "n_bm - n_b (tokens, incl. bracket/whitespace tokens)"}
    blob = json.dumps(man, sort_keys=True)
    rep["manifest_sha256"] = hashlib.sha256(blob.encode()).hexdigest()
    json.dump(man, open(os.path.join(a.out_dir, "train_candidates.json"), "w"), sort_keys=True)
    json.dump(rep, open(os.path.join(a.out_dir, "candidate_report.json"), "w"), indent=1)
    print(json.dumps({k: rep[k] for k in ("n_patients", "n_boxes", "n_failed_boxes", "manifest_sha256")}), json.dumps(rep["token_span_length"]))
    for k, v in by.items():
        print(k, v["n_boxes"], "accept", v["acceptance_rate"]["mean"], "min-accept", v["acceptance_rate"]["min"], "giou", v["giou"]["median"])


if __name__ == "__main__":
    main()
