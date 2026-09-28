"""iter_030 평가: 위험 baseline·Q·seed baseline AUROC/Capture, H2 회복률, F1/FP 부작용, bootstrap CI."""
import glob
import json
import math

import numpy as np

from . import metrics, parse
from .risk28_eval import auroc, capture_at_k, bootstrap_indices  # 범용 AUROC/Capture/bootstrap 재사용

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


def h1_report(rows, bstar_name):
    y = np.array([r["y_partial"] for r in rows])
    q = np.array([r["Q_continue_minus_close"] for r in rows])
    bstar = np.array([r[bstar_name] for r in rows])
    n = len(rows)

    def auc_q(idx):
        return auroc(q[idx], y[idx])

    def auc_b(idx):
        return auroc(bstar[idx], y[idx])
    diff = paired_diff_ci(auc_q, auc_b, n, seed=30017, alpha_lo=2.5, alpha_hi=97.5)
    auc_q_ci = metric_ci(auc_q, n, seed=30017)
    auc_b_ci = metric_ci(auc_b, n, seed=30017)
    cap_diff = capture_at_k(q.tolist(), y.tolist(), 0.2) - capture_at_k(bstar.tolist(), y.tolist(), 0.2)

    one = one_box_layer(rows)
    q1_ci = None
    if one and len({r["y_partial"] for r in one}) > 1:
        y1 = np.array([r["y_partial"] for r in one])
        q1 = np.array([r["Q_continue_minus_close"] for r in one])
        n1 = len(one)

        def auc_q1(idx):
            return auroc(q1[idx], y1[idx])
        q1_ci = metric_ci(auc_q1, n1, seed=30017)
    return {
        "n": n, "n_events": int(y.sum()), "bstar": bstar_name,
        "auroc_Q": auc_q_ci, "auroc_Bstar": auc_b_ci, "diff_Q_minus_Bstar": diff,
        "capture20_Q": capture_at_k(q.tolist(), y.tolist(), 0.2),
        "capture20_Bstar": capture_at_k(bstar.tolist(), y.tolist(), 0.2),
        "capture20_diff": cap_diff,
        "n_one_box": len(one), "n_one_box_events": int(sum(r["y_partial"] for r in one)),
        "auroc_Q_one_box_layer": q1_ci,
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
            "f_f1_03": f_metrics["f1"] if f_metrics else None, "f_f1_05": f_metrics5["f1"] if f_metrics5 else None,
            "f_recall_03": f_metrics["recall"] if f_metrics else None,
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
    }
