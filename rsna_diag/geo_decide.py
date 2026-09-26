"""iter_014 사전 고정 판정 규칙 (report.json -> decision.json). 결과를 본 뒤 규칙을 바꾸지 않는다. 사용: python -m rsna_diag.geo_decide explore|full --report R --out O

비교 기준(baseline) checkpoint: G는 V200 선택 checkpoint(guardrail 통과 최대 S_loc)만 쓴다. 선택이 없으면 selected=null, selection_eligible=false이며
final 점수는 별도 필드이고 확대 판정에 대체 사용하지 않는다. C·U에 선택 후보가 없을 때만 보수적 대체(V200 최고 S_loc checkpoint, guardrail 무시; G에는 불리한 기준)를 쓰고
대체 사실을 표시한다.

일반 확대: G 선택 checkpoint의 V400 guardrail 통과 AND G-C S_loc >= 0.03 AND G-U S_loc >= 0.01 AND G-C F1@0.5 > 0 (모두 V400 선택 checkpoint 기준).
  최종 대 최종 결과의 G-C, G-U 부호가 선택 결과와 반대(선택 >0 인데 최종 <= 0)이면 자동 확대를 보류한다.
보완 확대(1회): G가 V200·V400 guardrail을 통과(선택 존재), G-U 점추정 > 0, G-C F1@0.5 > 0, G-C paired 95% CI 상한 >= 0.03, G의 V200 마지막 milestone 간 S_loc 상승 >= 0.01
  (explore: update150->225, full: update300->450)이면 full-train으로 한 번 확대할 수 있다. 선택 부재·guardrail 실패는 이 경로로 우회하지 않는다.
"""
import argparse
import json

from . import select as SEL

GAP_C, GAP_U, LAST_GAIN = 0.03, 0.01, 0.01


def baseline_point(t):
    """trajectory entry -> dict(S_loc, f1@0.5, tag, substituted). 선택이 있으면 선택, 없으면 V200 최고 S_loc checkpoint의 V400 결과가 있어야 한다(없으면 None)."""
    if t.get("selected"):
        e = t["selected"]
        return {"S_loc": e["v400"]["S_loc"], "f1@0.5": e["v400"]["f1@0.5"], "tag": "selected", "substituted": False, "epoch": e["epoch"]}
    b = t.get("v200_best_fallback")
    if b:
        return {"S_loc": b["v400"]["S_loc"], "f1@0.5": b["v400"]["f1@0.5"], "tag": "v200_best_no_guardrail(fallback)", "substituted": True, "epoch": b["epoch"]}
    return None


def final_point(t):
    e = t.get("final")
    return {"S_loc": e["v400"]["S_loc"], "f1@0.5": e["v400"]["f1@0.5"], "epoch": e["epoch"]} if e else None


def decide(rep, mode, tags=("C", "U", "G")):
    tr = rep["trajectories"]
    key = lambda c: next((k for k in tr if k.split("@")[0] == c), None)
    kc, ku, kg = (key(c) for c in tags)
    out = {"rule": __doc__.split("\n")[2:14], "mode": mode, "trajectories": {"C": kc, "U": ku, "G": kg}}
    if not (kc and ku and kg):
        return {**out, "error": "C, U or G trajectory missing", "expand": False}
    C, U, G = tr[kc], tr[ku], tr[kg]
    g_sel = G.get("selected")
    out["G_selected"] = None if not g_sel else {"epoch": g_sel["epoch"], "update": g_sel["update"], "S_loc_v400": g_sel["v400"]["S_loc"]}
    out["G_selection_eligible"] = bool(g_sel)
    out["G_final"] = final_point(G)
    out["G_final_guardrail_v400_ok"] = G["final"]["guardrail_v400"]["ok"] if G.get("final") else None
    out["G_selected_guardrail_v400_ok"] = g_sel["guardrail_v400"]["ok"] if g_sel else None
    cb, ub, gb = baseline_point(C), baseline_point(U), baseline_point(G)
    out["C_baseline"], out["U_baseline"] = cb, ub
    out["C_final"], out["U_final"] = final_point(C), final_point(U)
    if not g_sel or cb is None or ub is None:
        out.update({"expand": False, "reason": "G has no eligible selected checkpoint (or C/U reference unavailable): no automatic expansion, no substitution by final"})
        return out
    ci = rep["pairwise_v400_paired_bootstrap"]["selected"].get(f"{kg}-{kc}")
    d_gc, d_gu = gb["S_loc"] - cb["S_loc"], gb["S_loc"] - ub["S_loc"]
    d_f05 = gb["f1@0.5"] - cb["f1@0.5"]
    g_guard = bool(g_sel["guardrail_v400"]["ok"])
    fin = {}
    if out["G_final"] and out["C_final"] and out["U_final"]:
        fin = {"G-C": out["G_final"]["S_loc"] - out["C_final"]["S_loc"], "G-U": out["G_final"]["S_loc"] - out["U_final"]["S_loc"],
               "G-C_f1@0.5": out["G_final"]["f1@0.5"] - out["C_final"]["f1@0.5"]}
    v = G["v200_detail_by_epoch"]
    eps = sorted(int(e) for e in v)
    last_gain = v[str(eps[-1])]["S_loc"] - v[str(eps[-2])]["S_loc"]
    out.update({"G_minus_C": d_gc, "G_minus_U": d_gu, "G_minus_C_f1@0.5": d_f05, "paired_ci_G_minus_C": ci, "G_v200_last_interval_gain": last_gain, "G_guardrail_v400_ok": g_guard,
                "final_vs_final": fin, "U_minus_C": ub["S_loc"] - cb["S_loc"]})
    general = g_guard and d_gc >= GAP_C and d_gu >= GAP_U and d_f05 > 0
    opposite = bool(fin) and (fin["G-C"] <= 0 or fin["G-U"] <= 0)
    supplement = g_guard and d_gu > 0 and d_f05 > 0 and ci is not None and ci["ci95"][1] >= GAP_C and last_gain >= LAST_GAIN
    out["general_criteria_met"] = bool(general)
    out["supplement_criteria_met"] = bool(supplement)
    out["final_opposes_selected"] = opposite
    if general and opposite:
        out.update({"expand": False, "reason": "general criteria met on selected checkpoints but final-vs-final has opposite sign: automatic expansion held, review checkpoint trend"})
    elif general:
        out.update({"expand": True, "expand_path": "general", "reason": f"G-C {d_gc:.4f} >= 0.03, G-U {d_gu:.4f} >= 0.01, G-C F1@0.5 {d_f05:.4f} > 0, guardrail ok"})
    elif supplement and mode == "explore":
        out.update({"expand": True, "expand_path": "supplement(once)", "reason": f"G-C {d_gc:.4f} < 0.03 but CI upper {ci['ci95'][1]:.4f} >= 0.03, G-U {d_gu:.4f} > 0, F1@0.5 {d_f05:.4f} > 0, last-interval gain {last_gain:.4f} >= 0.01"})
    else:
        out.update({"expand": False, "reason": f"G-C {d_gc:.4f}, G-U {d_gu:.4f}, G-C F1@0.5 {d_f05:.4f}, guardrail {g_guard}, CI upper {ci['ci95'][1] if ci else None}, last gain {last_gain:.4f}: below criteria"})
    if mode == "full":
        out["next"] = "C_compute" if out["expand"] and out.get("expand_path") == "general" else "stop"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["explore", "full"])
    ap.add_argument("--report", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rep = json.load(open(a.report))
    dec = {"mode": a.mode, "report": a.report, "report_sha256": SEL.file_sha(a.report), "decision": decide(rep, a.mode)}
    print(SEL.write_or_verify(a.out, json.loads(json.dumps(dec))), json.dumps(dec["decision"], indent=1)[:2500])


if __name__ == "__main__":
    main()
