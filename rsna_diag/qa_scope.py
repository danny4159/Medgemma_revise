"""iter_016 semantic_v1 분석: D36 semantic gate(과거 strict gate 판정은 수정하지 않는다), E180/P60 분석, 확대 결정.

- 모든 응답에 strict 상태, semantic 상태, 변환 종류를 함께 저장한다. 점수는 요청 집합이 완전할 때만 계산한다(qa_eval.require_complete).
- 정답 category는 parser에 들어가지 않는다 (채점에서만 사용).
- 확대 규칙(계획 §3)은 decide_expand로 코드화해 E180 결과를 보기 전에 잠근다 (qa_protocol의 REQUIRED_CODE).
사용:
  python -m rsna_diag.qa_scope d36 --reuse-manifest M --out OUT_JSON
  python -m rsna_diag.qa_scope e180 --protocol P --out OUT_JSON      # 분석 (primary E180, alternate/evidence P60)
"""
import argparse
import collections
import json
import math
import os

import numpy as np

from . import qa_eval as E, qa_gen, qa_requests as Q, qa_run, qa_spec as S

OUT = Q.OUT
Z975, Z95 = 2.2414027, 1.959964
THR_S, THR_PAIR, THR_EV = 0.10, 0.15, 0.10


def sets():
    return json.load(open(f"{OUT}/manifests/sets.json"))


def labels():
    return json.load(open(f"{OUT}/manifests/labels.json"))


def ids_by_cat(name, exclude=None):
    st = sets()
    ex = {i for c in S.CATEGORIES for i in st[exclude][c]} if exclude else set()
    return {c: [i for i in st[name][c] if i not in ex] for c in S.CATEGORIES}


def flat(d):
    return [i for c in S.CATEGORIES for i in d[c]]


def conv_table(pairs):
    """{(ckpt,cond,fmt,id,target): (strict_status, sem_status, conversion)}"""
    out = {}
    for row, rec in pairs:
        if row["target"] not in S.TARGETS:
            continue
        raw, eos = rec["suffix_text_raw"], rec["ended_eos"]
        st = S.parse_answer(row["fmt"], raw, eos)[0]
        ss, _, cv = S.parse_semantic(row["target"], row["fmt"], raw, eos)
        out[(row["checkpoint"], row["condition"], row["fmt"], row["id"], row["target"])] = (st, ss, cv)
    return out


def record_dump(pairs):
    """저장용: 응답별 strict/semantic 상태·변환 종류(원문 일부 포함)."""
    rows = []
    for row, rec in pairs:
        if row["target"] not in S.TARGETS:
            continue
        raw, eos = rec["suffix_text_raw"], rec["ended_eos"]
        sst, sans = S.parse_answer(row["fmt"], raw, eos)
        mst, mans, cv = S.parse_semantic(row["target"], row["fmt"], raw, eos)
        rows.append({"request_id": row["request_id"], "id": row["id"], "checkpoint": row["checkpoint"], "condition": row["condition"],
                     "fmt": row["fmt"], "target": row["target"], "strict": [sst, sans], "semantic": [mst, mans], "conversion": cv,
                     "ended_eos": eos, "n_out": rec["n_output_tokens"], "raw": raw[:80]})
    return rows


# ---------------- D36 semantic gate ----------------
def d36_gate(manifest_path, out):
    """D36 원문 432건을 semantic_v1으로 재평가한다. 모든 checkpoint x target에서 semantic valid>=0.95인 plain을 primary, json을 alternate로 한다.
    정답 정확도는 보지 않는다."""
    man = json.load(open(manifest_path))
    tab = json.load(open(f"{OUT}/manifests/checkpoints.json"))
    st = sets()
    ids = flat({c: st["D36"][c] for c in S.CATEGORIES})
    pairs_all, dump = {}, []
    for fmt in ("plain", "json"):
        for ck in ("M0", "B0", "C"):
            info = man["stages"][f"d36_{fmt}__{ck}"]
            pairs = E.load_reused(info["stage_dir"], info["requests"], ck, info["old_protocol"], tab)
            pairs_all[(fmt, ck)] = pairs
            dump += record_dump(pairs)
    res = {"strict": {}, "semantic": {}}
    for parser, key in (("strict", "strict"), ("semantic", "semantic")):
        for fmt in ("plain", "json"):
            for ck in ("M0", "B0", "C"):
                tb = E.answer_table(pairs_all[(fmt, ck)], parser)
                E.require_complete(tb, [ck], ["direct"], [fmt], ids)
                res[key][f"{fmt}/{ck}"] = E.format_stats(tb, ck, "direct", fmt, ids)
    conv = collections.Counter()
    for r in dump:
        conv[f"{r['fmt']}/{r['target']}/{r['conversion']}"] += 1
    ok = {fmt: all(res["semantic"][f"{fmt}/{ck}"][t]["valid_rate"] >= 0.95 for ck in ("M0", "B0", "C") for t in S.TARGETS) for fmt in ("plain", "json")}
    d = {"parser": S.SEMANTIC_VERSION, "n_patients": len(ids), "n_responses": len(dump), "stats": res, "gate_pass_semantic": ok,
         "primary_format": "plain" if ok["plain"] else None, "alternate_format": "json" if ok["plain"] else None, "conversion_counts": dict(conv),
         "rule": "semantic valid rate >= 0.95 for every checkpoint x target; plain=primary, json=alternate; accuracy not used",
         "note": "과거 iter_015 strict gate 판정은 수정하지 않는다. semantic_v1은 D36을 본 뒤 만든 개발 결정이다."}
    json.dump({"decision": d, "records": dump}, open(out, "w"), indent=1)
    return d


# ---------------- 점수·bound·통계 ----------------
def patient_bounds(tab, key, cat):
    """환자 pair 점수의 가능한 범위 (lo, hi). 알려진 오답(valid&wrong)이 있으면 hi=0, 둘 다 valid&correct면 lo=1, invalid는 미해석."""
    r, want = tab[key], S.GT_PAIR[cat]
    st = [(r[t][0] == "valid", r[t][1] == want[k]) for k, t in enumerate(S.TARGETS)]
    known_wrong = any(v and not c for v, c in st)
    all_right = all(v and c for v, c in st)
    return (1.0 if all_right else 0.0), (0.0 if known_wrong else 1.0)


def bound_vectors(tab, ckpt, cond, fmt, ibc):
    lo, hi = {}, {}
    for c, ids in ibc.items():
        b = [patient_bounds(tab, (ckpt, cond, fmt, i), c) for i in ids]
        lo[c], hi[c] = np.array([x[0] for x in b]), np.array([x[1] for x in b])
    return lo, hi


def diff_bounds(tab_a, ka, tab_b, kb, ibc):
    """S_scope(a)-S_scope(b)의 보수적 범위: (a의 lo - b의 hi, a의 hi - b의 lo) 를 category 평균한 뒤 균등 평균."""
    la, ha = bound_vectors(tab_a, *ka, ibc)
    lb, hb = bound_vectors(tab_b, *kb, ibc)
    lo = float(np.mean([la[c].mean() - hb[c].mean() for c in ibc]))
    hi = float(np.mean([ha[c].mean() - lb[c].mean() for c in ibc]))
    return lo, hi


def cls(x, thr=THR_S):
    return "pos" if x >= thr else ("neg" if x <= -thr else "mid")


def flippable(point, lo, hi, thr=THR_S):
    """보수적 범위가 |thr| 분류 또는 부호를 바꿀 수 있는가."""
    return len({cls(lo, thr), cls(hi, thr), cls(point, thr)}) > 1 or (lo < 0 < hi and point != 0)


def cp_upper(k, n, alpha=0.05):
    """Clopper-Pearson 단측 상한: P(X<=k | p)=alpha를 만족하는 p (이분법, scipy 없이). k=0이면 1-alpha^(1/n)."""
    if k >= n:
        return 1.0
    cdf = lambda p: sum(math.comb(n, j) * p ** j * (1 - p) ** (n - j) for j in range(k + 1))
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if cdf(mid) > alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def discordant(vec_a, vec_b):
    """환자별 두 조건의 정오가 다른 수와 exact 단측 95% 상한 (k=0이면 1-0.05^(1/n), 아니면 Clopper-Pearson)."""
    n = sum(len(v) for v in vec_a.values())
    k = int(sum((vec_a[c] != vec_b[c]).sum() for c in vec_a))
    up = cp_upper(k, n)
    return {"n": n, "discordant": k, "rate": k / n, "exact_one_sided_95_upper": float(up)}


def paired_se(vec_a, vec_b, n_target=None):
    """S_scope 차이의 SE(category별 표본분산, /9)와 category SE. n_target이 있으면 category당 n_target명으로 투영(sqrt(n/n_target))."""
    se_c, var = {}, 0.0
    for c in vec_a:
        d = vec_a[c] - vec_b[c]
        m = len(d)
        se = float(d.std(ddof=1) / math.sqrt(m))
        if n_target:
            se *= math.sqrt(m / n_target)
        se_c[c] = se
        var += se ** 2
    return math.sqrt(var) / 3.0, se_c


def ci_boot(vec_a, vec_b, level):
    b = E.bootstrap_diff(vec_a, vec_b, ci=level)
    return b


def pair_no_yes(tab, ckpt, cond, fmt, ids):
    """NoOpacity/NotNormal의 (no,yes) 정답률과 (no,no) 오류율 (invalid는 어느 쪽도 아님)."""
    n = len(ids)
    ok = err = 0
    for i in ids:
        r = tab[(ckpt, cond, fmt, i)]
        v = [x[1] if x[0] == "valid" else None for x in (r["O"], r["A"])]
        ok += v == ["no", "yes"]
        err += v == ["no", "no"]
    return {"n": n, "no_yes_correct": ok / n, "no_no_error": err / n}


def pair_acc_vec(tab, ckpt, cond, fmt, ids):
    return np.array([float(E.patient_correct(tab, (ckpt, cond, fmt, i), "not_normal_no_opacity")[2]) for i in ids])


def compare(tab_a, ka, tab_b, kb, ibc, level):
    va, vb = E.score_vectors(tab_a, *ka, ibc), E.score_vectors(tab_b, *kb, ibc)
    b = ci_boot(va, vb, level)
    b95 = ci_boot(va, vb, 0.95)
    lo, hi = diff_bounds(tab_a, ka, tab_b, kb, ibc)
    se, se_c = paired_se(va, vb)
    return {"point": b["S_scope"]["point"], f"ci{int(level * 1000) / 10}": b["S_scope"]["ci"], "ci95": b95["S_scope"]["ci"],
            "per_category_ci95": b95["per_category"], "conservative_bounds": [lo, hi],
            "bounds_can_flip": flippable(b["S_scope"]["point"], lo, hi), "se": se, "se_per_category": se_c,
            "discordance": discordant(va, vb)}, va, vb


# ---------------- 확대 결정 (결과를 보기 전에 잠긴 규칙) ----------------
def precision_projection(va, vb, n_main=200):
    se, se_c = paired_se(va, vb, n_target=n_main)
    hw = Z975 * se
    core = {c: Z95 * s for c, s in se_c.items()}
    return {"n_per_category": n_main, "se_S": se, "halfwidth_975": hw, "halfwidth_core_95": core,
            "meets": bool(hw <= 0.075 or any(v <= 0.10 for v in core.values()))}


def decide_expand(main, pairacc, evid, alt, integrity_ok=True):
    """main: {"B0-M0": comp, "C-B0": comp} (semantic plain, E180). pairacc: {"B0-M0": diff, "C-B0": diff} (NoOpacity/NotNormal (no,yes) 정답률 차이).
    evid: predicted-unavailable 비교(P60) 또는 None. alt: {"B0-M0": diff_json_P60, "C-B0": ...}.
    returns dict(expand, reasons, hold_reasons)."""
    reasons, hold = [], []
    for k, c in main.items():
        pt = c["point"]
        if abs(pt) >= THR_S:
            reasons.append(f"{k}: |S_scope diff|={abs(pt):.3f}>=0.10")
        if abs(pairacc[k]["diff"]) >= THR_PAIR:
            reasons.append(f"{k}: NoOpacity/NotNormal (no,yes) accuracy diff |{pairacc[k]['diff']:.3f}|>=0.15")
        ci = c["ci97.5"]
        near = (ci[0] <= THR_S <= ci[1]) or (ci[0] <= -THR_S <= ci[1])
        if near and abs(pt) < THR_S and c["projection"]["meets"]:
            reasons.append(f"{k}: CI {ci[0]:.3f},{ci[1]:.3f} contains an important effect (|0.10|) and E600 projected precision "
                           f"hw97.5={c['projection']['halfwidth_975']:.3f} meets the target")
        if c["bounds_can_flip"]:
            hold.append(f"{k}: residual invalid can flip the conclusion (conservative bounds {c['conservative_bounds']})")
        a = alt.get(k)
        if a is not None and abs(a["diff"]) >= THR_S and abs(pt) >= THR_S and np.sign(a["diff"]) != np.sign(pt):
            hold.append(f"{k}: plain and json give opposite important directions ({pt:.3f} vs {a['diff']:.3f})")
    if evid is not None:
        if abs(evid["point"]) >= THR_EV:
            reasons.append(f"evidence predicted-unavailable diff {evid['point']:.3f} (|.|>=0.10)")
        ci = evid["ci95"]
        if (ci[0] <= THR_EV <= ci[1] or ci[0] <= -THR_EV <= ci[1]) and abs(evid["point"]) < THR_EV and evid["projection"]["meets"]:
            reasons.append("evidence CI contains an important effect and P180 projected precision meets the target")
    if not integrity_ok:
        hold.append("integrity not ok")
    return {"expand": bool(reasons) and not hold, "reasons": reasons, "hold_reasons": hold,
            "rule": "plan §3: |S_scope diff|>=0.10 | pair acc diff>=0.15 | evidence diff>=0.10 | CI contains important effect & projected precision meets; hold if residual invalid or format directions flip"}


def seed_trigger(main, alt):
    """계획 §4: B0-M0에서 중요 효과(|S|>=0.10)가 있고 주 비교 CI가 0을 제외하며 alternate도 같은 방향일 때만 기존 B29/B43 실행."""
    c = main["B0-M0"]
    ci = c["ci97.5"]
    a = alt.get("B0-M0")
    ok = abs(c["point"]) >= THR_S and (ci[0] > 0 or ci[1] < 0) and a is not None and np.sign(a["diff"]) == np.sign(c["point"]) and a["diff"] != 0
    return {"trigger": bool(ok), "B0-M0": c["point"], "ci97.5": ci, "alternate_diff": None if a is None else a["diff"],
            "note": "C만의 변화나 모듈형 효과만으로는 seed 실행을 추가하지 않는다."}


def interpret(main, pairacc, evid, alt):
    """계획의 '결과별 의미' 분류(참고용 서술). 최종 해석은 보고서에서 한다."""
    lab = []
    for k, c in main.items():
        pt, ci = c["point"], c["ci97.5"]
        if pt <= -THR_S or pairacc[k]["diff"] <= -THR_PAIR:
            lab.append(f"{k}: target_scope_degradation_candidate (needs CI/alternate/seed support)")
        elif pt >= THR_S and ci[0] > 0 and alt.get(k) is not None and alt[k]["diff"] > 0:
            lab.append(f"{k}: positive_transfer_candidate")
    inside = all(-THR_S <= main[k]["ci97.5"][0] and main[k]["ci97.5"][1] <= THR_S for k in main)
    if inside and (evid is None or abs(evid["point"]) < THR_EV):
        lab.append("no_substantial_difference_within_[-0.10,0.10] (CI-based; not proof of equivalence)")
    return lab


# ---------------- E180 분석 ----------------
ROOTS = {}


def load_new(stage, ckpt, protocol):
    """stage: 이름 또는 이름 목록(확대 시 E180 + 신규 stage를 합친다). protocol: 경로 또는 {stage: 경로} (stage별 잠금 파일)."""
    if isinstance(stage, (list, tuple)):
        return [p for s_ in stage for p in load_new(s_, ckpt, protocol)]
    pr = protocol[stage] if isinstance(protocol, dict) else protocol
    return E.load_stage(stage, ckpt, pr, ROOTS.get(stage, "gen"))


def analyze(protocol, out, primary_stage="e180_plain", alt_stage="p60_json", ev_stage="p60_ev", main_set="E180", panel_set="P60",
            panel_override=None, with_bbox=True, roots=None):
    """main_set/panel_set: 표본 이름 (E180/P60 = 본평가, E600/P180 = 확대). panel_override/roots/with_bbox는 코드 경로 dry-run 전용."""
    ROOTS.clear()
    ROOTS.update(roots or {})
    lab = labels()
    ibc = ids_by_cat(main_set)
    ids = flat(ibc)
    pbc = panel_override or ids_by_cat(panel_set)
    pids = flat(pbc)
    pairs = {("plain", ck): load_new(primary_stage, ck, protocol) for ck in ("M0", "B0", "C")}
    tsem = {}
    tstr = {}
    for ck in ("M0", "B0", "C"):
        tsem.update(E.answer_table(pairs[("plain", ck)], "semantic"))
        tstr.update(E.answer_table(pairs[("plain", ck)], "strict"))
    E.require_complete(tsem, ["M0", "B0", "C"], ["direct"], ["plain"], ids)
    res = {"n_patients": len(ids), "n_requests_primary": sum(len(v) for v in pairs.values()), "primary_format": "plain"}
    gt_cat = {i: lab[i]["category"] for i in ids}
    res["scores"] = {}
    for ck in ("M0", "B0", "C"):
        row = {}
        for pname, tb in (("semantic", tsem), ("strict", tstr)):
            vec = E.score_vectors(tb, ck, "direct", "plain", ibc)
            sc, per = E.s_scope(vec)
            row[pname] = {"S_scope": sc, "per_category": per, "ci95": E.boot_ci(vec),
                          "valid": E.format_stats(tb, ck, "direct", "plain", ids),
                          "balanced_accuracy": {t: E.balanced_accuracy(tb, ck, "direct", "plain", t, gt_cat) for t in S.TARGETS},
                          "pair_confusion": E.pair_confusion(tb, ck, "direct", "plain", gt_cat),
                          "no_opacity_not_normal": pair_no_yes(tb, ck, "direct", "plain", ibc["not_normal_no_opacity"])}
        res["scores"][ck] = row
    conv = collections.Counter()
    for r in record_dump([p for ck in pairs for p in pairs[ck]]):
        conv[f"{r['target']}/{r['conversion']}"] += 1
    res["conversion_counts"] = dict(conv)
    res["strict_to_semantic_change"] = {ck: res["scores"][ck]["semantic"]["S_scope"] - res["scores"][ck]["strict"]["S_scope"] for ck in ("M0", "B0", "C")}
    res["constant_pair_baselines"] = E.constant_baselines(ibc)
    # 주 비교
    main, pairacc, vecs = {}, {}, {}
    for name, (a, b) in {"B0-M0": ("B0", "M0"), "C-B0": ("C", "B0")}.items():
        c, va, vb = compare(tsem, (a, "direct", "plain"), tsem, (b, "direct", "plain"), ibc, 0.975)
        c["projection"] = precision_projection(va, vb)
        cs, _, _ = compare(tstr, (a, "direct", "plain"), tstr, (b, "direct", "plain"), ibc, 0.975)
        c["strict_point"] = cs["point"]
        c["strict_ci97.5"] = cs["ci97.5"]
        main[name] = c
        pa = pair_acc_vec(tsem, a, "direct", "plain", ibc["not_normal_no_opacity"])
        pb = pair_acc_vec(tsem, b, "direct", "plain", ibc["not_normal_no_opacity"])
        rng = np.random.default_rng(E.BOOT_SEED)
        idx = rng.integers(0, len(pa), size=(E.BOOT_N, len(pa)))
        bs = pa[idx].mean(1) - pb[idx].mean(1)
        pairacc[name] = {"diff": float(pa.mean() - pb.mean()), "ci95": [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]}
    res["main_semantic_plain_E180"] = main
    res["no_opacity_not_normal_pair_accuracy_diff"] = pairacc
    # alternate (P60, json) — 같은 P60 환자의 plain과 비교
    alt, alt_res = {}, {}
    if alt_stage:
        tj = {}
        for ck in ("M0", "B0", "C"):
            tj.update(E.answer_table(load_new(alt_stage, ck, protocol), "semantic"))
        E.require_complete(tj, ["M0", "B0", "C"], ["direct"], ["json"], pids)
        alt_res["scores"] = {}
        for ck in ("M0", "B0", "C"):
            vec = E.score_vectors(tj, ck, "direct", "json", pbc)
            alt_res["scores"][ck] = {"S_scope": E.s_scope(vec)[0], "per_category": E.s_scope(vec)[1], "valid": E.format_stats(tj, ck, "direct", "json", pids)}
        tpp = {k: v for k, v in tsem.items() if k[3] in set(pids)}
        both = {**tpp, **tj}
        alt_res["format_agreement"] = {ck: E.agreement(both, ck, "direct", pids) for ck in ("M0", "B0", "C")}
        for name, (a, b) in {"B0-M0": ("B0", "M0"), "C-B0": ("C", "B0")}.items():
            c, _, _ = compare(tj, (a, "direct", "json"), tj, (b, "direct", "json"), pbc, 0.95)
            alt[name] = {"diff": c["point"], "ci95": c["ci95"]}
            alt_res[name] = c
        res["alternate_json_P60"] = alt_res
    # bbox·detector+rule
    if with_bbox:
        res["bbox_E180"] = {ck: {k: v for k, v in E.bbox_summary(ck, ids, lab).items() if k in ("n_positive", "f1@0.3", "f1@0.5", "valid_rate_all", "positive_valid_empty", "by_n_gt", "neg_Normal", "neg_NoOpacity/NotNormal")} for ck in ("M0", "B0", "C")}
        res["detector_rule"] = {ck: E.detector_rule(ck, ibc)[0] for ck in ("M0", "B0", "C")}
    # evidence (M0 reader, P60)
    evid = None
    if ev_stage:
        te = E.answer_table(load_new(ev_stage, "M0", protocol), "semantic")
        tes = E.answer_table(load_new(ev_stage, "M0", protocol), "strict")
        conds = ["ev_predicted", "ev_unavailable", "ev_oracle"]
        E.require_complete(te, ["M0"], conds, ["plain"], pids)
        er = {"scores": {}, "strict_scores": {}}
        for cd in conds:
            v = E.score_vectors(te, "M0", cd, "plain", pbc)
            er["scores"][cd] = {"S_scope": E.s_scope(v)[0], "per_category": E.s_scope(v)[1], "valid": E.format_stats(te, "M0", cd, "plain", pids),
                                "balanced_accuracy": {t: E.balanced_accuracy(te, "M0", cd, "plain", t, {i: lab[i]["category"] for i in pids}) for t in S.TARGETS},
                                "pair_confusion": E.pair_confusion(te, "M0", cd, "plain", {i: lab[i]["category"] for i in pids})}
            er["strict_scores"][cd] = E.s_scope(E.score_vectors(tes, "M0", cd, "plain", pbc))[0]
        c, va, vb = compare(te, ("M0", "ev_predicted", "plain"), te, ("M0", "ev_unavailable", "plain"), pbc, 0.95)
        c["projection"] = precision_projection(va, vb, n_main=60)
        er["predicted_minus_unavailable"] = c
        c2, _, _ = compare(te, ("M0", "ev_predicted", "plain"), tsem_direct_for_pids(tsem, pids), ("M0", "direct", "plain"), pbc, 0.95)
        er["predicted_minus_direct_M0"] = c2
        c3, _, _ = compare(te, ("M0", "ev_oracle", "plain"), te, ("M0", "ev_unavailable", "plain"), pbc, 0.95)
        er["oracle_minus_unavailable_oracle_only"] = c3
        er["predicted_source_status"] = dict(collections.Counter(r["extra"].get("source_status") for r, _ in load_new(ev_stage, "M0", protocol) if r["condition"] == "ev_predicted"))
        res["evidence_M0_P60"] = er
        evid = {"point": c["point"], "ci95": c["ci95"], "projection": c["projection"]}
    res["seed_reproduction_trigger"] = seed_trigger(main, alt)
    res["decision"] = decide_expand(main, pairacc, evid, alt, integrity_ok=True)
    res["interpretation_labels"] = interpret(main, pairacc, evid, alt)
    json.dump(res, open(out, "w"), indent=1, default=float)
    return res


def tsem_direct_for_pids(tsem, pids):
    return {k: v for k, v in tsem.items() if k[3] in set(pids)}


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    d = sp.add_parser("d36")
    d.add_argument("--reuse-manifest", required=True)
    d.add_argument("--out", required=True)
    e = sp.add_parser("e180")
    e.add_argument("--protocol", required=True)
    e.add_argument("--out", required=True)
    x = sp.add_parser("e600")
    x.add_argument("--protocol-e180", required=True)
    x.add_argument("--protocol-e600", required=True)
    x.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "d36":
        r = d36_gate(a.reuse_manifest, a.out)
        print(json.dumps({k: r[k] for k in ("gate_pass_semantic", "primary_format", "alternate_format", "conversion_counts")}, indent=1))
        return
    from . import lock_protocol, qa_protocol
    E.ALLOW_CHANGED = ("rsna_diag/qa_scope.py", "rsna_diag/qa_eval.py", "rsna_diag/qa_protocol.py")

    def changed(path):
        lk = json.load(open(path))["locked"]["files"]
        return {f: {"locked": h, "at_analysis": lock_protocol.sha(f)} for f, h in lk.items() if lock_protocol.sha(f) != h}

    if a.cmd == "e180":
        # 잠금 뒤 결과 열람 전에 분석 진입 코드 3개(qa_scope 병합 TypeError, qa_eval/qa_protocol의 allow_changed 통로)를 수정했다. 규칙·임계값·표본은 불변.
        r = analyze(a.protocol, a.out)
        r["analysis_code"] = {"changed_after_lock_before_results": changed(a.protocol),
                              "note": "결과를 보기 전 수정: qa_scope alt 표 병합 TypeError 1줄 + qa_protocol.verify(allow_changed)/qa_eval.ALLOW_CHANGED 통로. 규칙·임계값·표본 불변. 다른 잠긴 파일은 모두 일치."}
    else:
        pd = {"e180_plain": a.protocol_e180, "p60_json": a.protocol_e180, "p60_ev": a.protocol_e180,
              "e600x_plain": a.protocol_e600, "p180x_json": a.protocol_e600, "p180x_ev": a.protocol_e600}
        r = analyze(pd, a.out, primary_stage=["e180_plain", "e600x_plain"], alt_stage=["p60_json", "p180x_json"], ev_stage=["p60_ev", "p180x_ev"],
                    main_set="E600", panel_set="P180")
        r["analysis_code"] = {"e180_protocol_changed_files": changed(a.protocol_e180), "e600_protocol_changed_files": changed(a.protocol_e600),
                              "note": "E180 protocol 잠금 이후 분석 코드(qa_scope/qa_eval/qa_protocol/qa_requests)가 결과 열람 전·후에 수정됐다. 해당 hash를 기록한다."}
    json.dump(r, open(a.out, "w"), indent=1, default=float)
    print(json.dumps({"decision": r["decision"], "labels": r["interpretation_labels"], "seed": r.get("seed_reproduction_trigger")}, indent=1))


if __name__ == "__main__":
    main()
