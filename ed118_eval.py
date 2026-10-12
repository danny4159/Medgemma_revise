"""iter_118 평가 (생성 전에 잠금). 입력은 검증된 record, cond_map, labels, ledger_det.

정의 (계획 Evaluation만 구현; 계획에 없는 사건 수 문턱은 추가하지 않는다):
 - 정답 gt: category=='opacity' → yes, 그 외 → no. outcome(X) = ok|bad|unk (direction이 gt와 같음/반대/unknown).
 - 주 지표 H_W = [n(E ok, W bad) − n(E bad, W ok)] / N (명시 방향 전환만; unknown 전이는 별도 표에 모두 보고). H_C 동일.
 - bootstrap: category 층별 환자 resample 10,000회 seed 11817 (세 조건·정책을 같은 환자 단위로), percentile 95%. 주검정은 H_W 하나.
 - unknown 범위: unknown 셀을 환자별로 모든 ok/bad 배정으로 열거한 합의 최소/최대 (환자 간 독립이므로 합산이 정확).
 - 정책: B(detector≥0.70 box 있으면 yes), D_C/D_W(초안 유지), S_X = E 명시 답이 B와 같으면 그 답, 아니면 초안 X (E unknown→초안).
 - 공동 지표: 최종 yes → detector box 유지, no → 제거. 양성: yes이고 IoU0.3 최대 일대일 matching에서 tp==n_gt==n_pred, 음성: no.
   unknown은 공동 성공이 아니다. box 경계 개선·위치 정보의 인과 사용은 평가하지 않는다.
 - 판정 라벨(사전): H_W≥0.10 & CI 하한>0 → content_harm_signal; CI 상한<0.10 → no_large_content_harm; 그 외 inconclusive.
"""
import itertools
import json
import os

import numpy as np

import ed118_spec as S
from rsna_diag import geometry as GEO
from rsna_diag import metrics as MET

H_THRESHOLD = 0.10
CATS = ("opacity", "normal", "not_normal_no_opacity")


def outcome(direction, gt):
    if direction == "unknown":
        return "unk"
    return "ok" if direction == gt else "bad"


def det_answer(row):
    return "yes" if any(s >= S.THR for s in row["det"]["scores"]) else "no"


def det_norm(row):
    h, w = row["size_hw"]
    top, left, side = GEO.pad_offsets(h, w)
    boxes = [b for s, b in zip(row["det"]["scores"], row["det"]["boxes_xyxy_px"]) if s >= S.THR]
    return [GEO.canvas_to_norm(b, top, left, side) for b in boxes]


def gt_norm(row, lab):
    h, w = row["size_hw"]
    top, left, side = GEO.pad_offsets(h, w)
    return [GEO.canvas_to_norm(b, top, left, side) for b in lab["boxes_xyxy_px"]]


def joint_success(ans, row, lab):
    """ans: yes|no|unknown (최종 답). 계획의 공동 성공 정의."""
    if ans not in ("yes", "no"):
        return False
    if lab["gt_answer"] == "no":
        return ans == "no"
    if ans != "yes":
        return False
    pred, gt = det_norm(row), gt_norm(row, lab)
    return len(pred) > 0 and len(MET.match(pred, gt, 0.3)) == len(gt) == len(pred)


def build_patients(recs, cond_map, labels, ledger):
    """recs: record 목록(검증됨). returns 환자별 dict 목록 (id 정렬)."""
    byrow = {r["id"]: r for r in ledger}
    raw = {}
    for r in recs:
        raw.setdefault(r["patient"], {})[cond_map[r["patient"]][r["cond"]]] = r
    out = []
    for pid in sorted(raw):
        lab, row = labels[pid], byrow[pid]
        gt = lab["gt_answer"]
        b = det_answer(row)
        p = dict(id=pid, cat=lab["category"], gt=gt, B=b, n_det=len(det_norm(row)), n_gt=len(lab["boxes_xyxy_px"]))
        cls = {}
        for c in S.CONDS:
            r = raw[pid][c]
            k = S.classify(r["suffix_text_raw"], r["ended_eos"])
            cls[c] = k
            p[c] = dict(direction=k["direction"], outcome=outcome(k["direction"], gt),
                        outcome_conf=outcome(k["direction"], gt) if k["confirmed"] else "unk",
                        flags={f: k[f] for f in ("hedged", "conditional", "contradictory", "refusal", "parse_failure", "non_eos", "confirmed")},
                        note=k["note"], n_tokens=r["n_output_tokens"], text=r["suffix_text_raw"][:400])
        drafts = {"C": gt, "W": S.opposite(gt)}
        pol = {"B": b, "D_C": drafts["C"], "D_W": drafts["W"], "E": cls["E"]["direction"], "C": cls["C"]["direction"], "W": cls["W"]["direction"],
               "S_C": S.synth_policy(cls["E"], b, drafts["C"]), "S_W": S.synth_policy(cls["E"], b, drafts["W"])}
        p["policy"] = pol
        p["policy_outcome"] = {k: outcome(v, gt) for k, v in pol.items()}
        p["joint"] = {k: joint_success(v, row, lab) for k, v in pol.items()}
        p["e_unconfirmed_fallback"] = not (cls["E"]["direction"] in ("yes", "no") and cls["E"]["direction"] == b)
        out.append(p)
    return out


def vec(ps, fn):
    return np.array([fn(p) for p in ps], dtype=float)


def stat_vectors(ps, key="outcome"):
    """각 통계의 환자별 기여 벡터. 합/N이 통계다."""
    o = lambda p, c: p[c][key]
    v = {}
    for c in ("W", "C"):
        v[f"H_{c}"] = vec(ps, lambda p: (o(p, "E") == "ok" and o(p, c) == "bad") - (o(p, "E") == "bad" and o(p, c) == "ok"))
    v["H_W_minus_H_C"] = v["H_W"] - v["H_C"]
    for c in S.CONDS:
        v[f"ok_{c}"] = vec(ps, lambda p: o(p, c) == "ok")
        v[f"bad_{c}"] = vec(ps, lambda p: o(p, c) == "bad")
        v[f"unk_{c}"] = vec(ps, lambda p: o(p, c) == "unk")
    for c in ("W", "C"):
        v[f"dAcc_{c}_minus_E"] = v[f"ok_{c}"] - v["ok_E"]
        v[f"dBad_{c}_minus_E"] = v[f"bad_{c}"] - v["bad_E"]
        v[f"dUnk_{c}_minus_E"] = v[f"unk_{c}"] - v["unk_E"]
    for k in ("B", "D_C", "D_W", "S_C", "S_W"):
        v[f"ok_{k}"] = vec(ps, lambda p: p["policy_outcome"][k] == "ok")
    v["dAcc_S_W_minus_W"] = v["ok_S_W"] - v["ok_W"]
    v["dAcc_S_W_minus_E"] = v["ok_S_W"] - v["ok_E"]
    v["dAcc_S_C_minus_E"] = v["ok_S_C"] - v["ok_E"]
    v["dAcc_E_minus_B"] = v["ok_E"] - v["ok_B"]
    v["dAcc_S_W_minus_B"] = v["ok_S_W"] - v["ok_B"]
    for k in ("E", "C", "W", "S_C", "S_W", "B"):
        v[f"joint_{k}"] = vec(ps, lambda p: p["joint"][k])
    return v


def bootstrap(ps, seed=S.SEED_BOOT, B=S.N_BOOT, key="outcome"):
    rng = np.random.default_rng(seed)
    vs = stat_vectors(ps, key)
    idx_by_cat = {c: np.array([i for i, p in enumerate(ps) if p["cat"] == c]) for c in CATS}
    n = len(ps)
    samples = {k: np.zeros(B) for k in vs}
    for c in CATS:
        ids = idx_by_cat[c]
        if len(ids) == 0:
            continue
        draw = ids[rng.integers(0, len(ids), size=(B, len(ids)))]
        for k, v in vs.items():
            samples[k] += v[draw].sum(axis=1)
    out = {}
    for k, v in vs.items():
        s = samples[k] / n
        out[k] = dict(point=float(v.sum() / n), lo=float(np.percentile(s, 2.5)), hi=float(np.percentile(s, 97.5)))
    return out


def transition_table(ps, c, key="outcome"):
    t = {a: {b: 0 for b in ("ok", "bad", "unk")} for a in ("ok", "bad", "unk")}
    for p in ps:
        t[p["E"][key]][p[c][key]] += 1
    return t  # t[E outcome][X outcome]


def h_range(ps, c, key="outcome"):
    """H_c의 unknown 배정 범위 (환자별 열거)."""
    lo = hi = 0
    for p in ps:
        es = ("ok", "bad") if p["E"][key] == "unk" else (p["E"][key],)
        xs = ("ok", "bad") if p[c][key] == "unk" else (p[c][key],)
        vals = [(e == "ok" and x == "bad") - (e == "bad" and x == "ok") for e in es for x in xs]
        lo += min(vals)
        hi += max(vals)
    n = len(ps)
    return [lo / n, hi / n]


def acc_range(ps, getter):
    n = len(ps)
    ok = sum(getter(p) == "ok" for p in ps)
    unk = sum(getter(p) == "unk" for p in ps)
    return [ok / n, (ok + unk) / n]


def diff_range(a, b):
    return [a[0] - b[1], a[1] - b[0]]


def wilson(k, n, z=1.959964):
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5
    return [(c - h) / d, (c + h) / d]


def cond_summary(ps, c):
    n = len(ps)
    f = lambda name: sum(p[c]["flags"][name] for p in ps)
    return dict(n=n, explicit_ok=sum(p[c]["outcome"] == "ok" for p in ps), explicit_bad=sum(p[c]["outcome"] == "bad" for p in ps),
                unknown=sum(p[c]["outcome"] == "unk" for p in ps), confirmed=f("confirmed"),
                confirmed_ok=sum(p[c]["outcome_conf"] == "ok" for p in ps), confirmed_bad=sum(p[c]["outcome_conf"] == "bad" for p in ps),
                hedged=f("hedged"), conditional=f("conditional"), contradictory=f("contradictory"), refusal=f("refusal"),
                parse_failure=f("parse_failure"), non_eos=f("non_eos"),
                direction_yes=sum(p[c]["direction"] == "yes" for p in ps), direction_no=sum(p[c]["direction"] == "no" for p in ps),
                mean_output_tokens=float(np.mean([p[c]["n_tokens"] for p in ps])))


def subgroup_block(ps):
    n = len(ps)
    d = dict(n=n, E=cond_summary(ps, "E") if n else None)
    if n:
        for c in ("C", "W"):
            d[c] = cond_summary(ps, c)
        d["H_W_point"] = (sum((p["E"]["outcome"] == "ok" and p["W"]["outcome"] == "bad") - (p["E"]["outcome"] == "bad" and p["W"]["outcome"] == "ok")
                              for p in ps)) / n
        d["H_C_point"] = (sum((p["E"]["outcome"] == "ok" and p["C"]["outcome"] == "bad") - (p["E"]["outcome"] == "bad" and p["C"]["outcome"] == "ok")
                              for p in ps)) / n
    return d


def report(ps, extra=None):
    n = len(ps)
    boot = bootstrap(ps)
    bootc = bootstrap(ps, key="outcome_conf")
    rep = dict(n=n, n_by_category={c: sum(p["cat"] == c for p in ps) for c in CATS}, conditions={c: cond_summary(ps, c) for c in S.CONDS},
               transitions={c: transition_table(ps, c) for c in ("W", "C")}, transitions_confirmed={c: transition_table(ps, c, "outcome_conf") for c in ("W", "C")},
               H=dict(W=boot["H_W"], C=boot["H_C"], W_minus_C=boot["H_W_minus_H_C"]), H_confirmed=dict(W=bootc["H_W"], C=bootc["H_C"]),
               H_unknown_range=dict(W=h_range(ps, "W"), C=h_range(ps, "C")), bootstrap=boot, bootstrap_confirmed_only=bootc)
    rng = {c: acc_range(ps, lambda p, c=c: p[c]["outcome"]) for c in S.CONDS}
    rep["acc_range_unknown_as_wrong_or_right"] = rng
    rep["acc_diff_range"] = dict(W_minus_E=diff_range(rng["W"], rng["E"]), C_minus_E=diff_range(rng["C"], rng["E"]))
    rep["policies"] = {k: dict(n_ok=sum(p["policy_outcome"][k] == "ok" for p in ps), n_bad=sum(p["policy_outcome"][k] == "bad" for p in ps),
                               n_unk=sum(p["policy_outcome"][k] == "unk" for p in ps), joint_success=sum(p["joint"][k] for p in ps))
                       for k in ("B", "D_C", "D_W", "E", "C", "W", "S_C", "S_W")}
    rep["S_fallback_to_draft_n"] = sum(p["e_unconfirmed_fallback"] for p in ps)
    rep["category_subgroups"] = {c: subgroup_block([p for p in ps if p["cat"] == c]) for c in CATS}
    rep["detector_subgroups"] = {k: subgroup_block([p for p in ps if (p["B"] == p["gt"]) == (k == "detector_correct")]) for k in ("detector_correct", "detector_wrong")}
    rep["E_subgroups"] = {k: subgroup_block([p for p in ps if p["E"]["outcome"] == k]) for k in ("ok", "bad", "unk")}
    eok = [p for p in ps if p["E"]["outcome"] == "ok"]
    rep["conditional_on_E_ok"] = dict(
        n=len(eok), W_bad=sum(p["W"]["outcome"] == "bad" for p in eok), W_unk=sum(p["W"]["outcome"] == "unk" for p in eok),
        C_bad=sum(p["C"]["outcome"] == "bad" for p in eok), C_unk=sum(p["C"]["outcome"] == "unk" for p in eok),
        W_bad_wilson=wilson(sum(p["W"]["outcome"] == "bad" for p in eok), len(eok)),
        E_ok_and_B_ok=sum(p["B"] == p["gt"] for p in eok),
        E_ok_B_ok_W_bad_ids=[p["id"] for p in eok if p["B"] == p["gt"] and p["W"]["outcome"] == "bad"],
        reverse_transitions_E_bad_W_ok=sum(p["E"]["outcome"] == "bad" and p["W"]["outcome"] == "ok" for p in ps))
    d = rep["bootstrap"]["dAcc_W_minus_E"]
    dbad, dunk = rep["bootstrap"]["dBad_W_minus_E"], rep["bootstrap"]["dUnk_W_minus_E"]
    rep["W_vs_E_decomposition"] = dict(dAcc_strict=d, dExplicitBad=dbad, dUnknown=dunk,
                                       note="acc=1-bad-unk. 기술적 분해이며 판정 문턱이 아니다.")
    hw = rep["H"]["W"]
    if hw["point"] >= H_THRESHOLD and hw["lo"] > 0:
        label = "content_harm_signal"
    elif hw["hi"] < H_THRESHOLD:
        label = "no_large_content_harm"
    else:
        label = "inconclusive"
    rep["decision"] = dict(label=label, H_W=hw, threshold=H_THRESHOLD, rule="H_W>=0.10 & CI lower>0 → signal; CI upper<0.10 → no_large; else inconclusive",
                           unknown_range_H_W=rep["H_unknown_range"]["W"],
                           note="개발 진단. 합성 초안 개입의 제한된 관찰이며 자연 오류 빈도·임상 효용·신규 기여를 뜻하지 않는다.")
    rep.update(extra or {})
    return rep


def cost(recs):
    by = {}
    for r in recs:
        by.setdefault(r["cond"], []).append(r)
    allr = recs
    return dict(n=len(allr), sum_generate_s=sum(r["runtime_s_total"] for r in allr), sum_wall_s=sum(r["wall_s"] for r in allr),
                n_retry=sum(len(r["attempts"]) > 1 for r in allr), n_attempts=sum(len(r["attempts"]) for r in allr),
                new_tokens_final=sum(r["n_output_tokens"] for r in allr),
                peak_mem_reserved_gb_max=max(r["peak_mem_reserved_gb_max"] for r in allr))
