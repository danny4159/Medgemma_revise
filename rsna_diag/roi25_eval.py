"""iter_025 D768 채점: request row + 생성 record -> valid rate, 조건별 질문 정확도, Q4 paired 비교, 기존 oracle과의 비교."""
import glob
import json
import os

import numpy as np

from . import metrics as M, roi23_spec as R, roi25_spec as R25


class EvalError(RuntimeError):
    pass


def read_gen(gen_dir):
    recs = {}
    for f in sorted(glob.glob(os.path.join(gen_dir, "gen_worker*.jsonl"))):
        for ln in open(f):
            if ln.strip():
                r = json.loads(ln)
                if r["request_id"] in recs:
                    raise EvalError(f"duplicate request_id {r['request_id']} in {gen_dir}")
                recs[r["request_id"]] = r
    return recs


def parse_row(target, fmt, rec):
    st, ans, conv = R25.parse_semantic(target, fmt, rec["suffix_text_raw"], rec["ended_eos"])
    st_s, ans_s = R25.parse_answer(fmt, rec["suffix_text_raw"], rec["ended_eos"])
    return {"status": st, "answer": ans, "conversion": conv, "status_strict": st_s, "answer_strict": ans_s}


def collect(rows, recs_by_rid):
    """returns {(ckpt,condition): {id: {target: parsed}}}. 누락 record는 EvalError."""
    out = {}
    for row in rows:
        rec = recs_by_rid.get(row["request_id"])
        if rec is None:
            raise EvalError(f"missing generation record for {row['request_id']} "
                             f"(id={row['id']}, ckpt={row['checkpoint']}, cond={row['condition']}, target={row['target']})")
        if rec.get("modality") != row["modality"]:
            raise EvalError(f"modality mismatch for {row['request_id']}: record={rec.get('modality')} row={row['modality']}")
        key = (row["checkpoint"], row["condition"])
        out.setdefault(key, {}).setdefault(row["id"], {})[row["target"]] = parse_row(row["target"], row["fmt"], rec)
    return out


def gt_answers(gts, patient_ids):
    return {i: R.answers([b["yxyx_norm"] for b in gts[i]["boxes"]]) for i in patient_ids}


def valid_rate(per_patient, patient_ids):
    n_valid, n_total = 0, 0
    for i in patient_ids:
        d = per_patient.get(i, {})
        for t in R25.TARGETS:
            n_total += 1
            if d.get(t, {}).get("status") == "valid":
                n_valid += 1
    return {"n_valid": n_valid, "n_total": n_total, "rate": (n_valid / n_total if n_total else 0.0)}


def question_accuracy(per_patient, gt, patient_ids):
    n_correct, n_total = 0, 0
    for i in patient_ids:
        d = per_patient.get(i, {})
        for t in R25.TARGETS:
            n_total += 1
            p = d.get(t, {})
            if p.get("status") == "valid" and p.get("answer") == gt[i][t]:
                n_correct += 1
    return {"n_correct": n_correct, "n_total": n_total, "acc": (n_correct / n_total if n_total else None)}


def q4_series(per_patient, gt, patient_ids):
    vals, detail = [], {}
    for i in patient_ids:
        d = per_patient.get(i, {})
        valid = len(d) == 4 and all(d.get(t, {}).get("status") == "valid" for t in R25.TARGETS)
        correct = valid and all(d[t]["answer"] == gt[i][t] for t in R25.TARGETS)
        vals.append(1.0 if correct else 0.0)
        detail[i] = {"valid": valid, "correct": correct, "per_target": d}
    return np.array(vals, dtype=float), detail


def paired_ci(a, b, seed=25025, B=10000):
    n = len(a)
    idx = M.bootstrap_indices(n, B=B, seed=seed)
    mean_diff, lo, hi = M.paired_boot_ci(a, b, idx)
    d = np.asarray(a, float) - np.asarray(b, float)
    return {"mean_diff": mean_diff, "ci_lo": lo, "ci_hi": hi, "n": n, "n_improve": int((d > 0).sum()),
            "n_worsen": int((d < 0).sum()), "n_same": int((d == 0).sum())}


def old_oracle_q4(gen_dir_old, requests_path_old, gt, patient_ids):
    """iter_024 D24__O_{M0,B0}의 원시 record를 읽어(읽기 전용) 기존 oracle Q4를 재계산한다."""
    rows = [json.loads(ln) for ln in open(requests_path_old) if ln.strip()]
    recs = read_gen(gen_dir_old)
    per = {}
    for row in rows:
        rec = recs.get(row["request_id"])
        if rec is None:
            raise EvalError(f"missing old-oracle record for {row['request_id']} in {gen_dir_old}")
        per.setdefault(row["id"], {})[row["target"]] = parse_row(row["target"], row["fmt"], rec)
    return q4_series(per, gt, patient_ids)


def build_report(patient_ids, gts, rows_by_ckpt, recs_by_ckpt_cond, old_oracle=None):
    gt = gt_answers(gts, patient_ids)
    per = {}
    for ckpt, rows in rows_by_ckpt.items():
        recs = {}
        for cond in R25.CONDITIONS:
            recs.update(recs_by_ckpt_cond[(ckpt, cond)])
        per.update(collect(rows, recs))
    valid_rates = {f"{ck}_{cond}": valid_rate(per[(ck, cond)], patient_ids) for ck in ("M0", "B0") for cond in R25.CONDITIONS}
    q_acc = {f"{ck}_{cond}": question_accuracy(per[(ck, cond)], gt, patient_ids) for ck in ("M0", "B0") for cond in R25.CONDITIONS}
    q4 = {}
    q4_detail = {}
    for ck in ("M0", "B0"):
        for cond in R25.CONDITIONS:
            vals, det = q4_series(per[(ck, cond)], gt, patient_ids)
            q4[f"{ck}_{cond}"] = vals
            q4_detail[f"{ck}_{cond}"] = det
    comparisons = {}
    for ck in ("M0", "B0"):
        comparisons[f"{ck}_OC_I_minus_OB_I"] = paired_ci(q4[f"{ck}_OC_I"], q4[f"{ck}_OB_I"])
        comparisons[f"{ck}_OB_I_minus_OB_T"] = paired_ci(q4[f"{ck}_OB_I"], q4[f"{ck}_OB_T"])
        comparisons[f"{ck}_OC_I_minus_OC_T"] = paired_ci(q4[f"{ck}_OC_I"], q4[f"{ck}_OC_T"])
        if old_oracle and ck in old_oracle:
            comparisons[f"{ck}_OB_I_minus_old_oracle"] = paired_ci(q4[f"{ck}_OB_I"], old_oracle[ck][0])
    yes_rate = {f"{ck}_{cond}": {t: float(np.mean([1.0 if per[(ck, cond)].get(i, {}).get(t, {}).get("answer") == "yes" else 0.0
                                                    for i in patient_ids if per[(ck, cond)].get(i, {}).get(t, {}).get("status") == "valid"]))
                                 if any(per[(ck, cond)].get(i, {}).get(t, {}).get("status") == "valid" for i in patient_ids) else None
                for t in R25.TARGETS} for ck in ("M0", "B0") for cond in R25.CONDITIONS}
    return {"fmt": R25.FMT, "n_patients": len(patient_ids), "valid_rates": valid_rates, "question_accuracy": q_acc,
            "q4_mean": {k: float(v.mean()) for k, v in q4.items()}, "comparisons": comparisons, "yes_rate": yes_rate,
            "old_oracle_q4_mean": ({ck: float(v[0].mean()) for ck, v in old_oracle.items()} if old_oracle else None)}
