"""iter_057: iter_056 D6/E48 기존 출력의 위치(slab index) 통제 재분석. CPU-only, 새 생성·학습 0.

python msd57_analysis.py --out-dir results/iter_057/analysis
- 입력은 results/iter_056/ 의 본 실행(gen/D, gen/E)만 읽고 hash를 manifest에 잠근다. 쓰기는 out-dir에만 한다.
- 위치 규칙은 D 정답만으로 선택해 E 비교 전에 저장한다.
"""
import argparse
import glob
import hashlib
import itertools
import json
import os
import re
import time

import numpy as np

import msd56_run as R

SRC = "results/iter_056"
CONDS = ["DENSE", "U8", "O8", "TEXT"]
NSLAB = 6
B = 10000
SEED = 57


def sha_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def atomic_write(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, default=int)
    os.replace(tmp, path)


# ---------------- 입력 로딩·검증 ----------------
def input_files():
    fs = [f"{SRC}/data/{n}" for n in ("cases.json", "case_order.json", "gt_slabs.json", "requests_D.jsonl", "requests_E.jsonl",
                                      "cond_map_D.json", "cond_map_E.json", "protocol_D.json", "protocol_E.json")]
    for s in "DE":
        fs += sorted(glob.glob(f"{SRC}/gen/{s}/gen_worker[0-9]*.jsonl"))
    fs += [f"{SRC}/source/msd56_run_v1_used_for_D_main.py", f"{SRC}/eval_E/report.json", f"{SRC}/eval_E/breakdown.json"]
    return [f for f in fs if not f.endswith(".log")]


def lock_inputs(out_dir):
    path = os.path.join(out_dir, "input_manifest.json")
    cur = {f: sha_file(f) for f in input_files()}
    if os.path.exists(path):
        old = json.load(open(path))["files"]
        if old != cur:
            raise R.RunError("input hash changed vs existing manifest")
        return cur
    atomic_write(path, {"files": cur, "created": time.strftime("%Y-%m-%dT%H:%M:%S")})
    return cur


def load_split(split, gt_rows):
    """검증된 표 반환: list of dict(case, slab, cond, rid, present, answer, raw, ...)."""
    reqs = [json.loads(l) for l in open(f"{SRC}/data/requests_{split}.jsonl") if l.strip()]
    rid2req = {r["rid"]: r for r in reqs}
    if len(rid2req) != len(reqs):
        raise R.RunError(f"{split}: duplicate request rid")
    pdig = sha_file(f"{SRC}/data/protocol_{split}.json")
    recs = {}
    for fn in sorted(glob.glob(f"{SRC}/gen/{split}/gen_worker[0-9]*.jsonl")):
        if fn.endswith(".log"):
            continue
        for r in R.read_jsonl(fn):
            if r["rid"] in recs:
                raise R.RunError(f"{split}: duplicate record {r['rid']}")
            recs[r["rid"]] = r
    if set(recs) != set(rid2req):
        raise R.RunError(f"{split}: record/request mismatch miss={len(set(rid2req) - set(recs))} extra={len(set(recs) - set(rid2req))}")
    for r in recs.values():
        if r["protocol_digest"] != pdig:
            raise R.RunError("record protocol digest mismatch")
        if R.parse_answer(r["suffix_text_raw"]) != r["answer"]:
            raise R.RunError(f"stored answer != re-parsed raw for {r['rid']}")
        if r["image_file_sha256"] != rid2req[r["rid"]]["image_file_sha256"]:
            raise R.RunError("record image hash != request")
    cmap = json.load(open(f"{SRC}/data/cond_map_{split}.json"))
    gt = {(g["case"], g["slab"]): g for g in gt_rows if g["split"] == split}
    seen = set()
    table = []
    for c in cmap:
        k = (c["case"], c["slab"], c["cond"])
        if k in seen:
            raise R.RunError(f"duplicate cond row {k}")
        seen.add(k)
        g = gt[(c["case"], c["slab"])]
        req = rid2req[c["rid"]]
        # 요청 영상의 z 번호가 GT 구성(slices)과 일치하는지
        zs = [int(re.search(r"_z(\d+)\.png$", p).group(1)) for p in req["images"]]
        if c["cond"] in g["cond"] and zs != g["cond"][c["cond"]]["slices"]:
            raise R.RunError(f"request slices != gt slices for {k}")
        if not all(os.path.basename(p).startswith(c["case"] + "_") for p in req["images"]):
            raise R.RunError(f"request image case mismatch {k}")
        r = recs[c["rid"]]
        cov = g["cond"].get(c["cond"]) or {}
        table.append({"case": c["case"], "slab": c["slab"], "cond": c["cond"], "rid": c["rid"], "present": g["present"],
                      "answer": R.parse_answer(r["suffix_text_raw"]), "ended_eos": r["ended_eos"],
                      "ann_voxels": g["ann_voxels"], "n_pos_slices": g["n_pos_slices"],
                      "missed_positive": cov.get("missed_positive"), "cov_frac_voxels": cov.get("cov_frac_voxels")})
    exp = {(c, s, cn) for (c, s) in gt for cn in CONDS}
    if seen != exp:
        raise R.RunError(f"{split}: cond matrix != gt x conds (miss={len(exp - seen)} extra={len(seen - exp)})")
    cases = sorted({k[0] for k in gt})
    for c in cases:
        if sorted(s for (cc, s) in gt if cc == c) != list(range(NSLAB)):
            raise R.RunError(f"{c}: slabs != 0..5")
    return table, gt, recs, rid2req


# ---------------- 통계 ----------------
def counts_by_case(rows, cases, pred_fn):
    """(ncase, NSLAB, 4) = TP, P, TN, N. pred_fn(row)->'PRESENT'/'ABSENT'/None. invalid는 해당 class의 오답."""
    idx = {c: i for i, c in enumerate(cases)}
    A = np.zeros((len(cases), NSLAB, 4))
    for t in rows:
        a = pred_fn(t)
        i, s = idx[t["case"]], t["slab"]
        if t["present"]:
            A[i, s, 1] += 1
            A[i, s, 0] += a == "PRESENT"
        else:
            A[i, s, 3] += 1
            A[i, s, 2] += a == "ABSENT"
    return A


def ba_overall(S):
    """S: (..., NSLAB, 4) 합산된 count (..., 에 replicate 차원 허용). 구간 전체 BA, 한 class가 없으면 nan."""
    tp, p, tn, n = (S[..., k].sum(-1) for k in range(4))
    with np.errstate(all="ignore"):
        return np.where((p > 0) & (n > 0), (tp / p + tn / n) / 2, np.nan)


def ba_std(S, support):
    """지원 위치(E GT 기준 양쪽 class 존재)의 BA를 동일 가중 평균. 지원 위치 중 한 class라도 사라지면 nan(재가중 안 함)."""
    sup = list(support)
    tp, p, tn, n = (S[..., sup, k] for k in range(4))
    with np.errstate(all="ignore"):
        b = (tp / p + tn / n) / 2
    ok = np.all((p > 0) & (n > 0), axis=-1)
    return np.where(ok, b.mean(-1), np.nan)


def support_positions(A):
    S = A.sum(0)
    return [s for s in range(NSLAB) if S[s, 1] > 0 and S[s, 3] > 0]


def cluster_boot_stats(Amap, fns, seed=SEED, b=B):
    """Amap: {name: (ncase, NSLAB, 4)}; fns: {metric: callable(dict name->summed counts (b,NSLAB,4))->(b,)}.
    같은 재표집 case를 모든 조건·baseline에 공통 적용. 반환 {metric: [lo, hi, n_valid]}."""
    rng = np.random.default_rng(seed)
    n = next(iter(Amap.values())).shape[0]
    W = np.zeros((b, n))
    for i in range(b):
        W[i] = np.bincount(rng.integers(0, n, n), minlength=n)
    sums = {k: np.einsum("bn,nsk->bsk", W, v) for k, v in Amap.items()}
    out = {}
    for m, f in fns.items():
        v = f(sums)
        v = v[~np.isnan(v)]
        out[m] = [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5)), int(len(v))] if len(v) else [None, None, 0]
    return out


# ---------------- 위치 규칙 ----------------
def rule_search(rows_D):
    """64개 위치별 이진 규칙(1=PRESENT) 중 D 전체 BA 최대. 동률: PRESENT 위치 수 작은 것, 이어 tuple 사전순."""
    P = np.zeros(NSLAB)
    N = np.zeros(NSLAB)
    for t in rows_D:
        (P if t["present"] else N)[t["slab"]] += 1
    if P.sum() == 0 or N.sum() == 0:
        raise R.RunError("D has a single class")
    cands = []
    for tup in itertools.product((0, 1), repeat=NSLAB):
        t_ = np.array(tup)
        sens = (P * t_).sum() / P.sum()
        spec = (N * (1 - t_)).sum() / N.sum()
        cands.append(((sens + spec) / 2, tup))
    best = max(b for b, _ in cands)
    tied = sorted([(sum(t), t) for b, t in cands if abs(b - best) < 1e-12])
    return {"rule_present_by_slab": list(tied[0][1]), "D_BA": best, "n_tied": len(tied), "tied_rules": [list(t) for _, t in tied]}


def rule_pred_fn(rule):
    return lambda t: "PRESENT" if rule[t["slab"]] else "ABSENT"


# ---------------- 보고용 metric ----------------
def cell(A):
    S = A.sum(0)
    out = {}
    for s in range(NSLAB):
        tp, p, tn, n = S[s]
        out[str(s)] = {"P": int(p), "N": int(n), "TP": int(tp), "FN": int(p - tp), "TN": int(tn), "FP": int(n - tn),
                       "sens": float(tp / p) if p else None, "spec": float(tn / n) if n else None,
                       "BA": float((tp / p + tn / n) / 2) if p and n else None}
    return out


def ok_(t):
    return (t["answer"] == "PRESENT") == t["present"] and t["answer"] is not None


def run(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time()
    manifest = lock_inputs(out_dir)
    gt_rows = json.load(open(f"{SRC}/data/gt_slabs.json"))["rows"]
    D, gtD, recsD, _ = load_split("D", gt_rows)
    E, gtE, recsE, _ = load_split("E", gt_rows)
    casesD, casesE = {k[0] for k in gtD}, {k[0] for k in gtE}
    if casesD & casesE:
        raise R.RunError("D/E case overlap")
    cases = sorted(casesE)
    # 회귀: 고유 요청 수, 조건 행 수
    reg = {"E_unique_requests": len(recsE), "E_cond_rows": len(E), "D_unique_requests": len(recsD), "D_slabs": len(gtD), "E_slabs": len(gtE)}
    assert reg["E_unique_requests"] == 766 and reg["E_cond_rows"] == 1152 and reg["D_unique_requests"] == 97 and reg["D_slabs"] == 36 and reg["E_slabs"] == 288, reg

    # 위치 규칙: D 정답만 사용, E 비교 전에 저장
    rule_path = os.path.join(out_dir, "position_rule_D.json")
    D_rows = [t for t in D if t["cond"] == "DENSE"]
    rule = rule_search(D_rows)
    rule["selection"] = "D36 BA max over 64 binary position rules; tie: fewer PRESENT slabs then lexicographic tuple"
    rule["D_prevalence_by_slab"] = {str(s): [sum(1 for t in D_rows if t["slab"] == s and t["present"]), sum(1 for t in D_rows if t["slab"] == s)] for s in range(NSLAB)}
    if os.path.exists(rule_path):
        if json.load(open(rule_path))["rule_present_by_slab"] != rule["rule_present_by_slab"]:
            raise R.RunError("stored rule differs")
    else:
        atomic_write(rule_path, rule)
    rv = rule["rule_present_by_slab"]

    byc = {cn: [t for t in E if t["cond"] == cn] for cn in CONDS}
    A = {cn: counts_by_case(byc[cn], cases, lambda t: t["answer"]) for cn in CONDS}
    A["RULE_D"] = counts_by_case(byc["DENSE"], cases, rule_pred_fn(rv))
    A["CONST_PRESENT"] = counts_by_case(byc["DENSE"], cases, lambda t: "PRESENT")
    A["CONST_ABSENT"] = counts_by_case(byc["DENSE"], cases, lambda t: "ABSENT")
    supp = support_positions(A["DENSE"])

    # 위치별·전체 point estimates
    rep = {"note": "post-hoc exploratory re-analysis of iter_056 outputs; E is development data; not confirmatory", "rule_D": rule,
           "support_positions_from_E_GT": supp, "regression_counts": reg, "cond": {}}
    for k, a in A.items():
        s = a.sum(0)
        rep["cond"][k] = {"by_slab": cell(a), "BA_all": float(ba_overall(s[None])[0]), "BA_std": float(ba_std(s[None], supp)[0]),
                          "per_slab_support_BA": {str(i): cell(a)[str(i)]["BA"] for i in supp},
                          "invalid": int(sum(1 for t in byc.get(k, []) if t["answer"] is None)),
                          "case_n": len(cases)}
    # bootstrap (seed57)
    ba_all = lambda k: (lambda S: ba_overall(S[k]))
    ba_s = lambda k: (lambda S: ba_std(S[k], supp))
    fns = {}
    for k in ("DENSE", "U8", "O8", "TEXT", "RULE_D"):
        fns[f"{k}.BA_all"] = ba_all(k)
        fns[f"{k}.BA_std"] = ba_s(k)
        fns[f"{k}.BA_std_minus_0.5"] = (lambda kk: (lambda S: ba_std(S[kk], supp) - 0.5))(k)
    for k in ("DENSE", "U8", "O8"):
        fns[f"{k}-RULE_D.BA_all"] = (lambda kk: (lambda S: ba_overall(S[kk]) - ba_overall(S["RULE_D"])))(k)
        fns[f"{k}-RULE_D.BA_std"] = (lambda kk: (lambda S: ba_std(S[kk], supp) - ba_std(S["RULE_D"], supp)))(k)
    for x, y in (("U8", "DENSE"), ("O8", "DENSE"), ("O8", "U8"), ("DENSE", "TEXT")):
        fns[f"{x}-{y}.BA_all"] = (lambda xx, yy: (lambda S: ba_overall(S[xx]) - ba_overall(S[yy])))(x, y)
        fns[f"{x}-{y}.BA_std"] = (lambda xx, yy: (lambda S: ba_std(S[xx], supp) - ba_std(S[yy], supp)))(x, y)
    # 처리량 추정(첫 100회) 후 전체 실행
    tb = time.time()
    cluster_boot_stats(A, fns, b=100)
    est = (time.time() - tb) / 100 * B
    tb = time.time()
    ci = cluster_boot_stats(A, fns)
    act = time.time() - tb
    rep["bootstrap"] = {"seed": SEED, "B": B, "unit": "E case (6 slabs resampled together; same draw for all conditions/baselines)",
                        "ci": ci, "caveat": "선택된 D 규칙에 조건부. 희소 class로 지원 위치 class가 사라진 replicate는 undefined로 제외(재가중 없음).",
                        "cpu_est_s_from_first100": est, "cpu_actual_s": act}
    # point estimates of paired
    pt = {}
    for name, f in fns.items():
        S = {k: v.sum(0)[None] for k, v in A.items()}
        pt[name] = float(f(S)[0])
    rep["point"] = pt

    # 기존 seed56 CI 회귀 (iter_056 report의 DENSE/U8/O8/TEXT BA_ci95와 대조)
    old = json.load(open(f"{SRC}/eval_E/report.json"))
    reg56 = {}
    ci56 = cluster_boot_stats({k: A[k] for k in CONDS}, {k: ba_all(k) for k in CONDS}, seed=56)
    for k in CONDS:
        reg56[k] = {"new": ci56[k], "old": old["cond"][k]["BA_ci95"], "BA_new": rep["cond"][k]["BA_all"], "BA_old": old["cond"][k]["BA"]}
    rep["regression_vs_iter056"] = reg56
    for k in CONDS:
        o = old["cond"][k]
        n = rep["cond"][k]["by_slab"]
        tot = {x: sum(n[str(s)][x] for s in range(NSLAB)) for x in ("TP", "FN", "TN", "FP")}
        assert tot == {x: o[x] for x in ("TP", "FN", "TN", "FP")}, (k, tot)
        assert abs(rep["cond"][k]["BA_all"] - o["BA"]) < 1e-12
        for i in range(2):
            assert abs(reg56[k]["new"][i] - reg56[k]["old"][i]) < 1e-9, (k, reg56[k])
    bd = json.load(open(f"{SRC}/eval_E/breakdown.json"))["position_only_insample_prior"]["BA"]
    rep["regression_vs_iter056"]["majority_by_slab_BA_old_reported"] = bd

    # E 자체 64규칙 사후 참고(상한 아님: 6-index 결정적 규칙 집합 in-sample 최댓값)
    s0 = A["DENSE"].sum(0)
    best_e = max(((((s0[:, 1] * np.array(t)).sum() / s0[:, 1].sum()) + (s0[:, 3] * (1 - np.array(t))).sum() / s0[:, 3].sum()) / 2, t)
                 for t in itertools.product((0, 1), repeat=NSLAB))
    maj = [int(s0[s, 1] >= s0[s, 3]) for s in range(NSLAB)]
    maj_ba = ((s0[:, 1] * np.array(maj)).sum() / s0[:, 1].sum() + (s0[:, 3] * (1 - np.array(maj))).sum() / s0[:, 3].sum()) / 2
    rep["E_in_sample_reference"] = {"best_of_64_BA": float(best_e[0]), "best_rule": list(best_e[1]), "majority_rule_BA": float(maj_ba),
                                    "caveat": "E 정답으로 맞춘 사후 참고값. 모든 위치 기반 방법의 상한이 아님."}
    assert abs(best_e[0] - 0.761664) < 1e-5 and abs(maj_ba - 0.719336) < 1e-5

    # 잔여 오류
    res = {}
    key = lambda t: (t["case"], t["slab"])
    dn, u8 = {key(t): t for t in byc["DENSE"]}, {key(t): t for t in byc["U8"]}
    for k_, m in (("DENSE", dn), ("U8", u8)):
        res[f"{k_}_errors"] = [{"case": c, "slab": s, "present": t["present"], "answer": t["answer"], "ann_voxels": t["ann_voxels"],
                                "missed_positive": t["missed_positive"], "cov_frac_voxels": t["cov_frac_voxels"],
                                "rule_D_pred": "PRESENT" if rv[s] else "ABSENT"} for (c, s), t in sorted(m.items()) if not ok_(t)]
    cat = {}
    for (c, s), t in dn.items():
        u = u8[(c, s)]
        rp = bool(rv[s])
        e = ("both_wrong" if not ok_(t) and not ok_(u) else "dense_only_wrong" if not ok_(t) else "u8_only_wrong" if not ok_(u) else None)
        if e:
            cat.setdefault(e, []).append({"case": c, "slab": s, "present": t["present"], "rule_D_correct": rp == t["present"]})
    res["error_overlap"] = {k: {"n": len(v), "n_cases": len({x["case"] for x in v}), "n_where_rule_D_correct": sum(x["rule_D_correct"] for x in v),
                                "items": v} for k, v in cat.items()}
    for k_, m in (("DENSE", dn), ("U8", u8)):
        er = res[f"{k_}_errors"]
        fn_c = {e["case"] for e in er if e["present"]}
        fp_c = {e["case"] for e in er if not e["present"]}
        per_case = {}
        for e in er:
            per_case[e["case"]] = per_case.get(e["case"], 0) + 1
        res[f"{k_}_summary"] = {"FN": sum(e["present"] for e in er), "FP": sum(not e["present"] for e in er), "n_cases_FN": len(fn_c),
                                "n_cases_FP": len(fp_c), "n_cases_any_error": len(per_case), "errors_per_case_hist": {str(n): sum(1 for v in per_case.values() if v == n) for n in sorted(set(per_case.values()))},
                                "cases_with_ge2_errors": sorted(c for c, v in per_case.items() if v >= 2),
                                "errors_by_slab": {str(s): sum(1 for e in er if e["slab"] == s) for s in range(NSLAB)}}
    lost = [(c, s) for (c, s), t in dn.items() if t["present"] and ok_(t) and not ok_(u8[(c, s)])]
    res["U8_loses_DENSE_correct_positive"] = {"n": len(lost), "selection_missed_all_annotation": sum(bool(u8[k_]["missed_positive"]) for k_ in lost)}
    rep["residual"] = res
    # 결정
    d = rep["cond"]["DENSE"]
    lo, hi, nv = ci["DENSE.BA_std"][0], ci["DENSE.BA_std"][1], ci["DENSE.BA_std"][2]
    pt_ = d["BA_std"]
    n_err_cases = max(res["DENSE_summary"]["n_cases_any_error"], 0)
    if pt_ > 0.5 and ci["DENSE.BA_std_minus_0.5"][0] is not None and ci["DENSE.BA_std_minus_0.5"][0] > 0:
        cls = "positive"
    elif hi is not None and hi <= 0.55:
        cls = "negative"
    else:
        cls = "inconclusive"
    rep["prespecified_decision"] = {"DENSE_BA_std": pt_, "CI95": [lo, hi], "n_valid_replicates": nv, "classification": cls,
                                    "residual_error_cases_DENSE(>=5 needed for positive follow-up)": n_err_cases,
                                    "residual_ge5_cases": bool(n_err_cases >= 5)}
    atomic_write(os.path.join(out_dir, "report.json"), rep)
    atomic_write(os.path.join(out_dir, "per_row_E.json"), E)
    rep["cpu_total_s"] = time.time() - t0
    atomic_write(os.path.join(out_dir, "report.json"), rep)
    return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    if os.path.abspath(a.out_dir).find("iter_056") >= 0:
        raise SystemExit("refuse to write under iter_056")
    r = run(a.out_dir)
    print(json.dumps({"rule": r["rule_D"]["rule_present_by_slab"], "support": r["support_positions_from_E_GT"], "point": r["point"],
                      "decision": r["prespecified_decision"], "boot": r["bootstrap"]["ci"]}, indent=1, default=int))
