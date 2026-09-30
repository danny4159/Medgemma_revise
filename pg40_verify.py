"""iter_040 독립 재계산 (pg39_spec/pg39_eval/rsna_diag.parse·metrics를 쓰지 않는 별도 구현).
원시 생성 record(gen_worker*.jsonl)의 suffix_text_raw에서 strict JSON 목록을 직접 해석하고, 정규화 GT는 원본 normalized xyxy와 영상 크기에서 다시 계산한다.
문장별 최대 cardinality one-to-one matching은 증강 경로(augmenting path) 알고리즘으로 계산한다 (F1은 cardinality에만 의존).
대상: 순수 JSON 목록으로 출력하는 학습 모델(B/C/M/C_compute). M0의 복잡한 출력 형식은 iter_039 검증 범위를 따른다.

python pg40_verify.py --subset V96 --model M=results/iter_040/gen/M --model C=... --report results/iter_040/eval/v96_MC.json --out results/iter_040/eval/verify_v96_MC.json
"""
import argparse
import glob
import json
import os
import re
import sys

import numpy as np

EVAL_MANIFEST = "results/iter_040/data/manifest_eval_private.jsonl"
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
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u


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
    """returns (valid, {id: [boxes]}, n_fp_ignored). 순수 JSON 목록만 인정 (그 밖은 invalid=점수 0)."""
    t = raw[:-len(EOT)] if raw.endswith(EOT) else raw
    if not ended:
        return False, {}, 0
    try:
        arr = json.loads(t.strip())
    except Exception:
        return False, {}, 0
    if not isinstance(arr, list):
        return False, {}, 0
    out = {"qA": [], "qB": []}
    for e in arr:
        if not isinstance(e, dict) or set(e) != {"box_2d", "label"}:
            return False, {}, 0
        b, lab = e["box_2d"], e["label"]
        if not (isinstance(b, list) and len(b) == 4 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in b) and isinstance(lab, str)):
            return False, {}, 0
        if not (0 <= b[0] < b[2] <= 1000 and 0 <= b[1] < b[3] <= 1000):
            return False, {}, 0
        m = re.fullmatch(r"\s*q([abAB])\s*", lab)
        if not m:
            return False, {}, 0
        pid = "q" + m.group(1).upper()
        if pid in allowed:
            out[pid].append([float(v) for v in b])
    return True, out, 0


def load_man(subset):
    out = {}
    for l in open(EVAL_MANIFEST):
        r = json.loads(l)
        if subset == "V96" and r["eval_set"] == "V96" or subset == "V48" and r["eval_set"] == "V96" and r["is_V48"] or subset == "H192" and r["eval_set"] == "H192":
            out[r["PatientID"]] = r
    return out


def patient_f1(gen_dir, man, thr):
    recs = []
    for fn in sorted(glob.glob(os.path.join(gen_dir, "gen_worker*.jsonl"))):
        for ln in open(fn):
            if ln.strip():
                recs.append(json.loads(ln))
    by = {}
    for r in recs:
        if r["patient"] not in man:
            continue
        m = man[r["patient"]]
        h, w = m["image_meta"]["h"], m["image_meta"]["w"]
        t = r["targets"][0]
        gt = [canvas(b, h, w) for b in m["gt_boxes_xyxy_norm"][t]]
        ok, groups, _ = parse(r["suffix_text_raw"], r["ended_eos"], set(r["targets"]))
        pred = groups.get(t, []) if ok else []
        by.setdefault(r["patient"], {})[t] = (f1(pred, gt, thr), ok, len(pred), len(gt))
    assert all(set(v) == {"qA", "qB"} for v in by.values()) and set(by) == set(man), "coverage"
    return by


def boot(vals, level, B=10000, seed=20260930):
    idx = np.random.default_rng(seed).integers(0, len(vals), size=(B, len(vals)), dtype=np.int32)
    m = vals[idx].mean(axis=1)
    a = (1 - level) / 2 * 100
    return [float(vals.mean()), float(np.percentile(m, a)), float(np.percentile(m, 100 - a))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subset", required=True)
    ap.add_argument("--model", action="append", required=True, help="NAME=gen_dir")
    ap.add_argument("--report", required=True)
    ap.add_argument("--pairs", nargs="*", default=[])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("output exists")
    man = load_man(a.subset)
    pids = sorted(man)
    rep = json.load(open(a.report))
    res = {"models": {}, "pairs": {}, "compare_with_report": {}}
    vec3, vec5 = {}, {}
    for m in a.model:
        n, g = m.split("=", 1)
        b3, b5 = patient_f1(g, man, 0.3), patient_f1(g, man, 0.5)
        vec3[n] = np.array([np.mean([b3[p][t][0] for t in ("qA", "qB")]) for p in pids])
        vec5[n] = np.array([np.mean([b5[p][t][0] for t in ("qA", "qB")]) for p in pids])
        inval = sum(not b3[p][t][1] for p in pids for t in ("qA", "qB"))
        fp = float(np.mean([b3[p][t][2] - 0 for p in pids for t in ("qA", "qB")]))
        res["models"][n] = {"f1_03_ci95": boot(vec3[n], 0.95), "f1_05_mean": float(vec5[n].mean()), "n_invalid_sentences": inval}
        rp = rep["models"][n]["summary"]
        res["compare_with_report"][n] = {"f1_03_abs_diff": abs(res["models"][n]["f1_03_ci95"][0] - rp["f1_03"][0]),
                                         "f1_03_ci_abs_diff": max(abs(x - y) for x, y in zip(res["models"][n]["f1_03_ci95"], rp["f1_03"])),
                                         "f1_05_abs_diff": abs(res["models"][n]["f1_05_mean"] - rp["f1_05"][0]),
                                         "invalid_count_vs_report": [inval, round(rp["invalid_rate"] * 2 * len(pids))]}
    for pr in a.pairs:
        x, y = pr.split(":")
        d = vec3[x] - vec3[y]
        res["pairs"][pr] = {"f1_03_diff_ci975": boot(d, 0.975), "f1_03_diff_ci95": boot(d, 0.95), "f1_05_diff": float((vec5[x] - vec5[y]).mean())}
        rp = rep["pairs"][pr]["f1_03"]
        res["compare_with_report"][pr] = {"diff_abs": abs(res["pairs"][pr]["f1_03_diff_ci975"][0] - rp["diff_mean_ci975"][0]),
                                          "ci975_abs_diff": max(abs(u - v) for u, v in zip(res["pairs"][pr]["f1_03_diff_ci975"], rp["diff_mean_ci975"])),
                                          "ci95_abs_diff": max(abs(u - v) for u, v in zip(res["pairs"][pr]["f1_03_diff_ci95"], rp["diff_mean_ci95"]))}
    mx = max(v for c in res["compare_with_report"].values() for k, v in c.items() if isinstance(v, float))
    res["max_abs_diff_vs_report"] = mx
    res["all_match_1e-9"] = bool(mx < 1e-9 and all(c["invalid_count_vs_report"][0] == c["invalid_count_vs_report"][1]
                                                    for c in res["compare_with_report"].values() if "invalid_count_vs_report" in c))
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(res, open(a.out, "w"), indent=1)
    print(json.dumps(res, indent=1)[:2500])


if __name__ == "__main__":
    main()
