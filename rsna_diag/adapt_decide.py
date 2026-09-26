"""iter_013 사전 고정 판정 규칙 (report.json -> decision.json). 결과를 본 뒤 규칙을 바꾸지 않는다. 사용: python -m rsna_diag.adapt_decide explore|full --report R --out O

explore -> 확대: D(선택 checkpoint, V400)가 C(선택 checkpoint)보다 S_loc 0.03 이상 높고 D의 V400 guardrail을 통과하면 확대.
  점추정이 0.03 미만이어도 paired 95% CI 상한 >= 0.03 이고 D의 V200 마지막 구간(epoch2->3) S_loc 개선 >= 0.01이면 한 번 확대.
  C에 통과 checkpoint가 없으면 C의 (guardrail 무시) 최고 S_loc를 기준으로 삼는다 (D에 불리한 보수적 기준).
full  -> seed 재현: 각 조건의 LR·checkpoint를 V200 선택 예산(2 LR x 3 milestone)에서 고른 뒤, D가 가장 강한 C보다 0.03 이상, 같은 설정 H보다 0.01 이상 높고
  guardrail 통과면 seed29/43 재현으로 진행. 이득이 C 또는 H로 설명되면 D의 다중 seed 확대를 중단한다.
"""
import argparse
import json
import os

from . import adapt_eval as AE, select as SEL


def best_s_loc(t, prefer="selected"):
    """trajectory entry -> (S_loc, tag, entry) of the selected (또는 없으면 final) checkpoint."""
    e = t.get(prefer) or t.get("final")
    return e["v400"]["S_loc"], (prefer if t.get(prefer) else "final"), e


def decide_explore(rep):
    tr = rep["trajectories"]
    C, D, H = tr.get("C@2e-05"), tr.get("D@2e-05"), tr.get("H@2e-05")
    out = {"rule": __doc__.split("\n")[2:5]}
    if not (C and D):
        return {"error": "C or D trajectory missing"}
    cs, ctag, ce = best_s_loc(C)
    ds, dtag, de = best_s_loc(D)
    ci = rep["pairwise_v400_paired_bootstrap"]["selected"].get("D@2e-05-C@2e-05")
    d_guard = bool(D.get("selected")) and D["selected"]["guardrail_v400"]["ok"]
    v = D["v200_detail_by_epoch"]
    last_gain = v["3"]["S_loc"] - v["2"]["S_loc"]
    expand, reason = AE.expand_rule(ds, cs, ci, last_gain, d_guard)
    out.update({"C_selected_S_loc": cs, "C_tag": ctag, "D_selected_S_loc": ds, "D_tag": dtag, "D_minus_C": ds - cs, "paired_ci_D_minus_C": ci,
                "D_v200_last_interval_gain": last_gain, "D_guardrail_v400_ok": d_guard, "expand": expand, "reason": reason})
    if H:
        hs, htag, _ = best_s_loc(H)
        out["H_selected_S_loc"] = hs
        out["H_minus_C"] = hs - cs
        out["D_minus_H"] = ds - hs
    out["final_checkpoint_S_loc"] = {k: (t["final"]["v400"]["S_loc"] if t.get("final") else None) for k, t in tr.items()}
    out["B0_S_loc_v400"] = rep["b0"]["v400"]["S_loc"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["explore"])
    ap.add_argument("--report", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rep = json.load(open(a.report))
    dec = {"mode": a.mode, "report": a.report, "report_sha256": SEL.file_sha(a.report), "decision": decide_explore(rep)}
    print(SEL.write_or_verify(a.out, json.loads(json.dumps(dec))), json.dumps(dec["decision"], indent=1)[:1500])


if __name__ == "__main__":
    main()
