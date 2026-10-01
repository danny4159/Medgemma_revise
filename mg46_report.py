"""iter_046 최종 개발 비교 (CPU only, 기본 python). 순서: lock-pre(V96 생성 전) -> [V96 A 추론, timing] -> lock-post -> report -> mg46_verify -> completion.

  python mg46_report.py lock-pre  --out results/iter_046/eval/eval_lock_pre.json
  python mg46_report.py lock-post --pre results/iter_046/eval/eval_lock_pre.json --out results/iter_046/eval/eval_lock_post.json
  python mg46_report.py report    --lock results/iter_046/eval/eval_lock_post.json --out results/iter_046/eval/report.json
  python mg46_report.py complete  --report ... --verify ... --out results/iter_046/eval/completion.json

사전 고정 규칙(plan.md Evaluation, V96 결과를 보기 전에 확정; 결과를 본 뒤 바꾸지 않는다):
  주지표 문장 F1@0.3(환자 안 평균 -> 환자 평균), 원본 정규화 xyxy 최대 cardinality 일대일 matching(pg39_spec.match_fast).
  정확도·FP 차이: 환자 paired bootstrap 10,000회 seed 4401, 97.5% CI. 비용: 6 paired block의 A/P log-ratio 평균 +- t(5) 95% CI.
  H_adaptation: A_fixed(0.4)-P F1@0.3 점차>=0.05 & CI하한>0.
  modular_sufficient: A_sel-C F1@0.3 CI하한>=-0.03 & F1@0.5 CI하한>=-0.03 & FP차 CI상한<=0.10 & A/P device-seconds CI상한<=2 & p95 CI상한<=2 & throughput(A/P) CI하한>=0.5.
  C_residual_advantage: C-A_sel F1@0.3 점차>=0.05 & CI하한>0 & 학습경로 정상 & 허용한 수렴 점검 완료.
  그 외 불확정(부족한 증거 명시). provenance/무결성 결함이면 execution_failed.
"""
import argparse
import glob
import hashlib
import json
import os
import sys
import time

import numpy as np

import mg45_eval as E
import mg45_report as MR
import mg46_eval as E6
from rsna_diag import parse

ROOT = "results/iter_046"
MAN = E.MAN
NBOOT, SEED = MR.NBOOT, MR.SEED
V96_A = f"{ROOT}/mg/V96_A_w2b4"
V96_P = "results/iter_045/mg/V96_P_w2b4"
FINAL = f"{ROOT}/decisions/final_selection.json"
TIMING = f"{ROOT}/timing"
ATTEMPTS = f"{TIMING}/attempts.json"
SRC = ["mg46_report.py", "mg46_verify.py", "mg46_timing.py", "mg46_eval.py", "mg46_run.py", "mg46_train.py", "mg45_report.py", "mg45_eval.py", "mg45_mg.py", "mg45_worker.py",
       "mg45_launch.py", "pg39_spec.py", "pg43_eval.py", "pg43_run.py", "rsna_diag/metrics.py", "rsna_diag/parse.py", "rsna_diag/geometry.py", "rsna_diag/__init__.py",
       "rsna_diag/generate.py", "rsna_diag/prompts.py", "rsna_diag/lora.py", "rsna_diag/queue_lock.py", MAN, MR.C_REQ, MR.C_PROTO, f"{ROOT}/protocol/protocol_lock.json",
       "results/iter_045/decisions/D24_select.json"]


def fsha(p):
    return E.file_sha(p)


def attempts():
    d = {k: 1 for k in range(1, 7)}
    if os.path.exists(ATTEMPTS):
        d.update({int(k): v for k, v in json.load(open(ATTEMPTS)).items()})
    return d


def decision_files():
    return sorted(glob.glob(f"{ROOT}/decisions/*.json"))


def train_files(tj):
    return sorted(glob.glob(f"{ROOT}/train/{tj}/reached_epoch*.json") + glob.glob(f"{ROOT}/train/{tj}/weights_e*.json") + glob.glob(f"{ROOT}/train/{tj}/train_log.jsonl"))


def write_once(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        sys.exit(f"exists: {path}")
    tmp = path + f".{os.getpid()}.tmp"
    json.dump(obj, open(tmp, "w"), indent=1)
    os.replace(tmp, path)


def cmd_lock_pre(a):
    fin = json.load(open(FINAL))
    lock = {"files": {f: fsha(f) for f in SRC}, "decisions": {f: fsha(f) for f in decision_files()}, "train_files": {f: fsha(f) for f in train_files(fin["traj"])},
            "final_ckpt": {"path": fin["ckpt_path"], "sha256": fin["ckpt_sha256"], "file_sha256_now": fsha(fin["ckpt_path"])}, "locked_at": time.time(),
            "note": "V96 A 추론·timing 이전에 작성(final_selection 포함). V96 결과로 선택을 바꾸지 않는다."}
    if lock["final_ckpt"]["file_sha256_now"] != fin["ckpt_sha256"]:
        sys.exit("final checkpoint sha != final_selection")
    write_once(a.out, lock)
    print("locked-pre", len(lock["files"]), "sources", len(lock["decisions"]), "decisions")


def cmd_lock_post(a):
    pre = json.load(open(a.pre))
    att = attempts()
    post = {"pre_sha256": fsha(a.pre), "v96_A_completion": fsha(V96_A + "/completion.json"), "v96_P_completion": fsha(V96_P + "/completion.json"),
            "c_completion": fsha(MR.C_GEN + "/completion.json"),
            "timing_completions": {f"{s}{k}": fsha(f"{TIMING}/block{k}_a{att[k]}_{s}/completion.json") for k in range(1, 7) for s in ("A", "P")},
            "attempts": {str(k): v for k, v in att.items()}, "locked_at": time.time()}
    write_once(a.out, post)
    print("locked-post")


def check_lock(post_path):
    post = json.load(open(post_path))
    pre_p = f"{ROOT}/eval/eval_lock_pre.json"
    if fsha(pre_p) != post["pre_sha256"]:
        raise E.EvalError("pre lock changed")
    pre = json.load(open(pre_p))
    bad = [f for f, h in pre["files"].items() if fsha(f) != h] + [f for f, h in pre["decisions"].items() if fsha(f) != h] + [f for f, h in pre["train_files"].items() if fsha(f) != h]
    if bad:
        raise E.EvalError(f"locked sources/decisions/train files changed: {bad}")
    att = attempts()
    if {str(k): v for k, v in att.items()} != post["attempts"]:
        raise E.EvalError("timing attempts changed")
    chk = {"v96_A_completion": V96_A + "/completion.json", "v96_P_completion": V96_P + "/completion.json", "c_completion": MR.C_GEN + "/completion.json"}
    for k, p in chk.items():
        if fsha(p) != post[k]:
            raise E.EvalError(f"{k} changed")
    for k in range(1, 7):
        for s in ("A", "P"):
            if fsha(f"{TIMING}/block{k}_a{att[k]}_{s}/completion.json") != post["timing_completions"][f"{s}{k}"]:
                raise E.EvalError("timing completion changed")
    return pre, post


def training_summary(fin):
    tj = fin["traj"]
    d = f"{ROOT}/train/{tj}"
    last_ep = max(int(os.path.basename(f)[len("reached_epoch"):-5]) for f in glob.glob(d + "/reached_epoch*.json"))
    rows = [json.loads(l) for l in open(d + "/train_log.jsonl") if l.strip()]
    steps = [r["step"] for r in rows]
    reached = json.load(open(f"{d}/reached_epoch{last_ep}.json"))
    ok_steps = steps == list(range(20 * last_ep))
    finite = all(r["finite"] and np.isfinite(r["loss"]) and np.isfinite(r["grad_norm"]) for r in rows)
    wsh = {}
    for e in (2, 5, 10, 15, 20, 25, 30):
        p = f"{d}/weights_e{e}.json"
        if os.path.exists(p):
            wsh[e] = json.load(open(p))["sha256"] == json.load(open(f"{d}/weights_e{e}.pth.sha256.json"))["sha256"]
    curve = {}
    for c in E6.load_ckpt_decisions([tj], [2, 5, 10, 15, 20, 25, 30]):
        curve[str(c["epoch"])] = {"thr": c["selected_threshold"], "f1_03": c["selected"]["f1_03"], "f1_05": c["selected"]["f1_05"], "fp": c["selected"]["fp_per_sentence"],
                                  "fixed0.4_f1_03": c["fixed_0.4"]["f1_03"], "mean_train_loss": reached["epoch_mean_train_loss"].get(str(c["epoch"]))}
    phase1 = {}
    for c in E6.load_ckpt_decisions(["S", "U"], [2, 5]):
        phase1[c["label"]] = {"thr": c["selected_threshold"], "f1_03": c["selected"]["f1_03"], "f1_05": c["selected"]["f1_05"], "fp": c["selected"]["fp_per_sentence"]}
    step_s = [r["step_s"] + r["data_s"] for r in rows]
    return {"traj": tj, "last_epoch": last_ep, "n_updates": len(rows), "steps_contiguous_unique": ok_steps, "all_finite": finite, "weights_digest_ok": wsh,
            "discarded_logs": sorted(glob.glob(d + "/train_log.discarded_*.jsonl")), "d24_curve_selected_traj": curve, "phase1_candidates": phase1,
            "epoch_mean_train_loss": reached["epoch_mean_train_loss"], "wall_sum_step_plus_data_s": float(np.sum(step_s)), "peak_alloc_gb_max": max(r["peak_alloc_gb"] for r in rows),
            "gt_dropped_by_aug": int(sum(r["n_gt_dropped"] for r in rows)), "empty_after_aug": int(sum(r["n_empty_after_aug"] for r in rows)),
            "normal_path": bool(ok_steps and finite and all(wsh.values()))}


def timing_block(k, att):
    out = {}
    for s in ("A", "P"):
        d = f"{TIMING}/block{k}_a{att}_{s}"
        man = json.load(open(MAN))
        if s == "A":
            fin = json.load(open(FINAL))
            recs, comp, _ = E6.verify_dir(d, "V96", "A_final", fin["ckpt_path"], man)
        else:
            recs, comp, _ = E.verify_mg_dir(d, "V96", "P", man)
        mp = {int(w): g for w, g in comp["mapping"].items()}
        by_p = {}
        for (p, t), r in recs.items():
            if "t_orig_done" not in r:
                raise E.EvalError(f"timing record lacks t_orig_done: {d}")
            by_p.setdefault(p, []).append(r)
        lat = {p: max(x["t_orig_done"] for x in v) - min(x["t_dispatch"] for x in v) for p, v in by_p.items()}
        iv = {}
        for p, v in by_p.items():
            iv.setdefault(mp[v[0]["worker"]], []).append((min(x["t_dispatch"] for x in v), max(x["t_orig_done"] for x in v)))
        span = sum(max(e for _, e in v) - min(s_ for s_, _ in v) for v in iv.values())
        v = np.array(list(lat.values()))
        cold, peak_res = MR.mg_meta_cold(d)
        out[s] = {"workload_wall_s": comp["workload_wall_s"], "patients_per_min": 96 / comp["workload_wall_s"] * 60, "device_seconds_span": span,
                  "device_seconds_union": sum(MR.PE_union(x) for x in iv.values()),
                  "latency_s": {"mean": float(v.mean()), "p50": float(np.percentile(v, 50)), "p95": float(np.percentile(v, 95)), "n": int(len(v))},
                  "peak_alloc_gb_max": comp["peak_alloc_gb_max"], "peak_reserved_gb_max": peak_res, "cold_load_s_max": cold, "workers": comp["workers"],
                  "batch": comp["batch"], "mapping": comp["mapping"], "n_records": len(recs)}
    return out


def cmd_report(a):
    if os.path.exists(a.out):
        sys.exit("output exists")
    t_start = time.time()
    pre, post = check_lock(a.lock)
    man = json.load(open(MAN))
    fin = json.load(open(FINAL))
    ents = {e["PatientID"]: e for e in man["V96"]}
    pids = sorted(ents)
    thr_sel, thr_fix = fin["selected_threshold"], 0.4
    train = training_summary(fin)
    # ---- 시스템별 출력 ----
    crecs, cprov = MR.verify_c_import(ents)
    c_git_ok = all(cprov["code_hash_equals_git_blob_at_iter040_commit"].values())
    c_sc, c_status, c_inv = MR.c_scores(crecs, ents)
    a_recs, a_comp, a_proto = E6.verify_dir(V96_A, "V96", "A_final", fin["ckpt_path"], man)
    p_recs, p_comp, p_proto = E.verify_mg_dir(V96_P, "V96", "P", man, allow_code_diff=True)  # iter_045 원 protocol의 code hash는 amendment로 달라짐: 회귀 증거 별도 확인
    amend_ok = json.load(open(f"{ROOT}/tests/regress_P_vs_iter045_final_worker.json"))
    p_thr = json.load(open("results/iter_045/decisions/D24_select.json"))["ckpts"]["P"]["selected_threshold"]
    sysdefs = {"C": c_sc, "P@sel": E.mg_scores(p_recs, ents, p_thr), "A@0.4": E.mg_scores(a_recs, ents, thr_fix), "A@sel": E.mg_scores(a_recs, ents, thr_sel),
               "A@0.8": E.mg_scores(a_recs, ents, 0.8), "P@0.8": E.mg_scores(p_recs, ents, 0.8)}
    idx = MR.boot_idx(len(pids))
    prim = {}
    for s, sc in sysdefs.items():
        b = E.summarize(sc, pids)
        b["f1_03_ci95"] = MR.ci(MR.pat_arr(sc, pids, "f1_03"), 0.95, idx)
        b["f1_05_ci95"] = MR.ci(MR.pat_arr(sc, pids, "f1_05"), 0.95, idx)
        b["n_sentences"] = len(sc)
        prim[s] = b
    prim["C"]["valid_rate"] = float(np.mean([v in parse.VALID for v in c_status.values()]))
    prim["C"]["eos_rate"] = float(np.mean([r["ended_eos"] for r in crecs.values()]))
    repro = {"C_f1_03": prim["C"]["f1_03"], "C_f1_05": prim["C"]["f1_05"], "stored": MR.C_STORED, "abs_diff_03": abs(prim["C"]["f1_03"] - MR.C_STORED["f1_03"]),
             "abs_diff_05": abs(prim["C"]["f1_05"] - MR.C_STORED["f1_05"]), "canvas_vs_original_invariance": c_inv,
             "P_sel_threshold": p_thr, "P_f1_03_vs_iter045_report": {"now": prim["P@sel"]["f1_03"], "iter045": 0.395313}}

    def diff(x, y, key, level):
        return MR.ci(MR.pat_arr(sysdefs[x], pids, key) - MR.pat_arr(sysdefs[y], pids, key), level, idx)
    cmp = {}
    for x, y in (("A@0.4", "P@sel"), ("A@sel", "C"), ("C", "A@sel"), ("A@sel", "P@sel"), ("A@0.4", "C"), ("A@0.8", "P@0.8")):
        cmp[f"{x}_minus_{y}"] = {m: diff(x, y, m, 0.975) for m in ("f1_03", "f1_05", "fp_03", "recall_03")}
    # ---- 층별 (보조 기술) ----
    area = lambda b: max(0, b[2] - b[0]) * max(0, b[3] - b[1]) / 1e6
    max_area = {(p, t): max(area(b) for b in ents[p]["gt_canvas_yxyx"][t]) for p in pids for t in ("qA", "qB")}
    med = float(np.median(list(max_area.values())))
    strat = {"multi_box": lambda p, t: len(ents[p]["gt_canvas_yxyx"][t]) > 1, "single_box": lambda p, t: len(ents[p]["gt_canvas_yxyx"][t]) == 1,
             "small_box": lambda p, t: max_area[(p, t)] < med, "large_box": lambda p, t: max_area[(p, t)] >= med,
             "gt_count_gt5(query limit)": lambda p, t: len(ents[p]["gt_canvas_yxyx"][t]) > 5}
    strata = {}
    for nm, fn in strat.items():
        ks = [(p, t) for p in pids for t in ("qA", "qB") if fn(p, t)]
        if not ks:
            continue
        strata[nm] = {"n_sentences": len(ks), "systems": {s: {"f1_03": float(np.mean([sc[k]["f1_03"] for k in ks])), "recall_03": float(np.mean([sc[k]["recall_03"] for k in ks])),
                                                           "fp_per_sentence": float(np.mean([sc[k]["fp_03"] for k in ks])), "empty_rate": float(np.mean([bool(sc[k]["empty"]) for k in ks])),
                                                           "missed_gt_per_sentence": float(np.mean([sc[k]["n_gt"] * (1 - sc[k]["recall_03"]) for k in ks]))} for s, sc in sysdefs.items()}}
    # ---- 오류 출력 점검: 좌표 유효성 (임의 clipping 없이 범위 밖 box는 개수만 기록) ----
    def box_checks(recs, thr):
        n = bad_size = oob = nonfinite = 0
        for r in recs.values():
            for b in r["detections"][str(thr)]["boxes_orig_xyxy"]:
                n += 1
                nonfinite += int(not all(np.isfinite(b)))
                bad_size += int(b[2] <= b[0] or b[3] <= b[1])
                oob += int(b[0] < 0 or b[1] < 0 or b[2] > 1 or b[3] > 1)
        return {"n_boxes": n, "nonfinite": nonfinite, "nonpositive_size": bad_size, "outside_unit_square_kept_unclipped": oob}
    coord = {"A@sel": box_checks(a_recs, thr_sel), "P@sel": box_checks(p_recs, p_thr)}
    # ---- timing ----
    att = attempts()
    blocks = {k: timing_block(k, att[k]) for k in range(1, 7)}
    bl = [blocks[k] for k in range(1, 7)]
    cost = {"blocks": {str(k): blocks[k] for k in blocks}, "lead_order": {str(k): ("A" if k % 2 == 1 else "P") for k in range(1, 7)}, "attempts": {str(k): v for k, v in att.items()}}
    for nm in ("device_seconds_span", "device_seconds_union"):
        cost[f"A_over_P_{nm}"] = MR.ratio_ci([b["A"][nm] for b in bl], [b["P"][nm] for b in bl])
    cost["A_over_P_throughput"] = MR.ratio_ci([b["A"]["patients_per_min"] for b in bl], [b["P"]["patients_per_min"] for b in bl])
    cost["A_over_P_p95_latency"] = MR.ratio_ci([b["A"]["latency_s"]["p95"] for b in bl], [b["P"]["latency_s"]["p95"] for b in bl])
    cost["A_over_P_mean_latency"] = MR.ratio_ci([b["A"]["latency_s"]["mean"] for b in bl], [b["P"]["latency_s"]["mean"] for b in bl])
    cost["historical_iter045_MG_over_C_device_seconds"] = {"geo_mean": 0.036942, "ci95": [0.030080, 0.045369],
                                                           "note": "iter_045 별도 paired block; A/P(iter_046)와 곱해 A/C 동시측정 CI로 제시하지 않는다 (신규 C 대비 end-to-end 비용은 미검증)"}
    cost["cold_loading_s_max"] = {s: [blocks[k][s]["cold_load_s_max"] for k in range(1, 7)] for s in ("A", "P")}
    # timing 출력 정합성: timing 최종 box == V96 raw (선택 threshold)
    integ_t = []
    for k in range(1, 7):
        d = f"{TIMING}/block{k}_a{att[k]}_A"
        recs, _, _ = E6.verify_dir(d, "V96", "A_final", fin["ckpt_path"], man)
        ts, ref = E.mg_scores(recs, ents, thr_sel), E.mg_scores(a_recs, ents, thr_sel)
        recsP, _, _ = E.verify_mg_dir(f"{TIMING}/block{k}_a{att[k]}_P", "V96", "P", man)
        tsP, refP = E.mg_scores(recsP, ents, p_thr), E.mg_scores(p_recs, ents, p_thr)
        integ_t.append({"block": k, "A_n_f1_or_count_differ": sum(abs(ts[x]["f1_03"] - ref[x]["f1_03"]) > 1e-12 or abs(ts[x]["f1_05"] - ref[x]["f1_05"]) > 1e-12 or ts[x]["n_pred"] != ref[x]["n_pred"] for x in ts),
                        "P_n_f1_or_count_differ": sum(abs(tsP[x]["f1_03"] - refP[x]["f1_03"]) > 1e-12 or abs(tsP[x]["f1_05"] - refP[x]["f1_05"]) > 1e-12 or tsP[x]["n_pred"] != refP[x]["n_pred"] for x in tsP),
                        "A_max_abs_logit_diff_vs_raw": float(max(np.abs(np.array(recs[x]["logits"]) - np.array(a_recs[x]["logits"])).max() for x in recs)),
                        "P_max_abs_logit_diff_vs_raw": float(max(np.abs(np.array(recsP[x]["logits"]) - np.array(p_recs[x]["logits"])).max() for x in recsP))})
    # ---- 결정 ----
    adapt = cmp["A@0.4_minus_P@sel"]["f1_03"]
    mod_acc = cmp["A@sel_minus_C"]
    cm = cmp["C_minus_A@sel"]
    H_adapt = {"A_fixed-P_f1_03_point>=0.05": adapt["mean"] >= 0.05, "A_fixed-P_f1_03_ci_lo>0": adapt["lo"] > 0}
    mod = {"A-C_f1_03_ci_lo>=-0.03": mod_acc["f1_03"]["lo"] >= -0.03, "A-C_f1_05_ci_lo>=-0.03": mod_acc["f1_05"]["lo"] >= -0.03, "A-C_fp_ci_hi<=0.10": mod_acc["fp_03"]["hi"] <= 0.10,
           "A/P_device_ci_hi<=2": cost["A_over_P_device_seconds_span"]["ci95_hi"] <= 2.0, "A/P_p95_ci_hi<=2": cost["A_over_P_p95_latency"]["ci95_hi"] <= 2.0,
           "A/P_throughput_ci_lo>=0.5": cost["A_over_P_throughput"]["ci95_lo"] >= 0.5}
    sd = json.load(open(f"{ROOT}/decisions/supp_decision.json"))
    curve = train["d24_curve_selected_traj"]
    conv_unconfirmed = False
    if sd["run_supp"] and all(str(e) in curve for e in (25, 30)):
        best_ep = E6.select_best([{"traj": fin["traj"], "epoch": int(e), "selected": {"f1_03": v["f1_03"], "f1_05": v["f1_05"], "fp_per_sentence": v["fp"]}} for e, v in curve.items()])[0]["epoch"]
        conv_unconfirmed = bool(best_ep == 30 and curve["30"]["f1_03"] - curve["25"]["f1_03"] >= 0.01)
    res_adv = {"C-A_f1_03_point>=0.05": cm["f1_03"]["mean"] >= 0.05, "C-A_f1_03_ci_lo>0": cm["f1_03"]["lo"] > 0, "training_path_normal": train["normal_path"],
               "convergence_check_completed_and_not_still_rising": (not conv_unconfirmed)}
    integrity_ok = bool(repro["abs_diff_03"] < 1e-9 and repro["abs_diff_05"] < 1e-9 and c_inv["mismatch"] == 0 and c_git_ok and all(i["A_n_f1_or_count_differ"] == 0 and i["P_n_f1_or_count_differ"] == 0 for i in integ_t)
                        and all(c["nonfinite"] == 0 for c in coord.values()) and prim["A@sel"]["n_patients"] == 96 and train["normal_path"]
                        and abs(prim["P@sel"]["f1_03"] - 0.3953125) < 1e-5 and amend_ok["D24_P_w2b4_cfg_a2"]["max_abs_logit_diff"] == 0.0)
    if not integrity_ok:
        outcome = "execution_failed_provenance_or_integrity"
    elif all(H_adapt.values()) and all(mod.values()):
        outcome = "adaptation_effect_and_modular_alternative_supported"
    elif all(mod.values()):
        outcome = "modular_alternative_supported"
    elif all(res_adv.values()):
        outcome = "C_residual_advantage_supported"
    else:
        outcome = "scientifically_inconclusive"
    unmet = {"adaptation": [k for k, v in H_adapt.items() if not v], "modular": [k for k, v in mod.items() if not v], "residual": [k for k, v in res_adv.items() if not v]}
    decision = {"outcome": outcome, "H_adaptation_conditions": H_adapt, "modular_sufficient_conditions": mod, "C_residual_advantage_conditions": res_adv, "unmet": unmet,
                "provenance_integrity_ok": integrity_ok, "c_code_hash_vs_git_all_true": c_git_ok, "convergence_unconfirmed_after_supp": conv_unconfirmed,
                "note": "개발 자료 V96 고정 비교(이미 본 개발 자료, D24로 선택). 동일 annotation budget 적응이지만 사전학습·해상도·학습량·선택 자료가 다르다. 독립 확인·신규 contribution·공동 요청/부재 거부 판정이 아니다."}
    rep = {"n_patients": len(pids), "final_selection": {k: fin[k] for k in ("traj", "label", "epoch", "selected_threshold", "ckpt_sha256", "supp_run")}, "primary_V96": prim, "compare_paired_ci975": cmp,
           "strata": strata, "strata_small_threshold": med, "C_reproduction": repro, "C_import_provenance": cprov, "coord_checks": coord, "training": train, "supp_decision": sd,
           "cost": cost, "timing_integrity": integ_t, "decision": decision,
           "a_run": {"dir": V96_A, "workers": a_comp["workers"], "batch": a_comp["batch"], "workload_wall_s": a_comp.get("workload_wall_s"), "exit_codes": a_comp["exit_codes"]},
           "provenance": {"lock_post_sha256": fsha(a.lock), "eval_source_sha256": fsha("mg46_report.py"), "bootstrap": {"B": NBOOT, "seed": SEED}, "eval_wall_s": time.time() - t_start}}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    pi = a.out.replace(".json", "_per_item.json")
    tmp, tmp2 = a.out + f".{os.getpid()}.tmp", pi + f".{os.getpid()}.tmp"
    json.dump(rep, open(tmp, "w"), indent=1)
    json.dump({s_: {f"{k[0]}|{k[1]}": v for k, v in sc.items()} for s_, sc in sysdefs.items()}, open(tmp2, "w"))
    os.replace(tmp2, pi)
    os.replace(tmp, a.out)
    print(json.dumps({"outcome": outcome, "unmet": unmet, "f1_03": {s_: round(prim[s_]["f1_03"], 4) for s_ in prim}, "f1_05": {s_: round(prim[s_]["f1_05"], 4) for s_ in prim},
                      "fp": {s_: round(prim[s_]["fp_per_sentence"], 4) for s_ in prim}}, indent=1))


def cmd_complete(a):
    """최종 completion: report·per_item·verify PASS·lock·decision 파일을 digest로 묶는다. verify 실패면 생성하지 않는다."""
    ver = json.load(open(a.verify))
    if ver.get("PASS") is not True:
        sys.exit("verify not PASS; no completion")
    comp = {"report": {"path": a.report, "sha256": fsha(a.report)}, "per_item": {"path": a.report.replace(".json", "_per_item.json"), "sha256": fsha(a.report.replace(".json", "_per_item.json"))},
            "verify": {"path": a.verify, "sha256": fsha(a.verify)}, "lock_pre": fsha(f"{ROOT}/eval/eval_lock_pre.json"), "lock_post": fsha(f"{ROOT}/eval/eval_lock_post.json"),
            "decisions": {f: fsha(f) for f in decision_files()}, "completed_at": time.time(), "complete": True}
    write_once(a.out, comp)
    print("completion written")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("lock-pre")
    l.add_argument("--out", required=True)
    l2 = sub.add_parser("lock-post")
    l2.add_argument("--pre", required=True)
    l2.add_argument("--out", required=True)
    r = sub.add_parser("report")
    r.add_argument("--lock", required=True)
    r.add_argument("--out", required=True)
    c = sub.add_parser("complete")
    c.add_argument("--report", required=True)
    c.add_argument("--verify", required=True)
    c.add_argument("--out", required=True)
    a = ap.parse_args()
    {"lock-pre": cmd_lock_pre, "lock-post": cmd_lock_post, "report": cmd_report, "complete": cmd_complete}[a.cmd](a)


if __name__ == "__main__":
    main()
