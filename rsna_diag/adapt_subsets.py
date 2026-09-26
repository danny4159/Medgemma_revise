"""iter_013: 결과를 보기 전에 고정하는 결정적 subset 추출. 사용: python -m rsna_diag.adapt_subsets --out-dir results/iter_013/subsets

- train1200 = train 2,400 중 opacity 600 (n_box{1,2,3+} x 환자 union 면적 삼분위 strata, 최대잉여법 비례 배분, strata 안은 sha256 순),
  Normal 300, NoOpacity/NotNormal 300 (sha256 순). 작은 층을 제외하지 않고 추출 수와 원분포를 기록한다. 동일 환자 중복 없음.
- v200 = validation 400 중 양성 100 (같은 strata 방식), Normal 50, NoOpacity/NotNormal 50. V400의 부분집합 (개발 subset).
- sanity16 = train1200 안에서 양성 8 (단일 box 크기 3층 각 1 + 복수 box 5), 각 음성 층 4. thr48 = train1200 밖 train에서 양성 24, 음성 12+12 (추론 처리량 비교용).
- 면적 삼분위 경계는 기존 train 전체(select/sft_eval.area_edges)의 값을 쓴다.
"""
import argparse
import hashlib
import json
import os

import numpy as np

from . import sft_eval

GT = "results/iter_010/manifests/gt_manifest.json"
SEED = "iter013-subsets-v1"


def h(i, salt=""):
    return hashlib.sha256(f"{SEED}|{salt}|{i}".encode()).hexdigest()


def allocate(sizes, total):
    """strata 크기 dict -> 합이 total인 비례 배분 (최대잉여법, 결정적). 각 strata 크기를 넘지 않는다."""
    tot = sum(sizes.values())
    raw = {k: v * total / tot for k, v in sizes.items()}
    base = {k: int(np.floor(r)) for k, r in raw.items()}
    left = total - sum(base.values())
    for k in sorted(raw, key=lambda k: (-(raw[k] - base[k]), str(k)))[:left]:
        base[k] += 1
    return base


def strata(gt, ids, edges):
    out = {}
    for i in ids:
        nb = len(gt[i]["boxes"])
        t = int(np.digitize(sft_eval.gt_area_frac(gt[i]), edges))
        out.setdefault((min(nb, 3), t), []).append(i)
    return out


def pick_pos(gt, ids, n, edges, salt):
    st = strata(gt, ids, edges)
    al = allocate({k: len(v) for k, v in st.items()}, n)
    chosen = []
    for k in sorted(st):
        chosen += sorted(st[k], key=lambda i: h(i, salt))[:al[k]]
    return sorted(chosen), {str(k): {"available": len(st[k]), "chosen": al[k]} for k in sorted(st)}


def pick_neg(ids, n, salt):
    return sorted(sorted(ids, key=lambda i: h(i, salt))[:n])


def box_area_hist(gt, ids, cuts):
    a = np.array([(b["yxyx_norm"][2] - b["yxyx_norm"][0]) * (b["yxyx_norm"][3] - b["yxyx_norm"][1]) / 1e6 for i in ids for b in gt[i]["boxes"]])
    return {"n_boxes": int(len(a)), "share_below_cut1": float((a < cuts[0]).mean()), "share_below_cut2": float((a < cuts[1]).mean())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    gt = json.load(open(GT))
    ids = lambda s: sorted(json.load(open(f"results/iter_010/manifests/{s}_ids.json")))
    tr, va = ids("train"), ids("validation")
    edges = sft_eval.area_edges(gt, tr)
    cat = lambda pool, c: [i for i in pool if gt[i]["category"] == c]
    tr_pos_pool = cat(tr, "opacity")
    tp, tp_rep = pick_pos(gt, tr_pos_pool, 600, edges, "train")
    t1200 = sorted(tp + pick_neg(cat(tr, "normal"), 300, "train_normal") + pick_neg(cat(tr, "not_normal_no_opacity"), 300, "train_nn"))
    vp, vp_rep = pick_pos(gt, cat(va, "opacity"), 100, edges, "val")
    v200 = sorted(vp + pick_neg(cat(va, "normal"), 50, "val_normal") + pick_neg(cat(va, "not_normal_no_opacity"), 50, "val_nn"))
    # sanity16: 단일 box 크기 3층 각 1 + 복수 box 5 + 음성 4+4
    s1 = strata(gt, [i for i in t1200 if gt[i]["category"] == "opacity"], edges)
    san = []
    for t in range(3):
        san.append(sorted(s1[(1, t)], key=lambda i: h(i, "san"))[0])
    multi = [i for k in sorted(s1) if k[0] >= 2 for i in s1[k]]
    san += sorted(multi, key=lambda i: h(i, "san"))[:5]
    san += sorted([i for i in t1200 if gt[i]["category"] == "normal"], key=lambda i: h(i, "san"))[:4]
    san += sorted([i for i in t1200 if gt[i]["category"] == "not_normal_no_opacity"], key=lambda i: h(i, "san"))[:4]
    rest = [i for i in tr if i not in set(t1200)]
    tp48, _ = pick_pos(gt, cat(rest, "opacity"), 24, edges, "thr48")
    thr48 = sorted(tp48 + pick_neg(cat(rest, "normal"), 12, "thr48n") + pick_neg(cat(rest, "not_normal_no_opacity"), 12, "thr48nn"))
    os.makedirs(a.out_dir, exist_ok=True)
    cuts = [0.02, 0.06]  # 개별 box 면적 참고 경계 (보고용 분포 비교 전용, 추출에는 쓰이지 않음)
    hv = lambda c: sorted([i for i in v200 if gt[i]["category"] == c], key=lambda i: h(i, "val8"))
    val8 = sorted(hv("opacity")[:4] + hv("normal")[:2] + hv("not_normal_no_opacity")[:2])  # 재개 검사용 validation 8명 (v200의 부분집합)
    outs = {"train1200": t1200, "v200": v200, "sanity16": sorted(san), "thr48": thr48, "val8": val8}
    for k, v in outs.items():
        assert len(set(v)) == len(v)
        p = os.path.join(a.out_dir, f"{k}_ids.json")
        json.dump(v, open(p, "w"))
    assert not set(t1200) & set(v200) and set(v200) <= set(va) and set(t1200) <= set(tr) and not set(thr48) & set(t1200)
    assert set(outs["sanity16"]) <= set(t1200) and len(outs["sanity16"]) == 16
    rep = {"seed": SEED, "area_tertile_edges_train": edges,
           "sizes": {k: len(v) for k, v in outs.items()},
           "categories": {k: {c: sum(gt[i]["category"] == c for i in v) for c in ("opacity", "normal", "not_normal_no_opacity")} for k, v in outs.items()},
           "train_pos_strata": tp_rep, "val_pos_strata": vp_rep,
           "box_area_shares_full_train_pos": box_area_hist(gt, tr_pos_pool, cuts), "box_area_shares_train1200_pos": box_area_hist(gt, tp, cuts),
           "n_box_dist_full_train_pos": {str(k): int(v) for k, v in zip(*np.unique([len(gt[i]["boxes"]) for i in tr_pos_pool], return_counts=True))},
           "n_box_dist_train1200_pos": {str(k): int(v) for k, v in zip(*np.unique([len(gt[i]["boxes"]) for i in tp], return_counts=True))},
           "sha256": {k: hashlib.sha256(open(os.path.join(a.out_dir, f"{k}_ids.json"), "rb").read()).hexdigest() for k in outs}}
    json.dump(rep, open(os.path.join(a.out_dir, "subsets_report.json"), "w"), indent=1)
    print(json.dumps({k: rep[k] for k in ("sizes", "categories", "n_box_dist_full_train_pos", "n_box_dist_train1200_pos", "box_area_shares_full_train_pos", "box_area_shares_train1200_pos")}, indent=1))


if __name__ == "__main__":
    main()
