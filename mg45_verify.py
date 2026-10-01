"""iter_045 독립 검증기 (CPU only). report 계산(pg39_spec.match_fast / parse_ids)과 별도로 구현한다:
  - C 출력: 자체 JSON 해석(전체 문자열이 JSON list) + 자체 canvas->원본 정규화 변환 + 완전탐색 최대 cardinality matching(동률 총 IoU 최대).
  - MG 출력: raw logits에서 softmax/threshold 통과 수 재계산(pre_wbf_n), 저장된 최종 box를 같은 완전탐색 matching으로 채점.
  - report 의 시스템별 환자 F1@0.3/0.5, FP/문장, 평균과 paired bootstrap CI(C - MG-selected)를 독립 계산해 대조한다.
불일치가 하나라도 있으면 종료 코드 1 (불일치 시스템/환자를 제외한 PASS 금지).
python mg45_verify.py --report results/iter_045/eval/report.json --out results/iter_045/eval/verify.json
"""
import argparse
import itertools
import json
import math
import os
import sys

import numpy as np

import mg45_eval as E

MAN = E.MAN


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def best_matching(pred, gt, thr):
    """완전탐색: (일치 수, 총 IoU) 사전식 최대. 작은 쪽을 순회하며 큰 쪽의 서로 다른 원소 또는 미할당에 배정."""
    if not pred or not gt:
        return 0
    small, big, flip = (pred, gt, False) if len(pred) <= len(gt) else (gt, pred, True)
    w = [[(iou(s, b)) for b in big] for s in small]
    best = [(0, 0.0)]

    def rec(i, used, cnt, tot):
        if i == len(small):
            if (cnt, tot) > best[0]:
                best[0] = (cnt, tot)
            return
        rec(i + 1, used, cnt, tot)  # 미할당
        for j in range(len(big)):
            if j not in used and w[i][j] >= thr:
                rec(i + 1, used | {j}, cnt + 1, tot + w[i][j])
    rec(0, frozenset(), 0, 0.0)
    return best[0][0]


def f1(pred, gt, thr):
    tp = best_matching(pred, gt, thr)
    p = tp / len(pred) if pred else 0.0
    r = tp / len(gt) if gt else 0.0
    return 2 * p * r / (p + r) if p + r > 0 else 0.0, len(pred) - tp, r


def own_parse_list(text):
    """전체 문자열(<end_of_turn> 제거 후)이 JSON list이고 각 원소가 box_2d(4개 수)를 갖는 경우만 인정. 그 외 None."""
    t = text.strip()
    if t.endswith("<end_of_turn>"):
        t = t[: -len("<end_of_turn>")].strip()
    try:
        v = json.loads(t)
    except Exception:
        return None
    if not isinstance(v, list):
        return None
    out = []
    for it in v:
        if not isinstance(it, dict) or "box_2d" not in it:
            return None
        b = it["box_2d"]
        if not (isinstance(b, list) and len(b) == 4 and all(isinstance(x, (int, float)) for x in b)):
            return None
        out.append([float(x) for x in b])
    return out


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
    ents = {e["PatientID"]: e for e in man["V96"]}
    pids = sorted(ents)
    sel = json.load(open("results/iter_045/decisions/D24_select.json"))
    res = {"mismatches": [], "systems": {}}

    # ---- C ----
    import glob
    crecs = {}
    for f in glob.glob("results/iter_040/gen/C/gen_worker*.jsonl"):
        for l in open(f):
            r = json.loads(l)
            crecs[(r["patient"], r["targets"][0])] = r
    own = {}
    n_unparsed = 0
    for (p, t), r in crecs.items():
        e = ents[p]
        top, left, side = (r["pad_affine_top_left_side"][0], r["pad_affine_top_left_side"][1], r["pad_affine_top_left_side"][2])
        boxes = own_parse_list(r["suffix_text_raw"]) if r["ended_eos"] else None
        if boxes is None:
            n_unparsed += 1
            boxes = []
        orig = []
        for y0, x0, y1, x1 in boxes:
            X0, Y0, X1, Y1 = x0 * side / 1000 - left, y0 * side / 1000 - top, x1 * side / 1000 - left, y1 * side / 1000 - top
            orig.append([X0 / e["w"], Y0 / e["h"], X1 / e["w"], Y1 / e["h"]])
        gt = e["gt_boxes_xyxy_norm"][t]
        a3, fp3, rec3 = f1(orig, gt, 0.3)
        a5, _, _ = f1(orig, gt, 0.5)
        own[(p, t)] = {"f1_03": a3, "f1_05": a5, "fp_03": fp3, "empty": len(orig) == 0}
    res["C_own_unparsed_or_noneos"] = n_unparsed
    # ---- MG ----
    def mg_own(ck, thr):
        recs, _, _ = E.verify_mg_dir({"P": "results/iter_045/mg/V96_P_w2b4", "MS": "results/iter_045/mg/V96_MS_w2b4"}[ck], "V96", ck, man)
        out, pass_bad = {}, 0
        for (p, t), r in recs.items():
            lg = np.array(r["logits"], dtype=np.float64)
            ex = np.exp(lg - lg.max(axis=-1, keepdims=True))
            prob0 = (ex / ex.sum(axis=-1, keepdims=True))[:, 0]
            n_pass = int((prob0 > thr).sum())
            pass_bad += int(n_pass != r["detections"][str(thr)]["pre_wbf_n"])
            boxes = r["detections"][str(thr)]["boxes_orig_xyxy"]
            gt = ents[p]["gt_boxes_xyxy_norm"][t]
            a3, fp3, _ = f1(boxes, gt, 0.3)
            a5, _, _ = f1(boxes, gt, 0.5)
            out[(p, t)] = {"f1_03": a3, "f1_05": a5, "fp_03": fp3, "empty": len(boxes) == 0}
        return out, pass_bad
    P_thr, MS_thr = sel["ckpts"]["P"]["selected_threshold"], sel["ckpts"]["MS"]["selected_threshold"]
    systems = {"C": (own, 0)}
    systems["MG-P@sel"] = mg_own("P", P_thr)
    systems["MG-MS@sel"] = mg_own("MS", MS_thr)
    systems["MG-P@0.8"] = mg_own("P", 0.8)
    systems["MG-MS@0.8"] = mg_own("MS", 0.8)
    for name, (sc, pass_bad) in systems.items():
        rp = per[name]
        md = {"f1_03": 0.0, "f1_05": 0.0, "fp_03": 0.0}
        for (p, t), v in sc.items():
            q = rp[f"{p}|{t}"]
            for k in md:
                md[k] = max(md[k], abs(v[k] - q[k]))
        mean03 = float(np.mean([np.mean([sc[(p, t)]["f1_03"] for t in ("qA", "qB")]) for p in pids]))
        mean05 = float(np.mean([np.mean([sc[(p, t)]["f1_05"] for t in ("qA", "qB")]) for p in pids]))
        fpm = float(np.mean([np.mean([sc[(p, t)]["fp_03"] for t in ("qA", "qB")]) for p in pids]))
        ok = md["f1_03"] < 1e-9 and md["f1_05"] < 1e-9 and md["fp_03"] < 1e-9 and pass_bad == 0 \
            and abs(mean03 - rep["primary_V96"][name]["f1_03"]) < 1e-9 and abs(mean05 - rep["primary_V96"][name]["f1_05"]) < 1e-9 \
            and abs(fpm - rep["primary_V96"][name]["fp_per_sentence"]) < 1e-9
        ok = bool(ok)
        res["systems"][name] = {"own_f1_03": mean03, "own_f1_05": mean05, "own_fp_per_sentence": fpm, "max_abs_item_diff_vs_report": md,
                                "threshold_pass_count_mismatch": pass_bad, "ok": bool(ok)}
        if not ok:
            res["mismatches"].append(name)
    # C 저장값 재현
    res["C_matches_stored_iter040"] = bool(abs(res["systems"]["C"]["own_f1_03"] - 0.5779513888888889) < 1e-9 and abs(res["systems"]["C"]["own_f1_05"] - 0.2911458333333333) < 1e-9)
    if not res["C_matches_stored_iter040"]:
        res["mismatches"].append("C_stored")
    # 독립 paired bootstrap (C - MG-selected)
    sn = f"MG-{sel['selected']['ckpt']}@sel"
    d = np.array([np.mean([own[(p, t)]["f1_03"] - systems[sn][0][(p, t)]["f1_03"] for t in ("qA", "qB")]) for p in pids])
    idx = np.random.default_rng(4401).integers(0, len(pids), size=(10000, len(pids)), dtype=np.int32)
    m = d[idx].mean(axis=1)
    lo, hi = float(np.percentile(m, 1.25)), float(np.percentile(m, 98.75))
    rc = rep["compare_paired_ci975"][f"C_minus_{sn}"]["f1_03"]
    res["bootstrap_C_minus_sel_f1_03"] = {"own": [float(d.mean()), lo, hi], "report": [rc["mean"], rc["lo"], rc["hi"]],
                                          "ok": bool(abs(lo - rc["lo"]) < 1e-9 and abs(hi - rc["hi"]) < 1e-9 and abs(d.mean() - rc["mean"]) < 1e-9)}
    if not res["bootstrap_C_minus_sel_f1_03"]["ok"]:
        res["mismatches"].append("bootstrap")
    res["PASS"] = len(res["mismatches"]) == 0
    json.dump(res, open(a.out, "x"), indent=1)
    print(json.dumps({"PASS": res["PASS"], "mismatches": res["mismatches"], "systems": {k: v["ok"] for k, v in res["systems"].items()},
                      "C_unparsed": n_unparsed, "bootstrap_ok": res["bootstrap_C_minus_sel_f1_03"]["ok"]}))
    sys.exit(0 if res["PASS"] else 1)


if __name__ == "__main__":
    main()
