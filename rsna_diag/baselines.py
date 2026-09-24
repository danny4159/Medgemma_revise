"""영상 비의존/고정 보정 baseline (iter_010).

1. coord_correction: iter_009의 기존 개발 자료(dev80+eval300=380명)의 실제 생성 출력에서 prompt별로 800개 고정 후보 변환 중
   양성 end-to-end F1@0.3 최대인 것을 선택한다 (동률: identity에 가까운 변환). 새 split은 선택에 쓰지 않는다.
   변환 순서: (선택) y/x 축 교환 -> 높이·너비 배율(중심 유지) -> 중심 이동(dy,dx) -> [0,1000] canvas 교집합. 면적 0이 되면 box 소멸(기록).
2. box 집합 prior: train 양성의 실제 GT box 집합 중 train 양성 평균 F1@0.3 최대 하나 (단일 box prior 함께). 확인 환자는 선택에 쓰지 않는다.
사용: python -m rsna_diag.baselines --out results/iter_010/baselines
"""
import argparse
import glob
import itertools
import json
import multiprocessing as mp
import os

import numpy as np

from . import metrics as M, parse as PA, sft_eval

IT9 = "results/iter_009"
SHIFTS = [-150, -75, 0, 75, 150]
SCALES = [0.4, 0.6, 0.8, 1.0]
PROMPTS = ["official_long", "concise"]
CANDIDATES = [(sw, dy, dx, sh, sc_w) for sw in (0, 1) for dy in SHIFTS for dx in SHIFTS for sh in SCALES for sc_w in SCALES]
assert len(CANDIDATES) == 800
_G = {}


def apply_box(b, spec):
    sw, dy, dx, sh, scw = spec
    y0, x0, y1, x1 = b
    if sw:
        y0, x0, y1, x1 = x0, y0, x1, y1
    cy, cx = (y0 + y1) / 2 + dy, (x0 + x1) / 2 + dx
    h, w = (y1 - y0) * sh, (x1 - x0) * scw
    ny0, ny1, nx0, nx1 = max(0.0, cy - h / 2), min(1000.0, cy + h / 2), max(0.0, cx - w / 2), min(1000.0, cx + w / 2)
    if ny1 - ny0 <= 0 or nx1 - nx0 <= 0:
        return None
    return [ny0, nx0, ny1, nx1]


def apply_pred(pred, spec):
    """valid 출력의 모든 box에 같은 변환. 실패 출력은 그대로(구제하지 않음). returns (new pred, n_vanished)."""
    if pred["status"] not in PA.VALID:
        return pred, 0
    nb = [apply_box(b, spec) for b in pred["boxes"]]
    kept = [b for b in nb if b is not None]
    st = "valid_nonempty" if kept else "valid_empty"
    return {"status": st, "boxes": kept}, len(nb) - len(kept)


def identity_distance(spec):
    sw, dy, dx, sh, scw = spec
    return (sw, abs(dy) + abs(dx), abs(1 - sh) + abs(1 - scw), spec)


def load_iter9_records(ids, prompts=PROMPTS):
    """iter_009의 pilot/dev/eval 생성 record를 (id,prompt)로 모은다. 중복은 suffix가 동일할 때만 허용한다."""
    recs = {}
    for f in sorted(glob.glob(f"{IT9}/*/run/gen_shard*.jsonl")):
        if f.endswith((".env.json", ".log")):
            continue
        for ln in open(f):
            if not ln.strip():
                continue
            r = json.loads(ln)
            if r["id"] not in ids or r["prompt_name"] not in prompts:
                continue
            k = (r["id"], r["prompt_name"])
            if k in recs:
                if recs[k]["suffix_ids"] != r["suffix_ids"] or recs[k]["input_ids_sha256"] != r["input_ids_sha256"]:
                    raise ValueError(f"conflicting duplicate {k}")
                continue
            recs[k] = r
    return recs


def _f1_for_spec(args):
    spec, items = args
    tot = 0.0
    for pred, g in items:
        p, _ = apply_pred(pred, spec)
        tot += M.patient_metrics(p["boxes"] if p["status"] in PA.VALID else [], g, 0.3)["f1"]
    return tot / len(items)


def select_correction(preds_pos, gts_pos, pool):
    items = list(zip(preds_pos, gts_pos))
    scores = pool.map(_f1_for_spec, [(s, items) for s in CANDIDATES], chunksize=20)
    best = max(scores)
    tied = [c for c, s in zip(CANDIDATES, scores) if s >= best - 1e-12]
    chosen = min(tied, key=identity_distance)
    ident = CANDIDATES.index((0, 0, 0, 1.0, 1.0))
    return {"spec": list(chosen), "score": best, "identity_score": scores[ident], "n_tied": len(tied),
            "top5": sorted(([s, list(c)] for c, s in zip(CANDIDATES, scores)), key=lambda x: -x[0])[:5]}, scores


def _prior_score(args):
    cand, gts = args
    return float(np.mean([M.patient_metrics(cand, g, 0.3)["f1"] for g in gts]))


def select_prior(gts_train_pos, pool):
    # 실제 GT 집합 후보 (중복 제거, 등장 순서 고정)
    seen, sets = set(), []
    for g in gts_train_pos:
        key = json.dumps(sorted(g))
        if key not in seen:
            seen.add(key)
            sets.append(g)
    sc = pool.map(_prior_score, [(c, gts_train_pos) for c in sets], chunksize=10)
    k = int(np.argmax(sc))
    boxes = [b for g in gts_train_pos for b in g]
    sb, s2 = set(), []
    for b in boxes:
        t = tuple(b)
        if t not in sb:
            sb.add(t)
            s2.append([b])
    sc1 = pool.map(_prior_score, [(c, gts_train_pos) for c in s2], chunksize=10)
    k1 = int(np.argmax(sc1))
    return {"set": sets[k], "score": sc[k], "n_candidates": len(sets), "n_gt": len(sets[k])}, \
           {"box": s2[k1][0], "score": sc1[k1], "n_candidates": len(s2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--gt", default="results/iter_010/manifests/gt_manifest.json")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    gt9 = json.load(open(f"{IT9}/manifests/gt_manifest.json"))
    ids9 = sorted(gt9)
    assert len(ids9) == 380
    recs = load_iter9_records(set(ids9))
    miss = [(i, p) for i in ids9 for p in PROMPTS if (i, p) not in recs]
    if miss:
        raise RuntimeError(f"iter_009 records missing: {len(miss)} e.g. {miss[:3]}")
    pos9 = [i for i in ids9 if gt9[i]["category"] == "opacity"]
    gts9 = [[b["yxyx_norm"] for b in gt9[i]["boxes"]] for i in pos9]
    pool = mp.Pool(min(16, os.cpu_count() or 4))
    out = {"n_dev_patients": len(ids9), "n_dev_positive": len(pos9), "candidates": len(CANDIDATES),
           "transform_order": "swap -> scale about center -> shift -> clip to [0,1000]"}
    for p in PROMPTS:
        parsed = sft_eval.parse_records(recs, pos9, p)
        sel, scores = select_correction([parsed[i] for i in pos9], gts9, pool)
        # 선택 변환의 소멸 box 수 (개발 양성)
        van = sum(apply_pred(parsed[i], tuple(sel["spec"]))[1] for i in pos9)
        sel["n_vanished_boxes_dev_positive"] = van
        sel["spec_fields"] = ["swap_axes", "dy", "dx", "h_scale", "w_scale"]
        out[p] = sel
        print(p, sel["spec"], round(sel["score"], 4), "identity", round(sel["identity_score"], 4), flush=True)
    gt = json.load(open(a.gt))
    train_pos = sorted(i for i in gt if gt[i]["split"] == "train" and gt[i]["category"] == "opacity")
    g_tr = [[b["yxyx_norm"] for b in gt[i]["boxes"]] for i in train_pos]
    pset, pbox = select_prior(g_tr, pool)
    out["prior_set"], out["prior_single_box"] = pset, pbox
    out["prior_selection"] = {"split": "train", "n_positive": len(train_pos)}
    json.dump(out, open(f"{a.out}/baselines.json", "w"), indent=1)
    print("prior set", pset["set"], round(pset["score"], 4), "single", pbox["box"], round(pbox["score"], 4))


if __name__ == "__main__":
    main()
