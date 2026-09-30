"""iter_039 평가기 fixture: 합성 GT/출력으로 환자 점수·교환 oracle·invalid 처리·결정 규칙을 검사. 결과 results/iter_039/tests/fixtures_pg39_eval.json"""
import json
import os
import sys

import numpy as np

import pg39_eval as E
import pg39_spec as S

res = {}


def check(n, c, info=None):
    res[n] = {"pass": bool(c), "info": info}
    print(("PASS " if c else "FAIL ") + n, "" if c else info)


H, W = 1000, 1200
top = 100  # (1200-1000)//2
side = 1200


def man_for(k):
    return {"PatientID": f"P{k}", "image_meta": {"h": H, "w": W}, "stratum": "share0_multi0",
            "gt_boxes_xyxy_norm": {"qA": [[0.1, 0.1, 0.3, 0.3]], "qB": [[0.6, 0.6, 0.9, 0.9]]},
            "extra_boxes_xyxy_norm": {"qA": [], "qB": []}}


def canvas(box_xyxy_norm):
    x0, y0, x1, y1 = box_xyxy_norm
    return [round((y0 * H + top) * 1000 / side, 3), round(x0 * W * 1000 / side, 3), round((y1 * H + top) * 1000 / side, 3),
            round(x1 * W * 1000 / side, 3)]


A, B = canvas([0.1, 0.1, 0.3, 0.3]), canvas([0.6, 0.6, 0.9, 0.9])


def rec(p, cond, targets, items, eos=True):
    txt = "Final Answer: " + json.dumps([{"box_2d": b, "label": l} for l, b in items]) + "<end_of_turn>"
    return {"patient": p, "cond": cond, "targets": targets, "suffix_text_raw": txt, "ended_eos": eos, "n_output_tokens": 10,
            "wall_s": 1.0, "peak_mem_alloc_gb_max": 8.0, "attempts": [{}], "request_id": f"{p}{cond}{targets}"}


man = {}
recs = []
for k in range(8):
    p = f"P{k}"
    man[p] = man_for(k)
    conds = [("I-long", ["qA"], [("qA", A)]), ("I-long", ["qB"], [("qB", B)]),
             ("C-long", ["qA"], [("qA", A)]), ("C-long", ["qB"], [("qB", B)]),
             ("I-short", ["qA"], [("qA", A)]), ("I-short", ["qB"], [("qB", B)])]
    for c, t, it in conds:
        recs.append(rec(p, c, t, it))
    both = ["qA", "qB"]
    if k < 4:  # 교환 오류: 상자는 맞지만 ID가 서로 바뀜
        j = [("qA", B), ("qB", A)]
    else:
        j = [("qA", A), ("qB", B)]
    recs.append(rec(p, "J-long", both, j))
    recs.append(rec(p, "J-reverse", both, [("qA", A), ("qB", B)]))
    recs.append(rec(p, "J-short", both, [("qA", A), ("qB", B)] if k != 7 else [("opacity", A)]))
rep = E.evaluate(recs, man)
check("I_long_perfect", abs(rep["mean_f1_03"]["I-long"][0] - 1.0) < 1e-12)
check("J_long_half_when_half_swapped", abs(rep["mean_f1_03"]["J-long"][0] - 0.5) < 1e-12, rep["mean_f1_03"]["J-long"])
check("delta_long", abs(rep["delta_long_I_minus_J"]["ci95"][0] - 0.5) < 1e-12)
check("swap_oracle_recovers", abs(rep["swap_oracle_J-long"]["best_of_swap"] - 1.0) < 1e-12 and rep["swap_oracle_J-long"]["patients_improved"] == 4)
check("invalid_scored_zero_and_counted", rep["format"]["J-short"]["status_counts"].get("unknown_id") == 1
      and abs(rep["mean_f1_03"]["J-short"][0] - 7 / 8) < 1e-12)
check("loss_counts", rep["loss_recovery_I_vs_J-long"]["success_lost"] == 8 and rep["loss_recovery_I_vs_J-long"]["success_gained"] == 0)
check("truncation_is_invalid", E.S.parse_ids("Final Answer: [", False, {"qA"})["status"] == "truncated")
# 결정 규칙
base = json.loads(json.dumps(rep, default=float))


def mk(i_mean, i_ci, full_i, dl, ds, n=96, valid=1.0, trunc=0.0):
    r = {"n_patients": n, "capability": {"I_long_mean_f1_03": [i_mean, *i_ci], "patients_with_ge1_sentence_f1_eq_1": full_i},
         "delta_long_I_minus_J": {"ci95": dl, "ci975": dl}, "delta_short_I_minus_J": {"ci95": ds, "ci975": ds},
         "format_family": {"long_valid": valid, "short_valid": valid, "unresolved_truncation_rate": trunc},
         "valid_subset_sensitivity": {"long": {"n": n, "delta_ci95": dl}}}
    return r


d = E.e96_decision(mk(0.5, (0.4, 0.6), 40, [0.12, 0.02, 0.22], [0.03, -0.05, 0.11]))
check("expand_A", d["expand_to_E288"] and d["criterion_a"] and not d["hold"], d)
d = E.e96_decision(mk(0.5, (0.4, 0.6), 40, [0.02, -0.04, 0.08], [0.0, -0.05, 0.05]))
check("hold_when_both_upper_lt_0.10", d["hold"] and not d["expand_to_E288"], d)
d = E.e96_decision(mk(0.30, (0.2, 0.38), 40, [0.12, 0.02, 0.22], [0.03, -0.05, 0.11]))
check("hold_when_I_upper_lt_0.40", d["hold"] and not d["expand_to_E288"])
d = E.e96_decision(mk(0.42, (0.33, 0.51), 30, [0.08, 0.0, 0.16], [0.0, -0.05, 0.05], valid=0.8))
check("no_uncertain_expand_with_format_problem", not d["criterion_b_uncertain_precision"])
d = E.e96_decision(mk(0.42, (0.33, 0.51), 30, [0.08, 0.02, 0.14], [0.0, -0.05, 0.05]))
check("uncertain_expand_B_when_precise", d["criterion_b_uncertain_precision"] and d["expand_to_E288"] and d["projected_ci_halfwidth_at_288"] <= 0.06, d)
f = E.f_decision(mk(0.5, (0.4, 0.6), 100, [0.12, 0.03, 0.22], [0.03, -0.05, 0.11], n=288))
check("F_needs_valid_subset_content_loss", not f["run_F120"] or f["content_loss_not_explained_by_format"], f)
f = E.f_decision(dict(mk(0.5, (0.4, 0.6), 100, [0.12, 0.03, 0.22], [0.03, -0.05, 0.11], n=288),
                      valid_subset_sensitivity={"long": {"n": 288, "delta_ci95": [0.10, 0.02, 0.18]}}))
check("F_runs_when_all_met", f["run_F120"], f)
os.makedirs("results/iter_039/tests", exist_ok=True)
out = "results/iter_039/tests/fixtures_pg39_eval.json"
if os.path.exists(out):
    sys.exit("exists")
json.dump(res, open(out, "w"), indent=1)
nf = sum(not v["pass"] for v in res.values())
print(f"{len(res) - nf}/{len(res)} passed")
sys.exit(1 if nf else 0)
