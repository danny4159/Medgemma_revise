"""iter_114: CURE–MG 위치 불일치(D_cure), 의료 적응 MedGrounder MSPC–MG 불일치(D_mspc), MG confidence(B)의 오류 검토 포착 비교 (CPU 분석).

고정 규칙(iter_113 에서 이어받음, 새 결과 전에 protocol.json 에 코드·입력 hash 와 함께 잠근다):
- 대상 M = MedGrounder A_U_e5 의 선택 운영점 0.8 출력. 오류 E_G=1[union IoU(M, 공식 GT)<0.3], 빈 M 은 오류.
- 위험 B=1-min(M scores)(M 비면 1). D_cure=1-unionIoU(M,CURE), D_mspc=1-unionIoU(M,MSPC) (둘 다 빈 출력이면 0, 한쪽만 비면 1).
- CURE truncated/malformed/coord_invalid, MSPC 비유한/범위 밖 box, MG 기술 결함은 세 순위에서 공통 제외(원 분모·이유 보존). CURE no_box 는 빈 집합.
- 순위: 위험 내림차순, 동률은 (sha256("iter113|item_key"), 복제 순번) 오름차순. K=ceil(N/4).
- ΔA=(cap_D_cure-cap_B)/N, ΔB=(cap_D_cure-cap_D_mspc)/N. 환자 bootstrap 20000회 seed 113, 매 복제마다 N/K/세 순위 재계산,
  양측 98.75% percentile(= 0.625, 99.375). 확대: 초기에서 A 또는 B 가 (상한>=0.05 and 반폭>0.05) 이면 최대 집단까지 한 번.
- 두 순위의 합집합 포착은 같은 K 의 성능으로 제시하지 않는다.
"""
import json
import random

import numpy as np

import nr113_core as B
import nr107_geom as G

TAG = "iter114"
SEED = 113
BOOT_N = 20000
CI_Q = (0.625, 99.375)
MIN_EFFECT = 0.05
FIELDS = ("B", "D", "P")  # confidence / cure / mspc


class LinkError(B.LinkError):
    pass


def mspc_defects(det):
    bad = []
    if len(det["boxes_orig_xyxy"]) != len(det["scores"]):
        return ["mspc_scores_length"]
    if any(not B.box_ok(b) for b in det["boxes_orig_xyxy"]):
        bad.append("mspc_invalid_box")
    if any((not isinstance(s, (int, float)) or s != s or s in (float("inf"), float("-inf"))) for s in det["scores"]):
        bad.append("mspc_score_nonfinite")
    elif any(s < float(B.THR_KEY) for s in det["scores"]):
        bad.append("mspc_score_below_thr")
    return bad


def mg_target_defects(det):
    """대상 MG(A) 한 출력의 기술 결함. iter_113 link 의 check_boxes("mg", ...) 규칙(범위 밖·퇴화 box = 연결 결함 → 항목 공통 제외)을 이어받는다."""
    bad = [x.replace("mg_", "mg_A_") for x in B.mg_defects(det)]
    if not bad and any(not B.box_ok(b) for b in det["boxes_orig_xyxy"]):
        bad.append("mg_A_invalid_box")
    return bad


def build_entries(ledger, require=("cure", "mspc")):
    """ledger 항목 -> 순위 entry. excluded_from_ranking 이 있는 항목은 제외 목록으로."""
    ent, excl = [], []
    for l in ledger:
        why = l.get("excluded_from_ranking")
        if why:
            excl.append({"item_key": l["item_key"], "reason": why})
            continue
        eg = B.is_error(l["M"], l["GT"])
        eh = B.is_error(l["M"], l["ALT"]) if l["ALT"] else None
        e = {"item_key": l["item_key"], "patient": l["PatientID"], "tk": B.tie_key(l["item_key"]),
             "D": B.risk_d(l["M"], l["C"]), "B": B.risk_b(l["M_scores"]), "e": eg, "eh": eh, "annot": B.annot_status(eg, eh),
             "iou_M_GT": G.union_iou(l["M"], l["GT"]) if l["M"] else 0.0}
        e["P"] = B.risk_d(l["M"], l["P"]) if "P" in l else None
        ent.append(e)
    return ent, excl


def captures(entries):
    sel = {f: B.select(entries, f)[0] for f in FIELDS}
    K = B.k_of(len(entries))
    cap = {f: sum(entries[i]["e"] for i in sel[f]) for f in FIELDS}
    return cap, sel, K


def deltas(entries):
    cap, sel, K = captures(entries)
    return cap["D"] - cap["B"], cap["D"] - cap["P"], cap, sel, K


def bounds_pair(entries, fx, fy, und):
    n = len(entries)
    sx, _ = B.select(entries, fx)
    sy, _ = B.select(entries, fy)
    ox, rx = B.tie_options(entries, fx)
    oy, ry = B.tie_options(entries, fy)
    fxo, fyo = B.fixed_options(entries, sx), B.fixed_options(entries, sy)
    none = [False] * n
    free = list(und)
    return {"tie_only": (B.extreme(entries, ox, rx, oy, ry, none, False), B.extreme(entries, ox, rx, oy, ry, none, True)),
            "annot_only": (B.extreme(entries, fxo, 0, fyo, 0, free, False), B.extreme(entries, fxo, 0, fyo, 0, free, True)),
            "tie_and_annot": (B.extreme(entries, ox, rx, oy, ry, free, False), B.extreme(entries, ox, rx, oy, ry, free, True))}


def side_range(entries, field):
    n = len(entries)
    zero = [0] * n
    free = [False] * n
    opt, r = B.tie_options(entries, field)
    lo = B.extreme(entries, opt, r, zero, 0, free, False)
    hi = B.extreme(entries, opt, r, zero, 0, free, True)
    return (lo, hi)


def complementarity(entries, sel, a, b):
    sa, sb = sel[a], sel[b]
    cats = {"a_only": [i for i in sorted(sa) if i not in sb], "b_only": [i for i in sorted(sb) if i not in sa], "both": [i for i in sorted(sa) if i in sb],
            "neither": [i for i in range(len(entries)) if i not in sa and i not in sb]}
    out = {}
    for k, idx in cats.items():
        err = [i for i in idx if entries[i]["e"]]
        out[k + "_errors"] = [entries[i]["item_key"] for i in err]
        out[k + "_error_patients"] = len({entries[i]["patient"] for i in err})
    return out


def bootstrap(entries, n_boot=BOOT_N, seed=SEED):
    pats = sorted({e["patient"] for e in entries})
    by_p = {p: [e for e in entries if e["patient"] == p] for p in pats}
    rng = random.Random(seed)
    out = []
    for _ in range(n_boot):
        draws = [rng.randrange(len(pats)) for _ in pats]
        rep = []
        for j, di in enumerate(draws):
            for e in by_p[pats[di]]:
                ne = dict(e)
                ne["tk"] = (e["tk"][0], j)
                rep.append(ne)
        dA, dB, cap, _, K = deltas(rep)
        out.append((dA, dB, len(rep)))
    return out


def summarize(boot):
    res = {}
    for name, idx in (("A", 0), ("B", 1)):
        v = np.array([x[idx] / x[2] for x in boot])
        lo, hi = (float(np.percentile(v, q)) for q in CI_Q)
        res[name] = {"ci_9875": [lo, hi], "half_width": (hi - lo) / 2, "ci95_descriptive": [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))],
                     "mean": float(v.mean()), "p_gt0": float((v > 0).mean()), "p_lt0": float((v < 0).mean()), "n": len(v)}
    return res


def leave_one_patient_out(entries):
    out = {}
    for p in sorted({e["patient"] for e in entries}):
        sub = [e for e in entries if e["patient"] != p]
        dA, dB, cap, _, K = deltas(sub)
        out[p] = {"N": len(sub), "K": K, "dA": dA, "dB": dB}
    return out


def analyze(ledger, n_boot=BOOT_N, seed=SEED):
    ent, excl = build_entries(ledger)
    N = len(ent)
    dA, dB, cap, sel, K = deltas(ent)
    und = [e["annot"].startswith("undetermined") for e in ent]
    bA = bounds_pair(ent, "D", "B", und)
    bB = bounds_pair(ent, "D", "P", und)
    boot = bootstrap(ent, n_boot, seed)
    s = summarize(boot)
    loo = leave_one_patient_out(ent)
    res = {"N": N, "K": K, "n_patients": len({e["patient"] for e in ent}), "n_errors_official": sum(e["e"] for e in ent),
           "excluded_from_ranking": excl, "capture": {"cure": cap["D"], "mspc": cap["P"], "confidence": cap["B"]},
           "precision": {"cure": cap["D"] / K, "mspc": cap["P"] / K, "confidence": cap["B"] / K},
           "dA_count": dA, "dB_count": dB, "dA": dA / N, "dB": dB / N,
           "selected": {"cure": [ent[i]["item_key"] for i in sorted(sel["D"])], "mspc": [ent[i]["item_key"] for i in sorted(sel["P"])],
                        "confidence": [ent[i]["item_key"] for i in sorted(sel["B"])]},
           "complementarity_A": complementarity(ent, sel, "D", "B"), "complementarity_B": complementarity(ent, sel, "D", "P"),
           "annotation_status_counts": {k: sum(1 for e in ent if e["annot"] == k) for k in ("confirmed_error", "confirmed_ok", "undetermined_disagree", "undetermined_no_alt")},
           "bounds_A": bA, "bounds_B": bB,
           "side_tie_ranges": {"cure": side_range(ent, "D"), "mspc": side_range(ent, "P"), "confidence": side_range(ent, "B")},
           "bootstrap": s, "leave_one_patient_out": {"A": {"min": min(v["dA"] for v in loo.values()), "max": max(v["dA"] for v in loo.values()), "n_negative": sum(v["dA"] < 0 for v in loo.values())},
                                                       "B": {"min": min(v["dB"] for v in loo.values()), "max": max(v["dB"] for v in loo.values()), "n_negative": sum(v["dB"] < 0 for v in loo.values())},
                                                       "per_patient": loo}}
    res["positive_checks"] = {"A": positive_checks(res, "A"), "B": positive_checks(res, "B")}
    return res, ent, boot


def positive_checks(res, which):
    d = res["dA" if which == "A" else "dB"]
    b = res["bounds_" + which]
    ci = res["bootstrap"][which]["ci_9875"]
    loo = res["leave_one_patient_out"][which]
    return {"delta_ge_min": d >= MIN_EFFECT, "ci_lower_gt0": ci[0] > 0, "conservative_tie_annot_min_gt0": b["tie_and_annot"][0] > 0,
            "loo_no_negative": loo["n_negative"] == 0}


def expansion_decision(res_init, n_remaining_patients):
    """사전 규칙: 초기 평가에서 A 또는 B 중 하나라도 (상한>=0.05 and 반폭>0.05) 이면 확대. 남은 환자가 없으면 종료."""
    cond = {}
    for w in ("A", "B"):
        b = res_init["bootstrap"][w]
        cond[w] = {"ci_upper": b["ci_9875"][1], "half_width": b["half_width"], "upper_ge_0.05": b["ci_9875"][1] >= MIN_EFFECT, "half_width_gt_0.05": b["half_width"] > MIN_EFFECT}
        cond[w]["meets"] = cond[w]["upper_ge_0.05"] and cond[w]["half_width_gt_0.05"]
    expand = (cond["A"]["meets"] or cond["B"]["meets"]) and n_remaining_patients > 0
    return {"conditions": cond, "n_remaining_patients": n_remaining_patients, "expand": bool(expand)}


def judge(res, cost_mspc_le_cure):
    """최종 투자 판정 입력. cost_mspc_le_cure: True/False/None(불확정)."""
    out = {}
    for w in ("A", "B"):
        pc = res["positive_checks"][w]
        ci = res["bootstrap"][w]["ci_9875"]
        if all(pc.values()):
            st = "positive"
        elif ci[1] < MIN_EFFECT:
            st = "min_useful_effect_excluded_opposite_direction" if ci[1] <= 0 else "min_useful_effect_excluded"
        else:
            st = "inconclusive"
        out[w] = {"status": st, "checks": pc, "ci_9875": ci}
    b_hi = res["bootstrap"]["B"]["ci_9875"][1]
    general_sufficient = b_hi < MIN_EFFECT and cost_mspc_le_cure is True
    out["general_control_sufficient"] = general_sufficient
    out["general_control_cost_unresolved"] = (b_hi < MIN_EFFECT and cost_mspc_le_cure is None)
    if out["A"]["status"] == "positive" and out["B"]["status"] == "positive":
        out["summary"] = "A_and_B_positive"
    elif out["A"]["status"] == "positive":
        out["summary"] = "A_only_positive"
    elif general_sufficient:
        out["summary"] = "general_control_sufficient_hold_specific_investment"
    else:
        out["summary"] = "inconclusive_or_excluded"
    return out
