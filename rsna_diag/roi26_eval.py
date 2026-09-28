"""iter_026 채점: S_i(사분면 결합 F1), Q4_select(전체 정답), C_query(질의 배정 대조), 환자 영상 대응 대조, 통계."""
import glob
import hashlib
import itertools
import json
import os

import numpy as np

from . import metrics as M, roi26_spec as R26, roi26_data as D26

IOU_THR = 0.3
IOU_THR2 = 0.5
PERMS = list(itertools.permutations(R26.TARGETS))  # 24개, identity 포함


class EvalError(RuntimeError):
    pass


def load_gen(gen_dir):
    recs = {}
    for f in sorted(glob.glob(os.path.join(gen_dir, "gen_worker*.jsonl"))):
        for ln in open(f):
            if ln.strip():
                r = json.loads(ln)
                if r["request_id"] in recs:
                    raise EvalError(f"duplicate request_id {r['request_id']} in {gen_dir}")
                recs[r["request_id"]] = r
    return recs


def parsed_for_row(row, recs_by_rid):
    rec = recs_by_rid.get(row["request_id"])
    if rec is None:
        raise EvalError(f"missing generation record for {row['request_id']} (id={row['id']}, target={row['target']})")
    pr = R26.parse_row(rec["suffix_text_raw"], rec["ended_eos"])
    return pr


def collect_direct(rows, recs_by_rid):
    """rows: 같은 (ckpt,condition)의 4×N 행. returns {id: {target: parse_result}}."""
    out = {}
    for row in rows:
        pr = parsed_for_row(row, recs_by_rid)
        out.setdefault(row["id"], {})[row["target"]] = pr
    return out


def is_valid(pr):
    return pr["status"] in ("valid_nonempty", "valid_empty")


def eligible_boxes(boxes, target):
    return [b for b in boxes if R26.quadrant_of(*R26.center_yx(b)) == target]


def patient_score(per_target_pred, gt_by_target, thr=IOU_THR):
    """per_target_pred: {target: [box,...]} (미필터, 요청 조건별 원본 예측). gt_by_target: {target: [box,...]}.
    returns (S, tp_sum, p_sum, g_sum, per_target_tp)."""
    tp_sum, p_sum, g_sum = 0, 0, 0
    detail = {}
    for t in R26.TARGETS:
        pred = per_target_pred.get(t, [])
        gt = gt_by_target.get(t, [])
        elig = eligible_boxes(pred, t)
        pairs = M.match(elig, gt, thr)
        tp = len(pairs)
        tp_sum += tp
        p_sum += len(pred)
        g_sum += len(gt)
        detail[t] = {"tp": tp, "n_pred": len(pred), "n_gt": len(gt)}
    s = (2.0 * tp_sum / (p_sum + g_sum)) if (p_sum + g_sum) > 0 else 0.0
    return s, tp_sum, p_sum, g_sum, detail


def q4_select(per_target_pred, gt_by_target):
    for t in R26.TARGETS:
        pred = per_target_pred.get(t, [])
        gt = gt_by_target.get(t, [])
        elig = eligible_boxes(pred, t)
        pairs = M.match(elig, gt, IOU_THR)
        if len(pairs) != len(gt) or len(pred) != len(gt):
            return False
    return True


def c_query(per_target_pred, gt_by_target, thr=IOU_THR):
    """permutation π: query t에 원래 target π(t)로 생성된 리스트를 배정한다."""
    real, _, _, _, _ = patient_score(per_target_pred, gt_by_target, thr)
    scores = []
    for perm in PERMS:
        assign = {t: per_target_pred.get(pt, []) for t, pt in zip(R26.TARGETS, perm)}
        s, _, _, _, _ = patient_score(assign, gt_by_target, thr)
        scores.append(s)
    return real - float(np.mean(scores))


def patient_valid(per_target):
    return len(per_target) == 4 and all(is_valid(per_target[t]) for t in R26.TARGETS)


def build_metrics(per_id, gts, patient_ids, donor_map=None):
    """per_id: {id: {target: parse_result}}. gts: roi23_data GT dict. returns per-patient arrays + detail."""
    S, Q4, CQ, INVALID = [], [], [], []
    detail = {}
    for i in patient_ids:
        pt = per_id.get(i, {})
        gt_by_target = D26.partition_gt([b["yxyx_norm"] for b in gts[i]["boxes"]])
        if not patient_valid(pt):
            S.append(0.0)
            Q4.append(0.0)
            CQ.append(0.0)
            INVALID.append(True)
            detail[i] = {"valid": False, "statuses": {t: pt.get(t, {}).get("status") for t in R26.TARGETS}}
            continue
        pred_by_t = {t: pt[t]["boxes"] for t in R26.TARGETS}
        s, tp, p, g, det = patient_score(pred_by_t, gt_by_target)
        q4 = q4_select(pred_by_t, gt_by_target)
        cq = c_query(pred_by_t, gt_by_target)
        S.append(s)
        Q4.append(1.0 if q4 else 0.0)
        CQ.append(cq)
        INVALID.append(False)
        detail[i] = {"valid": True, "S": s, "Q4": q4, "C_query": cq, "tp": tp, "n_pred": p, "n_gt": g, "per_target": det}
    out = {"S": np.array(S), "Q4": np.array(Q4), "C_query": np.array(CQ), "invalid": np.array(INVALID)}
    if donor_map:
        # donor가 배정되지 않은 경우(홀수 인원의 남는 1명)만 nan(제외)로 둔다.
        # donor는 있지만 그 donor의 응답이 invalid면, invalid=0점 규약(patient_valid 실패시 S=0)을 그대로 적용해
        # donor_S=0.0으로 채점한다(제외하지 않는다).
        DS = []
        for i in patient_ids:
            donor = donor_map.get(i)
            if donor is None:
                DS.append(float("nan"))
                continue
            if not patient_valid(per_id.get(donor, {})):
                DS.append(0.0)
                continue
            pred_by_t = {t: per_id[donor][t]["boxes"] for t in R26.TARGETS}
            gt_by_target = D26.partition_gt([b["yxyx_norm"] for b in gts[i]["boxes"]])
            s, _, _, _, _ = patient_score(pred_by_t, gt_by_target)
            DS.append(s)
        out["donor_S"] = np.array(DS)
    return out, detail


def rule_copy_empty_baseline(source_boxes_by_id, gts, patient_ids):
    """source_boxes_by_id: {id: (boxes_norm float list or None, status)} (하나의 원본 전체 bbox 출력).
    returns {name: metrics dict} for rule / copy / empty. status != valid는 invalid로 표시한다.
    id가 source_boxes_by_id에 아예 없으면(실행 결함으로 그 환자의 원본 생성이 누락) EvalError를 던진다.
    실제 생성은 있었으나 parse가 invalid인 경우만 모델 실패(0점)로 표시한다."""
    out = {}
    for name in ("rule", "copy", "empty"):
        S, Q4, CQ, INVALID = [], [], [], []
        detail = {}
        for i in patient_ids:
            if i not in source_boxes_by_id:
                raise EvalError(f"source bbox record entirely missing for {i} (execution gap, not a model failure)")
            boxes, status = source_boxes_by_id[i]
            if status == "missing":
                raise EvalError(f"source bbox status=missing for {i} (execution gap, not a model failure)")
            gt_by_target = D26.partition_gt([b["yxyx_norm"] for b in gts[i]["boxes"]])
            if boxes is None:
                S.append(0.0); Q4.append(0.0); CQ.append(0.0); INVALID.append(True)
                detail[i] = {"valid": False, "status": status}
                continue
            if name == "empty":
                pred_by_t = {t: [] for t in R26.TARGETS}
            elif name == "copy":
                pred_by_t = {t: list(boxes) for t in R26.TARGETS}
            else:  # rule
                parts = D26.partition_gt(boxes)
                pred_by_t = parts
            s, tp, p, g, det = patient_score(pred_by_t, gt_by_target)
            q4 = q4_select(pred_by_t, gt_by_target)
            cq = c_query(pred_by_t, gt_by_target)
            S.append(s); Q4.append(1.0 if q4 else 0.0); CQ.append(cq); INVALID.append(False)
            detail[i] = {"valid": True, "S": s, "Q4": q4, "C_query": cq}
        out[name] = {"S": np.array(S), "Q4": np.array(Q4), "C_query": np.array(CQ), "invalid": np.array(INVALID),
                     "detail": detail}
    return out


def diagnostics(per_id, gts, patient_ids, thr2=IOU_THR2):
    """iter_026 리뷰 task 8 복원: 요청 밖(다른 사분면) 예측 비율, 빈 응답 비율, '전체 복사' 성향 proxy,
    사분면별 tp/pred/gt 평균, IoU@0.5 S를 patient_valid인 환자만 대상으로 집계한다(정보용, gate에 미사용)."""
    n_valid_patients = 0
    n_empty_resp, n_resp = 0, 0
    n_out_of_quadrant, n_pred_total = 0, 0
    per_target_tp = {t: 0 for t in R26.TARGETS}
    per_target_pred = {t: 0 for t in R26.TARGETS}
    per_target_gt = {t: 0 for t in R26.TARGETS}
    s50 = []
    copy_like = 0  # 한 응답의 예측 개수가 그 환자의 GT 전체 개수(4개 target 합)보다 많거나 같고 3개 이상인 경우(전체 복사 proxy)
    for i in patient_ids:
        pt = per_id.get(i, {})
        gt_by_target = D26.partition_gt([b["yxyx_norm"] for b in gts[i]["boxes"]])
        n_gt_total = sum(len(gt_by_target[t]) for t in R26.TARGETS)
        if not patient_valid(pt):
            continue
        n_valid_patients += 1
        pred_by_t = {t: pt[t]["boxes"] for t in R26.TARGETS}
        s5, tp5, p5, g5, det5 = patient_score(pred_by_t, gt_by_target, thr=thr2)
        s50.append(s5)
        for t in R26.TARGETS:
            n_resp += 1
            pred = pred_by_t[t]
            if len(pred) == 0:
                n_empty_resp += 1
            elig = eligible_boxes(pred, t)
            n_out_of_quadrant += len(pred) - len(elig)
            n_pred_total += len(pred)
            if n_gt_total > 0 and len(pred) >= n_gt_total and len(pred) >= 3:
                copy_like += 1
            per_target_tp[t] += det5[t]["tp"]
            per_target_pred[t] += det5[t]["n_pred"]
            per_target_gt[t] += det5[t]["n_gt"]
    return {
        "n_valid_patients": n_valid_patients,
        "mean_S_iou50": float(np.mean(s50)) if s50 else None,
        "empty_response_rate": (n_empty_resp / n_resp) if n_resp else None,
        "out_of_quadrant_pred_rate": (n_out_of_quadrant / n_pred_total) if n_pred_total else None,
        "copy_like_response_rate": (copy_like / n_resp) if n_resp else None,
        "per_target": {t: {"tp": per_target_tp[t], "n_pred": per_target_pred[t], "n_gt": per_target_gt[t]}
                       for t in R26.TARGETS},
    }


def donor_pairs(patient_ids):
    """SHA256('iter026-pair-v1|'+id) 순 정렬 후 인접 2명씩 짝짓는다 (홀수면 마지막 1명은 짝 없음)."""
    ordered = sorted(patient_ids, key=lambda i: hashlib.sha256(("iter026-pair-v1|" + i).encode()).hexdigest())
    pairs = []
    for k in range(0, len(ordered) - 1, 2):
        pairs.append((ordered[k], ordered[k + 1]))
    donor_map = {}
    for a, b in pairs:
        donor_map[a] = b
        donor_map[b] = a
    return pairs, donor_map


def paired_ci(a, b, seed=26026, B=10000):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    n = len(a)
    idx = M.bootstrap_indices(n, B=B, seed=seed)
    mean_diff, lo, hi = M.paired_boot_ci(a, b, idx)
    d = a - b
    return {"mean_diff": mean_diff, "ci_lo": lo, "ci_hi": hi, "n": n, "n_improve": int((d > 0).sum()),
            "n_worsen": int((d < 0).sum()), "n_same": int((d == 0).sum())}


def cluster_paired_ci(diff_by_id, pairs, seed=26026, B=10000):
    """diff_by_id: {id: real_S - donor_S} (nan 제외하고 넘긴다). pairs: (a,b) 교환 쌍 목록 (cluster 단위).
    쌍을 통째로 resample하고 그 안의 개인 모두를 포함해 평균 차이의 percentile 95% CI를 구한다."""
    usable = [(a, b) for a, b in pairs if a in diff_by_id and b in diff_by_id]
    if not usable:
        return {"mean_diff": float("nan"), "ci_lo": float("nan"), "ci_hi": float("nan"), "n_pairs": 0, "n_indiv": 0}
    rng = np.random.default_rng(seed)
    n = len(usable)
    all_vals = np.array([diff_by_id[i] for pair in usable for i in pair])
    mean_diff = float(all_vals.mean())
    means = []
    for _ in range(B):
        idx = rng.integers(0, n, size=n)
        vals = np.array([diff_by_id[i] for k in idx for i in usable[k]])
        means.append(vals.mean())
    means = np.array(means)
    return {"mean_diff": mean_diff, "ci_lo": float(np.percentile(means, 2.5)), "ci_hi": float(np.percentile(means, 97.5)),
            "n_pairs": n, "n_indiv": len(all_vals)}


def _binom_cdf(k, n, p):
    from math import comb
    if p <= 0.0:
        return 1.0 if k >= 0 else 0.0
    if p >= 1.0:
        return 1.0 if k >= n else 0.0
    return sum(comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(0, k + 1))


def _solve_p_for_cdf(target_cdf, k, n, tol=1e-10):
    lo, hi = 0.0, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2.0
        if _binom_cdf(k, n, mid) > target_cdf:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return (lo + hi) / 2.0


def exact_binom_ci(k, n, alpha=0.05):
    """Clopper-Pearson exact two-sided CI (scipy 없이 이항 CDF 이분탐색으로 계산)."""
    if n == 0:
        return (float("nan"), float("nan"))
    lo = 0.0 if k == 0 else _solve_p_for_cdf(1 - alpha / 2, k - 1, n)
    hi = 1.0 if k == n else _solve_p_for_cdf(alpha / 2, k, n)
    return (float(lo), float(hi))
