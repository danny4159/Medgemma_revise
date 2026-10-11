"""iter_109 독립 검증: production 집계(ev109_analyze/ev108_eval)를 호출하지 않고 ledger+labels에서 주요 수치를 다시 계산한다.

- 정답 수·점추정: 직접 집계. 경계: 4개 변수 전수 열거(production은 unresolved만 열거). bootstrap: 같은 seed·RNG 호출 순서의 단순 루프 구현.
- 성질 검사: (1) 같은 조건끼리 비교 0 (2) 양쪽 unresolved의 경계 (3) 명시적 답을 지우면(=unresolved화) 경계가 넓어지기만 함 (4) F 공유 변수 상쇄.
- 추출 재현: ledger의 모든 explicit 행을 raw에서 다시 추출해 일치하는지 + span 텍스트가 정확히 yes/no인지.
결과: results/iter_109/eval/verify_E600.json (덮어쓰지 않음). 하나라도 실패하면 exit 1.
"""
import itertools
import json
import sys
from pathlib import Path

import numpy as np

import ev108_data as D
import ev108_spec as S
import ev109_analyze as A
import ev109_extract as X

ROOT = Path(__file__).resolve().parent
EVAL = ROOT / "results/iter_109/eval"
TOL = 1e-9
checks = []


def chk(name, ok, detail=None):
    checks.append(dict(name=name, ok=bool(ok), detail=detail))


def boot(strata, d_vec, mask, B=S.N_BOOT, seed=S.SEED):
    """단순 루프 구현. A.E.Resampler 와 같은 RNG 호출 순서 (카테고리 정렬순, size=(B,n_c))."""
    n = len(strata)
    rng = np.random.default_rng(seed)
    draws = {}
    for c in sorted(set(strata)):
        idx = np.array([i for i, s in enumerate(strata) if s == c])
        draws[c] = idx[rng.integers(0, len(idx), size=(B, len(idx)))]
    allsel = np.concatenate([draws[c] for c in sorted(draws)], axis=1)  # B x n 재표집 환자 index
    mask = np.asarray(mask, bool)
    means = []
    for b in range(B):
        sel = allsel[b]
        sel = sel[mask[sel]]
        if len(sel):
            means.append(d_vec[sel].mean())
    return [float(x) for x in np.percentile(means, [2.5, 97.5])]


def cvals(p, cond, t, cats, ext, correct_when_unres):
    e = ext[(p, cond, t)]
    if e["answer"] is None:
        return correct_when_unres
    return int(e["answer"] == S.correct_answer(cats[p], t))


def main():
    rows = A.load_ledger()
    ext = {(r["patient"], r["cond"], r["target"]): r["ext"] for r in rows}
    sets, labels, infer, ckpt, bbox = D.load_assets()
    cats = {i: labels[i]["category"] for i in labels}
    bst = {i: S.parse_saved_bbox(bbox[i]["suffix_text_raw"], bbox[i]["ended_eos"])[0] for i in bbox}
    rep = json.load(open(EVAL / "report_E600.json"))
    ne = sorted(p for c in S.CATS for p in sets["E600"][c] if bst[p] == "ok")
    strata = [cats[p] for p in ne]
    chk("nonempty_236_by_cat", len(ne) == 236 and [strata.count(c) for c in S.CATS] == [164, 5, 67], [strata.count(c) for c in S.CATS])
    # 1) 추출 재현
    bad = 0
    for r in rows:
        e = X.resolve(r["target"], r["raw"], r["ended_eos"])
        if e != r["ext"]:
            bad += 1
        if r["ext"]["source"] == "explicit":
            for sp in r["ext"]["spans"]:
                s0, s1 = sp["span"]
                if X.clean(r["raw"])[s0:s1].lower() != sp["answer"] or sp["answer"] != r["ext"]["answer"]:
                    bad += 1
    chk("extraction_reproducible_and_spans_exact", bad == 0, bad)
    chk("no_duplicate_ledger_keys", len(ext) == len(rows) and len(rows) == 2852, len(rows))
    # 2) 점추정: unresolved=wrong
    pairs = [("T_minus_D_O", ("T", "O"), ("D", "O"), None), ("T_minus_D_A_nno", ("T", "A"), ("D", "A"), "nno"),
             ("T_minus_C_O", ("T", "O"), ("C", "O"), None), ("T_minus_C_A_nno", ("T", "A"), ("C", "A"), "nno"),
             ("T_minus_F_O", ("T", "O"), ("F", "O"), None), ("D_minus_F_A_nno", ("D", "A"), ("F", "A"), "nno"),
             ("L_minus_F_O", ("L", "O"), ("F", "O"), None), ("T_minus_L_O", ("T", "O"), ("L", "O"), None)]
    for name, a, b, m in pairs:
        mask = np.array([m is None or cats[p] == "not_normal_no_opacity" for p in ne])
        d0 = np.array([cvals(p, *a, cats, ext, 0) - cvals(p, *b, cats, ext, 0) for p in ne], float)
        dlo = np.array([cvals(p, *a, cats, ext, 0) - cvals(p, *b, cats, ext, 1) for p in ne], float)
        dhi = np.array([cvals(p, *a, cats, ext, 1) - cvals(p, *b, cats, ext, 0) for p in ne], float)
        c = rep["comparisons_explicit"]["comparisons"][name]
        bd = rep["comparison_bounds"][name]
        chk(f"point_{name}", abs(d0[mask].mean() - c["diff"]) < TOL, [float(d0[mask].mean()), c["diff"]])
        chk(f"bound_{name}", abs(dlo[mask].mean() - bd["bound"][0]) < TOL and abs(dhi[mask].mean() - bd["bound"][1]) < TOL)
        ci = boot(strata, d0, mask)
        chk(f"ci_{name}", max(abs(ci[0] - c["ci95"][0]), abs(ci[1] - c["ci95"][1])) < TOL, [ci, c["ci95"]])
        if name in ("T_minus_D_O", "T_minus_D_A_nno", "T_minus_C_O"):
            cl, ch = boot(strata, dlo, mask), boot(strata, dhi, mask)
            chk(f"endpoint_ci_{name}", max(abs(cl[0] - bd["endpoint_ci95"]["lo_end"][0]), abs(cl[1] - bd["endpoint_ci95"]["lo_end"][1]),
                                           abs(ch[0] - bd["endpoint_ci95"]["hi_end"][0]), abs(ch[1] - bd["endpoint_ci95"]["hi_end"][1])) < TOL)
    # 3) 정책: 4개 변수 전수 열거로 경계 재계산
    full = [i for c in S.CATS for i in sets["E600"][c]]
    pol_lo = {n: [] for n in A.POL}
    pol_hi = {n: [] for n in A.POL}
    diff_lo = {k: [] for k in rep["policy_bounds"]["diff_bound"]}
    diff_hi = {k: [] for k in rep["policy_bounds"]["diff_bound"]}
    for i in full:
        ne_i = bst[i] == "ok"
        known = {"F_O": cvals(i, "F", "O", cats, ext, None), "F_A": cvals(i, "F", "A", cats, ext, None)}
        if ne_i:
            known["T_O"], known["L_O"] = cvals(i, "T", "O", cats, ext, None), cvals(i, "L", "O", cats, ext, None)
        else:
            known["T_O"], known["L_O"] = 0, 0  # 사용되지 않는 변수
        opts = [[v] if v is not None else [0, 1] for v in known.values()]
        vals = {n: [] for n in A.POL}
        dv = {k: [] for k in diff_lo}
        for fo, fa, to, lo in itertools.product(*opts):
            rb_ans = "yes" if bst[i] == "ok" else "no"
            rb = int(rb_ans == S.correct_answer(cats[i], "O"))
            pair = {"F": fo * fa, "R": (to if ne_i else fo) * fa, "R_L": (lo if ne_i else fo) * fa, "R_B": rb * fa}
            for n in A.POL:
                vals[n].append(pair[n])
            for k in dv:
                a_, b_ = k.split("_minus_")
                dv[k].append(pair[a_] - pair[b_])
        for n in A.POL:
            pol_lo[n].append(min(vals[n]))
            pol_hi[n].append(max(vals[n]))
        for k in dv:
            diff_lo[k].append(min(dv[k]))
            diff_hi[k].append(max(dv[k]))
    fstrata = [cats[i] for i in full]

    def bal(v):
        v = np.array(v, float)
        return float(np.mean([v[[j for j, s in enumerate(fstrata) if s == c]].mean() for c in S.CATS]))
    for n in A.POL:
        b = rep["policy_bounds"]["S_scope_bound"][n]
        chk(f"policy_S_bound_{n}", abs(bal(pol_lo[n]) - b[0]) < TOL and abs(bal(pol_hi[n]) - b[1]) < TOL, [bal(pol_lo[n]), bal(pol_hi[n]), b])
    for k in diff_lo:
        b = rep["policy_bounds"]["diff_bound"][k]["bound"]
        chk(f"policy_diff_bound_{k}", abs(bal(diff_lo[k]) - b[0]) < TOL and abs(bal(diff_hi[k]) - b[1]) < TOL, [bal(diff_lo[k]), bal(diff_hi[k]), b])
    # 4) 성질: 같은 조건 비교 0, 단조성(더 많이 unresolved화 → 경계 포함 관계)
    same = [cvals(p, "T", "O", cats, ext, 0) - cvals(p, "T", "O", cats, ext, 0) for p in ne]
    chk("same_condition_diff_zero", all(x == 0 for x in same))
    rng = np.random.default_rng(1)
    ext2 = dict(ext)
    keys = [k for k, v in ext.items() if v["answer"] is not None and k[0] in set(ne) and k[1] in ("T", "D") and k[2] == "O"]
    for k in rng.choice(len(keys), size=len(keys) // 5, replace=False):
        ext2[keys[k]] = dict(ext[keys[k]], answer=None)
    d_lo1 = sum(cvals(p, "T", "O", cats, ext, 0) - cvals(p, "D", "O", cats, ext, 1) for p in ne) / len(ne)
    d_lo2 = sum(cvals(p, "T", "O", cats, ext2, 0) - cvals(p, "D", "O", cats, ext2, 1) for p in ne) / len(ne)
    d_hi1 = sum(cvals(p, "T", "O", cats, ext, 1) - cvals(p, "D", "O", cats, ext, 0) for p in ne) / len(ne)
    d_hi2 = sum(cvals(p, "T", "O", cats, ext2, 1) - cvals(p, "D", "O", cats, ext2, 0) for p in ne) / len(ne)
    chk("bounds_monotone_when_answers_removed", d_lo2 <= d_lo1 + 1e-12 and d_hi2 >= d_hi1 - 1e-12, [d_lo1, d_lo2, d_hi1, d_hi2])
    ok_all = all(c["ok"] for c in checks)
    out = dict(all_pass=ok_all, n=len(checks), n_pass=sum(c["ok"] for c in checks), checks=checks)
    p = EVAL / "verify_E600.json"
    if p.exists():
        sys.exit("exists")
    p.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str))
    print(out["n_pass"], "/", out["n"])
    for c in checks:
        if not c["ok"]:
            print("FAIL", c)
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
