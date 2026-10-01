"""iter_046 독립 검증기 (CPU only). mg46_report의 계산(pg39_spec.match_fast / parse_ids / mg45_eval.score)과 별도로 구현한다.
  - C: 자체 JSON 해석(전체 문자열이 JSON list) + 자체 canvas->원본 정규화 변환.
  - MG(P, A): raw logits에서 softmax/threshold 통과 수(pre_wbf_n) 재계산, 저장된 최종 box를 자체 완전탐색 matching으로 채점.
  - 모든 판정 지표(F1@0.3, F1@0.5, FP/문장, recall@0.3)의 시스템 평균과 6개 paired 비교의 97.5% CI(자체 bootstrap)를 report와 대조.
  - 모든 시스템의 요청 ID 집합(192), box 유한성·양의 크기, C 파싱 상태를 검사한다. 불일치 시스템/환자를 제외한 PASS 금지.
python mg46_verify.py --report results/iter_046/eval/report.json --out results/iter_046/eval/verify.json
"""
import argparse
import glob
import json
import os
import sys

import numpy as np

import mg45_eval as E
import mg46_eval as E6
import mg45_verify as V

MAN = E.MAN
ROOT = "results/iter_046"
METRICS = ("f1_03", "f1_05", "fp_03", "recall_03")


def f1_all(pred, gt):
    tp3 = V.best_matching(pred, gt, 0.3)
    tp5 = V.best_matching(pred, gt, 0.5)

    def f(tp):
        p = tp / len(pred) if pred else 0.0
        r = tp / len(gt) if gt else 0.0
        return 2 * p * r / (p + r) if p + r > 0 else 0.0
    return {"f1_03": f(tp3), "f1_05": f(tp5), "fp_03": len(pred) - tp3, "recall_03": tp3 / len(gt) if gt else 0.0, "empty": len(pred) == 0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("output exists")
    rep = json.load(open(a.report))
    per = json.load(open(a.report.replace(".json", "_per_item.json")))
    man = json.load(open(MAN))
    fin = json.load(open(f"{ROOT}/decisions/final_selection.json"))
    ents = {e["PatientID"]: e for e in man["V96"]}
    pids = sorted(ents)
    want_keys = {(p, t) for p in pids for t in ("qA", "qB")}
    res = {"mismatches": [], "systems": {}, "checks": {}}
    # ---- C ----
    crecs = {}
    for f in glob.glob("results/iter_040/gen/C/gen_worker*.jsonl"):
        for l in open(f):
            if l.strip():
                r = json.loads(l)
                if (r["patient"], r["targets"][0]) in crecs:
                    res["mismatches"].append("C duplicate record")
                crecs[(r["patient"], r["targets"][0])] = r
    if set(crecs) != want_keys:
        res["mismatches"].append("C key set != expected 192")
    own_c, n_unparsed = {}, 0
    for (p, t), r in crecs.items():
        e = ents[p]
        top, left, side = r["pad_affine_top_left_side"]
        boxes = V.own_parse_list(r["suffix_text_raw"]) if r["ended_eos"] else None
        if boxes is None:
            n_unparsed += 1
            boxes = []
        orig = [[(x0 * side / 1000 - left) / e["w"], (y0 * side / 1000 - top) / e["h"], (x1 * side / 1000 - left) / e["w"], (y1 * side / 1000 - top) / e["h"]] for y0, x0, y1, x1 in boxes]
        if not all(np.isfinite(x) for b in orig for x in b):
            res["mismatches"].append("C nonfinite box")
        own_c[(p, t)] = f1_all(orig, e["gt_boxes_xyxy_norm"][t])
    res["checks"]["C_unparsed_or_noneos"] = n_unparsed
    # ---- MG ----
    a_recs, _, _ = E6.verify_dir(f"{ROOT}/mg/V96_A_w2b4", "V96", "A_final", fin["ckpt_path"], man)
    p_recs, _, _ = E.verify_mg_dir("results/iter_045/mg/V96_P_w2b4", "V96", "P", man, allow_code_diff=True)
    p_thr = json.load(open("results/iter_045/decisions/D24_select.json"))["ckpts"]["P"]["selected_threshold"]

    def mg_own(recs, thr):
        out, pass_bad, bad_box = {}, 0, 0
        if set(recs) != want_keys:
            res["mismatches"].append("MG key set != expected 192")
        for (p, t), r in recs.items():
            lg = np.array(r["logits"], dtype=np.float64)
            ex = np.exp(lg - lg.max(axis=-1, keepdims=True))
            n_pass = int(((ex / ex.sum(axis=-1, keepdims=True))[:, 0] > thr).sum())
            pass_bad += int(n_pass != r["detections"][str(thr)]["pre_wbf_n"])
            boxes = r["detections"][str(thr)]["boxes_orig_xyxy"]
            bad_box += int(any((not all(np.isfinite(b))) or b[2] <= b[0] or b[3] <= b[1] for b in boxes))
            out[(p, t)] = f1_all(boxes, ents[p]["gt_boxes_xyxy_norm"][t])
        return out, pass_bad, bad_box
    systems = {"C": (own_c, 0, 0), "P@sel": mg_own(p_recs, p_thr), "A@0.4": mg_own(a_recs, 0.4), "A@sel": mg_own(a_recs, fin["selected_threshold"]),
               "A@0.8": mg_own(a_recs, 0.8), "P@0.8": mg_own(p_recs, 0.8)}
    pat = {s: {m: np.array([np.mean([sc[(p, t)][m] for t in ("qA", "qB")]) for p in pids]) for m in METRICS} for s, (sc, _, _) in systems.items()}
    for s, (sc, pass_bad, bad_box) in systems.items():
        rp = per[s]
        md = {m: max(abs(v[m] - rp[f"{p}|{t}"][m]) for (p, t), v in sc.items()) for m in METRICS}
        prim = rep["primary_V96"][s]
        means = {"f1_03": pat[s]["f1_03"].mean(), "f1_05": pat[s]["f1_05"].mean(), "fp_per_sentence": pat[s]["fp_03"].mean(), "recall_03": pat[s]["recall_03"].mean()}
        ok = all(v < 1e-9 for v in md.values()) and pass_bad == 0 and bad_box == 0 and all(abs(means[k] - prim[k]) < 1e-9 for k in means)
        res["systems"][s] = {"own": {k: float(v) for k, v in means.items()}, "max_abs_item_diff_vs_report": md, "threshold_pass_count_mismatch": pass_bad, "bad_boxes": bad_box, "ok": bool(ok)}
        if not ok:
            res["mismatches"].append(s)
    res["C_matches_stored_iter040"] = bool(abs(res["systems"]["C"]["own"]["f1_03"] - 0.5779513888888889) < 1e-9 and abs(res["systems"]["C"]["own"]["f1_05"] - 0.2911458333333333) < 1e-9)
    if not res["C_matches_stored_iter040"]:
        res["mismatches"].append("C_stored")
    # ---- 독립 bootstrap: 모든 판정 비교 x 모든 지표 ----
    idx = np.random.default_rng(4401).integers(0, len(pids), size=(10000, len(pids)), dtype=np.int32)
    res["bootstrap"] = {}
    for x, y in (("A@0.4", "P@sel"), ("A@sel", "C"), ("C", "A@sel"), ("A@sel", "P@sel"), ("A@0.4", "C"), ("A@0.8", "P@0.8")):
        name = f"{x}_minus_{y}"
        res["bootstrap"][name] = {}
        for m in METRICS:
            d = pat[x][m] - pat[y][m]
            mm = d[idx].mean(axis=1)
            lo, hi = float(np.percentile(mm, 1.25)), float(np.percentile(mm, 98.75))
            rc = rep["compare_paired_ci975"][name][m]
            ok = abs(lo - rc["lo"]) < 1e-9 and abs(hi - rc["hi"]) < 1e-9 and abs(d.mean() - rc["mean"]) < 1e-9
            res["bootstrap"][name][m] = {"own": [float(d.mean()), lo, hi], "report": [rc["mean"], rc["lo"], rc["hi"]], "ok": bool(ok)}
            if not ok:
                res["mismatches"].append(f"bootstrap {name} {m}")
    # ---- 비용 비율 독립 재계산 ----
    import math
    att = {k: 1 for k in range(1, 7)}
    ap_ = f"{ROOT}/timing/attempts.json"
    if os.path.exists(ap_):
        att.update({int(k): v for k, v in json.load(open(ap_)).items()})
    t5 = 2.5705818366147395
    ratios = {"device_seconds_span": [], "patients_per_min": [], "p95": []}
    for k in range(1, 7):
        row = {}
        for s in ("A", "P"):
            d = f"{ROOT}/timing/block{k}_a{att[k]}_{s}"
            files = sorted(glob.glob(d + "/raw_worker*.jsonl"))
            recs = [json.loads(l) for f in files for l in open(f, "rb").read().split(b"\n")[:-1] if l.strip()]
            comp = json.load(open(d + "/completion.json"))
            if len(recs) != 192 or len({r["request_id"] for r in recs}) != 192 or any(c != 0 for c in comp["exit_codes"]):
                res["mismatches"].append(f"timing {s}{k} incomplete/duplicate")
            mp = {int(w): g for w, g in comp["mapping"].items()}
            bp = {}
            for r in recs:
                bp.setdefault(r["patient"], []).append(r)
            lat = [max(x["t_orig_done"] for x in v) - min(x["t_dispatch"] for x in v) for v in bp.values()]
            gi = {}
            for v in bp.values():
                gi.setdefault(mp[v[0]["worker"]], []).append((min(x["t_dispatch"] for x in v), max(x["t_orig_done"] for x in v)))
            row[s] = {"span": sum(max(e for _, e in v) - min(s_ for s_, _ in v) for v in gi.values()), "ppm": 96 / comp["workload_wall_s"] * 60, "p95": float(np.percentile(lat, 95))}
        ratios["device_seconds_span"].append(row["A"]["span"] / row["P"]["span"])
        ratios["patients_per_min"].append(row["A"]["ppm"] / row["P"]["ppm"])
        ratios["p95"].append(row["A"]["p95"] / row["P"]["p95"])
    cost_own = {}
    for k, v in ratios.items():
        lr = np.log(v)
        se = lr.std(ddof=1) / math.sqrt(6)
        cost_own[k] = {"geo_mean": float(math.exp(lr.mean())), "lo": float(math.exp(lr.mean() - t5 * se)), "hi": float(math.exp(lr.mean() + t5 * se))}
    rc = rep["cost"]
    for k, rk in (("device_seconds_span", "A_over_P_device_seconds_span"), ("patients_per_min", "A_over_P_throughput"), ("p95", "A_over_P_p95_latency")):
        ok = abs(cost_own[k]["geo_mean"] - rc[rk]["geo_mean"]) < 1e-9 and abs(cost_own[k]["lo"] - rc[rk]["ci95_lo"]) < 1e-9 and abs(cost_own[k]["hi"] - rc[rk]["ci95_hi"]) < 1e-9
        cost_own[k]["ok"] = bool(ok)
        if not ok:
            res["mismatches"].append(f"cost {k}")
    res["cost_own"] = cost_own
    res["PASS"] = len(res["mismatches"]) == 0
    json.dump(res, open(a.out, "x"), indent=1)
    print(json.dumps({"PASS": res["PASS"], "mismatches": res["mismatches"], "systems": {k: v["ok"] for k, v in res["systems"].items()}, "C_unparsed": n_unparsed}))
    sys.exit(0 if res["PASS"] else 1)


if __name__ == "__main__":
    main()
