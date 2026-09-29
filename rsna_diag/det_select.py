"""detector validation 선택·수렴 보완·조건부 seed 판정 (기본 medgemma env, torch 불필요).

원본: results/iter_034/select_checkpoint.py (sha256 15861b73...), results/iter_033/select_fp_budget.py (sha256 ed2edc7b...).
iter_035 변경:
- FP 누락·비유한 필수 수치는 오류(원본은 infinity로 대체).
- V100: epoch별 최고 threshold(utility→양성 F1@0.5→작은 전체 FP/환자→높은 threshold), epoch 선택(utility→F1@0.5→이른 epoch).
- 수렴 보완 규칙(계획 고정): epoch22→26 utility 또는 F1@0.5 증가≥0.01, 또는 epoch26 utility가 V100 최고점
  대비 0.01 이내이면서 마지막 4 epoch 평균 train loss가 이전 4 epoch보다 10% 이상 감소 → 12 epoch 연장.
- V400: checkpoint×threshold를 utility→양성 F1@0.5→작은 전체 FP/환자→이른 epoch→높은 threshold로 선택.
  선택점에서 후보 cap(100개)에 걸린 영상이 threshold 이상 점수로 잘렸을 가능성이 있으면 차단.
- FP budget 0.25/0.5/1.0: 선택 checkpoint에서 lesion recall@0.3 최대→작은 FP→높은 threshold.
- seed 판정: V400에서 선택 detector와 B0(iter_012 seed17 epoch05 저장 validation 출력)의 차이.
"""
import argparse
import hashlib
import json
import math
import os
import sys

BASE = "/SSD1_1TB/home/milab/daniel/08_medgemma/research"
sys.path.insert(0, BASE)
B0_VAL = f"{BASE}/results/iter_012/train/lr2e-4_s17/epoch_05/val_gen/gen_worker0.jsonl"
B0_VAL_SHA = "ac9718d1ab766d246a14507b69b5cfd6e063f2116403a90386cdd3250f87d33e"


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def finite(x):
    return x is not None and isinstance(x, (int, float)) and math.isfinite(x)


def rows_of(scan, epoch):
    out = []
    for t, s in scan["thresholds"].items():
        fp = scan["fp_per_patient"].get(t, {}).get("fp_per_patient_all_n")
        lr = scan["lesion_recall"].get(t, {})
        vals = {"utility": s["utility"], "f1@0.3": s["f1@0.3"], "f1@0.5": s["f1@0.5"], "fp_per_patient": fp,
                "lesion_recall@0.3": lr.get("lesion_recall@0.3")}
        for k, v in vals.items():
            if not finite(v):
                raise ValueError(f"missing/nonfinite {k} at epoch {epoch} threshold {t}")
        out.append({"epoch": int(epoch), "threshold": float(t), **vals,
                    "frac_patients_with_fp": scan["fp_per_patient"][t]["frac_patients_with_fp"]})
    return out


def load_scan(d):
    p = os.path.join(d, "threshold_scan.json")
    s = json.load(open(p))
    s["_path"] = p
    s["_sha256"] = sha(p)
    return s


def best_threshold(rows):
    return max(rows, key=lambda r: (r["utility"], r["f1@0.5"], -r["fp_per_patient"], r["threshold"]))


def cmd_v100(a):
    per = {}
    for item in a.scans:
        ep, d = item.split(":", 1)
        s = load_scan(d)
        if s["manifest"] != "V100":
            raise ValueError(f"{d} is not V100")
        b = best_threshold(rows_of(s, ep))
        per[int(ep)] = {**b, "scan": s["_path"], "scan_sha256": s["_sha256"]}
    best_ep = max(per, key=lambda e: (per[e]["utility"], per[e]["f1@0.5"], -e))
    out = {"per_epoch_best": per, "best_epoch": best_ep, "rule": "threshold: utility>F1@0.5>small FP>high thr; epoch: utility>F1@0.5>earlier"}
    json.dump(out, open(a.out, "w"), indent=2)
    print(json.dumps({"best_epoch": best_ep, "per_epoch": {e: [round(v["utility"], 4), round(v["f1@0.3"], 4), round(v["f1@0.5"], 4), v["threshold"]] for e, v in sorted(per.items())}}, indent=1))


def epoch_losses(run_dir, upe):
    from rsna_diag import det_train as T
    recs, _ = T.canonical_log(run_dir)
    if not recs or recs[0]["update"] != 0:
        raise ValueError("canonical log must start at 0")
    by = {}
    for r in recs:
        by.setdefault(r["update"] // upe + 1, []).append(r["loss"])
    return {e: sum(v) / len(v) for e, v in by.items() if len(v) == upe}


def cmd_extend(a):
    v = json.load(open(a.v100))["per_epoch_best"]
    v = {int(k): x for k, x in v.items()}
    if 22 not in v or 26 not in v:
        raise ValueError("need V100 epochs 22 and 26")
    rc = json.load(open(os.path.join(a.run_dir, "run_config.json")))
    L = epoch_losses(a.run_dir, rc["updates_per_epoch"])
    if any(e not in L for e in range(19, 27)):
        raise ValueError("need complete epochs 19..26 in canonical log")
    last4 = sum(L[e] for e in range(23, 27)) / 4
    prev4 = sum(L[e] for e in range(19, 23)) / 4
    top = max(x["utility"] for x in v.values())
    c1 = (v[26]["utility"] - v[22]["utility"] >= 0.01) or (v[26]["f1@0.5"] - v[22]["f1@0.5"] >= 0.01)
    c2 = (v[26]["utility"] >= top - 0.01) and (last4 <= 0.9 * prev4)
    out = {"extend": bool(c1 or c2), "cond_increase_22_26": c1, "cond_near_top_and_loss_drop": c2,
           "utility_22": v[22]["utility"], "utility_26": v[26]["utility"], "f1@0.5_22": v[22]["f1@0.5"],
           "f1@0.5_26": v[26]["f1@0.5"], "v100_top_utility": top, "mean_loss_epochs19_22": prev4,
           "mean_loss_epochs23_26": last4, "loss_ratio": last4 / prev4, "epoch_mean_loss": L}
    json.dump(out, open(a.out, "w"), indent=2)
    print(json.dumps({k: v for k, v in out.items() if k != "epoch_mean_loss"}, indent=1))


def cap_problem(scan, thr, raw_dir):
    """선택 threshold 이상 점수를 가진 box가 100개 cap에서 잘렸을 가능성: cap에 도달한 영상의 최저 점수≥thr."""
    raw = json.load(open(os.path.join(raw_dir, "raw_preds.json")))
    hits = [i for i, r in raw.items() if len(r["scores"]) >= 100 and min(r["scores"]) >= thr]
    return hits


def cmd_v400(a):
    rows = []
    scans = {}
    for item in a.scans:
        ep, d = item.split(":", 1)
        s = load_scan(d)
        if s["manifest"] != "V400":
            raise ValueError(f"{d} is not V400")
        scans[int(ep)] = (d, s)
        rows += rows_of(s, ep)
    sel = max(rows, key=lambda r: (r["utility"], r["f1@0.5"], -r["fp_per_patient"], -r["epoch"], r["threshold"]))
    d, s = scans[sel["epoch"]]
    cap_hits = cap_problem(s, sel["threshold"], d)
    ep_rows = [r for r in rows if r["epoch"] == sel["epoch"]]
    budgets = {}
    for b in (0.25, 0.5, 1.0):
        ok = [r for r in ep_rows if r["fp_per_patient"] <= b]
        if not ok:
            budgets[str(b)] = None
            continue
        r = max(ok, key=lambda r: (r["lesion_recall@0.3"], -r["fp_per_patient"], r["threshold"]))
        budgets[str(b)] = {"threshold": r["threshold"], "lesion_recall@0.3": r["lesion_recall@0.3"],
                           "fp_per_patient": r["fp_per_patient"], "cap_hits": len(cap_problem(s, r["threshold"], d))}
    out = {"selected": sel, "selected_raw_dir": d, "selected_checkpoint": s["completion"]["checkpoint"],
           "selected_checkpoint_sha256": s["completion"]["checkpoint_sha256"],
           "cap_problem_ids": cap_hits, "cap_ok": not cap_hits, "fp_budgets": budgets,
           "scans": {e: {"dir": dd, "scan_sha256": ss["_sha256"]} for e, (dd, ss) in scans.items()},
           "rule": "utility>F1@0.5>small FP/patient(all N)>earlier epoch>higher threshold",
           "top10": sorted(rows, key=lambda r: (-r["utility"], -r["f1@0.5"], r["fp_per_patient"], r["epoch"], -r["threshold"]))[:10]}
    json.dump(out, open(a.out, "w"), indent=2)
    print(json.dumps({"selected": sel, "cap_ok": out["cap_ok"], "fp_budgets": budgets}, indent=1))


def det_vs_b0_val(raw_dir, thr):
    from rsna_diag import sft_eval as SE, metrics as M, det_lib as D
    gt, _ = D.load_gt_infer()
    ids = json.load(open(f"{BASE}/results/iter_010/manifests/validation_ids.json"))
    if sha(B0_VAL) != B0_VAL_SHA:
        raise ValueError("B0 validation output changed")
    recs = {}
    for l in open(B0_VAL):
        r = json.loads(l)
        k = (r["id"], r["prompt_name"])
        if k in recs:
            raise ValueError("duplicate B0 record")
        recs[k] = r
    b0 = SE.parse_records(recs, ids, "concise", strict=True)
    from rsna_diag import det_eval as E
    raw, comp, rid = E.load_verified(raw_dir, "V400")
    if rid != ids:
        raise ValueError("V400 ids differ from validation ids")
    det = D.preds_to_norm_yxyx(raw, gt, thr)
    sd, sb = SE.summarize(det, gt, ids), SE.summarize(b0, gt, ids)
    out = {"det_f1@0.3": sd["f1@0.3"], "det_f1@0.5": sd["f1@0.5"], "b0_f1@0.3": sb["f1@0.3"], "b0_f1@0.5": sb["f1@0.5"],
           "diff_f1@0.3": sd["f1@0.3"] - sb["f1@0.3"], "diff_f1@0.5": sd["f1@0.5"] - sb["f1@0.5"],
           "det_utility": sd["utility"], "b0_utility": sb["utility"]}
    pos = [i for i in ids if gt[i]["category"] == "opacity"]
    for thr_iou in (0.3, 0.5):
        do = so = tot = 0
        for i in pos:
            g = [b["yxyx_norm"] for b in gt[i]["boxes"]]
            db = det[i]["boxes"]
            bb = b0[i]["boxes"] if b0[i]["status"] in ("valid_nonempty", "valid_empty") else []
            dm = {gi for gi, _ in M.match(db, g, thr_iou)}
            bm = {gi for gi, _ in M.match(bb, g, thr_iou)}
            do += len(dm - bm); so += len(bm - dm); tot += len(g)
        out[f"det_only_rate@{thr_iou}"] = do / tot
        out[f"sft_only_rate@{thr_iou}"] = so / tot
    return out


def cmd_seed(a):
    sel = json.load(open(a.selection))
    r17 = det_vs_b0_val(sel["selected_raw_dir"], sel["selected"]["threshold"])
    out = {"seed17": r17, "selection17": a.selection}
    trig29 = (abs(r17["diff_f1@0.3"]) >= 0.03 or abs(r17["diff_f1@0.5"]) >= 0.03
              or r17["det_only_rate@0.3"] >= 0.05 or r17["sft_only_rate@0.3"] >= 0.05)
    out["train_seed29"] = bool(trig29)
    out["rule29"] = "|dF1@0.3|>=0.03 or |dF1@0.5|>=0.03 or det-only/SFT-only GT rate@IoU0.3>=0.05 (V400, vs B0)"
    if a.selection29:
        sel29 = json.load(open(a.selection29))
        r29 = det_vs_b0_val(sel29["selected_raw_dir"], sel29["selected"]["threshold"])
        out["seed29"] = r29
        flip = any((r17[k] > 0) != (r29[k] > 0) for k in ("diff_f1@0.3", "diff_f1@0.5"))
        mag = any(abs(r17[k] - r29[k]) >= 0.03 for k in ("diff_f1@0.3", "diff_f1@0.5"))
        out["train_seed43"] = bool(flip or mag)
        out["rule43"] = "sign of (det-B0) differs between seeds or |d17-d29|>=0.03 for F1@0.3 or F1@0.5"
    json.dump(out, open(a.out, "w"), indent=2)
    print(json.dumps(out, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("v100"); p.add_argument("--scans", nargs="+", required=True); p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_v100)
    p = sub.add_parser("extend"); p.add_argument("--v100", required=True); p.add_argument("--run_dir", required=True)
    p.add_argument("--out", required=True); p.set_defaults(func=cmd_extend)
    p = sub.add_parser("v400"); p.add_argument("--scans", nargs="+", required=True); p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_v400)
    p = sub.add_parser("seed"); p.add_argument("--selection", required=True); p.add_argument("--selection29", default=None)
    p.add_argument("--out", required=True); p.set_defaults(func=cmd_seed)
    a = ap.parse_args()
    for f in ("out",):
        if os.path.exists(getattr(a, f)):
            raise FileExistsError(f"refusing to overwrite {getattr(a, f)}")
    a.func(a)


if __name__ == "__main__":
    main()
