"""iter_108 평가·분기 (결과를 보기 전에 잠금). 순수 함수 + 검증된 record 입력 CLI.

입력 단위: answers[(patient, cond, target)] = record dict(suffix_text_raw, ended_eos). cond ∈ F,D,T,C,L. 정답은 labels에서만 읽는다.
- 주평가 parser: semantic_v1 (strict 병기). invalid(truncated 포함)는 전체 분모에서 오답으로 계산한다.
- 비교: nonempty 환자(저장 B0 bbox ok). 주 endpoint: T−D O 정확도(pooled), T−D A 정확도(not_normal_no_opacity nonempty).
- 환자 단위 category-층화 bootstrap 10,000회, seed 10817, 모든 조건·질문을 같은 환자 재표집으로 함께 계산한다.
- P180→E600 확대 분기는 plan.md §4 문구 그대로이며 추가 문턱은 없다.
"""
import json
import math
import sys

import numpy as np

import ev108_spec as S

COND_NEW = ("D", "T", "C")
Z = 1.0


# ---------------- answers ----------------
def score(cat, target, rec, parser="sem"):
    """returns (status, answer|None, correct(0/1), valid(bool)). invalid는 correct=0."""
    fn = S.sem if parser == "sem" else S.strict
    st, ans = fn(target, rec["suffix_text_raw"], rec["ended_eos"])
    ok = int(st == "valid" and ans == S.correct_answer(cat, target))
    return st, ans, ok, st == "valid"


class Resampler:
    """category 층화 환자 bootstrap의 재표집 횟수 행렬 (B x n). 모든 비교가 같은 행렬을 쓴다."""

    def __init__(self, strata, seed=S.SEED, B=S.N_BOOT):
        self.n = len(strata)
        rng = np.random.default_rng(seed)
        counts = np.zeros((B, self.n), dtype=np.int32)
        for s in sorted(set(strata)):
            idx = np.array([i for i, x in enumerate(strata) if x == s])
            draws = idx[rng.integers(0, len(idx), size=(B, len(idx)))]
            rows = np.repeat(np.arange(B), len(idx))
            np.add.at(counts, (rows, draws.ravel()), 1)
        self.counts = counts

    def mean_ci(self, d, mask=None):
        """d: 환자별 값 벡터. mask: 부분집합. returns (point, lo, hi, degenerate)."""
        d = np.asarray(d, float)
        m = np.ones(self.n, bool) if mask is None else np.asarray(mask, bool)
        c = self.counts[:, m].astype(float)
        num = c @ d[m]
        den = c.sum(axis=1)
        ok = den > 0
        means = num[ok] / den[ok]
        lo, hi = np.percentile(means, [2.5, 97.5])
        return float(d[m].mean()), float(lo), float(hi), bool(np.all(d[m] == d[m][0]))


# ---------------- paired comparisons ----------------
def paired(vals_a, vals_b):
    """vals: list of (valid, correct) per patient. returns dict of vectors and counts."""
    n = len(vals_a)
    ca = np.array([v[1] for v in vals_a], float)
    cb = np.array([v[1] for v in vals_b], float)
    va = np.array([v[0] for v in vals_a], bool)
    vb = np.array([v[0] for v in vals_b], bool)
    both = va & vb
    c2w = int(((ca == 0) & (cb == 1) & both).sum())  # a가 b보다 나쁨: b는 맞고 a는 틀림 (a: 대상 조건)
    w2c = int(((ca == 1) & (cb == 0) & both).sum())
    changed_valid = int((both & (ca != cb)).sum())
    inv_driven = int(((~both) & (ca != cb)).sum())
    # invalid를 a에 유리/불리하게 배정한 정확도 차이 범위
    a_lo = np.where(va, ca, 0.0)
    a_hi = np.where(va, ca, 1.0)
    b_lo = np.where(vb, cb, 0.0)
    b_hi = np.where(vb, cb, 1.0)
    return dict(n=n, d=ca - cb, ca=ca, cb=cb, changed_valid=changed_valid, b_right_a_wrong=c2w, a_right_b_wrong=w2c,
                invalid_driven=inv_driven, bound_lo=a_lo - b_hi, bound_hi=a_hi - b_lo, n_invalid_a=int((~va).sum()), n_invalid_b=int((~vb).sum()))


def compare(R, vals_a, vals_b, mask=None):
    """대상 조건 a와 기준 b의 환자별 (valid,correct) 목록에서 정확도 차이 a-b와 전이·형식 범위를 계산한다."""
    p = paired(vals_a, vals_b)
    m = np.ones(p["n"], bool) if mask is None else np.asarray(mask, bool)
    va = np.array([v[0] for v in vals_a], bool)
    vb = np.array([v[0] for v in vals_b], bool)
    ca, cb = p["ca"], p["cb"]
    both = va & vb
    pt, lo, hi, deg = R.mean_ci(p["d"], m)
    n = int(m.sum())
    out = {"n": n, "acc_a": float(ca[m].mean()) if n else None, "acc_b": float(cb[m].mean()) if n else None,
           "diff": pt, "ci95": [lo, hi], "degenerate_bootstrap": deg,
           "changed_valid": int(((ca != cb) & both & m).sum()),
           "a_right_b_wrong_valid": int(((ca == 1) & (cb == 0) & both & m).sum()),
           "a_wrong_b_right_valid": int(((ca == 0) & (cb == 1) & both & m).sum()),
           "invalid_driven_changes": int(((ca != cb) & ~both & m).sum()),
           "n_invalid_a": int((~va)[m].sum()), "n_invalid_b": int((~vb)[m].sum()),
           "format_bound": [float(p["bound_lo"][m].mean()), float(p["bound_hi"][m].mean())] if n else None}
    b = out["format_bound"]
    out["format_direction_stable"] = bool((pt > 0 and b[0] > 0) or (pt < 0 and b[1] < 0)) if n and pt != 0 else None
    out["changed_valid_rate_exact95"] = list(S.exact_binom_ci(out["changed_valid"], n)) if n else None
    return out


def comparisons(patients, cats, ans, parser):
    """patients: nonempty id list (고정 순서). ans[(pid,cond,target)] -> rec. returns dict of comparison results."""
    strata = [cats[p] for p in patients]
    R = Resampler(strata)
    vals = {}
    for cond in ("F", "D", "T", "C"):
        for tg in S.TARGETS:
            vals[(cond, tg)] = [(lambda s: (s[3], s[2]))(score(cats[p], tg, ans[(p, cond, tg)], parser)) for p in patients]
    vals[("L", "O")] = [(lambda s: (s[3], s[2]))(score(cats[p], "O", ans[(p, "L", "O")], parser)) for p in patients]
    nno = np.array([cats[p] == "not_normal_no_opacity" for p in patients])
    allm = np.ones(len(patients), bool)
    out = {"n_nonempty": len(patients), "n_by_category": {c: int(sum(x == c for x in strata)) for c in S.CATS}}
    spec = [("T_minus_D_O", ("T", "O"), ("D", "O"), allm), ("T_minus_D_A_nno", ("T", "A"), ("D", "A"), nno),
            ("T_minus_C_O", ("T", "O"), ("C", "O"), allm), ("T_minus_C_A_nno", ("T", "A"), ("C", "A"), nno),
            ("D_minus_F_O", ("D", "O"), ("F", "O"), allm), ("D_minus_F_A_nno", ("D", "A"), ("F", "A"), nno),
            ("T_minus_F_O", ("T", "O"), ("F", "O"), allm), ("T_minus_F_A_nno", ("T", "A"), ("F", "A"), nno),
            ("T_minus_D_A_pooled", ("T", "A"), ("D", "A"), allm), ("T_minus_C_A_pooled", ("T", "A"), ("C", "A"), allm),
            ("L_minus_F_O", ("L", "O"), ("F", "O"), allm), ("T_minus_L_O", ("T", "O"), ("L", "O"), allm)]
    out["comparisons"] = {name: compare(R, vals[a], vals[b], mask) for name, a, b, mask in spec}
    out["accuracy"] = {f"{cond}_{tg}": {"pooled": float(np.mean([v[1] for v in vals[(cond, tg)]])),
                                         **{c: float(np.mean([v[1] for v, s in zip(vals[(cond, tg)], strata) if s == c])) if c in set(strata) else None
                                            for c in S.CATS},
                                         "n_invalid": int(sum(not v[0] for v in vals[(cond, tg)]))} for (cond, tg) in vals}
    return out


# ---------------- policies on full sets ----------------
def bbox_rule_answer(status):
    return "yes" if status == "ok" else "no"


def policy_answers(pid, status, ans):
    """R/R_L/R_B 정책별 (O답 record-like, A답 record-like). 빈 예측이면 O도 F. invalid/truncated bbox도 F (실제 데이터에는 0건)."""
    f_o, f_a = ans[(pid, "F", "O")], ans[(pid, "F", "A")]
    ne = status == "ok"
    pol = {"F": (f_o, f_a)}
    pol["R"] = (ans[(pid, "T", "O")] if ne else f_o, f_a)
    pol["R_L"] = (ans[(pid, "L", "O")] if ne else f_o, f_a)
    pol["R_B"] = ({"suffix_text_raw": bbox_rule_answer(status), "ended_eos": True} if status in ("ok", "empty") else f_o, f_a)
    return pol


def policy_report(ids_by_cat, cats, bstatus, ans, parser):
    """ids_by_cat: 전체 집합(180 또는 600). nonempty의 D/T/L/C 답은 ans에 있어야 한다. returns policy 요약 + S_scope 차이."""
    ids = [i for c in S.CATS for i in ids_by_cat[c]]
    strata = [cats[i] for i in ids]
    R = Resampler(strata)
    names = ["F", "R", "R_L", "R_B"]
    per = {n: {"pair": [], "O": [], "A": [], "valid_pair": []} for n in names}
    for i in ids:
        pol = policy_answers(i, bstatus[i], ans)
        for n in names:
            so = score(cats[i], "O", pol[n][0], parser)
            sa = score(cats[i], "A", pol[n][1], parser)
            per[n]["O"].append(so[2])
            per[n]["A"].append(sa[2])
            per[n]["pair"].append(so[2] * sa[2])
            per[n]["valid_pair"].append(int(so[3] and sa[3]))
    out = {"n": len(ids), "policies": {}, "diffs": {}}
    for n in names:
        sc = {c: float(np.mean([v for v, s in zip(per[n]["pair"], strata) if s == c])) for c in S.CATS}
        out["policies"][n] = {"S_scope": float(np.mean(list(sc.values()))), "pair_acc_by_category": sc,
                              "O_sensitivity_opacity": float(np.mean([v for v, s in zip(per[n]["O"], strata) if s == "opacity"])),
                              "O_specificity_nonopacity": float(np.mean([v for v, s in zip(per[n]["O"], strata) if s != "opacity"])),
                              "A_acc_by_category": {c: float(np.mean([v for v, s in zip(per[n]["A"], strata) if s == c])) for c in S.CATS},
                              "n_pair_invalid_component": int(len(ids) - sum(per[n]["valid_pair"]))}
    for a, b in (("R", "F"), ("R_L", "F"), ("R_B", "F"), ("R_L", "R"), ("R_B", "R"), ("R_B", "R_L")):
        d = np.array(per[a]["pair"], float) - np.array(per[b]["pair"], float)
        # category 균등 평균: 각 category 평균의 단순 평균. bootstrap 복원 행렬로 계산.
        pt = float(np.mean([d[[i for i, s in enumerate(strata) if s == c]].mean() for c in S.CATS]))
        reps = []
        for c in S.CATS:
            m = np.array([s == c for s in strata])
            cm = R.counts[:, m].astype(float)
            reps.append((cm @ d[m]) / cm.sum(axis=1))
        reps = np.mean(reps, axis=0)
        lo, hi = np.percentile(reps, [2.5, 97.5])
        out["diffs"][f"{a}_minus_{b}_S_scope"] = {"diff": pt, "ci95": [float(lo), float(hi)]}
    return out


# ---------------- crop 특성 ----------------
def crop_stats(geo, labels, patients):
    """사전 정의 기술통계. GT는 opacity category 환자의 coverage/IoU 기술통계에만 쓰고 후속 선택에는 쓰지 않는다."""
    ar = [geo[p]["area_ratio"] for p in patients]
    out = {"n": len(patients), "area_ratio_mean": float(np.mean(ar)), "area_ratio_median": float(np.median(ar)),
           "area_ratio_min": float(np.min(ar)), "area_ratio_max": float(np.max(ar)),
           "T_equals_C": int(sum(geo[p]["T_equals_C"] for p in patients)),
           "n_boxes_hist": {str(k): int(sum(geo[p]["n_boxes"] == k for p in patients)) for k in sorted({geo[p]["n_boxes"] for p in patients})}}
    cov, hit, cover_all = [], 0, 0
    pos = [p for p in patients if labels[p]["category"] == "opacity"]
    for p in pos:
        side = geo[p]["side"]
        x0, y0, x1, y1 = geo[p]["rect_T"]
        rect = (y0 * 1000.0 / side, x0 * 1000.0 / side, y1 * 1000.0 / side, x1 * 1000.0 / side)
        gcov = []
        any_hit = False
        for g in labels[p]["boxes"]:
            gb = g["yxyx_norm"]
            gcov.append(inter(gb, rect) / max(1e-9, area(gb)))
            for pb in geo[p]["boxes_yxyx"]:
                u = area(gb) + area(pb) - inter(gb, pb)
                if inter(gb, pb) / u >= 0.3:
                    any_hit = True
        cov.append(float(np.mean(gcov)) if gcov else float("nan"))
        hit += any_hit
        cover_all += bool(gcov) and all(c >= 0.999 for c in gcov)
    out["opacity_positives"] = {"n": len(pos), "mean_gt_coverage_by_T_crop": float(np.nanmean(cov)) if cov else None,
                                "n_with_pred_box_iou_ge_0.3_to_any_gt": int(hit), "n_all_gt_boxes_inside_T_crop": int(cover_all)}
    return out


def area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def inter(a, b):
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


# ---------------- 분기 ----------------
EXPAND_ENDPOINTS = ("T_minus_D_O", "T_minus_D_A_nno", "T_minus_C_O")


def expansion_decision(cmp_p180, n_e600_by_endpoint):
    """P180 -> E600 나머지 nonempty 확대 여부 (plan §4 그대로).
    A: |diff|>=0.10 이고 양쪽 semantic-valid인 변화 환자>=3.
    B: 변화(semantic-valid) 환자>=4, 95% CI가 0과 (+0.10 또는 -0.10)을 함께 포함, 예상 반폭 = 현재 반폭*sqrt(n_P/n_E) <= 0.15.
    endpoint: T-D O, T-D A(nno), T-C O. n_e600_by_endpoint: {endpoint: E600 실제 분모}."""
    res = {}
    for name in EXPAND_ENDPOINTS:
        c = cmp_p180["comparisons"][name]
        lo, hi = c["ci95"]
        cond_a = abs(c["diff"]) >= 0.10 - 1e-12 and c["changed_valid"] >= 3
        half = (hi - lo) / 2
        proj = half * math.sqrt(c["n"] / n_e600_by_endpoint[name]) if n_e600_by_endpoint[name] else None
        cond_b = (c["changed_valid"] >= 4 and lo <= 0 <= hi and ((lo <= 0.10 <= hi) or (lo <= -0.10 <= hi)) and proj is not None and proj <= 0.15)
        res[name] = {"A": bool(cond_a), "B": bool(cond_b), "diff": c["diff"], "ci95": c["ci95"], "changed_valid": c["changed_valid"],
                     "n_P": c["n"], "n_E": n_e600_by_endpoint[name], "projected_halfwidth": proj}
    expand = any(v["A"] or v["B"] for v in res.values())
    return {"expand": bool(expand), "endpoints": res}


def limited_positive(c):
    """최종 단계 제한된 양성 관찰 (plan Evaluation '양성 관찰')."""
    return bool(abs(c["diff"]) >= 0.10 - 1e-12 and not (c["ci95"][0] <= 0 <= c["ci95"][1]) and c["changed_valid"] >= 3
                and c["format_direction_stable"] is True)


if __name__ == "__main__":
    sys.exit("library module; use ev108_report.py")
