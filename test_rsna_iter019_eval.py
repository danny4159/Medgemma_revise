"""iter_019 mi19_eval 독립 검사: parser 연결, wrong-instance 판정, H 사건, pair success, CI."""
import json
import sys

sys.path.insert(0, "/SSD1_1TB/home/milab/daniel/08_medgemma/research")
from rsna_diag import mi19_eval as E

results = []


def check(name, cond, detail=None):
    results.append({"name": name, "pass": bool(cond), "detail": detail})


def mk_rec(text, eos=True):
    return {"suffix_text_raw": text + ("<end_of_turn>" if eos else ""), "ended_eos": eos}


def test_classify_response_single_box():
    rec = mk_rec('Final Answer: [{"box_2d":[100,100,200,200],"label":"referenced vertebra"}]')
    c = E.classify_response(rec)
    check("single_box_valid", c["parse_status"] == "valid_nonempty" and c["n_boxes"] == 1)
    check("single_box_values", c["box"] == [100.0, 100.0, 200.0, 200.0])


def test_classify_response_multi_box_flagged():
    rec = mk_rec('Final Answer: [{"box_2d":[1,1,2,2],"label":"x"},{"box_2d":[3,3,4,4],"label":"y"}]')
    c = E.classify_response(rec)
    check("multi_box_wrong_count", c["parse_status"].endswith("_wrong_count") and c["box"] is None)


def test_classify_response_truncated():
    c = E.classify_response(mk_rec("Final Answer: [", eos=False))
    check("truncated_status", c["parse_status"] == "truncated" and c["box"] is None)


def test_classify_pred_wrong_instance():
    target = [0, 0, 10, 10]
    other = [(5, [100, 100, 110, 110])]
    pred = [100, 100, 110, 110]  # matches other exactly, misses target entirely
    r = E.classify_pred(pred, target, other)
    check("wrong_instance_detected", r["is_wrong_instance"] and r["wrong_instance_label"] == 5, r)


def test_classify_pred_success():
    target = [0, 0, 10, 10]
    other = [(5, [100, 100, 110, 110])]
    pred = [1, 1, 9, 9]
    r = E.classify_pred(pred, target, other)
    check("success_detected", r["success_0.5"] and not r["is_wrong_instance"], r)


def test_classify_pred_ambiguous_tie_not_wrong():
    target = [0, 0, 10, 10]
    other = [(5, [0, 0, 10, 10])]  # identical box as target -> tie, not wrong-instance (ambiguous)
    pred = [0, 0, 10, 10]
    r = E.classify_pred(pred, target, other)
    check("tie_not_forced_wrong", not r["is_wrong_instance"] and r["success_0.5"], r)


def test_pair_success_rate():
    rows = [
        {"patient": "p1", "success_0.5": True}, {"patient": "p1", "success_0.5": True},
        {"patient": "p2", "success_0.5": True}, {"patient": "p2", "success_0.5": False},
        {"patient": "p3", "success_0.5": False}, {"patient": "p3", "success_0.5": False},
    ]
    r = E.pair_success_rate(rows)
    check("pair_success_rate_value", abs(r["rate"] - 1 / 3) < 1e-9, r)
    check("pair_success_n", r["n_patients"] == 3)


def test_compute_H():
    patients = ["p1", "p2"]
    o_rows = [{"patient": "p1", "label": 1, "success_0.5": True}, {"patient": "p1", "label": 2, "success_0.5": True},
             {"patient": "p2", "label": 1, "success_0.5": False}, {"patient": "p2", "label": 2, "success_0.5": True}]
    jrt = [{"patient": "p1", "label": 1, "box": [0, 0, 1, 1], "is_wrong_instance": True, "wrong_instance_label": 9},
          {"patient": "p1", "label": 2, "box": [0, 0, 1, 1], "is_wrong_instance": False, "wrong_instance_label": None}]
    jtr = [{"patient": "p1", "label": 1, "box": [0, 0, 1, 1], "is_wrong_instance": True, "wrong_instance_label": 9},
          {"patient": "p1", "label": 2, "box": [0, 0, 1, 1], "is_wrong_instance": False, "wrong_instance_label": None}]
    h = E.compute_H(patients, o_rows, jrt, jtr)
    check("H_p1_event", h["events"]["p1"] is True, h)
    check("H_p2_no_event_missing_j", h["events"]["p2"] is False, h)
    check("H_k_and_n", h["k"] == 1 and h["n"] == 2)


def test_paired_diff_all_equal_gives_zero_ci():
    patients = ["p1", "p2", "p3"]
    a = {"p1": True, "p2": True, "p3": False}
    b = {"p1": True, "p2": True, "p3": False}
    d = E.paired_diff(a, b, patients)
    check("paired_diff_zero", d["mean_diff"] == 0.0 and d["ci95"] == [0.0, 0.0] and d["discordant_n"] == 0, d)


for fn in [test_classify_response_single_box, test_classify_response_multi_box_flagged, test_classify_response_truncated,
           test_classify_pred_wrong_instance, test_classify_pred_success, test_classify_pred_ambiguous_tie_not_wrong,
           test_pair_success_rate, test_compute_H, test_paired_diff_all_equal_gives_zero_ci]:
    fn()

n_pass = sum(1 for r in results if r["pass"])
print(json.dumps({"n": len(results), "n_pass": n_pass, "results": results}, indent=1, default=str))
json.dump({"n": len(results), "n_pass": n_pass, "results": results},
          open("/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_021/tests/fixtures_eval.json", "w"), indent=1, default=str)
assert n_pass == len(results)
