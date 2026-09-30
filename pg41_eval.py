"""iter_041 평가: 독립 I-short(기존 iter_040 출력, 출처 protocol로 재검증) vs 공동 J-short AB/BA(신규) 비교 + 실제 병렬 비용.

입력은 config JSON(각 조건의 gen dir·requests·protocol·검증기). 모든 completion은 검증기(old=pg40_run, new=pg41_run) 통과 후에만 사용한다.
평가 manifest/selection lock/평가 소스(pg41_eval.py, pg41_rules.py, pg39_spec.py)의 digest를 report에 기록하고, 사전 규칙(pg41_rules)으로 판정한다.
GT는 이 파일에서만 읽는다. 결과는 새 경로에만 쓴다(존재하면 거부).

python pg41_eval.py --config results/iter_041/eval/config_V96.json --out results/iter_041/eval/report_V96.json
"""
import argparse
import hashlib
import json
import os
import sys

import numpy as np

import pg39_eval as E39
import pg39_spec as S
import pg40_run as R40
import pg41_rules as RULES
import pg41_run as R41
from rsna_diag import metrics, parse

SMALL_AREA = E39.SMALL_AREA


def fsha(p):
    return R41.file_sha(p)


def load_verified(src):
    """src: {gen, req, proto, verifier}. returns records (completion·요청 집합·digest·현재 영상 hash 검증 통과)."""
    mod = R40 if src["verifier"] == "pg40" else R41
    recs = mod.verify_completion(src["gen"], src["req"], src["proto"])
    rows = R41.read_requests(src["req"])
    if src["verifier"] == "pg40":  # 기존 검증기는 현재 영상 hash를 재검증하지 않으므로 여기서 추가 검사
        from rsna_diag import generate as G
        seen = {}
        for r in rows:
            if r["image"] not in seen:
                if fsha(r["image"]) != r["image_file_sha256"] or G.load_image(r["image"])[2] != r["input_pixel_sha256"]:
                    raise R41.RunError(f"current image hash mismatch {r['image']}")
                seen[r["image"]] = 1
    return recs


def load_manifest(path, lock_path, subset):
    lock = json.load(open(lock_path))
    key = "manifest_eval_sha256"
    if fsha(path) != lock[key]:
        raise R41.RunError("eval manifest hash != selection_lock")
    out = {}
    for l in open(path):
        r = json.loads(l)
        if r["eval_set"] == subset:
            out[r["PatientID"]] = r
    return out


def entry(rec, man):
    m = man[rec["patient"]]
    gt = E39.gt_canvas(m)
    p = S.parse_ids(rec["suffix_text_raw"], rec["ended_eos"], set(rec["targets"]))
    sc = S.score_request(p["status"], p["groups"], rec["targets"], gt)
    ent = {"status": p["status"], "valid": p["status"] in parse.VALID, "eos": rec["ended_eos"], "scores": sc, "groups": p["groups"],
           "n_out": rec["n_output_tokens"], "wall": rec["wall_s"], "t_start": rec.get("t_start"), "ts": rec["ts"],
           "caps_used": len(rec["attempts"]), "tokens_all_attempts": sum(a["n_new"] for a in rec["attempts"]), "other_id": p["other_id_boxes"]}
    if len(rec["targets"]) == 2:
        ent["swap_f1_03"] = S.swap_score(p["groups"], gt) if ent["valid"] else 0.0
        ent["swap_sent"] = {"qA": S.sent_metrics(p["groups"].get("qB", []), gt["qA"], 0.3)["f1"] if ent["valid"] else 0.0,
                            "qB": S.sent_metrics(p["groups"].get("qA", []), gt["qB"], 0.3)["f1"] if ent["valid"] else 0.0}
    return ent


def model_tab(recsI, recsAB, recsBA, man):
    tab = {}
    for r in recsI:
        tab.setdefault(r["patient"], {}).setdefault("I", {})[r["targets"][0]] = entry(r, man)
    for r in recsAB:
        tab.setdefault(r["patient"], {})["AB"] = entry(r, man)
    for r in recsBA:
        tab.setdefault(r["patient"], {})["BA"] = entry(r, man)
    for p, v in tab.items():
        assert set(v["I"]) == {"qA", "qB"} and "AB" in v and "BA" in v, p
    return tab


def sc(tab, p, c, key="f1_03"):
    if c == "I":
        return float(np.mean([tab[p]["I"][t]["scores"][t][key] for t in ("qA", "qB")]))
    return float(np.mean([tab[p][c]["scores"][t][key] for t in ("qA", "qB")]))


def sent(tab, p, c, t, key="f1_03"):
    return tab[p]["I"][t]["scores"][t][key] if c == "I" else tab[p][c]["scores"][t][key]


def ents(tab, p, c):
    return list(tab[p]["I"].values()) if c == "I" else [tab[p][c]]


def eval_model(tab, man):
    pids = sorted(tab)
    X = {c: np.array([sc(tab, p, c) for p in pids]) for c in ("I", "AB", "BA")}
    X5 = {c: np.array([sc(tab, p, c, "f1_05") for p in pids]) for c in ("I", "AB", "BA")}
    rep = {"n_patients": len(pids)}
    rep["mean_f1_03"] = {c: E39.ci(X[c]) for c in X}
    rep["mean_f1_05"] = {c: E39.ci(X5[c]) for c in X5}
    rep["delta_I_minus_JAB"] = {"ci975": E39.pci(X["I"], X["AB"], 0.975), "ci95": E39.pci(X["I"], X["AB"])}
    rep["delta_I_minus_JBA"] = {"ci975": E39.pci(X["I"], X["BA"], 0.975), "ci95": E39.pci(X["I"], X["BA"])}
    rep["order_effect_JAB_minus_JBA"] = {"ci95": E39.pci(X["AB"], X["BA"])}
    rep["delta_f1_05_I_minus_JAB_JBA"] = [float((X5["I"] - X5["AB"]).mean()), float((X5["I"] - X5["BA"]).mean())]
    # 형식
    fmt = {}
    for c in X:
        es = [e for p in pids for e in ents(tab, p, c)]
        st = {}
        for e in es:
            st[e["status"]] = st.get(e["status"], 0) + 1
        fmt[c] = {"n_requests": len(es), "valid_rate": float(np.mean([e["valid"] for e in es])),
                  "final_truncation_rate": float(np.mean([not e["eos"] for e in es])),
                  "retried_rate": float(np.mean([e["caps_used"] > 1 for e in es])), "status_counts": st,
                  "other_id_requests": int(sum(e["other_id"] > 0 for e in es))}
    rep["format"] = fmt
    # 공통 valid/EOS subset
    def ok(p):
        return all(e["valid"] and e["eos"] for c in ("I", "AB", "BA") for e in ents(tab, p, c))
    keep = [i for i, p in enumerate(pids) if ok(p)]
    rep["common_valid_eos_subset"] = {"n": len(keep)}
    if len(keep) >= 5:
        rep["common_valid_eos_subset"].update({"delta_AB": E39.pci(X["I"][keep], X["AB"][keep], 0.975),
                                               "delta_BA": E39.pci(X["I"][keep], X["BA"][keep], 0.975)})
    # 문장 단위 손실/회복
    for c in ("AB", "BA"):
        a = np.array([[sent(tab, p, "I", t), sent(tab, p, c, t)] for p in pids for t in ("qA", "qB")])
        i_ok, j_ok = a[:, 0] >= 1 - 1e-12, a[:, 1] >= 1 - 1e-12
        lost = {"invalid_or_truncated": 0, "empty": 0, "assigned_to_other_sentence": 0, "localization_or_count": 0}
        for p in pids:
            for t in ("qA", "qB"):
                if sent(tab, p, "I", t) >= 1 - 1e-12 and sent(tab, p, c, t) < 1 - 1e-12:
                    e = tab[p][c]
                    if not e["valid"]:
                        lost["invalid_or_truncated"] += 1
                    elif not e["groups"].get(t):
                        lost["empty"] += 1
                    elif e["swap_sent"][t] >= 1 - 1e-12:
                        lost["assigned_to_other_sentence"] += 1
                    else:
                        lost["localization_or_count"] += 1
        rep[f"loss_recovery_I_vs_J{c}"] = {
            "sentences": int(len(a)), "I_full_success": int(i_ok.sum()), "J_full_success": int(j_ok.sum()),
            "success_lost": int((i_ok & ~j_ok).sum()), "success_gained": int((~i_ok & j_ok).sum()),
            "lost_by_cause": lost, "discordance_wilson95": list(metrics.wilson(int((i_ok != j_ok).sum()), len(a)))}
        swp = np.array([max(X[c][i], tab[p][c]["swap_f1_03"]) for i, p in enumerate(pids)])
        rep[f"swap_oracle_J{c}"] = {"orig": float(X[c].mean()), "best_of_swap": float(swp.mean()), "gain_ci95": E39.pci(swp, X[c]),
                                    "patients_improved": int((swp > X[c] + 1e-12).sum()), "note": "오류 분해용 상한, 실용 방법 아님"}
    # 층별
    man_p = {p: man[p] for p in pids}
    cross = {p: S.cross_iou_max(*(E39.gt_canvas(man_p[p])[k] for k in ("qA", "qB"))) for p in pids}
    small = lambda p: any((b[2] - b[0]) * (b[3] - b[1]) < SMALL_AREA for k in ("qA", "qB") for b in man_p[p]["gt_boxes_xyxy_norm"][k])
    strata = {"multi_box": lambda p: any(len(man_p[p]["gt_boxes_xyxy_norm"][k]) > 1 for k in ("qA", "qB")),
              "share_group": lambda p: man_p[p]["stratum"].startswith("share1"), "small_box": small,
              "cross_iou_lt_0.1": lambda p: cross[p] < 0.1, "cross_iou_ge_0.1(overlap)": lambda p: cross[p] >= 0.1}
    rep["strata"] = {}
    for s, fn in strata.items():
        kp = [i for i, p in enumerate(pids) if fn(p)]
        d = {"n": len(kp)}
        if len(kp) >= 5:
            d.update({"I_f1": float(X["I"][kp].mean()), "delta_AB_ci95": E39.pci(X["I"][kp], X["AB"][kp]),
                      "delta_BA_ci95": E39.pci(X["I"][kp], X["BA"][kp])})
        rep["strata"][s] = d
    # 오검출/미검출/빈 예측
    for c in X:
        scs = [e["scores"][t] for p in pids for e in ents(tab, p, c) for t in e["scores"]]
        rep[f"box_stats_{c}"] = {"recall_03_mean": float(np.mean([s_["recall_03"] for s_ in scs])),
                                 "fp_per_sentence_03": float(np.mean([s_["fp_03"] for s_ in scs])),
                                 "empty_pred_rate": float(np.mean([s_["empty"] for s_ in scs])),
                                 "pred_boxes_per_sentence": float(np.mean([s_["n_pred"] for s_ in scs])),
                                 "gt_boxes_per_sentence": float(np.mean([s_["n_gt"] for s_ in scs]))}
    rep["_per_patient_f1_03"] = {p: {c: float(X[c][i]) for c in X} for i, p in enumerate(pids)}
    rep["_X"] = {c: X[c] for c in X}
    return rep


def pct(x, q):
    return float(np.percentile(np.asarray(x, float), q))


def cost_rows(recs, mode):
    """queue별 환자 지연(첫 요청 시작 ~ 환자 요청 모두 종료)과 요청 wall 합. mode: I(2요청/환자) 또는 J(1요청/환자)."""
    by = {}
    for r in recs:
        by.setdefault(r["patient"], []).append(r)
    n_req = 2 if mode == "I" else 1
    assert all(len(v) == n_req for v in by.values()), "requests per patient"
    pids = sorted(by)
    lat = np.array([max(r["ts"] for r in by[p]) - min(r["t_start"] for r in by[p]) for p in pids])
    wsum = np.array([sum(r["wall_s"] for r in by[p]) for p in pids])
    tok = np.array([sum(a["n_new"] for r in by[p] for a in r["attempts"]) for p in pids])
    return pids, lat, wsum, tok


def cost_analysis(src_I, src_J):
    """src_I/J: {recs, completion}. I와 J 큐의 worker·GPU 구성이 같은지 확인하고 비율을 계산."""
    out = {}
    cI, cJ = src_I["comp"], src_J["comp"]
    same_cfg = cI["workers"] == cJ["workers"] and cI["mapping"] == cJ["mapping"]
    pi, latI, wI, tI = cost_rows(src_I["recs"], "I")
    pj, latJ, wJ, tJ = cost_rows(src_J["recs"], "J")
    assert pi == pj
    n = len(pi)
    CI, CJ = cI["cost"], cJ["cost"]

    def thr(c):
        return n / c["first_request_start_to_last_end_s"] * 60

    idx = metrics.bootstrap_indices(n, RULES.BOOT_B, RULES.BOOT_SEED)
    dev_proxy = wI[idx].mean(axis=1) / wJ[idx].mean(axis=1)
    lat_ratio = np.array([np.percentile(latI[i], 95) / np.percentile(latJ[i], 95) for i in idx])
    out = {"same_worker_gpu_config": bool(same_cfg), "workers": [cI["workers"], cJ["workers"]], "n_patients": n,
           "device_seconds_generate_union": [CI["device_seconds_generate_union"], CJ["device_seconds_generate_union"]],
           "device_seconds_incl_loading_union": [CI["device_seconds_incl_loading_union"], CJ["device_seconds_incl_loading_union"]],
           "device_seconds_per_patient": [CI["device_seconds_generate_union"] / n, CJ["device_seconds_generate_union"] / n],
           "devsec_ratio_I_over_J": CI["device_seconds_generate_union"] / CJ["device_seconds_generate_union"],
           "devsec_ratio_incl_loading": (CI["device_seconds_incl_loading_union"] / CJ["device_seconds_incl_loading_union"]
                                         if CI["device_seconds_incl_loading_union"] and CJ["device_seconds_incl_loading_union"] else None),
           "request_wall_sum_ratio_I_over_J": float(wI.sum() / wJ.sum()),
           "request_wall_ratio_bootstrap_ci95": [float(np.percentile(dev_proxy, 2.5)), float(np.percentile(dev_proxy, 97.5))],
           "latency_s": {"I": {"median": pct(latI, 50), "p95": pct(latI, 95), "mean": float(latI.mean())},
                         "J": {"median": pct(latJ, 50), "p95": pct(latJ, 95), "mean": float(latJ.mean())}},
           "p95_latency_ratio_I_over_J": pct(latI, 95) / pct(latJ, 95),
           "p95_latency_ratio_bootstrap_ci95": [float(np.percentile(lat_ratio, 2.5)), float(np.percentile(lat_ratio, 97.5))],
           "median_latency_ratio_I_over_J": pct(latI, 50) / pct(latJ, 50),
           "throughput_patients_per_min": [thr(CI), thr(CJ)], "throughput_ratio_I_over_J": thr(CI) / thr(CJ),
           "throughput_incl_loading_patients_per_min": [n / CI["launcher_wall_s_incl_loading"] * 60, n / CJ["launcher_wall_s_incl_loading"] * 60],
           "tokens_per_patient_all_attempts": [float(tI.mean()), float(tJ.mean())],
           "retried_requests": [CI["n_records_with_retry"], CJ["n_records_with_retry"]],
           "note": "device_seconds=GPU별 요청 구간 합집합(겹침 중복 합산 없음)의 GPU 합. 실제 커널 연산량이 아님. 비율 CI는 요청 wall 합 기반 환자 bootstrap이며 device-seconds 자체의 구간이 아니다."}
    return out


def load_res_peak(dirpath):
    mx = {}
    p = os.path.join(dirpath, "resource_log.jsonl")
    if os.path.exists(p):
        for l in open(p):
            for g in json.loads(l)["gpu"]:
                i, u, _ = [x.strip() for x in g.split(",")]
                mx[i] = max(mx.get(i, 0), int(u))
    return mx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("output exists")
    cfg = json.load(open(a.config))
    man = load_manifest(cfg["manifest"], cfg["selection_lock"], cfg["subset"])
    rep = {"config": cfg, "config_sha256": fsha(a.config),
           "source_digests": {f: fsha(f) for f in ("pg41_eval.py", "pg41_rules.py", "pg39_spec.py", "pg39_eval.py", "pg41_run.py",
                                                    "pg40_run.py", cfg["manifest"], cfg["selection_lock"])},
           "models": {}}
    data = {}
    for m, srcs in cfg["models"].items():
        data[m] = {}
        for k, s in srcs.items():
            recs = load_verified(s)
            comp = json.load(open(os.path.join(s["gen"], "completion.json")))
            data[m][k] = {"recs": recs, "comp": comp}
        tab = model_tab(data[m]["I"]["recs"], data[m]["JAB"]["recs"], data[m]["JBA"]["recs"], man)
        assert set(tab) == set(man), "patients != manifest subset"
        rep["models"][m] = eval_model(tab, man)
    # C 재실행 I(Icost)와 기존 I의 token 대조
    if "Icost" in data.get("C", {}):
        old = {(r["patient"], r["targets"][0]): r["suffix_ids"] for r in data["C"]["I"]["recs"]}
        new = {(r["patient"], r["targets"][0]): r["suffix_ids"] for r in data["C"]["Icost"]["recs"]}
        rep["C_I_rerun_vs_stored"] = {"n_compared": len(new), "token_mismatch": sum(old[k] != new[k] for k in new), "keys_equal": set(old) == set(new)}
        rep["cost"] = {}
        for c in ("JAB", "JBA"):
            rep["cost"][f"I_over_{c}"] = cost_analysis(data["C"]["Icost"], data["C"][c])
        rep["cost"]["peak_gpu_mib"] = {"Icost": load_res_peak(cfg["models"]["C"]["Icost"]["gen"]),
                                       "JAB": load_res_peak(cfg["models"]["C"]["JAB"]["gen"]), "JBA": load_res_peak(cfg["models"]["C"]["JBA"]["gen"])}
        rep["cost"]["queue_order"] = cfg.get("queue_order")
    # 판정
    C, B = rep["models"]["C"], rep["models"]["B"]
    cs = C["common_valid_eos_subset"]
    cm = [cs.get("delta_AB", [-1])[0], cs.get("delta_BA", [-1])[0]]
    acc = RULES.accuracy_class(C["delta_I_minus_JAB"]["ci975"], C["delta_I_minus_JBA"]["ci975"], B["delta_I_minus_JAB"]["ci975"][0],
                               B["delta_I_minus_JBA"]["ci975"][0], cm[0], cm[1])
    ca, cb = rep["cost"]["I_over_JAB"], rep["cost"]["I_over_JBA"]
    cost = RULES.cost_class([ca["devsec_ratio_I_over_J"], cb["devsec_ratio_I_over_J"]],
                            [ca["p95_latency_ratio_I_over_J"], cb["p95_latency_ratio_I_over_J"]],
                            [ca["throughput_ratio_I_over_J"], cb["throughput_ratio_I_over_J"]])
    strad = lambda ci, t: ci[0] < t <= ci[1]
    boundary = bool(any(strad(x["request_wall_ratio_bootstrap_ci95"], RULES.DEVSEC_RATIO_MIN) for x in (ca, cb)) or
                    (any(strad(x["p95_latency_ratio_bootstrap_ci95"], RULES.P95_LAT_RATIO_MIN) for x in (ca, cb)) and
                     not all(x["throughput_ratio_I_over_J"] <= RULES.THROUGHPUT_RATIO_MAX for x in (ca, cb))))
    same_cfg = ca["same_worker_gpu_config"] and cb["same_worker_gpu_config"]
    rep["decision"] = {"accuracy": acc, "cost": cost, "cost_boundary": boundary, "cost_queues_same_config": same_cfg,
                       "overall": RULES.overall(acc, cost, boundary) if same_cfg else "uncertain_hold_no_extension",
                       "B_deltas_point": [B["delta_I_minus_JAB"]["ci975"][0], B["delta_I_minus_JBA"]["ci975"][0]],
                       "C_common_subset_deltas_point": cm,
                       "scope": "V96 개발 자료 한 번의 비교. 독립 확인·내부 원인·모듈형 우위·신규 기여 판정이 아님."}
    perp = {m: rep["models"][m].pop("_per_patient_f1_03") for m in rep["models"]}
    for m in rep["models"]:
        rep["models"][m].pop("_X")
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump({**rep, "_per_patient_f1_03": perp}, open(a.out, "x"), indent=1, default=str)
    print(json.dumps({"models": {m: {k: rep["models"][m][k] for k in ("mean_f1_03", "delta_I_minus_JAB", "delta_I_minus_JBA", "common_valid_eos_subset")}
                                 for m in rep["models"]}, "decision": rep["decision"]}, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main()
