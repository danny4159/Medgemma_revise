"""iter_108 독립 재계산: production 평가기(ev108_eval/ev108_spec parser)를 import하지 않고 원시 출력 JSONL과 labels/bbox 저장 파일에서 주요 수치를 다시 계산한다.
python ev108_verify.py <p180|e600> <report.json> <out.json>   (out은 새 파일만)
parser는 plan §Evaluation의 semantic_v1 정의(전체 문자열 yes/no[./!], 전체 JSON {"answer"}, A에 한해 Normal/Abnormal)를 별도로 구현한다."""
import glob
import json
import re
import sys
from pathlib import Path

import numpy as np

R16, R15, R108 = Path("results/iter_016"), Path("results/iter_015"), Path("results/iter_108")
EOT = "<end_of_turn>"


def sem(target, raw, eos):
    if not eos:
        return None
    t = raw[:-len(EOT)] if raw.endswith(EOT) else raw
    t = t.strip()
    c = t.lower()
    if c and c[-1] in ".!":
        c = c[:-1]
    if c in ("yes", "no"):
        return c
    if target == "A" and c in ("normal", "abnormal"):
        return {"normal": "no", "abnormal": "yes"}[c]
    if t.startswith("{"):
        try:
            v = json.loads(t)
        except ValueError:
            return None
        if isinstance(v, dict) and list(v) == ["answer"] and v["answer"] in ("yes", "no"):
            return v["answer"]
    return None


GT = {"opacity": {"O": "yes", "A": "yes"}, "normal": {"O": "no", "A": "no"}, "not_normal_no_opacity": {"O": "no", "A": "yes"}}


def rd(p):
    return [json.loads(l) for l in open(p) if l.strip()]


def main():
    which, rep_path, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    if out.exists():
        sys.exit("exists")
    rep = json.load(open(rep_path))
    labels = json.load(open(R16 / "manifests/labels.json"))
    sets = json.load(open(R16 / "manifests/sets.json"))
    cat = {i: v["category"] for i, v in labels.items()}
    name = "P180" if which == "p180" else "E600"
    full = [i for c in ("opacity", "normal", "not_normal_no_opacity") for i in sets[name][c]]
    # 저장 bbox: 비어 있지 않은 환자
    bb = {}
    for r in rd(R15 / "reuse/bbox_B0_concise.jsonl"):
        bb[r["id"]] = r
    nonempty = sorted(i for i in full if bb[i]["ended_eos"] and bb[i]["suffix_text_raw"].replace(EOT, "").strip() != "[]")
    # 원시 출력
    ans = {}
    seen = set()
    for stage, d in rep["dirs"].items():
        for f in glob.glob(f"{d}/gen_worker*.jsonl"):
            for r in rd(f):
                assert r["request_id"] not in seen
                seen.add(r["request_id"])
                ans[(r["patient"], r["cond"], r["target"])] = sem(r["target"], r["suffix_text_raw"], r["ended_eos"])
    for st in ("e180_plain__M0", "e600x_plain__M0"):
        for f in glob.glob(str(R16 / f"gen/{st}/gen_worker*.jsonl")):
            for r in rd(f):
                if r["condition"] == "direct" and r["fmt"] == "plain" and r["checkpoint"] == "M0":
                    ans[(r["id"], "F", r["target"])] = sem(r["target"], r["suffix_text_raw"], r["ended_eos"])
    assert all((p, c, t) in ans for p in nonempty for c in ("D", "T", "C") for t in "OA") and all((p, "L", "O") in ans for p in nonempty)
    assert all((p, "F", t) in ans for p in full for t in "OA")

    def ok(p, c, t):
        a = ans[(p, c, t)]
        return int(a is not None and a == GT[cat[p]][t])

    def valid(p, c, t):
        return ans[(p, c, t)] is not None

    res = {"nonempty_n": len(nonempty), "nonempty_by_cat": {c: sum(cat[p] == c for p in nonempty) for c in GT}}
    nno = [p for p in nonempty if cat[p] == "not_normal_no_opacity"]

    def cmp(a, b, subset):
        (ca, ta), (cb, tb) = a, b
        d = [ok(p, ca, ta) - ok(p, cb, tb) for p in subset]
        chg = sum(1 for p in subset if valid(p, ca, ta) and valid(p, cb, tb) and ok(p, ca, ta) != ok(p, cb, tb))
        return {"diff": sum(d) / len(d), "changed_valid": chg, "n": len(subset)}
    spec = {"T_minus_D_O": (("T", "O"), ("D", "O"), nonempty), "T_minus_D_A_nno": (("T", "A"), ("D", "A"), nno),
            "T_minus_C_O": (("T", "O"), ("C", "O"), nonempty), "T_minus_C_A_nno": (("T", "A"), ("C", "A"), nno),
            "D_minus_F_O": (("D", "O"), ("F", "O"), nonempty), "D_minus_F_A_nno": (("D", "A"), ("F", "A"), nno),
            "T_minus_F_O": (("T", "O"), ("F", "O"), nonempty), "L_minus_F_O": (("L", "O"), ("F", "O"), nonempty),
            "T_minus_L_O": (("T", "O"), ("L", "O"), nonempty)}
    res["comparisons"] = {k: cmp(*v) for k, v in spec.items()}
    # 독립 bootstrap (category 층화, 별도 구현: 비교마다 환자 index를 직접 재표집, seed 10817)
    rng = np.random.default_rng(10817)
    cats_of = np.array([cat[p] for p in nonempty])
    idx_by = {c: np.where(cats_of == c)[0] for c in GT}
    B = 10000
    draws = {c: idx_by[c][rng.integers(0, len(idx_by[c]), size=(B, len(idx_by[c])))] for c in GT if len(idx_by[c])}
    full_idx = np.concatenate([draws[c] for c in draws], axis=1)
    pos = {p: i for i, p in enumerate(nonempty)}
    for k, (a, b, sub) in spec.items():
        vec = np.zeros(len(nonempty))
        msk = np.zeros(len(nonempty), bool)
        for p in sub:
            vec[pos[p]] = ok(p, a[0], a[1]) - ok(p, b[0], b[1])
            msk[pos[p]] = True
        num = (vec[full_idx] * msk[full_idx]).sum(axis=1)
        den = msk[full_idx].sum(axis=1)
        m = num[den > 0] / den[den > 0]
        res["comparisons"][k]["ci95_indep"] = [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]
    # 정책 S_scope (full 집합; 빈 예측은 F)
    ne = set(nonempty)

    def pol_ans(p, pol, t):
        if t == "A" or p not in ne and pol != "R_B":
            return ans[(p, "F", t)]
        if pol == "F":
            return ans[(p, "F", "O")]
        if pol == "R":
            return ans[(p, "T", "O")]
        if pol == "R_L":
            return ans[(p, "L", "O")]
        if pol == "R_B":
            return "yes" if p in ne else "no"

    def scope(pol):
        per = {c: [] for c in GT}
        for p in full:
            a_o, a_a = pol_ans(p, pol, "O"), pol_ans(p, pol, "A")
            per[cat[p]].append(int(a_o == GT[cat[p]]["O"] and a_a == GT[cat[p]]["A"]))
        return float(np.mean([np.mean(v) for v in per.values()]))
    res["S_scope"] = {k: scope(k) for k in ("F", "R", "R_L", "R_B")}
    # 보고서와 대조
    prod = rep["comparisons_sem"]["comparisons"]
    prods = rep["policies_sem"]["policies"]
    cmp_rows = []
    for k, v in res["comparisons"].items():
        pv = prod[k]
        cmp_rows.append({"name": k, "diff_equal": abs(pv["diff"] - v["diff"]) < 1e-12, "changed_valid_equal": pv["changed_valid"] == v["changed_valid"],
                         "n_equal": pv["n"] == v["n"], "ci_lo_gap": abs(pv["ci95"][0] - v["ci95_indep"][0]), "ci_hi_gap": abs(pv["ci95"][1] - v["ci95_indep"][1])})
    scope_rows = [{"policy": k, "equal": abs(prods[k]["S_scope"] - v) < 1e-12} for k, v in res["S_scope"].items()]
    allok = (all(r["diff_equal"] and r["changed_valid_equal"] and r["n_equal"] and r["ci_lo_gap"] < 0.03 and r["ci_hi_gap"] < 0.03 for r in cmp_rows)
             and all(r["equal"] for r in scope_rows)
             and res["nonempty_n"] == rep["comparisons_sem"]["n_nonempty"])
    res.update({"compare_with_report": cmp_rows, "scope_compare": scope_rows, "n_unique_new_requests": len(seen), "all_ok": bool(allok),
                "note": "점추정·전이 수·S_scope는 정확히 일치해야 하며 CI는 별도 재표집이라 |차이|<0.03(Monte Carlo 허용)로 확인"})
    out.write_text(json.dumps(res, indent=1))
    print(json.dumps({"all_ok": allok, "n_new": len(seen)}))
    for r in cmp_rows:
        print(r)
    print(scope_rows)


if __name__ == "__main__":
    main()
