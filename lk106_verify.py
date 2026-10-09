"""iter_106 독립 재계산: lk106_spec/lk106_eval을 import하지 않고 원시 outputs.jsonl + inputs에서 좌표 추출·matching·recall·bootstrap을 다시 구현한다.
사용: python lk106_verify.py --stage E32 --gen DIR --nshards N [--ind-gen DIR --ind-shards N] --report REPORT.json --out FILE
(완전성·provenance는 lk106_run.verify_completion 몫이며 여기서는 수치만 대조한다. 요청 중복/누락은 직접 검사한다.)
"""
import argparse
import itertools
import json
import math
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "results/iter_105/data"


def read_jsonl(p):
    out = []
    for ln in Path(p).read_bytes().split(b"\n")[:-1]:
        if ln.strip():
            out.append(json.loads(ln))
    return out


def extract_boxes(text, ended):
    """별도 구현: '[' 로 쪼개 ']' 앞의 쉼표 구분 숫자 4개를 읽는다."""
    if not ended:
        return "truncated", []
    boxes = []
    for chunk in text.split("[")[1:]:
        if "]" not in chunk:
            continue
        inner = chunk.split("]")[0]
        parts = [p.strip() for p in inner.split(",")]
        if len(parts) != 4:
            continue
        try:
            if not all(re.fullmatch(r"-?\d+(\.\d+)?", p) for p in parts):
                continue
            c = [float(p) for p in parts]
        except ValueError:
            continue
        if not all(math.isfinite(v) for v in c) or c[2] <= 0 or c[3] <= 0 or min(c) < 0 or max(c) > 1:
            return "coord_invalid", []
        boxes.append((c[0] - c[2] / 2, c[1] - c[3] / 2, c[0] + c[2] / 2, c[1] + c[3] / 2))
    return ("valid_nonempty" if boxes else "no_box"), boxes


def iou(a, b):
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    i = w * h
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u > 0 else 0.0


def max_match(gts, preds, thr=0.3):
    """brute force: 각 GT에 서로 다른 예측 또는 미할당을 permutations로 열거."""
    best = 0
    opts = list(range(len(preds))) + [None] * len(gts)
    for assign in set(itertools.permutations(opts, len(gts))) if len(preds) + len(gts) <= 9 else []:
        n = sum(1 for g, p in zip(gts, assign) if p is not None and iou(g, preds[p]) >= thr)
        best = max(best, n)
    return best


def max_match_big(gts, preds, thr=0.3):
    # 예측이 많을 때: 2 GT 전용 직접 열거
    n = len(gts)
    assert n <= 2
    if n == 1:
        return int(any(iou(gts[0], p) >= thr for p in preds))
    a = [j for j, p in enumerate(preds) if iou(gts[0], p) >= thr]
    b = [j for j, p in enumerate(preds) if iou(gts[1], p) >= thr]
    if not a or not b:
        return int(bool(a) or bool(b))
    return 2 if any(x != y for x in a for y in b) else 1


def mm(gts, preds):
    return max_match_big(gts, preds)


def boot(vals, seed, n=10000):
    v = np.asarray(vals, float)
    idx = np.random.default_rng(seed).integers(0, len(v), size=(n, len(v)))
    m = v[idx].mean(axis=1)
    return float(v.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def gather(gen, nshards):
    recs = {}
    for k in range(nshards):
        for r in read_jsonl(Path(gen) / "cure" / f"shard{k}" / "outputs.jsonl"):
            assert r["id"] not in recs, "dup"
            recs[r["id"]] = r
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--gen", required=True)
    ap.add_argument("--nshards", type=int, required=True)
    ap.add_argument("--ind-gen")
    ap.add_argument("--ind-shards", type=int)
    ap.add_argument("--report", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = json.loads((DATA / f"inputs_{a.stage}.json").read_text())
    new = gather(a.gen, a.nshards)
    if a.ind_gen:
        ind = {}
        for k, r in gather(a.ind_gen, a.ind_shards).items():
            if r["kind"] == "pg":
                ind[k.replace("|pg-S1", "|I1").replace("|pg-S2", "|I2")] = r
    else:
        ind = new
    rep = json.loads(Path(a.report).read_text())["summary"]
    per = []
    for r in rows:
        iid = r["ImageID"]
        g = lambda c: (ind if c in ("I1", "I2") else new)[f"{iid}|CURE|{c}"]
        bx = {}
        for c in ("I1", "I2", "J12", "J21", "R11", "R22"):
            rec = g(c)
            exp_prompt = {"I1": r["S1"], "I2": r["S2"], "J12": r["S1"] + " " + r["S2"], "J21": r["S2"] + " " + r["S1"], "R11": r["S1"] + " " + r["S1"],
                          "R22": r["S2"] + " " + r["S2"]}[c]
            assert rec["prompt"] == "Ground the phrase: " + exp_prompt, "prompt mismatch"
            bx[c] = extract_boxes(rec["text"], rec["attempts"][-1]["ended_eos"])
        gt = [tuple(r["box1"]), tuple(r["box2"])]
        rI = mm(gt, bx["I1"][1] + bx["I2"][1])
        r12 = mm(gt, bx["J12"][1])
        r21 = mm(gt, bx["J21"][1])
        s = {"I1": mm([gt[0]], bx["I1"][1]), "R11": mm([gt[0]], bx["R11"][1]), "I2": mm([gt[1]], bx["I2"][1]), "R22": mm([gt[1]], bx["R22"][1])}
        per.append({"I": rI / 2, "J12": r12 / 2, "J21": r21 / 2, "rep": ((s["I1"] - s["R11"]) + (s["I2"] - s["R22"])) / 2,
                    "st": {c: bx[c][0] for c in bx}})
    chk = {}
    def close(x, y):
        return bool(abs(x - y) < 1e-12)
    chk["recall_I"] = close(np.mean([p["I"] for p in per]), rep["recall_I"]["mean"])
    chk["recall_J12"] = close(np.mean([p["J12"] for p in per]), rep["recall_J12"]["mean"])
    chk["recall_J21"] = close(np.mean([p["J21"] for p in per]), rep["recall_J21"]["mean"])
    d12 = boot([p["I"] - p["J12"] for p in per], 106017 + 1)
    d21 = boot([p["I"] - p["J21"] for p in per], 106017 + 2)
    dm = boot([p["I"] - (p["J12"] + p["J21"]) / 2 for p in per], 106017 + 3)
    rd = boot([p["rep"] for p in per], 106017 + 4)
    for name, got, key in (("d12", d12, "diff_I_minus_J12"), ("d21", d21, "diff_I_minus_J21"), ("dmean", dm, "diff_I_minus_Jmean"),
                           ("rep", rd, "repetition_drop_I_minus_R")):
        e = rep[key]
        chk[name] = bool(close(got[0], e["mean"]) and close(got[1], e["ci95"][0]) and close(got[2], e["ci95"][1]))
    from collections import Counter
    for c in ("I1", "I2", "J12", "J21", "R11", "R22"):
        chk[f"status_{c}"] = dict(Counter(p["st"][c] for p in per)) == rep["status_counts"][c]
    res = {"stage": a.stage, "n": len(per), "all_pass": bool(all(chk.values())), "checks": chk,
           "values": {"d12": d12, "d21": d21, "dmean": dm, "rep": rd}}
    p = Path(a.out)
    if p.exists():
        raise SystemExit("output exists")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))
    return 0 if res["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
