"""iter_041 독립 재계산: pg39_spec/pg39_eval/rsna_diag.parse·metrics를 쓰지 않는 별도 구현.
원시 record의 suffix_text_raw에서 순수 JSON 목록을 직접 해석(공동 출력은 label qA/qB로 그룹 분리; 문장에 붙은 ID는 순서 반전과 무관),
GT는 원본 normalized xyxy + 영상 크기에서 다시 canvas 좌표로 변환, 문장별 matching은 augmenting path 알고리즘. 환자별 점수를 report의 저장값과 대조.
질의 형식이 순수 JSON이 아닌 응답은 invalid(점수 0)로 처리하며, report의 파이프라인 판정과 다른 record 수를 함께 보고한다.

python pg41_verify.py --report results/iter_041/eval/report_V96.json --out results/iter_041/eval/verify_V96.json
"""
import argparse
import glob
import json
import os
import re
import sys

import numpy as np

EOT = "<end_of_turn>"


def canvas(box, h, w):
    side = max(h, w)
    top = (side - h) // 2 if h < w else 0
    left = (side - w) // 2 if w < h else 0
    x0, y0, x1, y1 = box[0] * w, box[1] * h, box[2] * w, box[3] * h
    return [(y0 + top) * 1000 / side, (x0 + left) * 1000 / side, (y1 + top) * 1000 / side, (x1 + left) * 1000 / side]


def iou(a, b):
    ih = min(a[2], b[2]) - max(a[0], b[0])
    iw = min(a[3], b[3]) - max(a[1], b[1])
    if ih <= 0 or iw <= 0:
        return 0.0
    i = ih * iw
    return i / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i)


def max_matching(pred, gt, thr):
    adj = [[j for j, p in enumerate(pred) if iou(g, p) >= thr] for g in gt]
    owner = {}

    def aug(u, seen):
        for v in adj[u]:
            if v in seen:
                continue
            seen.add(v)
            if v not in owner or aug(owner[v], seen):
                owner[v] = u
                return True
        return False
    return sum(aug(u, set()) for u in range(len(gt)))


def f1(pred, gt, thr):
    tp = max_matching(pred, gt, thr) if pred and gt else 0
    if tp == 0:
        return 0.0
    p, r = tp / len(pred), tp / len(gt)
    return 2 * p * r / (p + r)


def parse(raw, ended, allowed):
    t = raw[:-len(EOT)] if raw.endswith(EOT) else raw
    if not ended:
        return False, {}
    try:
        arr = json.loads(t.strip())
    except Exception:
        return False, {}
    if not isinstance(arr, list):
        return False, {}
    out = {"qA": [], "qB": []}
    for e in arr:
        if not isinstance(e, dict) or set(e) != {"box_2d", "label"}:
            return False, {}
        b, lab = e["box_2d"], e["label"]
        if not (isinstance(b, list) and len(b) == 4 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in b) and isinstance(lab, str)):
            return False, {}
        if not (0 <= b[0] < b[2] <= 1000 and 0 <= b[1] < b[3] <= 1000):
            return False, {}
        m = re.fullmatch(r"\s*q([abAB])\s*", lab)
        if not m:
            return False, {}
        pid = "q" + m.group(1).upper()
        if pid in allowed:
            out[pid].append([float(v) for v in b])
    return True, out


def read_dir(d):
    recs = []
    for fn in sorted(glob.glob(os.path.join(d, "gen_worker*.jsonl"))):
        for ln in open(fn):
            if ln.strip():
                recs.append(json.loads(ln))
    return recs


def per_patient(recs, man, thr):
    """{patient: {cond_key: F1 (문장 평균)}} cond_key: I (두 요청), AB, BA."""
    acc = {}
    inval = {}
    for r in recs:
        m = man[r["patient"]]
        h, w = m["image_meta"]["h"], m["image_meta"]["w"]
        ok, g = parse(r["suffix_text_raw"], r["ended_eos"], set(r["targets"]))
        key = "I" if len(r["targets"]) == 1 else ("AB" if r["cond"] == "J-short" else "BA")
        vals = []
        for t in r["targets"]:
            gt = [canvas(b, h, w) for b in m["gt_boxes_xyxy_norm"][t]]
            vals.append(f1(g.get(t, []) if ok else [], gt, thr))
        acc.setdefault((r["patient"], key), []).extend(vals)
        inval.setdefault(key, []).append(not ok)
    return {k: float(np.mean(v)) for k, v in acc.items()}, {k: int(sum(v)) for k, v in inval.items()}


def boot(vals, level, B=10000, seed=20260930):
    vals = np.asarray(vals, float)
    idx = np.random.default_rng(seed).integers(0, len(vals), size=(B, len(vals)), dtype=np.int32)
    m = vals[idx].mean(axis=1)
    a = (1 - level) / 2 * 100
    return [float(vals.mean()), float(np.percentile(m, a)), float(np.percentile(m, 100 - a))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("output exists")
    rep = json.load(open(a.report))
    cfg = rep["config"]
    man = {}
    for l in open(cfg["manifest"]):
        r = json.loads(l)
        if r["eval_set"] == cfg["subset"]:
            man[r["PatientID"]] = r
    pids = sorted(man)
    res = {"models": {}, "compare": {}}
    for m, srcs in cfg["models"].items():
        recs = []
        for k in ("I", "JAB", "JBA"):
            recs += read_dir(srcs[k]["gen"])
        assert len(recs) == 192 + 96 + 96, len(recs)
        pp3, inv = per_patient(recs, man, 0.3)
        pp5, _ = per_patient(recs, man, 0.5)
        X = {c: np.array([pp3[(p, c)] for p in pids]) for c in ("I", "AB", "BA")}
        X5 = {c: np.array([pp5[(p, c)] for p in pids]) for c in ("I", "AB", "BA")}
        r_ = {"f1_03_mean": {c: float(X[c].mean()) for c in X}, "f1_05_mean": {c: float(X5[c].mean()) for c in X5},
              "delta_AB_ci975": boot(X["I"] - X["AB"], 0.975), "delta_BA_ci975": boot(X["I"] - X["BA"], 0.975),
              "invalid_requests_strict_json": inv}
        res["models"][m] = r_
        rp = rep["_per_patient_f1_03"][m]
        mx = max(abs(rp[p][c] - X[c][i]) for i, p in enumerate(pids) for c in X)
        rm = rep["models"][m]
        res["compare"][m] = {"max_abs_patient_f1_diff": float(mx),
                             "mean_f1_max_abs_diff": max(abs(rm["mean_f1_03"][c][0] - X[c].mean()) for c in X),
                             "f1_05_max_abs_diff": max(abs(rm["mean_f1_05"][c][0] - X5[c].mean()) for c in X5),
                             "delta_ci975_max_abs_diff_vs_report(rng differs)": max(
                                 max(abs(u - v) for u, v in zip(r_["delta_AB_ci975"], rm["delta_I_minus_JAB"]["ci975"])),
                                 max(abs(u - v) for u, v in zip(r_["delta_BA_ci975"], rm["delta_I_minus_JBA"]["ci975"]))),
                             "invalid_pipeline_rate_vs_strict": {c: [rm["format"][c]["valid_rate"], 1 - inv[c] / rm["format"][c]["n_requests"]] for c in X}}
    res["patient_f1_match_1e-9"] = bool(all(v["max_abs_patient_f1_diff"] < 1e-9 for v in res["compare"].values()))
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(res, open(a.out, "x"), indent=1)
    print(json.dumps(res, indent=1)[:3000])


if __name__ == "__main__":
    main()
