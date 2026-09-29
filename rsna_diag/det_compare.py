"""개발비교800(iter_010 confirm) detector vs 저장 base/SFT 비교 (기본 medgemma env).

원본: results/iter_034/analyze_confirm800.py (sha256 88342a8d...)와 그 원본 iter_033 analyze_confirm800.py,
results/iter_034/verify_confirm_sft.py (sha256 c11799c8...). metric·parser·utility는 기존 승인 모듈(sft_eval·metrics·parse)을 쓴다.
iter_035 변경:
- 저장 SFT/base 출력: 중복을 덮어쓰지 않고 오류, 예상 (id,prompt) 집합·adapter·protocol·completion·영상 hash 대조,
  iter_012 확인 주수치(seed별 F1@0.3) 재현.
- detector: det_eval.load_verified로 completion·checkpoint·manifest 연결을 검사하고, 잠긴 선택 파일의 checkpoint·
  threshold만 사용한다. 누락 record는 오류.
- 주비교: 양성 400명 환자 평균 F1@0.3·F1@0.5의 detector17−B0 차이에 실제 97.5% paired bootstrap CI
  (1.25/98.75 percentile, 10,000회 공통 환자 resample). 원본은 95% 함수를 97.5 label로 불렀다. 기존 metrics.paired_boot_ci는
  수정하지 않는다.
- FP/환자(전체 N 하한, valid-only), FP 보유율과 차이의 95% CI, lesion recall, 전체 미검출, invalid, GT 개수·union 면적·
  개별 GT 면적(train 기준 삼분위) 층, FP budget별 detector recall.
- 상보성: exhaustive matching(metrics.match)의 GT identity로 both/det-only/SFT-only/both-miss, 비율 CI는 resample마다
  분자·분모 재계산. 민감도: 동점 규칙 반대(높은 pred index 우선), best-IoU cover, 다른 SFT seed·detector seed·FP budget.
"""
import argparse
import glob
import hashlib
import json
import os
import sys

import numpy as np

BASE = "/SSD1_1TB/home/milab/daniel/08_medgemma/research"
sys.path.insert(0, BASE)
from rsna_diag import geometry as G, metrics as M, parse as PA, sft_eval as SE  # noqa: E402

IT010 = f"{BASE}/results/iter_010/manifests"
IT012 = f"{BASE}/results/iter_012"
ADAPTERS = {17: "e13f3c4461b826a060c90dfe4e4ee4c2ebac36a08f84be1a45a37495816cec11",
            29: "9185488c82b6efd6fe53df3c92ca5f4b6efb3e059d0f36eeb3c9ee9f911a99cc",
            43: "881ca7fda81669374993893f85b26ff91a74b9762a10edbb1c428c991ad735b7"}
PROTOCOL = "797ae7074325d714cf1c54c2d4fb1cc6904dc0f5babd18e817195d219b4d4a92"
B = 10000
BOOT_SEED = 20260924


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def load_stored(run_dir, ids, prompts, adapter, infer):
    recs = {}
    files = sorted(glob.glob(f"{run_dir}/gen_worker*.jsonl"))
    for p in files:
        for l in open(p):
            r = json.loads(l)
            k = (r["id"], r["prompt_name"])
            if k in recs:
                raise ValueError(f"duplicate stored record {k} in {run_dir}")
            recs[k] = r
    exp = {(i, pr) for i in ids for pr in prompts}
    if set(recs) != exp:
        raise ValueError(f"{run_dir}: stored set != expected (missing {len(exp - set(recs))}, extra {len(set(recs) - exp)})")
    bad = [k for k, r in recs.items() if r["adapter_digest"] != adapter or r["protocol_digest"] != PROTOCOL
           or r["image_file_sha256"] != infer[k[0]]["file_sha256"]]
    if bad:
        raise ValueError(f"{run_dir}: provenance mismatch for {len(bad)} records e.g. {bad[:2]}")
    comp = json.load(open(f"{run_dir}/completion.json"))
    if comp["n_actual_unique"] != len(exp) or comp["n_missing"] or comp["n_duplicate"] or comp["adapter_digest"] != adapter:
        raise ValueError(f"{run_dir}: completion inconsistent")
    return recs, {"files": {os.path.basename(p): sha(p) for p in files}, "n": len(recs)}


def boot_ci(d, idx, lo, hi):
    m = d[idx].mean(axis=1)
    return [float(np.percentile(m, lo)), float(np.percentile(m, hi))]


def ratio_ci(num, den, idx):
    rs = num[idx].sum(axis=1) / den[idx].sum(axis=1)
    return [float(np.percentile(rs, 2.5)), float(np.percentile(rs, 97.5))]


def boxes_valid(pred):
    return pred["boxes"] if pred["status"] in PA.VALID else []


def match_rev(pred, gt, thr):
    """동점 민감도: pred 순서를 뒤집어 metrics.match를 적용(높은 index 우선) 후 원래 index로 환원."""
    n = len(pred)
    pairs = M.match(list(reversed(pred)), gt, thr)
    return [(gi, n - 1 - pi) for gi, pi in pairs]


def gt_hits(pred, g, thr, mode):
    if not pred or not g:
        return set()
    if mode == "exact":
        return {gi for gi, _ in M.match(pred, g, thr)}
    if mode == "rev":
        return {gi for gi, _ in match_rev(pred, g, thr)}
    if mode == "cover":
        return {gi for gi, gb in enumerate(g) if any(M.iou(p, gb) >= thr for p in pred)}
    raise ValueError(mode)


def complementarity(det, sft, gt, pos, thr, idx, mode="exact"):
    rows = []
    for i in pos:
        g = [b["yxyx_norm"] for b in gt[i]["boxes"]]
        dh, sh = gt_hits(boxes_valid(det[i]), g, thr, mode), gt_hits(boxes_valid(sft[i]), g, thr, mode)
        n = len(g)
        rows.append([len(dh & sh), len(dh - sh), len(sh - dh), n - len(dh | sh), n])
    a = np.array(rows, float)
    tot = a[:, 4].sum()
    out = {"total_gt": int(tot), "both_hit": int(a[:, 0].sum()), "detector_only": int(a[:, 1].sum()),
           "sft_only": int(a[:, 2].sum()), "both_miss": int(a[:, 3].sum()),
           "n_patients_with_det_only": int((a[:, 1] > 0).sum()), "n_patients_with_sft_only": int((a[:, 2] > 0).sum())}
    for k, c in (("detector_only", 1), ("sft_only", 2), ("both_miss", 3), ("both_hit", 0)):
        out[f"{k}_rate"] = float(a[:, c].sum() / tot)
        out[f"{k}_rate_ci95"] = ratio_ci(a[:, c], a[:, 4], idx)
    out["gt_union_recall"] = float((a[:, 0] + a[:, 1] + a[:, 2]).sum() / tot)
    return out, a


def fp_stats(preds, gt, ids, thr=0.3):
    allv, validv = [], []
    for i in ids:
        g = [b["yxyx_norm"] for b in gt[i]["boxes"]]
        if preds[i]["status"] in PA.VALID:
            pb = preds[i]["boxes"]
            fp = len(pb) - (M.patient_metrics(pb, g, thr)["tp"] if pb and g else 0)
            allv.append(fp); validv.append(fp)
        else:
            allv.append(0)  # invalid: 관측 가능한 FP 없음 → 전체 N 평균은 하한
    return np.array(allv, float), {"fp_per_patient_all_n_lower_bound": float(np.mean(allv)),
                                   "fp_per_patient_valid_only": float(np.mean(validv)) if validv else None,
                                   "frac_with_fp_all_n": float(np.mean([x > 0 for x in allv])),
                                   "n_all": len(allv), "n_valid": len(validv)}


def lesion_stats(preds, gt, pos, thr):
    tp = n = miss_all = inv = 0
    for i in pos:
        g = [b["yxyx_norm"] for b in gt[i]["boxes"]]
        pb = boxes_valid(preds[i])
        t = M.patient_metrics(pb, g, thr)["tp"] if pb else 0
        tp += t; n += len(g); miss_all += (t == 0); inv += preds[i]["status"] not in PA.VALID
    return {"lesion_recall": tp / n, "tp": tp, "n_gt": n, "patients_all_missed": miss_all,
            "patients_all_missed_rate": miss_all / len(pos), "invalid_positive": inv}


def indiv_area_edges(gt, train_ids):
    a = [M.area(b["yxyx_norm"]) / 1e6 for i in train_ids if gt[i]["category"] == "opacity" for b in gt[i]["boxes"]]
    return [float(np.quantile(a, 1 / 3)), float(np.quantile(a, 2 / 3))]


def strata(det, sft, gt, pos, union_edges, gt_edges, idx_fn):
    out = {}
    def f1s(preds, ids, thr):
        return np.array([M.patient_metrics(boxes_valid(preds[i]), [b["yxyx_norm"] for b in gt[i]["boxes"]], thr)["f1"] for i in ids])
    groups = {"n_gt=1": [i for i in pos if len(gt[i]["boxes"]) == 1], "n_gt=2": [i for i in pos if len(gt[i]["boxes"]) == 2],
              "n_gt>=3": [i for i in pos if len(gt[i]["boxes"]) >= 3]}
    ua = {i: M.union_area([b["yxyx_norm"] for b in gt[i]["boxes"]]) / 1e6 for i in pos}
    for k, name in enumerate(("small", "medium", "large")):
        groups[f"union_area_{name}"] = [i for i in pos if int(np.digitize(ua[i], union_edges)) == k]
    for name, ids in groups.items():
        if not ids:
            out[name] = {"n": 0}
            continue
        r = {"n": len(ids)}
        for thr in (0.3, 0.5):
            d, s = f1s(det, ids, thr), f1s(sft, ids, thr)
            r[f"det_f1@{thr}"], r[f"b0_f1@{thr}"] = float(d.mean()), float(s.mean())
            r[f"diff_f1@{thr}"] = float((d - s).mean())
            r[f"diff_f1@{thr}_ci95"] = boot_ci(d - s, idx_fn(len(ids)), 2.5, 97.5)
        out[name] = r
    # 개별 GT 면적 삼분위: lesion recall
    for k, name in enumerate(("small", "medium", "large")):
        for thr in (0.3, 0.5):
            dn = sn = n = 0
            for i in pos:
                g = [b["yxyx_norm"] for b in gt[i]["boxes"]]
                dh, sh = gt_hits(boxes_valid(det[i]), g, thr, "exact"), gt_hits(boxes_valid(sft[i]), g, thr, "exact")
                for gi, gb in enumerate(g):
                    if int(np.digitize(M.area(gb) / 1e6, gt_edges)) == k:
                        n += 1; dn += gi in dh; sn += gi in sh
            out.setdefault(f"indiv_gt_area_{name}", {"n_gt": n})[f"lesion_recall@{thr}"] = {"det": dn / n if n else None, "b0": sn / n if n else None}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selection17", required=True)
    ap.add_argument("--confirm_dir17", required=True)
    ap.add_argument("--extra_det", nargs="*", default=[], help="seed:selection.json:confirm_dir")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        raise FileExistsError(a.out)
    from rsna_diag import det_eval as E, det_lib as D
    gt, infer = D.load_gt_infer()
    ids = json.load(open(f"{IT010}/confirm_ids.json"))
    train_ids = json.load(open(f"{IT010}/train_ids.json"))
    pos = [i for i in ids if gt[i]["category"] == "opacity"]
    cats = {c: [i for i in ids if gt[i]["category"] == c] for c in ("opacity", "normal", "not_normal_no_opacity")}
    union_edges = json.load(open(f"{BASE}/results/iter_033/data/area_edges.json"))["train_positive_area_tertile_edges"]
    if [round(x, 12) for x in union_edges] != [round(x, 12) for x in SE.area_edges(gt, train_ids)]:
        raise ValueError("union-area edges differ from train recomputation")
    gt_edges = indiv_area_edges(gt, train_ids)
    out = {"n_confirm": len(ids), "n_positive": len(pos), "note": "confirm800은 이전 반복의 개발 비교에 쓰인 집단이며 독립 확인이 아니다.",
           "union_area_edges_train": union_edges, "indiv_gt_area_edges_train": gt_edges}

    # ---- 저장 VLM 출력
    stored = {}
    base_recs, prov = load_stored(f"{IT012}/confirm_base", ids, ("official_long", "concise"), None, infer)
    out["provenance"] = {"base": prov}
    for p in ("official_long", "concise"):
        stored[f"base_{p}"] = SE.parse_records(base_recs, ids, p, strict=True)
    for s in (17, 29, 43):
        recs, prov = load_stored(f"{IT012}/confirm_sft_seed{s}", ids, ("concise",), ADAPTERS[s], infer)
        out["provenance"][f"sft{s}"] = prov
        stored[f"sft{s}"] = SE.parse_records(recs, ids, "concise", strict=True)
    ref = json.load(open(f"{IT012}/final/confirm_result.json"))["primary"]["per_seed_f1@0.3"]

    # ---- detector
    def load_det(selp, cdir):
        sel = json.load(open(selp))
        raw, comp, rid = E.load_verified(cdir, "confirm800", sel["selected_checkpoint"])
        if comp["checkpoint_sha256"] != sel["selected_checkpoint_sha256"] or rid != ids:
            raise ValueError("detector confirm output not linked to locked selection")
        thr = sel["selected"]["threshold"]
        return raw, D.preds_to_norm_yxyx(raw, gt, thr), sel, comp
    raw17, det17, sel17, comp17 = load_det(a.selection17, a.confirm_dir17)
    out["provenance"]["detector17"] = {"selection": a.selection17, "selection_sha256": sha(a.selection17),
                                       "confirm_dir": os.path.abspath(a.confirm_dir17),
                                       "checkpoint_sha256": comp17["checkpoint_sha256"],
                                       "raw_preds_sha256": comp17["raw_preds_sha256"], "threshold": sel17["selected"]["threshold"]}
    models = {"detector17": det17, **stored}
    extra = {}
    for item in a.extra_det:
        s, selp, cdir = item.split(":", 2)
        raw_x, det_x, sel_x, comp_x = load_det(selp, cdir)
        models[f"detector{s}"] = det_x
        extra[s] = (raw_x, sel_x)
        out["provenance"][f"detector{s}"] = {"selection": selp, "checkpoint_sha256": comp_x["checkpoint_sha256"],
                                             "threshold": sel_x["selected"]["threshold"]}

    out["summary"] = {}
    for name, pr in models.items():
        sm = SE.summarize(pr, gt, ids, edges=union_edges)
        out["summary"][name] = {k: sm[k] for k in ("f1@0.3", "f1@0.5", "precision@0.3", "recall@0.3", "utility",
                                                    "status_all", "positive_valid_empty", "neg_Normal",
                                                    "neg_NoOpacity/NotNormal", "by_n_gt", "by_gt_area_tertile")}
        out["summary"][name]["lesion@0.3"] = lesion_stats(pr, gt, pos, 0.3)
        out["summary"][name]["lesion@0.5"] = lesion_stats(pr, gt, pos, 0.5)
        _, fs = fp_stats(pr, gt, ids)
        out["summary"][name]["fp_all800"] = fs
        out["summary"][name]["fp_by_category"] = {c: fp_stats(pr, gt, cids)[1] for c, cids in cats.items()}
    out["sft_reproduction_vs_iter012"] = {f"sft{s}": {"now": out["summary"][f"sft{s}"]["f1@0.3"], "iter012": ref[f"sft_seed{s}"],
                                                      "match": abs(out["summary"][f"sft{s}"]["f1@0.3"] - ref[f"sft_seed{s}"]) < 1e-12}
                                           for s in (17, 29, 43)}

    # ---- 주비교: 97.5% paired CI
    idx = M.bootstrap_indices(len(pos), B=B, seed=BOOT_SEED)
    _, ppd = SE.per_patient(det17, gt, ids)
    p0, ppb = SE.per_patient(stored["sft17"], gt, ids)
    assert p0 == pos
    prim = {}
    for k in ("f1@0.3", "f1@0.5"):
        d = ppd[k] - ppb[k]
        prim[k] = {"diff": float(d.mean()), "ci97.5": boot_ci(d, idx, 1.25, 98.75), "ci95": boot_ci(d, idx, 2.5, 97.5),
                   "det": float(ppd[k].mean()), "b0": float(ppb[k].mean())}
    out["primary_detector17_minus_B0"] = {**prim, "B": B, "seed": BOOT_SEED, "unit": "positive patient (n=400)",
                                          "percentiles": "97.5% CI = [1.25, 98.75]"}
    out["other_pairs_positive"] = {}
    for name in [m for m in models if m not in ("detector17", "sft17")]:
        _, pp = SE.per_patient(models[name], gt, ids)
        out["other_pairs_positive"][f"detector17_minus_{name}"] = {
            k: {"diff": float((ppd[k] - pp[k]).mean()), "ci95": boot_ci(ppd[k] - pp[k], idx, 2.5, 97.5)} for k in ("f1@0.3", "f1@0.5")}
        if name.startswith("detector"):
            out["other_pairs_positive"][f"{name}_minus_B0"] = {
                k: {"diff": float((pp[k] - ppb[k]).mean()), "ci97.5": boot_ci(pp[k] - ppb[k], idx, 1.25, 98.75)} for k in ("f1@0.3", "f1@0.5")}

    # ---- FP 증가 95% CI (전체 800, 전체 N 하한 기준)
    idx800 = M.bootstrap_indices(len(ids), B=B, seed=BOOT_SEED)
    fd, _ = fp_stats(det17, gt, ids)
    fb, _ = fp_stats(stored["sft17"], gt, ids)
    out["fp_increase_detector17_minus_B0_all800"] = {"diff": float((fd - fb).mean()), "ci95": boot_ci(fd - fb, idx800, 2.5, 97.5),
                                                     "note": "B0 invalid는 FP 0으로 세는 전체 N 하한 기준"}
    out["fp_increase_by_category"] = {}
    for c, cids in cats.items():
        a1, _ = fp_stats(det17, gt, cids); a2, _ = fp_stats(stored["sft17"], gt, cids)
        out["fp_increase_by_category"][c] = {"diff": float((a1 - a2).mean()),
                                             "ci95": boot_ci(a1 - a2, M.bootstrap_indices(len(cids), B=B, seed=BOOT_SEED), 2.5, 97.5)}

    # ---- FP budget operating points (validation에서 고정)
    out["fp_budget_detector17"] = {}
    for b, r in sel17["fp_budgets"].items():
        if r is None:
            out["fp_budget_detector17"][b] = None
            continue
        pr = D.preds_to_norm_yxyx(raw17, gt, r["threshold"])
        out["fp_budget_detector17"][b] = {"threshold": r["threshold"], "val_fp": r["fp_per_patient"],
                                          "lesion@0.3": lesion_stats(pr, gt, pos, 0.3), "fp_all800": fp_stats(pr, gt, ids)[1],
                                          "f1@0.3": SE.summarize(pr, gt, ids)["f1@0.3"]}

    # ---- 상보성
    comp = {}
    for thr in (0.3, 0.5):
        c, arr = complementarity(det17, stored["sft17"], gt, pos, thr, idx)
        comp[f"iou{thr}"] = c
        comp[f"iou{thr}_tie_reversed"] = complementarity(det17, stored["sft17"], gt, pos, thr, idx, "rev")[0]
        comp[f"iou{thr}_best_iou_cover"] = complementarity(det17, stored["sft17"], gt, pos, thr, idx, "cover")[0]
        for s in (29, 43):
            comp[f"iou{thr}_vs_sft{s}"] = complementarity(det17, stored[f"sft{s}"], gt, pos, thr, idx)[0]
        for s in extra:
            comp[f"iou{thr}_detector{s}_vs_sft17"] = complementarity(models[f"detector{s}"], stored["sft17"], gt, pos, thr, idx)[0]
        for b, r in (out["fp_budget_detector17"] or {}).items():
            if r:
                pr = D.preds_to_norm_yxyx(raw17, gt, r["threshold"])
                comp[f"iou{thr}_fpbudget{b}"] = complementarity(pr, stored["sft17"], gt, pos, thr, idx)[0]
    out["complementarity"] = comp
    out["strata"] = strata(det17, stored["sft17"], gt, pos, union_edges, gt_edges,
                           lambda n: M.bootstrap_indices(n, B=B, seed=BOOT_SEED))

    # ---- 사전 판정 기준(비용 조건은 latency 결과와 합쳐 보고서에서 판정)
    c3 = comp["iou0.3"]
    out["criteria"] = {
        "detector_f1_ci97.5_lower_gt0_both": all(prim[k]["ci97.5"][0] > 0 for k in prim),
        "detector_point_diff_ge_0.03_any": any(prim[k]["diff"] >= 0.03 for k in prim),
        "fp_increase_ci95_upper_le_0.05": out["fp_increase_detector17_minus_B0_all800"]["ci95"][1] <= 0.05,
        "sft_only_rate_ci95_upper_le_0.05@0.3": c3["sft_only_rate_ci95"][1] <= 0.05,
        "complementarity_one_side_ge_5pct_and_ge20patients@0.3": {
            "detector_only": c3["detector_only_rate"] >= 0.05 and c3["n_patients_with_det_only"] >= 20 and c3["detector_only_rate_ci95"][0] > 0,
            "sft_only": c3["sft_only_rate"] >= 0.05 and c3["n_patients_with_sft_only"] >= 20 and c3["sft_only_rate_ci95"][0] > 0},
        "sft_advantage_any_f1_ci97.5_upper_lt0": any(prim[k]["ci97.5"][1] < 0 for k in prim),
    }
    json.dump(out, open(a.out, "w"), indent=2)
    print(json.dumps({"primary": out["primary_detector17_minus_B0"], "fp_increase": out["fp_increase_detector17_minus_B0_all800"],
                      "comp@0.3": {k: c3[k] for k in ("detector_only_rate", "sft_only_rate", "both_miss_rate",
                                                       "detector_only_rate_ci95", "sft_only_rate_ci95",
                                                       "n_patients_with_det_only", "n_patients_with_sft_only")},
                      "criteria": out["criteria"], "sft_repro": out["sft_reproduction_vs_iter012"]}, indent=1))


if __name__ == "__main__":
    main()
