"""iter_030 E402 최종 판정: 계획서 Evaluation 절(양성/음성/불확정) 기준을 적용한다. C에서 잠근 B*를 그대로 쓴다."""
import json
import os

OUT = "results/iter_030/decide_e.json"


def decide(report):
    h1, h2 = report["h1"], report["h2"]
    diff = h1["diff_Q_minus_Bstar"]
    q1 = h1["auroc_Q_one_box_layer"]

    h1_positive = (diff["point"] >= 0.05 and diff["lo"] > 0.0
                  and q1 is not None and q1["lo"] > 0.5
                  and h1["capture20_diff"] >= 0.0)
    h1_negative = (diff["hi"] < 0.05) and not (q1 is not None and q1["hi"] > 0.5 and q1["lo"] > 0.5)

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
              "auroc_Q_one_box_layer": q1, "capture20_diff": h1["capture20_diff"]},
        "H2": {"verdict": verdict(h2_positive, h2_negative), "n_events": h2["n_events"],
              "n_recovered": h2["n_recovered"], "recovery_rate": h2["recovery_rate"],
              "wilson_95_lo": h2["wilson_95_lo"], "wilson_95_hi": h2["wilson_95_hi"]},
        "note": "H1/H2는 독립적으로 판정한다. 한쪽의 양성으로 다른 쪽을 주장하지 않는다 (계획서 Hypothesis 절).",
    }


def main():
    if os.path.exists(OUT):
        raise RuntimeError(f"refusing to overwrite existing {OUT}")
    report = json.load(open("results/iter_030/E402/report.json"))
    decision = decide(report)
    json.dump(decision, open(OUT, "w"), indent=1)
    print(json.dumps(decision, indent=1))


if __name__ == "__main__":
    main()
