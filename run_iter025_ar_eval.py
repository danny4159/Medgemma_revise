"""iter_025 답 읽기(AR) sanity 채점: GT 사분면 이름을 text로 직접 제공한 list-membership 과제의 정확도.
E 진입 gate와 무관한 진단 전용 결과다. 사용: python run_iter025_ar_eval.py
"""
import json
import os

os.environ.setdefault("ROI25_RUN_ROOT", "results/iter_025")

from rsna_diag import roi23_data as D, roi25_eval as EV, roi25_requests as RQ, roi25_spec as R25  # noqa: E402

OUT = "results/iter_025"
items, gts = D.load_val_pool()
d24 = json.load(open(f"{OUT}/manifests_d24_ids.json"))
d_gts = {i: gts[i] for i in d24}
cfg = json.load(open(f"{OUT}/protocol_AR.json"))["locked"]["generation_config_digest"]
gt = EV.gt_answers(d_gts, d24)

report = {}
for ck in ("M0", "B0"):
    rows = RQ.load_rows(f"{OUT}/requests/AR__{ck}.jsonl", cfg)
    recs = EV.read_gen(f"{OUT}/gen/AR__{ck}")
    completion = json.load(open(f"{OUT}/gen/AR__{ck}/completion.json"))
    if completion["n_expected"] != len(rows) or completion["n_actual_unique"] != len(rows):
        raise SystemExit(f"{ck}: AR completion.json does not match request count")
    missing = [r["request_id"] for r in rows if r["request_id"] not in recs]
    if missing:
        raise SystemExit(f"{ck}: missing {len(missing)} AR records")
    per = EV.collect(rows, recs)[(ck, "AR")]
    vr = EV.valid_rate(per, d24)
    qa = EV.question_accuracy(per, gt, d24)
    q4, _ = EV.q4_series(per, gt, d24)
    report[ck] = {"valid_rate": vr, "question_accuracy": qa, "q4_mean": float(q4.mean())}

os.makedirs(f"{OUT}/eval", exist_ok=True)
json.dump(report, open(f"{OUT}/eval/report_AR.json", "w"), indent=1, default=str)
print(json.dumps(report, indent=1, default=str))
