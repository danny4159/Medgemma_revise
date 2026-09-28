"""iter_029 계획의 Evaluation 기준으로 E 결과를 기계 판독 decision으로 정리한다.

기준(plan.md Evaluation 절 그대로):
- 단순 baseline 양성: E에서 고정 score가 AUROC>=0.75, 95% CI 하한>=0.65, Capture@20%>=0.50.
  token 또는 seed로 충족하면 confidence head/loss는 보류.
- 재질의 추가 정보 양성: C 선택 V-T AUROC 차이>=0.10, 97.5% CI 하한>0, Capture@20%도 같은 방향.
- 음성: 모든 score의 95% CI 상한이 실용 목표 미달.
- 불확정: CI가 기준을 가로지름.
"""
import json
import os

OUT = "results/iter_029/decide"


def main():
    e = json.load(open("results/iter_029/E_eval/e_eval.json"))
    c = json.load(open("results/iter_029/C_eval/c_eval.json"))
    verify = json.load(open(os.path.join(OUT, "independent_verify.json")))
    if not verify["ok"]:
        raise RuntimeError("independent verification failed; refusing to render a decision")

    rep_T, rep_V = e["representative_T"], e["representative_V"]

    simple_baseline_positive = {}
    for name in e["raw_auroc"]:
        if name == "random":
            continue
        auc = e["cis"][name]["auroc"]
        cap = e["cis"][name]["capture20"]
        pos = auc["point"] >= 0.75 and auc["lo"] >= 0.65 and cap["point"] >= 0.50
        simple_baseline_positive[name] = {
            "positive": pos, "auroc_point": auc["point"], "auroc_ci_lo": auc["lo"],
            "capture20_point": cap["point"],
        }
    token_or_seed_positive = simple_baseline_positive["entropy"]["positive"] or \
        simple_baseline_positive["token_nll"]["positive"] or \
        simple_baseline_positive["seed_disagreement"]["positive"]

    diff_VT_C = c["diff_V_minus_T_auroc"]
    v_minus_t_auroc_diff = e["raw_auroc"][rep_V] - e["raw_auroc"][rep_T]
    v_cap = e["capture_at_20pct"][rep_V]
    t_cap = e["capture_at_20pct"][rep_T]
    requery_positive = (diff_VT_C["point"] >= 0.10 and diff_VT_C["lo"] > 0.0 and v_cap > t_cap)

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

    decision = {
        "representative_T": rep_T, "representative_V": rep_V,
        "simple_baseline_positive_per_score": simple_baseline_positive,
        "token_or_seed_meets_simple_baseline_positive": token_or_seed_positive,
        "requery_additional_info_positive": {
            "positive": requery_positive,
            "C_diff_V_minus_T_point": diff_VT_C["point"], "C_diff_V_minus_T_ci_lo_975": diff_VT_C["lo"],
            "E_diff_V_minus_T_point": v_minus_t_auroc_diff,
            "E_capture20_V": v_cap, "E_capture20_T": t_cap,
        },
        "overall": overall,
        "notes": [
            "token_or_seed_positive=True는 entropy/token_nll/seed_disagreement 중 하나가 E에서 "
            "사전 목표를 충족함을 뜻하며, 계획에 따라 새 confidence head/loss 투자는 보류 대상이다.",
            "requery_positive=False는 presence_b0(교정된 V)가 C에서 사전 정한 추가 정보 이득 기준을 "
            "충족하지 못했다는 뜻이다(diff_V-T point는 음수).",
            "이 decision은 개발 자료(C/E)에서 나온 것이며 독립 확인(새 환자 집단)은 별도로 필요하다.",
        ],
    }
    json.dump(decision, open(os.path.join(OUT, "decision.json"), "w"), indent=1, ensure_ascii=False)
    print(json.dumps(decision, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
