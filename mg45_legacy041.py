"""iter_045: iter_041 비용 결합 판정 한정 정정 artifact (원본 plan/review/report는 수정하지 않는다).

원 blocker(iter_041 review.json): pg41_eval이 요청 wall 합 기반 환자 bootstrap CI(request_wall_ratio_bootstrap_ci95)를 device-seconds 경계 검사에 쓰고,
처리량 비율의 CI 없이 cost_boundary=false를 만들었다. 이 스크립트는
  1) 원 plan/review/report/timing 파일의 hash를 연결하고,
  2) 정확도 수치와 비용 점추정치를 원시 record에서 다시 계산해 저장값과 일치함을 확인하며(불변성 회귀),
  3) device-seconds·처리량의 '유효한 반복 구간'은 unavailable(조건당 비동기 단회 큐: 요청 resampling은 반복 실행 변동성이 아님)로, 결합 투자 판정은 unresolved로 기록한다.
원 기준(device 비율 1.25, p95 1.20, throughput 0.80)은 바꾸지 않는다. 이번 MG 비용 문턱으로 옛 joint 판정을 대체하지 않는다.
python mg45_legacy041.py --out results/iter_045/legacy041_correction/correction.json
"""
import argparse
import glob
import hashlib
import json
import os
import sys

AG = "/SSD1_1TB/home/milab/daniel/08_medgemma/agent/runs/iter_041"
PLAN_SHA = "e9786ff168532ae432a03be8aa9d64e84308bc69ff08d8cd03e3002fd28eb87f"
REPORT = "results/iter_041/eval/report_V96.json"
QUEUES = {"Icost": "results/iter_041/gen/V96_C_Icost", "JAB": "results/iter_041/gen/V96_C_JAB", "JBA": "results/iter_041/gen/V96_C_JBA"}


def fsha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def union(iv):
    tot, cs, ce = 0.0, None, None
    for s_, e_ in sorted(iv):
        if ce is None or s_ > ce:
            if ce is not None:
                tot += ce - cs
            cs, ce = s_, e_
        else:
            ce = max(ce, e_)
    return tot + ((ce - cs) if ce is not None else 0.0)


def combined_decision(accuracy_class, cost_point_burden, repeated_cost_ci_available):
    """정확도·비용 결합 판정. 유효한 반복 비용 구간이 없으면 양성 결합 판정을 내리지 않는다."""
    if not repeated_cost_ci_available:
        return "unresolved"
    return "positive_method_pilot_candidate" if (accuracy_class == "positive" and cost_point_burden) else "not_positive"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("output exists")
    plan_sha = fsha(AG + "/plan.md")
    if plan_sha != PLAN_SHA:
        sys.exit("iter_041 plan sha changed")
    rv = json.load(open(AG + "/review.json"))
    rep = json.load(open(REPORT))
    out = {"original": {"plan_md": AG + "/plan.md", "plan_sha256": plan_sha, "review_json": AG + "/review.json", "review_json_sha256": fsha(AG + "/review.json"),
                        "blocking_issues_verbatim": rv["blocking_issues"], "report": REPORT, "report_sha256": fsha(REPORT)},
           "queues": {}, "recomputed_vs_stored": {}}
    for q, d in QUEUES.items():
        comp = json.load(open(d + "/completion.json"))
        mapping = {int(k): v for k, v in comp["mapping"].items()}
        recs = []
        files = sorted(glob.glob(d + "/gen_worker*.jsonl"))
        for f in files:
            recs += [json.loads(l) for l in open(f, "rb").read().split(b"\n")[:-1] if l.strip()]
        iv = {}
        for r in recs:
            iv.setdefault(mapping[r["worker"]], []).append((r["t_start"], r["ts"]))
        out["queues"][q] = {"dir": d, "completion_sha256": fsha(d + "/completion.json"), "worker_files": {os.path.basename(f): fsha(f) for f in files},
                            "timing_files": {os.path.basename(f): fsha(f) for f in sorted(glob.glob(d + "/worker*.timing.*.json"))},
                            "n_records": len(recs), "sum_request_wall_s": sum(r["wall_s"] for r in recs),
                            "device_seconds_generate_union_recomputed": sum(union(v) for v in iv.values()),
                            "device_seconds_generate_union_stored": comp["cost"]["device_seconds_generate_union"],
                            "request_wall_sum_differs_from_device_union": abs(sum(r["wall_s"] for r in recs) - sum(union(v) for v in iv.values())) > 1.0}
    st = rep["cost"]
    out["recomputed_vs_stored"] = {
        "Icost_device_union_abs_diff": abs(out["queues"]["Icost"]["device_seconds_generate_union_recomputed"] - st["I_over_JAB"]["device_seconds_generate_union"][0]),
        "JAB_device_union_abs_diff": abs(out["queues"]["JAB"]["device_seconds_generate_union_recomputed"] - st["I_over_JAB"]["device_seconds_generate_union"][1]),
        "JBA_device_union_abs_diff": abs(out["queues"]["JBA"]["device_seconds_generate_union_recomputed"] - st["I_over_JBA"]["device_seconds_generate_union"][1]),
        "devsec_ratio_I_over_JAB_stored": st["I_over_JAB"]["devsec_ratio_I_over_J"], "devsec_ratio_I_over_JBA_stored": st["I_over_JBA"]["devsec_ratio_I_over_J"],
        "p95_latency_ratio_stored": [st["I_over_JAB"]["p95_latency_ratio_I_over_J"], st["I_over_JBA"]["p95_latency_ratio_I_over_J"]],
        "throughput_ratio_stored": [st["I_over_JAB"]["throughput_ratio_I_over_J"], st["I_over_JBA"]["throughput_ratio_I_over_J"]],
        "accuracy_stored": {"C_I_f1_03": rep["models"]["C"]["mean_f1_03"]["I"][0], "C_JAB_f1_03": rep["models"]["C"]["mean_f1_03"]["AB"][0],
                            "C_JBA_f1_03": rep["models"]["C"]["mean_f1_03"]["BA"][0]}}
    out["recomputed_vs_stored"]["point_estimates_unchanged"] = all(v < 1e-6 for k, v in out["recomputed_vs_stored"].items() if k.endswith("abs_diff"))
    out["original_thresholds_unchanged"] = {"device_seconds_ratio_ge": 1.25, "p95_latency_ratio_ge": 1.20, "throughput_ratio_le": 0.80,
                                            "note": "원 기준 유지. 이번 MG 비용 문턱(0.50/2.0/1.20)으로 대체하지 않는다."}
    out["valid_repeated_run_ci_device_seconds_throughput"] = "unavailable"
    out["valid_repeated_run_ci_reason"] = "조건당 비동기 단회 큐. 요청/환자 resampling CI는 반복 실행의 device 시간·처리량 변동성이 아니다. 단회 timing 복제로 해결된 것으로 만들지 않는다."
    out["combined_investment_decision"] = combined_decision(rep["decision"]["accuracy"]["class"], rep["decision"]["cost"]["cost_burden"], False)
    out["original_overall_preserved_as_recorded"] = rep["decision"]["overall"]
    out["note"] = "원본 report/review/blocking_issues는 수정하지 않았다. 정확도 관찰(C I 0.578 vs J 0.381/0.354)과 비용 점추정은 유지되며, 비용 CI를 요구하는 결합 판정만 unresolved다."
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(out, open(a.out, "x"), indent=1)
    print(json.dumps({"point_estimates_unchanged": out["recomputed_vs_stored"]["point_estimates_unchanged"], "combined": out["combined_investment_decision"],
                      "diffs": {k: v for k, v in out["recomputed_vs_stored"].items() if k.endswith("abs_diff")},
                      "wall_sum_vs_union": {q: [v["sum_request_wall_s"], v["device_seconds_generate_union_recomputed"]] for q, v in out["queues"].items()}}, indent=1))


if __name__ == "__main__":
    main()
