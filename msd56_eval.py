"""iter_056 평가: 구간 단위 confusion/BA/sens/spec/invalid, case-cluster bootstrap, coverage 층별, 비용, 사전 규칙 판정.

사용: python msd56_eval.py --split D|E --out-dir results/iter_056/eval_X --gen-dirs DIR[,DIR] [--model-tag medgemma]
- 완료 검증(요청 전수 존재·중복 없음)을 evaluator 안에서 강제한다. invalid는 해당 class의 오답.
- 판정 규칙 (사전 고정, plan Evaluation): basic_signal = (DENSE|O8) BA>=0.70 & sens,spec>=0.60 & TEXT 대비 BA>=0.10.
"""
import argparse
import glob
import json
import os

import numpy as np

import msd56_run as R

CONDS = ["DENSE", "U8", "O8", "TEXT"]
B = 10000
SEED = 56


def load_records(gen_dirs, rows):
    recs = {}
    for d in gen_dirs:
        for fn in sorted(glob.glob(os.path.join(d, "gen_worker*.jsonl"))):
            for r in R.read_jsonl(fn):
                if r["rid"] in recs:
                    raise R.RunError(f"duplicate rid {r['rid']}")
                recs[r["rid"]] = r
    need = {r["rid"] for r in rows}
    miss = need - set(recs)
    extra = set(recs) - need
    if miss or extra:
        raise R.RunError(f"incomplete/extra records: missing={len(miss)} extra={len(extra)}")
    return recs


def confusion(items):
    """items: list of (present_bool, answer or None)."""
    tp = sum(1 for p, a in items if p and a == "PRESENT")
    fn_ = sum(1 for p, a in items if p and a != "PRESENT")
    tn = sum(1 for p, a in items if (not p) and a == "ABSENT")
    fp = sum(1 for p, a in items if (not p) and a != "ABSENT")
    inv_p = sum(1 for p, a in items if p and a is None)
    inv_n = sum(1 for p, a in items if (not p) and a is None)
    return tp, fn_, tn, fp, inv_p, inv_n


def metrics(items):
    tp, fn_, tn, fp, ip, in_ = confusion(items)
    P, N = tp + fn_, tn + fp
    sens = tp / P if P else None
    spec = tn / N if N else None
    ba = (sens + spec) / 2 if (P and N) else None
    return {"n": len(items), "P": P, "N": N, "TP": tp, "FN": fn_, "TN": tn, "FP": fp, "invalid_pos": ip, "invalid_neg": in_,
            "sens": sens, "spec": spec, "BA": ba, "invalid_rate": (ip + in_) / len(items) if items else None,
            "acc": (tp + tn) / len(items) if items else None}


def cluster_boot(by_case, fn, seed=SEED, b=B):
    """by_case: {case: list of row dicts}; fn(list_of_rows)->float or None. 환자 대응이 불명확하므로 case를 cluster로 재표집."""
    rng = np.random.default_rng(seed)
    cases = sorted(by_case)
    vals = []
    for _ in range(b):
        pick = rng.integers(0, len(cases), len(cases))
        rows = [r for i in pick for r in by_case[cases[i]]]
        v = fn(rows)
        if v is not None:
            vals.append(v)
    if not vals:
        return None
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5)), len(vals)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True)
    ap.add_argument("--gen-dirs", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--model-tag", default="medgemma")
    ap.add_argument("--requests", default=None)
    ap.add_argument("--cond-map", default=None)
    ap.add_argument("--conds", default=",".join(CONDS))
    a = ap.parse_args()
    conds = a.conds.split(",")
    req_path = a.requests or f"results/iter_056/data/requests_{a.split}.jsonl"
    cmap_path = a.cond_map or f"results/iter_056/data/cond_map_{a.split}.json"
    rows = [json.loads(ln) for ln in open(req_path)]
    cmap = json.load(open(cmap_path))
    gt = {(r["case"], r["slab"]): r for r in json.load(open("results/iter_056/data/gt_slabs.json"))["rows"] if r["split"] == a.split}
    recs = load_records(a.gen_dirs.split(","), rows)
    table = []
    for c in cmap:
        if c["cond"] not in conds:
            continue
        g = gt[(c["case"], c["slab"])]
        r = recs[c["rid"]]
        cov = g["cond"].get(c["cond"])
        table.append({"case": c["case"], "slab": c["slab"], "cond": c["cond"], "rid": c["rid"], "present": g["present"],
                      "answer": r["answer"], "ended_eos": r["ended_eos"], "final_cap": r["final_cap"], "raw": r["suffix_text_raw"][:120],
                      "n_images": r["n_images"], "n_input_tokens": r["n_input_tokens"], "runtime_s": r["runtime_s_total"],
                      "ann_voxels": g["ann_voxels"], "n_pos_slices": g["n_pos_slices"],
                      "missed_positive": (cov or {}).get("missed_positive"),
                      "cov_frac_voxels": (cov or {}).get("cov_frac_voxels"),
                      "cov_frac_pos_slices": (cov or {}).get("cov_frac_pos_slices"),
                      "cov_frac_max_area": (cov or {}).get("cov_frac_max_area")})
    n_expect = len(gt) * len(conds)
    if len(table) != n_expect or len({(t["case"], t["slab"], t["cond"]) for t in table}) != n_expect:
        raise R.RunError("evaluation matrix incomplete/duplicated")
    os.makedirs(a.out_dir, exist_ok=True)
    rep = {"split": a.split, "model_tag": a.model_tag, "n_slabs": len(gt), "n_cases": len({k[0] for k in gt}),
           "prevalence": sum(g["present"] for g in gt.values()) / len(gt), "cond": {}, "paired": {}, "coverage": {}, "cost": {}}
    by = {cn: [t for t in table if t["cond"] == cn] for cn in conds}
    for cn in conds:
        items = [(t["present"], t["answer"]) for t in by[cn]]
        m = metrics(items)
        bc = {}
        for t in by[cn]:
            bc.setdefault(t["case"], []).append(t)
        m["BA_ci95"] = cluster_boot(bc, lambda rr: metrics([(t["present"], t["answer"]) for t in rr])["BA"])
        m["sens_ci95"] = cluster_boot(bc, lambda rr: metrics([(t["present"], t["answer"]) for t in rr])["sens"])
        m["spec_ci95"] = cluster_boot(bc, lambda rr: metrics([(t["present"], t["answer"]) for t in rr])["spec"])
        m["non_eos"] = sum(1 for t in by[cn] if not t["ended_eos"])
        m["answers"] = {k: sum(1 for t in by[cn] if t["answer"] == k) for k in ("PRESENT", "ABSENT", None)}
        m["answers"] = {str(k): v for k, v in m["answers"].items()}
        rep["cond"][cn] = m
    allp = [(g["present"], "PRESENT") for g in gt.values()]
    alla = [(g["present"], "ABSENT") for g in gt.values()]
    rep["cond"]["CONST_PRESENT"] = metrics(allp)
    rep["cond"]["CONST_ABSENT"] = metrics(alla)

    def key(t):
        return (t["case"], t["slab"])
    pairs = [("DENSE", "TEXT"), ("O8", "TEXT"), ("U8", "TEXT"), ("U8", "DENSE"), ("O8", "DENSE"), ("O8", "U8")]
    for x, y in pairs:
        if x not in conds or y not in conds:
            continue
        bx = {key(t): t for t in by[x]}
        by_ = {key(t): t for t in by[y]}
        cl = {}
        for k in bx:
            cl.setdefault(k[0], []).append((bx[k], by_[k]))

        def diff(rr):
            mx = metrics([(p["present"], p["answer"]) for p, _ in rr])["BA"]
            my = metrics([(q["present"], q["answer"]) for _, q in rr])["BA"]
            return None if mx is None or my is None else mx - my
        d = diff([pq for v in cl.values() for pq in v])
        # 사건: x만 정답 / y만 정답, 사건이 분포한 case 수
        def ok(t):
            return (t["answer"] == "PRESENT") if t["present"] else (t["answer"] == "ABSENT")
        better = {k[0] for k in bx if ok(bx[k]) and not ok(by_[k])}
        worse = {k[0] for k in bx if ok(by_[k]) and not ok(bx[k])}
        nb = sum(1 for k in bx if ok(bx[k]) and not ok(by_[k]))
        nw = sum(1 for k in bx if ok(by_[k]) and not ok(bx[k]))
        rep["paired"][f"{x}-{y}"] = {"BA_diff": d, "ci95": cluster_boot(cl, diff), "x_only_correct": nb, "y_only_correct": nw,
                                      "n_cases_x_only": len(better), "n_cases_y_only": len(worse),
                                      "n_cases_event": len(better | worse)}
    # coverage / 층별
    pos = [g for g in gt.values() if g["present"]]
    med = float(np.median([g["ann_voxels"] for g in pos])) if pos else None
    for cn in conds:
        if cn == "TEXT":
            continue
        pt = [t for t in by[cn] if t["present"]]
        cv = {"n_pos_slabs": len(pt), "missed_positive": sum(1 for t in pt if t["missed_positive"]),
              "mean_cov_frac_voxels": float(np.mean([t["cov_frac_voxels"] for t in pt])) if pt else None,
              "mean_cov_frac_pos_slices": float(np.mean([t["cov_frac_pos_slices"] for t in pt])) if pt else None,
              "mean_cov_frac_max_area": float(np.mean([t["cov_frac_max_area"] for t in pt])) if pt else None}
        sm = [t for t in pt if t["ann_voxels"] <= med]
        lg = [t for t in pt if t["ann_voxels"] > med]
        cv["sens_small_lesion(<=median voxels)"] = {"n": len(sm), "TP": sum(1 for t in sm if t["answer"] == "PRESENT")}
        cv["sens_large_lesion(>median voxels)"] = {"n": len(lg), "TP": sum(1 for t in lg if t["answer"] == "PRESENT")}
        cv["sens_missed_positive_slabs"] = {"n": sum(1 for t in pt if t["missed_positive"]),
                                           "TP": sum(1 for t in pt if t["missed_positive"] and t["answer"] == "PRESENT")}
        cv["median_ann_voxels_pos"] = med
        rep["coverage"][cn] = cv
    # 비용: 고유 요청 단위 (U8/O8 공유 요청은 한 번만 생성). 조건별 평균은 조건 행 기준.
    for cn in conds:
        rep["cost"][cn] = {"mean_runtime_s_per_condition_row": float(np.mean([t["runtime_s"] for t in by[cn]])),
                           "mean_n_images": float(np.mean([t["n_images"] for t in by[cn]])),
                           "mean_input_tokens": float(np.mean([t["n_input_tokens"] for t in by[cn]]))}
    rep["cost"]["unique_requests"] = len(rows)
    rep["cost"]["sum_runtime_s_unique"] = float(sum(r["runtime_s_total"] for r in recs.values()))
    rep["cost"]["retries_to_2048"] = sum(1 for r in recs.values() if len(r["attempts"]) > 1)
    rep["cost"]["peak_mem_alloc_gb_max"] = max(r["peak_mem_alloc_gb_max"] for r in recs.values())
    rep["cost"]["peak_mem_reserved_gb_max"] = max(r["peak_mem_reserved_gb_max"] for r in recs.values())
    # per-case 분포 (case별 정답 수)
    rep["per_case_correct"] = {cn: {} for cn in conds}
    for cn in conds:
        for t in by[cn]:
            ok_ = (t["answer"] == "PRESENT") if t["present"] else (t["answer"] == "ABSENT")
            rep["per_case_correct"][cn][t["case"]] = rep["per_case_correct"][cn].get(t["case"], 0) + int(ok_)
    # 사전 규칙
    dec = decide(rep, conds)
    rep["decision"] = dec
    json.dump(rep, open(os.path.join(a.out_dir, "report.json"), "w"), indent=1)
    json.dump(table, open(os.path.join(a.out_dir, "per_slab.json"), "w"))
    print(json.dumps({"cond": {k: {kk: v[kk] for kk in ("n", "P", "N", "TP", "FN", "TN", "FP", "sens", "spec", "BA", "invalid_rate")} for k, v in rep["cond"].items()},
                      "decision": dec}, indent=1))


def decide(rep, conds):
    c = rep["cond"]
    out = {}

    def ba(cn):
        return c[cn]["BA"] if cn in c else None
    if any(ba(x) is None for x in conds if x in c):
        out["note"] = "BA undefined (single class) -> no automatic branch"
        return out
    sig = {}
    for cn in ("DENSE", "O8"):
        if cn in c and "TEXT" in c:
            sig[cn] = bool(c[cn]["BA"] >= 0.70 and c[cn]["sens"] >= 0.60 and c[cn]["spec"] >= 0.60 and c[cn]["BA"] - c["TEXT"]["BA"] >= 0.10)
    out["basic_signal_by_cond"] = sig
    out["basic_signal"] = any(sig.values())
    # Qwen 분기: DENSE와 O8 모두 BA<0.65 이거나 둘 다 TEXT 대비 BA 이득 <0.05
    if "DENSE" in c and "O8" in c and "TEXT" in c:
        both_low = c["DENSE"]["BA"] < 0.65 and c["O8"]["BA"] < 0.65
        both_nogain = (c["DENSE"]["BA"] - c["TEXT"]["BA"] < 0.05) and (c["O8"]["BA"] - c["TEXT"]["BA"] < 0.05)
        out["qwen_branch_triggered"] = bool(both_low or both_nogain)
        out["qwen_branch_reason"] = {"both_BA_lt_0.65": bool(both_low), "both_gain_vs_text_lt_0.05": bool(both_nogain)}
    if "DENSE" in c and "O8" in c and "U8" in c:
        mx = max(c[x]["BA"] for x in ("DENSE", "U8", "O8"))
        mn = min(c[x]["BA"] for x in ("DENSE", "U8", "O8"))
        ev = {k: rep["paired"].get(k, {}).get("n_cases_event") for k in ("U8-DENSE", "O8-DENSE", "O8-U8")}
        out["max_pairwise_BA_gap(DENSE,U8,O8)"] = mx - mn
        out["residual_difference"] = bool(out["basic_signal"] and (mx - mn) >= 0.10 and any((v or 0) >= 5 for v in ev.values()))
        out["events_cases"] = ev
        out["u8_within_0.05_of_dense"] = bool(abs(c["U8"]["BA"] - c["DENSE"]["BA"]) <= 0.05)
        ratio = rep["cost"]["U8"]["mean_runtime_s_per_condition_row"] / rep["cost"]["DENSE"]["mean_runtime_s_per_condition_row"]
        out["u8_cost_ratio_runtime_vs_dense"] = ratio
        out["negative_action_uniform_baseline"] = bool(out["u8_within_0.05_of_dense"] and ratio <= 0.5)
    return out


if __name__ == "__main__":
    main()
