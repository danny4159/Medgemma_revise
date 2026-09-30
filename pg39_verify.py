"""iter_039 독립 재계산: pg39_spec/pg39_eval의 parser·DP matching과 별도 구현(raw_decode + 열거 matching + 자체 IoU/bootstrap)으로
환자별 조건 점수와 주차이를 재계산해 보고서와 대조한다.
python pg39_verify.py REPORT.json OUT.json GEN_DIR [GEN_DIR...] (records는 각 GEN_DIR/gen_worker*.jsonl, manifest는 고정 경로)
"""
import glob
import itertools
import json
import os
import re
import sys

import numpy as np

report_path, out_path, *gens = sys.argv[1:]
if os.path.exists(out_path):
    sys.exit("output exists")
rep = json.load(open(report_path))
man = {}
for l in open("results/iter_039/data/manifest_private.jsonl"):
    r = json.loads(l)
    man[r["PatientID"]] = r
recs = [json.loads(l) for g in gens for f in sorted(glob.glob(g + "/gen_worker*.jsonl")) for l in open(f)]


def extract(txt, eos):
    if not eos:
        return None
    t = txt.replace("<end_of_turn>", "")
    if "<unused95>" in t:
        t = t.split("<unused95>", 1)[1]
    ms = [m.end() for m in re.finditer(r"final answer\s*:", t, re.I)]
    seg = t[ms[-1]:] if ms else t
    i = seg.find("[")
    if i < 0:
        return None
    try:
        v, _ = json.JSONDecoder().raw_decode(seg[i:])
    except Exception:
        return None
    if not isinstance(v, list):
        return None
    out = []
    for e in v:
        if not (isinstance(e, dict) and isinstance(e.get("box_2d"), list) and len(e["box_2d"]) == 4 and isinstance(e.get("label"), str)):
            return None
        b = e["box_2d"]
        if not all(isinstance(x, (int, float)) and 0 <= x <= 1000 for x in b) or not (b[0] < b[2] and b[1] < b[3]):
            return None
        m = re.fullmatch(r"\s*q([ab])\s*", e["label"], re.I)
        if not m:
            return None
        out.append(("q" + m.group(1).upper(), [float(x) for x in b]))
    return out


def iou(a, b):
    ih = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iw = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ih * iw
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u > 0 else 0.0


def f1_enum(pred, gt, thr=0.3):
    if not pred and not gt:
        return 0.0
    best = 0
    # 최대 cardinality를 모든 부분 injective 대응 열거로 구한다 (작은 집합 전용)
    for k in range(min(len(pred), len(gt)), 0, -1):
        for gs in itertools.combinations(range(len(gt)), k):
            for ps in itertools.permutations(range(len(pred)), k):
                if all(iou(pred[p], gt[g]) >= thr for g, p in zip(gs, ps)):
                    best = k
                    break
            if best:
                break
        if best:
            break
    if best == 0 or not pred or not gt:
        return 0.0
    pr, rc = best / len(pred), best / len(gt)
    return 2 * pr * rc / (pr + rc)


def gt_canvas(m, k):
    h, w = m["image_meta"]["h"], m["image_meta"]["w"]
    side = max(h, w)
    top = (side - h) // 2 if h < w else 0
    left = (side - w) // 2 if w < h else 0
    return [[(y0 * h + top) * 1000 / side, (x0 * w + left) * 1000 / side, (y1 * h + top) * 1000 / side, (x1 * w + left) * 1000 / side]
            for x0, y0, x1, y1 in m["gt_boxes_xyxy_norm"][k]]


per = {}
for r in recs:
    m = man[r["patient"]]
    ent = extract(r["suffix_text_raw"], r["ended_eos"])
    tg = r["targets"]
    sc = []
    for t in tg:
        if ent is None:
            sc.append(0.0)
            continue
        if any(l not in ("qA", "qB") for l, _ in ent):
            sc.append(0.0)
            continue
        pred = [b for l, b in ent if l == t]
        sc.append(f1_enum(pred, gt_canvas(m, t)))
    per.setdefault(r["patient"], {}).setdefault(r["cond"], []).extend(sc)
mine = {p: {c: float(np.mean(v)) for c, v in cs.items()} for p, cs in per.items()}
theirs = rep["_per_patient"]
maxdiff = max(abs(mine[p][c] - theirs[p][c]) for p in theirs for c in theirs[p])
rng = np.random.default_rng(20260930)
pids = sorted(mine)
n = len(pids)
idx = rng.integers(0, n, size=(10000, n))
res = {"n_patients": n, "max_abs_diff_per_patient_condition": maxdiff}
for name, (a, b), lv in (("delta_long", ("I-long", "J-long"), 97.5), ("delta_short", ("I-short", "J-short"), 97.5)):
    d = np.array([mine[p][a] - mine[p][b] for p in pids])
    m = d[idx].mean(axis=1)
    lo, hi = (100 - lv) / 2, 100 - (100 - lv) / 2
    res[name] = [float(d.mean()), float(np.percentile(m, lo)), float(np.percentile(m, hi))]
    res[name + "_report"] = rep["delta_long_I_minus_J" if a == "I-long" else "delta_short_I_minus_J"]["ci975"]
res["mean_I_long"] = float(np.mean([mine[p]["I-long"] for p in pids]))
res["pass_per_patient"] = maxdiff < 1e-9
res["pass_delta_point"] = all(abs(res[k][0] - res[k + "_report"][0]) < 1e-9 for k in ("delta_long", "delta_short"))
json.dump(res, open(out_path, "w"), indent=1)
print(json.dumps(res, indent=1))
