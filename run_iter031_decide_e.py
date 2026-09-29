"""iter_031 E402 최종 판정: 계획서 Evaluation 절(양성/음성/불확정) 기준을 적용한다.

C에서 잠근 B*는 E report 생성 시(run_iter031_eval.py --decide-c)에 이미 고정됐으므로 여기서는 재선택하지 않는다.
h1_report가 definable=False(단일 class 등)를 반환할 수 있어 None을 안전하게 처리한다.
"""
import argparse
import json
import os


def _gt(v, thr):
    return v is not None and v > thr


def _ge(v, thr):
    return v is not None and v >= thr


def decide(report):
    h1, h2 = report["h1"], report["h2"]
    diff = h1["diff_Q_minus_Bstar"]
    q1 = h1["auroc_Q_one_box_layer"]
    diff_point, diff_lo, diff_hi = diff.get("point"), diff.get("lo"), diff.get("hi")
    q1_lo = q1.get("lo") if q1 else None
    q1_hi = q1.get("hi") if q1 else None

    h1_positive = (_ge(diff_point, 0.05) and _gt(diff_lo, 0.0)
                  and _gt(q1_lo, 0.5)
                  and h1["capture20_diff"] >= 0.0)
    # diff_hi가 정의되지 않으면(단일 class) 음성 판정 불가 -> False로 두어 inconclusive로 남긴다.
    h1_negative = (diff_hi is not None and diff_hi < 0.05) and not (q1_hi is not None and q1_hi > 0.5 and q1_lo is not None and q1_lo > 0.5)

    h2_positive = (h2["n_events"] > 0) and (h2["recovery_rate"] >= 0.25) and (h2["wilson_95_lo"] > 0.10)
    h2_negative = h2["n_events"] > 0 and (h2["wilson_95_hi"] < 0.25)

    def verdict(pos, neg):
        if pos:
            return "positive"
        if neg:
            return "negative"
        return "inconclusive"

    return {
        "bstar": report["bstar"],
        "H1": {"verdict": verdict(h1_positive, h1_negative), "diff_Q_minus_Bstar": diff,
              "auroc_Q_one_box_layer": q1, "capture20_diff": h1["capture20_diff"],
              "diff_definable": diff.get("definable"), "q1_definable": (q1.get("definable") if q1 else False)},
        "H2": {"verdict": verdict(h2_positive, h2_negative), "n_events": h2["n_events"],
              "n_recovered": h2["n_recovered"], "recovery_rate": h2["recovery_rate"],
              "wilson_95_lo": h2["wilson_95_lo"], "wilson_95_hi": h2["wilson_95_hi"]},
        "population_cost": h2.get("population_cost"),
        "note": "H1/H2는 독립적으로 판정한다. 한쪽의 양성으로 다른 쪽을 주장하지 않는다 (계획서 Hypothesis 절).",
        "input_report_protocol_digest": report.get("protocol_digest"),
        "input_report_source_manifest_sha256": report.get("source_manifest_sha256"),
        "input_decide_c_link": report.get("decide_c_link"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default="results/iter_031/E402/report.json")
    ap.add_argument("--decide-c", default="results/iter_031/decide_c.json")
    ap.add_argument("--out", default="results/iter_031/decide_e.json")
    a = ap.parse_args()
    if os.path.exists(a.out):
        raise RuntimeError(f"refusing to overwrite existing {a.out}")
    report = json.load(open(a.report))
    if report["split"] != "E":
        raise RuntimeError(f"expected an E-split report, got {report['split']!r}")
    decide_c = json.load(open(a.decide_c))
    if not decide_c.get("enter_E"):
        raise RuntimeError("C201 decision has enter_E=False; E402 decision should not have been generated")
    link = report.get("decide_c_link") or {}
    if link.get("bstar") != decide_c.get("bstar"):
        raise RuntimeError(f"E report bstar {link.get('bstar')!r} != C decision bstar {decide_c.get('bstar')!r}")
    decision = decide(report)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(decision, open(a.out, "w"), indent=1)
    print(json.dumps({k: v for k, v in decision.items() if k != "population_cost"}, indent=1))


if __name__ == "__main__":
    main()
