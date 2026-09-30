"""iter_040 단계 decision artifact 생성 (사전 규칙, 결과를 보고 규칙을 바꾸지 않는다). 기존 decision 파일은 덮어쓰지 않는다.

  ext     : V48 epoch2/5 F1@0.3·V48 CE로 epoch8 연장 여부
  select  : V48 평가된 (LR, epoch) 중 B 선택 (F1@0.3 -> F1@0.5 -> 낮은 invalid -> 이른 epoch)
  bgate   : B의 V96 valid/truncation gate와 대조 적용 가능성
  ratio   : 사전 측정한 M/C 학습 시간 비율 r -> C_compute update 수
  cost    : M과 C_compute의 실제 누적 학습 시간 비교 (5% 규칙) -> 추가 update 수
  v96     : M-C, M-C_compute 판정 (guardrail 포함) -> H192 run 여부
"""
import argparse
import glob
import json
import math
import os
import sys

import numpy as np

Z975 = 2.2414027276  # 양측 97.5% (percentile CI의 정규 근사 반폭 계수)


def load(p):
    return json.load(open(p))


def save(path, obj):
    if os.path.exists(path):
        sys.exit(f"decision exists: {path}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + f".{os.getpid()}.tmp"
    json.dump(obj, open(tmp, "w"), indent=1)
    os.replace(tmp, path)
    print(json.dumps(obj, indent=1)[:3000])


def f1(rep, name):
    return rep["models"][name]["summary"]["f1_03"][0]


def cmd_ext(a):
    rep = load(a.v48)
    out = {"rule": "each LR: (F1@0.3 epoch5 - epoch2 >= 0.02) and (V48 CE epoch5 <= 0.95*epoch2). If ANY LR satisfies, both LRs are extended once to epoch 8 "
                   "(interpretation of 'each LR ... both LRs extend': recorded before results)", "per_lr": {}}
    for lr in a.lrs:
        e2, e5 = f1(rep, f"lr{lr}_e2"), f1(rep, f"lr{lr}_e5")
        c2 = load(f"results/iter_040/train2/B_lr{lr}_s17/epoch_02/valce.json")["val_ce_V48"]
        c5 = load(f"results/iter_040/train2/B_lr{lr}_s17/epoch_05/valce.json")["val_ce_V48"]
        out["per_lr"][lr] = {"f1_e2": e2, "f1_e5": e5, "d_f1": e5 - e2, "ce_e2": c2, "ce_e5": c5, "ce_ratio": c5 / c2,
                             "criterion_met": bool(e5 - e2 >= 0.02 and c5 <= 0.95 * c2)}
    out["extend"] = any(v["criterion_met"] for v in out["per_lr"].values())
    save(a.out, out)


def cmd_select(a):
    rep = load(a.v48)
    cands = []
    for lr in a.lrs:
        for e in a.epochs:
            n = f"lr{lr}_e{e}"
            if n in rep["models"]:
                s = rep["models"][n]["summary"]
                cands.append({"name": n, "lr": lr, "epoch": e, "f1_03": s["f1_03"][0], "f1_05": s["f1_05"][0], "invalid": s["invalid_rate"]})
    cands.sort(key=lambda c: (-round(c["f1_03"], 12), -round(c["f1_05"], 12), c["invalid"], c["epoch"]))
    best = cands[0]
    rising = None
    if any(c["epoch"] == 8 for c in cands):
        e5 = next(c for c in cands if c["lr"] == best["lr"] and c["epoch"] == 5)
        e8 = next(c for c in cands if c["lr"] == best["lr"] and c["epoch"] == 8)
        rising = bool(e8["f1_03"] - e5["f1_03"] >= 0.02)
    out = {"selected": best, "adapter_dir": f"results/iter_040/train2/B_lr{best['lr']}_s17/epoch_{best['epoch']:02d}", "all_candidates": cands,
           "baseline_still_rising_after_extension": rising,
           "note": "selection on V48 (development, not independent); ties: F1@0.5, lower invalid, earlier epoch"}
    save(a.out, out)


def cmd_bgate(a):
    rep = load(a.v96)
    s = rep["models"]["B"]["summary"]
    valid = 1 - s["invalid_rate"]
    tr = s["unresolved_truncation_rate"]
    man = [json.loads(l) for l in open("results/iter_040/data/manifest_train_private.jsonl")]
    n_el = sum(r["contrast_eligible"] for r in man)
    out = {"B_valid_rate": valid, "B_unresolved_truncation": tr, "valid_ge_0.95": valid >= 0.95, "truncation_le_0.02": tr <= 0.02,
           "contrast_eligible_patients": n_el, "contrast_applicable": n_el > 0,
           "proceed_to_M_C": bool(valid >= 0.95 and tr <= 0.02 and n_el > 0), "B_v96": {"f1_03": s["f1_03"], "f1_05": s["f1_05"]}}
    save(a.out, out)


def cmd_ratio(a):
    def steps(d):
        return [json.loads(l) for l in open(os.path.join(d, "train_log.jsonl")) if '"event": "step"' in l]
    c, m = steps(a.c_dir), steps(a.m_dir)
    tc, tm = [x["step_time_s"] for x in c][1:], [x["step_time_s"] for x in m][1:]
    r = sum(tm) / sum(tc)
    tokr = sum(x["fwd_tokens"] for x in m) / sum(x["fwd_tokens"] for x in c)
    m_updates = a.m_updates
    out = {"r_time": r, "r_time_median": float(np.median(tm) / np.median(tc)), "r_tokens": tokr, "n_steps_used_each": len(tc), "excluded": "first step (warmup)",
           "source": {"C": a.c_dir, "M": a.m_dir, "note": "same T rows (first 64 patients by PatientID order), same GPU, mb=2, run sequentially before exploration"},
           "M_updates": m_updates, "C_compute_total_updates": math.ceil(r * m_updates), "rule": "ceil(r * M_updates) applied to the total updates after B"}
    save(a.out, out)


def train_time(run_dir, upto_step=None):
    xs = [json.loads(l) for l in open(os.path.join(run_dir, "train_log.jsonl")) if '"event": "step"' in l]
    byk = {}
    for x in xs:
        byk[x["step"]] = x  # 재개 시 중복 step은 마지막 기록
    xs = [byk[k] for k in sorted(byk) if upto_step is None or k <= upto_step]
    return {"n_steps": len(xs), "train_time_s": sum(x["step_time_s"] for x in xs), "fwd_tokens": sum(x["fwd_tokens"] for x in xs)}


def cmd_cost(a):
    tm, tc = train_time(a.m_dir), train_time(a.c_dir)
    ratio = tc["train_time_s"] / tm["train_time_s"]
    need = None
    if ratio < 0.95:
        per = tc["train_time_s"] / tc["n_steps"]
        need = math.ceil((tm["train_time_s"] - tc["train_time_s"]) / per)
    out = {"M": tm, "C_compute_so_far": tc, "C_over_M_time": ratio, "within_5pct": abs(ratio - 1) <= 0.05,
           "extra_C_updates_needed_if_cheaper_by_more_than_5pct": need,
           "rule": "if C_compute is cheaper than M by >=5%, extend C by update units; if C is costlier, keep and mark conservative"}
    save(a.out, out)


def cmd_v96(a):
    rep = load(a.v96)
    P = rep["pairs"]
    dC, dK = P["M:C"], P["M:C_compute"]
    M, C, K = (rep["models"][n]["summary"] for n in ("M", "C", "C_compute"))
    tM, tC, tK = train_time(a.m_dir), train_time(a.c_dir, a.m_updates), train_time(a.c_dir)
    inf = {"M_generate_s": M["cost"]["mean_generate_s_per_request"], "C_generate_s": C["cost"]["mean_generate_s_per_request"],
           "ratio": M["cost"]["mean_generate_s_per_request"] / C["cost"]["mean_generate_s_per_request"]}
    tr = {"M_time_s": tM["train_time_s"], "C_time_s": tC["train_time_s"], "C_compute_time_s": tK["train_time_s"],
          "M_over_C": tM["train_time_s"] / tC["train_time_s"], "C_compute_over_M": tK["train_time_s"] / tM["train_time_s"]}
    res = {}
    for nm, d in (("M-C", dC), ("M-C_compute", dK)):
        res[nm] = {"f1_03_diff": d["f1_03"]["diff_mean_ci975"][0], "ci975": d["f1_03"]["diff_mean_ci975"][1:], "ci95": d["f1_03"]["diff_mean_ci95"][1:],
                   "f1_05_diff": d["f1_05"]["diff_mean_ci95"][0], "fp_per_sentence_diff": d["fp_per_sentence_diff"],
                   "invalid_diff_pp": d["invalid_rate_diff_pp"], "trunc_diff_pp": d["truncation_rate_diff_pp"], "sd_paired": d["f1_03"]["sd_paired"]}
    g = {"f1_05_loss_le_0.02": all(r["f1_05_diff"] >= -0.02 for r in res.values()),
         "fp_increase_le_0.05": all(r["fp_per_sentence_diff"] <= 0.05 for r in res.values()),
         "invalid_trunc_increase_lt_2pp": all(r["invalid_diff_pp"] < 2 and r["trunc_diff_pp"] < 2 for r in res.values()),
         "inference_cost_le_1.10": inf["ratio"] <= 1.10, "train_cost_le_3x_C": tr["M_over_C"] <= 3.0}
    g["all"] = all(g.values())
    diffs = [r["f1_03_diff"] for r in res.values()]
    lo_min = min(r["ci975"][0] for r in res.values())
    small = min(diffs)
    cond_h = bool(all(d > 0 for d in diffs) and small >= 0.025 and all(r["ci975"][1] >= 0.05 for r in res.values()))
    clear_pos = bool(all(d >= 0.05 for d in diffs) and all(r["ci975"][0] > 0 for r in res.values()) and g["all"])
    hw = max(Z975 * r["sd_paired"] / math.sqrt(192) for r in res.values())
    negative = bool(any(r["ci975"][1] < 0.05 for r in res.values()) or res["M-C_compute"]["f1_03_diff"] <= 0)
    run = bool(g["all"] and (clear_pos or cond_h) and hw <= 0.05)
    out = {"V96": res, "guardrails": g, "inference_cost": inf, "train_cost": tr, "condition_for_H192": cond_h, "clear_positive_on_V96": clear_pos,
           "projected_ci975_halfwidth_H192_n192": hw, "halfwidth_le_0.05": hw <= 0.05, "negative_by_ci_upper_lt_0.05_or_no_gain": negative, "run": run,
           "classification": "clear_positive" if clear_pos else ("negative" if negative else ("run_H192_for_precision" if run else
                                                                                                        ("inconclusive_guardrail_fail" if not g["all"] else "inconclusive_no_H192"))),
           "rule": "run iff guardrails pass and (clear positive or [both diffs>0, smaller>=0.025, both CI975 upper>=0.05]) and projected H192 CI975 half-width<=0.05",
           "note": "V96 is development data incl. model selection; H192 (if run) is a separate report"}
    save(a.out, out)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("ext", "select", "bgate", "ratio", "cost", "v96"):
        s = sub.add_parser(n)
        s.add_argument("--out", required=True)
    sub.choices["ext"].add_argument("--v48", required=True)
    sub.choices["ext"].add_argument("--lrs", nargs="+", default=["1e-4", "2e-4"])
    sub.choices["select"].add_argument("--v48", required=True)
    sub.choices["select"].add_argument("--lrs", nargs="+", default=["1e-4", "2e-4"])
    sub.choices["select"].add_argument("--epochs", nargs="+", type=int, default=[2, 5, 8])
    sub.choices["bgate"].add_argument("--v96", required=True)
    sub.choices["ratio"].add_argument("--c-dir", required=True)
    sub.choices["ratio"].add_argument("--m-dir", required=True)
    sub.choices["ratio"].add_argument("--m-updates", type=int, default=117)
    sub.choices["cost"].add_argument("--m-dir", required=True)
    sub.choices["cost"].add_argument("--c-dir", required=True)
    sub.choices["v96"].add_argument("--v96", required=True)
    sub.choices["v96"].add_argument("--m-dir", required=True)
    sub.choices["v96"].add_argument("--c-dir", required=True, help="C 학습 run (update m-updates까지가 C, 전체가 C_compute)")
    sub.choices["v96"].add_argument("--m-updates", type=int, default=117)
    a = ap.parse_args()
    {"ext": cmd_ext, "select": cmd_select, "bgate": cmd_bgate, "ratio": cmd_ratio, "cost": cmd_cost, "v96": cmd_v96}[a.cmd](a)


if __name__ == "__main__":
    main()
