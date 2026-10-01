"""iter_048 사전 판정 규칙 (plan.md Evaluation을 결과 전에 코드로 고정; 결과를 보고 바꾸지 않는다). CPU.

recovered   : M1(J_J-E_J) mean>=0.10 & 97.5% CI lo>0  AND  M2((E_I-E_J)-(J_I-J_J)) mean>=0.10 & 97.5% CI lo>0  AND  (J_I-E_I) F1@0.3 95% CI lo >= -0.03
sufficient  : J_AB와 J_BA 각각의 (E_I 대비) F1@0.3 97.5% CI lo>=-0.03, F1@0.5 95% CI lo>=-0.03, FP/문장 95% CI hi<=0.10 (모두)
residual    : (J_I - J_J) mean>=0.05 & 95% CI lo>0
adv(X)      : (X - A) F1@0.3 mean>=0.05 & 97.5% CI lo>0, F1@0.5 95% CI lo>=-0.03, FP 95% CI hi<=0.10
cost_opp    : J/E device-seconds ratio 95% CI hi<=0.80 & throughput ratio 95% CI lo>=1.25 & p95 latency ratio 95% CI hi<=1.20
outcome     : recovered&sufficient -> recovered_and_preserved / else residual -> residual_joint_loss / else indeterminate_format_effect
next        : recovered_and_preserved -> 별도 공동 loss 투자 종료 (adv(J_J)&cost_opp면 독립 확인 가치 검토)
              residual_joint_loss -> adv(E_I)&cost_opp면 최소 방법 pilot 가치를 다음 리뷰에서 판단, 아니면 보류
              indeterminate -> 비교 종료 (추가 표본/seed/prompt/timing 없음). adv(E_I)와 adv(J_J)가 모두 거짓이면 MG 대비 필요한 이점 미확보로 공동 grounding 추가 방법 투자 보류.
적용 범위: 두 양성 문장, T305 단일 seed, 개발 V96. 신규성/내부 원인/임상 일반화 판정이 아니다.
python pg48_decide.py --report R --timing T --out OUT
"""
import argparse
import hashlib
import json
import os
import sys


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def decide(rep, timing):
    c = rep["compare"]
    M1, M2 = c["M1_J_J_minus_E_J"]["f1_03_ci975"], c["M2_loss_reduction_(E_I-E_J)-(J_I-J_J)"]["f1_03_ci975"]
    JIE = c["J_I_minus_E_I"]["f1_03"]["ci95"]
    rec = {"M1_mean>=0.10": M1["mean"] >= 0.10, "M1_lo>0": M1["lo"] > 0, "M2_mean>=0.10": M2["mean"] >= 0.10, "M2_lo>0": M2["lo"] > 0, "J_I-E_I_lo95>=-0.03": JIE["lo"] >= -0.03}
    recovered = all(rec.values())
    suff = {}
    for o in ("AB", "BA"):
        cc = c[f"J_{o}_minus_E_I"]
        suff[o] = {"f1_03_lo975>=-0.03": cc["f1_03_ci975"]["lo"] >= -0.03, "f1_05_lo95>=-0.03": cc["f1_05_ci95"]["lo"] >= -0.03, "fp_hi95<=0.10": cc["fp_03_ci95"]["hi"] <= 0.10}
    sufficient = all(v for d in suff.values() for v in d.values())
    jl = c["J_loss_J_I_minus_J_J"]["f1_03_ci95"]
    residual = jl["mean"] >= 0.05 and jl["lo"] > 0

    def adv(name):
        cc = c[f"{name}_minus_A"]
        d = {"f1_03_mean>=0.05": cc["f1_03_ci975"]["mean"] >= 0.05, "f1_03_lo975>0": cc["f1_03_ci975"]["lo"] > 0, "f1_05_lo95>=-0.03": cc["f1_05_ci95"]["lo"] >= -0.03,
             "fp_hi95<=0.10": cc["fp_03_ci95"]["hi"] <= 0.10}
        return all(d.values()), d
    advE, advE_d = adv("E_I")
    advJ, advJ_d = adv("J_J")
    r = timing["ratios"]["J/E"]
    cost = {"device_hi95<=0.80": r["device_seconds"]["hi95"] <= 0.80, "throughput_lo95>=1.25": r["throughput"]["lo95"] >= 1.25, "p95_hi95<=1.20": r["p95_latency"]["hi95"] <= 1.20}
    cost_opp = all(cost.values())
    outcome = "recovered_and_preserved" if (recovered and sufficient) else ("residual_joint_loss" if residual else "indeterminate_format_effect")
    hold_mg = not (advE or advJ)
    if outcome == "recovered_and_preserved":
        nxt = "close separate joint-loss investment" + ("; review independent confirmation (J_J advantage over A and cost opportunity both met)" if (advJ and cost_opp) else "")
    elif outcome == "residual_joint_loss":
        nxt = "next review judges minimal method pilot value (E_I advantage over A and J cost opportunity both met)" if (advE and cost_opp) else "hold joint grounding method investment"
    else:
        nxt = "close this comparison (no more samples/seeds/prompts/timing); preserve observations"
    return {"outcome": outcome, "recovered": recovered, "recovered_conditions": rec, "sufficient": sufficient, "sufficient_conditions": suff, "residual": residual,
            "residual_stat": jl, "adv_E_I_over_A": advE, "adv_E_I_detail": advE_d, "adv_J_J_over_A": advJ, "adv_J_J_detail": advJ_d, "cost_opportunity_J_over_E": cost_opp, "cost_detail": cost,
            "hold_no_required_advantage_over_MG": hold_mg, "next_investment": nxt,
            "scope": "two positive sentences, T305 single seed, development V96; not novelty/internal-cause/clinical generalization"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--timing", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("exists")
    d = decide(json.load(open(a.report)), json.load(open(a.timing)))
    d["input_digests"] = {"report_sha256": sha(a.report), "timing_sha256": sha(a.timing), "decide_source_sha256": sha("pg48_decide.py")}
    json.dump(d, open(a.out, "w"), indent=1)
    print(json.dumps({k: d[k] for k in ("outcome", "recovered", "sufficient", "residual", "adv_E_I_over_A", "adv_J_J_over_A", "cost_opportunity_J_over_E", "hold_no_required_advantage_over_MG", "next_investment")}, indent=1))


if __name__ == "__main__":
    main()
