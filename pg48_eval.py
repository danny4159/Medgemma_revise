"""iter_048 평가 (CPU only): 문장별 최대 일대일 matching F1@0.3/0.5, recall, FP/문장, invalid·EOS. 환자 점수 = 두 문장 평균, J_J = AB/BA 평균.

점수 함수는 pg39_spec(parse_ids/score_request/sent_metrics)과 같은 생산 경로이며 독립 검증은 pg48_verify.py(별도 parser/matching)가 한다.
환자 paired bootstrap 10,000회, seed 4801 (같은 환자의 모든 조건을 함께 resample). 판정 규칙은 pg48_decide.py (결과 전에 고정).

라이브러리: score_dir / vectors / ci / diff. CLI: python pg48_eval.py --out results/iter_048/eval/report.json --epoch-sel results/iter_048/decisions/select.json
"""
import argparse
import hashlib
import json
import os
import sys
import time

import numpy as np

import pg39_spec as S39
import pg43_run as R
from rsna_diag import parse

MAN = "results/iter_043/data/manifest_private.json"
NBOOT = 10000
SEED = 4801
METRICS = ("f1_03", "f1_05", "recall_03", "fp_03")


def boot_idx(n, seed=SEED, B=NBOOT):
    return np.random.default_rng(seed).integers(0, n, size=(B, n), dtype=np.int32)


def ci(vals, level, idx):
    v = np.asarray(vals, float)
    m = v[idx].mean(axis=1)
    a = (1 - level) / 2 * 100
    return {"mean": float(v.mean()), "lo": float(np.percentile(m, a)), "hi": float(np.percentile(m, 100 - a)), "level": level}


def score_record(rec, e):
    """returns (status, {target: metrics}). e: manifest entry (GT canvas)."""
    tg = rec["targets"]
    r = S39.parse_ids(rec["suffix_text_raw"], rec["ended_eos"], set(tg))
    return r["status"], S39.score_request(r["status"], r["groups"], tg, e["gt_canvas_yxyx"]), r


def score_dir(records_by_key, ents):
    """records_by_key: {(patient, cond, targets_tuple): record}. returns per-system dict:
    I: {(p,t): (status, metrics, eos, n_out_tok)}, AB/BA: {p: (status, {t: metrics}, eos, n_out_tok)}"""
    out = {"I": {}, "AB": {}, "BA": {}}
    for (p, cond, tg), rec in records_by_key.items():
        st, sc, _ = score_record(rec, ents[p])
        if cond == "I-short":
            out["I"][(p, tg[0])] = (st, sc[tg[0]], bool(rec["ended_eos"]), rec["n_output_tokens"])
        elif cond == "J-short":
            out["AB"][p] = (st, sc, bool(rec["ended_eos"]), rec["n_output_tokens"])
        elif cond == "J-short-rev":
            out["BA"][p] = (st, sc, bool(rec["ended_eos"]), rec["n_output_tokens"])
        else:
            raise ValueError(cond)
    return out


def score_a(a_recs, ents, thr="0.8"):
    """MedGrounder 출력 (원본 정규화 xyxy)을 GT(원본 정규화 xyxy)와 같은 matching 함수로 채점."""
    out = {}
    for (p, t), r in a_recs.items():
        boxes = r["detections"][thr]["boxes_orig_xyxy"]
        gt = ents[p]["gt_boxes_xyxy_norm"][t]
        m3, m5 = S39.sent_metrics(boxes, gt, 0.3), S39.sent_metrics(boxes, gt, 0.5)
        out[(p, t)] = {"f1_03": m3["f1"], "f1_05": m5["f1"], "recall_03": m3["recall"], "fp_03": m3["fp"], "n_pred": len(boxes), "n_gt": len(gt)}
    return out


def pat_vec(scored, pids, kind, metric):
    """환자별 두 문장 평균 벡터. kind: I | AB | BA | J(AB,BA 평균) | A."""
    if kind == "I":
        return np.array([np.mean([scored["I"][(p, t)][1][metric] for t in ("qA", "qB")]) for p in pids])
    if kind in ("AB", "BA"):
        return np.array([np.mean([scored[kind][p][1][t][metric] for t in ("qA", "qB")]) for p in pids])
    if kind == "J":
        return (pat_vec(scored, pids, "AB", metric) + pat_vec(scored, pids, "BA", metric)) / 2
    raise ValueError(kind)


def a_vec(a_scored, pids, metric):
    return np.array([np.mean([a_scored[(p, t)][metric] for t in ("qA", "qB")]) for p in pids])


def summarize(scored, pids, idx):
    res = {}
    for kind in ("I", "AB", "BA", "J"):
        res[kind] = {m: ci(pat_vec(scored, pids, kind, m), 0.95, idx) for m in METRICS}
    for kind in ("I", "AB", "BA"):
        items = list(scored[kind].values())
        res[kind]["n_requests"] = len(items)
        res[kind]["n_invalid"] = sum(it[0] not in parse.VALID for it in items)
        res[kind]["status_counts"] = {s: sum(it[0] == s for it in items) for s in sorted({it[0] for it in items})}
        res[kind]["eos_rate"] = float(np.mean([it[2] for it in items]))
        res[kind]["mean_output_tokens"] = float(np.mean([it[3] for it in items]))
    return res


def build_report(systems, a_scored, ents, pids, strata_info):
    """systems: {name: scored}. 모든 비교는 같은 환자 index에서."""
    idx = boot_idx(len(pids))
    rep = {"n_patients": len(pids), "bootstrap": {"B": NBOOT, "seed": SEED}, "systems": {}, "A": {}, "compare": {}}
    for n, sc in systems.items():
        rep["systems"][n] = summarize(sc, pids, idx)
    rep["A"] = {m: ci(a_vec(a_scored, pids, m), 0.95, idx) for m in METRICS}
    V = {}
    for n, sc in systems.items():
        for kind in ("I", "AB", "BA", "J"):
            for m in METRICS:
                V[(n, kind, m)] = pat_vec(sc, pids, kind, m)
    for m in METRICS:
        V[("A", "A", m)] = a_vec(a_scored, pids, m)

    def d(x, y, m, level):
        return ci(V[x + (m,)] - V[y + (m,)], level, idx)
    cmp = {}
    # 주비교 1/2 (97.5%)
    cmp["M1_J_J_minus_E_J"] = {"f1_03_ci975": d(("J", "J"), ("E", "J"), "f1_03", 0.975), "f1_03_ci95": d(("J", "J"), ("E", "J"), "f1_03", 0.95)}
    e_loss = V[("E", "I", "f1_03")] - V[("E", "J", "f1_03")]
    j_loss = V[("J", "I", "f1_03")] - V[("J", "J", "f1_03")]
    cmp["M2_loss_reduction_(E_I-E_J)-(J_I-J_J)"] = {"f1_03_ci975": ci(e_loss - j_loss, 0.975, idx), "f1_03_ci95": ci(e_loss - j_loss, 0.95, idx)}
    cmp["E_loss_E_I_minus_E_J"] = {"f1_03_ci95": ci(e_loss, 0.95, idx)}
    cmp["J_loss_J_I_minus_J_J"] = {"f1_03_ci95": ci(j_loss, 0.95, idx), "f1_03_ci975": ci(j_loss, 0.975, idx)}
    cmp["J_I_minus_E_I"] = {m: {"ci95": d(("J", "I"), ("E", "I"), m, 0.95)} for m in METRICS}
    # 충분성: J_AB / J_BA vs E_I
    for o in ("AB", "BA"):
        cmp[f"J_{o}_minus_E_I"] = {"f1_03_ci975": d(("J", o), ("E", "I"), "f1_03", 0.975), "f1_05_ci95": d(("J", o), ("E", "I"), "f1_05", 0.95),
                                   "fp_03_ci95": d(("J", o), ("E", "I"), "fp_03", 0.95), "recall_03_ci95": d(("J", o), ("E", "I"), "recall_03", 0.95)}
    # 추가 기준 비교
    for name, x in (("E_I", ("E", "I")), ("J_J", ("J", "J")), ("J_I", ("J", "I")), ("E_J", ("E", "J")), ("C_I", ("C", "I")), ("C_J", ("C", "J"))):
        cmp[f"{name}_minus_A"] = {"f1_03_ci975": d(x, ("A", "A"), "f1_03", 0.975), "f1_03_ci95": d(x, ("A", "A"), "f1_03", 0.95),
                                  "f1_05_ci95": d(x, ("A", "A"), "f1_05", 0.95), "fp_03_ci95": d(x, ("A", "A"), "fp_03", 0.95),
                                  "recall_03_ci95": d(x, ("A", "A"), "recall_03", 0.95)}
    for tgt in ("E", "J"):
        cmp[f"{tgt}_I_minus_C_I"] = {"f1_03_ci95": d((tgt, "I"), ("C", "I"), "f1_03", 0.95)}
        cmp[f"{tgt}_J_minus_C_J"] = {"f1_03_ci95": d((tgt, "J"), ("C", "J"), "f1_03", 0.95)}
    cmp["J_J_minus_J_I_residual"] = {"f1_03_ci95": ci(-j_loss, 0.95, idx)}
    rep["compare"] = cmp
    # 층별 (사전 정의; 결과와 무관)
    rep["strata"] = strata_info["fn"](systems, a_scored, ents, pids, V, idx)
    return rep, V


def strata(systems, a_scored, ents, pids, V, idx):
    """multi/single box 문장, 작은/큰 GT (가장 큰 GT box 면적이 V96 192문장 중앙값 미만), 환자 stratum. 환자 벡터 대신 문장 단위 평균 F1@0.3 (I/J 조건 문장 점수 평균)."""
    def area(b):
        return max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    mx = {(p, t): max(area(b) for b in ents[p]["gt_boxes_xyxy_norm"][t]) for p in pids for t in ("qA", "qB")}
    med = float(np.median(list(mx.values())))
    groups = {"multi_box": lambda p, t: len(ents[p]["gt_boxes_xyxy_norm"][t]) > 1, "single_box": lambda p, t: len(ents[p]["gt_boxes_xyxy_norm"][t]) == 1,
              "small_box(max GT area<median)": lambda p, t: mx[(p, t)] < med, "large_box": lambda p, t: mx[(p, t)] >= med}
    out = {"small_threshold_max_gt_area_median": med}
    for gname, fn in groups.items():
        ks = [(p, t) for p in pids for t in ("qA", "qB") if fn(p, t)]
        row = {"n_sentences": len(ks), "systems": {}}
        for n, sc in systems.items():
            def s_I(k):
                return sc["I"][k][1]["f1_03"]

            def s_J(k):
                return np.mean([sc["AB"][k[0]][1][k[1]]["f1_03"], sc["BA"][k[0]][1][k[1]]["f1_03"]])
            row["systems"][n] = {"I_f1_03": float(np.mean([s_I(k) for k in ks])), "J_f1_03": float(np.mean([s_J(k) for k in ks])),
                                 "I_missed_gt": float(np.mean([sc["I"][k][1]["n_gt"] - sc["I"][k][1]["tp_03"] for k in ks])),
                                 "I_fp": float(np.mean([sc["I"][k][1]["fp_03"] for k in ks]))}
        row["systems"]["A"] = {"f1_03": float(np.mean([a_scored[k]["f1_03"] for k in ks])), "missed_gt": float(np.mean([a_scored[k]["n_gt"] - a_scored[k]["recall_03"] * a_scored[k]["n_gt"] for k in ks])),
                               "fp": float(np.mean([a_scored[k]["fp_03"] for k in ks]))}
        out[gname] = row
    return out


def main():
    import pg48_import as IM
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--select", required=True, help="results/iter_048/decisions/select.json (공통 epoch·adapter·gen dir)")
    ap.add_argument("--dry-run-c", action="store_true", help="코드 경로 검사 전용: E/J 자리에 C 출력을 넣는다 (결과는 tests/dryrun에만 저장, 판정에 쓰지 않는다)")
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("output exists")
    t0 = time.time()
    man = json.load(open(MAN))
    ents = {e["PatientID"]: e for e in man["V96"]}
    pids = [e["PatientID"] for e in man["V96"]]
    for e in man["V96"]:  # 현재 영상 hash
        if R.file_sha(e["image"]) != e["image_file_sha256"] or R.G.load_image(e["image"])[2] != e["input_pixel_sha256"]:
            raise R.RunError(f"current image hash mismatch {e['PatientID']}")
    sel = json.load(open(a.select)) if not a.dry_run_c else {"common_epoch": "dryrun", "adapters": {}, "v96_runs": {}}
    if a.dry_run_c and "tests/dryrun" not in a.out:
        sys.exit("--dry-run-c output must live under tests/dryrun")
    c = IM.load_c_v96()
    csc = {"I": {}, "AB": {}, "BA": {}}
    for tag in ("I", "AB", "BA"):
        sub = score_dir(c[tag]["records"], ents)
        csc[tag] = sub[tag]
    systems = {"C": csc}
    prov = {"C": {t: {"gen_dir": c[t]["gen_dir"], "completion_sha256": c[t]["completion_sha256"], "protocol_digest": c[t]["protocol_digest"]} for t in c}}
    for n in ("E", "J"):
        if a.dry_run_c:
            systems[n] = {k: dict(v) for k, v in csc.items()}
            prov[n] = {"gen_dir": c["I"]["gen_dir"], "dry_run_stand_in": "C"}
            continue
        info = sel["v96_runs"][n]
        recs = R.verify_completion(info["gen_dir"], info["requests"], info["protocol"])
        pd_, proto = R.verify_protocol(info["protocol"], info["requests"])
        if proto["adapter"]["digest"] != sel["adapters"][n]["digest"]:
            raise R.RunError(f"{n}: protocol adapter != selection")
        byk = {(r["patient"], r["cond"], tuple(r["targets"])): r for r in recs}
        systems[n] = score_dir(byk, ents)
        prov[n] = {"gen_dir": info["gen_dir"], "completion_sha256": R.file_sha(os.path.join(info["gen_dir"], "completion.json")), "protocol_digest": pd_,
                   "protocol_sha256": R.file_sha(info["protocol"]), "adapter_digest": proto["adapter"]["digest"], "epoch": sel["common_epoch"]}
    av = IM.load_a_v96()
    a_scored = score_a(av["records"], ents)
    prov["A"] = {"gen_dir": av["gen_dir"], "completion_sha256": av["completion_sha256"], "ckpt_sha256": IM.A_SHA, "threshold": 0.8}
    rep, V = build_report(systems, a_scored, ents, pids, {"fn": strata})
    rep["provenance"] = dict(prov, eval_source_sha256=R.file_sha("pg48_eval.py"), manifest_sha256=R.file_sha(MAN), select_sha256=(R.file_sha(a.select) if not a.dry_run_c else None),
                             spec_sha256=R.file_sha("pg39_spec.py"), parse_sha256=R.file_sha("rsna_diag/parse.py"), metrics_sha256=R.file_sha("rsna_diag/metrics.py"),
                             eval_wall_s=time.time() - t0)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    per = {"patients": pids, "vectors": {f"{k[0]}|{k[1]}|{k[2]}": v.tolist() for k, v in V.items()}}
    tmp2 = a.out.replace(".json", "_per_patient.json") + f".{os.getpid()}.tmp"
    json.dump(per, open(tmp2, "w"))
    tmp = a.out + f".{os.getpid()}.tmp"
    json.dump(rep, open(tmp, "w"), indent=1)
    os.replace(tmp2, a.out.replace(".json", "_per_patient.json"))
    os.replace(tmp, a.out)
    print(json.dumps({n: {k: rep["systems"][n][k]["f1_03"]["mean"] for k in ("I", "AB", "BA", "J")} for n in rep["systems"]}, indent=1))
    print("A f1_03", rep["A"]["f1_03"]["mean"])


if __name__ == "__main__":
    main()
