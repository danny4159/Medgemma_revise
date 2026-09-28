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
        valid_count[key] = None  # per-group(primary/boundary) valid_count는 아래에서 별도 계산한다
    del valid_count

    primary_ids = sorted(sets[stage]["primary"])
    boundary_ids = sorted(sets[stage]["boundary"])
    report["n_primary"] = len(primary_ids)
    report["n_boundary"] = len(boundary_ids)

    src_bbox = {}
    for ck, prompt_name in (("M0", "official_long"), ("B0", "concise")):
        recs_b, ntot = D26.source_bbox_records(ck, prompt_name)
        src = {i: D26.predicted_boxes(recs_b.get(i)) for i in patient_ids}
        src_bbox[ck] = src
    # M0-concise baseline 복원 (iter_026 리뷰 task 8): gate/comparisons에는 쓰지 않고 정보용으로만 보고한다.
    recs_m0c, _ = D26.source_bbox_records("M0", "concise")
    src_bbox["M0_concise"] = {i: D26.predicted_boxes(recs_m0c.get(i)) for i in patient_ids}

    def group_report(ids, group_name):
        """primary 또는 boundary 집단 하나에 대해 metrics/baseline/comparison/subset을 독립적으로 계산한다.
        primary·boundary를 합쳐서 donor pairing·paired CI를 만들지 않는다 (iter_026 리뷰 결함 수정)."""
        g = {}
        vc = {}
        for key in ("V_M0", "V_B0", "RD_M0"):
            n_valid = sum(1 for i in ids for t in R26.TARGETS
                          if per[key].get(i, {}).get(t, {}).get("status") in ("valid_nonempty", "valid_empty"))
            vc[key] = n_valid
        g["valid_count"] = vc
        g["valid_rate"] = {k: v / (len(ids) * 4) if ids else None for k, v in vc.items()}

        pairs, donor_map = E.donor_pairs(ids)
        metrics = {}
        for key in ("V_M0", "V_B0", "RD_M0"):
            m, det = E.build_metrics(per[key], gts, ids, donor_map=(donor_map if key in ("V_M0", "V_B0") else None))
            metrics[key] = {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in m.items()}
            metrics[key]["mean_S"] = float(np.mean(m["S"])) if ids else None
            metrics[key]["mean_Q4"] = float(np.mean(m["Q4"])) if ids else None
            metrics[key]["mean_C_query"] = float(np.mean(m["C_query"])) if ids else None
            metrics[key]["n_invalid"] = int(m["invalid"].sum())
        g["metrics"] = metrics
        g["diagnostics"] = {key: E.diagnostics(per[key], gts, ids) for key in ("V_M0", "V_B0", "RD_M0")}

        baselines = {ck: E.rule_copy_empty_baseline({i: src_bbox[ck][i] for i in ids}, gts, ids)
                     for ck in ("M0", "B0", "M0_concise")}
        g["baselines"] = {ck: {name: {"mean_S": float(np.mean(baselines[ck][name]["S"])) if ids else None,
                                       "mean_Q4": float(np.mean(baselines[ck][name]["Q4"])) if ids else None,
                                       "n_invalid": int(baselines[ck][name]["invalid"].sum())}
                                for name in ("rule", "copy", "empty")} for ck in ("M0", "B0", "M0_concise")}

        s_b0_minus_m0 = E.paired_ci(metrics["V_B0"]["S"], metrics["V_M0"]["S"])
        s_b0_minus_copy = E.paired_ci(metrics["V_B0"]["S"], baselines["B0"]["copy"]["S"])
        rule_minus_b0_direct = E.paired_ci(baselines["B0"]["rule"]["S"], metrics["V_B0"]["S"])
        reader_minus_b0_direct = E.paired_ci(metrics["RD_M0"]["S"], metrics["V_B0"]["S"])  # RD(reader) - B0 direct (부호 반전 없음)
        cq_b0 = E.paired_ci(metrics["V_B0"]["C_query"], np.zeros(len(ids)))
        cq_m0 = E.paired_ci(metrics["V_M0"]["C_query"], np.zeros(len(ids)))

        donor_diff = {}
        for ck in ("M0", "B0"):
            real = metrics[f"V_{ck}"]["S"]
            donor = metrics[f"V_{ck}"]["donor_S"]
            diff_by_id = {}
            for i, r, dn in zip(ids, real, donor):
                if not (isinstance(dn, float) and np.isnan(dn)):
                    diff_by_id[i] = r - dn
            donor_diff[ck] = E.cluster_paired_ci(diff_by_id, pairs)

        g["primary_like"] = {
            "S_B0_minus_S_M0": s_b0_minus_m0,
            "S_B0_minus_Copy_B0": s_b0_minus_copy,
            "S_rule_B0_minus_S_B0_direct": rule_minus_b0_direct,
            "rule_minus_B0_direct_S": rule_minus_b0_direct,
            "reader_minus_B0_direct_S": reader_minus_b0_direct,
            "rule_or_reader_minus_B0_direct_S": {
                "rule": rule_minus_b0_direct, "reader": reader_minus_b0_direct,
                "max_mean_diff": max(rule_minus_b0_direct["mean_diff"], reader_minus_b0_direct["mean_diff"]),
            },
            "C_query_B0_mean": cq_b0["mean_diff"], "C_query_B0_ci_lo": cq_b0["ci_lo"],
            "C_query_M0_mean": cq_m0["mean_diff"], "C_query_M0_ci_lo": cq_m0["ci_lo"],
            "donor_diff_B0": donor_diff["B0"], "donor_diff_M0": donor_diff["M0"],
        }

        multi = D26.multi_quadrant_subset(gts, ids)
        idx_multi = [k for k, i in enumerate(ids) if i in set(multi)]

        def sub(arr):
            return np.array(arr)[idx_multi] if idx_multi else np.array([])

        q4_b0_direct = sub(metrics["V_B0"]["Q4"])
        q4_b0_rule = sub(baselines["B0"]["rule"]["Q4"])
        q4_m0_direct = sub(metrics["V_M0"]["Q4"])
        g["subset_like"] = {
            "ids": multi, "n": len(multi),
            "B0_direct_Q4_select_successes": int(q4_b0_direct.sum()) if len(multi) else 0,
            "B0_direct_Q4_select_rate": float(q4_b0_direct.mean()) if len(multi) else None,
            "B0_direct_Q4_select_exact_ci": E.exact_binom_ci(int(q4_b0_direct.sum()), len(multi)) if len(multi) else (float("nan"), float("nan")),
            "B0_rule_Q4_select_rate": float(q4_b0_rule.mean()) if len(multi) else None,
            "B0_rule_Q4_select_exact_ci": E.exact_binom_ci(int(q4_b0_rule.sum()), len(multi)) if len(multi) else (float("nan"), float("nan")),
            "M0_direct_Q4_select_successes": int(q4_m0_direct.sum()) if len(multi) else 0,
        }
        return g

    rep_primary = group_report(primary_ids, "primary")
    rep_boundary = group_report(boundary_ids, "boundary") if boundary_ids else None

    report["valid_count_primary"] = rep_primary["valid_count"]
    report["valid_rate_primary"] = rep_primary["valid_rate"]
    report["metrics_primary"] = rep_primary["metrics"]
    report["baselines_primary"] = rep_primary["baselines"]
    report["diagnostics_primary"] = rep_primary["diagnostics"]
    report["primary"] = rep_primary["primary_like"]
    report["subset"] = rep_primary["subset_like"]
    report["subset_ids"] = rep_primary["subset_like"]["ids"]
    report["n_subset"] = rep_primary["subset_like"]["n"]

    if rep_boundary is not None:
        report["valid_count_boundary"] = rep_boundary["valid_count"]
        report["valid_rate_boundary"] = rep_boundary["valid_rate"]
        report["metrics_boundary"] = rep_boundary["metrics"]
        report["baselines_boundary"] = rep_boundary["baselines"]
        report["diagnostics_boundary"] = rep_boundary["diagnostics"]
        report["boundary"] = rep_boundary["primary_like"]
        report["subset_boundary"] = rep_boundary["subset_like"]
        report["subset_boundary_ids"] = rep_boundary["subset_like"]["ids"]
        report["n_subset_boundary"] = rep_boundary["subset_like"]["n"]

    if stage == "E200":
        from rsna_diag import roi26_decide as DEC
        cls = DEC.classify_e200(report)
        report["classification"] = cls
        report["positive_candidate"] = cls["positive_candidate"]

import os as _os
_os.makedirs("results/iter_027/eval", exist_ok=True)
_outp = f"results/iter_027/eval/report_{stage}.json"
json.dump(report, open(_outp, "w"), indent=1, default=str)
print("wrote", _outp)
