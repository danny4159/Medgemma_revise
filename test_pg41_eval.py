"""iter_041 판정 규칙·비용 계산·평가 함수 합성 fixture (CPU).

python test_pg41_eval.py --out results/iter_041/tests/fixtures_pg41_eval.json
"""
import argparse
import json
import sys

import numpy as np

import pg39_spec as S
import pg41_eval as E
import pg41_rules as RU

RES = []


def check(name, ok, detail=None):
    RES.append({"name": name, "pass": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name, json.dumps(detail, default=str)[:250], flush=True)


def rec(patient, targets, t0, t1, wall=None, n=10, worker=0):
    return {"patient": patient, "targets": targets, "t_start": t0, "ts": t1, "wall_s": wall if wall is not None else t1 - t0,
            "attempts": [{"n_new": n}], "worker": worker}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    # 판정 규칙
    ci = lambda m, lo, hi: [m, lo, hi]
    pos = RU.accuracy_class(ci(.08, .03, .13), ci(.07, .02, .12), .06, .05, .07, .06)
    check("rule_positive", pos["class"] == "positive")
    check("rule_positive_needs_lower_ci_gt0", RU.accuracy_class(ci(.08, -.01, .13), ci(.07, .02, .12), .06, .05, .07, .06)["class"] == "uncertain")
    check("rule_positive_needs_B_positive", RU.accuracy_class(ci(.08, .03, .13), ci(.07, .02, .12), -.01, .05, .07, .06)["class"] == "uncertain")
    check("rule_positive_needs_common_subset_positive", RU.accuracy_class(ci(.08, .03, .13), ci(.07, .02, .12), .06, .05, -.01, .06)["class"] == "uncertain")
    check("rule_point_below_0.05_not_positive", RU.accuracy_class(ci(.04, .01, .07), ci(.07, .02, .12), .06, .05, .07, .06)["class"] == "uncertain")
    neg = RU.accuracy_class(ci(.01, -.02, .04), ci(0.0, -.03, .03), 0, 0, 0, 0)
    check("rule_negative_both_ci_upper_lt_0.05", neg["class"] == "negative" and not neg["strong_negative"])
    check("rule_strong_negative_upper_le_0.02", RU.accuracy_class(ci(0, -.03, .02), ci(0, -.03, .015), 0, 0, 0, 0)["strong_negative"])
    check("rule_one_order_crossing_is_uncertain", RU.accuracy_class(ci(.01, -.02, .04), ci(.06, .01, .11), .0, .0, .0, .0)["class"] == "uncertain")
    c_ok = RU.cost_class([1.3, 1.4], [1.25, 1.3], [0.9, 0.9])
    check("cost_burden_true_with_p95_route", c_ok["cost_burden"])
    check("cost_burden_true_with_throughput_route", RU.cost_class([1.3, 1.4], [1.0, 1.0], [0.7, 0.75])["cost_burden"])
    check("cost_burden_false_if_one_order_below_dev", not RU.cost_class([1.3, 1.1], [1.5, 1.5], [0.5, 0.5])["cost_burden"])
    check("overall_positive_candidate", RU.overall(pos, c_ok, False) == "positive_method_pilot_candidate")
    check("overall_boundary_is_uncertain", RU.overall(pos, c_ok, True) == "uncertain_hold_no_extension")
    check("overall_negative_preserves_independent", RU.overall(neg, c_ok, False).startswith("independent_baseline_preserved"))
    check("overall_accuracy_loss_without_cost_holds", RU.overall(pos, RU.cost_class([1.0, 1.0], [1, 1], [1, 1]), False).startswith("independent"))
    # 환자 지연·비용: I는 두 요청을 한 환자 작업으로 묶는다
    recs_I = [rec("p1", ["qA"], 0, 10), rec("p1", ["qB"], 1, 14, worker=1), rec("p2", ["qA"], 20, 25), rec("p2", ["qB"], 21, 30, worker=1)]
    pids, lat, wsum, tok = E.cost_rows(recs_I, "I")
    check("patient_latency_is_first_start_to_last_end_not_wall_max_or_sum", list(lat) == [14.0, 10.0] and list(wsum) == [10 + 13, 5 + 9] and pids == ["p1", "p2"], [list(lat), list(wsum)])
    try:
        E.cost_rows(recs_I[:3], "I")
        ok = False
    except AssertionError:
        ok = True
    check("missing_request_in_patient_unit_rejected", ok)
    # 채점: J 공동 출력에서 문장 그룹, 교환 oracle
    gt = {"qA": [[100, 100, 200, 200]], "qB": [[500, 500, 600, 600]]}
    swapped = {"qA": [[500, 500, 600, 600]], "qB": [[100, 100, 200, 200]]}
    check("swap_score_recovers_group_assignment_error", S.swap_score(swapped, gt) == 1.0 and S.sent_metrics(swapped["qA"], gt["qA"], 0.3)["f1"] == 0.0)
    # 판정 함수 통합: 입력 순서가 바뀐 JBA도 targets는 [qA,qB]
    rows = [json.loads(l) for l in open("results/iter_041/requests/requests_V96_JBA.jsonl")][:3]
    check("JBA_rows_targets_and_cond", all(r["targets"] == ["qA", "qB"] and r["cond"] == "J-short-rev" for r in rows))
    json.dump({"results": RES, "n_pass": sum(x["pass"] for x in RES), "n": len(RES)}, open(a.out, "x"), indent=1, default=str)
    print(f"{sum(x['pass'] for x in RES)}/{len(RES)} PASS")
    sys.exit(0 if all(x["pass"] for x in RES) else 1)


if __name__ == "__main__":
    main()
