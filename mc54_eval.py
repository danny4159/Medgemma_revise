"""iter_054 평가: raw record → 시스템별 답/margin → 지표, orientation O, G = O − max_b S_b, 연결 성분 cluster bootstrap, LOCO, 의심 제외, 최악/최선 범위.
평가 입력은 verify_completion(main)으로 재검증한 raw만 쓴다. 정답·pair 대응은 eval_manifest에서만 읽는다.
사용: python mc54_eval.py --out-dir results/iter_054/eval   (eval_lock.json이 현재 평가 소스·raw와 일치해야 실행)"""
import argparse
import glob
import json
import os
import sys

import numpy as np

import mc54_run as RUN
import mc54_spec as S

REQ = "results/iter_054/data/requests.jsonl"
PROTO = "results/iter_054/protocol/protocol_main.json"
MAIN = "results/iter_054/raw/main"
EVM = "results/iter_054/data/eval_manifest.json"
BASE = ["MC_orig", "MC_swap", "GD_orig", "GD_swap", "GD_avg", "GD_cal", "PS", "PS_cal"]
NREP, SEED = 10000, 54
PRIMARY_PARSER = "strict"
EVAL_CODE = ["mc54_eval.py", "mc54_decide.py", "mc54_verify.py", "mc54_spec.py", "mc54_run.py"]


def mc_letter(rec, order, parser):
    txt = rec["payload"]["suffix_text_raw"]
    ok_eos = rec["payload"]["ended_eos"]
    shown = S.parse_strict(txt) if parser == "strict" else S.parse_official_manual(txt)
    if not ok_eos:
        shown = "-"  # 비EOS 최종 출력은 invalid로 유지
    return S.to_canonical_letter(shown, order)


def observations(recs, evm):
    """pair → {mc:{(slot,order):rec}, gd:{...}, ps:{(slot,opt):rec}}"""
    obs = {}
    for r in recs:
        m = evm["requests"][r["request_id"]]
        o = obs.setdefault(m["pair"], {"mc": {}, "gd": {}, "ps": {}})
        key = (m["slot"], m["order"]) if m["kind"] != "ps" else (m["slot"], m["option"])
        assert key not in o[m["kind"]], (m, key)
        o[m["kind"]][key] = r
    return obs


def systems_for_pair(o, parser):
    """returns dict system → {'ans':(a1,a2) canonical, 'margin':(m1,m2) or None}; text-only systems under 'T_*'."""
    out = {}
    for order in S.ORDERS:
        out[f"MC_{order}"] = {"ans": tuple(mc_letter(o["mc"][(s, order)], order, parser) for s in ("im1", "im2")), "margin": None}
        out[f"T_MC_{order}"] = {"ans": (mc_letter(o["mc"][("text", order)], order, parser),) * 2, "margin": None}
    gm = {}
    for order in S.ORDERS:
        for s in ("im1", "im2", "text"):
            gm[(s, order)] = S.canonical_margin(o["gd"][(s, order)]["payload"]["shown_margin"], order)
    for order in S.ORDERS:
        mg = (gm[("im1", order)], gm[("im2", order)])
        out[f"GD_{order}"] = {"ans": tuple(S.pick_from_margin(x) for x in mg), "margin": mg}
        t = gm[("text", order)]
        out[f"T_GD_{order}"] = {"ans": (S.pick_from_margin(t),) * 2, "margin": (t, t)}
    avg = tuple((gm[(s, "orig")] + gm[(s, "swap")]) / 2 for s in ("im1", "im2"))
    tavg = (gm[("text", "orig")] + gm[("text", "swap")]) / 2
    out["GD_avg"] = {"ans": tuple(S.pick_from_margin(x) for x in avg), "margin": avg}
    out["T_GD_avg"] = {"ans": (S.pick_from_margin(tavg),) * 2, "margin": (tavg, tavg)}
    cal = tuple(a - tavg for a in avg)
    out["GD_cal"] = {"ans": tuple(S.pick_from_margin(x) for x in cal), "margin": cal}
    ps = {k: o["ps"][k]["payload"]["mean_ll"] for k in o["ps"]}
    d = tuple(ps[(s, "A")] - ps[(s, "B")] for s in ("im1", "im2"))
    dt = ps[("text", "A")] - ps[("text", "B")]
    out["PS"] = {"ans": tuple(S.pick_from_margin(x) for x in d), "margin": d}
    out["T_PS"] = {"ans": (S.pick_from_margin(dt),) * 2, "margin": (dt, dt)}
    c = tuple(x - dt for x in d)
    out["PS_cal"] = {"ans": tuple(S.pick_from_margin(x) for x in c), "margin": c}
    return out


def orient(margin, truth):
    """정답 A 영상 margin vs 정답 B 영상 margin. truth=(t1,t2) 가 서로 다를 때만."""
    if truth[0] == truth[1] or margin is None:
        return None
    ia = 0 if truth[0] == "A" else 1
    return S.orientation(margin[ia], margin[1 - ia])


def per_pair_table(recs, evm, parser=PRIMARY_PARSER):
    obs = observations(recs, evm)
    pairs = sorted(obs)
    tab = {}
    for p in pairs:
        pm = evm["pairs"][p]
        truth = (pm["im1_correct"], pm["im2_correct"])
        sy = systems_for_pair(obs[p], parser)
        row = {"truth": truth, "component": pm["component"], "suspect": pm["suspect_flag"], "systems": {}}
        for name, v in sy.items():
            c1, i1, c2, i2, conf = S.set_outcome(v["ans"][0], v["ans"][1], truth[0], truth[1])
            row["systems"][name] = {"ans": v["ans"], "c1": c1, "c2": c2, "i1": int(i1), "i2": int(i2), "conf": conf, "set": int(c1 and c2),
                                    "near_tie": (None if v["margin"] is None else int(any(abs(x) < 0.125 for x in v["margin"]))),
                                    "margin": v["margin"]}
        row["orient"] = {n: orient(sy[n]["margin"], truth) for n in ("GD_avg", "GD_cal", "PS", "PS_cal", "T_GD_avg", "T_PS")}
        tab[p] = row
    return tab


def summarize(tab, names):
    pairs = sorted(tab)
    N = len(pairs)
    out = {}
    for n in names:
        v = [tab[p]["systems"][n] for p in pairs]
        nvalid_pair = sum(1 for x in v if not x["i1"] and not x["i2"])
        conf = sum(x["conf"] for x in v)
        out[n] = {"individual_acc": sum(x["c1"] + x["c2"] for x in v) / (2 * N), "set_acc": sum(x["set"] for x in v) / N,
                  "invalid_or_abstain_rate": sum(x["i1"] + x["i2"] for x in v) / (2 * N), "image_coverage": 1 - sum(x["i1"] + x["i2"] for x in v) / (2 * N),
                  "valid_pair_coverage": nvalid_pair / N, "same_answer_rate_all_pairs": conf / N,
                  "confusion_among_valid_pairs": (conf / nvalid_pair if nvalid_pair else None),
                  "near_tie_slots": (None if v[0]["near_tie"] is None else sum(x["near_tie"] for x in v))}
    return out


def pair_vectors(tab, pairs):
    """bootstrap용 pair 수준 벡터."""
    vec = {}
    for n in BASE:
        vec[f"S:{n}"] = np.array([tab[p]["systems"][n]["set"] for p in pairs], float)
    vec["ACC:GD_avg"] = np.array([(tab[p]["systems"]["GD_avg"]["c1"] + tab[p]["systems"]["GD_avg"]["c2"]) / 2 for p in pairs], float)
    vec["ACC:T_GD_avg"] = np.array([(tab[p]["systems"]["T_GD_avg"]["c1"] + tab[p]["systems"]["T_GD_avg"]["c2"]) / 2 for p in pairs], float)
    vec["O:GD_avg"] = np.array([tab[p]["orient"]["GD_avg"] for p in pairs], float)
    return vec


def stats_from(means):
    """means: dict vec-key → 값. returns O, G, 각 baseline S, ΔS vs MC_orig, 정확도 차."""
    s = {n: means[f"S:{n}"] for n in BASE}
    mx = max(s.values())
    o = means["O:GD_avg"]
    d = {"O": o, "G": o - mx, "max_S": mx, "ACC_gd_minus_text": means["ACC:GD_avg"] - means["ACC:T_GD_avg"]}
    d.update({f"S:{n}": s[n] for n in BASE})
    d.update({f"dS:{n}": s[n] - s["MC_orig"] for n in BASE})
    d.update({f"O_minus_S:{n}": o - s[n] for n in BASE})
    return d


def cluster_bootstrap(tab, pairs, nrep=NREP, seed=SEED):
    comps = sorted({tab[p]["component"] for p in pairs})
    K = len(comps)
    ci = {c: i for i, c in enumerate(comps)}
    vec = pair_vectors(tab, pairs)
    N_k = np.zeros(K)
    A = {k: np.zeros(K) for k in vec}
    for j, p in enumerate(pairs):
        k = ci[tab[p]["component"]]
        N_k[k] += 1
        for key, v in vec.items():
            A[key][k] += v[j]
    rs = np.random.RandomState(seed)
    reps = []
    for _ in range(nrep):
        cnt = np.bincount(rs.randint(0, K, size=K), minlength=K).astype(float)
        den = cnt @ N_k
        reps.append(stats_from({k: (cnt @ A[k]) / den for k in vec}))
    keys = reps[0].keys()
    res = {}
    for k in keys:
        a = np.array([r[k] for r in reps])
        res[k] = {"ci95": [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))], "ci975": [float(np.percentile(a, 1.25)), float(np.percentile(a, 98.75))]}
    return res, K


def point(tab, pairs):
    vec = pair_vectors(tab, pairs)
    return stats_from({k: float(np.mean(v)) for k, v in vec.items()})


def loco(tab, pairs):
    comps = sorted({tab[p]["component"] for p in pairs})
    rows = []
    for c in comps:
        sub = [p for p in pairs if tab[p]["component"] != c]
        s = point(tab, sub)
        rows.append({"dropped_component": c, "n_pairs_dropped": len(pairs) - len(sub), "O": s["O"], "G": s["G"],
                     "ACC_gd_minus_text": s["ACC_gd_minus_text"]})
    return rows


def missing_range(point_s, n_avail, n_total, o_pairs_avail):
    """미확보 pair를 최악/최선으로 채웠을 때 O, G의 가능한 범위 (모든 시스템 S는 0 또는 1 가능, O는 0 또는 1)."""
    k = n_total - n_avail
    mxS = point_s["max_S"] * n_avail
    O_sum = point_s["O"] * n_avail
    lo = (O_sum) / n_total - (mxS + k) / n_total
    hi = (O_sum + k) / n_total - (mxS) / n_total
    return {"n_missing_pairs": k, "O_range": [O_sum / n_total, (O_sum + k) / n_total], "G_range": [lo, hi]}


def lock_check(lock_path):
    lk = json.load(open(lock_path))
    for f, h in lk["eval_code"].items():
        if RUN.file_sha(f) != h:
            raise SystemExit(f"eval lock violated: {f} changed")
    if RUN.file_sha(EVM) != lk["eval_manifest_sha256"] or RUN.file_sha(os.path.join(MAIN, "completion.json")) != lk["completion_sha256"]:
        raise SystemExit("eval lock violated: manifest/completion")
    return lk


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--lock", required=True)
    a = ap.parse_args()
    lk = lock_check(a.lock)
    recs = RUN.verify_completion(MAIN, REQ, PROTO)  # raw–protocol–요청 연결 재검증
    evm = json.load(open(EVM))
    os.makedirs(a.out_dir, exist_ok=True)
    rep_path = os.path.join(a.out_dir, "report.json")
    if os.path.exists(rep_path):
        sys.exit("report exists; refusing to overwrite")
    tab = per_pair_table(recs, evm, PRIMARY_PARSER)
    tab_off = per_pair_table(recs, evm, "official")
    pairs = sorted(tab)
    names_all = BASE + ["T_MC_orig", "T_MC_swap", "T_GD_orig", "T_GD_swap", "T_GD_avg", "T_PS"]
    summ = summarize(tab, names_all)
    summ_off = summarize(tab_off, ["MC_orig", "MC_swap", "T_MC_orig", "T_MC_swap"])
    pt = point(tab, pairs)
    boot, K = cluster_bootstrap(tab, pairs)
    n_comp = K
    comp_sizes = {}
    for p in pairs:
        comp_sizes[tab[p]["component"]] = comp_sizes.get(tab[p]["component"], 0) + 1
    max_share = max(comp_sizes.values()) / len(pairs)
    # O 계열 및 회귀 검사
    orient = {n: float(np.mean([tab[p]["orient"][n] for p in pairs])) for n in ("GD_avg", "GD_cal", "PS", "PS_cal", "T_GD_avg", "T_PS")}
    cal_eq = all(tab[p]["orient"]["GD_cal"] == tab[p]["orient"]["GD_avg"] for p in pairs)
    pscal_eq = all(tab[p]["orient"]["PS_cal"] == tab[p]["orient"]["PS"] for p in pairs)
    text_half = all(tab[p]["orient"]["T_GD_avg"] == 0.5 and tab[p]["orient"]["T_PS"] == 0.5 for p in pairs)
    n_same_truth = sum(tab[p]["truth"][0] == tab[p]["truth"][1] for p in pairs)
    lo = loco(tab, pairs)
    nosus = [p for p in pairs if not tab[p]["suspect"]]
    pt_nosus = point(tab, nosus)
    # 사전 의심 제외 민감도: 점추정만 (CI는 보조)
    rng_missing = missing_range(pt, len(pairs), len(evm["pairs"]), None)
    # MC 출력 형식 통계
    mc_recs = [r for r in recs if r["kind"] == "mc"]
    parse_diff = sum(S.parse_strict(r["payload"]["suffix_text_raw"]) != S.parse_official_manual(r["payload"]["suffix_text_raw"]) for r in mc_recs)
    mc_stats = {"n_mc": len(mc_recs), "n_retry": sum(len(r["payload"]["attempts"]) > 1 for r in mc_recs),
                "n_non_eos_final": sum(not r["payload"]["ended_eos"] for r in mc_recs), "strict_vs_official_differ": parse_diff,
                "max_output_tokens": max(r["payload"]["n_output_tokens"] for r in mc_recs)}
    comp = json.load(open(os.path.join(MAIN, "completion.json")))
    report = {"n_pairs_evaluated": len(pairs), "n_pairs_official": len(evm["pairs"]), "n_components": n_comp, "max_component_share": max_share,
              "component_inference_limited": bool(n_comp < 20 or max_share > 0.20), "parser_primary": PRIMARY_PARSER,
              "systems": summ, "systems_official_parser_sensitivity": summ_off, "orientation_point": orient, "orientation_regression": {
                  "GD_cal_equals_GD_avg_per_pair": cal_eq, "PS_cal_equals_PS_per_pair": pscal_eq, "text_only_orientation_exactly_half": text_half,
                  "n_pairs_same_truth_letter_excluded_from_orientation": n_same_truth},
              "point": pt, "bootstrap_cluster": boot, "bootstrap_config": {"n_rep": NREP, "seed": SEED, "unit": "connected component (shared image/PMC/pixel)", "n_units": K},
              "loco": lo, "loco_summary": {"O_min": min(r["O"] for r in lo), "G_min": min(r["G"] for r in lo), "G_max": max(r["G"] for r in lo),
                                           "ACC_min": min(r["ACC_gd_minus_text"] for r in lo)},
              "suspect_excluded": {"n_excluded": len(pairs) - len(nosus), "O": pt_nosus["O"], "G": pt_nosus["G"], "ACC_gd_minus_text": pt_nosus["ACC_gd_minus_text"]},
              "missing_pairs_range": rng_missing, "mc_stats": mc_stats,
              "cost": {k: comp.get(k) for k in ("sum_request_wall_s_all_records", "peak_mem_reserved_gb_max", "by_kind_mean_wall_s", "n_mc_retries",
                                               "n_forward_calls", "n_generate_calls_all_attempts", "wall_s_this_attempt")},
              "cost_all_attempts": comp["cost_all_attempts"], "cost_this_dir_only": comp["cost_this_dir_only"],
              "provenance": {"eval_lock_sha256": RUN.file_sha(a.lock), "eval_code": lk["eval_code"], "completion_sha256": lk["completion_sha256"],
                             "eval_manifest_sha256": lk["eval_manifest_sha256"], "protocol_main_sha256": RUN.file_sha(PROTO)}}
    pp = {p: {"truth": tab[p]["truth"], "component": tab[p]["component"], "suspect": tab[p]["suspect"], "orient": tab[p]["orient"],
              "systems": {n: {k: v for k, v in tab[p]["systems"][n].items()} for n in names_all}} for p in pairs}
    tmp = rep_path + f".{os.getpid()}.tmp"
    with open(os.path.join(a.out_dir, "per_pair.json"), "x") as f:
        json.dump(pp, f)
    json.dump(report, open(tmp, "w"), indent=1)
    os.replace(tmp, rep_path)
    print(json.dumps({"n": len(pairs), "O": pt["O"], "G": pt["G"], "max_S": pt["max_S"]}))


if __name__ == "__main__":
    main()
