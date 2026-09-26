"""iter_014 평가·판정 fixture (CPU): multi(GT>=2)/ge3 집계 정정, selected=null 판정, 확대 규칙 경계. 결과: results/iter_014/tests/fixtures_iter014_eval.json"""
import json
import os
import sys

import numpy as np

from rsna_diag import adapt_eval as AE, geo_decide as GD, sft_eval

OUT = "results/iter_014/tests/fixtures_iter014_eval.json"
res = []


def ok(name, cond, detail=""):
    res.append({"name": name, "pass": bool(cond), "detail": str(detail)[:400]})
    print(("PASS " if cond else "FAIL ") + name, str(detail)[:200], flush=True)


def synth():
    """GT box 1/2/3/4개 환자와 음성. 예측 = GT를 그대로 복사한 부분집합으로 환자별 S_loc를 손으로 알 수 있게 한다."""
    gt, preds, ids = {}, {}, []
    for pid, n, k in (("a", 1, 1), ("b", 2, 2), ("c", 3, 3), ("d", 3, 1), ("e", 4, 2)):
        boxes = [[10 * (j + 1), 10 * (j + 1), 10 * (j + 1) + 50, 10 * (j + 1) + 50] for j in range(n)]
        gt[pid] = {"category": "opacity", "split": "validation", "boxes": [{"yxyx_norm": b} for b in boxes], "image_w": 1000, "image_h": 1000}
        preds[pid] = {"status": "valid_nonempty", "boxes": boxes[:k]}
        ids.append(pid)
    gt["n"] = {"category": "normal", "split": "validation", "boxes": []}
    preds["n"] = {"status": "valid_empty", "boxes": []}
    ids.append("n")
    return gt, preds, ids


def main():
    gt, preds, ids = synth()
    try:
        d = AE.detail(preds, gt, ids, [0.01, 0.02], [0.01, 0.02])
    except Exception as e:  # sft_eval.summarize가 다른 필드를 요구할 수 있다
        d = None
        print("detail error", repr(e))
    ok("AE.detail runs on synthetic patients", d is not None)
    if d is not None:
        g = d["by_n_gt_S_loc"]
        ok("multi counts GT>=2 (b,c,d,e = 4), single 1, ge3 = 3 (c,d,e)", g["single"]["n"] == 1 and g["multi"]["n"] == 4 and g["ge3"]["n"] == 3, {k: v["n"] for k, v in g.items()})
        # 환자별 F1(thr 0.3 = 0.5 동일, IoU=1): F1 = 2k/(k+n)
        f = {"a": 1.0, "b": 2 * 2 / (2 + 2), "c": 2 * 3 / (3 + 3), "d": 2 * 1 / (1 + 3), "e": 2 * 2 / (2 + 4)}
        want_multi = np.mean([f[p] for p in "bcde"])
        want_ge3 = np.mean([f[p] for p in "cde"])
        ok("multi/ge3 S_loc equal hand-computed patient means", abs(g["multi"]["S_loc"] - want_multi) < 1e-12 and abs(g["ge3"]["S_loc"] - want_ge3) < 1e-12, (g["multi"]["S_loc"], want_multi, g["ge3"]["S_loc"], want_ge3))
        ok("overall S_loc unchanged by the multi fix (= mean over all 5 positives)", abs(d["S_loc"] - np.mean(list(f.values()))) < 1e-12, d["S_loc"])

    def entry(sel_S, fin_S, guard=True, sel_ok=True):
        mk = lambda e, s, f05: {"epoch": e, "update": 75 * e, "v400": {"S_loc": s, "f1@0.5": f05}, "guardrail_v400": {"ok": guard}}
        return {"selected": mk(2, sel_S, sel_S - 0.05) if sel_ok else None, "final": mk(3, fin_S, fin_S - 0.05),
                "v200_best_fallback": None if sel_ok else mk(1, sel_S, sel_S - 0.05),
                "v200_detail_by_epoch": {"1": {"S_loc": 0.5}, "2": {"S_loc": 0.52}, "3": {"S_loc": 0.53}}}

    def rep(c, u, g, ci_hi=0.05):
        return {"trajectories": {"C@2e-05": c, "U@2e-05": u, "G@2e-05": g},
                "pairwise_v400_paired_bootstrap": {"selected": {"G@2e-05-C@2e-05": {"diff": 0.0, "ci95": [-0.01, ci_hi]}}}}

    r = rep(entry(0.50, 0.51), entry(0.51, 0.52), entry(0.55, 0.56))
    d = GD.decide(r, "explore")
    ok("general expansion: G-C 0.05>=0.03, G-U 0.04>=0.01, F1@0.5 diff>0", d["expand"] and d["expand_path"] == "general", d.get("reason"))
    r = rep(entry(0.50, 0.51), entry(0.545, 0.52), entry(0.55, 0.56))
    ok("G-U below 0.01 -> no general expansion (augmentation effect)", not GD.decide(r, "explore")["expand"] or GD.decide(r, "explore")["expand_path"] != "general")
    g_null = entry(0.55, 0.56, sel_ok=False)
    g_null["selected"] = None
    g_null["v200_best_fallback"] = None
    d = GD.decide(rep(entry(0.50, 0.51), entry(0.51, 0.52), g_null), "explore")
    ok("G selected=null -> expand False, no substitution by final", d["expand"] is False and d["G_selection_eligible"] is False and d["G_final"]["S_loc"] == 0.56, d.get("reason"))
    d = GD.decide(rep(entry(0.50, 0.51, sel_ok=False), entry(0.51, 0.52), entry(0.55, 0.56)), "explore")
    ok("C has no selected -> conservative V200-best fallback flagged as substituted", d["C_baseline"]["substituted"] is True and d["C_baseline"]["tag"].startswith("v200_best"))
    r = rep(entry(0.50, 0.49), entry(0.51, 0.50), entry(0.55, 0.48))
    d = GD.decide(r, "explore")
    ok("selected wins but final-vs-final opposite sign -> automatic expansion held", d["general_criteria_met"] and d["final_opposes_selected"] and not d["expand"], d.get("reason"))
    r = rep(entry(0.50, 0.51), entry(0.51, 0.52), entry(0.52, 0.56), ci_hi=0.031)
    r["trajectories"]["G@2e-05"]["v200_detail_by_epoch"] = {"1": {"S_loc": 0.5}, "2": {"S_loc": 0.52}, "3": {"S_loc": 0.535}}
    d = GD.decide(r, "explore")
    ok("supplement path (once): CI upper>=0.03, last gain>=0.01, G-U>0, F1@0.5>0", d["expand"] and d["expand_path"] == "supplement(once)", d.get("reason"))
    d = GD.decide(r, "full")
    ok("supplement path is not available in full stage", not d["expand"])
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"n": len(res), "n_pass": sum(x["pass"] for x in res), "results": res}, open(OUT, "w"), indent=1)
    print(f"{sum(x['pass'] for x in res)}/{len(res)} PASS")
    return 0 if all(x["pass"] for x in res) else 1


if __name__ == "__main__":
    sys.exit(main())
