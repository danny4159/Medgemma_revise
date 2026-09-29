"""iter_031 C201 decision: E402 진입 여부를 계획서 4절 기준으로 판정하고 잠근다.

run_iter030_decide_c.py의 판정 임계값 논리(점기준/회복기준/CI 보완 경로)는 계획서와 일치해 그대로 쓴다.
이번에 고치는 것: h1_report가 단일 class 등으로 정의 불가(definable=False, point=None)를 반환할 수 있으므로
None을 안전하게 "기준 미달"로 처리하고, report.json의 protocol_digest·source_manifest_sha256을 decision에
연결해 남긴다 (다음 단계에서 같은 실행 계열인지 대조할 수 있도록).
"""
import argparse
import json
import os


def _num_ge(v, thr):
    return v is not None and v >= thr


def decide(report):
    h1, h2 = report["h1"], report["h2"]
    diff = h1["diff_Q_minus_Bstar"]
    q1 = h1["auroc_Q_one_box_layer"]

    diff_point, diff_hi = diff.get("point"), diff.get("hi")
    q1_point = q1.get("point") if q1 else None
    q1_hi = q1.get("hi") if q1 else None

    point_criterion = _num_ge(diff_point, 0.03) and _num_ge(q1_point, 0.60)
    recovery_criterion = (h2["n_events"] > 0) and (h2["recovery_rate"] >= 0.20)

    ci_soft = False
    ci_soft_reason = None
    if not (point_criterion or recovery_criterion):
        cond_a = _num_ge(diff_hi, 0.05) and _num_ge(q1_hi, 0.65)
        cond_b = (h2["n_recovered"] >= 1) and (h2["wilson_95_hi"] >= 0.25)
        ci_soft = bool(cond_a or cond_b)
        if cond_a:
            ci_soft_reason = "diff_Q_minus_Bstar CI 상한>=0.05 and one-box Q AUROC CI 상한>=0.65"
        elif cond_b:
            ci_soft_reason = "recovery>=1건 and wilson 95% 상한>=0.25"

    enter_e = bool(point_criterion or recovery_criterion or ci_soft)
    return {
        "point_criterion_met": point_criterion, "recovery_criterion_met": recovery_criterion,
        "ci_soft_criterion_met": ci_soft, "ci_soft_reason": ci_soft_reason,
        "enter_E": enter_e,
        "bstar": report["bstar"], "diff_Q_minus_Bstar": diff, "auroc_Q_one_box_layer": q1,
        "diff_definable": diff.get("definable"), "q1_definable": (q1.get("definable") if q1 else False),
        "h2_recovery_rate": h2["recovery_rate"], "h2_n_events": h2["n_events"], "h2_n_recovered": h2["n_recovered"],
        "h2_wilson_95_hi": h2["wilson_95_hi"],
        "input_report_protocol_digest": report.get("protocol_digest"),
        "input_report_source_manifest_sha256": report.get("source_manifest_sha256"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default="results/iter_031/C201/report.json")
    ap.add_argument("--out", default="results/iter_031/decide_c.json")
    a = ap.parse_args()
    if os.path.exists(a.out):
        raise RuntimeError(f"refusing to overwrite existing {a.out}")
    report = json.load(open(a.report))
    if report["split"] != "C":
        raise RuntimeError(f"expected a C-split report, got {report['split']!r}")
    decision = decide(report)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(decision, open(a.out, "w"), indent=1)
    print(json.dumps(decision, indent=1))


if __name__ == "__main__":
    main()
