"""iter_010 비교 평가. 두 단계:

  comparator: validation(400)의 base 생성·보정·prior 중 양성 F1@0.3 최대인 단순 비교군 1개를 주 비교군으로 고정 (확인 결과를 보기 전에).
  confirm:    고정된 주 비교군과 SFT 3개 seed를 확인 800명에서 같은 metric으로 비교 (paired bootstrap 10,000회, seed 20260925).
사용: python -m rsna_diag.final_eval comparator --val-base DIR --out FILE
      python -m rsna_diag.final_eval confirm --comparator FILE --conf-base DIR --sft seed=DIR ... --out FILE
"""
import argparse
import json
import os

import numpy as np

from . import baselines as B, evaluate as EV, metrics as M, parse as PA, sft_eval

GT = "results/iter_010/manifests/gt_manifest.json"
BASE_JSON = "results/iter_010/baselines/baselines.json"
BOOT_SEED, BOOT_B = 20260925, 10000


def split_ids(gt, split):
    return sorted(i for i in gt if gt[i]["split"] == split)


def base_predictions(recs, ids, bl):
    """base 생성 record -> {이름: preds}. 보정은 prompt별 고정 변환 (실패 출력은 그대로)."""
    out = {}
    for p in ("official_long", "concise"):
        raw = sft_eval.parse_records(recs, ids, p)
        out[p] = raw
        spec = tuple(bl[p]["spec"])
        out[p + "+corr"] = {i: B.apply_pred(raw[i], spec)[0] for i in ids}
    return out


def prior_predictions(ids, bl):
    return {"prior_set": {i: {"status": "valid_nonempty", "boxes": bl["prior_set"]["set"]} for i in ids},
            "prior_single": {i: {"status": "valid_nonempty", "boxes": [bl["prior_single_box"]["box"]]} for i in ids}}


def all_simple(recs, ids, bl):
    d = base_predictions(recs, ids, bl)
    d.update(prior_predictions(ids, bl))
    return d


def cmd_comparator(a):
    gt = json.load(open(GT))
    bl = json.load(open(BASE_JSON))
    ids = split_ids(gt, "validation")
    recs = EV.load_gen(os.path.join(a.val_base, "gen_worker*.jsonl"))
    tr = [i for i in gt if gt[i]["split"] == "train"]
    edges = sft_eval.area_edges(gt, tr)
    preds = all_simple(recs, ids, bl)
    summ = {k: sft_eval.summarize(v, gt, ids, edges) for k, v in preds.items()}
    best = max(summ, key=lambda k: (round(summ[k]["f1@0.3"], 12), k))
    json.dump({"comparator": best, "selection": "validation positive mean F1@0.3 (end-to-end)", "n_val": len(ids),
               "val_f1@0.3": {k: v["f1@0.3"] for k, v in summ.items()}, "val_summaries": summ}, open(a.out, "w"), indent=1)
    print("comparator", best, {k: round(v["f1@0.3"], 4) for k, v in summ.items()})


def cmd_confirm(a):
    comp = json.load(open(a.comparator))
    gt = json.load(open(GT))
    bl = json.load(open(BASE_JSON))
    ids = split_ids(gt, "confirm")
    pos = [i for i in ids if gt[i]["category"] == "opacity"]
    tr = [i for i in gt if gt[i]["split"] == "train"]
    edges = sft_eval.area_edges(gt, tr)
    recs = EV.load_gen(os.path.join(a.conf_base, "gen_worker*.jsonl"))
    preds = all_simple(recs, ids, bl)
    sft = {}
    for kv in a.sft:
        seed, d = kv.split("=")
        r = EV.load_gen(os.path.join(d, "gen_worker*.jsonl"))
        sft[f"sft_seed{seed}"] = sft_eval.parse_records(r, ids, "concise")
        adg = {x["adapter_digest"] for x in r.values()}
        assert len(adg) == 1, f"seed {seed}: multiple adapter digests {adg}"
    preds.update(sft)
    summ = {k: sft_eval.summarize(v, gt, ids, edges) for k, v in preds.items()}
    per = {k: sft_eval.per_patient(v, gt, ids)[1]["f1@0.3"] for k, v in preds.items()}
    idx = M.bootstrap_indices(len(pos), BOOT_B, BOOT_SEED)
    cname = comp["comparator"]
    seeds = sorted(sft)
    mean_sft = np.mean([per[s] for s in seeds], axis=0)
    m, lo, hi = M.paired_boot_ci(mean_sft, per[cname], idx)
    diffs = {s: float(per[s].mean() - per[cname].mean()) for s in seeds}
    boot_all = {}
    for k in preds:
        if k in sft or k == cname:
            continue
        mm, l_, h_ = M.paired_boot_ci(mean_sft, per[k], idx)
        boot_all[k] = {"mean_diff": mm, "ci95": [l_, h_]}
    base_c = summ["concise"]
    neg_ok = {}
    for s in seeds:
        neg_ok[s] = {nm: (base_c[f"neg_{nm}"]["valid_empty"]["rate"] - summ[s][f"neg_{nm}"]["valid_empty"]["rate"]) <= 0.05
                     for nm in ("Normal", "NoOpacity/NotNormal")}
    crit = {"mean_diff_ge_0.05": m >= 0.05, "ci_lower_gt_0": lo > 0, "all_seed_diffs_positive": all(v > 0 for v in diffs.values()),
            "valid_output_rate_all_ge_95pct_each_seed": all(summ[s]["valid_rate_all"]["rate"] >= 0.95 for s in seeds),
            "negative_valid_empty_not_worse_than_5pp_vs_base_concise": all(all(v.values()) for v in neg_ok.values())}
    verdict = "success" if all(crit.values()) else ("partial_improvement" if m > 0 else "no_improvement")
    res = {"comparator": cname, "n_confirm_positive": len(pos), "primary": {"mean_sft_minus_comparator_f1@0.3": m, "ci95": [lo, hi],
           "bootstrap": {"B": BOOT_B, "seed": BOOT_SEED, "unit": "positive patient", "note": "학습 seed 불확실성을 충분히 추정하지 않는다"},
           "per_seed_diff": diffs, "per_seed_f1@0.3": {s: float(per[s].mean()) for s in seeds},
           "seed_range_f1@0.3": [min(per[s].mean() for s in seeds), max(per[s].mean() for s in seeds)]},
           "criteria": crit, "negative_layer_detail": neg_ok, "verdict_preregistered_criteria": verdict,
           "diff_vs_other_baselines": boot_all, "summaries": summ}
    json.dump(res, open(a.out, "w"), indent=1)
    print(json.dumps({k: res["primary"][k] for k in ("mean_sft_minus_comparator_f1@0.3", "ci95", "per_seed_diff")}), crit, verdict)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("comparator")
    c.add_argument("--val-base", required=True)
    c.add_argument("--out", required=True)
    f = sp.add_parser("confirm")
    f.add_argument("--comparator", required=True)
    f.add_argument("--conf-base", required=True)
    f.add_argument("--sft", nargs="+", required=True)
    f.add_argument("--out", required=True)
    a = ap.parse_args()
    {"comparator": cmd_comparator, "confirm": cmd_confirm}[a.cmd](a)


if __name__ == "__main__":
    main()
