"""iter_026 공용 평가 실행기: stage(D24/E60/E200 등)의 V/O/RD 결과를 채점해 report JSON을 만든다.
사용: python eval_iter026.py D
     python eval_iter026.py E60
     python eval_iter026.py E200   (E60+E200_extra gen dir를 합쳐 200명 전체로 채점)
"""
import glob
import json
import sys

import numpy as np

from rsna_diag import roi23_data as D, roi26_data as D26, roi26_eval as E, roi26_requests as Q, roi26_spec as R26

stage = sys.argv[1]


def load_gen_merged(names):
    recs = {}
    for name in names:
        for f in sorted(glob.glob(f"results/iter_026/gen/{name}/gen_worker*.jsonl")):
            for ln in open(f):
                if ln.strip():
                    r = json.loads(ln)
                    if r["request_id"] in recs and json.dumps(recs[r["request_id"]], sort_keys=True) != json.dumps(r, sort_keys=True):
                        raise E.EvalError(f"conflicting duplicate {r['request_id']}")
                    recs[r["request_id"]] = r
    return recs


def per_patient_from_rows(rows, recs):
    return E.collect_direct(rows, recs)


if stage == "D":
    items, gts = D.load_val_pool()
    d24 = json.load(open("results/iter_026/manifests_d24_build.json"))["d24_ids"]
    patient_ids = sorted(d24)
    jobs = {"V_M0": "D_V__M0", "V_B0": "D_V__B0", "O_M0": "D_O__M0", "O_B0": "D_O__B0", "RD_M0": "D_RD__M0"}
    text_jobs = {"V_M0_text": "D_TEXT__M0", "V_B0_text": "D_TEXT__B0"}
elif stage in ("E60", "E200"):
    items, gts = D.load_confirm_pool()
    sets = json.load(open("results/iter_023/manifests/sets.json"))
    if stage == "E60":
        patient_ids = sorted(sets["E60"]["primary"] + sets["E60"]["boundary"])
        jobs = {"V_M0": ["E60_V__M0"], "V_B0": ["E60_V__B0"], "RD_M0": ["E60_RD__M0"]}
    else:
        patient_ids = sorted(sets["E200"]["primary"] + sets["E200"]["boundary"])
        jobs = {"V_M0": ["E60_V__M0", "E200_extra_V__M0"], "V_B0": ["E60_V__B0", "E200_extra_V__B0"],
                "RD_M0": ["E60_RD__M0", "E200_extra_RD__M0"]}
    text_jobs = {}
else:
    raise SystemExit(f"unknown stage {stage}")

report = {"stage": stage, "n_patients": len(patient_ids)}

if stage == "D":
    per = {}
    valid_count = {}
    for key, name in jobs.items():
        rows = Q.load_rows(f"results/iter_026/requests/{name}.jsonl")
        recs = load_gen_merged([name])
        p = per_patient_from_rows(rows, recs)
        per[key] = p
        n_valid = sum(1 for i in patient_ids for t in R26.TARGETS if p.get(i, {}).get(t, {}).get("status") in ("valid_nonempty", "valid_empty"))
        valid_count[key] = n_valid
    for key, name in text_jobs.items():
        rows = Q.load_rows(f"results/iter_026/requests/{name}.jsonl")
        recs = load_gen_merged([name])
        st = {t: R26.parse_row(recs[r["request_id"]]["suffix_text_raw"], recs[r["request_id"]]["ended_eos"])["status"] for r in rows for t in [r["target"]]}
        valid_count[key] = sum(1 for v in st.values() if v in ("valid_nonempty", "valid_empty"))
        report.setdefault("text_status", {})[key] = st
    report["valid_count"] = valid_count

    metrics = {}
    for key in ("V_M0", "V_B0", "O_M0", "O_B0", "RD_M0"):
        m, det = E.build_metrics(per[key], gts, patient_ids)
        metrics[key] = {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in m.items()}
        metrics[key]["mean_S"] = float(np.mean(m["S"]))
        metrics[key]["mean_Q4"] = float(np.mean(m["Q4"]))
        metrics[key]["mean_C_query"] = float(np.mean(m["C_query"]))
        metrics[key]["n_invalid"] = int(m["invalid"].sum())
    report["metrics"] = metrics
    report["comparisons"] = {
        "V_B0_minus_V_M0_S": E.paired_ci(metrics["V_B0"]["S"], metrics["V_M0"]["S"]),
        "RD_M0_minus_V_M0_S": E.paired_ci(metrics["RD_M0"]["S"], metrics["V_M0"]["S"]),
        "O_B0_minus_O_M0_S": E.paired_ci(metrics["O_B0"]["S"], metrics["O_M0"]["S"]),
    }

else:
    per = {}
    valid_count = {}
    for key, names in jobs.items():
        rows = []
        for name in names:
            rows += Q.load_rows(f"results/iter_026/requests/{name}.jsonl")
        recs = load_gen_merged(names)
        p = per_patient_from_rows(rows, recs)
        per[key] = p
        n_valid = sum(1 for i in patient_ids for t in R26.TARGETS if p.get(i, {}).get(t, {}).get("status") in ("valid_nonempty", "valid_empty"))
        valid_count[key] = n_valid
    report["valid_count"] = valid_count
    report["valid_rate"] = {k: v / (len(patient_ids) * 4) for k, v in valid_count.items()}

    primary_ids = sorted(sets[stage]["primary"])
    boundary_ids = sorted(sets[stage]["boundary"])
    multi = D26.multi_quadrant_subset(gts, primary_ids)  # 계획의 "진부분집합"은 primary 안에서 정의한다
    multi_boundary = D26.multi_quadrant_subset(gts, boundary_ids)
    pairs, donor_map = E.donor_pairs(patient_ids)

    metrics = {}
    for key in ("V_M0", "V_B0", "RD_M0"):
        m, det = E.build_metrics(per[key], gts, patient_ids, donor_map=(donor_map if key in ("V_M0", "V_B0") else None))
        metrics[key] = {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in m.items()}
        metrics[key]["mean_S"] = float(np.mean(m["S"]))
        metrics[key]["mean_Q4"] = float(np.mean(m["Q4"]))
        metrics[key]["mean_C_query"] = float(np.mean(m["C_query"]))
        metrics[key]["n_invalid"] = int(m["invalid"].sum())
        metrics[key]["_detail"] = None
    report["metrics"] = metrics

    idx_multi = [k for k, i in enumerate(patient_ids) if i in set(multi)]
    idx_multi_boundary = [k for k, i in enumerate(patient_ids) if i in set(multi_boundary)]
    report["subset_ids"] = multi
    report["n_subset"] = len(multi)
    report["subset_boundary_ids"] = multi_boundary
    report["n_subset_boundary"] = len(multi_boundary)

    src_bbox = {}
    for ck, prompt_name in (("M0", "official_long"), ("B0", "concise")):
        recs_b, ntot = D26.source_bbox_records(ck, prompt_name)
        src = {i: D26.predicted_boxes(recs_b.get(i)) for i in patient_ids}
        src_bbox[ck] = src
    baselines = {}
    for ck in ("M0", "B0"):
        baselines[ck] = E.rule_copy_empty_baseline(src_bbox[ck], gts, patient_ids)

    report["baselines"] = {ck: {name: {"mean_S": float(np.mean(baselines[ck][name]["S"])),
                                        "mean_Q4": float(np.mean(baselines[ck][name]["Q4"])),
                                        "n_invalid": int(baselines[ck][name]["invalid"].sum())}
                                 for name in ("rule", "copy", "empty")} for ck in ("M0", "B0")}

    def subset_arr(arr):
        return np.array(arr)[idx_multi]

    report["comparisons"] = {
        "S_B0_minus_S_M0": E.paired_ci(metrics["V_B0"]["S"], metrics["V_M0"]["S"]),
        "S_B0_minus_Copy_B0": E.paired_ci(metrics["V_B0"]["S"], baselines["B0"]["copy"]["S"]),
        "S_RD_minus_S_B0": E.paired_ci(metrics["RD_M0"]["S"], metrics["V_B0"]["S"]),
        "S_rule_B0_minus_S_B0_direct": E.paired_ci(baselines["B0"]["rule"]["S"], metrics["V_B0"]["S"]),
        "S_RD_minus_S_V_M0": E.paired_ci(metrics["RD_M0"]["S"], metrics["V_M0"]["S"]),
    }
    report["C_query_ci"] = {ck: E.paired_ci(metrics[f"V_{ck}"]["C_query"], np.zeros(len(patient_ids))) for ck in ("M0", "B0")}

    subset_q4_b0_direct = subset_arr(metrics["V_B0"]["Q4"])
    subset_q4_b0_rule = subset_arr(baselines["B0"]["rule"]["Q4"])
    subset_q4_m0_direct = subset_arr(metrics["V_M0"]["Q4"])

    def exact_ci(k, n):
        return E.exact_binom_ci(k, n)

    report["subset"] = {
        "n": len(multi),
        "B0_direct_Q4_select_successes": int(subset_q4_b0_direct.sum()),
        "B0_direct_Q4_select_rate": float(subset_q4_b0_direct.mean()) if len(multi) else None,
        "B0_direct_Q4_select_exact_ci": exact_ci(int(subset_q4_b0_direct.sum()), len(multi)),
        "B0_rule_Q4_select_rate": float(subset_q4_b0_rule.mean()) if len(multi) else None,
        "B0_rule_Q4_select_exact_ci": exact_ci(int(subset_q4_b0_rule.sum()), len(multi)),
        "M0_direct_Q4_select_successes": int(subset_q4_m0_direct.sum()),
    }

    def subset_arr_b(arr):
        return np.array(arr)[idx_multi_boundary]

    bq4_b0_direct = subset_arr_b(metrics["V_B0"]["Q4"])
    bq4_b0_rule = subset_arr_b(baselines["B0"]["rule"]["Q4"])
    report["subset_boundary"] = {
        "n": len(multi_boundary),
        "B0_direct_Q4_select_successes": int(bq4_b0_direct.sum()),
        "B0_direct_Q4_select_rate": float(bq4_b0_direct.mean()) if len(multi_boundary) else None,
        "B0_rule_Q4_select_rate": float(bq4_b0_rule.mean()) if len(multi_boundary) else None,
    }

    donor_diff = {}
    for ck in ("M0", "B0"):
        real = metrics[f"V_{ck}"]["S"]
        donor = metrics[f"V_{ck}"]["donor_S"]
        diff_by_id = {}
        for i, r, dn in zip(patient_ids, real, donor):
            if not (isinstance(dn, float) and np.isnan(dn)):
                diff_by_id[i] = r - dn
        donor_diff[ck] = E.cluster_paired_ci(diff_by_id, pairs)
    report["donor_diff"] = donor_diff

json.dump(report, open(f"results/iter_026/eval/report_{stage}.json", "w"), indent=1, default=str)
print("wrote", f"results/iter_026/eval/report_{stage}.json")
