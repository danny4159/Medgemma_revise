"""iter_109 2단계: 원 평가 회귀 → 명시적 답 평가 → unresolved 공동 배정 범위 → 전이 분해.

python ev109_analyze.py   -> results/iter_109/eval/report_E600.json (+ report_P180_aux.json). 기존 파일은 덮어쓰지 않는다.
GT/category는 ledger 잠금 hash 확인 후에만 읽는다. 원 ev108_eval 순수 함수를 그대로 재사용한다(수정 없음).
"""
import itertools
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

import ev108_data as D
import ev108_eval as E
import ev108_spec as S

ROOT = Path(__file__).resolve().parent
PROV = ROOT / "results/iter_109/provenance"
EVAL = ROOT / "results/iter_109/eval"
R108E = ROOT / "results/iter_108/eval"
TOL = 1e-12


def save_new(path, obj):
    path = Path(path)
    if path.exists():
        sys.exit(f"exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str))


def load_ledger():
    """잠금 hash 확인 후 ledger(iter_108 + F)를 읽는다."""
    rows = []
    for lk, lf in (("ledger_lock.json", "responses_extracted.jsonl"), ("ledger_lock_F.json", "responses_extracted_F.jsonl")):
        lock = json.load(open(PROV / lk))
        if D.file_sha(PROV / lf) != lock["ledger_sha256"]:
            sys.exit(f"ledger changed after lock: {lf}")
        rows += D.read_jsonl(PROV / lf)
    if D.file_sha(ROOT / "ev109_extract.py") != json.load(open(PROV / "ledger_lock.json"))["rules_sha256"]:
        sys.exit("extract rules changed after lock")
    return rows


def deep_diff(a, b, path=""):
    """저장 report와 재계산 결과의 차이 목록 (float은 TOL)."""
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in set(a) | set(b):
            if k not in a or k not in b:
                out.append(f"{path}/{k}: missing")
            else:
                out += deep_diff(a[k], b[k], f"{path}/{k}")
    elif isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            out.append(f"{path}: len")
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                out += deep_diff(x, y, f"{path}[{i}]")
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        if abs(a - b) > TOL:
            out.append(f"{path}: {a} vs {b}")
    elif a != b:
        out.append(f"{path}: {a!r} vs {b!r}")
    return out


# ---------------- 공동 배정 범위 ----------------
def corr_of(cat, target, resp):
    """resp = ext dict. returns 0/1 (해결) 또는 None (unresolved)."""
    if resp["answer"] is None:
        return None
    return int(resp["answer"] == S.correct_answer(cat, target))


def enum_assign(vals, fn):
    """vals: {name: 0/1/None}. unresolved 변수만 {0,1}로 열거해 fn(dict)->value 의 (min,max)를 반환."""
    free = [k for k, v in vals.items() if v is None]
    lo, hi = None, None
    for combo in itertools.product((0, 1), repeat=len(free)):
        a = {k: v for k, v in vals.items() if v is not None}
        a.update(dict(zip(free, combo)))
        x = fn(a)
        lo = x if lo is None else min(lo, x)
        hi = x if hi is None else max(hi, x)
    return lo, hi


def comparison_bounds(R, cats, patients, ext, spec):
    """spec: (name, (condA,tgA), (condB,tgB), mask). 환자별 enumerate → 환자별 d_lo/d_hi 벡터."""
    out = {}
    for name, a, b, mask in spec:
        dlo, dhi = [], []
        for p in patients:
            va = corr_of(cats[p], a[1], ext[(p, a[0], a[1])])
            vb = corr_of(cats[p], b[1], ext[(p, b[0], b[1])])
            lo, hi = enum_assign({"a": va, "b": vb}, lambda x: x["a"] - x["b"])
            dlo.append(lo)
            dhi.append(hi)
        dlo, dhi = np.array(dlo, float), np.array(dhi, float)
        m = np.asarray(mask, bool)
        out[name] = {"bound": [float(dlo[m].mean()), float(dhi[m].mean())],
                     "endpoint_ci95": {"lo_end": list(R.mean_ci(dlo, m)[1:3]), "hi_end": list(R.mean_ci(dhi, m)[1:3])},
                     "_dlo": dlo, "_dhi": dhi}
    return out


POL = ("F", "R", "R_L", "R_B")


def policy_options(cat, status, v):
    """v: {F_O,F_A,T_O,L_O: 0/1/None}. returns (min/max over assignments helper input) → function of assignment dict → {policy: pair}."""
    ne = status == "ok"
    rb_known = status in ("ok", "empty")
    rb = int(S_bbox_rule(status) == S.correct_answer(cat, "O")) if rb_known else None

    def fn(a):
        fo, fa = a["F_O"], a["F_A"]
        to, lo_ = a.get("T_O"), a.get("L_O")
        return {"F": fo * fa, "R": (to if ne else fo) * fa, "R_L": (lo_ if ne else fo) * fa, "R_B": (rb if rb_known else fo) * fa}
    return fn


def S_bbox_rule(status):
    return E.bbox_rule_answer(status)


def policy_bounds(R, strata, ids, cats, bstatus, ext):
    """정책 S_scope 및 차이(R-F 등)의 공동 배정 범위. F 응답(F_O,F_A)은 모든 정책이 공유하는 하나의 변수다."""
    per_pair = {n: ([], []) for n in POL}
    diff_names = (("R", "F"), ("R_L", "F"), ("R_B", "F"), ("R_L", "R"), ("R_B", "R"), ("R_B", "R_L"))
    per_diff = {f"{a}_minus_{b}": ([], []) for a, b in diff_names}
    for i in ids:
        st = bstatus[i]
        v = {"F_O": corr_of(cats[i], "O", ext[(i, "F", "O")]), "F_A": corr_of(cats[i], "A", ext[(i, "F", "A")])}
        if st == "ok":
            v["T_O"] = corr_of(cats[i], "O", ext[(i, "T", "O")])
            v["L_O"] = corr_of(cats[i], "O", ext[(i, "L", "O")])
        fn = policy_options(cats[i], st, v)
        for n in POL:
            lo, hi = enum_assign(v, lambda a, n=n: fn(a)[n])
            per_pair[n][0].append(lo)
            per_pair[n][1].append(hi)
        for a, b in diff_names:
            lo, hi = enum_assign(v, lambda x, a=a, b=b: fn(x)[a] - fn(x)[b])
            per_diff[f"{a}_minus_{b}"][0].append(lo)
            per_diff[f"{a}_minus_{b}"][1].append(hi)

    def balanced(vec):
        vec = np.asarray(vec, float)
        return float(np.mean([vec[[k for k, s in enumerate(strata) if s == c]].mean() for c in S.CATS]))

    def ci(vec):
        vec = np.asarray(vec, float)
        reps = []
        for c in S.CATS:
            m = np.array([s == c for s in strata])
            cm = R.counts[:, m].astype(float)
            reps.append((cm @ vec[m]) / cm.sum(axis=1))
        lo, hi = np.percentile(np.mean(reps, axis=0), [2.5, 97.5])
        return [float(lo), float(hi)]

    out = {"S_scope_bound": {n: [balanced(per_pair[n][0]), balanced(per_pair[n][1])] for n in POL}, "diff_bound": {}}
    for k, (lo, hi) in per_diff.items():
        out["diff_bound"][k] = {"bound": [balanced(lo), balanced(hi)], "endpoint_ci95": {"lo_end": ci(lo), "hi_end": ci(hi)}}
    return out


# ---------------- 전이 분해 ----------------
def transitions(patients, cats, orig_ans, ext, spec):
    """원 semantic_v1에서 invalid가 관여한 정확도 차이 환자를 명시적 답 평가 이후 분해한다."""
    out = {}
    for name, a, b, mask in spec:
        c = Counter()
        for p, mk in zip(patients, mask):
            if not mk:
                continue
            sa = E.score(cats[p], a[1], orig_ans[(p, a[0], a[1])], "sem")
            sb = E.score(cats[p], b[1], orig_ans[(p, b[0], b[1])], "sem")
            if sa[2] == sb[2] or (sa[3] and sb[3]):
                continue
            c["orig_invalid_driven"] += 1
            va, vb = corr_of(cats[p], a[1], ext[(p, a[0], a[1])]), corr_of(cats[p], b[1], ext[(p, b[0], b[1])])
            if va is None or vb is None:
                c["after_unresolved"] += 1
            elif va == vb:
                c["after_resolved_same_correctness"] += 1
            elif va > vb:
                c["after_content_a_right_b_wrong"] += 1
            else:
                c["after_content_a_wrong_b_right"] += 1
        out[name] = dict(c)
    return out


def make_new_ans(orig_ans, ext):
    new = {}
    for k, r in orig_ans.items():
        e = ext[k]
        new[k] = {"suffix_text_raw": e["answer"], "ended_eos": True} if e["answer"] else {"suffix_text_raw": "UNRESOLVED explanation", "ended_eos": True}
    return new


def comp_spec(nonempty, cats):
    nno = [cats[p] == "not_normal_no_opacity" for p in nonempty]
    allm = [True] * len(nonempty)
    return [("T_minus_D_O", ("T", "O"), ("D", "O"), allm), ("T_minus_D_A_nno", ("T", "A"), ("D", "A"), nno),
            ("T_minus_C_O", ("T", "O"), ("C", "O"), allm), ("T_minus_C_A_nno", ("T", "A"), ("C", "A"), nno),
            ("D_minus_F_O", ("D", "O"), ("F", "O"), allm), ("D_minus_F_A_nno", ("D", "A"), ("F", "A"), nno),
            ("T_minus_F_O", ("T", "O"), ("F", "O"), allm), ("T_minus_F_A_nno", ("T", "A"), ("F", "A"), nno),
            ("T_minus_D_A_pooled", ("T", "A"), ("D", "A"), allm), ("T_minus_C_A_pooled", ("T", "A"), ("C", "A"), allm),
            ("L_minus_F_O", ("L", "O"), ("F", "O"), allm), ("T_minus_L_O", ("T", "O"), ("L", "O"), allm)]


def analyze(name, sets, cats, bstatus, orig_ans, ext, stored=None):
    full = {c: sets[name][c] for c in S.CATS}
    full_ids = {i for c in S.CATS for i in full[c]}
    nonempty = sorted(p for p in full_ids if bstatus[p] == "ok")
    # 원 ev108 순서(정렬된 nonempty)와 동일
    ne_ext = {k: v for k, v in ext.items() if k[0] in full_ids}
    ne_orig = {k: v for k, v in orig_ans.items() if k[0] in full_ids}
    out = {"set": name, "n_full": len(full_ids), "n_nonempty": len(nonempty)}
    new_ans = make_new_ans(ne_orig, ne_ext)
    t_boot = time.time()
    for parser, ans in (("strict", ne_orig), ("sem", ne_orig), ("explicit", new_ans)):
        pr = "sem" if parser == "explicit" else parser
        out[f"comparisons_{parser}"] = E.comparisons(nonempty, cats, ans, pr)
        out[f"policies_{parser}"] = E.policy_report(full, cats, bstatus, ans, pr)
    out["_t_boot_s"] = time.time() - t_boot
    # 회귀: 저장된 iter_108 report와 비교
    if stored is not None:
        reg = {}
        for k in ("comparisons_sem", "policies_sem", "comparisons_strict", "policies_strict"):
            d = deep_diff(stored[k], out[k.replace("sem", "sem")])
            reg[k] = {"n_diff": len(d), "diffs": d[:5]}
        out["regression_vs_iter108_report"] = reg
    # 명시적 답 범위
    strata = [cats[p] for p in nonempty]
    R = E.Resampler(strata)
    spec = comp_spec(nonempty, cats)
    cb = comparison_bounds(R, cats, nonempty, ne_ext, spec)
    out["comparison_bounds"] = {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")} for k, v in cb.items()}
    # 교차 확인: E.compare의 format_bound와 열거 bound 일치
    out["bound_crosscheck_max_abs"] = max(max(abs(out["comparisons_explicit"]["comparisons"][k]["format_bound"][0] - cb[k]["bound"][0]),
                                              abs(out["comparisons_explicit"]["comparisons"][k]["format_bound"][1] - cb[k]["bound"][1])) for k in cb)
    ids_pol = [i for c in S.CATS for i in full[c]]
    pol_strata = [cats[i] for i in ids_pol]
    Rp = E.Resampler(pol_strata)
    out["policy_bounds"] = policy_bounds(Rp, pol_strata, ids_pol, cats, bstatus, ne_ext)
    out["transitions_orig_invalid_driven"] = transitions(nonempty, cats, ne_orig, ne_ext, spec)
    # 조건·질문별 응답 구성
    comp = {}
    for (p, c, t), e in ne_ext.items():
        comp.setdefault(f"{c}_{t}", Counter())[e["source"]] += 1
    out["response_source_counts"] = {k: dict(v) for k, v in sorted(comp.items())}
    reasons = Counter((c, t, e["reason"]) for (p, c, t), e in ne_ext.items() if e["source"] == "unresolved")
    out["unresolved_reasons"] = {f"{k[0]}_{k[1]}:{k[2]}": v for k, v in sorted(reasons.items())}
    # 새 수용 응답의 정답 여부 (원 invalid → explicit)
    exp_c = Counter()
    for (p, c, t), e in ne_ext.items():
        if e["source"] == "explicit":
            exp_c[(c, t, "correct" if e["answer"] == S.correct_answer(cats[p], t) else "wrong")] += 1
    out["explicit_accepted_by_correctness"] = {f"{k[0]}_{k[1]}:{k[2]}": v for k, v in sorted(exp_c.items())}
    return out


def main():
    t0 = time.time()
    rows = load_ledger()
    ext = {(r["patient"], r["cond"], r["target"]): r["ext"] for r in rows}
    orig_ans = {(r["patient"], r["cond"], r["target"]): {"suffix_text_raw": r["raw"], "ended_eos": r["ended_eos"]} for r in rows}
    if len(ext) != len(rows):
        sys.exit("duplicate ledger keys")
    sets, labels, infer, ckpt, bbox = D.load_assets()
    cats = {i: labels[i]["category"] for i in labels}
    bstatus = {i: S.parse_saved_bbox(bbox[i]["suffix_text_raw"], bbox[i]["ended_eos"])[0] for i in bbox}
    # 200반복 시간 측정 (전체 예상 wall-clock 근거)
    nonempty = sorted(p for c in S.CATS for p in sets["E600"][c] if bstatus[p] == "ok")
    ta = time.time()
    E.Resampler([cats[p] for p in nonempty], B=200)
    t200 = time.time() - ta
    stored = json.load(open(R108E / "report_E600.json"))
    rep = analyze("E600", sets, cats, bstatus, orig_ans, ext, stored)
    rep["timing"] = {"resampler_200_s": t200, "full_analysis_s": time.time() - t0, "analyze_boot_s": rep.pop("_t_boot_s")}
    rep["inputs"] = {"n_ledger_rows": len(rows), "ledger_lock": json.load(open(PROV / "ledger_lock.json")), "ledger_lock_F": json.load(open(PROV / "ledger_lock_F.json")),
                     "extract_lock": json.load(open(ROOT / "results/iter_109/extract_lock.json"))}
    save_new(EVAL / "report_E600.json", rep)
    aux = analyze("P180", sets, cats, bstatus, orig_ans, ext, json.load(open(R108E / "report_P180.json")))
    aux.pop("_t_boot_s")
    save_new(EVAL / "report_P180_aux.json", aux)
    for k, v in rep["regression_vs_iter108_report"].items():
        print("regression", k, v["n_diff"])
    print("crosscheck", rep["bound_crosscheck_max_abs"], "elapsed", time.time() - t0)


if __name__ == "__main__":
    main()
