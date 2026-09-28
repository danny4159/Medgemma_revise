"""iter_023 채점: request row + 생성 record -> 환자별 Q4, 규칙 baseline, paired CI, permutation 연관성 분석."""
import glob
import json
import math
import os

import numpy as np

from . import metrics as M, roi23_data as D, roi23_spec as R


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


def parse_row(row, rec, fmt):
    st, ans, conv = R.parse_semantic(row["target"], fmt, rec["suffix_text_raw"], rec["ended_eos"])
    st_strict, ans_strict = R.parse_answer(fmt, rec["suffix_text_raw"], rec["ended_eos"])
    return {"status": st, "answer": ans, "conversion": conv, "status_strict": st_strict, "answer_strict": ans_strict}


def collect(rows, recs_by_rid, fmt):
    """returns {id: {target: parsed}}. missing record -> EvalError."""
    out = {}
    for row in rows:
        rec = recs_by_rid.get(row["request_id"])
        if rec is None:
            raise EvalError(f"missing generation record for request {row['request_id']} (id={row['id']}, target={row['target']})")
        out.setdefault(row["id"], {})[row["target"]] = parse_row(row, rec, fmt)
    return out


def gt_answers(gts, patient_ids):
    out = {}
    for i in patient_ids:
        boxes = [b["yxyx_norm"] for b in gts[i]["boxes"]]
        out[i] = R.answers(boxes)
    return out


def q4_series(per_patient, gt, patient_ids):
    vals, detail = [], {}
    for i in patient_ids:
        d = per_patient.get(i, {})
        valid = len(d) == 4 and all(d.get(t, {}).get("status") == "valid" for t in R.TARGETS)
        correct = valid and all(d[t]["answer"] == gt[i][t] for t in R.TARGETS)
        vals.append(1.0 if correct else 0.0)
        detail[i] = {"valid": valid, "correct": correct, "per_target": d}
    return np.array(vals, dtype=float), detail


def rule_q4_series(bbox_by_id, gt, patient_ids):
    """예측 bbox(파싱된 status 포함)에 사분면 중심 규칙을 적용. invalid bbox는 실패(0)로 세고 별도 coverage로 센다."""
    vals, detail, n_invalid = [], {}, 0
    for i in patient_ids:
        boxes, status = bbox_by_id.get(i, (None, "missing"))
        if boxes is None:
            vals.append(0.0)
            detail[i] = {"valid": False, "correct": False, "bbox_status": status}
            n_invalid += 1
            continue
        pred = R.answers(boxes)
        correct = all(pred[t] == gt[i][t] for t in R.TARGETS)
        vals.append(1.0 if correct else 0.0)
        detail[i] = {"valid": True, "correct": correct, "bbox_status": status, "pred": pred}
    return np.array(vals, dtype=float), detail, n_invalid


def _binom_cdf(k, n, p):
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    if p <= 0.0:
        return 1.0
    if p >= 1.0:
        return 0.0
    s = 0.0
    for i in range(0, k + 1):
        s += math.comb(n, i) * (p ** i) * ((1 - p) ** (n - i))
    return s


def _bisect_p(f, target, lo=0.0, hi=1.0, iters=200):
    for _ in range(iters):
        mid = (lo + hi) / 2
        if f(mid) > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def clopper_pearson(k, n, alpha=0.05):
    """정확한 Clopper-Pearson 양측 구간. math.comb로 직접 계산 (scipy 없음)."""
    if n == 0:
        return (float("nan"), float("nan"))
    lo = 0.0 if k == 0 else _bisect_p(lambda p: _binom_cdf(k - 1, n, p), 1 - alpha / 2)
    hi = 1.0 if k == n else _bisect_p(lambda p: _binom_cdf(k, n, p), alpha / 2)
    return (lo, hi)


def paired_ci(a, b, seed=23023, B=10000, bonferroni_m=2):
    n = len(a)
    idx = M.bootstrap_indices(n, B=B, seed=seed)
    mean_diff, lo, hi = M.paired_boot_ci(a, b, idx)
    d = np.asarray(a, float) - np.asarray(b, float)
    n_improve, n_worsen, n_same = int((d > 0).sum()), int((d < 0).sum()), int((d == 0).sum())
    out = {"mean_diff": mean_diff, "ci_lo": lo, "ci_hi": hi, "n": n, "n_improve": n_improve, "n_worsen": n_worsen,
           "n_same": n_same}
    if lo == hi:
        alpha = 0.05 / bonferroni_m
        imp_lo, imp_hi = clopper_pearson(n_improve, n, alpha)
        wor_lo, wor_hi = clopper_pearson(n_worsen, n, alpha)
        out["degenerate"] = True
        out["note"] = ("bootstrap CI degenerate (all paired differences equal); reporting Bonferroni-corrected "
                       "Clopper-Pearson bounds on improve/worsen proportions as a conservative alternative")
        out["cp_improve_prop_ci"] = [imp_lo, imp_hi]
        out["cp_worsen_prop_ci"] = [wor_lo, wor_hi]
        # 계획식: [L_improve-U_worsen, U_improve-L_worsen], [-1,1]로 clip. 판정에는 이 구간을 쓴다 (bootstrap 원본은 보존).
        out["diff_interval_clipped"] = [max(-1.0, imp_lo - wor_hi), min(1.0, imp_hi - wor_lo)]
    else:
        out["degenerate"] = False
    lo_j, hi_j = (out["diff_interval_clipped"] if out["degenerate"] else (out["ci_lo"], out["ci_hi"]))
    out["judge_ci_lo"], out["judge_ci_hi"] = lo_j, hi_j
    return out


def permutation_association(pred_bool, gt_bool, seed, B=10000):
    """pred_bool, gt_bool: (n_patients, 4) 0/1 배열. 환자 순서를 permute하고 정확도 분포를 만든다."""
    n = pred_bool.shape[0]
    rng = np.random.default_rng(seed)
    obs = float((pred_bool == gt_bool).mean())
    accs = np.empty(B)
    for b in range(B):
        perm = rng.permutation(n)
        accs[b] = float((pred_bool[perm] == gt_bool).mean())
    return {"observed_accuracy": obs, "perm_mean": float(accs.mean()), "perm_sd": float(accs.std()),
            "p_value_upper_tail": float((accs >= obs).mean())}


def to_bool_matrix(per_patient, patient_ids):
    """valid한 환자만 포함(순서 보존). returns (ids_kept, bool_matrix[n,4] with yes=1)."""
    ids_kept, mat = [], []
    for i in patient_ids:
        d = per_patient.get(i, {})
        if len(d) == 4 and all(d.get(t, {}).get("status") == "valid" for t in R.TARGETS):
            ids_kept.append(i)
            mat.append([1 if d[t]["answer"] == "yes" else 0 for t in R.TARGETS])
    return ids_kept, np.array(mat, dtype=int)


def valid_rate(per_patient, patient_ids, key="status"):
    n_valid = sum(1 for i in patient_ids for t in R.TARGETS if per_patient.get(i, {}).get(t, {}).get(key) == "valid")
    return n_valid, len(patient_ids) * 4
