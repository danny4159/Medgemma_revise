"""생성 결과 평가 (iter_009): parse -> 환자별 metric -> 주지표(공통 위치 불일치) -> baseline -> paired bootstrap.

사용: python -m rsna_diag.evaluate --gen "results/iter_009/dev/run/gen_shard*.jsonl" --split development --out results/iter_009/dev/eval
      python -m rsna_diag.evaluate --gen "..." --split independent_eval --out ... --prior-from-dev
"""
import argparse
import collections
import glob
import json
import os

import numpy as np

from . import metrics as M, overlay, parse as PA

PROMPTS = ["official_long", "concise", "legacy_detect"]
NORMAL_PROMPTS = ["official_long", "concise"]
SEED = 20260924
HARD_IOU = 0.3
GT_CAT_NAMES = {"opacity": "positive", "normal": "Normal", "not_normal_no_opacity": "NoOpacity/NotNormal"}


def load_gen(pattern):
    recs = {}
    files = [f for pat in pattern.split(",") for f in sorted(glob.glob(pat))]
    for f in files:
        if f.endswith((".env.json", ".log")):
            continue
        for ln in open(f):
            if ln.strip():
                r = json.loads(ln)
                k = (r["id"], r["prompt_name"])
                if k in recs:
                    raise ValueError(f"duplicate generation record {k} in {f} (already loaded from {recs[k].get('_file')})")
                r["_file"] = f
                recs[k] = r
    return recs


def gt_boxes(g):
    return [b["yxyx_norm"] for b in g["boxes"]]


def rate(k, n):
    lo, hi = M.wilson(k, n)
    return {"k": k, "n": n, "rate": (k / n if n else None), "wilson95": [lo, hi]}


def evaluate(recs, gt, split, prior_box=None, B=10000):
    ids = sorted(i for i, g in gt.items() if g["split"] == split)
    pos = [i for i in ids if gt[i]["category"] == "opacity"]
    out = {"split": split, "n_patients": len(ids), "n_positive": len(pos), "prompts": {}, "missing_requests": []}
    parsed = {}
    for i in ids:
        for p in PROMPTS:
            r = recs.get((i, p))
            if r is None:
                out["missing_requests"].append([i, p])
                parsed[(i, p)] = {"status": "missing", "boxes": [], "flags": [], "problems": []}
            else:
                parsed[(i, p)] = PA.parse_response(r["suffix_text_raw"], r["ended_eos"])
    per = {}
    for p in PROMPTS:
        st_all = collections.Counter(parsed[(i, p)]["status"] for i in ids)
        st_pos = collections.Counter(parsed[(i, p)]["status"] for i in pos)
        valid = lambda i: parsed[(i, p)]["status"] in PA.VALID
        d = {"status_all": dict(st_all), "status_positive": dict(st_pos),
             "valid_rate_positive": rate(sum(valid(i) for i in pos), len(pos)),
             "valid_rate_all": rate(sum(valid(i) for i in ids), len(ids))}
        for thr in (0.3, 0.5):
            f1s, recs_, precs = [], [], []
            for i in pos:
                pb = parsed[(i, p)]["boxes"] if valid(i) else []
                m = M.patient_metrics(pb, gt_boxes(gt[i]), thr)
                f1s.append(m["f1"]); recs_.append(m["recall"]); precs.append(m["precision"])
            d[f"f1@{thr}_end_to_end"] = float(np.mean(f1s)) if f1s else None
            d[f"recall@{thr}_end_to_end"] = float(np.mean(recs_)) if recs_ else None
            d[f"precision@{thr}_end_to_end"] = float(np.mean(precs)) if precs else None
            vi = [k for k, i in enumerate(pos) if valid(i)]
            d[f"f1@{thr}_valid_only"] = {"mean": float(np.mean([f1s[k] for k in vi])) if vi else None, "n": len(vi)}
            per[(p, f"f1@{thr}")] = np.array(f1s)
        uis = [M.union_iou(parsed[(i, p)]["boxes"] if valid(i) else [], gt_boxes(gt[i])) for i in pos]
        d["union_iou_end_to_end"] = float(np.mean(uis)) if uis else None
        per[(p, "union_iou")] = np.array(uis)
        vne = [i for i in pos if parsed[(i, p)]["status"] == "valid_nonempty"]
        hard = [i for i in vne if M.max_iou_all(parsed[(i, p)]["boxes"], gt_boxes(gt[i])) < HARD_IOU]
        d["hard_mismatch"] = {"k": len(hard), "n_positive": len(pos), "n_valid_nonempty": len(vne),
                              "rate_over_positives": rate(len(hard), len(pos)),
                              "rate_over_valid_nonempty": rate(len(hard), len(vne)), "ids": hard}
        d["positive_valid_empty"] = rate(st_pos.get("valid_empty", 0), len(pos))
        d["positive_n_pred_dist"] = dict(collections.Counter(len(parsed[(i, p)]["boxes"]) for i in vne))
        # 음성 층
        for cat, nm in (("normal", "Normal"), ("not_normal_no_opacity", "NoOpacity/NotNormal")):
            neg = [i for i in ids if gt[i]["category"] == cat]
            d[f"neg_{nm}"] = {"valid_empty": rate(sum(parsed[(i, p)]["status"] == "valid_empty" for i in neg), len(neg)),
                              "valid_nonempty": rate(sum(parsed[(i, p)]["status"] == "valid_nonempty" for i in neg), len(neg)),
                              "format_fail": rate(sum(parsed[(i, p)]["status"] not in PA.VALID for i in neg), len(neg))}
        d["flags_all"] = dict(collections.Counter(f for i in ids for f in parsed[(i, p)]["flags"]))
        d["duplicate_boxes_total"] = int(sum(PA.duplicates([b for b in parsed[(i, p)]["boxes"] if b]) for i in ids))
        gen_recs = [recs[(i, p)] for i in ids if (i, p) in recs]
        d["generation"] = {"n_requests": len(gen_recs),
                           "n_cap_extended": sum(1 for r in gen_recs if len(r["attempts"]) > 1),
                           "n_final_cap_1000_2000_4000": [sum(1 for r in gen_recs if r["final_cap"] == c) for c in (1000, 2000, 4000)],
                           "mean_out_tokens": float(np.mean([r["n_output_tokens"] for r in gen_recs])) if gen_recs else None,
                           "max_out_tokens": max((r["n_output_tokens"] for r in gen_recs), default=None),
                           "mean_runtime_s": float(np.mean([r["runtime_s_total"] for r in gen_recs])) if gen_recs else None,
                           "peak_mem_gb_max": max((r["peak_mem_alloc_gb_max"] for r in gen_recs), default=None),
                           "prefix_mismatch_across_caps": sum(1 for r in gen_recs for a in r["attempts"] if a.get("prefix_matches_previous") is False)}
        out["prompts"][p] = d
    # 주지표: 두 정상 prompt 공통 위치 불일치
    common = [i for i in pos if all(i in out["prompts"][p]["hard_mismatch"]["ids"] for p in NORMAL_PROMPTS)]
    valid95 = {p: {"positive": out["prompts"][p]["valid_rate_positive"]["rate"], "all": out["prompts"][p]["valid_rate_all"]["rate"]}
               for p in NORMAL_PROMPTS}
    lo, hi = M.wilson(len(common), len(pos))
    out["primary"] = {"definition": "양성 환자 중 official_long과 concise 모두 유효·비어있지 않은 출력이고 모든 예측-GT IoU < 0.3",
                      "common_hard_mismatch": {"k": len(common), "n": len(pos), "rate": len(common) / len(pos) if pos else None,
                                               "wilson95": [lo, hi]}, "common_ids": common,
                      "valid_output_rate_normal_prompts": valid95,
                      "criterion_valid_ge_95pct_both_prompts_positive_and_all": all(v["positive"] >= .95 and v["all"] >= .95 for v in valid95.values()),
                      "criterion_wilson_lower_gt_20pct": bool(lo > 0.20)}
    prim = out["primary"]
    if prim["criterion_valid_ge_95pct_both_prompts_positive_and_all"]:
        prim["verdict"] = ("supported" if prim["criterion_wilson_lower_gt_20pct"] else
                           ("not_supported" if hi <= 0.20 else "inconclusive"))
    else:
        prim["verdict"] = "not_evaluable_valid_output_rate_below_95pct"
    # baselines
    base = {}
    if prior_box is not None:
        for thr in (0.3, 0.5):
            base[f"prior_f1@{thr}"] = float(np.mean([M.patient_metrics([prior_box], gt_boxes(gt[i]), thr)["f1"] for i in pos]))
        pf = np.array([M.patient_metrics([prior_box], gt_boxes(gt[i]), 0.3)["f1"] for i in pos])
        per[("prior", "f1@0.3")] = pf
        per[("prior", "union_iou")] = np.array([M.union_iou([prior_box], gt_boxes(gt[i])) for i in pos])
        base["prior_box"] = prior_box
        base["prior_union_iou"] = float(per[("prior", "union_iou")].mean())
        base["prior_hard_mismatch_rate"] = float(np.mean([M.max_iou_all([prior_box], gt_boxes(gt[i])) < HARD_IOU for i in pos]))
    swap = {}
    for k, p in enumerate(PROMPTS):
        perm = M.derangement(len(pos), SEED + 100 + k)
        f1, hard, uis = [], 0, []
        for a, i in enumerate(pos):
            donor = pos[perm[a]]
            pr = parsed[(donor, p)]
            pb = pr["boxes"] if pr["status"] in PA.VALID else []
            f1.append(M.patient_metrics(pb, gt_boxes(gt[i]), 0.3)["f1"])
            uis.append(M.union_iou(pb, gt_boxes(gt[i])))
            hard += int(pr["status"] == "valid_nonempty" and M.max_iou_all(pb, gt_boxes(gt[i])) < HARD_IOU)
        per[(f"swap_{p}", "f1@0.3")] = np.array(f1)
        per[(f"swap_{p}", "union_iou")] = np.array(uis)
        swap[p] = {"f1@0.3": float(np.mean(f1)), "union_iou": float(np.mean(uis)), "hard_mismatch_rate_over_positives": hard / len(pos),
                   "permutation_seed": SEED + 100 + k, "scope": "within positives (donor = 다른 양성 환자의 전체 예측)"}
        # 전체 집단 derangement: 음성 추가 예측률 비교용
        permA = M.derangement(len(ids), SEED + 200 + k)
        ne = {}
        for cat, nm in (("normal", "Normal"), ("not_normal_no_opacity", "NoOpacity/NotNormal")):
            idx = [a for a, i in enumerate(ids) if gt[i]["category"] == cat]
            ne[nm] = float(np.mean([parsed[(ids[permA[a]], p)]["status"] == "valid_nonempty" for a in idx]))
        swap[p]["whole_population_negative_valid_nonempty_rate"] = ne
    base["image_swap"] = swap
    out["baselines"] = base
    # paired bootstrap (양성 환자 단위)
    idx = M.bootstrap_indices(len(pos), B, SEED)
    comps = [("official_long", "concise", "f1@0.3"), ("official_long", "legacy_detect", "f1@0.3"), ("concise", "legacy_detect", "f1@0.3")]
    for p in NORMAL_PROMPTS:
        comps += [(p, "prior", "f1@0.3"), (p, f"swap_{p}", "f1@0.3")]
    for p in PROMPTS:
        comps += [(p, "prior", "f1@0.3")] if p not in NORMAL_PROMPTS else []
    boot = {}
    for a, b, met in comps:
        if (a, met) in per and (b, met) in per:
            m, lo_, hi_ = M.paired_boot_ci(per[(a, met)], per[(b, met)], idx)
            boot[f"{a} - {b} [{met}]"] = {"mean_diff": m, "ci95": [lo_, hi_]}
    out["paired_bootstrap"] = {"B": B, "seed": SEED, "unit": "positive patient", "diffs": boot}
    return out, parsed, idx, pos


def size_stats(parsed, gt, pos):
    """위치 불일치의 크기/위치 분포 (기술 통계)."""
    rows = []
    for i in pos:
        g = gt_boxes(gt[i])
        garea = M.union_area(g)
        row = {"id": i, "n_gt": len(g), "gt_union_area_frac": garea / 1e6}
        for p in PROMPTS:
            pr = parsed[(i, p)]
            pb = pr["boxes"] if pr["status"] in PA.VALID else []
            row[p] = {"status": pr["status"], "n_pred": len(pb), "pred_union_area_frac": M.union_area(pb) / 1e6 if pb else 0.0,
                      "max_iou": M.max_iou_all(pb, g) if pb else 0.0}
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", required=True)
    ap.add_argument("--split", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--gt", default="results/iter_010/manifests/gt_manifest.json")
    ap.add_argument("--images-dir", default="results/iter_010/data/images")
    ap.add_argument("--B", type=int, default=10000)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    gt = json.load(open(a.gt))
    recs = load_gen(a.gen)
    dev_pos = [gt_boxes(g) for i, g in sorted(gt.items()) if g["split"] == "train" and g["category"] == "opacity"]
    prior_box, prior_score = M.medoid_box(dev_pos)
    res, parsed, idx, pos = evaluate(recs, gt, a.split, prior_box, a.B)
    res["baselines"]["prior_selection_mean_best_iou_on_dev_positives"] = prior_score
    json.dump(res, open(f"{a.out}/metrics.json", "w"), indent=1)
    np.savez_compressed(f"{a.out}/bootstrap_indices.npz", idx=idx, positive_ids=np.array(pos))
    json.dump(size_stats(parsed, gt, pos), open(f"{a.out}/positive_case_table.json", "w"), indent=1)
    # 사례: 공통 오류/성공 최대 20명씩 (고정 ID 순서)
    ok = [i for i in pos if all(parsed[(i, p)]["status"] == "valid_nonempty" and M.max_iou_all(parsed[(i, p)]["boxes"], gt_boxes(gt[i])) >= 0.5
                                for p in NORMAL_PROMPTS)]
    cases = {"common_error": res["primary"]["common_ids"][:20], "success_iou_ge_0.5_both": ok[:20]}
    os.makedirs(f"{a.out}/cases", exist_ok=True)
    detail = {}
    for kind, lst in cases.items():
        for i in lst:
            g = gt[i]
            ims = []
            for p in NORMAL_PROMPTS:
                pb = [b for b in parsed[(i, p)]["boxes"] if b]
                ims.append(overlay.draw(f"{a.images_dir}/{g['sop']}.png", gt_boxes(g), pb, 512, f"{i} {p}"))
            overlay.montage(ims, 2).save(f"{a.out}/cases/{kind}_{i}.png")
            detail[f"{kind}/{i}"] = {"gt": gt_boxes(g), **{p: {"status": parsed[(i, p)]["status"], "boxes": parsed[(i, p)]["boxes"],
                                                            "response": recs[(i, p)]["suffix_text_raw"] if (i, p) in recs else None} for p in NORMAL_PROMPTS}}
    json.dump(detail, open(f"{a.out}/case_details.json", "w"), indent=1)
    pm = res["primary"]
    print(json.dumps({"split": a.split, "n_pos": res["n_positive"], "missing": len(res["missing_requests"]), "primary": {k: pm[k] for k in pm if k != "common_ids"}}, indent=1))
    for p in PROMPTS:
        d = res["prompts"][p]
        print(p, "valid_pos", round(d["valid_rate_positive"]["rate"], 3), "f1@.3", round(d["f1@0.3_end_to_end"], 3), "f1@.5", round(d["f1@0.5_end_to_end"], 3),
              "hard/pos", d["hard_mismatch"]["k"], "/", d["hard_mismatch"]["n_positive"], "status_pos", d["status_positive"])
    print("prior f1@.3", res["baselines"].get("prior_f1@0.3"), "swap", {p: round(v["f1@0.3"], 3) for p, v in res["baselines"]["image_swap"].items()})


if __name__ == "__main__":
    main()
