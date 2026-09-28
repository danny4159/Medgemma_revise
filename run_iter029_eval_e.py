"""iter_029 E800(빈 출력 398명) 확인 평가. C에서 고정한 대표 T/V·calibration을 그대로 적용, 재선택하지 않는다.

iter_028의 run_iter028_eval_e.py를 그대로 따르되 build_table을 이번 교정본(run_iter029_eval_c)에서
가져온다. C_eval/c_eval.json이 먼저 존재해야 한다(단계 2가 단계 3보다 먼저 실행돼야 함을 강제).
"""
import json
import os

import numpy as np

from rsna_diag import risk28_eval as Ev
from run_iter029_eval_c import build_table, SCORE_NAMES, RESULTS_ROOT

OUT = "results/iter_029/E_eval"
C_EVAL_PATH = "results/iter_029/C_eval/c_eval.json"


def main():
    if not os.path.exists(C_EVAL_PATH):
        raise RuntimeError(f"missing {C_EVAL_PATH}: run run_iter029_eval_c.py first (C selects rep_T/rep_V/calibration)")
    if os.path.exists(os.path.join(OUT, "e_eval.json")):
        raise RuntimeError(f"refusing to overwrite existing {OUT}/e_eval.json")
    os.makedirs(OUT, exist_ok=True)
    sm = json.load(open(f"{RESULTS_ROOT}/source_manifest.json"))
    c_eval = json.load(open(C_EVAL_PATH))
    rep_T, rep_V = c_eval["representative_T"], c_eval["representative_V"]
    calibrations = c_eval["calibrations"]

    rows = build_table(sm, "E")
    y = [r["y"] for r in rows]
    n = len(rows)
    print(f"E: n={n} n_events={sum(y)}")

    raw_auroc = {name: Ev.auroc([r[name] for r in rows], y) for name in SCORE_NAMES}
    capture20 = {name: Ev.capture_at_k([r[name] for r in rows], y, 0.2) for name in SCORE_NAMES}
    remain20 = {name: Ev.remaining_after_review([r[name] for r in rows], y, 0.2) for name in SCORE_NAMES}

    def ci_for(name):
        s = np.array([r[name] for r in rows])
        yy = np.array(y)

        def auc_fn(idx):
            return Ev.auroc(s[idx], yy[idx])

        def cap_fn(idx):
            return Ev.capture_at_k(s[idx], yy[idx], 0.2)
        return {"auroc": Ev.metric_ci(auc_fn, n, B=10000, seed=28017),
                "capture20": Ev.metric_ci(cap_fn, n, B=10000, seed=28017)}

    cis = {name: ci_for(name) for name in SCORE_NAMES}

    s_T = np.array([r[rep_T] for r in rows])
    s_V = np.array([r[rep_V] for r in rows])
    s_seed = np.array([r["seed_disagreement"] for r in rows])
    yy = np.array(y)

    def auc_T(idx):
        return Ev.auroc(s_T[idx], yy[idx])

    def auc_V(idx):
        return Ev.auroc(s_V[idx], yy[idx])

    def auc_seed(idx):
        return Ev.auroc(s_seed[idx], yy[idx])

    diff_VT = Ev.paired_diff_ci(auc_V, auc_T, n, B=10000, seed=28017, alpha_lo=1.25, alpha_hi=98.75)
    diff_Vseed = Ev.paired_diff_ci(auc_V, auc_seed, n, B=10000, seed=28017, alpha_lo=1.25, alpha_hi=98.75)

    calib_metrics = {}
    for name in SCORE_NAMES:
        s = np.array([r[name] for r in rows])
        probs = Ev.apply_platt(calibrations[name], s)
        calib_metrics[name] = {"brier": Ev.brier(probs, y), "ece": Ev.ece(probs, y)}

    by_cat = {}
    for cat in ("opacity", "normal", "not_normal_no_opacity"):
        sub = [r for r in rows if r["category"] == cat]
        by_cat[cat] = {"n": len(sub), "n_events": sum(r["y"] for r in sub)}

    n_common3 = sum(1 for r in rows if r["seed_disagreement"] == 0.0)

    single_class_subgroups = [cat for cat, d in by_cat.items() if d["n_events"] == 0 or d["n_events"] == d["n"]]

    out = {
        "n": n, "n_events": int(sum(y)), "representative_T": rep_T, "representative_V": rep_V,
        "raw_auroc": raw_auroc, "capture_at_20pct": capture20, "remaining_after_review": remain20,
        "cis": cis, "diff_V_minus_T_auroc_975": diff_VT, "diff_V_minus_seed_auroc_975": diff_Vseed,
        "calibration_metrics": calib_metrics, "by_category": by_cat,
        "n_common_empty_3seeds": n_common3,
        "single_class_subgroups_auroc_undefined": single_class_subgroups,
        "sign_convention": "same as C_eval (presence corrected, ptrue unchanged from iter_028)",
        "corrects": "iter_028's run_iter028_eval_e.py which inherited the presence sign error via build_table",
    }
    json.dump(out, open(os.path.join(OUT, "e_eval.json"), "w"), indent=1)
    json.dump(rows, open(os.path.join(OUT, "e_table.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
