"""iter_021 실행 오케스트레이터: D8 동작 확인 -> gate 판정 -> E48 가능성 탐색 -> F 확대 판정(조건부).
계획의 stage gate(D 통과 후에만 E, E decision 후에만 F)를 강제한다. 실행 인자 없이 그대로
`python run_iter021.py`로 실행하며, 이미 완료된 stage는 mi19_pipeline.run_split의 재사용
검증(요청 내용 대조 + protocol 재검증 + completion.json 존재)을 통해 안전하게 건너뛴다.
"""
import json
import math
import os
import sys

from rsna_diag import mi19_pipeline as PL

RUN_ROOT = PL.RUN_ROOT
GPUS = "0,1"


def d_gate_check(report):
    ok = True
    reasons = []
    for c in ("J_RT", "J_TR", "O"):
        fs = report["format_stats"][c]
        if fs["valid_rate"] < 0.95:
            ok = False
            reasons.append(f"{c} valid_rate {fs['valid_rate']:.4f} < 0.95")
        if fs["cap_rate"] > 0.05:
            ok = False
            reasons.append(f"{c} cap_rate {fs['cap_rate']:.4f} > 0.05")
    return ok, reasons


def wilson(k, n, z=1.959963984540054):
    if n == 0:
        return [float("nan"), float("nan")]
    p = k / n
    denom = 1 + z * z / n
    center = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [(center - half) / denom, (center + half) / denom]


def f_expand_check(report_e, n_f_available):
    """계획 5단계의 F 확대 4개 조건. 반환: (expand:bool, reasons:list[str])."""
    reasons = []
    o_pair = report_e["pair_success"]["O"]["rate"]
    if not (o_pair >= 0.75):
        reasons.append(f"O pair_success {o_pair:.4f} < 0.75 (gate fails)")
    strong_baseline = any(report_e["pair_success"][c]["rate"] >= 0.90 for c in ("C", "N", "S2"))
    if strong_baseline:
        reasons.append("C/N/S2 중 하나 이상 pair_success>=0.90 (단순 해결 경로 보존, F 열지 않음)")
    if n_f_available < 64:
        reasons.append(f"F available {n_f_available} < 64")
    h = report_e["H"]
    k, n = h["k"], h["n"]
    h_rate = h["H"]
    wilson_e = h["wilson_95"]
    size_ok = False
    if h_rate >= 0.15:
        size_ok = True
    else:
        if wilson_e[1] >= 0.15:
            # 예상 F Wilson 반폭 <= 0.10 및 E 반폭의 80% 이하 (예상 p=(k+0.5)/49)
            p_hat = (k + 0.5) / 49.0
            nf = min(n_f_available, 12 * n_f_available)  # F 규모는 12*nF 호출이지만 H는 환자 단위이므로 n_f_available명 기준
            wf = wilson(round(p_hat * nf), nf)
            half_f = (wf[1] - wf[0]) / 2
            half_e = (wilson_e[1] - wilson_e[0]) / 2
            if half_f <= 0.10 and half_f <= 0.80 * half_e:
                size_ok = True
            else:
                reasons.append(f"H_E<0.15 and predicted F half-width {half_f:.4f} fails (<=0.10 and <=80% of E half-width {half_e:.4f})")
        else:
            reasons.append(f"H_E={h_rate:.4f}<0.15 and Wilson upper {wilson_e[1]:.4f}<0.15")
    if not size_ok:
        pass  # already recorded reason above
    expand = (not reasons) and size_ok
    # size_ok already folds into reasons when False; recompute overall expand cleanly:
    expand = (o_pair >= 0.75) and (not strong_baseline) and (n_f_available >= 64) and size_ok
    return expand, reasons


def main():
    os.makedirs(RUN_ROOT, exist_ok=True)
    decisions = {}

    print("=== STAGE D8 ===", flush=True)
    resD, phase1D, s2D, manifest, pidsD = PL.run_split("D", workers=2, peak_gb=10, gpus=GPUS)
    okD = all(v["rc"] == 0 for v in resD.values())
    if not okD:
        json.dump({"stage": "D", "run": resD, "status": "generation_failed"},
                  open(f"{RUN_ROOT}/report_D_run_status.json", "w"), indent=1, default=str)
        print(json.dumps({"stage": "D", "status": "generation_failed", "run": resD}, indent=1, default=str))
        sys.exit(2)
    reportD, evD = PL.evaluate_split("D", phase1D, s2D, manifest, pidsD)
    json.dump({"report": reportD}, open(f"{RUN_ROOT}/report_D.json", "w"), indent=1, default=str)
    json.dump(evD, open(f"{RUN_ROOT}/eval_raw_D.json", "w"), indent=1, default=str)
    gateD_ok, gateD_reasons = d_gate_check(reportD)
    decisions["D"] = {"gate_ok": gateD_ok, "reasons": gateD_reasons, "format_stats": reportD["format_stats"]}
    json.dump(decisions["D"], open(f"{RUN_ROOT}/decision_D.json", "w"), indent=1, default=str)
    print(json.dumps({"stage": "D", "gate_ok": gateD_ok, "reasons": gateD_reasons}, indent=1, default=str))
    if not gateD_ok:
        print("D gate FAILED; not proceeding to E per plan (E 결과로 prompt/parser를 조정하지 않는다).")
        sys.exit(3)

    print("=== STAGE E48 ===", flush=True)
    resE, phase1E, s2E, manifestE, pidsE = PL.run_split("E", workers=2, peak_gb=10, gpus=GPUS)
    okE = all(v["rc"] == 0 for v in resE.values())
    if not okE:
        json.dump({"stage": "E", "run": resE, "status": "generation_failed"},
                  open(f"{RUN_ROOT}/report_E_run_status.json", "w"), indent=1, default=str)
        print(json.dumps({"stage": "E", "status": "generation_failed", "run": resE}, indent=1, default=str))
        sys.exit(4)
    reportE, evE = PL.evaluate_split("E", phase1E, s2E, manifestE, pidsE)
    json.dump({"report": reportE}, open(f"{RUN_ROOT}/report_E.json", "w"), indent=1, default=str)
    json.dump(evE, open(f"{RUN_ROOT}/eval_raw_E.json", "w"), indent=1, default=str)

    split_map = json.load(open(f"{PL.DATA_DIR}/split.json"))
    n_f_available = len(split_map["F"])
    expand, reasons = f_expand_check(reportE, n_f_available)
    decision_f = {"expand_F": expand, "reasons": reasons, "n_f_available": n_f_available,
                  "H_E": reportE["H"], "pair_success_E": {c: reportE["pair_success"][c]["rate"] for c in reportE["pair_success"]}}
    json.dump(decision_f, open(f"{RUN_ROOT}/decision_F.json", "w"), indent=1, default=str)
    print(json.dumps({"stage": "F_decision", **decision_f}, indent=1, default=str))

    if not expand:
        print("F 확대 조건 미충족: F 보존, 이번 반복은 E까지로 종료.")
        return

    print("=== STAGE F (conditional) ===", flush=True)
    resF, phase1F, s2F, manifestF, pidsF = PL.run_split("F", workers=2, peak_gb=10, gpus=GPUS)
    okF = all(v["rc"] == 0 for v in resF.values())
    if not okF:
        json.dump({"stage": "F", "run": resF, "status": "generation_failed"},
                  open(f"{RUN_ROOT}/report_F_run_status.json", "w"), indent=1, default=str)
        print(json.dumps({"stage": "F", "status": "generation_failed", "run": resF}, indent=1, default=str))
        sys.exit(5)
    reportF, evF = PL.evaluate_split("F", phase1F, s2F, manifestF, pidsF)
    json.dump({"report": reportF}, open(f"{RUN_ROOT}/report_F.json", "w"), indent=1, default=str)
    json.dump(evF, open(f"{RUN_ROOT}/eval_raw_F.json", "w"), indent=1, default=str)
    print(json.dumps({"stage": "F", "H": reportF["H"]}, indent=1, default=str))


if __name__ == "__main__":
    main()
