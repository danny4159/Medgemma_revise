"""iter_017 U/B/K/L(/X) 분석·확대 결정 (결과를 보기 전에 protocol에 잠근다).

- 점수는 완료·요청 집합·completion 내용이 검증된 stage(qa_eval.load_stage)와 iter_016 재사용 stage(qa_reuse.verify_old_stage 호환성 검증)에서만 계산한다.
- 주지표: semantic S_scope(category별 '두 질문 모두 정답' 비율의 균등 평균). 주 비교 B-U, L-K: category 내 환자 paired bootstrap 10,000회, seed 20260927, 97.5% CI.
  그 외 비교는 95% 탐색 CI. 확대·X 판단 경계: |S_scope| 0.05, category별 정답 쌍 정확도 |0.10| (계획 §3).
사용:
  python -m rsna_diag.ev17_analysis analyze --set P180 --new p180_ev:PROTO[,stage2:PROTO2] --out OUT.json [--x stage:PROTO]   (결정은 OUT_decision.json에도 저장)
"""
import argparse
import collections
import json
import math

import numpy as np

from . import ev17_reuse, ev17_spec as V, qa_eval as E, qa_gen, qa_requests as Q, qa_reuse, qa_scope as SC, qa_spec as S

OUT = Q.OUT
IMP_S, IMP_CAT = 0.05, 0.10
Z975, Z95 = 2.2414027, 1.959964
MAIN = {"B-U": ("B", "U"), "L-K": ("L", "K")}


def old_pairs(manifest):
    """iter_016 재사용 stage 전체를 호환성 검증 후 [(row, record)]로."""
    tab = json.load(open(f"{OUT}/manifests/checkpoints.json"))
    out = {}
    for name, info in manifest["iter016_stages"].items():
        out[name] = E.load_reused(info["stage_dir"], info["requests"], name.split("__")[1], info["old_protocol"], tab)
    return out


def ids_of(name, exclude=None):
    return SC.ids_by_cat(name, exclude)


def build_tables(new_stages, old, ids_all):
    """new_stages: [(stage, protocol)] (M0). returns semantic/strict 답 표, 신규 pair 목록."""
    new = [p for st, pr in new_stages for p in E.load_stage(st, "M0", pr, "gen")]
    pairs = list(new) + [p for v in old.values() for p in v]
    tsem, tstr = E.answer_table(pairs, "semantic"), E.answer_table(pairs, "strict")
    return tsem, tstr, new


def status_by_id(ids, src):
    st = {}
    for i in ids:
        rec = src.get(i)
        if rec is None:
            raise Q.RequestError(f"no B0 bbox record for {i}")
        b, s = Q.predicted_boxes(rec)
        st[i] = {"status": s, "k": None if b is None else len(b)}
    return st


def vecs(tab, ck, cond, ibc):
    return E.score_vectors(tab, ck, cond, "plain", ibc)


def cmp_(tab, ka, kb, ibc, level):
    c, va, vb = SC.compare(tab, (*ka, "plain"), tab, (*kb, "plain"), ibc, level)
    se, se_c = SC.paired_se(va, vb, n_target=200)
    c["projection_E600"] = {"halfwidth_975": Z975 * se, "halfwidth_cat_95": {k: Z95 * v for k, v in se_c.items()}}
    return c


def has_imp(lo, hi, imp):
    return lo <= -imp or hi >= imp


def has_null(lo, hi, imp):
    return lo < imp and hi > -imp


def contains(lo, hi, x):
    return lo <= x <= hi


def decide_comparison(c, at_n=None):
    """계획 §3의 세 확대 규칙을 한 비교(c=cmp_ 결과)에 적용. at_n이 있으면 X 판단용으로 '현재 표본의 반폭'을 정밀도 기준에 쓴다."""
    lo, hi = c["ci97.5"]
    pt = c["point"]
    r1 = abs(pt) >= IMP_S and (contains(lo, hi, 0) or contains(lo, hi, IMP_S) or contains(lo, hi, -IMP_S))
    cats = []
    for cat, v in c["per_category_ci95"].items():
        plo, phi = v["ci"]
        if abs(v["point"]) >= IMP_CAT and (contains(plo, phi, 0) or contains(plo, phi, IMP_CAT) or contains(plo, phi, -IMP_CAT)):
            cats.append(cat)
    r2 = bool(cats)
    pr = c["projection_E600"] if at_n is None else c["projection_now"]
    prec = pr["halfwidth_975"] <= IMP_S or any(v <= IMP_CAT for v in pr["halfwidth_cat_95"].values())
    r3 = has_imp(lo, hi, IMP_S) and has_null(lo, hi, IMP_S) and prec
    return {"point": pt, "ci97.5": [lo, hi], "rule1_point_ge_0.05_and_judgment_changeable": bool(r1),
            "rule2_category_ge_0.10_and_more_patients_needed": bool(r2), "rule2_categories": cats,
            "rule3_ci_contains_important_and_null_and_precision_meets": bool(r3), "precision": pr, "trigger": bool(r1 or r2 or r3)}


def now_projection(tab, ka, kb, ibc):
    va, vb = vecs(tab, ka[0], ka[1], ibc), vecs(tab, kb[0], kb[1], ibc)
    se, se_c = SC.paired_se(va, vb)
    return {"halfwidth_975": Z975 * se, "halfwidth_cat_95": {k: Z95 * v for k, v in se_c.items()}}


def gates(res):
    g = {"format": {}, "empty_consistency": res["empty_consistency"]}
    ok = True
    for cond, r in res["format"].items():
        for t, v in r.items():
            g["format"][f"{cond}/{t}"] = v["valid_rate"]
            ok &= v["valid_rate"] >= 0.95
    g["format_ok"] = bool(ok)
    g["consistency_ok"] = res["empty_consistency"]["n_mismatch"] == 0
    g["all_ok"] = bool(ok and g["consistency_ok"])
    return g


def decide_expand(res):
    g = gates(res)
    per = {k: decide_comparison(res["main"][k]) for k in MAIN_NAMES}
    trig = [k for k, v in per.items() if v["trigger"]]
    hold = [] if g["all_ok"] else ["input/format gate not passed (" + json.dumps({k: g[k] for k in ("format_ok", "consistency_ok")}) + ")"]
    return {"expand_to_E600": bool(trig) and not hold, "triggered_by": trig, "hold_reasons": hold, "per_comparison": per, "gates": g,
            "rule": "plan §3: rule1 |S diff|>=0.05 & CI can change judgment; rule2 category |pair-acc diff|>=0.10 & CI (95%) can change; "
                    "rule3 97.5% CI contains both an important (|.|>=0.05) and a null value & projected E600 precision <=0.05 (S) or <=0.10 (category)"}


def decide_x(res):
    """X: L-K에 대해서만 (L-B 단독 차이로는 실행하지 않는다). 정밀도는 도달한 표본의 현재 반폭 기준."""
    c = dict(res["main"]["L-K"])
    c["projection_now"] = res["projection_now"]["L-K"]
    d = decide_comparison(c, at_n=True)
    g = gates(res)
    return {"run_X": bool(d["trigger"]) and g["all_ok"], "L-K": d, "gates": g,
            "rule": "plan §4: L-K |S|>=0.05 or category>=0.10, or CI contains important & null with current-sample precision <=0.05/0.10. L-B alone never triggers."}


MAIN_NAMES = list(MAIN)


def empty_consistency(tsem_raw_pairs, ids_status):
    """빈(valid_empty) 예측 환자에서 B/K/L (동일 prompt)의 원문 응답이 같은지, invalid에서 U/B/K/L이 같은지."""
    by = collections.defaultdict(dict)
    for row, rec in tsem_raw_pairs:
        by[(row["id"], row["target"])][row["condition"]] = rec["suffix_text_raw"]
    n = mism = 0
    ex = []
    for i, s in ids_status.items():
        grp = ("ev17_B", "ev17_K", "ev17_L") if s["status"] == "valid_empty" else (("ev17_U", "ev17_B", "ev17_K", "ev17_L") if s["status"] not in ("valid_nonempty",) else None)
        if not grp:
            continue
        for t in S.TARGETS:
            d = by[(i, t)]
            if not all(g in d for g in grp):
                continue
            n += 1
            if len({d[g] for g in grp}) != 1:
                mism += 1
                ex.append({"id": i, "target": t, "raw": {g: d[g][:40] for g in grp}})
    return {"n_groups": n, "n_mismatch": mism, "examples": ex[:10]}


def subset_effect(tab, ka, kb, ibc, ids_status, which):
    """which: nonempty | empty | invalid (B0 localizer 출력 상태로 정의한 조건부 분석). category별 paired 평균 차이와 95% bootstrap CI."""
    keep = {"nonempty": lambda s: s == "valid_nonempty", "empty": lambda s: s == "valid_empty",
            "invalid": lambda s: s not in ("valid_nonempty", "valid_empty")}[which]
    out = {}
    rng = np.random.default_rng(E.BOOT_SEED)
    for c, ids in ibc.items():
        sel = [i for i in ids if keep(ids_status[i]["status"])]
        if not sel:
            out[c] = {"n": 0}
            continue
        a = np.array([float(E.patient_correct(tab, (ka[0], ka[1], "plain", i), c)[2]) for i in sel])
        b = np.array([float(E.patient_correct(tab, (kb[0], kb[1], "plain", i), c)[2]) for i in sel])
        idx = rng.integers(0, len(sel), size=(E.BOOT_N, len(sel)))
        bs = a[idx].mean(1) - b[idx].mean(1)
        out[c] = {"n": len(sel), "acc_a": float(a.mean()), "acc_b": float(b.mean()), "diff": float(a.mean() - b.mean()),
                  "ci95": [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]}
    return out


def cost_table(pairs, tab_ck=None):
    """조건별 reader 호출·평균 입력 token·평균 요청 시간 (localizer 호출은 별도 열)."""
    agg = collections.defaultdict(lambda: [0, 0, 0.0, 0])
    for row, rec in pairs:
        if row["target"] not in S.TARGETS:
            continue
        a = agg[(row["checkpoint"], row["condition"])]
        a[0] += 1
        a[1] += rec["n_input_tokens"]
        a[2] += rec["runtime_s_total"]
        a[3] += rec["n_output_tokens"]
    return {f"{k[0]}/{k[1]}": {"n_requests": v[0], "mean_input_tokens": v[1] / v[0], "mean_request_s": v[2] / v[0], "mean_output_tokens": v[3] / v[0]}
            for k, v in agg.items()}


def analyze(set_name, new_stages, out, x_stages=None, panel="P180"):
    ev17_reuse.install_pins()
    manifest = json.load(open(ev17_reuse.MANIFEST))
    lab = SC.labels()
    ibc = ids_of(set_name)
    ids = SC.flat(ibc)
    pbc = ids_of(panel)
    pids = SC.flat(pbc)
    old = old_pairs(manifest)
    tsem, tstr, new = build_tables(new_stages, old, ids)
    keep = set(ids) | set(pids)
    tsem = {k: v for k, v in tsem.items() if k[3] in keep}
    tstr = {k: v for k, v in tstr.items() if k[3] in keep}
    conds = ["U", "B", "K", "L"]
    xnew = []
    if x_stages:
        xnew = [p for st, pr in x_stages for p in E.load_stage(st, "M0", pr, "gen")]
        tsem.update({k: v for k, v in E.answer_table(xnew, "semantic").items() if k[3] in keep})
        tstr.update({k: v for k, v in E.answer_table(xnew, "strict").items() if k[3] in keep})
        conds.append("X")
    E.require_complete(tsem, ["M0"], [V.COND_NAME[c] for c in conds], ["plain"], ids)
    E.require_complete(tsem, ["M0", "B0", "C"], ["direct"], ["plain"], ids)
    E.require_complete(tsem, ["M0"], ["ev_predicted", "ev_unavailable", "ev_oracle"], ["plain"], pids)
    src = Q.bbox_records("B0")
    stt = status_by_id(ids, src)
    gt_cat = {i: lab[i]["category"] for i in ids}
    res = {"set": set_name, "n_patients": len(ids), "n_logical_requests_new": len(new) + len(xnew), "conditions": conds,
           "bbox_source_status": {c: dict(collections.Counter(stt[i]["status"] for i in ibc[c])) for c in ibc},
           "nonempty_k": {c: dict(collections.Counter(stt[i]["k"] for i in ibc[c] if stt[i]["status"] == "valid_nonempty")) for c in ibc}}
    keys = {c: ("M0", V.COND_NAME[c]) for c in conds}
    keys.update({"direct_M0": ("M0", "direct"), "direct_B0": ("B0", "direct"), "direct_C": ("C", "direct")})
    res["scores"], res["format"] = {}, {}
    for name, (ck, cond) in keys.items():
        row = {}
        for pn, tb in (("semantic", tsem), ("strict", tstr)):
            v = vecs(tb, ck, cond, ibc)
            sc, per = E.s_scope(v)
            row[pn] = {"S_scope": sc, "per_category": per, "ci95": E.boot_ci(v), "valid": E.format_stats(tb, ck, cond, "plain", ids),
                       "pair_confusion": E.pair_confusion(tb, ck, cond, "plain", gt_cat),
                       "balanced_accuracy": {t: E.balanced_accuracy(tb, ck, cond, "plain", t, gt_cat) for t in S.TARGETS}}
        res["scores"][name] = row
        res["format"][name] = row["semantic"]["valid"]
    conv = collections.Counter()
    for r in SC.record_dump(new + xnew):
        conv[f"{r['condition']}/{r['target']}/{r['conversion']}"] += 1
    res["conversion_counts"] = dict(conv)
    res["empty_consistency"] = empty_consistency(new, stt)
    # 주 비교 (97.5%)와 탐색 비교 (95%)
    res["main"], res["projection_now"] = {}, {}
    for nm, (a, b) in MAIN.items():
        res["main"][nm] = cmp_(tsem, keys[a], keys[b], ibc, 0.975)
        res["projection_now"][nm] = now_projection(tsem, keys[a], keys[b], ibc)
        res["main"][nm]["strict_point"] = cmp_(tstr, keys[a], keys[b], ibc, 0.975)["point"]
    sec = {"K-B": ("K", "B"), "L-B": ("L", "B"), "K-U": ("K", "U"), "L-U": ("L", "U"),
           "U-directM0": ("U", "direct_M0"), "B-directM0": ("B", "direct_M0"), "K-directM0": ("K", "direct_M0"), "L-directM0": ("L", "direct_M0"),
           "L-directB0": ("L", "direct_B0"), "L-directC": ("L", "direct_C")}
    if "X" in conds:
        sec.update({"L-X": ("L", "X"), "X-K": ("X", "K"), "X-U": ("X", "U")})
    res["secondary"] = {nm: cmp_(tsem, keys[a], keys[b], ibc, 0.95) for nm, (a, b) in sec.items()}
    # 기존 문구 조건과의 차이 (P180만; 특정 문장의 단독 인과 효과가 아니다)
    okeys = {"old_predicted": ("M0", "ev_predicted"), "old_unavailable": ("M0", "ev_unavailable")}
    res["vs_old_wording_P180"] = {}
    for nm, (a, b) in {"L-old_predicted": ("L", "old_predicted"), "K-old_predicted": ("K", "old_predicted"), "B-old_predicted": ("B", "old_predicted"),
                       "U-old_unavailable": ("U", "old_unavailable"), "old_predicted-old_unavailable": ("old_predicted", "old_unavailable")}.items():
        ka = keys.get(a) or okeys[a]
        kb = keys.get(b) or okeys[b]
        res["vs_old_wording_P180"][nm] = cmp_(tsem, ka, kb, pbc, 0.95)
    res["old_reference_scores_P180"] = {}
    for nm in ("ev_predicted", "ev_unavailable", "ev_oracle"):
        v = vecs(tsem, "M0", nm, pbc)
        res["old_reference_scores_P180"][nm] = {"S_scope": E.s_scope(v)[0], "per_category": E.s_scope(v)[1],
                                                "note": "oracle는 원인 분리용 참고이며 실용 비교·순위에 포함하지 않는다" if nm == "ev_oracle" else "iter_016 문구 조건"}
    # 조건부 하위 집단 (B0 출력 상태로 정의; 전체 환자 효과를 대체하지 않는다)
    res["subsets"] = {w: {nm: subset_effect(tsem, keys[a], keys[b], ibc, stt, w) for nm, (a, b) in
                          {"B-U": ("B", "U"), "K-B": ("K", "B"), "L-K": ("L", "K"), "L-U": ("L", "U"), "L-directM0": ("L", "direct_M0")}.items()}
                      for w in ("nonempty", "empty", "invalid")}
    # 규칙 baseline과 고정 답 쌍
    res["detector_rule"] = E.detector_rule("B0", ibc)[0]
    res["constant_pair_baselines"] = E.constant_baselines(ibc)
    res["cost"] = cost_table(new + xnew + [p for n_, v in old.items() if n_.split("__")[0] in ("e180_plain", "e600x_plain") and n_.endswith("__M0") for p in v])
    res["decision_expand"] = decide_expand(res) if set_name == "P180" else None
    res["decision_x"] = decide_x(res)
    json.dump(res, open(out, "w"), indent=1, default=float)
    json.dump({"set": set_name, "decision_expand": res["decision_expand"], "decision_x": res["decision_x"]}, open(out.replace(".json", "_decision.json"), "w"),
              indent=1, default=float)
    per = [{"request_id": r["request_id"], "id": r["id"], "condition": r["condition"], "target": r["target"], "raw": rec["suffix_text_raw"],
            "ended_eos": rec["ended_eos"], "n_out": rec["n_output_tokens"], "final_cap": rec["final_cap"]} for r, rec in new + xnew]
    with open(out.replace(".json", "_raw.jsonl"), "w") as f:
        for p in per:
            f.write(json.dumps(p) + "\n")
    return res


def parse_stages(s):
    return [tuple(x.split(":", 1)) for x in s.split(",")] if s else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["analyze"])
    ap.add_argument("--set", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--x", default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if not a.out.endswith(".json"):
        raise SystemExit("--out must end with .json")
    r = analyze(a.set, parse_stages(a.new), a.out, parse_stages(a.x))
    print(json.dumps({"S_scope": {k: round(v["semantic"]["S_scope"], 4) for k, v in r["scores"].items()},
                      "main": {k: [round(v["point"], 4), v["ci97.5"]] for k, v in r["main"].items()},
                      "decision_expand": r["decision_expand"] and {k: r["decision_expand"][k] for k in ("expand_to_E600", "triggered_by", "hold_reasons")},
                      "decision_x": {k: r["decision_x"][k] for k in ("run_X",)}}, indent=1, default=float))


if __name__ == "__main__":
    main()
