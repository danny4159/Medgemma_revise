"""iter_116 평가 (생성 결과를 보기 전에 잠근다). 입력은 검증된 record와 ledger/gt.

정의 (모두 계획에 명시된 것만 구현; 계획에 없는 사건 수 문턱은 추가하지 않는다):
 - 정답: category=='opacity' → yes, 그 외 → no (표적 Q_O).
 - 정책 정답 수는 unresolved(None)를 정답으로 세지 않는다 (주 보수적 점수).
 - correction: K 오답 환자 중 정책이 정답인 수. harm: K 정답 환자 중 정책이 정답이 아닌 수(unresolved 포함, harm_wrong은 resolved 반대 답만).
 - 공동 지표: 최종 답이 yes면 고정 detector 후보(score>=0.70)를 유지, no/unresolved면 제거(빈 집합). 양성은 yes이고 IoU0.3 최대 일대일 matching에서
   TP==n_GT==n_pred, 음성은 no이고 box 없음일 때 공동 성공. unresolved는 공동 성공이 아니다. IoU0.5·양성 F1·FP/FN은 보조.
 - unresolved 범위: 환자별로 미해결 변수(G,N,E,R,T)의 모든 yes/no 배정을 열거해 각 지표의 환자별 최소/최대를 합산한다.
   같은 출력이 여러 정책(E→S, G→M)에 쓰이므로 환자 내에서는 공유 변수로 함께 배정한다 (환자 간은 독립이므로 합산이 정확).
 - bootstrap: 환자 단위 10,000회, seed 11617, 그룹(불일치/일치 대조)별 분리, percentile 95%.
"""
import itertools
import json
import os

import numpy as np

import ed116_spec as ES
import ev109_extract as X
from rsna_diag import geometry as GEO
from rsna_diag import metrics as MET

POL = ("K", "B", "G", "M", "N", "E", "R", "T", "S")
COMP = ("K", "B", "G", "M", "N", "E", "S")  # 성공 기준의 필수 단순/기존 대조 (T는 보고만)
JOINT_POL = ("K", "B", "N", "E", "R", "T", "S")
FREE = ("G", "N", "E", "R", "T")
# 사전 투자 분기 상수 (계획 Evaluation '양성 탐색')
MIN_CORRECTION = 10
MAX_HARM = 5
MIN_ADV = 5
MAX_AGREE_HARM_RATE = 0.05
TECH_MIN_RESOLVED = 6  # 12명 중 절반 미만(<6)이면 본생성 보류


def gt_answer(cat):
    return "yes" if cat == "opacity" else "no"


def derive(k, b, g, n, e, r, t):
    s = e if (e is not None and e == b) else k
    return dict(K=k, B=b, G=g, M=ES.majority(k, b, g), N=n, E=e, R=r, T=t, S=s)


def det_norm_boxes(row):
    top, left, side = row["pad"]
    return [GEO.canvas_to_norm(b, top, left, side) for _, b in ES.det_boxes(row)]


def make_patient(row, gt, model_ans):
    """row: ledger_nogt 행, gt: gt.json 항목, model_ans: cond→raw answer|None (N/E/R/T)."""
    base = derive(ES.answer_K(row), ES.answer_B(row), ES.answer_G(row), model_ans.get("N"), model_ans.get("E"),
                  model_ans.get("R"), model_ans.get("T"))
    pred = det_norm_boxes(row)
    g = gt["gt_yxyx_norm"]
    m03, m05 = MET.match(pred, g, 0.3), MET.match(pred, g, 0.5)
    return dict(id=row["id"], cat=gt["category"], y=gt_answer(gt["category"]), base=base, n_det=len(pred), n_gt=len(g),
                tp03=len(m03), tp05=len(m05))


def scalars(p, ans):
    """한 환자·한 배정(ans: 정책→답 또는 None)의 지표. None은 보수적으로 처리한다."""
    y, kc = p["y"], p["base"]["K"] == p["y"]
    out = {}
    cor = {q: int(ans[q] == y) for q in POL}
    for q in POL:
        out[f"correct_{q}"] = cor[q]
        out[f"correction_{q}"] = cor[q] if not kc else 0
        out[f"harm_{q}"] = (1 - cor[q]) if kc else 0
        out[f"harmwrong_{q}"] = int(kc and ans[q] is not None and ans[q] != y)
        out[f"flip_to_yes_{q}"] = int(ans[q] == "yes" and p["base"]["K"] == "no")
        out[f"flip_to_no_{q}"] = int(ans[q] == "no" and p["base"]["K"] == "yes")
    for q in POL:
        if q != "R":
            out[f"diff_R_{q}"] = cor["R"] - cor[q]
    pos = p["y"] == "yes"
    for q in JOINT_POL:
        a = ans[q]
        npred = p["n_det"] if a == "yes" else 0
        for thr, tp_all in (("03", p["tp03"]), ("05", p["tp05"])):
            tp = tp_all if a == "yes" else 0
            if pos:
                ok = int(a == "yes" and tp == p["n_gt"] == npred)
            else:
                ok = int(a == "no" and npred == 0)
            out[f"joint{thr}_{q}"] = ok
            out[f"fp{thr}_{q}"] = npred - tp
            out[f"fn{thr}_{q}"] = (p["n_gt"] - tp) if pos else 0
        if pos:
            tp = p["tp03"] if a == "yes" else 0
            prec = tp / npred if npred else 0.0
            rec = tp / p["n_gt"]
            out[f"posf1_03_{q}"] = 2 * prec * rec / (prec + rec) if prec + rec > 0 else 0.0
        else:
            out[f"posf1_03_{q}"] = 0.0
    for q in JOINT_POL:
        if q != "R":
            out[f"jdiff03_R_{q}"] = out["joint03_R"] - out[f"joint03_{q}"]
    return out


def point_scalars(p):
    return scalars(p, p["base"])


def range_scalars(p):
    """미해결 변수 모든 yes/no 배정에서 지표별 (min, max). 해결된 환자는 점추정과 같다."""
    free = [v for v in FREE if p["base"][v] is None]
    lo = hi = None
    for combo in itertools.product(("yes", "no"), repeat=len(free)):
        b = dict(p["base"])
        for v, a in zip(free, combo):
            b[v] = a
        d = derive(b["K"], b["B"], b["G"], b["N"], b["E"], b["R"], b["T"])
        sc = scalars(p, d)
        if lo is None:
            lo, hi = dict(sc), dict(sc)
        else:
            for k, v in sc.items():
                lo[k] = min(lo[k], v)
                hi[k] = max(hi[k], v)
    return lo, hi


def boot_idx(n):
    return np.random.default_rng(ES.SEED_BOOT).integers(0, n, size=(ES.N_BOOT, n), dtype=np.int32)


def ci_mean(v, idx):
    v = np.asarray(v, float)
    m = v[idx].mean(axis=1)
    return [float(v.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]


def ci_ratio(num, den, idx):
    num, den = np.asarray(num, float), np.asarray(den, float)
    if den.sum() == 0:
        return [None, None, None]
    n_, d_ = num[idx].sum(axis=1), den[idx].sum(axis=1)
    ok = d_ > 0
    r = n_[ok] / d_[ok]
    return [float(num.sum() / den.sum()), float(np.percentile(r, 2.5)), float(np.percentile(r, 97.5))]


def group_report(patients):
    n = len(patients)
    pts = [point_scalars(p) for p in patients]
    rng = [range_scalars(p) for p in patients]
    keys = list(pts[0])
    point = {k: int(sum(d[k] for d in pts)) if all(isinstance(d[k], int) for d in pts) else float(sum(d[k] for d in pts)) for k in keys}
    rmin = {k: float(sum(lo[k] for lo, _ in rng)) for k in keys}
    rmax = {k: float(sum(hi[k] for _, hi in rng)) for k in keys}
    kc = np.array([int(p["base"]["K"] == p["y"]) for p in patients])
    n_kc, n_kw = int(kc.sum()), int(n - kc.sum())
    idx = boot_idx(n)
    vec = lambda k: np.array([d[k] for d in pts], float)
    ci = {}
    for q in POL:
        if q != "R":
            ci[f"diff_R_{q}"] = ci_mean(vec(f"diff_R_{q}"), idx)
    for q in JOINT_POL:
        if q != "R":
            ci[f"jdiff03_R_{q}"] = ci_mean(vec(f"jdiff03_R_{q}"), idx)
    for q in POL:
        ci[f"correction_rate_{q}"] = ci_ratio(vec(f"correction_{q}"), 1 - kc, idx)
        ci[f"harm_rate_{q}"] = ci_ratio(vec(f"harm_{q}"), kc, idx)
        ci[f"accuracy_{q}"] = ci_mean(vec(f"correct_{q}"), idx)
    cats = {}
    for c in ("opacity", "normal", "not_normal_no_opacity"):
        sub = [i for i, p in enumerate(patients) if p["cat"] == c]
        cats[c] = dict(n=len(sub), K_correct=int(sum(pts[i]["correct_K"] for i in sub)),
                       correct={q: int(sum(pts[i][f"correct_{q}"] for i in sub)) for q in POL},
                       to_yes_R=int(sum(pts[i]["flip_to_yes_R"] for i in sub)), to_no_R=int(sum(pts[i]["flip_to_no_R"] for i in sub)))
    follow = {}
    for q in ("N", "E", "R", "T"):
        res = [p for p in patients if p["base"][q] is not None]
        follow[q] = dict(n_resolved=len(res), n_unresolved=n - len(res),
                         equals_K=int(sum(p["base"][q] == p["base"]["K"] for p in res)),
                         equals_B=int(sum(p["base"][q] == p["base"]["B"] for p in res)))
    return dict(n=n, n_K_correct=n_kc, n_K_wrong=n_kw, point=point, range_min=rmin, range_max=rmax, ci95=ci, by_category=cats, follow=follow,
                n_unresolved_cells={q: int(sum(p["base"][q] is None for p in patients)) for q in FREE})


def decide(mm, ag):
    """사전 투자 분기. mm: 불일치 그룹 report, ag: 일치 대조 report. 계획에 없는 문턱은 쓰지 않는다.
    각 기준은 지표 하나에 대한 부등식이므로 '모든 미해결 배정에서 기준 충족'은 지표별 최악값에서의 충족과 같다."""

    def get(mode, rep, k):
        if mode == "point":
            return rep["point"][k]
        good_high = k.startswith("correction_") or k.startswith("diff_")  # 클수록 R에 유리한 지표
        lo, hi = rep["range_min"][k], rep["range_max"][k]
        if mode == "worst":
            return lo if good_high else hi
        return hi if good_high else lo

    def crit(mode):
        c = {"R_correction>=10": get(mode, mm, "correction_R") >= MIN_CORRECTION,
             "R_harm<=5": get(mode, mm, "harm_R") <= MAX_HARM}
        for x in COMP:
            c[f"R_minus_{x}>=5"] = get(mode, mm, f"diff_R_{x}") >= MIN_ADV
        c["agree_harm_rate<=0.05"] = get(mode, ag, "harm_R") <= MAX_AGREE_HARM_RATE * ag["n_K_correct"]
        return c

    res = {m: crit(m) for m in ("point", "worst", "best")}
    point_ok, worst_ok, best_ok = (all(res[m].values()) for m in ("point", "worst", "best"))
    if point_ok and worst_ok:
        label = "positive_exploratory"
    elif point_ok:
        label = "inconclusive_unresolved_flips_criteria"
    elif best_ok:
        label = "inconclusive_unresolved_could_satisfy"
    else:
        label = "hold_current_frozen_setting"
    return dict(label=label, point=res["point"], worst=res["worst"], best=res["best"],
                note="CI·표본 변동에 따른 불확정은 계획에 수치 기준이 없어 자동 분기에서 사용하지 않고 보고서에 서술한다.")


def format_report(recs_by_cond):
    """cond→records(list). 응답 형식 준수와 내용 정확도를 분리하기 위한 형식 통계."""
    out = {}
    for c, recs in recs_by_cond.items():
        srcs, reasons, strict = {}, {}, 0
        for r in recs:
            res = X.resolve("O", r["suffix_text_raw"], r["ended_eos"])
            srcs[res["source"]] = srcs.get(res["source"], 0) + 1
            if res["source"] == "unresolved":
                reasons[res["reason"]] = reasons.get(res["reason"], 0) + 1
            strict += int(ES.S.strict("O", r["suffix_text_raw"], r["ended_eos"])[0] == "valid")
        out[c] = dict(n=len(recs), source=srcs, unresolved_reasons=reasons, strict_valid=strict,
                      eos=sum(bool(r["ended_eos"]) for r in recs), retry=sum(len(r["attempts"]) > 1 for r in recs),
                      mean_output_tokens=float(np.mean([r["n_output_tokens"] for r in recs])) if recs else None)
    return out


def tech_gate(recs, tech_ids):
    """기술 12명 × 4조건. 한 조건이라도 resolved가 12명 중 6 미만이면 본생성 보류 (사전 형식 분기)."""
    by = {c: {} for c in ES.COND_ORDER}
    for r in recs:
        by[r["cond"]][r["patient"]] = r
    det = {}
    ok = True
    for c in ES.COND_ORDER:
        miss = [i for i in tech_ids if i not in by[c]]
        n_res = sum(X.resolve("O", by[c][i]["suffix_text_raw"], by[c][i]["ended_eos"])["answer"] is not None for i in tech_ids if i in by[c])
        det[c] = dict(n_records=len(by[c]), n_missing=len(miss), n_resolved=n_res, passes=(not miss) and n_res >= TECH_MIN_RESOLVED)
        ok &= det[c]["passes"]
    return dict(run=bool(ok), per_condition=det, min_resolved_required=TECH_MIN_RESOLVED, n_tech=len(tech_ids),
                note="기술 검사 통과는 정확도 문턱이 아니다. 형식(resolved) 분기만 판정한다.")
