"""iter_053 사전 판정 (plan.md Proposed Experiment §4 / Evaluation을 코드로 고정). 결과를 보고 문턱을 바꾸지 않는다.

python rr53_decide.py E --report R --verify V --protocol P --out DEC        # E -> F 진입 여부 (run=true일 때만 F protocol 허용)
python rr53_decide.py F --report R --verify V --protocol P --e-decision DEC_E --out DEC
순수 함수 decide_e / decide_f는 report dict(와 manifest 층 크기)만 입력으로 받는다.
"""
import argparse
import json
import math
import os
import sys

import numpy as np

from rr53_data import OUT, file_sha

R_GOAL, HFAIL_GOAL = 0.80, 0.05
ACC_GAIN, R_TRADE, HFAIL_TRADE = 0.10, 0.15, 0.05
HALF_R, HALF_HFAIL = 0.10, 0.05
T975 = 2.242  # 계획의 근사 계수
SIMPLE = ["R1", "R2", "BJ", "BI"]
MIN_VALID = 0.95
CONDS_VALID = ("R1", "R2", "T", "BJ", "BT", "BI")


def sufficient(c):
    """동시 보정 구간(또는 퇴화 시 exact 경계)으로 r 하한>=0.80 및 h_fail 상한<=0.05."""
    r, h = c["r"], c["h_fail"]
    r_lo = 1 - r["degenerate_exact"]["any_event_patient_fraction_upper"] if r.get("degenerate_exact") else r["simult_lo"]
    h_hi = h["degenerate_exact"]["any_event_patient_fraction_upper"] if h.get("degenerate_exact") else h["simult_hi"]
    return bool(r_lo >= R_GOAL and h_hi <= HFAIL_GOAL), dict(r_lower=r_lo, hfail_upper=h_hi)


def misses_goal(c):
    """동시 보정한 r 상한<0.80 또는 h_fail 하한>0.05."""
    r, h = c["r"], c["h_fail"]
    return bool(r["simult_hi"] < R_GOAL or h["simult_lo"] > HFAIL_GOAL), dict(r_upper=r["simult_hi"], hfail_lower=h["simult_lo"])


def run_valid(report, verify):
    ok = verify.get("passed") is True and report["n_non_eos_final"] == 0 and all(report["valid_rate_by_cond"][c] >= MIN_VALID for c in CONDS_VALID)
    return bool(ok)


def expected_half_width(per_patient, f_sizes, metric):
    """E 층내 표본분산 s²_h(환자별 BJ-R2 차이, ddof=1)와 F 층별 n_h로 예상 97.5% 반폭 2.242*sqrt(sum(s²_h/n_h)/16)."""
    s2 = {}
    for code in ("00", "01", "10", "11"):
        d = [v["metrics"]["BJ"][metric] - v["metrics"]["R2"][metric] for v in per_patient.values() if v["stratum"] == code]
        s2[code] = float(np.var(d, ddof=1)) if len(d) > 1 else 0.0
    if all(v == 0 for v in s2.values()):
        return None, s2
    return T975 * math.sqrt(sum(s2[k] / f_sizes[k] for k in s2) / 16), s2


def decide_e(report, verify, f_sizes, f_independence_ok):
    d = dict(stage="E", checks={}, flags=[])
    valid = run_valid(report, verify)
    d["checks"]["run_valid"] = valid
    if not valid:
        d.update(run=False, outcome="invalid_run")
        return d
    c, df = report["conds"], report["diffs"]
    suff = {k: sufficient(c[k]) for k in SIMPLE}
    d["checks"]["simple_sufficient"] = {k: v[0] for k, v in suff.items()}
    d["checks"]["simple_sufficient_bounds"] = {k: v[1] for k, v in suff.items()}
    if any(v[0] for v in suff.values()):
        d.update(run=False, outcome="simple_alternative_sufficient_hold_F")
        return d
    acc = df["BJ-BT:acc"]
    c2 = bool(acc["mean"] >= ACC_GAIN and acc["lo"] > 0)
    rd, hd = df["BJ-R2:r"], df["BJ-R2:h_fail"]
    c3 = bool(rd["mean"] >= R_TRADE and hd["mean"] >= HFAIL_TRADE)
    cv = report["common_valid"]["BJ-R2"]
    c3_valid_dir = bool(cv["r_diff"] > 0 and cv["hfail_diff"] > 0)
    c4 = {k: bool(c[k]["r"]["mean"] < R_GOAL or c[k]["h_fail"]["mean"] > HFAIL_GOAL) for k in SIMPLE}
    hr, sr = expected_half_width(report["per_patient_metrics"], f_sizes, "r")
    hh, sh = expected_half_width(report["per_patient_metrics"], f_sizes, "h_fail")
    c5 = bool(hr is not None and hh is not None and hr <= HALF_R and hh <= HALF_HFAIL)
    d["checks"].update(bj_minus_bt_acc=dict(mean=acc["mean"], lo95=acc["lo"], passed=c2),
                       bj_minus_r2_tradeoff_points=dict(r=rd["mean"], h_fail=hd["mean"], passed=c3), common_valid_same_direction=c3_valid_dir,
                       each_simple_point_misses_goal=c4, expected_half_width=dict(r=hr, h_fail=hh, s2_r=sr, s2_h_fail=sh, passed=c5),
                       f_independence_ok=bool(f_independence_ok),
                       f_effective_n_equal_variance=1 / (sum((1 / 4) ** 2 / n for n in f_sizes.values())))
    if hr is None or hh is None:
        d["flags"].append("zero_within_stratum_variance_precision_not_supported_hold_F")
    allc = c2 and c3 and c3_valid_dir and all(c4.values()) and c5 and f_independence_ok
    d["run"] = bool(allc)
    d["outcome"] = "enter_F" if allc else "hold_F_current_correction_design_investment_on_hold"
    return d


def decide_f(report, verify):
    d = dict(stage="F", checks={}, flags=[])
    valid = run_valid(report, verify)
    d["checks"]["run_valid"] = valid
    if not valid:
        d.update(run=False, outcome="invalid_run")
        return d
    c, df = report["conds"], report["diffs"]
    suff = {k: sufficient(c[k]) for k in SIMPLE}
    miss = {k: misses_goal(c[k]) for k in SIMPLE}
    acc, rd, hd = df["BJ-BT:acc"], df["BJ-R2:r"], df["BJ-R2:h_fail"]
    cv = report["common_valid"]["BJ-R2"]
    crit = dict(acc_gain=bool(acc["mean"] >= ACC_GAIN and acc["lo"] > 0), r_trade=bool(rd["mean"] >= R_TRADE and rd["lo"] > 0),
                hfail_trade=bool(hd["mean"] >= HFAIL_TRADE and hd["lo"] > 0), common_valid_same_direction=bool(cv["r_diff"] > 0 and cv["hfail_diff"] > 0),
                each_simple_misses_goal={k: v[0] for k, v in miss.items()})
    d["checks"].update(simple_sufficient={k: v[0] for k, v in suff.items()}, criteria=crit,
                       bounds=dict(sufficient={k: v[1] for k, v in suff.items()}, misses={k: v[1] for k, v in miss.items()}))
    if any(v[0] for v in suff.values()):
        d["outcome"] = "simple_alternative_sufficient"
    elif crit["acc_gain"] and crit["r_trade"] and crit["hfail_trade"] and crit["common_valid_same_direction"] and all(crit["each_simple_misses_goal"].values()):
        d["outcome"] = "positive_min_method_review"
    else:
        if acc["hi"] < ACC_GAIN:
            d["flags"].append("image_gain_over_text_below_0.10")
        if rd["hi"] < R_TRADE or hd["hi"] < HFAIL_TRADE:
            d["flags"].append("bj_r2_tradeoff_not_reached")
        neg = acc["hi"] < ACC_GAIN or rd["hi"] < R_TRADE or hd["hi"] < HFAIL_TRADE
        d["outcome"] = "negative_no_tradeoff" if neg else "inconclusive"
    d["run"] = d["outcome"] == "positive_min_method_review"
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["E", "F"])
    for k in ("report", "verify", "protocol", "out"):
        ap.add_argument("--" + k, required=True)
    ap.add_argument("--e-decision", default=None)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("refuse to overwrite decision")
    rep, ver = json.load(open(a.report)), json.load(open(a.verify))
    if rep["stage"] != a.stage or ver["stage"] != a.stage or ver["source_digests"]["report"] != file_sha(a.report):
        sys.exit("report/verify stage or digest mismatch")
    inputs = dict(report=a.report, verify=a.verify, protocol=a.protocol)
    if a.stage == "E":
        fm = json.load(open(f"{OUT}/data/manifest_F.json"))
        sizes = {}
        for r in fm["rows"]:
            sizes[r["truth_code"]] = sizes.get(r["truth_code"], 0) + 1
        chk = json.load(open(f"{OUT}/data/data_check.json"))
        dec = decide_e(rep, ver, sizes, chk["f_independence_ok"])
        inputs["manifest_F"] = f"{OUT}/data/manifest_F.json"
    else:
        if not a.e_decision:
            sys.exit("F decision requires the E decision")
        ed = json.load(open(a.e_decision))
        if ed.get("run") is not True:
            sys.exit("E decision did not permit F")
        dec = decide_f(rep, ver)
        inputs["e_decision"] = a.e_decision
    dec["inputs"] = {k: dict(path=p, sha256=file_sha(p)) for k, p in inputs.items()}
    dec["data_check_sha256"] = file_sha(f"{OUT}/data/data_check.json")
    tmp = a.out + ".tmp"
    json.dump(dec, open(tmp, "w"), indent=1)
    os.replace(tmp, a.out)
    print(json.dumps(dec, indent=1))


if __name__ == "__main__":
    main()
