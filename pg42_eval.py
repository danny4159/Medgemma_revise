"""iter_042 평가. E_M0/E_C completion을 verify_completion으로 재검증한 뒤 집계한다 (D는 평가에 사용하지 않음).
python pg42_eval.py --out results/iter_042/eval/report_E.json   (기존 파일 덮어쓰기 거부)
결정 규칙은 plan.md Evaluation 그대로 구현하며 결과를 보고 바꾸지 않는다.
"""
import argparse
import hashlib
import json
import os
import sys

import numpy as np

import pg39_spec as S39
import pg41_run as R
import pg42_spec as S

OUT = "results/iter_042"


def sha_file(p):
    return R.file_sha(p)


def load_model(model):
    req = f"{OUT}/requests/requests_E_{model}.jsonl"
    proto = f"{OUT}/protocol/protocol_E_{model}.json"
    recs = R.verify_completion(f"{OUT}/gen/E_{model}", req, proto)
    pdig, p = R.verify_protocol(proto, req)
    want_ad = None if model == "M0" else "419ae81f5ef455d39742b158537373da6e26061b362d13205ab28b4a50905ba8"
    if (p.get("adapter") or {}).get("digest") != want_ad:
        raise R.RunError(f"adapter mismatch for {model}")
    return {(r["patient"], r["cond"]): r for r in recs}, pdig


def parsed(rec, cond):
    if cond == "P":
        return {"p": S.parse_P(rec["suffix_text_raw"], rec["ended_eos"])}
    return S.parse_G(rec["suffix_text_raw"], rec["ended_eos"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("output exists")
    man = [json.loads(l) for l in open(f"{OUT}/data/manifest_private.jsonl")]
    man = [m for m in man if m["set"] == "E"]
    pos = [m for m in man if m["group"] == "pos"]
    neg = [m for m in man if m["group"] == "neg"]
    R0, d0 = load_model("M0")
    RC, dC = load_model("C")
    for m in man:
        for cond in S.CONDS:
            assert (m["PatientID"], cond) in R0 and (m["PatientID"], cond) in RC
    PR = {"M0": {}, "C": {}}
    for mod, RR in (("M0", R0), ("C", RC)):
        for (pid, cond), rec in RR.items():
            PR[mod][(pid, cond)] = parsed(rec, cond)

    def cls_boxes(pid, name):
        """name: M0_short, M0_neutral, C_short, C_neutral, gate_P0, gate_PC -> (cls, boxes)"""
        if name.startswith("gate_"):
            pl = PR["M0" if name == "gate_P0" else "C"][(pid, "P")]["p"]
            c = PR["C"][(pid, "G_neutral")]
            return S.gate_output(pl, c["cls"], c["boxes"])
        mod, cond = name.split("_")
        r = PR[mod][(pid, "G_" + cond)]
        return r["cls"], r["boxes"]
    names = ["M0_short", "M0_neutral", "C_short", "C_neutral", "gate_P0", "gate_PC"]
    P = {n: [] for n in names}
    N = {n: [] for n in names}
    for m in pos:
        h, w = m["image_meta"]["h"], m["image_meta"]["w"]
        gt = S39.gt_to_canvas(m["gt_boxes_xyxy_norm"]["qA"], h, w)
        for n in names:
            c, b = cls_boxes(m["PatientID"], n)
            P[n].append(S.score_pos(c, b, gt))
    for m in neg:
        for n in names:
            c, _ = cls_boxes(m["PatientID"], n)
            N[n].append(S.score_neg(c))
    arr = lambda D, n, k: np.array([float(x[k]) for x in D[n]])
    rep = {"n_pos": len(pos), "n_neg": len(neg), "systems": {}, "presence": {}, "compare": {}, "sensitivity": {}, "decision": {}}
    for n in names:
        fb = int(sum(x["false_box"] for x in N[n]))
        inv = int(sum(x["invalid"] for x in N[n]))
        ve = int(sum(x["valid_empty"] for x in N[n]))
        cf = int(sum(x["conservative_fail"] for x in N[n]))
        rep["systems"][n] = {
            "pos": {"f1_03": S.boot_mean(arr(P, n, "f1_03"), 0.95), "f1_05": float(arr(P, n, "f1_05").mean()),
                    "recall_03": float(arr(P, n, "recall_03").mean()), "fp_per_patient": float(arr(P, n, "fp_03").mean()),
                    "invalid": int(sum(x["invalid"] for x in P[n])), "empty": int(sum(x["empty"] for x in P[n]))},
            "neg": {"false_box": [fb, len(neg), S.wilson(fb, len(neg))], "valid_empty": [ve, len(neg), S.wilson(ve, len(neg))],
                    "invalid": [inv, len(neg), S.wilson(inv, len(neg))], "conservative_fail": [cf, len(neg), S.wilson(cf, len(neg))]}}
    # grounding invalid rate over all E requests (G_neutral, C) and (G_short)
    def inv_all(mod, cond):
        k = sum(PR[mod][(m["PatientID"], "G_" + cond)]["cls"] == "invalid" for m in man)
        return [int(k), len(man), S.wilson(k, len(man))]
    rep["grounding_invalid_all_E"] = {f"{mod}_{c}": inv_all(mod, c) for mod in ("M0", "C") for c in ("short", "neutral")}
    rep["lenient_false_box"] = {f"{mod}_{c}": [int(sum(PR[mod][(m["PatientID"], "G_" + c)]["lenient_nonempty"] for m in neg)), len(neg)]
                                for mod in ("M0", "C") for c in ("short", "neutral")}
    rep["finish_all_eos"] = {mod: bool(all(r["ended_eos"] for r in RR.values())) for mod, RR in (("M0", R0), ("C", RC))}
    for mod in ("M0", "C"):
        pl_pos = [PR[mod][(m["PatientID"], "P")]["p"] for m in pos]
        pl_neg = [PR[mod][(m["PatientID"], "P")]["p"] for m in neg]
        sens, spec = pl_pos.count("yes"), pl_neg.count("no")
        rep["presence"][mod] = {"sensitivity": [sens, len(pos), S.wilson(sens, len(pos))],
                                "specificity": [spec, len(neg), S.wilson(spec, len(neg))],
                                "invalid_pos": pl_pos.count("invalid"), "invalid_neg": pl_neg.count("invalid")}

    def cmp(a_, b_, level):
        return {"pos_f1_03_diff": S.boot_diff(arr(P, a_, "f1_03"), arr(P, b_, "f1_03"), level),
                "neg_false_box_diff": S.boot_diff(arr(N, a_, "false_box"), arr(N, b_, "false_box"), level)}
    for c in ("short", "neutral"):
        rep["compare"][f"C_minus_M0_{c}_ci975"] = cmp(f"C_{c}", f"M0_{c}", 0.975)
    for n in ("C_neutral", "gate_P0", "gate_PC", "M0_short", "M0_neutral"):
        rep["compare"][f"{n}_minus_C_short_ci95"] = cmp(n, "C_short", 0.95)
    for n in ("gate_P0", "gate_PC"):
        rep["compare"][f"{n}_minus_C_neutral_ci95"] = cmp(n, "C_neutral", 0.95)
    # 사전 고정 민감도: 양성 hedge 제외, 음성 명시적 'pleural effusion'만
    hp = np.array([not m["flags"]["hedged"] for m in pos])
    ex_neg = np.array([not m["flags"]["bare_effusion"] for m in neg])
    rep["sensitivity"] = {"n_pos_nonhedged": int(hp.sum()), "n_neg_explicit_pleural": int(ex_neg.sum()),
                          "pos_f1_03_nonhedged": {n: float(arr(P, n, "f1_03")[hp].mean()) for n in names},
                          "neg_false_box_explicit_pleural": {n: [int(arr(N, n, "false_box")[ex_neg].sum()), int(ex_neg.sum())] for n in names}}
    # ---- 사전 고정 결정 규칙 ----
    fb = {n: rep["systems"][n]["neg"]["false_box"][2] for n in names}  # [p, lo, hi]
    f1 = {n: rep["systems"][n]["pos"]["f1_03"]["mean"] for n in names}
    dec = {"simple_solution": {}, "pilot_gate": {}, "adaptation_worsening": {}}
    for n in ("C_neutral", "gate_P0", "gate_PC"):
        c = rep["compare"][f"{n}_minus_C_short_ci95"]
        red = -c["neg_false_box_diff"]["mean"]
        red_lo = -c["neg_false_box_diff"]["hi"]
        dec["simple_solution"][n] = {"fb_reduction": red, "fb_reduction_ci_lo": red_lo, "f1_diff_ci_lo": c["pos_f1_03_diff"]["lo"],
                                     "fb_wilson_hi": fb[n][2],
                                     "supported": bool(red >= 0.15 and red_lo > 0 and c["pos_f1_03_diff"]["lo"] >= -0.05),
                                     "residual_fb_wilson_hi_le_0.20": bool(fb[n][2] <= 0.20)}
    cn = "C_neutral"
    core = bool(f1[cn] >= 0.40 and rep["grounding_invalid_all_E"]["C_neutral"][2][0] <= 0.05 and fb[cn][0] >= 0.25 and fb[cn][1] > 0.10)
    dec["pilot_gate"]["C_neutral_core"] = {"pos_f1": f1[cn], "invalid_rate": rep["grounding_invalid_all_E"]["C_neutral"][2][0],
                                            "false_box": fb[cn][0], "false_box_wilson_lo": fb[cn][1], "passed": core}
    for g in ("gate_P0", "gate_PC"):
        loss = -rep["compare"][f"{g}_minus_C_neutral_ci95"]["pos_f1_03_diff"]["mean"]
        loss_lo = -rep["compare"][f"{g}_minus_C_neutral_ci95"]["pos_f1_03_diff"]["hi"]
        a_ = bool(fb[g][0] >= 0.25 and fb[g][1] > 0.10)
        b_ = bool(loss >= 0.10 and loss_lo > 0)
        dec["pilot_gate"][g] = {"a_residual_false_box": a_, "b_positive_loss": b_, "loss": loss, "loss_ci_lo": loss_lo, "passed": a_ or b_}
    dec["pilot_gate"]["passed_all"] = bool(core and all(dec["pilot_gate"][g]["passed"] for g in ("gate_P0", "gate_PC")))
    for c in ("short", "neutral"):
        d = rep["compare"][f"C_minus_M0_{c}_ci975"]["neg_false_box_diff"]
        dec["adaptation_worsening"][c] = {"diff": d["mean"], "ci_lo": d["lo"], "supported": bool(d["mean"] >= 0.15 and d["lo"] > 0)}
    dec["competence"] = {"C_short_pos_f1": f1["C_short"], "C_neutral_pos_f1": f1["C_neutral"], "C_neutral_ge_0.40": bool(f1["C_neutral"] >= 0.40)}
    if any(v["supported"] and v["residual_fb_wilson_hi_le_0.20"] for v in dec["simple_solution"].values()):
        dec["outcome"] = "simple_solution_supported_hold_method_investment"
    elif dec["pilot_gate"]["passed_all"]:
        dec["outcome"] = "minimal_method_pilot_candidate"
    else:
        dec["outcome"] = "inconclusive_or_negative_hold"
    rep["decision"] = dec
    rep["provenance"] = {"eval_source_sha256": sha_file("pg42_eval.py"), "spec_sha256": sha_file("pg42_spec.py"),
                         "manifest_sha256": sha_file(f"{OUT}/data/manifest_private.jsonl"),
                         "selection_lock_sha256": sha_file(f"{OUT}/data/selection_lock.json"),
                         "protocol_digest": {"M0": d0, "C": dC},
                         "completion_sha256": {m: sha_file(f"{OUT}/gen/E_{m}/completion.json") for m in ("M0", "C")},
                         "bootstrap": {"B": 10000, "seed": 20261001}}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    tmp = a.out + f".{os.getpid()}.tmp"
    json.dump(rep, open(tmp, "w"), indent=1)
    os.replace(tmp, a.out)
    json.dump({"per_patient": {n: {"pos": P[n], "neg": N[n]} for n in names}, "pos_ids": [m["PatientID"] for m in pos],
               "neg_ids": [m["PatientID"] for m in neg]}, open(a.out.replace(".json", "_per_patient.json"), "x"), indent=0)
    print(json.dumps({"n_pos": rep["n_pos"], "n_neg": rep["n_neg"], "outcome": dec["outcome"]}))


if __name__ == "__main__":
    main()
