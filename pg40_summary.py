"""iter_040 결과 요약 파일 생성 (저장된 eval/decision/train 로그에서만 읽는다). python pg40_summary.py --out results/iter_040/summary.json"""
import argparse
import json
import os
import sys


def load(p):
    return json.load(open(p))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("output exists")
    R = "results/iter_040"
    v96 = load(f"{R}/eval/v96_MC.json")
    v48 = load(f"{R}/eval/v48_B.json")
    dec = {k: load(f"{R}/decisions/{k}.json") for k in ("ext", "select_B", "bgate", "ratio", "cost_check", "v96_decision")}
    out = {"stage_reached": "method pilot: V96 comparison finished; H192 not run (negative decision)",
           "V48_B_candidates": {n: {"f1_03": m["summary"]["f1_03"][0], "f1_05": m["summary"]["f1_05"][0], "invalid": m["summary"]["invalid_rate"]}
                                for n, m in v48["models"].items()},
           "V96": {n: {"f1_03": m["summary"]["f1_03"], "f1_05": m["summary"]["f1_05"][0], "recall": m["summary"]["recall_03"][0],
                       "fp_per_sentence": m["summary"]["fp_per_sentence"], "invalid": m["summary"]["invalid_rate"],
                       "truncation": m["summary"]["unresolved_truncation_rate"], "mean_generate_s": m["summary"]["cost"]["mean_generate_s_per_request"]}
                   for n, m in v96["models"].items()},
           "V96_pairs": {k: {"f1_03": v["f1_03"]["diff_mean_ci975"], "ci95": v["f1_03"]["diff_mean_ci95"], "f1_05_diff": v["f1_05"]["diff_mean_ci95"][0],
                             "fp_per_sentence_diff": v["fp_per_sentence_diff"]} for k, v in v96["pairs"].items()},
           "decisions": {k: {kk: vv for kk, vv in v.items() if kk in ("extend", "selected", "proceed_to_M_C", "r_time", "C_compute_total_updates", "C_over_M_time",
                                                                           "within_5pct", "run", "classification", "guardrails", "train_cost", "inference_cost",
                                                                           "projected_ci975_halfwidth_H192_n192", "baseline_still_rising_after_extension")}
                         for k, v in dec.items()},
           "margin_diagnostic": load(f"{R}/eval/margin_v96.json"), "independent_verify": {k: load(f"{R}/eval/verify_v96_MC.json")[k]
                                                                                      for k in ("all_match_1e-9", "max_abs_diff_vs_report")},
           "medgrounder": load(f"{R}/medgrounder/feasibility.json")["conclusion"]}
    json.dump(out, open(a.out, "w"), indent=1)
    print(json.dumps(out, indent=1)[:3500])


if __name__ == "__main__":
    main()
