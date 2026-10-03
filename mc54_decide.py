"""iter_054 사전 고정 판정 규칙(plan.md Evaluation). 결과를 보고 문턱을 바꾸지 않는다.
입력: eval report.json + verify.json(PASS 필수). 출력: decision.json (입력 digest 포함, 덮어쓰기 금지)."""
import json
import os
import sys

import mc54_eval as E
import mc54_run as RUN

TH = {"O_min": 0.70, "O_ci_lo_gt": 0.50, "G_min": 0.15, "G_ci_lo_gt": 0.05, "ACC_min": 0.05, "ACC_ci_lo_gt": 0.0,
      "simple_dS_min": 0.10, "simple_resid_max": 0.05}


def decide(rep, verify_ok):
    b = rep["bootstrap_cluster"]
    p = rep["point"]
    c = {}
    c["integrity_valid"] = bool(verify_ok)
    c["O"] = p["O"] >= TH["O_min"] and b["O"]["ci95"][0] > TH["O_ci_lo_gt"]
    c["G"] = p["G"] >= TH["G_min"] and b["G"]["ci95"][0] > TH["G_ci_lo_gt"]
    c["ACC_vs_text"] = p["ACC_gd_minus_text"] >= TH["ACC_min"] and b["ACC_gd_minus_text"]["ci95"][0] > TH["ACC_ci_lo_gt"]
    se = rep["suspect_excluded"]
    c["suspect_excluded_direction"] = se["O"] > 0.5 and se["G"] > 0 and se["ACC_gd_minus_text"] > 0
    ls = rep["loco_summary"]
    c["loco_direction"] = ls["O_min"] > 0.5 and ls["G_min"] > 0 and ls["ACC_min"] > 0
    c["component_inference_ok"] = not rep["component_inference_limited"]
    positive_all = all(c.values())
    simple = []
    for n in E.BASE:
        if n == "MC_orig":
            continue
        if p[f"dS:{n}"] >= TH["simple_dS_min"] and b[f"dS:{n}"]["ci95"][0] > 0 and p[f"O_minus_S:{n}"] <= TH["simple_resid_max"]:
            simple.append(n)
    negative = b["O"]["ci95"][1] < TH["O_min"] or b["G"]["ci95"][1] < TH["G_min"]
    if not verify_ok:
        label, action = "execution_invalid", "fix_and_remeasure_affected_requests_only"
    elif simple:
        label, action = "simple_alternative_explains", "close_new_calibration_investment_keep_baseline"
    elif positive_all:
        label, action = "positive", "next_full_review_may_consider_minimal_method_test_value_only"
    elif negative:
        label, action = "negative", "hold_single_image_calibration_candidate"
    else:
        label, action = "indeterminate", "hold_no_automatic_extension"
    return {"label": label, "action": action, "criteria": c, "positive_all_criteria_met": positive_all, "positive_blocked_by_inference_limits_only":
            bool(not positive_all and all(v for k, v in c.items() if k != "component_inference_ok") and not c["component_inference_ok"]),
            "simple_alternative_systems": simple, "negative_condition": bool(negative), "thresholds": TH,
            "key": {"O": p["O"], "O_ci95": b["O"]["ci95"], "G": p["G"], "G_ci95": b["G"]["ci95"], "max_S": p["max_S"],
                    "ACC_gd_minus_text": p["ACC_gd_minus_text"], "ACC_ci95": b["ACC_gd_minus_text"]["ci95"]}}


def main(rep_path, ver_path, out_path):
    rep = json.load(open(rep_path))
    ver = json.load(open(ver_path))
    if os.path.exists(out_path):
        sys.exit("decision exists")
    ok = ver.get("all_pass") is True and ver.get("report_sha256") == RUN.file_sha(rep_path)
    d = decide(rep, ok)
    d["inputs"] = {"report": rep_path, "report_sha256": RUN.file_sha(rep_path), "verify": ver_path, "verify_sha256": RUN.file_sha(ver_path),
                   "verify_all_pass": ver.get("all_pass")}
    json.dump(d, open(out_path, "x"), indent=1)
    print(json.dumps({k: d[k] for k in ("label", "action", "criteria", "simple_alternative_systems")}, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
