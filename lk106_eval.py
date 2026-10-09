"""iter_106 평가: 두 소견 위치 집합 보존(I vs J12/J21), 반복 대조(R11/R22), 형식·종료, 비용.

주지표: 환자별 영역 recall = (IoU>=0.3 최대 일대일 matching으로 맞힌 main GT 수)/2. 형식 실패(coord_invalid/truncated)는 분모에 유지(recall 0).
사용: python lk106_eval.py --stage E32 --gen results/iter_106/gen/E32 --nshards 2 --ind-gen results/iter_105/gen/E32 --ind-shards 2 --out results/iter_106/eval/report_E32.json
D4는 --ind-gen 없이(I1/I2는 iter_106 D4 생성) 실행한다. 결과 파일은 새로 만들며 덮어쓰지 않는다.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

import lk106_run as R
import lk106_spec as S
from report86_common import ROOT, SEED, sha, sha_obj, save, read_jsonl_complete

BOOT_SEED, N_BOOT = 106017, 10000


def load_gen(gen, stage, nshards):
    sd = sha_obj(R.scientific_protocol(stage, "CURE", nshards))
    recs = {}
    for k in range(nshards):
        _, rr = R.verify_completion(R.shard_dir(gen, "CURE", k), stage, "CURE", k, nshards, sd)
        for r in rr:
            assert r["id"] not in recs, "duplicate request id across shards"
            recs[r["id"]] = r
    return recs, sd


def load_ind_from_iter105(gen, nshards):
    """iter_105 E32 독립 PG 출력 재사용. 현재 소스로 protocol이 일치하는 경우에만 완료 검증을 통과한다(lk105_run.verify_completion)."""
    import lk105_run as R5
    sd = sha_obj(R5.scientific_protocol("E32", "CURE", nshards))
    recs = {}
    for k in range(nshards):
        _, rr = R5.verify_completion(R5.shard_dir(gen, "CURE", k), "E32", "CURE", k, nshards, sd)
        for r in rr:
            if r["kind"] == "pg":
                key = r["id"].replace("|pg-S1", "|I1").replace("|pg-S2", "|I2")
                assert key not in recs
                recs[key] = r
    return recs, sd


def box_set(rec):
    p = S.parse_pg(rec["text"], rec["attempts"][-1]["ended_eos"])
    return p["status"], p["boxes"]


def slots_match(slots, preds, thr):
    """민감도: 각 GT slot은 main+extra 중 어느 box와 맞아도 된다. 예측 하나는 slot 하나에만 대응(일대일)."""
    adj = [[j for j, p in enumerate(preds) if any(S.iou(g, p) >= thr for g in sl)] for sl in slots]
    owner = {}

    def aug(i, seen):
        for j in adj[i]:
            if j in seen:
                continue
            seen.add(j)
            if j not in owner or aug(owner[j], seen):
                owner[j] = i
                return True
        return False
    for i in range(len(slots)):
        aug(i, set())
    return len(owner)


def boot(vals, rng_seed=BOOT_SEED, n=N_BOOT):
    v = np.asarray(vals, float)
    rng = np.random.default_rng(rng_seed)
    idx = rng.integers(0, len(v), size=(n, len(v)))
    m = v[idx].mean(1)
    return {"mean": float(v.mean()), "ci95": [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))], "n": len(v)}


def evaluate(stage, new, ind, rows):
    per = []
    for r in rows:
        iid = r["ImageID"]
        gts = [r["box1"], r["box2"]]
        d = {"ImageID": iid, "PatientID": r["PatientID"]}
        st, b = {}, {}
        for c in ("I1", "I2", "J12", "J21", "R11", "R22"):
            rec = ind[f"{iid}|CURE|{c}"] if c in ("I1", "I2") else new[f"{iid}|CURE|{c}"]
            st[c], b[c] = box_set(rec)
            d[f"status_{c}"] = st[c]
            d[f"n_attempts_{c}"] = len(rec["attempts"])
            d[f"prompt_tokens_{c}"] = len(rec["input_ids"])
            d[f"n_new_{c}"] = rec["attempts"][-1]["n_new"]
        multis = {"I": b["I1"] + b["I2"], "J12": b["J12"], "J21": b["J21"]}
        extras = [[r["box1"]] + r["extra1"], [r["box2"]] + r["extra2"]]
        for name, preds in multis.items():
            sc = S.score_boxes(gts, preds)
            d[name] = {k: sc[k] for k in ("recall", "n_matched", "matched_idx", "n_pred", "n_unmatched")}
            d[name]["f1_ann"] = S.f1_ann(sc["n_matched"], sc["n_pred"], 2)
            m5 = S.match(gts, preds, 0.5)[1]
            d[name]["recall_iou05"] = m5 / 2
            d[name]["recall_extra_sens"] = slots_match(extras, preds, S.IOU_THR) / 2
        # 단일 GT 대조 (같은 소견 반복)
        for sent, gt, ind_c, rep_c in (("S1", r["box1"], "I1", "R11"), ("S2", r["box2"], "I2", "R22")):
            d[f"single_{ind_c}"] = 1.0 if S.match([gt], b[ind_c])[1] else 0.0
            d[f"single_{rep_c}"] = 1.0 if S.match([gt], b[rep_c])[1] else 0.0
        d["rep_drop"] = ((d["single_I1"] - d["single_R11"]) + (d["single_I2"] - d["single_R22"])) / 2
        gi = set(d["I"]["matched_idx"])
        for j in ("J12", "J21"):
            d[f"lost_{j}"] = len(gi - set(d[j]["matched_idx"]))
            d[f"gained_{j}"] = len(set(d[j]["matched_idx"]) - gi)
        d["lost_both_orders"] = bool(d["lost_J12"] > 0 and d["lost_J21"] > 0)
        d["clean"] = all(d[f"status_{c}"] in ("valid_nonempty", "no_box") for c in ("I1", "I2", "J12", "J21"))
        per.append(d)
    return per


def summarize(per):
    A = lambda f: [f(d) for d in per]
    out = {"n": len(per)}
    for k in ("I", "J12", "J21"):
        out[f"recall_{k}"] = boot(A(lambda d: d[k]["recall"]))
        out[f"both_recovered_{k}"] = float(np.mean(A(lambda d: d[k]["n_matched"] == 2)))
        out[f"f1_ann_{k}"] = float(np.mean(A(lambda d: d[k]["f1_ann"])))
        out[f"n_pred_mean_{k}"] = float(np.mean(A(lambda d: d[k]["n_pred"])))
        out[f"n_unmatched_mean_{k}"] = float(np.mean(A(lambda d: d[k]["n_unmatched"])))
        out[f"recall_iou05_{k}"] = float(np.mean(A(lambda d: d[k]["recall_iou05"])))
        out[f"recall_extra_sens_{k}"] = float(np.mean(A(lambda d: d[k]["recall_extra_sens"])))
    out["diff_I_minus_J12"] = boot(A(lambda d: d["I"]["recall"] - d["J12"]["recall"]), BOOT_SEED + 1)
    out["diff_I_minus_J21"] = boot(A(lambda d: d["I"]["recall"] - d["J21"]["recall"]), BOOT_SEED + 2)
    out["diff_I_minus_Jmean"] = boot(A(lambda d: d["I"]["recall"] - (d["J12"]["recall"] + d["J21"]["recall"]) / 2), BOOT_SEED + 3)
    out["diff_I_minus_J_iou05_mean"] = float(np.mean(A(lambda d: d["I"]["recall_iou05"] - (d["J12"]["recall_iou05"] + d["J21"]["recall_iou05"]) / 2)))
    out["diff_I_minus_J_extra_sens_mean"] = float(np.mean(A(lambda d: d["I"]["recall_extra_sens"] - (d["J12"]["recall_extra_sens"] + d["J21"]["recall_extra_sens"]) / 2)))
    out["gt_lost_J12"] = int(sum(d["lost_J12"] for d in per))
    out["gt_lost_J21"] = int(sum(d["lost_J21"] for d in per))
    out["gt_gained_J12"] = int(sum(d["gained_J12"] for d in per))
    out["gt_gained_J21"] = int(sum(d["gained_J21"] for d in per))
    out["patients_lost_J12"] = int(sum(d["lost_J12"] > 0 for d in per))
    out["patients_lost_J21"] = int(sum(d["lost_J21"] > 0 for d in per))
    out["patients_lost_both_orders"] = int(sum(d["lost_both_orders"] for d in per))
    out["single_recall"] = {c: float(np.mean(A(lambda d: d[f"single_{c}"]))) for c in ("I1", "I2", "R11", "R22")}
    out["repetition_drop_I_minus_R"] = boot(A(lambda d: d["rep_drop"]), BOOT_SEED + 4)
    out["repetition_drop_minus_joint_drop_mean"] = float(np.mean(A(lambda d: d["rep_drop"])) - out["diff_I_minus_Jmean"]["mean"])
    stat = {c: dict(Counter(d[f"status_{c}"] for d in per)) for c in ("I1", "I2", "J12", "J21", "R11", "R22")}
    out["status_counts"] = stat
    out["final_not_eos"] = {c: int(sum(d[f"status_{c}"] == "truncated" for d in per)) for c in stat}
    out["retried_cap"] = {c: int(sum(d[f"n_attempts_{c}"] > 1 for d in per)) for c in stat}
    out["prompt_tokens_mean"] = {c: float(np.mean(A(lambda d: d[f"prompt_tokens_{c}"]))) for c in stat}
    out["n_new_tokens_mean"] = {c: float(np.mean(A(lambda d: d[f"n_new_{c}"]))) for c in stat}
    clean = [d for d in per if d["clean"]]
    out["clean_subset"] = {"n": len(clean)}
    if clean:
        out["clean_subset"]["diff_I_minus_Jmean"] = boot([d["I"]["recall"] - (d["J12"]["recall"] + d["J21"]["recall"]) / 2 for d in clean], BOOT_SEED + 5)
        out["clean_subset"]["diff_I_minus_J12_mean"] = float(np.mean([d["I"]["recall"] - d["J12"]["recall"] for d in clean]))
        out["clean_subset"]["diff_I_minus_J21_mean"] = float(np.mean([d["I"]["recall"] - d["J21"]["recall"] for d in clean]))
    # 사전 규칙 (plan 'Evaluation')
    j12, j21 = out["diff_I_minus_J12"]["mean"], out["diff_I_minus_J21"]["mean"]
    cond = {"loss_ge_10pp_both_orders": bool(j12 >= 0.10 and j21 >= 0.10),
            "patients_lost_both_orders_ge_4": bool(out["patients_lost_both_orders"] >= 4),
            "greater_than_repetition_drop": bool(out["diff_I_minus_Jmean"]["mean"] > out["repetition_drop_I_minus_R"]["mean"]),
            "clean_subset_direction_remains": bool(clean and out["clean_subset"]["diff_I_minus_J12_mean"] > 0 and out["clean_subset"]["diff_I_minus_J21_mean"] > 0)}
    out["prespecified_flags"] = cond
    out["branch"] = ("candidate_limited_loss_review" if all(cond.values()) else
                     "joint_preserves_small_difference" if abs(j12) < 0.10 and abs(j21) < 0.10 else "mixed_or_uncertain")
    return out


def cost_d4(new, ind, rows):
    """D4 동일 환자 workload: 독립 2요청 완료까지 vs 공동 1요청 완료까지 (요청별 e2e = CLAHE transform부터 저장 직전)."""
    rowsout = []
    for r in rows:
        iid = r["ImageID"]
        e = lambda c: (ind if c in ("I1", "I2") else new)[f"{iid}|CURE|{c}"]
        gen = lambda c: sum(a["runtime_s"] for a in e(c)["attempts"])
        rowsout.append({"ImageID": iid, "I_e2e_s": e("I1")["e2e_s"] + e("I2")["e2e_s"], "J12_e2e_s": e("J12")["e2e_s"], "J21_e2e_s": e("J21")["e2e_s"],
                        "I_gen_s": gen("I1") + gen("I2"), "J12_gen_s": gen("J12"), "J21_gen_s": gen("J21"),
                        "I_new_tokens": e("I1")["attempts"][-1]["n_new"] + e("I2")["attempts"][-1]["n_new"],
                        "J12_new_tokens": e("J12")["attempts"][-1]["n_new"], "J21_new_tokens": e("J21")["attempts"][-1]["n_new"]})
    mean = lambda k: float(np.mean([x[k] for x in rowsout]))
    return {"per_patient": rowsout, "mean": {k: mean(k) for k in rowsout[0] if k != "ImageID"},
            "note": "D4 4명, 같은 worker 구성에서 측정한 end-to-end(요청마다 공식 CLAHE transform 포함, 모델 로딩 제외). 확정적 비용 우위 주장에 쓰지 않는다."}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=["D4", "E32"])
    ap.add_argument("--gen", required=True)
    ap.add_argument("--nshards", type=int, required=True)
    ap.add_argument("--ind-gen")
    ap.add_argument("--ind-shards", type=int)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows, _ = R.stage_rows(a.stage)
    new, sd = load_gen(a.gen, a.stage, a.nshards)
    for r in rows:
        for c in R.STAGE_CONDS[a.stage]:
            assert f"{r['ImageID']}|CURE|{c}" in new
    if a.ind_gen:
        ind, ind_sd = load_ind_from_iter105(a.ind_gen, a.ind_shards)
        ind_src = {"path": a.ind_gen, "protocol_digest": ind_sd}
    else:
        ind, ind_src = new, {"path": a.gen, "note": "I1/I2 regenerated in this run"}
    per = evaluate(a.stage, new, ind, rows)
    summ = summarize(per)
    rep = {"stage": a.stage, "summary": summ, "independent_source": ind_src, "new_protocol_digest": sd, "n_patients": len(per),
           "iou_threshold": S.IOU_THR, "bootstrap": {"seed": BOOT_SEED, "n": N_BOOT},
           "source_sha256": {f: sha(ROOT / f) for f in ("lk106_eval.py", "lk106_spec.py", "lk106_run.py")},
           "input_sha256": sha(R.DATA / f"inputs_{a.stage}.json"), "label": "iter_105에서 이미 사용한 train 개발 자료; 독립 확증 아님"}
    if a.stage == "D4":
        rep["cost"] = cost_d4(new, ind, rows)
    out = Path(a.out)
    save(out, rep)
    save(out.with_name(out.stem + "_per_patient.json"), per)
    print(json.dumps({k: summ[k] for k in ("recall_I", "recall_J12", "recall_J21", "diff_I_minus_Jmean", "repetition_drop_I_minus_R", "status_counts", "branch")},
                     indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
