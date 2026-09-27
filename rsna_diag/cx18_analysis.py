"""iter_018 target-scope 진단(CheXpert) 평가: raw generation record -> 답 표 -> 주효과 H(macro accuracy(D)-accuracy(Tscope), 주방향
main=Cardiomegaly reference-> Pleural Effusion 판단) -> 환자 paired bootstrap -> 확대 결정(E48) -> 최종 보고(F).

점수는 qa_run.verify_job/verify_completion으로 검증을 통과한(요청 집합과 정확히 일치, 완료된) stage에서만 계산한다.
사용:
  python -m rsna_diag.cx18_analysis gate --stage d16_plain --protocol P --out results/iter_018/d16/gate.json
  python -m rsna_diag.cx18_analysis expand-decision --stage e48_plain --protocol P --out results/iter_018/e48/decision.json
  python -m rsna_diag.cx18_analysis report --stage f_plain --protocol P --out results/iter_018/f/report.json
"""
import argparse
import json
import math
import os

import numpy as np

from . import cx18_spec as CX, generate, qa_protocol, qa_requests as Q

OUT = "results/iter_018"
CKPT = "M0"
BOOT_N, BOOT_SEED = 10000, 20260928
Z975 = 1.9599639845400545


class AnalysisError(RuntimeError):
    pass


# ---------- 원시 결과 로딩과 답 표 ----------

def load_stage(stage, protocol, gen_root="gen"):
    from . import qa_gen, qa_run
    pdig = qa_protocol.verify(protocol)
    rp = f"{OUT}/requests/{stage}__{CKPT}.jsonl"
    cfg, _ = qa_protocol.static_cfg()
    rows = Q.load_rows(rp, cfg)
    if json.load(open(protocol))["locked"]["files"].get(rp) != generate.sha(open(rp, "rb").read()):
        raise AnalysisError(f"{rp} not locked in {protocol}")
    d = f"{OUT}/{gen_root}/{stage}__{CKPT}"
    if not os.path.exists(f"{d}/completion.json"):
        raise qa_gen.QAError(f"completion.json missing in {d}")
    done, missing = qa_run.verify_job(d, rows, cfg, pdig, None)
    if missing:
        raise qa_gen.QAError(f"{len(missing)} requests missing in {d}")
    qa_run.verify_completion(d, rows, cfg, pdig, rp, len(done))
    by = {r["request_id"]: r for r in rows}
    return [(by[k], v) for k, v in done.items()]


def answer_table(pairs):
    """{(direction, cond, fmt, patient_id): {status, answer, ended_eos, n_out}}. 중복은 예외."""
    t = {}
    for row, rec in pairs:
        st, ans = CX.parse_answer(row["fmt"], rec["suffix_text_raw"], rec["ended_eos"])
        key = (row["target"], row["condition"], row["fmt"], row["id"])
        if key in t:
            raise AnalysisError(f"duplicate answer for {key}")
        t[key] = {"status": st, "answer": ans, "ended_eos": rec["ended_eos"], "n_out": rec["n_output_tokens"]}
    return t


def require_complete(tab, directions, conds, fmt, ids):
    want = {(d, c, fmt, i) for d in directions for c in conds for i in ids}
    have = {k for k in tab if k[0] in set(directions) and k[1] in set(conds) and k[2] == fmt}
    miss, extra = want - have, have - want
    if miss or extra:
        raise AnalysisError(f"answer table incomplete: missing {len(miss)} extra {len(extra)} e.g. {sorted(miss)[:3]}")
    return True


# ---------- 정답·flip ----------

def is_correct(tab, direction, cond, fmt, pid, cat):
    e = tab[(direction, cond, fmt, pid)]
    return e["status"] == "valid" and e["answer"] == CX.gt_answer(direction, cat)


def cat_ids(labels, ids):
    out = {c: [] for c in CX.CATEGORIES}
    for i in ids:
        out[labels[i]["category"]].append(i)
    return out


def correctness_vectors(tab, direction, cond, fmt, ids_by_cat, labels):
    return {c: np.array([float(is_correct(tab, direction, cond, fmt, i, labels[i]["category"])) for i in ids], dtype=float)
            for c, ids in ids_by_cat.items()}


def macro_accuracy(vec_by_cat):
    per = {c: float(v.mean()) for c, v in vec_by_cat.items()}
    return float(np.mean(list(per.values()))), per


def flips(tab, direction, cond_a, cond_b, fmt, ids, labels):
    """cond_a(예: D) -> cond_b(예: Tscope) 전이. negative: a 정답, b 오답(또는 invalid). positive: a 오답, b 정답."""
    neg, pos = [], []
    for i in ids:
        cat = labels[i]["category"]
        ca, cb = is_correct(tab, direction, cond_a, fmt, i, cat), is_correct(tab, direction, cond_b, fmt, i, cat)
        if ca and not cb:
            neg.append(i)
        elif not ca and cb:
            pos.append(i)
    return neg, pos


def valid_both(tab, direction, cond_a, cond_b, fmt, ids):
    return [i for i in ids if tab[(direction, cond_a, fmt, i)]["status"] == "valid"
            and tab[(direction, cond_b, fmt, i)]["status"] == "valid"]


# ---------- bootstrap ----------

def paired_diff_bootstrap(vec_a, vec_b, n=BOOT_N, seed=BOOT_SEED, ci=0.95):
    """category별 (a-b) paired 환자 bootstrap 후 4 category 동일 가중치 macro. returns dict(point, ci, per_category)."""
    rng = np.random.default_rng(seed)
    cats = list(vec_a)
    diffs = {}
    for c in cats:
        m = len(vec_a[c])
        idx = rng.integers(0, m, size=(n, m))
        diffs[c] = vec_a[c][idx].mean(1) - vec_b[c][idx].mean(1)
    tot = np.mean([diffs[c] for c in cats], axis=0)
    lo, hi = (1 - ci) / 2 * 100, (1 + ci) / 2 * 100
    point = float(np.mean([vec_a[c].mean() - vec_b[c].mean() for c in cats]))
    per_cat = {c: {"point": float(vec_a[c].mean() - vec_b[c].mean()),
                   "ci": [float(np.percentile(diffs[c], lo)), float(np.percentile(diffs[c], hi))]} for c in cats}
    return {"point": point, "ci": [float(np.percentile(tot, lo)), float(np.percentile(tot, hi))], "per_category": per_cat,
            "n_boot": n, "seed": seed}


# ---------- exact binomial (Clopper-Pearson) 보수적 구간: bootstrap 퇴화(discordant 0) 대비 ----------

def _binom_sf(k, n, p):
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    return float(sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1)))


def clopper_pearson(k, n, alpha=0.05, iters=100):
    """returns (lo, hi) exact binomial CI for a proportion k/n."""
    if n <= 0:
        raise AnalysisError("clopper_pearson needs n > 0")
    if k == 0:
        lo = 0.0
    else:
        a, b, target = 0.0, 1.0, alpha / 2
        for _ in range(iters):
            mid = (a + b) / 2
            if _binom_sf(k, n, mid) < target:
                a = mid
            else:
                b = mid
        lo = (a + b) / 2
    if k == n:
        hi = 1.0
    else:
        # P(X<=k|p_U) = alpha/2  <=>  P(X>=k+1|p_U) = 1-alpha/2 (survival function is increasing in p)
        a, b, target = 0.0, 1.0, 1 - alpha / 2
        for _ in range(iters):
            mid = (a + b) / 2
            if _binom_sf(k + 1, n, mid) < target:
                a = mid
            else:
                b = mid
        hi = (a + b) / 2
    return lo, hi


def conservative_macro_diff_bound(neg_by_cat, pos_by_cat, n_by_cat, alpha_total=0.05):
    """discordant(negative/positive flip) 빈도의 category별 exact binomial CI를 Bonferroni로 동시 보장하고,
    각 category의 최악/최선 (neg_hi - pos_lo, neg_lo - pos_hi)로 macro 차이의 보수적 [lo, hi]를 만든다.
    bootstrap이 퇴화(전부 0)일 때도 표본 크기에 근거한 비퇴화 구간을 제공하기 위한 것이다."""
    cats = list(n_by_cat)
    k = len(cats) * 2  # category마다 neg, pos 두 구간 -> Bonferroni로 alpha 분배
    per_alpha = alpha_total / k
    per_cat = {}
    los, his = [], []
    for c in cats:
        n = n_by_cat[c]
        neg_lo, neg_hi = clopper_pearson(neg_by_cat[c], n, per_alpha)
        pos_lo, pos_hi = clopper_pearson(pos_by_cat[c], n, per_alpha)
        d_lo, d_hi = neg_lo - pos_hi, neg_hi - pos_lo
        per_cat[c] = {"n": n, "neg": neg_by_cat[c], "pos": pos_by_cat[c], "neg_ci": [neg_lo, neg_hi], "pos_ci": [pos_lo, pos_hi],
                      "diff_bound": [d_lo, d_hi]}
        los.append(d_lo)
        his.append(d_hi)
    return {"macro_bound": [float(np.mean(los)), float(np.mean(his))], "per_category": per_cat,
            "note": "Bonferroni-adjusted Clopper-Pearson bound on macro(neg-pos) rate; conservative, not a bootstrap CI",
            "alpha_total": alpha_total, "per_interval_alpha": per_alpha}


# ---------- 확대 판단(E48 -> F) ----------

def expected_half_width(disc_by_cat, n_e_by_cat, n_f_by_cat, z=Z975):
    """category별 (discordant+1)/(n_e+2) smoothed rate로 Var(diff)~=p, macro(등가중 1/4)의 SE를 F 실제 표본 수로 계산."""
    var_terms = []
    per_cat = {}
    for c in disc_by_cat:
        p = (disc_by_cat[c] + 1) / (n_e_by_cat[c] + 2)
        nf = n_f_by_cat[c]
        v = p / nf if nf > 0 else float("inf")
        var_terms.append(v)
        per_cat[c] = {"smoothed_discordant_rate": p, "n_f": nf, "var_contribution": v}
    var_macro = sum(var_terms) / (len(var_terms) ** 2)
    hw = float(z * math.sqrt(var_macro))
    return hw, per_cat


def expand_decision(stage, protocol, out, f_counts_by_cat=None):
    from . import qa_gen
    labels = json.load(open(f"{OUT}/manifests/labels.json"))
    sets = json.load(open(f"{OUT}/manifests/sets.json"))
    fmt = "plain"
    pairs = load_stage(stage, protocol)
    tab = answer_table(pairs)
    ids = sorted({r["id"] for r, _ in pairs})
    require_complete(tab, list(CX.DIRECTIONS), list(CX.CONDITIONS), fmt, ids)
    ids_by_cat = cat_ids(labels, ids)
    vec_d = correctness_vectors(tab, "main", "D", fmt, ids_by_cat, labels)
    vec_ts = correctness_vectors(tab, "main", "Tscope", fmt, ids_by_cat, labels)
    h_boot = paired_diff_bootstrap(vec_d, vec_ts)
    h_point, h_per_cat = h_boot["point"], h_boot["per_category"]
    neg_ids, pos_ids = flips(tab, "main", "D", "Tscope", fmt, ids, labels)
    neg_by_cat, pos_by_cat, disc_by_cat, n_by_cat = {}, {}, {}, {}
    for c, cids in ids_by_cat.items():
        neg_by_cat[c] = sum(1 for i in cids if i in neg_ids)
        pos_by_cat[c] = sum(1 for i in cids if i in pos_ids)
        disc_by_cat[c] = neg_by_cat[c] + pos_by_cat[c]
        n_by_cat[c] = len(cids)
    if f_counts_by_cat is None:
        f_counts_by_cat = {c: len(sets["F"][c]) for c in CX.CATEGORIES}
    hw, hw_detail = expected_half_width(disc_by_cat, n_by_cat, f_counts_by_cat)
    rule_a = h_point >= 0.10 and len(neg_ids) >= 4
    rule_b = h_point >= 0.0 and h_boot["ci"][0] <= 0.10 <= h_boot["ci"][1] and len(neg_ids) >= 4 and hw <= 0.10
    expand = bool(rule_a or rule_b)
    d = {"stage": stage, "estimand": "H = macro_accuracy(D) - macro_accuracy(Tscope), direction=main", "H_point": h_point,
         "H_ci95": h_boot["ci"], "H_per_category": h_per_cat, "n_negative_flip": len(neg_ids), "n_positive_flip": len(pos_ids),
         "negative_flip_ids": neg_ids, "positive_flip_ids": pos_ids, "neg_by_category": neg_by_cat, "pos_by_category": pos_by_cat,
         "expected_F_half_width": hw, "expected_F_half_width_detail": hw_detail, "f_counts_by_category": f_counts_by_cat,
         "rule_a_pass": rule_a, "rule_b_pass": rule_b, "expand_to_F": expand}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(d, open(out, "w"), indent=1, sort_keys=True)
    return d


# ---------- 최종 보고 ----------

def full_report(stage, protocol, out):
    labels = json.load(open(f"{OUT}/manifests/labels.json"))
    fmt = "plain"
    pairs = load_stage(stage, protocol)
    tab = answer_table(pairs)
    ids = sorted({r["id"] for r, _ in pairs})
    require_complete(tab, list(CX.DIRECTIONS), list(CX.CONDITIONS), fmt, ids)
    ids_by_cat = cat_ids(labels, ids)
    n_by_cat = {c: len(v) for c, v in ids_by_cat.items()}

    per_condition = {}
    for direction in CX.DIRECTIONS:
        per_condition[direction] = {}
        for cond in CX.CONDITIONS:
            vec = correctness_vectors(tab, direction, cond, fmt, ids_by_cat, labels)
            acc, acc_per_cat = macro_accuracy(vec)
            valid = {c: float(np.mean([tab[(direction, cond, fmt, i)]["status"] == "valid" for i in ids_by_cat[c]])) for c in CX.CATEGORIES}
            trunc = {c: float(np.mean([tab[(direction, cond, fmt, i)]["status"] == "truncated" for i in ids_by_cat[c]])) for c in CX.CATEGORIES}
            per_condition[direction][cond] = {"macro_accuracy": acc, "per_category_accuracy": acc_per_cat,
                                              "valid_rate_per_category": valid, "truncated_rate_per_category": trunc}

    vec_d = correctness_vectors(tab, "main", "D", fmt, ids_by_cat, labels)
    vec_ts = correctness_vectors(tab, "main", "Tscope", fmt, ids_by_cat, labels)
    h_boot = paired_diff_bootstrap(vec_d, vec_ts)
    neg_ids, pos_ids = flips(tab, "main", "D", "Tscope", fmt, ids, labels)
    neg_by_cat = {c: sum(1 for i in cids if i in neg_ids) for c, cids in ids_by_cat.items()}
    pos_by_cat = {c: sum(1 for i in cids if i in pos_ids) for c, cids in ids_by_cat.items()}
    degenerate = all(v == 0 for v in h_boot["ci"]) and h_boot["point"] == 0.0
    conservative = conservative_macro_diff_bound(neg_by_cat, pos_by_cat, n_by_cat) if degenerate else None

    both_valid = valid_both(tab, "main", "D", "Tscope", fmt, ids)
    valid_neg = [i for i in neg_ids if i in both_valid]
    valid_pos = [i for i in pos_ids if i in both_valid]
    content_only_diff = (len(valid_neg) - len(valid_pos)) / len(both_valid) if both_valid else None

    secondary = {}
    for direction in CX.DIRECTIONS:
        for a, b in (("U", "D"), ("T", "D"), ("Tscope", "T")):
            va = correctness_vectors(tab, direction, a, fmt, ids_by_cat, labels)
            vb = correctness_vectors(tab, direction, b, fmt, ids_by_cat, labels)
            secondary[f"{direction}:{a}-{b}"] = paired_diff_bootstrap(va, vb)
    va = correctness_vectors(tab, "aux", "D", fmt, ids_by_cat, labels)
    vb = correctness_vectors(tab, "aux", "Tscope", fmt, ids_by_cat, labels)
    secondary["aux:D-Tscope"] = paired_diff_bootstrap(va, vb)

    d = {"stage": stage, "n_patients": len(ids), "n_by_category": n_by_cat, "per_condition": per_condition,
         "primary": {"estimand": "H = macro_accuracy(D) - macro_accuracy(Tscope), direction=main", "bootstrap": h_boot,
                     "n_negative_flip": len(neg_ids), "n_positive_flip": len(pos_ids), "negative_flip_ids": neg_ids,
                     "positive_flip_ids": pos_ids, "neg_by_category": neg_by_cat, "pos_by_category": pos_by_cat,
                     "n_both_valid": len(both_valid), "content_only_net_harm_rate": content_only_diff,
                     "bootstrap_degenerate": degenerate, "conservative_bound": conservative},
         "secondary": secondary}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(d, open(out, "w"), indent=1, sort_keys=True, default=str)
    return d


# ---------- D16 형식 gate ----------

def format_gate(stage, protocol, out):
    labels = json.load(open(f"{OUT}/manifests/labels.json"))
    fmt = "plain" if "plain" in stage else "json"
    pairs = load_stage(stage, protocol)
    tab = answer_table(pairs)
    ids = sorted({r["id"] for r, _ in pairs})
    require_complete(tab, list(CX.DIRECTIONS), list(CX.CONDITIONS), fmt, ids)
    per = {}
    cond_totals = {}
    for cond in CX.CONDITIONS:
        cond_valid, cond_n = 0, 0
        for direction in CX.DIRECTIONS:
            st = [tab[(direction, cond, fmt, i)]["status"] for i in ids]
            v = sum(s == "valid" for s in st)
            per[f"{direction}:{cond}"] = {"n": len(st), "valid": v, "valid_rate": v / len(st), "status": {s: st.count(s) for s in sorted(set(st))}}
            cond_valid += v
            cond_n += len(st)
        cond_totals[cond] = {"n": cond_n, "valid": cond_valid, "valid_rate": cond_valid / cond_n}
    gate_direction = all(v["valid"] >= 15 for v in per.values())
    gate_condition = all(v["valid"] >= 31 for v in cond_totals.values())
    d = {"stage": stage, "fmt": fmt, "per_direction_condition": per, "per_condition_total": cond_totals,
         "gate_direction_pass_15_of_16": gate_direction, "gate_condition_pass_31_of_32": gate_condition,
         "gate_pass": bool(gate_direction and gate_condition), "n_patients": len(ids)}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(d, open(out, "w"), indent=1, sort_keys=True)
    return d


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    g = sp.add_parser("gate")
    g.add_argument("--stage", required=True)
    g.add_argument("--protocol", required=True)
    g.add_argument("--out", required=True)
    e = sp.add_parser("expand-decision")
    e.add_argument("--stage", required=True)
    e.add_argument("--protocol", required=True)
    e.add_argument("--out", required=True)
    r = sp.add_parser("report")
    r.add_argument("--stage", required=True)
    r.add_argument("--protocol", required=True)
    r.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "gate":
        d = format_gate(a.stage, a.protocol, a.out)
        print(json.dumps({"gate_pass": d["gate_pass"]}))
    elif a.cmd == "expand-decision":
        d = expand_decision(a.stage, a.protocol, a.out)
        print(json.dumps({"expand_to_F": d["expand_to_F"], "H_point": d["H_point"], "H_ci95": d["H_ci95"]}))
    elif a.cmd == "report":
        d = full_report(a.stage, a.protocol, a.out)
        print(json.dumps({"primary_bootstrap": d["primary"]["bootstrap"], "n_negative_flip": d["primary"]["n_negative_flip"]}))


if __name__ == "__main__":
    main()
