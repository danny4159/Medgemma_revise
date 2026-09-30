"""iter_039 평가·판정. 입력: 완료 검증(verify_completion)을 통과한 생성 결과 + 잠긴 manifest. 결과는 새 경로에만 쓴다.

python pg39_eval.py --stage E96 --gen results/iter_039/gen/E96 --requests results/iter_039/requests/requests_E96.jsonl \
   --protocol results/iter_039/protocol/protocol_E96.json --out results/iter_039/eval/report_E96.json
"""
import argparse
import json
import math
import os
import sys

import numpy as np

import pg39_run as R
import pg39_spec as S
from rsna_diag import metrics, parse

MANIFEST = "results/iter_039/data/manifest_private.jsonl"
B_BOOT = 10000
SEED = 20260930
SMALL_AREA = 0.02  # 사전 고정: 영상 면적 대비 GT box 면적 2% 미만이면 small


def load_manifest(subsets):
    out = {}
    for l in open(MANIFEST):
        r = json.loads(l)
        if r["subset"] in subsets:
            out[r["PatientID"]] = r
    return out


def gt_canvas(m, key="gt_boxes_xyxy_norm"):
    h, w = m["image_meta"]["h"], m["image_meta"]["w"]
    return {k: S.gt_to_canvas(m[key][k], h, w) for k in ("qA", "qB")}


def ci(x, level=0.95):
    x = np.asarray(x, float)
    idx = metrics.bootstrap_indices(len(x), B_BOOT, SEED)
    m = x[idx].mean(axis=1)
    a = (1 - level) / 2 * 100
    return [float(x.mean()), float(np.percentile(m, a)), float(np.percentile(m, 100 - a))]


def pci(a, b, level=0.95):
    return ci(np.asarray(a, float) - np.asarray(b, float), level)


def patient_table(recs, man):
    """record -> {patient: {cond: {...}}}. invalid는 f1=0 (별도 집계)."""
    tab = {}
    for r in recs:
        m = man[r["patient"]]
        gt = gt_canvas(m)
        allowed = set(r["targets"])
        p = S.parse_ids(r["suffix_text_raw"], r["ended_eos"], allowed)
        sc = S.score_request(p["status"], p["groups"], r["targets"], gt)
        ent = {"status": p["status"], "valid": p["status"] in parse.VALID, "eos": r["ended_eos"],
               "other_id_boxes": p["other_id_boxes"], "scores": sc, "n_out": r["n_output_tokens"],
               "wall": r["wall_s"], "peak_gb": r["peak_mem_alloc_gb_max"], "caps_used": len(r["attempts"]),
               "flags": p["flags"], "groups": p["groups"]}
        if r["cond"] in ("J-long", "J-reverse", "J-short"):
            ent["swap_f1_03"] = S.swap_score(p["groups"], gt) if ent["valid"] else 0.0
        tab.setdefault(r["patient"], {}).setdefault(r["cond"], []).append((tuple(r["targets"]), ent))
    return tab


def pat_score(tab, pid, cond, key="f1_03"):
    v = []
    for tg, e in tab[pid][cond]:
        for t in tg:
            v.append(e["scores"][t][key])
    return float(np.mean(v))


def sent_scores(tab, pid, cond, key="f1_03"):
    return {t: e["scores"][t][key] for tg, e in tab[pid][cond] for t in tg}


def wilson_bounds(k, n):
    return metrics.wilson(k, n)


def evaluate(recs, man):
    tab = patient_table(recs, man)
    pids = sorted(tab)
    n = len(pids)
    conds = ["I-long", "J-long", "J-reverse", "C-long", "I-short", "J-short"]
    X = {c: np.array([pat_score(tab, p, c) for p in pids]) for c in conds}
    X5 = {c: np.array([pat_score(tab, p, c, "f1_05") for p in pids]) for c in conds}
    rep = {"n_patients": n, "n_requests": len(recs)}
    rep["mean_f1_03"] = {c: ci(X[c]) for c in conds}
    rep["mean_f1_05"] = {c: ci(X5[c]) for c in conds}
    rep["delta_long_I_minus_J"] = {"ci975": pci(X["I-long"], X["J-long"], 0.975), "ci95": pci(X["I-long"], X["J-long"])}
    rep["delta_short_I_minus_J"] = {"ci975": pci(X["I-short"], X["J-short"], 0.975), "ci95": pci(X["I-short"], X["J-short"])}
    rep["mechanism_exploratory_ci95"] = {
        "I-long_minus_C-long": pci(X["I-long"], X["C-long"]), "C-long_minus_J-long": pci(X["C-long"], X["J-long"]),
        "J-long_minus_J-reverse": pci(X["J-long"], X["J-reverse"]),
        "I-long_minus_J-reverse": pci(X["I-long"], X["J-reverse"])}
    # 개별 능력 기준
    full_i = sum(any(v >= 1.0 - 1e-12 for v in sent_scores(tab, p, "I-long").values()) for p in pids)
    rep["capability"] = {"I_long_mean_f1_03": rep["mean_f1_03"]["I-long"], "patients_with_ge1_sentence_f1_eq_1": full_i}
    # 형식·길이
    fmt = {}
    for c in conds:
        ents = [e for p in pids for _, e in tab[p][c]]
        st = {}
        for e in ents:
            st[e["status"]] = st.get(e["status"], 0) + 1
        fmt[c] = {"n": len(ents), "valid": sum(e["valid"] for e in ents) / len(ents),
                  "truncated_final": sum(not e["eos"] for e in ents) / len(ents),
                  "retried_cap": sum(e["caps_used"] > 1 for e in ents) / len(ents), "status_counts": st,
                  "other_id_boxes_reqs": sum(e["other_id_boxes"] > 0 for e in ents)}
    rep["format"] = fmt
    tot = sum(f["n"] for f in fmt.values())
    rep["format_family"] = {
        "long_valid": float(np.mean([e["valid"] for p in pids for c in ("I-long", "J-long", "J-reverse", "C-long") for _, e in tab[p][c]])),
        "short_valid": float(np.mean([e["valid"] for p in pids for c in ("I-short", "J-short") for _, e in tab[p][c]])),
        "unresolved_truncation_rate": float(sum(not e["eos"] for p in pids for c in conds for _, e in tab[p][c]) / tot)}
    # 유효 subset 민감도 (사후 조건부 분석)
    def allvalid(p, cs):
        return all(e["valid"] and e["eos"] for c in cs for _, e in tab[p][c])
    sens = {}
    for fam, cs in (("long", ("I-long", "J-long")), ("short", ("I-short", "J-short"))):
        keep = [i for i, p in enumerate(pids) if allvalid(p, cs)]
        if len(keep) >= 5:
            a, b = X[f"I-{fam}"][keep], X[f"J-{fam}"][keep]
            sens[fam] = {"n": len(keep), "delta_ci95": pci(a, b), "delta_ci975": pci(a, b, 0.975)}
        else:
            sens[fam] = {"n": len(keep), "delta_ci95": None}
    rep["valid_subset_sensitivity"] = sens
    # 문장 단위 손실/회복 (I 완전 성공 기준)
    def sent_pairs(cj):
        a = np.array([[sent_scores(tab, p, "I-long")[t], sent_scores(tab, p, cj)[t]] for p in pids for t in ("qA", "qB")])
        return a
    for cj in ("J-long", "J-reverse", "C-long"):
        a = sent_pairs(cj)
        i_ok, j_ok = a[:, 0] >= 1 - 1e-12, a[:, 1] >= 1 - 1e-12
        rep[f"loss_recovery_I_vs_{cj}"] = {
            "sentences": int(len(a)), "I_full_success": int(i_ok.sum()), "success_lost": int((i_ok & ~j_ok).sum()),
            "success_gained": int((~i_ok & j_ok).sum()), "lost_rate_among_I_success": float((i_ok & ~j_ok).sum() / max(1, i_ok.sum())),
            "discordant": int((i_ok != j_ok).sum()), "discordance_wilson95": list(wilson_bounds(int((i_ok != j_ok).sum()), len(a)))}
    # 그룹 교환 oracle
    for c in ("J-long", "J-reverse", "J-short"):
        orig = X[c]
        swp = np.array([max(pat_score(tab, p, c), tab[p][c][0][1]["swap_f1_03"]) for p in pids])
        rep[f"swap_oracle_{c}"] = {"orig": float(orig.mean()), "best_of_swap": float(swp.mean()),
                                   "gain_ci95": pci(swp, orig), "patients_improved": int((swp > orig + 1e-12).sum())}
    # 층별
    man_p = {p: man[p] for p in pids}
    cross = {p: S.cross_iou_max(*(gt_canvas(man_p[p])[k] for k in ("qA", "qB"))) for p in pids}
    def small(p):
        return any((b[2] - b[0]) * (b[3] - b[1]) < SMALL_AREA for k in ("qA", "qB") for b in man_p[p]["gt_boxes_xyxy_norm"][k])

    strata = {"multi_box": lambda p: any(len(man_p[p]["gt_boxes_xyxy_norm"][k]) > 1 for k in ("qA", "qB")),
              "share_group": lambda p: man_p[p]["stratum"].startswith("share1"),
              "small_box": small, "cross_iou_lt_0.1": lambda p: cross[p] < 0.1,
              "cross_iou_ge_0.1(overlap)": lambda p: cross[p] >= 0.1}
    rep["strata"] = {}
    for s, fn in strata.items():
        keep = [i for i, p in enumerate(pids) if fn(p)]
        d = {"n": len(keep)}
        if len(keep) >= 5:
            d["delta_long"] = pci(X["I-long"][keep], X["J-long"][keep])
            d["delta_short"] = pci(X["I-short"][keep], X["J-short"][keep])
            d["I_long"] = float(X["I-long"][keep].mean())
            sw = [max(X["J-long"][i], tab[pids[i]]["J-long"][0][1]["swap_f1_03"]) for i in keep]
            d["swap_gain_J_long"] = float(np.mean(sw) - X["J-long"][keep].mean())
        rep["strata"][s] = d
    # 오검출·미검출·빈 예측
    for c in ("I-long", "J-long", "I-short", "J-short"):
        sc = [e["scores"][t] for p in pids for tg, e in tab[p][c] for t in tg]
        rep[f"box_stats_{c}"] = {"recall_mean": float(np.mean([s["recall_03"] for s in sc])),
                                 "fp_per_sentence": float(np.mean([s["fp_03"] for s in sc])),
                                 "empty_pred_rate": float(np.mean([s["empty"] for s in sc])),
                                 "union_iou_mean": float(np.mean([s["union_iou"] for s in sc]))}
    # 비용 (환자 단위: 두 문장을 모두 처리)
    def cost(cs):
        return {"requests_per_patient": float(np.mean([sum(len(tab[p][c]) for c in cs) for p in pids])),
                "out_tokens_per_patient": float(np.mean([sum(e["n_out"] for c in cs for _, e in tab[p][c]) for p in pids])),
                "gen_wall_s_per_patient_sum": float(np.mean([sum(e["wall"] for c in cs for _, e in tab[p][c]) for p in pids])),
                "gen_wall_s_per_patient_parallel2_max": float(np.mean([max(e["wall"] for c in cs for _, e in tab[p][c]) for p in pids])),
                "peak_alloc_gb_max": float(max(e["peak_gb"] for p in pids for c in cs for _, e in tab[p][c]))}
    rep["cost"] = {"I-long(2 req)": cost(["I-long"]), "J-long(1 req)": cost(["J-long"]),
                   "I-short(2 req)": cost(["I-short"]), "J-short(1 req)": cost(["J-short"])}
    # extra annotation 방향 (양쪽 문장 모두 extra box가 있는 환자)
    keep = [i for i, p in enumerate(pids) if all(man_p[p]["extra_boxes_xyxy_norm"][k] for k in ("qA", "qB"))]
    ex = {"n": len(keep)}
    if len(keep) >= 5:
        def xscore(p, c):
            g = gt_canvas(man_p[p], "extra_boxes_xyxy_norm")
            v = []
            for tg, e in tab[p][c]:
                pr = S.score_request(e["status"], e["groups"], list(tg), g)
                v += [pr[t]["f1_03"] for t in tg]
            return float(np.mean(v))
        a = [xscore(pids[i], "I-long") for i in keep]
        b = [xscore(pids[i], "J-long") for i in keep]
        ex["delta_long_extra_gt"] = pci(a, b)
        ex["delta_long_official_gt_same_patients"] = pci(X["I-long"][keep], X["J-long"][keep])
    rep["extra_annotation_direction"] = ex
    rep["_per_patient"] = {p: {c: float(X[c][i]) for c in conds} for i, p in enumerate(pids)}
    return rep


def d_gate(rep):
    fam = rep["format_family"]
    long_ok = fam["long_valid"] >= 0.9
    short_ok = fam["short_valid"] >= 0.9
    trunc_ok = fam["unresolved_truncation_rate"] <= 0.02
    return {"long_valid_ge_0.90": long_ok, "short_valid_ge_0.90": short_ok, "unresolved_trunc_le_0.02": trunc_ok,
            "pass": bool(long_ok and short_ok and trunc_ok)}


def e96_decision(rep):
    cap = rep["capability"]
    i_mean, i_lo, i_hi = cap["I_long_mean_f1_03"][0], *cap["I_long_mean_f1_03"][1:]
    cap_ok = i_mean >= 0.40 and cap["patients_with_ge1_sentence_f1_eq_1"] >= 24
    dl = rep["delta_long_I_minus_J"]["ci95"]
    ds = rep["delta_short_I_minus_J"]["ci95"]
    fmt_ok = rep["format_family"]["long_valid"] >= 0.9 and rep["format_family"]["short_valid"] >= 0.9 \
        and rep["format_family"]["unresolved_truncation_rate"] <= 0.02
    hold = i_hi < 0.40 or (dl[2] < 0.10 and ds[2] < 0.10)
    a = dl[0] >= 0.10 and ds[0] > 0
    n = rep["n_patients"]
    hw = (dl[2] - dl[1]) / 2 * math.sqrt(n / 288.0)
    straddle = (i_lo < 0.40 <= i_hi) or (dl[1] < 0.10 <= dl[2])
    b = fmt_ok and straddle and hw <= 0.06
    expand = (not hold) and ((cap_ok and a) or b)
    return {"capability_met": bool(cap_ok), "criterion_a": bool(cap_ok and a), "criterion_b_uncertain_precision": bool(b),
            "projected_ci_halfwidth_at_288": hw, "hold": bool(hold), "expand_to_E288": bool(expand),
            "inputs": {"I_long": cap["I_long_mean_f1_03"], "delta_long_ci95": dl, "delta_short_ci95": ds}}


def f_decision(rep, sens_ok_min=0.05):
    cap = rep["capability"]
    cap_ok = cap["I_long_mean_f1_03"][0] >= 0.40 and cap["patients_with_ge1_sentence_f1_eq_1"] >= 24
    dl = rep["delta_long_I_minus_J"]["ci975"]
    ds = rep["delta_short_I_minus_J"]["ci95"]
    sv = rep["valid_subset_sensitivity"]["long"]
    content = sv.get("delta_ci95") is not None and sv["delta_ci95"][0] >= sens_ok_min and sv["delta_ci95"][1] > 0
    run = bool(cap_ok and dl[0] >= 0.10 and dl[1] > 0 and ds[0] > 0 and content)
    return {"run_F120": run, "capability_met": bool(cap_ok), "delta_long_ci975": dl, "delta_short_ci95": ds,
            "content_loss_not_explained_by_format": bool(content), "valid_subset_long": sv}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--gen", nargs="+", required=True)
    ap.add_argument("--requests", nargs="+", required=True)
    ap.add_argument("--protocol", nargs="+", required=True)
    ap.add_argument("--subsets", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("output exists")
    recs = []
    for g, rq, pr in zip(a.gen, a.requests, a.protocol):
        recs += R.verify_completion(g, rq, pr)
    man = load_manifest(set(a.subsets))
    if {r["patient"] for r in recs} != set(man):
        sys.exit("patients in records != manifest subsets")
    rep = evaluate(recs, man)
    rep["stage"] = a.stage
    rep["d_gate"] = d_gate(rep)
    if a.stage == "E96":
        rep["decision_E96"] = e96_decision(rep)
    if a.stage == "E288":
        rep["decision_F"] = f_decision(rep)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(rep, open(a.out, "w"), indent=1)
    print(json.dumps({k: rep[k] for k in rep if k not in ("_per_patient", "strata", "format", "cost")}, indent=1)[:6000])


if __name__ == "__main__":
    main()
