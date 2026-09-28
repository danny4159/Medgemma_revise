"""iter_030 task 2: iter_029 decide의 결함을 새 경로에서만 교정한다 (원본 iter_029 파일/결과는 건드리지 않는다).

수정 대상 결함 (reuse manifest에 적힌 필요 검증):
1. run_iter029_decide.py의 requery_positive가 C의 95% CI(diff_V_minus_T_auroc, alpha 2.5/97.5)를 쓰면서
   E의 97.5% paired CI(diff_V_minus_T_auroc_975, alpha 1.25/98.75)를 쓴다는 계획 문구와 어긋난다.
   -> E의 diff_V_minus_T_auroc_975를 결정 기준에 사용한다.
2. token_or_seed_positive가 TOKEN_FAMILY(token_nll, token_nll_eos, entropy) 중 token_nll_eos를 빼고
   entropy/token_nll/seed_disagreement만 검사한다. -> token_nll_eos도 포함한다.
3. E/C report·raw output·calibration·독립 검증 digest를 연결해 입력이 같은 실행에서 나왔는지 확인한다.
4. 기존 경로 덮어쓰기 거부(이미 있으면 실패)를 유지한다.

이 스크립트는 results/iter_029/*의 기존 산출물을 읽기 전용으로만 사용하고, 새 파일은
results/iter_030/correction_029/에만 쓴다.
"""
import hashlib
import json
import os

OUT = "results/iter_030/correction_029"
E_EVAL_PATH = "results/iter_029/E_eval/e_eval.json"
C_EVAL_PATH = "results/iter_029/C_eval/c_eval.json"
VERIFY_PATH = "results/iter_029/decide/independent_verify.json"

TOKEN_FAMILY = ["token_nll", "token_nll_eos", "entropy"]


def sha256_file(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def decide(e, c, verify):
    if not verify["ok"]:
        raise RuntimeError("independent verification failed; refusing to render a corrected decision")

    rep_T, rep_V = e["representative_T"], e["representative_V"]
    if rep_T != c["representative_T"] or rep_V != c["representative_V"]:
        raise RuntimeError(f"C/E representative mismatch: C={(c['representative_T'], c['representative_V'])} "
                            f"E={(rep_T, rep_V)}")

    simple_baseline_positive = {}
    for name in e["raw_auroc"]:
        if name == "random":
            continue
        auc = e["cis"][name]["auroc"]
        cap = e["cis"][name]["capture20"]
        pos = auc["point"] >= 0.75 and auc["lo"] >= 0.65 and cap["point"] >= 0.50
        simple_baseline_positive[name] = {"positive": pos, "auroc_point": auc["point"], "auroc_ci_lo": auc["lo"],
                                          "capture20_point": cap["point"]}
    # 수정 1: 계획된 TOKEN_FAMILY 전체(token_nll_eos 포함)를 검사한다.
    token_or_seed_positive = any(simple_baseline_positive[name]["positive"]
                                 for name in TOKEN_FAMILY + ["seed_disagreement"])

    # 수정 2: E의 97.5% paired CI(diff_V_minus_T_auroc_975)를 결정 기준으로 쓴다 (C의 95% CI가 아니다).
    diff_VT_E975 = e["diff_V_minus_T_auroc_975"]
    v_cap = e["capture_at_20pct"][rep_V]
    t_cap = e["capture_at_20pct"][rep_T]
    requery_positive = (diff_VT_E975["point"] >= 0.10 and diff_VT_E975["lo"] > 0.0 and v_cap > t_cap)

    all_ci_upper_below_target = all(
        (e["cis"][name]["auroc"]["hi"] < 0.75) and (e["cis"][name]["capture20"]["hi"] < 0.50)
        for name in e["raw_auroc"] if name != "random"
    )
    any_ci_straddles = any(
        (e["cis"][name]["auroc"]["lo"] < 0.75 < e["cis"][name]["auroc"]["hi"])
        for name in e["raw_auroc"] if name != "random"
    )

    if token_or_seed_positive:
        overall = "simple_baseline_positive_new_confidence_head_deferred"
    elif all_ci_upper_below_target:
        overall = "negative_limited_to_current_score_set"
    elif any_ci_straddles:
        overall = "inconclusive_ci_straddles_target"
    else:
        overall = "mixed"

    return {
        "representative_T": rep_T, "representative_V": rep_V,
        "simple_baseline_positive_per_score": simple_baseline_positive,
        "token_or_seed_meets_simple_baseline_positive": token_or_seed_positive,
        "token_family_checked": TOKEN_FAMILY + ["seed_disagreement"],
        "requery_additional_info_positive": {
            "positive": requery_positive,
            "E_diff_V_minus_T_975_point": diff_VT_E975["point"], "E_diff_V_minus_T_975_ci_lo": diff_VT_E975["lo"],
            "E_capture20_V": v_cap, "E_capture20_T": t_cap,
        },
        "overall": overall,
        "corrects": [
            "run_iter029_decide.py used C's 95% CI (diff_V_minus_T_auroc) despite the plan requiring E's "
            "97.5% paired CI (diff_V_minus_T_auroc_975) for the decision gate.",
            "run_iter029_decide.py's token_or_seed_positive omitted token_nll_eos from TOKEN_FAMILY.",
        ],
        "note": "이 decision은 results/iter_029의 기존 GPU 출력·통계를 그대로 재사용하며 새 generation은 없다. "
                "여전히 개발 자료(C/E)이며 독립 확인이 아니다.",
    }


def main():
    out_decision = os.path.join(OUT, "decision.json")
    if os.path.exists(out_decision):
        raise RuntimeError(f"refusing to overwrite existing {out_decision}")
    os.makedirs(OUT, exist_ok=True)

    e = json.load(open(E_EVAL_PATH))
    c = json.load(open(C_EVAL_PATH))
    verify = json.load(open(VERIFY_PATH))

    corrected = decide(e, c, verify)
    provenance = {
        "e_eval_sha256": sha256_file(E_EVAL_PATH), "c_eval_sha256": sha256_file(C_EVAL_PATH),
        "independent_verify_sha256": sha256_file(VERIFY_PATH),
        "e_eval_path": E_EVAL_PATH, "c_eval_path": C_EVAL_PATH, "verify_path": VERIFY_PATH,
    }
    out = {"decision": corrected, "input_provenance": provenance}
    json.dump(out, open(out_decision, "w"), indent=1, ensure_ascii=False)
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
