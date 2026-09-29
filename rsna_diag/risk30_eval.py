"""iter_030/031 평가: 위험 baseline·Q·seed baseline AUROC/Capture, H2 회복률, F1/FP 부작용, bootstrap CI.

iter_031 수정: E의 97.5%(1.25/98.75) primary CI, ceil(0.2N) Capture, 단일 class 배제 재표집 bootstrap,
one-box layer diff 보고, 전체 O/F 비용(F1/FP/invalid/latency) 집계를 추가한다.
"""
import glob
import json
import math

import numpy as np

from . import metrics, parse
from .risk28_eval import auroc, bootstrap_indices  # 범용 AUROC/bootstrap 재사용 (capture는 iter_030/031 전용 ceil 버전을 쓴다)

BASELINE_ORDER = ["neg_n_pred_boxes", "neg_n_output_tokens", "first_token_entropy",
                  "mean_nll_excl_last", "mean_entropy_excl_last", "eos_nll", "branch_chosen_token_nll"]
SEED_BASELINES = ["seed_max_box_diff", "seed_geom_mismatch_mean"]
ALL_RISK_SCORES = BASELINE_ORDER + SEED_BASELINES


def load_all(out_dir):
    out = {}
    for fn in sorted(glob.glob(f"{out_dir}/gen_worker*.jsonl")):
        for ln in open(fn):
            if ln.strip():
                r = json.loads(ln)
                out[(r["id"], r["task"])] = r
    return out


def seed_geom_mismatch(seed_boxes, ref_boxes, thr=0.3):
    """seed_boxes가 비어있으면 0. 아니면 ref_boxes에 IoU>=thr로 matching되지 않는 seed_boxes 비율."""
    if not seed_boxes:
        return 0.0
    pairs = metrics.match(ref_boxes, seed_boxes, thr)  # gt=ref, pred=seed -> pairs (ref_idx, seed_idx)
    matched_seed = {si for _, si in pairs}
    return float(len(seed_boxes) - len(matched_seed)) / len(seed_boxes)


def build_rows(source_manifest, source_audit, o_records, split):
    rows = []
    for pid, item in source_manifest["patients"][split].items():
        o = o_records.get((pid, "O"))
        if o is None:
            raise RuntimeError(f"missing O record for {pid}")
        a = source_audit["patients"][split][pid]
        ev = a["event"]
        s29 = a["pred_boxes_seed29"] or []
        s43 = a["pred_boxes_seed43"] or []
        n17 = item["n_pred_boxes"]
        seed_max_diff = max(len(s29), len(s43)) - n17
        geom_29 = seed_geom_mismatch(s29, a["pred_boxes_seed17"], 0.3)
        geom_43 = seed_geom_mismatch(s43, a["pred_boxes_seed17"], 0.3)
        rows.append({
            "id": pid, "y_partial": int(ev["y_partial"]), "n_gt": ev["n_gt"], "n_pred": n17,
            "category": a["category"],
            "neg_n_pred_boxes": o["neg_n_pred_boxes"], "neg_n_output_tokens": o["neg_n_output_tokens"],
            "first_token_entropy": o["first_token_entropy"], "mean_nll_excl_last": o["mean_nll_excl_last"],
            "mean_entropy_excl_last": o["mean_entropy_excl_last"], "eos_nll": o["eos_nll"],
            "branch_chosen_token_nll": o["branch_chosen_token_nll"],
            "Q_continue_minus_close": o["Q_continue_minus_close"],
            "seed_max_box_diff": float(seed_max_diff), "seed_geom_mismatch_mean": (geom_29 + geom_43) / 2.0,
            "reproduced_expected_suffix": o["reproduced_expected_suffix"], "ended_eos_O": o["ended_eos"],
        })
    return rows


def metric_ci(values_fn, n, B=10000, seed=30017, alpha_lo=2.5, alpha_hi=97.5):
    idx = bootstrap_indices(n, B, seed)
    vals = np.array([values_fn(row) for row in idx])
    point = values_fn(np.arange(n))
    return {"point": float(point), "lo": float(np.percentile(vals, alpha_lo)),
            "hi": float(np.percentile(vals, alpha_hi)), "B": B, "seed": seed}


def paired_diff_ci(a_fn, b_fn, n, B=10000, seed=30017, alpha_lo=2.5, alpha_hi=97.5):
    idx = bootstrap_indices(n, B, seed)
    a_vals = np.array([a_fn(row) for row in idx])
    b_vals = np.array([b_fn(row) for row in idx])
    d = a_vals - b_vals
    point = a_fn(np.arange(n)) - b_fn(np.arange(n))
    return {"point": float(point), "lo": float(np.percentile(d, alpha_lo)), "hi": float(np.percentile(d, alpha_hi)),
            "B": B, "seed": seed}


def capture_at_k_ceil(scores, y, frac=0.2):
    """계획서의 Capture@ceil(0.2N) (risk28_eval.capture_at_k의 round(0.2N)과 다르다).
    경계 동점은 그 집단 내 무작위 검토 기대값으로 처리한다 (round 버전과 동일한 tie 규칙, k만 ceil)."""
    s = np.asarray(scores, float)
    yy = np.asarray(y, int)
    n = len(s)
    k = math.ceil(n * frac)
    if k <= 0 or yy.sum() == 0:
        return 0.0
    order = np.argsort(-s, kind="stable")
    thresh = s[order[k - 1]]
    above = s > thresh
    tie = s == thresh
    n_take_from_tie = k - int(above.sum())
    captured = float(yy[above].sum())
    if n_take_from_tie > 0 and tie.sum() > 0:
        tie_pos_rate = yy[tie].sum() / tie.sum()
        captured += n_take_from_tie * tie_pos_rate
    return float(captured / yy.sum())


def bootstrap_idx_nondegenerate(y, B, seed, max_factor=200):
    """단일 class(전부 0 또는 전부 1)인 resample은 거부하고 재표집한다 (AUROC 정의 불가 방지).
    같은 idx를 Q/B*/one-box 등 여러 score에 공유하므로 거부는 y 배열 하나만으로 판정한다.
    returns (idx array shape (B_accepted, n), n_rejected)."""
    rng = np.random.default_rng(seed)
    n = len(y)
    y = np.asarray(y)
    out, n_rejected, tries, max_tries = [], 0, 0, B * max_factor
    while len(out) < B and tries < max_tries:
        idx = rng.integers(0, n, size=n)
        tries += 1
        yy = y[idx]
        if yy.min() == yy.max():
            n_rejected += 1
            continue
        out.append(idx)
    if len(out) < B:
        raise RuntimeError(f"could not draw {B} non-degenerate bootstrap resamples for n={n} "
                            f"after {tries} attempts (n_rejected={n_rejected})")
    return np.array(out), n_rejected


def auroc_ci_safe(y, score, n, seed=30017, alpha_lo=2.5, alpha_hi=97.5, B=10000):
    """단일 class 원 집단이면 정의 불가(definable=False)로 표시한다. 그 외에는 단일 class resample을
    거부·재표집한 뒤 percentile CI를 계산하고 거부 횟수를 남긴다."""
    y = np.asarray(y)
    score = np.asarray(score, float)
    if len(np.unique(y)) < 2:
        return {"point": None, "lo": None, "hi": None, "definable": False, "n_rejected": 0, "B": B, "seed": seed}
    idx, n_rej = bootstrap_idx_nondegenerate(y, B, seed)
    vals = np.array([auroc(score[i], y[i]) for i in idx])
    point = auroc(score, y)
    return {"point": float(point), "lo": float(np.percentile(vals, alpha_lo)), "hi": float(np.percentile(vals, alpha_hi)),
            "definable": True, "n_rejected": int(n_rej), "B": B, "seed": seed}


def diff_auroc_ci_safe(y, score_a, score_b, n, seed=30017, alpha_lo=2.5, alpha_hi=97.5, B=10000):
    y = np.asarray(y)
    score_a = np.asarray(score_a, float)
    score_b = np.asarray(score_b, float)
    if len(np.unique(y)) < 2:
        return {"point": None, "lo": None, "hi": None, "definable": False, "n_rejected": 0, "B": B, "seed": seed}
    idx, n_rej = bootstrap_idx_nondegenerate(y, B, seed)
    a = np.array([auroc(score_a[i], y[i]) for i in idx])
    b = np.array([auroc(score_b[i], y[i]) for i in idx])
    d = a - b
    point = auroc(score_a, y) - auroc(score_b, y)
    return {"point": float(point), "lo": float(np.percentile(d, alpha_lo)), "hi": float(np.percentile(d, alpha_hi)),
            "definable": True, "n_rejected": int(n_rej), "B": B, "seed": seed}


SPLIT_ALPHA = {"C": (2.5, 97.5), "E": (1.25, 98.75)}
ONE_BOX_ALPHA = (2.5, 97.5)  # 계획서: 한 박스 층은 항상 95% CI로 보고한다 (split과 무관)


def wilson(k, n):
    return metrics.wilson(k, n)


def compute_baseline_aurocs(rows, score_names=ALL_RISK_SCORES):
    y = [r["y_partial"] for r in rows]
    out = {}
    for name in score_names:
        s = [r[name] for r in rows]
        out[name] = auroc(s, y)
    return out


def pick_bstar(rows):
    """C에서 Q를 제외한 baseline 중 엄격한 사건 AUROC 최대 항목을 계획서 순서로 동점 처리해 선택한다."""
    aurocs = compute_baseline_aurocs(rows, ALL_RISK_SCORES)
    best_name, best_val = None, -1.0
    for name in ALL_RISK_SCORES:  # 목록 순서 = 동점 우선순위
        v = aurocs[name]
        if not math.isnan(v) and v > best_val + 1e-12:
            best_name, best_val = name, v
    return best_name, aurocs


def one_box_layer(rows):
    return [r for r in rows if r["n_pred"] == 1]


def h1_report(rows, bstar_name, split):
    """split: "C" -> 주비교 95%(2.5/97.5) CI, "E" -> 주비교 97.5%(1.25/98.75) CI (계획서 Evaluation 절).
    한 박스 층(Q AUROC와 그 Q-B* diff)은 split과 무관하게 항상 95% CI로 보고한다."""
    alpha_lo, alpha_hi = SPLIT_ALPHA[split]
    y = np.array([r["y_partial"] for r in rows])
    q = np.array([r["Q_continue_minus_close"] for r in rows])
    bstar = np.array([r[bstar_name] for r in rows])
    n = len(rows)

    diff = diff_auroc_ci_safe(y, q, bstar, n, seed=30017, alpha_lo=alpha_lo, alpha_hi=alpha_hi)
    auc_q_ci = auroc_ci_safe(y, q, n, seed=30017, alpha_lo=alpha_lo, alpha_hi=alpha_hi)
    auc_b_ci = auroc_ci_safe(y, bstar, n, seed=30017, alpha_lo=alpha_lo, alpha_hi=alpha_hi)
    cap_diff = capture_at_k_ceil(q.tolist(), y.tolist(), 0.2) - capture_at_k_ceil(bstar.tolist(), y.tolist(), 0.2)

    one = one_box_layer(rows)
    q1_ci = diff_q1 = None
    n1_events = int(sum(r["y_partial"] for r in one)) if one else 0
    if one and len({r["y_partial"] for r in one}) > 1:
        y1 = np.array([r["y_partial"] for r in one])
        q1 = np.array([r["Q_continue_minus_close"] for r in one])
        b1 = np.array([r[bstar_name] for r in one])
        n1 = len(one)
        q1_ci = auroc_ci_safe(y1, q1, n1, seed=30017, alpha_lo=ONE_BOX_ALPHA[0], alpha_hi=ONE_BOX_ALPHA[1])
        diff_q1 = diff_auroc_ci_safe(y1, q1, b1, n1, seed=30017, alpha_lo=ONE_BOX_ALPHA[0], alpha_hi=ONE_BOX_ALPHA[1])
    return {
        "n": n, "n_events": int(y.sum()), "bstar": bstar_name, "split": split,
        "ci_alpha": [alpha_lo, alpha_hi],
        "auroc_Q": auc_q_ci, "auroc_Bstar": auc_b_ci, "diff_Q_minus_Bstar": diff,
        "capture20_Q": capture_at_k_ceil(q.tolist(), y.tolist(), 0.2),
        "capture20_Bstar": capture_at_k_ceil(bstar.tolist(), y.tolist(), 0.2),
        "capture20_diff": cap_diff, "capture_k": math.ceil(0.2 * n),
        "n_one_box": len(one), "n_one_box_events": n1_events,
        "auroc_Q_one_box_layer": q1_ci,
        "diff_Q_minus_Bstar_one_box_layer": diff_q1,
    }


def f_new_boxes(o_boxes, f_boxes):
    """F_boxes[:len(o_boxes)]가 O와 정확히 같아야 한다(강제 전 prefix 보존). 아니면 None(무효)."""
    n = len(o_boxes)
    if f_boxes[:n] != o_boxes:
        return None
    return f_boxes[n:]


def decode_and_parse(tokenizer, suffix_ids, ended_eos):
    text = tokenizer.decode(suffix_ids, skip_special_tokens=False)
    return text, parse.parse_response(text, ended_eos)


def h2_and_cost_report(source_manifest, source_audit, f_records, split, tokenizer):
    """엄격한 사건의 회복률과 전체 모집단의 F1/FP/dup/invalid/길이 비용을 계산한다."""
    events_detail, recovered_ids = [], []
    cost_rows = []
    for pid, item in source_manifest["patients"][split].items():
        a = source_audit["patients"][split][pid]
        ev = a["event"]
        o_boxes = a["pred_boxes_seed17"]
        gt = a["gt_boxes_norm"]
        f = f_records.get((pid, "F"))
        if f is None:
            raise RuntimeError(f"missing F record for {pid}")
        f_text, f_parsed = decode_and_parse(tokenizer, f["suffix_ids"], f["ended_eos"])
        f_valid = f_parsed["status"] in parse.VALID
        f_boxes = f_parsed["boxes"] if f_valid else []
        new_boxes = f_new_boxes(o_boxes, f_boxes) if f_valid else None
        prefix_preserved = new_boxes is not None
        o_metrics = metrics.patient_metrics(o_boxes, gt, 0.3)
        o_metrics5 = metrics.patient_metrics(o_boxes, gt, 0.5)
        f_metrics = metrics.patient_metrics(f_boxes, gt, 0.3) if f_valid else None
        f_metrics5 = metrics.patient_metrics(f_boxes, gt, 0.5) if f_valid else None
        dup_f = parse.duplicates(f_boxes) if f_valid else None
        cost_rows.append({
            "id": pid, "category": a["category"], "n_gt": len(gt), "n_pred_O": len(o_boxes),
            "f_valid": f_valid, "f_prefix_preserved": prefix_preserved, "f_status": f_parsed["status"],
            "f_forced_applied": f.get("forced_token_applied"), "f_ended_eos": f["ended_eos"],
            "o_f1_03": o_metrics["f1"], "o_f1_05": o_metrics5["f1"], "o_recall_03": o_metrics["recall"],
            "o_tp_03": o_metrics["tp"], "o_fp_03": o_metrics["unmatched_pred"],
            "f_f1_03": f_metrics["f1"] if f_metrics else None, "f_f1_05": f_metrics5["f1"] if f_metrics5 else None,
            "f_recall_03": f_metrics["recall"] if f_metrics else None,
            "f_tp_03": f_metrics["tp"] if f_metrics else None, "f_fp_03": f_metrics["unmatched_pred"] if f_metrics else None,
            "f_n_pred": len(f_boxes) if f_valid else None, "f_dup": dup_f,
            "f_new_box_count": len(new_boxes) if new_boxes is not None else None,
            "f_runtime_s": f["runtime_s"], "f_n_attempts": f["n_attempts"], "f_final_cap": f["final_cap"],
        })
        if ev["y_partial"]:
            recovered = False
            if prefix_preserved and new_boxes:
                missed_gt = [gt[i] for i in ev["zero_overlap_gt_idx"]]
                pairs = metrics.match(new_boxes, missed_gt, 0.3)
                recovered = len(pairs) >= 1
            events_detail.append({"id": pid, "recovered": recovered, "f_valid": f_valid,
                                  "prefix_preserved": prefix_preserved,
                                  "n_new_boxes": len(new_boxes) if new_boxes is not None else None})
            if recovered:
                recovered_ids.append(pid)

    n_events = len(events_detail)
    n_recovered = len(recovered_ids)
    wilson_lo, wilson_hi = wilson(n_recovered, n_events) if n_events else (float("nan"), float("nan"))
    return {
        "n_events": n_events, "n_recovered": n_recovered,
        "recovery_rate": (n_recovered / n_events) if n_events else float("nan"),
        "wilson_95_lo": wilson_lo, "wilson_95_hi": wilson_hi,
        "events_detail": events_detail, "recovered_ids": recovered_ids,
        "cost_rows": cost_rows,
        "population_cost": population_cost_report(cost_rows),
    }


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return float(np.mean(xs)) if xs else float("nan")


def _median(xs):
    xs = [x for x in xs if x is not None]
    return float(np.median(xs)) if xs else float("nan")


def population_cost_report(cost_rows, seed=30017, B=10000):
    """전체 O/F 모집단의 F1/FP/추가 TP·FP/중복/invalid/길이·latency 비용 (계획서 Evaluation 절).

    invalid를 분모에서 제거하지 않는다: operational_* 배열은 f_valid=False에 0을 대입한다.
    파싱 불가능(F invalid)한 응답의 FP 개수는 세지 않고 별도로 undefined로 명시하며,
    유효 응답만의 FP 평균은 하한 성격임을 필드명(valid_responses_only)으로 표시한다.
    """
    n = len(cost_rows)
    invalid_n = sum(1 for r in cost_rows if not r["f_valid"])
    op_f1_03_f = np.array([r["f_f1_03"] if r["f_valid"] else 0.0 for r in cost_rows])
    op_f1_05_f = np.array([r["f_f1_05"] if r["f_valid"] else 0.0 for r in cost_rows])
    op_recall_03_f = np.array([r["f_recall_03"] if r["f_valid"] else 0.0 for r in cost_rows])
    o_f1_03 = np.array([r["o_f1_03"] for r in cost_rows])
    o_f1_05 = np.array([r["o_f1_05"] for r in cost_rows])
    o_recall_03 = np.array([r["o_recall_03"] for r in cost_rows])

    def op_f1_03(idx):
        return float(np.mean(op_f1_03_f[idx]))

    def base_f1_03(idx):
        return float(np.mean(o_f1_03[idx]))

    def op_f1_05(idx):
        return float(np.mean(op_f1_05_f[idx]))

    def base_f1_05(idx):
        return float(np.mean(o_f1_05[idx]))

    def op_recall(idx):
        return float(np.mean(op_recall_03_f[idx]))

    def base_recall(idx):
        return float(np.mean(o_recall_03[idx]))

    diff_f1_03 = paired_diff_ci(op_f1_03, base_f1_03, n, B=B, seed=seed)
    diff_f1_05 = paired_diff_ci(op_f1_05, base_f1_05, n, B=B, seed=seed)
    diff_recall = paired_diff_ci(op_recall, base_recall, n, B=B, seed=seed)

    valid_rows = [r for r in cost_rows if r["f_valid"]]
    n_valid = len(valid_rows)
    extra_tp = [r["f_tp_03"] - r["o_tp_03"] for r in valid_rows]
    extra_fp = [r["f_fp_03"] - r["o_fp_03"] for r in valid_rows]
    n_dup = sum(1 for r in valid_rows if (r["f_dup"] or 0) > 0)

    return {
        "n": n, "n_valid_f": n_valid, "n_invalid_f": invalid_n, "invalid_rate": invalid_n / n if n else float("nan"),
        "operational_note": "F invalid(파싱 불가) 응답은 F1/recall=0으로 처리한 하한값이다 (분모에서 제거하지 않음).",
        "operational_f1_03_F": op_f1_03(np.arange(n)), "f1_03_O": base_f1_03(np.arange(n)),
        "diff_operational_f1_03_F_minus_O": diff_f1_03,
        "operational_f1_05_F": op_f1_05(np.arange(n)), "f1_05_O": base_f1_05(np.arange(n)),
        "diff_operational_f1_05_F_minus_O": diff_f1_05,
        "operational_recall_03_F": op_recall(np.arange(n)), "recall_03_O": base_recall(np.arange(n)),
        "diff_operational_recall_03_F_minus_O": diff_recall,
        "fp_per_patient_valid_responses_only": {
            "note": "invalid 응답의 FP는 정의되지 않아 제외했다; 아래 평균은 전체 환자당 FP의 하한 성격이다.",
            "o_fp_mean_over_valid_f_subset": _mean([r["o_fp_03"] for r in valid_rows]),
            "f_fp_mean": _mean([r["f_fp_03"] for r in valid_rows]),
            "n_valid": n_valid, "n_fp_undefined_due_to_invalid": invalid_n,
        },
        "extra_tp_mean_over_valid": _mean(extra_tp), "extra_fp_mean_over_valid": _mean(extra_fp),
        "n_duplicates_gt0_over_valid": n_dup, "duplicate_rate_over_valid": (n_dup / n_valid) if n_valid else float("nan"),
        "f_runtime_s_mean": _mean([r["f_runtime_s"] for r in cost_rows]),
        "f_runtime_s_median": _median([r["f_runtime_s"] for r in cost_rows]),
        "f_n_attempts_mean": _mean([r["f_n_attempts"] for r in cost_rows]),
        "f_final_cap_counts": {str(c): sum(1 for r in cost_rows if r["f_final_cap"] == c)
                               for c in sorted({r["f_final_cap"] for r in cost_rows})},
    }
