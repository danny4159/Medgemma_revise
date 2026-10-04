"""iter_066 평가 진입점. scoring 출력(m66_run)과 iter_065 생성 출력(G_F/G_J)을 현재 protocol·요청·labels·모델 파일에 재연결해 검증한 뒤 계산한다.

서브명령: gate-d | prior | report | decide-e12
 - gate-d: D tech 전부 통과 + D completion 검증 -> gates/D_gate.json (E12 protocol의 진입 조건)
 - prior: D6 정답에서만 질문 무조건 prior와 구간 위치별 prior를 고정 (동률 ABSENT)
 - report: 단계(D | E12 | E48=E12+E36)별 G/L/prior/null BA, case bootstrap(seed66, 10,000회)
 - decide-e12: 사전 고정 확대 조건으로 gates/E12_decision.json 생성
점수 선택: mean_ll(PRESENT) > mean_ll(ABSENT) -> PRESENT, 동률 ABSENT. 원 생성 판정은 iter_065 규칙(parse_answer, invalid=오답) 그대로.
"""
import argparse
import glob
import json
import os
import sys

import numpy as np

import m65_run as R65
import m66_run as R
import msd56_run as M

SEED, NB = 66, 10000
SRC65 = R.SRC65
GEN = {"D": ("results/iter_065/gen/D_medgemma", "results/iter_065/protocol/medgemma_D_v2.json"),
       "E12": ("results/iter_065/gen/E12_medgemma", "results/iter_065/protocol/medgemma_E12.json"),
       "E36": ("results/iter_065/gen/E36_medgemma", "results/iter_065/protocol/medgemma_E36_v2.json")}
RUN65_DRIFT = ("ae255669fe5b2319301b28bc56ed9c293199837f81af19058493452e41850a35",
               "29e3e6fc7d57b598c1f14924392416568e39bf61eb0eb575d3d3e4663126bac6")
SYS = ("G_F", "G_J", "L_F", "L_J")
NSLAB = 6


def sha_file(p):
    return R.file_sha(p)


def gen_protocol_ok(stage, split_requests):
    """iter_065 생성 protocol과 현재 입력 비교. 허용 차이는 m65_run.py hash 한 쌍(ae25..→29e3..)뿐이며 D/E12에만 허용."""
    gdir, ppath = GEN[stage]
    p = json.load(open(ppath))
    labels, tm = f"{SRC65}/data/labels_{stage}.json", f"{SRC65}/data/target_manifest_{stage}.json"
    comp, mf = R65.components("medgemma", split_requests, labels, tm, full_model_hash=True)
    diff = [k for k in comp if comp[k] != p["components"].get(k)]
    code_diff = {f: (p["components"]["code"].get(f), comp["code"][f]) for f in comp["code"] if comp["code"][f] != p["components"]["code"].get(f)}
    allowed = {} if stage == "E36" else {"m65_run.py": RUN65_DRIFT}
    if diff not in ([], ["code"]) or {k: tuple(v) for k, v in code_diff.items()} != {k: tuple(v) for k, v in allowed.items()} and code_diff:
        raise AssertionError(("iter_065 protocol mismatch", diff, code_diff))
    for f, v in code_diff.items():
        assert tuple(v) == allowed.get(f), ("unexpected code drift", f, v)
    assert all(mf[k]["sha256"] == v["sha256"] and mf[k]["size"] == v["size"] for k, v in p["model_files"].items()) and set(mf) == set(p["model_files"])
    assert R65.digest(p["components"], p["model_files"]) == p["digest"]
    return p["digest"], code_diff


def load_gen(stage):
    """iter_065 생성 출력(원 verify.json clean·record 파일 hash 유지)과 현재 protocol 연결. returns {rid: record}"""
    gdir, _ = GEN[stage]
    v = json.load(open(f"{gdir}/verify.json"))
    assert v["n_problems"] == 0 and v["n_records"] == v["n_requests"], "iter_065 verify not clean"
    for f, h in v["record_file_sha256"].items():
        assert sha_file(f) == h, f"gen record changed {f}"
    pd, drift = gen_protocol_ok(stage, f"{SRC65}/data/requests_{stage}.jsonl")
    assert pd == v["protocol_digest"] or drift, "protocol digest/verify mismatch"
    recs = {}
    for f in sorted(glob.glob(f"{gdir}/worker*.jsonl")):
        for r in R65.read_jsonl(f):
            assert r["rid"] not in recs, "dup gen record"
            recs[r["rid"]] = r
    return recs, {"verify_protocol_digest": v["protocol_digest"], "run_py_drift": drift}


def load_stage(stage, out_dir):
    req = f"results/iter_066/data/requests_{stage}.jsonl"
    proto = f"results/iter_066/protocol/{os.path.basename(out_dir.rstrip('/'))}.json"
    return req, proto


def collect(stages_dirs):
    """stages_dirs: [(stage, out_dir, protocol)]. 완료 검증된 L 점수, G 생성, 정답을 (case, slab) 단위로 합친다."""
    Lrec, Grec, lab, prov = {}, {}, {}, {}
    prompts = {}
    for stage, out_dir, proto in stages_dirs:
        req = f"results/iter_066/data/requests_{stage}.jsonl"
        recs, p, comp = R.verify_completion(out_dir, req, proto)
        assert p["stage"].split("_")[0] == stage
        for r in recs:
            assert r["request_id"] not in Lrec
            Lrec[r["request_id"]] = r
        labels_path = f"{SRC65}/data/labels_{stage}.json"
        assert p["locked_files"][labels_path] == sha_file(labels_path)
        lb = json.load(open(labels_path))
        g, gp = load_gen(stage)
        rows = {r["request_id"]: r for r in R.read_requests(req)}
        for rid, row in rows.items():
            prompts.setdefault(row["cond"], set()).add(row["prompt"])
            lab[rid] = lb[rid]
            Grec[rid] = g[rid]
            assert lb[rid]["case"] == row["case"] and lb[rid]["slab"] == row["slab"] and lb[rid]["cond"] == row["cond"] and lb[rid]["q"] == "W"
        prov[stage] = {"out_dir": out_dir, "protocol_digest": comp["protocol_digest"], "protocol_sha256": sha_file(proto),
                       "completion_sha256": sha_file(os.path.join(out_dir, "completion.json")), "gen": gp,
                       "labels_sha256": sha_file(labels_path), "requests_sha256": sha_file(req)}
    assert all(len(v) == 1 for v in prompts.values()), "prompts differ across cases within a condition (null invalid)"
    return Lrec, Grec, lab, prov


def arrays(Lrec, Grec, lab):
    cases = sorted({v["case"] for v in lab.values()})
    ci = {c: i for i, c in enumerate(cases)}
    n = len(cases)
    gt = np.full((n, NSLAB), -1)
    preds = {s: np.full((n, NSLAB), -2) for s in SYS}
    extra = {"g_eos": np.zeros((n, NSLAB), dtype=bool), "g_invalid": {c: np.zeros((n, NSLAB), dtype=bool) for c in "FJ"},
             "cov": np.zeros((n, NSLAB), dtype=bool), "margin": {c: np.zeros((n, NSLAB)) for c in "FJ"}}
    for rid, l in lab.items():
        i, s, c = ci[l["case"]], l["slab"], l["cond"]
        y = 1 if l["answer"] == "PRESENT" else 0
        if gt[i, s] not in (-1, y):
            raise AssertionError("F/J labels differ for the same slab")
        gt[i, s] = y
        if c == "F":
            extra["cov"][i, s] = bool(l["coverage"])
        g = Grec[rid]
        pa = M.parse_answer(g["attempts"][-1]["text"])
        preds["G_" + c][i, s] = -1 if pa is None else int(pa == "PRESENT")
        extra["g_invalid"][c][i, s] = pa is None
        if c == "F":
            extra["g_eos"][i, s] = bool(g["attempts"][-1]["ended_eos"])
        sc = Lrec[rid]["scores"]
        mp, ma = sc["PRESENT"]["mean_ll"], sc["ABSENT"]["mean_ll"]
        preds["L_" + c][i, s] = 1 if mp > ma else 0  # 동률 -> ABSENT
        extra["margin"][c][i, s] = mp - ma
    assert (gt >= 0).all() and all((p >= -1).all() for p in preds.values()), "incomplete (case, slab) matrix"
    return cases, gt, preds, extra


def case_counts(pred, gt):
    """(n,4): tp, fn, tn, fp. invalid(-1)은 오답(gt1->fn, gt0->fp)."""
    tp = ((gt == 1) & (pred == 1)).sum(1)
    fn = ((gt == 1) & (pred != 1)).sum(1)
    tn = ((gt == 0) & (pred == 0)).sum(1)
    fp = ((gt == 0) & (pred != 0)).sum(1)
    return np.stack([tp, fn, tn, fp], 1).astype(float)


def ba(cnt):
    tp, fn, tn, fp = cnt[..., 0], cnt[..., 1], cnt[..., 2], cnt[..., 3]
    with np.errstate(divide="ignore", invalid="ignore"):
        return 0.5 * (tp / (tp + fn) + tn / (tn + fp))


def sens_spec(cnt):
    s = cnt.sum(0)
    return float(s[0] / (s[0] + s[1])) if s[0] + s[1] else None, float(s[2] / (s[2] + s[3])) if s[2] + s[3] else None


def null_counts(pred, gt, sel=None):
    """같은 구간 위치에서 case 대응을 제거한 기대 BA용 기대 count (donor=선택된 모든 case 균등, 자기 case 포함 1/n).
    pred: (n,6)(valid 0/1), gt (n,6). sel: (NB, n) 재표집 index 또는 None. returns (...,4) 기대 count의 합."""
    if sel is None:
        m = pred.mean(0)  # (6,)
        tp = (gt * m).sum()
        P = gt.sum()
        fp = ((1 - gt) * m).sum()
        N = (1 - gt).sum()
        return np.array([tp, P - tp, N - fp, fp])
    p, g = pred[sel], gt[sel]  # (NB,n,6)
    m = p.mean(1)  # (NB,6)
    tp = (g * m[:, None, :]).sum((1, 2))
    P = g.sum((1, 2))
    fp = ((1 - g) * m[:, None, :]).sum((1, 2))
    N = (1 - g).sum((1, 2))
    return np.stack([tp, P - tp, N - fp, fp], 1)


def prior_preds(prior, n):
    return {"prior_global": np.full((n, NSLAB), int(prior["global_pred"])),
            "prior_pos": np.tile(np.array(prior["position_pred"]), (n, 1))}


def boot_diffs(fns, sel):
    out = {}
    for name, f in fns.items():
        d = f(sel)
        ok = ~np.isnan(d)
        out[name] = {"n_valid_replicates": int(ok.sum()), "n_excluded": int((~ok).sum()),
                     "ci95": [float(np.percentile(d[ok], 2.5)), float(np.percentile(d[ok], 97.5))] if ok.any() else None}
    return out


def analyze(cases, gt, preds, extra, prior):
    n = len(cases)
    pp = prior_preds(prior, n)
    allp = {**preds, **pp}
    cc = {k: case_counts(v, gt) for k, v in allp.items()}
    rep = {"n_cases": n, "n_slabs": int(gt.size), "n_pos": int(gt.sum()), "n_neg": int((1 - gt).sum()), "systems": {}}
    for k, c in cc.items():
        s, sp = sens_spec(c)
        rep["systems"][k] = {"BA": float(ba(c.sum(0))) if s is not None and sp is not None else None, "sens": s, "spec": sp,
                             "counts_tp_fn_tn_fp": [int(x) for x in c.sum(0)]}
    nulls = {}
    for cnd in "FJ":
        v = preds["L_" + cnd]
        nc = null_counts(v, gt)
        nulls[cnd] = nc
        rep["systems"]["null_L_" + cnd] = {"BA": float(ba(nc)), "sens": float(nc[0] / (nc[0] + nc[1])), "spec": float(nc[2] / (nc[2] + nc[3])),
                                          "counts_tp_fn_tn_fp": [float(x) for x in nc], "self_donor_probability": 1.0 / n}
    rng = np.random.default_rng(SEED)
    sel = rng.integers(0, n, size=(NB, n))
    B = {k: (lambda sel, c=c: ba(c[sel].sum(1))) for k, c in cc.items()}
    for cnd in "FJ":
        v = preds["L_" + cnd]
        B["null_L_" + cnd] = lambda sel, v=v: ba(null_counts(v, gt, sel))
    D = {"L_J-G_J": lambda s: B["L_J"](s) - B["G_J"](s), "L_F-G_F": lambda s: B["L_F"](s) - B["G_F"](s),
         "L_J-L_F": lambda s: B["L_J"](s) - B["L_F"](s), "G_J-G_F": lambda s: B["G_J"](s) - B["G_F"](s),
         "R=(L_J-L_F)-(G_J-G_F)": lambda s: (B["L_J"](s) - B["L_F"](s)) - (B["G_J"](s) - B["G_F"](s)),
         "L_J-prior_pos": lambda s: B["L_J"](s) - B["prior_pos"](s), "L_J-prior_global": lambda s: B["L_J"](s) - B["prior_global"](s),
         "L_J-null_L_J": lambda s: B["L_J"](s) - B["null_L_J"](s), "L_F-null_L_F": lambda s: B["L_F"](s) - B["null_L_F"](s),
         "L_F-prior_pos": lambda s: B["L_F"](s) - B["prior_pos"](s)}
    pts = {"L_J-G_J": rep["systems"]["L_J"]["BA"] - rep["systems"]["G_J"]["BA"] if None not in (rep["systems"]["L_J"]["BA"], rep["systems"]["G_J"]["BA"]) else None}
    S = rep["systems"]
    g = lambda k: S[k]["BA"]
    try:
        pts = {"L_J-G_J": g("L_J") - g("G_J"), "L_F-G_F": g("L_F") - g("G_F"), "L_J-L_F": g("L_J") - g("L_F"), "G_J-G_F": g("G_J") - g("G_F"),
               "R=(L_J-L_F)-(G_J-G_F)": (g("L_J") - g("L_F")) - (g("G_J") - g("G_F")), "L_J-prior_pos": g("L_J") - g("prior_pos"),
               "L_J-prior_global": g("L_J") - g("prior_global"), "L_J-null_L_J": g("L_J") - g("null_L_J"),
               "L_F-null_L_F": g("L_F") - g("null_L_F"), "L_F-prior_pos": g("L_F") - g("prior_pos")}
    except TypeError:
        pts = {}
    rep["contrasts"] = {k: {"point": pts.get(k), **v} for k, v in boot_diffs(D, sel).items()}
    rep["bootstrap"] = {"seed": SEED, "n": NB, "unit": "case", "note": "class가 사라진 replicate는 제외(n_excluded)"}
    # 생성 출력 상태(원 규칙 재현) 및 보조 분해
    rep["gen_status"] = {"G_F_invalid": int(extra["g_invalid"]["F"].sum()), "G_J_invalid": int(extra["g_invalid"]["J"].sum()),
                         "G_F_nonEOS": int((~extra["g_eos"]).sum()) if False else None}
    inv = extra["g_invalid"]["J"]
    rep["invalid_only_subgroup_G_J"] = {"n": int(inv.sum()), "L_J_acc": float((preds["L_J"][inv] == gt[inv]).mean()) if inv.any() else None,
                                       "note": "설명용 하위집단. 전체 성능을 대체하지 않는다."}
    cov = extra["cov"]
    pos = gt == 1
    rep["coverage"] = {"pos_with_cov": int((pos & cov).sum()), "pos_without_cov": int((pos & ~cov).sum()),
                       "L_J_sens_cov": float((preds["L_J"][pos & cov] == 1).mean()) if (pos & cov).any() else None,
                       "L_J_sens_nocov": float((preds["L_J"][pos & ~cov] == 1).mean()) if (pos & ~cov).any() else None,
                       "L_F_sens_cov": float((preds["L_F"][pos & cov] == 1).mean()) if (pos & cov).any() else None,
                       "L_F_sens_nocov": float((preds["L_F"][pos & ~cov] == 1).mean()) if (pos & ~cov).any() else None,
                       "note": "coverage>0은 시각적 충분성의 증명이 아니다."}
    rep["L_pred_rate_PRESENT"] = {c: float(preds["L_" + c].mean()) for c in "FJ"}
    rep["margin_mean"] = {c: float(extra["margin"][c].mean()) for c in "FJ"}
    return rep


def cmd_prior(a):
    cases, gt = None, None
    lb = json.load(open(f"{SRC65}/data/labels_D.json"))
    m = {}
    for rid, l in lb.items():
        if l["q"] == "W" and l["cond"] == "F":
            m.setdefault(l["slab"], []).append(1 if l["answer"] == "PRESENT" else 0)
    allv = [x for v in m.values() for x in v]
    pos = sum(allv) * 2 > len(allv)
    posp = [int(sum(m[s]) * 2 > len(m[s])) for s in range(NSLAB)]
    out = {"source": f"{SRC65}/data/labels_D.json", "source_sha256": sha_file(f"{SRC65}/data/labels_D.json"),
           "rule": "majority of D6 W labels (F cond); tie -> ABSENT(0)", "global_counts_pos_of_total": [sum(allv), len(allv)],
           "global_pred": int(pos), "position_counts_pos_of_n": {str(s): [sum(m[s]), len(m[s])] for s in range(NSLAB)}, "position_pred": posp}
    R.atomic_write_json(a.out, out)
    print(out)


def cmd_gate_d(a):
    tech = json.load(open(a.tech))
    req = "results/iter_066/data/requests_D.jsonl"
    recs, p, comp = R.verify_completion(a.out_dir, req, a.protocol)
    ok = tech["all_pass"] is True and tech["protocol_digest"] == comp["protocol_digest"] and tech["requests_sha256"] == sha_file(req)
    g = {"for_stage": "E12", "run": bool(ok), "evidence": {
        "tech": {"path": a.tech, "sha256": sha_file(a.tech)}, "D_completion": {"path": os.path.join(a.out_dir, "completion.json"),
                                                                              "sha256": sha_file(os.path.join(a.out_dir, "completion.json"))},
        "D_protocol": {"path": a.protocol, "sha256": sha_file(a.protocol)}, "prior": {"path": a.prior, "sha256": sha_file(a.prior)}},
        "note": "기술 검사(입력 일치·token 경계·causal shift·독립 대조)와 D 완료만 확인. 모델 정답률은 gate가 아니다."}
    R.atomic_write_json(a.out, g)
    print(g["run"])


def cmd_report(a):
    sd = []
    for s in a.stage_dirs:
        stage, d, proto = s.split(":")
        sd.append((stage, d, proto))
    prior = json.load(open(a.prior))
    assert prior["source_sha256"] == sha_file(prior["source"])
    Lrec, Grec, lab, prov = collect(sd)
    cases, gt, preds, extra = arrays(Lrec, Grec, lab)
    rep = analyze(cases, gt, preds, extra, prior)
    n_eos = sum(1 for rid, g in Grec.items() if not g["attempts"][-1]["ended_eos"])
    rep["gen_status"] = {"G_F_invalid": int(extra["g_invalid"]["F"].sum()), "G_J_invalid": int(extra["g_invalid"]["J"].sum()),
                         "gen_nonEOS_total": n_eos,
                         "gen_nonEOS_but_parse_valid": sum(1 for rid, g in Grec.items() if not g["attempts"][-1]["ended_eos"] and M.parse_answer(g["attempts"][-1]["text"]) is not None)}
    rep["provenance"] = {"stages": prov, "prior": {"path": a.prior, "sha256": sha_file(a.prior)},
                         "eval_code": {f: sha_file(f) for f in ("m66_eval.py", "m66_run.py")}}
    rep["stages"] = [s[0] for s in sd]
    R.atomic_write_json(a.out, rep)
    S = rep["systems"]
    print(json.dumps({k: (round(v["BA"], 4) if v["BA"] is not None else None) for k, v in S.items()}))
    for k, v in rep["contrasts"].items():
        print(k, None if v["point"] is None else round(v["point"], 4), v["ci95"], "excl", v["n_excluded"])


def cmd_decide_e12(a):
    rep = json.load(open(a.report))
    assert rep["stages"] == ["E12"]
    S, C = rep["systems"], rep["contrasts"]
    defined = all(S[k]["BA"] is not None for k in ("L_J", "L_F", "G_J", "prior_pos", "null_L_J"))
    if not defined:
        out = {"for_stage": "E36", "run": True, "reason": "E12 BA 미정의: 성능 문턱 대신 E48 class 존재만 확인하고 확대", "criteria": None}
    else:
        LJ, LF, GJ, PP, NL = (S[k]["BA"] for k in ("L_J", "L_F", "G_J", "prior_pos", "null_L_J"))
        c1 = LJ >= 0.65 and (LJ - GJ) >= 0.15
        c2 = LJ >= LF - 0.10 and LJ > PP and (LJ - NL) >= 0.03
        out = {"for_stage": "E36", "run": bool(c1 or c2), "criteria": {"c1_recovery": bool(c1), "c2_residual_signal": bool(c2),
               "L_J": LJ, "L_F": LF, "G_J": GJ, "prior_pos": PP, "null_L_J": NL},
               "rule": "c1: L_J>=0.65 and L_J-G_J>=0.15 / c2: L_J>=L_F-0.10 and L_J>prior_pos(strict) and L_J-null>=0.03"}
    out["evidence"] = {"E12_report": {"path": a.report, "sha256": sha_file(a.report)}}
    R.atomic_write_json(a.out, out)
    print(json.dumps(out))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prior")
    p.add_argument("--out", required=True)
    g = sub.add_parser("gate-d")
    for k in ("tech", "out-dir", "protocol", "prior", "out"):
        g.add_argument("--" + k, required=True)
    r = sub.add_parser("report")
    r.add_argument("--stage-dirs", nargs="+", required=True, help="STAGE:OUT_DIR:PROTOCOL")
    r.add_argument("--prior", required=True)
    r.add_argument("--out", required=True)
    d = sub.add_parser("decide-e12")
    d.add_argument("--report", required=True)
    d.add_argument("--out", required=True)
    a = ap.parse_args()
    {"prior": cmd_prior, "gate-d": cmd_gate_d, "report": cmd_report, "decide-e12": cmd_decide_e12}[a.cmd](a)


if __name__ == "__main__":
    main()
