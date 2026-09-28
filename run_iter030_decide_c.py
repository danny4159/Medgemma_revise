"""iter_030 C201 decision: E402 진입 여부를 계획서 4절 기준으로 판정하고 잠근다."""
import json
import os

OUT = "results/iter_030/decide_c.json"


def decide(report):
    h1, h2 = report["h1"], report["h2"]
    diff = h1["diff_Q_minus_Bstar"]
    q1 = h1["auroc_Q_one_box_layer"]

    point_criterion = (diff["point"] >= 0.03) and (q1 is not None and q1["point"] >= 0.60)
    recovery_criterion = (h2["n_events"] > 0) and (h2["recovery_rate"] >= 0.20)

    ci_soft = False
    ci_soft_reason = None
    if not (point_criterion or recovery_criterion):
        cond_a = (diff["hi"] >= 0.05) and (q1 is not None and q1["hi"] >= 0.65)
        cond_b = (h2["n_recovered"] >= 1) and (h2["wilson_95_hi"] >= 0.25)
        ci_soft = bool(cond_a or cond_b)
        if cond_a:
            ci_soft_reason = "diff_Q_minus_Bstar CI 상한>=0.05 and one-box Q AUROC CI 상한>=0.65"
        elif cond_b:
            ci_soft_reason = "recovery>=1건 and wilson 95% 상한>=0.25"

    enter_e = bool(point_criterion or recovery_criterion or ci_soft)
    return {
        "point_criterion_met": point_criterion, "recovery_criterion_met": recovery_criterion,
        "ci_soft_criterion_met": ci_soft, "ci_soft_reason": ci_soft_reason,
        "enter_E": enter_e,
        "bstar": report["bstar"], "diff_Q_minus_Bstar": diff, "auroc_Q_one_box_layer": q1,
        "h2_recovery_rate": h2["recovery_rate"], "h2_n_events": h2["n_events"], "h2_n_recovered": h2["n_recovered"],
        "h2_wilson_95_hi": h2["wilson_95_hi"],
    }


def main():
    if os.path.exists(OUT):
        raise RuntimeError(f"refusing to overwrite existing {OUT}")
    report = json.load(open("results/iter_030/C201/report.json"))
    decision = decide(report)
    json.dump(decision, open(OUT, "w"), indent=1)
    print(json.dumps(decision, indent=1))


if __name__ == "__main__":
    main()
