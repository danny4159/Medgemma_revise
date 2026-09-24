"""iter_010 환자별 평가: 생성 record(또는 보정/prior 예측)를 같은 metric으로 요약한다.

preds: {id: {"status": str, "boxes": [[y0,x0,y1,x1],...]}} — 형식 실패·잘림은 valid가 아니며 end-to-end에서 box 없음(F1=0)으로 계산한다.
GT 좌표 규약·matching·metric은 iter_009 승인 모듈(metrics.py, parse.py)을 그대로 쓴다.
"""
import numpy as np

from . import metrics as M, parse as PA

NEG = (("normal", "Normal"), ("not_normal_no_opacity", "NoOpacity/NotNormal"))


def parse_records(recs, ids, prompt):
    """recs: {(id, prompt): record}. 누락은 status='missing'."""
    out = {}
    for i in ids:
        r = recs.get((i, prompt))
        out[i] = ({"status": "missing", "boxes": []} if r is None
                  else PA.parse_response(r["suffix_text_raw"], r["ended_eos"]))
    return out


def gt_boxes(g):
    return [b["yxyx_norm"] for b in g["boxes"]]


def gt_area_frac(g):
    return M.union_area(gt_boxes(g)) / 1e6


def area_edges(gt, train_ids):
    """train 양성 GT 면적의 삼분위 경계 (2개 값)."""
    a = np.array([gt_area_frac(gt[i]) for i in train_ids if gt[i]["category"] == "opacity"])
    return [float(np.quantile(a, 1 / 3)), float(np.quantile(a, 2 / 3))]


def per_patient(preds, gt, ids):
    """양성 환자별 end-to-end 값. returns dict of arrays over positives (ids 순서)."""
    pos = [i for i in ids if gt[i]["category"] == "opacity"]
    cols = {"f1@0.3": [], "f1@0.5": [], "p@0.3": [], "r@0.3": [], "union_iou": []}
    for i in pos:
        pr = preds[i]
        pb = pr["boxes"] if pr["status"] in PA.VALID else []
        g = gt_boxes(gt[i])
        m3, m5 = M.patient_metrics(pb, g, 0.3), M.patient_metrics(pb, g, 0.5)
        cols["f1@0.3"].append(m3["f1"]); cols["f1@0.5"].append(m5["f1"])
        cols["p@0.3"].append(m3["precision"]); cols["r@0.3"].append(m3["recall"])
        cols["union_iou"].append(M.union_iou(pb, g))
    return pos, {k: np.array(v) for k, v in cols.items()}


def rate(k, n):
    lo, hi = M.wilson(k, n)
    return {"k": int(k), "n": int(n), "rate": (k / n if n else None), "wilson95": [lo, hi]}


def summarize(preds, gt, ids, edges=None):
    pos, pp = per_patient(preds, gt, ids)
    st = lambda i: preds[i]["status"]
    valid = lambda i: st(i) in PA.VALID
    d = {"n_patients": len(ids), "n_positive": len(pos),
         "f1@0.3": float(pp["f1@0.3"].mean()) if len(pos) else None, "f1@0.5": float(pp["f1@0.5"].mean()) if len(pos) else None,
         "precision@0.3": float(pp["p@0.3"].mean()) if len(pos) else None, "recall@0.3": float(pp["r@0.3"].mean()) if len(pos) else None,
         "union_iou": float(pp["union_iou"].mean()) if len(pos) else None,
         "valid_rate_all": rate(sum(valid(i) for i in ids), len(ids)),
         "valid_rate_positive": rate(sum(valid(i) for i in pos), len(pos)),
         "positive_valid_empty": rate(sum(st(i) == "valid_empty" for i in pos), len(pos)),
         "status_all": {s: sum(st(i) == s for i in ids) for s in sorted({st(i) for i in ids})},
         "truncated_all": sum(st(i) == "truncated" for i in ids)}
    vi = [k for k, i in enumerate(pos) if valid(i)]
    d["f1@0.3_valid_only"] = {"mean": float(pp["f1@0.3"][vi].mean()) if vi else None, "n": len(vi)}
    for cat, nm in NEG:
        neg = [i for i in ids if gt[i]["category"] == cat]
        d[f"neg_{nm}"] = {"valid_empty": rate(sum(st(i) == "valid_empty" for i in neg), len(neg)),
                          "extra_box": rate(sum(st(i) == "valid_nonempty" for i in neg), len(neg)),
                          "format_fail": rate(sum(not valid(i) for i in neg), len(neg))}
    n_gt = np.array([len(gt[i]["boxes"]) for i in pos])
    if len(pos):
        d["by_n_gt"] = {"single": {"n": int((n_gt == 1).sum()), "f1@0.3": float(pp["f1@0.3"][n_gt == 1].mean()) if (n_gt == 1).any() else None},
                        "multi": {"n": int((n_gt > 1).sum()), "f1@0.3": float(pp["f1@0.3"][n_gt > 1].mean()) if (n_gt > 1).any() else None}}
        if edges:
            ar = np.array([gt_area_frac(gt[i]) for i in pos])
            bins = np.digitize(ar, edges)
            d["by_gt_area_tertile"] = {name: {"n": int((bins == b).sum()), "f1@0.3": float(pp["f1@0.3"][bins == b].mean()) if (bins == b).any() else None}
                                       for b, name in enumerate(("small", "medium", "large"))}
    npred = [len(preds[i]["boxes"]) for i in pos if st(i) == "valid_nonempty"]
    d["n_pred_dist_positive_nonempty"] = {str(k): int(v) for k, v in zip(*np.unique(npred, return_counts=True))} if npred else {}
    d["mean_n_pred_vs_n_gt_positive_valid"] = ([float(np.mean([len(preds[i]["boxes"]) for i in pos if valid(i)])),
                                                float(np.mean([len(gt[i]["boxes"]) for i in pos if valid(i)]))] if vi else None)
    d["utility"] = utility(d)
    return d


def utility(d):
    """0.5*양성 평균 F1@0.3 + 0.25*Normal valid_empty율 + 0.25*NoOpacity/NotNormal valid_empty율 (계획 고정식)."""
    n1, n2 = d["neg_Normal"]["valid_empty"], d["neg_NoOpacity/NotNormal"]["valid_empty"]
    if d["f1@0.3"] is None or n1["rate"] is None or n2["rate"] is None:
        return None
    return 0.5 * d["f1@0.3"] + 0.25 * n1["rate"] + 0.25 * n2["rate"]
