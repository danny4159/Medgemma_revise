"""iter_028 C400(빈 출력 199명) 평가: raw AUROC로 대표 T(token)·V(영상 재질의) 선택, calibration 적합, E 확대 결정."""
import json
import os

import numpy as np

from rsna_diag import risk28, risk28_eval as E

OUT = "results/iter_028/C_eval"


def build_table(sm, split):
    patients = [p for p in sm["patients"][split].values() if p["seed17_empty"]]
    sft = risk28.load_all(f"results/iter_028/{split}", "sft")
    base = risk28.load_all(f"results/iter_028/{split}", "base")
    rows = []
    for p in patients:
        pid = p["id"]
        ts = sft[(pid, "token_score")]
        pres_b = sft[(pid, "presence")]
        ptrue_b = sft[(pid, "ptrue")]
        pres_m = base[(pid, "presence")]
        ptrue_m = base[(pid, "ptrue")]
        seed_dis = ((not p["seed29_empty"]) + (not p["seed43_empty"])) / 2.0
        rows.append({
            "id": pid, "y": int(p["y_miss"]), "category": p["category"],
            "token_nll": ts["nll_bracket"], "token_nll_eos": (ts["nll_bracket"] + ts["nll_eos_step1"]) / 2.0,
            "entropy": ts["entropy_bracket"], "seed_disagreement": seed_dis,
            "presence_m0": pres_m["risk_no_minus_yes"], "presence_b0": pres_b["risk_no_minus_yes"],
            "ptrue_m0": ptrue_m["risk_no_minus_yes"], "ptrue_b0": ptrue_b["risk_no_minus_yes"],
        })
    return rows


SCORE_NAMES = ["token_nll", "token_nll_eos", "entropy", "seed_disagreement",
               "presence_m0", "presence_b0", "ptrue_m0", "ptrue_b0"]
TOKEN_FAMILY = ["token_nll", "token_nll_eos", "entropy"]
IMAGE_FAMILY = ["presence_m0", "presence_b0", "ptrue_m0", "ptrue_b0"]


def main():
    os.makedirs(OUT, exist_ok=True)
    sm = json.load(open("results/iter_028/source_manifest.json"))
    rows = build_table(sm, "C")
    y = [r["y"] for r in rows]
    n = len(rows)
    rng = np.random.default_rng(28017)
    random_score = rng.uniform(size=n).tolist()

    raw_auroc = {}
    for name in SCORE_NAMES:
        s = [r[name] for r in rows]
        raw_auroc[name] = E.auroc(s, y)
    raw_auroc["random"] = E.auroc(random_score, y)

    rep_T = max(TOKEN_FAMILY, key=lambda k: raw_auroc[k])
    rep_V = max(IMAGE_FAMILY, key=lambda k: raw_auroc[k])

    calibrations = {}
    for name in SCORE_NAMES:
        s = np.array([r[name] for r in rows])
        calibrations[name] = E.fit_platt(s, y)

    capture20 = {name: E.capture_at_k([r[name] for r in rows], y, 0.2) for name in SCORE_NAMES}
    capture20["random"] = E.capture_at_k(random_score, y, 0.2)

    def ci_for(name):
        s = np.array([r[name] for r in rows])
        yy = np.array(y)

        def auc_fn(idx):
            return E.auroc(s[idx], yy[idx])

        def cap_fn(idx):
            return E.capture_at_k(s[idx], yy[idx], 0.2)
        return {"auroc": E.metric_ci(auc_fn, n, B=10000, seed=28017, alpha_lo=2.5, alpha_hi=97.5),
                "capture20": E.metric_ci(cap_fn, n, B=10000, seed=28017, alpha_lo=2.5, alpha_hi=97.5)}

    cis = {name: ci_for(name) for name in SCORE_NAMES}

    s_T = np.array([r[rep_T] for r in rows])
    s_V = np.array([r[rep_V] for r in rows])
    s_seed = np.array([r["seed_disagreement"] for r in rows])
    yy = np.array(y)

    def auc_T(idx):
        return E.auroc(s_T[idx], yy[idx])

    def auc_V(idx):
        return E.auroc(s_V[idx], yy[idx])

    def auc_seed(idx):
        return E.auroc(s_seed[idx], yy[idx])

    diff_VT = E.paired_diff_ci(auc_V, auc_T, n, B=10000, seed=28017, alpha_lo=2.5, alpha_hi=97.5)
    diff_Vseed = E.paired_diff_ci(auc_V, auc_seed, n, B=10000, seed=28017, alpha_lo=2.5, alpha_hi=97.5)

    enter_E = False
    reasons = []
    for name in SCORE_NAMES:
        if cis[name]["auroc"]["hi"] >= 0.75:
            enter_E = True
            reasons.append(f"{name}: AUROC CI upper {cis[name]['auroc']['hi']:.3f} >= 0.75")
        if cis[name]["capture20"]["hi"] >= 0.50:
            enter_E = True
            reasons.append(f"{name}: Capture@20 CI upper {cis[name]['capture20']['hi']:.3f} >= 0.50")
    if diff_VT["lo"] <= 0.10 <= diff_VT["hi"] and (diff_VT["hi"] - diff_VT["lo"]) > 0.10:
        enter_E = True
        reasons.append(f"V-T AUROC diff CI [{diff_VT['lo']:.3f},{diff_VT['hi']:.3f}] contains 0.10 and width>0.10")
    if diff_Vseed["lo"] <= 0.10 <= diff_Vseed["hi"] and (diff_Vseed["hi"] - diff_Vseed["lo"]) > 0.10:
        enter_E = True
        reasons.append(f"V-seed AUROC diff CI [{diff_Vseed['lo']:.3f},{diff_Vseed['hi']:.3f}] contains 0.10 and width>0.10")

    out = {
        "n": n, "n_events": int(sum(y)), "representative_T": rep_T, "representative_V": rep_V,
        "raw_auroc": raw_auroc, "capture_at_20pct": capture20, "cis": cis,
        "diff_V_minus_T_auroc": diff_VT, "diff_V_minus_seed_auroc": diff_Vseed,
        "enter_E": enter_E, "reasons": reasons,
        "calibrations": calibrations,
    }
    json.dump(out, open(os.path.join(OUT, "c_eval.json"), "w"), indent=1)
    json.dump(rows, open(os.path.join(OUT, "c_table.json"), "w"), indent=1)
    print(f"n={n} n_events={sum(y)} rep_T={rep_T} rep_V={rep_V}")
    print("raw_auroc:", json.dumps(raw_auroc, indent=1))
    print("capture20:", json.dumps(capture20, indent=1))
    print("diff_V-T:", diff_VT)
    print("diff_V-seed:", diff_Vseed)
    print("enter_E:", enter_E)
    for r in reasons:
        print(" -", r)


if __name__ == "__main__":
    main()
