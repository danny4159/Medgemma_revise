"""iter_013 평가: V200/V400 생성 결과의 S_loc·guardrail·선택·paired bootstrap·오류 분해.

- S_loc = 양성 환자 평균 (F1@0.3 + F1@0.5) / 2, 환자별 최대 cardinality one-to-one matching (metrics.patient_metrics 재사용).
- guardrail: 유효 출력률(전체) >= 0.99, 두 음성 층 각각 B0 대비 valid_empty율 감소 <= 0.03 (운영 guardrail; 임상 비열등성 아님).
- 선택: guardrail 통과 후보 중 S_loc 최대, 동률은 이른 checkpoint. 통과 후보가 없으면 선택 없음 (규칙 완화 금지).
- 모든 점수는 원시 응답(record)에서 parse_records(strict)로 계산하고, 누락·중복·잉여 요청은 eval_gate가 거부한다.
"""
import json
import os

import numpy as np

from . import eval_gate, inputs, lock_protocol, metrics as M, parse as PA, sft_eval

MANIFEST = "results/iter_010/manifests/infer_manifest.jsonl"
GT = "results/iter_010/manifests/gt_manifest.json"
V400_IDS = "results/iter_010/manifests/validation_ids.json"
B0_ADAPTER = "results/iter_012/train/lr2e-4_s17/epoch_05"
B0_PROTOCOL = "results/iter_012/protocols/main_protocol.json"
VALID_MIN = 0.99
NEG_DROP_MAX = 0.03


def load_ids_items(ids_path, split="validation"):
    return inputs.load_items(MANIFEST, GT, ids_path, split, exact=False)


def b0_records(protocol, items):
    """iter_012 B0 (seed17 lr2e-4 epoch5) V400 응답을 현재 입력·adapter·생성 config와의 호환성 검증 후 읽기 전용으로 재사용한다.
    iter_012 protocol 파일은 코드 hash 때문에 현재 verify할 수 없으므로 digest_of + 생성 config digest 일치만 사용한다 (eval_gate.verify_gen의 부모 경로)."""
    pdir = os.path.join(B0_ADAPTER, "val_gen")
    return eval_gate.verify_gen(os.path.join("results/iter_013", "b0_v400_empty"), items, ["concise"], B0_ADAPTER, protocol, pdir, B0_PROTOCOL,
                                require_completion=False)


def preds_of(recs, ids):
    return sft_eval.parse_records(recs, ids, "concise", strict=True)


def s_loc_arrays(preds, gt, ids):
    pos, pp = sft_eval.per_patient(preds, gt, ids)
    return pos, (pp["f1@0.3"] + pp["f1@0.5"]) / 2, pp


def box_edges_train(gt, train_ids):
    a = np.array([M.area(b["yxyx_norm"]) / 1e6 for i in train_ids if gt[i]["category"] == "opacity" for b in gt[i]["boxes"]])
    return [float(np.quantile(a, 1 / 3)), float(np.quantile(a, 2 / 3))]


def detail(preds, gt, ids, aedges, bedges):
    """보고 항목 전체: F1/S_loc, valid_empty, 형식 실패·잘림, 예측 개수, 개별 box 크기별 recall, GT 개수별·union 면적별 성능."""
    summ = sft_eval.summarize(preds, gt, ids, aedges)
    pos, sl, pp = s_loc_arrays(preds, gt, ids)
    summ["S_loc"] = float(sl.mean()) if len(pos) else None
    ar = np.array([sft_eval.gt_area_frac(gt[i]) for i in pos])
    bins = np.digitize(ar, aedges)
    ng = np.array([len(gt[i]["boxes"]) for i in pos])
    summ["by_gt_area_tertile_S_loc"] = {n: {"n": int((bins == b).sum()), "S_loc": float(sl[bins == b].mean()) if (bins == b).any() else None}
                                        for b, n in enumerate(("small", "medium", "large"))}
    # iter_014 정정: iter_013의 "multi"는 GT==2만 집계해 GT>=3 환자를 누락했다. multi = GT>=2, ge3 = GT>=3 (별도 보고, multi의 부분집합)
    grp = (("single", ng == 1), ("multi", ng >= 2), ("ge3", ng >= 3))
    summ["by_n_gt_S_loc"] = {n: {"n": int(m.sum()), "S_loc": float(sl[m].mean()) if m.any() else None} for n, m in grp} if len(pos) else {}
    rec = {}
    for thr in (0.3, 0.5):
        hit = {"small": [0, 0], "medium": [0, 0], "large": [0, 0]}
        for i in pos:
            pr = preds[i]
            pb = pr["boxes"] if pr["status"] in PA.VALID else []
            g = [b["yxyx_norm"] for b in gt[i]["boxes"]]
            matched = {gi for gi, _ in M.match(pb, g, thr)}
            for gi, b in enumerate(g):
                t = ("small", "medium", "large")[int(np.digitize(M.area(b) / 1e6, bedges))]
                hit[t][1] += 1
                hit[t][0] += gi in matched
        rec[f"recall@{thr}_by_box_size"] = {t: {"matched": v[0], "n_gt_boxes": v[1], "recall": v[0] / v[1] if v[1] else None} for t, v in hit.items()}
    summ.update(rec)
    summ["box_size_edges_train"] = bedges
    summ["n_pred_boxes_mean_all"] = float(np.mean([len(preds[i]["boxes"]) for i in ids]))
    return summ


def guardrail(summ, b0_summ):
    """returns dict(ok, valid_rate, neg drops)"""
    d = {"valid_rate_all": summ["valid_rate_all"]["rate"], "valid_ok": summ["valid_rate_all"]["rate"] >= VALID_MIN}
    ok = d["valid_ok"]
    for _, nm in sft_eval.NEG:
        drop = b0_summ[f"neg_{nm}"]["valid_empty"]["rate"] - summ[f"neg_{nm}"]["valid_empty"]["rate"]
        d[f"neg_{nm}_valid_empty_drop_vs_B0"] = drop
        d[f"neg_{nm}_ok"] = drop <= NEG_DROP_MAX + 1e-12
        ok = ok and d[f"neg_{nm}_ok"]
    d["ok"] = bool(ok)
    return d


def select_checkpoint(cands, b0_summ):
    """cands: {name(order key): summary}, 이른 checkpoint 우선이 되도록 키는 update 수. returns (selected key or None, table)."""
    table, elig = {}, []
    for k in sorted(cands):
        g = guardrail(cands[k], b0_summ)
        table[k] = {"S_loc": cands[k]["S_loc"], "guardrail": g}
        if g["ok"]:
            elig.append(k)
    if not elig:
        return None, table
    return max(elig, key=lambda k: (round(cands[k]["S_loc"], 12), -k)), table


def paired_ci(preds_a, preds_b, gt, ids, B=10000, seed=20260924):
    """(a - b) S_loc의 환자 단위 paired bootstrap. returns dict."""
    pa, sa, _ = s_loc_arrays(preds_a, gt, ids)
    pb, sb, _ = s_loc_arrays(preds_b, gt, ids)
    if pa != pb:
        raise ValueError("patient order differs")
    idx = M.bootstrap_indices(len(pa), B, seed)
    m, lo, hi = M.paired_boot_ci(sa, sb, idx)
    return {"diff": m, "ci95": [lo, hi], "n_positive": len(pa), "B": B, "seed": seed}


def expand_rule(d_sel, c_sel, ci, d_v200_last_gain, d_guard_ok):
    """탐색 -> 확대 사전 기준. d_sel/c_sel: V400 S_loc (선택 checkpoint). ci: paired_ci 결과 (D-C). returns (bool, reason)."""
    diff = d_sel - c_sel
    if not d_guard_ok:
        return False, "D violates operating guardrail"
    if diff >= 0.03:
        return True, f"D-C {diff:.4f} >= 0.03"
    if ci["ci95"][1] >= 0.03 and d_v200_last_gain >= 0.01:
        return True, f"D-C {diff:.4f} < 0.03 but CI upper {ci['ci95'][1]:.4f} >= 0.03 and D V200 last-interval gain {d_v200_last_gain:.4f} >= 0.01"
    return False, f"D-C {diff:.4f}, CI upper {ci['ci95'][1]:.4f}, D V200 last gain {d_v200_last_gain:.4f}: below both criteria"
