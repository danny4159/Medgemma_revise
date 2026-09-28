"""iter_029 독립 검증: c_table/e_table 파생 표에 의존하지 않고 원시 JSONL과 GT/source에서
방향·rank AUROC·동점 포착률·대표 선택을 별도로 계산해 저장 결과와 대조한다.
"""
import json
import math
import os

import numpy as np

from rsna_diag import risk28

RESULTS_ROOT = "results/iter_028"
OUT = "results/iter_029/decide"


def rank_auroc(scores, y):
    """Mann-Whitney rank 기반 AUROC (동점은 평균 순위)."""
    s = np.asarray(scores, float)
    yy = np.asarray(y, int)
    order = np.argsort(s)
    ranks = np.empty(len(s))
    sv = s[order]
    i = 0
    while i < len(sv):
        j = i
        while j + 1 < len(sv) and sv[j + 1] == sv[i]:
            j += 1
        avg = (i + 1 + j + 1) / 2.0
        ranks[order[i:j + 1]] = avg
        i = j + 1
    n_pos, n_neg = int(yy.sum()), int(len(yy) - yy.sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    r_pos = ranks[yy == 1].sum()
    return float((r_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def capture_at_k_tiebreak_expected(scores, y, frac=0.2):
    """rsna_diag.risk28_eval.capture_at_k와 동일한 경계 동점 기대값 처리를 독립 구현한다."""
    s = np.asarray(scores, float)
    yy = np.asarray(y, int)
    n = len(s)
    k = int(round(n * frac))
    if k <= 0 or yy.sum() == 0:
        return 0.0
    order = np.argsort(-s, kind="stable")
    thresh = s[order[k - 1]]
    above = s > thresh
    tie = s == thresh
    n_take_from_tie = k - int(above.sum())
    captured = float(yy[above].sum())
    if n_take_from_tie > 0 and tie.sum() > 0:
        captured += n_take_from_tie * (yy[tie].sum() / tie.sum())
    return float(captured / yy.sum())


def build_rows_independent(sm, split):
    """run_iter029_eval_c.build_table과 별도로, raw JSONL을 직접 읽어 부호를 적용한다."""
    all_patients = list(sm["patients"][split].values())
    patients = [p for p in all_patients if p["seed17_empty"]]
    sft = risk28.load_all(f"{RESULTS_ROOT}/{split}", "sft")
    base = risk28.load_all(f"{RESULTS_ROOT}/{split}", "base")
    rows = []
    for p in patients:
        pid = p["id"]
        ts = sft[(pid, "token_score")]
        pres_b, ptrue_b = sft[(pid, "presence")], sft[(pid, "ptrue")]
        pres_m, ptrue_m = base[(pid, "presence")], base[(pid, "ptrue")]
        # independent re-derivation straight from logit_yes/logit_no, not from stored risk_no_minus_yes
        presence_m0 = pres_m["logit_yes"] - pres_m["logit_no"]
        presence_b0 = pres_b["logit_yes"] - pres_b["logit_no"]
        ptrue_m0 = ptrue_m["logit_no"] - ptrue_m["logit_yes"]
        ptrue_b0 = ptrue_b["logit_no"] - ptrue_b["logit_yes"]
        seed_dis = ((not p["seed29_empty"]) + (not p["seed43_empty"])) / 2.0
        rows.append({
            "id": pid, "y": int(p["y_miss"]), "category": p["category"],
            "token_nll": ts["nll_bracket"], "token_nll_eos": (ts["nll_bracket"] + ts["nll_eos_step1"]) / 2.0,
            "entropy": ts["entropy_bracket"], "seed_disagreement": seed_dis,
            "presence_m0": presence_m0, "presence_b0": presence_b0,
            "ptrue_m0": ptrue_m0, "ptrue_b0": ptrue_b0,
        })
    return rows


SCORE_NAMES = ["token_nll", "token_nll_eos", "entropy", "seed_disagreement",
               "presence_m0", "presence_b0", "ptrue_m0", "ptrue_b0"]
TOKEN_FAMILY = ["token_nll", "token_nll_eos", "entropy"]
IMAGE_FAMILY = ["presence_m0", "presence_b0", "ptrue_m0", "ptrue_b0"]


def main():
    os.makedirs(OUT, exist_ok=True)
    sm = json.load(open(f"{RESULTS_ROOT}/source_manifest.json"))
    c_eval = json.load(open("results/iter_029/C_eval/c_eval.json"))
    e_eval = json.load(open("results/iter_029/E_eval/e_eval.json"))
    c_table_saved = json.load(open("results/iter_029/C_eval/c_table.json"))
    e_table_saved = json.load(open("results/iter_029/E_eval/e_table.json"))

    problems = []
    report = {}
    for split, saved_eval, saved_table in (("C", c_eval, c_table_saved), ("E", e_eval, e_table_saved)):
        rows = build_rows_independent(sm, split)
        y = [r["y"] for r in rows]
        n = len(rows)

        # cross-check independent rows against saved table (id-aligned, same values)
        saved_by_id = {r["id"]: r for r in saved_table}
        if set(saved_by_id) != {r["id"] for r in rows}:
            problems.append(f"{split}: independent id set != saved table id set")
        max_abs_diff = {}
        for name in SCORE_NAMES:
            diffs = [abs(r[name] - saved_by_id[r["id"]][name]) for r in rows]
            max_abs_diff[name] = max(diffs)
            if max_abs_diff[name] > 1e-9:
                problems.append(f"{split}/{name}: independent vs saved max abs diff {max_abs_diff[name]}")

        raw_auroc_indep = {name: rank_auroc([r[name] for r in rows], y) for name in SCORE_NAMES}
        capture20_indep = {name: capture_at_k_tiebreak_expected([r[name] for r in rows], y) for name in SCORE_NAMES}
        for name in SCORE_NAMES:
            d = abs(raw_auroc_indep[name] - saved_eval["raw_auroc"][name])
            if d > 1e-9:
                problems.append(f"{split}/{name}: independent AUROC {raw_auroc_indep[name]} vs saved "
                                 f"{saved_eval['raw_auroc'][name]} diff {d}")
            dc = abs(capture20_indep[name] - saved_eval["capture_at_20pct"][name])
            if dc > 1e-9:
                problems.append(f"{split}/{name}: independent capture20 {capture20_indep[name]} vs saved "
                                 f"{saved_eval['capture_at_20pct'][name]} diff {dc}")

        rep_T_indep = max(TOKEN_FAMILY, key=lambda k: raw_auroc_indep[k])
        rep_V_indep = max(IMAGE_FAMILY, key=lambda k: raw_auroc_indep[k])
        if split == "C":
            if rep_T_indep != saved_eval["representative_T"] or rep_V_indep != saved_eval["representative_V"]:
                problems.append(f"C: independent representative selection ({rep_T_indep},{rep_V_indep}) != "
                                 f"saved ({saved_eval['representative_T']},{saved_eval['representative_V']})")

        report[split] = {
            "n": n, "n_events": int(sum(y)),
            "raw_auroc_independent": raw_auroc_indep, "capture20_independent": capture20_indep,
            "max_abs_diff_vs_saved_table": max_abs_diff,
            "representative_T_independent": rep_T_indep, "representative_V_independent": rep_V_indep,
        }

    out = {"ok": len(problems) == 0, "problems": problems, "per_split": report}
    json.dump(out, open(os.path.join(OUT, "independent_verify.json"), "w"), indent=1)
    print(f"ok={out['ok']} n_problems={len(problems)}")
    for p in problems:
        print(" -", p)


if __name__ == "__main__":
    main()
