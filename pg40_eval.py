"""iter_040 문장별 grounding 평가 (I-short 요청). 완료 검증(verify_completion)을 통과한 생성 결과 + 잠긴 eval manifest만 사용한다.

python pg40_eval.py --subset V96 --model M0=results/iter_039/gen/E96,results/iter_039/requests_v2/requests_E96.jsonl,results/iter_039/protocol/protocol_E96.json,iter039 \
    --model B=<gen_dir>,<requests>,<protocol>,iter040 --pairs M:C M:C_compute --out results/iter_040/eval/x.json
- 주지표: 환자 평균(두 문장 평균) F1@IoU0.3, 문장별 maximum-cardinality one-to-one matching (pg39_spec.match_fast / sent_metrics).
- 비교: 동일 환자 paired bootstrap 10,000회 seed 20260930, 95%와 97.5% CI.
"""
import argparse
import json
import os
import sys

import numpy as np

import pg39_eval as E
import pg39_run as R39
import pg40_run as R40
import pg39_spec as S
from rsna_diag import parse

EVAL_MANIFEST = "results/iter_040/data/manifest_eval_private.jsonl"
SMALL_AREA = E.SMALL_AREA


def load_eval_manifest(subset):
    out = {}
    for l in open(EVAL_MANIFEST):
        r = json.loads(l)
        if subset == "V96" and r["eval_set"] == "V96" or subset == "V48" and r["eval_set"] == "V96" and r["is_V48"] or subset == "H192" and r["eval_set"] == "H192":
            out[r["PatientID"]] = r
    return out


def load_recs(spec, subset, man):
    name, gen, req, proto, kind = spec
    R = R39 if kind == "iter039" else R40
    recs = R.verify_completion(gen, req, proto)
    recs = [r for r in recs if r["cond"] == "I-short" and r["patient"] in man]
    if {(r["patient"], tuple(r["targets"])) for r in recs} != {(p, (t,)) for p in man for t in ("qA", "qB")} or len(recs) != 2 * len(man):
        raise SystemExit(f"{name}: I-short records do not cover subset {subset} exactly (missing/duplicate/extra)")
    return recs


def sent_table(recs, man):
    """returns {patient: {qA: {...}, qB: {...}}} (문장별 F1@.3/.5, recall, fp, empty, union_iou, status, tokens ...)."""
    tab = E.patient_table(recs, man)
    out = {}
    for p, conds in tab.items():
        d = {}
        for tg, e in conds["I-short"]:
            t = tg[0]
            sc = e["scores"][t]
            d[t] = {"f1_03": sc["f1_03"], "f1_05": sc["f1_05"], "recall_03": sc["recall_03"], "fp_03": sc["fp_03"], "tp_03": sc["tp_03"],
                    "n_pred": sc["n_pred"], "n_gt": sc["n_gt"], "empty": bool(sc["empty"]), "union_iou": sc["union_iou"], "status": e["status"],
                    "valid": e["valid"], "eos": e["eos"], "n_out": e["n_out"], "wall": e["wall"], "peak_gb": e["peak_gb"], "caps_used": e["caps_used"],
                    "groups": e["groups"]}
        out[p] = d
    return out


def patient_vec(st, pids, key):
    return np.array([np.mean([st[p][t][key] for t in ("qA", "qB")]) for p in pids])


def summary(st, pids, man, recs):
    keys = ["f1_03", "f1_05", "recall_03", "fp_03", "union_iou"]
    d = {"n_patients": len(pids), "n_requests": 2 * len(pids)}
    for k in keys:
        d[k] = E.ci(patient_vec(st, pids, k))
    sents = [st[p][t] for p in pids for t in ("qA", "qB")]
    d["fp_per_sentence"] = float(np.mean([s["fp_03"] for s in sents]))
    d["empty_pred_rate"] = float(np.mean([s["empty"] for s in sents]))
    d["invalid_rate"] = float(np.mean([not s["valid"] for s in sents]))
    d["unresolved_truncation_rate"] = float(np.mean([not s["eos"] for s in sents]))
    d["status_counts"] = {}
    for s in sents:
        d["status_counts"][s["status"]] = d["status_counts"].get(s["status"], 0) + 1
    d["cost"] = {"mean_wall_s_per_request": float(np.mean([r["wall_s"] for r in recs])),
                 "mean_generate_s_per_request": float(np.mean([r["runtime_s_total"] for r in recs])),
                 "mean_final_out_tokens": float(np.mean([r["n_output_tokens"] for r in recs])),
                 "mean_new_tokens_all_attempts": float(np.mean([sum(a["n_new"] for a in r["attempts"]) for r in recs])),
                 "retry_rate": float(np.mean([len(r["attempts"]) > 1 for r in recs])),
                 "peak_alloc_gb_max": float(max(r["peak_mem_alloc_gb_max"] for r in recs))}
    return d


def strata(st, pids, man):
    cross = {p: S.cross_iou_max(*(E.gt_canvas(man[p])[k] for k in ("qA", "qB"))) for p in pids}

    def small(p):
        return any((b[2] - b[0]) * (b[3] - b[1]) < SMALL_AREA for k in ("qA", "qB") for b in man[p]["gt_boxes_xyxy_norm"][k])
    defs = {"multi_box": lambda p: any(len(man[p]["gt_boxes_xyxy_norm"][k]) > 1 for k in ("qA", "qB")),
            "single_box": lambda p: all(len(man[p]["gt_boxes_xyxy_norm"][k]) == 1 for k in ("qA", "qB")),
            "share_group": lambda p: man[p]["stratum"].startswith("share1"), "small_box": small,
            "contrast_eligible(cross_iou<0.1)": lambda p: cross[p] < 0.1, "overlap(cross_iou>=0.1)": lambda p: cross[p] >= 0.1}
    out = {}
    for s, fn in defs.items():
        keep = [p for p in pids if fn(p)]
        out[s] = {"n": len(keep), "f1_03_mean": float(patient_vec(st, keep, "f1_03").mean()) if keep else None,
                  "f1_05_mean": float(patient_vec(st, keep, "f1_05").mean()) if keep else None}
    return out


def discrimination(st, pids, man):
    """서로 분리된 GT 쌍(cross-IoU<0.1) 환자에서: 자기 문장 GT 대비 F1 - 다른 문장 GT 대비 F1 (생성된 해당 문장 예측 기준)."""
    gaps, own, oth = [], [], []
    for p in pids:
        gt = E.gt_canvas(man[p])
        if S.cross_iou_max(gt["qA"], gt["qB"]) >= 0.1:
            continue
        for t, o in (("qA", "qB"), ("qB", "qA")):
            pred = st[p][t]["groups"][t] if st[p][t]["valid"] else []
            a = S.sent_metrics(pred, gt[t], 0.3)["f1"]
            b = S.sent_metrics(pred, gt[o], 0.3)["f1"]
            own.append(a)
            oth.append(b)
            gaps.append(a - b)
    if not gaps:
        return None
    return {"n_sentences": len(gaps), "own_f1": float(np.mean(own)), "other_sentence_gt_f1": float(np.mean(oth)), "gap_mean": float(np.mean(gaps))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subset", required=True, choices=["V48", "V96", "H192"])
    ap.add_argument("--model", action="append", required=True, help="NAME=gen_dir,requests,protocol,iter039|iter040")
    ap.add_argument("--pairs", nargs="*", default=[], help="A:B  (A-B)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("output exists")
    man = load_eval_manifest(a.subset)
    pids = sorted(man)
    specs = []
    for m in a.model:
        n, rest = m.split("=", 1)
        g, rq, pr, kind = rest.split(",")
        specs.append((n, g, rq, pr, kind))
    rep = {"subset": a.subset, "n_patients": len(pids), "models": {}, "pairs": {}, "sources": {n: {"gen": g, "requests": rq, "protocol": pr, "kind": k}
                                                                                       for n, g, rq, pr, k in specs}}
    tabs = {}
    for spec in specs:
        recs = load_recs(spec, a.subset, man)
        st = sent_table(recs, man)
        tabs[spec[0]] = st
        rep["models"][spec[0]] = {"summary": summary(st, pids, man, recs), "strata": strata(st, pids, man), "discrimination": discrimination(st, pids, man),
                                  "protocol_sha256": R40.file_sha(spec[3])}
    for pr in a.pairs:
        x, y = pr.split(":")
        d = {}
        for k in ("f1_03", "f1_05", "recall_03", "fp_03"):
            va, vb = patient_vec(tabs[x], pids, k), patient_vec(tabs[y], pids, k)
            d[k] = {"diff_mean_ci95": E.pci(va, vb, 0.95), "diff_mean_ci975": E.pci(va, vb, 0.975), "sd_paired": float(np.std(va - vb, ddof=1))}
        d["fp_per_sentence_diff"] = rep["models"][x]["summary"]["fp_per_sentence"] - rep["models"][y]["summary"]["fp_per_sentence"]
        d["invalid_rate_diff_pp"] = 100 * (rep["models"][x]["summary"]["invalid_rate"] - rep["models"][y]["summary"]["invalid_rate"])
        d["truncation_rate_diff_pp"] = 100 * (rep["models"][x]["summary"]["unresolved_truncation_rate"] - rep["models"][y]["summary"]["unresolved_truncation_rate"])
        va, vb = patient_vec(tabs[x], pids, "f1_03"), patient_vec(tabs[y], pids, "f1_03")
        d["patients_a_better/equal/worse"] = [int((va > vb + 1e-12).sum()), int((abs(va - vb) <= 1e-12).sum()), int((va < vb - 1e-12).sum())]
        rep["pairs"][pr] = d
    rep["_per_patient_f1_03"] = {n: {p: float(np.mean([tabs[n][p][t]["f1_03"] for t in ("qA", "qB")])) for p in pids} for n in tabs}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(rep, open(a.out, "w"), indent=1)
    print(json.dumps({n: {"f1_03": rep["models"][n]["summary"]["f1_03"], "f1_05": rep["models"][n]["summary"]["f1_05"][0],
                          "invalid": rep["models"][n]["summary"]["invalid_rate"], "trunc": rep["models"][n]["summary"]["unresolved_truncation_rate"]}
                     for n in rep["models"]}, indent=1))
    for k, v in rep["pairs"].items():
        print(k, "f1_03 diff", v["f1_03"]["diff_mean_ci975"], "f1_05", v["f1_05"]["diff_mean_ci95"][0], "fp/sent", v["fp_per_sentence_diff"])


if __name__ == "__main__":
    main()
