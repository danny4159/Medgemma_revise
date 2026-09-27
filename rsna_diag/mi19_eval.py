"""iter_019 평가: 형식 분해, IoU, wrong-instance 판정, H·pair success, CI. 실제 생성 record와 C/N baseline을 입력받는다."""
import glob
import json

import numpy as np

from . import metrics, parse as PA


def classify_response(rec):
    """returns dict: parse_status, n_boxes, box(단일 유효 box 또는 None)."""
    pr = PA.parse_response(rec["suffix_text_raw"], rec["ended_eos"])
    st = pr["status"]
    if st in PA.VALID:
        boxes = pr["boxes"]
        if len(boxes) == 1:
            return {"parse_status": st, "n_boxes": 1, "box": [float(v) for v in boxes[0]]}
        return {"parse_status": f"{st}_wrong_count", "n_boxes": len(boxes), "box": None}
    return {"parse_status": st, "n_boxes": None, "box": None}


def classify_pred(pred_box, target_gt_box, other_gts):
    """other_gts: [(label, box), ...]. returns dict target_iou, success flags, wrong-instance 판정."""
    candidates = [("__target__", target_gt_box)] + list(other_gts)
    ious = [(lab, metrics.iou(pred_box, b)) for lab, b in candidates]
    max_iou = max(i for _, i in ious)
    tied = [lab for lab, i in ious if abs(i - max_iou) < 1e-9]
    target_iou = dict(ious)["__target__"]
    is_wrong = target_iou <= 0.1 and len(tied) == 1 and tied[0] != "__target__" and max_iou >= 0.3
    return {"target_iou": target_iou, "success_0.5": target_iou >= 0.5, "success_0.3": target_iou >= 0.3,
            "is_wrong_instance": is_wrong, "wrong_instance_label": tied[0] if is_wrong else None, "max_iou_any": max_iou}


def load_records(out_dir):
    recs = {}
    for f in sorted(glob.glob(f"{out_dir}/gen_worker*.jsonl")):
        for ln in open(f):
            if ln.strip():
                r = json.loads(ln)
                if r["request_id"] in recs:
                    raise RuntimeError(f"duplicate request_id {r['request_id']} across worker files in {out_dir}")
                recs[r["request_id"]] = r
    return recs


def evaluate_condition(rows, records, manifest, condition_label):
    """rows: mi19_requests 행 목록(단일 condition). returns list of per-row eval dict (patient,label 포함)."""
    out = []
    for row in rows:
        rec = records.get(row["request_id"])
        pid, lab = row["patient"], row["label"]
        m = manifest[pid]
        inst = next(i for i in m["instances"] if i["label"] == lab)
        target_gt = inst["target_gt_norm"]
        other_gts = [(o["label"], o["box_norm"]) for o in m["other_gt_boxes_in_T_norm"]] + \
                    [(i["label"], i["target_gt_norm"]) for i in m["instances"] if i["label"] != lab]
        if rec is None:
            out.append({"patient": pid, "label": lab, "condition": condition_label, "missing": True})
            continue
        cls = classify_response(rec)
        row_out = {"patient": pid, "label": lab, "condition": condition_label, "missing": False, **cls}
        if cls["box"] is not None:
            row_out.update(classify_pred(cls["box"], target_gt, other_gts))
        else:
            row_out.update({"target_iou": None, "success_0.5": False, "success_0.3": False,
                            "is_wrong_instance": False, "wrong_instance_label": None, "max_iou_any": None})
        out.append(row_out)
    return out


def evaluate_baseline(manifest, patient_ids, condition_fn, condition_label):
    """condition_fn(manifest_entry, inst) -> (pred_box_norm or None, meta). C/N에 사용."""
    out = []
    for pid in patient_ids:
        m = manifest[pid]
        for inst in m["instances"]:
            lab = inst["label"]
            target_gt = inst["target_gt_norm"]
            other_gts = [(o["label"], o["box_norm"]) for o in m["other_gt_boxes_in_T_norm"]] + \
                        [(i["label"], i["target_gt_norm"]) for i in m["instances"] if i["label"] != lab]
            pred, meta = condition_fn(m, inst)
            row = {"patient": pid, "label": lab, "condition": condition_label, "missing": False,
                  "parse_status": meta.get("status", "ok"), "box": pred, "meta": meta}
            if pred is not None:
                row.update(classify_pred(pred, target_gt, other_gts))
            else:
                row.update({"target_iou": None, "success_0.5": False, "success_0.3": False,
                           "is_wrong_instance": False, "wrong_instance_label": None, "max_iou_any": None})
            out.append(row)
    return out


def pair_success_rate(rows):
    """condition 하나의 rows(patient,label 여러 개)에서 환자별 두 instance 모두 success_0.5인 비율."""
    by_pat = {}
    for r in rows:
        by_pat.setdefault(r["patient"], []).append(r)
    n, k = 0, 0
    per_patient = {}
    for pid, rs in by_pat.items():
        ok = len(rs) >= 2 and all(r.get("success_0.5") for r in rs)
        per_patient[pid] = ok
        n += 1
        k += int(ok)
    return {"n_patients": n, "n_both_success": k, "rate": k / n if n else float("nan"),
            "wilson_95": metrics.wilson(k, n), "per_patient": per_patient}


def compute_H(patients, o_rows, j_rt_rows, j_tr_rows):
    """H 사건: O 두 instance 모두 성공, J_RT/J_TR 모두 유효 단일 box이고 같은 wrong_instance_label을 가진 instance가 하나 이상."""
    o_by_pat = {}
    for r in o_rows:
        o_by_pat.setdefault(r["patient"], {})[r["label"]] = r
    jrt_by = {}
    for r in j_rt_rows:
        jrt_by.setdefault(r["patient"], {})[r["label"]] = r
    jtr_by = {}
    for r in j_tr_rows:
        jtr_by.setdefault(r["patient"], {})[r["label"]] = r
    events, detail = {}, {}
    for pid in patients:
        o_ok = pid in o_by_pat and all(r.get("success_0.5") for r in o_by_pat[pid].values()) and len(o_by_pat[pid]) >= 2
        has_wrong = False
        labs_hit = []
        if pid in jrt_by and pid in jtr_by:
            for lab in jrt_by[pid]:
                a, b = jrt_by[pid].get(lab), jtr_by[pid].get(lab)
                if a is None or b is None:
                    continue
                if a.get("box") is not None and b.get("box") is not None and a.get("is_wrong_instance") and b.get("is_wrong_instance"):
                    if a.get("wrong_instance_label") == b.get("wrong_instance_label") and a["wrong_instance_label"] is not None:
                        has_wrong = True
                        labs_hit.append(lab)
        ev = bool(o_ok and has_wrong)
        events[pid] = ev
        detail[pid] = {"o_ok": o_ok, "has_wrong": has_wrong, "labels_hit": labs_hit}
    n = len(patients)
    k = sum(1 for v in events.values() if v)
    return {"n": n, "k": k, "H": k / n if n else float("nan"), "wilson_95": metrics.wilson(k, n),
            "events": events, "detail": detail}


def paired_diff(rate_a_per_patient, rate_b_per_patient, patients, seed=19019, B=10000):
    """paired bootstrap: patients 순서로 정렬한 0/1 배열의 평균차 CI. 값이 모두 같은 discordance=0이면 discordant 쌍 수를 함께 보고한다."""
    a = np.array([1.0 if rate_a_per_patient.get(p) else 0.0 for p in patients])
    b = np.array([1.0 if rate_b_per_patient.get(p) else 0.0 for p in patients])
    idx = metrics.bootstrap_indices(len(patients), B=B, seed=seed)
    mean_diff, lo, hi = metrics.paired_boot_ci(a, b, idx)
    discordant = int(np.sum(a != b))
    n = len(patients)
    # discordant 비율의 95% 이항구간: paired 효과 차이의 CI가 아니라, discordance=0일 때
    # bootstrap CI가 [0,0]이 되는 것을 "모집단 효과 영점"으로 오독하지 않기 위한 별도 지표다.
    discordant_wilson_95 = metrics.wilson(discordant, n) if n else [float("nan"), float("nan")]
    return {"mean_diff": mean_diff, "ci95": [lo, hi], "n": n, "discordant_n": discordant,
           "discordant_rate": discordant / n if n else float("nan"), "discordant_wilson_95": discordant_wilson_95,
           "a_pos": int(a.sum()), "b_pos": int(b.sum())}
