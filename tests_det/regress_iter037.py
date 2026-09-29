"""iter_037 회귀 대조: 변경된 계산 경로(det37)의 수치를 원래 저장 결과와 대조한다 (정확한 count, 수치 1e-8).
  V400(사후 검사): 선택 파일의 selected/fp_budgets 수치, SFT17 val_metrics.
  confirm800: iter_036 analysis.json(분해·R·CI·위치·FP 분해), iter_035 confirm800 analysis(FP budget·상보성·요약).
사용: python tests_det/regress_iter037.py --v400 <report.json> --c800 <report.json> --out <새 json>  (덮어쓰기 거부)"""
import argparse
import json
import os
import sys

BASE = "/SSD1_1TB/home/milab/daniel/08_medgemma/research"
sys.path.insert(0, BASE)
from rsna_diag import det37 as T  # noqa: E402

TOL = 1e-8
res = {"pass": 0, "fail": 0, "checks": []}


def chk(name, a, b, tol=TOL):
    if isinstance(a, (int, bool, str)) and isinstance(b, (int, bool, str)) or a is None or b is None:
        ok = a == b
    elif isinstance(a, (list, tuple)):
        ok = len(a) == len(b) and all(abs(x - y) <= tol for x, y in zip(a, b))
    else:
        ok = abs(a - b) <= tol
    res["pass" if ok else "fail"] += 1
    res["checks"].append({"name": name, "new": a, "old": b, "ok": bool(ok)})
    if not ok:
        print("FAIL", name, a, b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v400", required=True)
    ap.add_argument("--c800", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        raise FileExistsError(a.out)
    v = json.load(open(a.v400))
    c = json.load(open(a.c800))
    # ---- V400: 선택 파일 수치 (scan 경로의 별도 계산)
    for d in (17, 29):
        sel = json.load(open(T.SEL[d]))
        s = sel["selected"]
        t = v["detector"][f"det{d}__selected"]["table"]
        chk(f"V400 det{d} selected f1@0.3", t["f1@0.3"], s["f1@0.3"])
        chk(f"V400 det{d} selected f1@0.5", t["f1@0.5"], s["f1@0.5"])
        chk(f"V400 det{d} selected utility", t["utility"], s["utility"])
        chk(f"V400 det{d} selected lesion_recall@0.3", t["lesion@0.3"]["lesion_recall"], s["lesion_recall@0.3"])
        chk(f"V400 det{d} selected fp/patient", t["fp"]["all"]["iou0.3"]["fp_per_patient"], s["fp_per_patient"])
        for b, r in sel["fp_budgets"].items():
            t = v["detector"][f"det{d}__fp_budget_{b}"]["table"]
            chk(f"V400 det{d} budget{b} lesion_recall@0.3", t["lesion@0.3"]["lesion_recall"], r["lesion_recall@0.3"])
            chk(f"V400 det{d} budget{b} fp/patient", t["fp"]["all"]["iou0.3"]["fp_per_patient"], r["fp_per_patient"])
    vm = json.load(open(f"{T.IT012}/train/lr2e-4_s17/epoch_05/val_metrics.json"))
    ts = v["tables"]["sft17"]
    chk("V400 sft17 f1@0.3", ts["f1@0.3"], vm["f1@0.3"])
    chk("V400 sft17 f1@0.5", ts["f1@0.5"], vm["f1@0.5"])
    chk("V400 sft17 utility", ts["utility"], vm["utility"])
    chk("V400 sft17 status_all", str(sorted(ts["status_all"].items())), str(sorted(vm["status_all"].items())))
    # ---- confirm800 vs iter_036
    old36 = json.load(open(f"{BASE}/results/iter_036/full/analysis.json"))
    for d in (17, 29):
        for s in (17, 29, 43):
            for t in (0.3, 0.5):
                new = c["detector"][f"det{d}__selected"]["vs_sft"][f"sft{s}"]["decomposition"][f"iou{t}"]
                old = old36["decomposition"][f"det{d}_vs_sft{s}_iou{t}"]
                chk(f"c800 det{d} sft{s} iou{t} category_counts", str(sorted(new["category_counts"].items())), str(sorted(old["category_counts"].items())))
                if t == 0.3:
                    o = old36["r_and_threshold_excluded"][f"det{d}_vs_sft{s}"]
                    chk(f"c800 det{d} sft{s} r_numerator", new["r_numerator"], o["r_numerator"])
                    chk(f"c800 det{d} sft{s} r_affected", new["r_n_affected_patients"], o["r_n_affected_patients"])
                    chk(f"c800 det{d} sft{s} r_ci97.5", new["r_ci97.5"], o["r_ci97.5"])
                    chk(f"c800 det{d} sft{s} thr_excl_point", new["threshold_excluded_point"], o["threshold_excluded_point"])
                    chk(f"c800 det{d} sft{s} thr_excl_ci", new["threshold_excluded_ci97.5"], o["threshold_excluded_ci97.5"])
    ps = c["detector"]["det17__selected"]["pair_summary"]
    op = old36["position_precision_det17_vs_sft17"]
    chk("c800 det17 n_pairs", ps["detector"]["n_pairs_iou0.3"], op["detector"]["n_pairs_iou0.3"])
    chk("c800 sft17 n_pairs", ps["sft17"]["n_pairs_iou0.3"], op["sft"]["n_pairs_iou0.3"])
    chk("c800 det17 rematch rate (old transfer_rate)", ps["detector"]["gt_hit_by_independent_rematch_0.5_rate"], op["detector"]["transfer_rate_to_iou0.5"])
    chk("c800 sft17 rematch rate (old transfer_rate)", ps["sft17"]["gt_hit_by_independent_rematch_0.5_rate"], op["sft"]["transfer_rate_to_iou0.5"])
    for nm, key in (("detector17", "det17__selected"), ("sft17", "sft17")):
        fp = (c["detector"][key]["table"] if key.startswith("det") else c["tables"][key])["fp"]["all800"]["iou0.3"]
        o = old36["fp_decomposition"][nm]
        for k in ("competes_for_matched_gt", "near_miss_0.1_to_thr", "no_gt_within_0.1", "n_fp_total"):
            chk(f"c800 {nm} fp {k}", fp[k], o[k])
    # ---- confirm800 vs iter_035 analysis
    old35 = json.load(open(f"{BASE}/results/iter_035/confirm800/analysis.json"))
    for b, o in old35["fp_budget_detector17"].items():
        n = c["detector"][f"det17__fp_budget_{b}"]["table"]
        chk(f"c800 det17 budget{b} lesion@0.3 tp", n["lesion@0.3"]["tp"], o["lesion@0.3"]["tp"])
        chk(f"c800 det17 budget{b} f1@0.3", n["f1@0.3"], o["f1@0.3"])
        chk(f"c800 det17 budget{b} fp/patient", n["fp"]["all800"]["iou0.3"]["fp_per_patient"], o["fp_all800"]["fp_per_patient_all_n_lower_bound"])
        for t in (0.3, 0.5):
            nn = c["detector"][f"det17__fp_budget_{b}"]["vs_sft"]["sft17"]["complementarity"][f"iou{t}"]
            oo = old35["complementarity"][f"iou{t}_fpbudget{b}"]
            for k in ("detector_only", "sft_only", "both_hit", "both_miss", "total_gt"):
                chk(f"c800 det17 budget{b} iou{t} {k}", nn[k], oo[k])
    for t in (0.3, 0.5):
        for k in ("detector_only", "sft_only", "both_hit", "both_miss"):
            chk(f"c800 det17 selected iou{t} {k}", c["detector"]["det17__selected"]["vs_sft"]["sft17"]["complementarity"][f"iou{t}"][k], old35["complementarity"][f"iou{t}"][k])
            chk(f"c800 det17 selected iou{t} {k}_rate_ci95", c["detector"]["det17__selected"]["vs_sft"]["sft17"]["complementarity"][f"iou{t}"][f"{k}_rate_ci95"], old35["complementarity"][f"iou{t}"][f"{k}_rate_ci95"])
    for m, key in (("detector17", "det17__selected"),):
        n = c["detector"][key]["table"]
        chk("c800 det17 selected f1@0.3 vs iter035 summary", n["f1@0.3"], old35["summary"][m]["f1@0.3"])
        chk("c800 det17 selected f1@0.5 vs iter035 summary", n["f1@0.5"], old35["summary"][m]["f1@0.5"])
        chk("c800 det17 selected utility", n["utility"], old35["summary"][m]["utility"])
        chk("c800 det17 selected fp_all800", n["fp"]["all800"]["iou0.3"]["fp_per_patient"], old35["summary"][m]["fp_all800"]["fp_per_patient_all_n_lower_bound"])
    for s in (17, 29, 43):
        chk(f"c800 sft{s} f1@0.3", c["tables"][f"sft{s}"]["f1@0.3"], old35["summary"][f"sft{s}"]["f1@0.3"])
        chk(f"c800 sft{s} fp/patient", c["tables"][f"sft{s}"]["fp"]["all800"]["iou0.3"]["fp_per_patient"], old35["summary"][f"sft{s}"]["fp_all800"]["fp_per_patient_all_n_lower_bound"])
    d = c["detector"]["det17__selected"]["vs_sft"]["sft17"]["diff_f1@0.3"]
    chk("c800 primary diff f1@0.3", d["diff"], old35["primary_detector17_minus_B0"]["f1@0.3"]["diff"])
    chk("c800 primary ci97.5 f1@0.3", d["ci97.5"], old35["primary_detector17_minus_B0"]["f1@0.3"]["ci97.5"])
    print(json.dumps({"pass": res["pass"], "fail": res["fail"]}))
    T.write_json_new(a.out, res)
    sys.exit(1 if res["fail"] else 0)


if __name__ == "__main__":
    main()
