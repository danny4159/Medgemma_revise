"""iter_025 D768 채점 실행: request row + gen record -> report_D.json, D_decision.json.
사용: python run_iter025_d_eval.py
"""
import json
import os

os.environ.setdefault("ROI25_RUN_ROOT", "results/iter_025")

from rsna_diag import roi23_data as D, roi25_eval as EV, roi25_decide as DEC, roi25_requests as RQ, roi25_spec as R25  # noqa: E402

OUT = "results/iter_025"

items, gts = D.load_val_pool()
d24 = json.load(open(f"{OUT}/manifests_d24_ids.json"))
d_items = {i: items[i] for i in d24}
d_gts = {i: gts[i] for i in d24}
cfg = json.load(open(f"{OUT}/protocol_D.json"))["locked"]["generation_config_digest"]

rows_by_ckpt = {}
recs_by_ckpt_cond = {}
for ck in ("M0", "B0"):
    rows = RQ.load_rows(f"{OUT}/requests/D__{ck}.jsonl", cfg)
    rows_by_ckpt[ck] = rows
    recs = EV.read_gen(f"{OUT}/gen/D__{ck}")
    got_ids = {r["request_id"] for r in rows}
    completion = json.load(open(f"{OUT}/gen/D__{ck}/completion.json"))
    if completion["n_expected"] != len(rows) or completion["n_actual_unique"] != len(rows):
        raise SystemExit(f"{ck}: completion.json does not match request count")
    for cond in R25.CONDITIONS:
        cond_rows = [r for r in rows if r["condition"] == cond]
        cond_recs = {r["request_id"]: recs[r["request_id"]] for r in cond_rows if r["request_id"] in recs}
        missing = [r["request_id"] for r in cond_rows if r["request_id"] not in recs]
        if missing:
            raise SystemExit(f"{ck}/{cond}: missing {len(missing)} generation records, e.g. {missing[:3]}")
        recs_by_ckpt_cond[(ck, cond)] = cond_recs

# old (iter_024) oracle D24 Q4, read-only comparison
gt = EV.gt_answers(d_gts, d24)
old_oracle = {}
for ck, key in (("M0", "O_M0"), ("B0", "O_B0")):
    reqp = f"results/iter_024/requests/D24__{key}.jsonl"
    gendir = f"results/iter_024/gen/D24__{key}"
    old_oracle[ck] = EV.old_oracle_q4(gendir, reqp, gt, d24)

report = EV.build_report(d24, d_gts, rows_by_ckpt, recs_by_ckpt_cond, old_oracle=old_oracle)
os.makedirs(f"{OUT}/eval", exist_ok=True)
json.dump(report, open(f"{OUT}/eval/report_D.json", "w"), indent=1, default=str)
print(json.dumps({k: report[k] for k in ("valid_rates", "question_accuracy", "q4_mean", "old_oracle_q4_mean")}, indent=1, default=str))

os.makedirs(f"{OUT}/decide", exist_ok=True)
decision = DEC.decide_d()
print(json.dumps(decision, indent=1, default=str))
