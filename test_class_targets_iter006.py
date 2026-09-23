"""iter_006: (image, class)별 target 계약과 probe metric·대조군·집계 규약 테스트 (CPU, float64).

실행: python research/test_class_targets_iter006.py --manifest research/results/iter_005/nih_manifest.json \
          --targets research/results/iter_006/nih_class_targets.npz --out research/results/iter_006/class_target_tests.json
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grounding_data import class_targets as CT  # noqa: E402
from grounding_data import targets as T  # noqa: E402

TOL = 1e-10
RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append({"test": name, "pass": bool(cond), "detail": str(detail)[:400]})
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {str(detail)[:160]}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--targets", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    A, E, C, P = CT.MAIN_CLASSES
    W = H = 1024

    # 1) 다중 클래스 영상: 떨어진 box → 각 클래스 target은 자기 box cell에만 질량
    ann = [{"label": A, "xyxy": [0, 0, 64, 64]}, {"label": E, "xyxy": [512, 512, 640, 640]},
           {"label": "Mass", "xyxy": [800, 100, 900, 200]}]
    f, c, o = CT.image_class_targets(ann, W, H)
    ea = np.zeros((64, 64))
    ea[0:4, 0:4] = 1
    ee = np.zeros((64, 64))
    ee[32:40, 32:40] = 1
    check("multi-class: Atelectasis target = only its box", np.abs(f[0] - ea).max() < TOL)
    check("multi-class: Effusion target = only its box", np.abs(f[1] - ee).max() < TOL)
    check("multi-class: no cross-class mass (A on E cells, E on A cells, none on Mass cells)",
          f[0][32:40, 32:40].sum() == 0 and f[1][0:4, 0:4].sum() == 0 and f[:, 6:13, 50:57].sum() == 0)
    check("classes without bbox are unknown (observed False, zero target), non-main class ignored",
          list(o) == [True, True, False, False] and np.abs(f[2:]).max() == 0 and np.abs(c[2:]).max() == 0)
    # 2) 겹치는 다른 클래스 box: 클래스 target은 자기 box 면적만
    ann2 = [{"label": A, "xyxy": [100, 100, 300, 300]}, {"label": C, "xyxy": [200, 200, 500, 500]}]
    f2, c2, o2 = CT.image_class_targets(ann2, W, H)
    area = lambda t: t.sum() / 64 ** 2 * W * H  # noqa: E731
    check("overlapping classes: A area = 200*200, Cardiomegaly area = 300*300 (not union 120000)",
          abs(area(f2[0]) - 40000) < 1e-6 and abs(area(f2[2]) - 90000) < 1e-6, (area(f2[0]), area(f2[2])))
    allu = T.bbox_union_occupancy([a["xyxy"] for a in ann2], W, H)
    check("overlapping classes: class-wise target differs from all-class union", np.abs(f2[0] - allu).max() > 0.1)
    # 3) 같은 클래스 box 두 개 → union
    ann3 = [{"label": P, "xyxy": [100, 100, 300, 300]}, {"label": P, "xyxy": [200, 200, 400, 400]}]
    f3, c3, o3 = CT.image_class_targets(ann3, W, H)
    check("same-class boxes: union area (70000)", abs(area(f3[3]) - 70000) < 1e-6, area(f3[3]))
    # 4) coarse = fine 4x4 평균 = 직접 16 격자
    d1 = max(np.abs(c2[k] - T.coarse_from_fine(f2[k])).max() for k in range(4))
    d2 = np.abs(c2[0] - T.bbox_union_occupancy([[100, 100, 300, 300]], W, H, n=16)).max()
    check("coarse == 4x4 mean of fine == direct 16-grid (<=1e-10)", d1 <= TOL and d2 <= TOL, (d1, d2))

    # 5) soft-IoU
    t = np.zeros((4, 4))
    t[:2, :2] = 1
    p = np.full((4, 4), 0.5)
    exp = (0.5 * 4) / (8 + 4 - 2)
    check("soft-IoU formula sum(pt)/(sum p+sum t-sum pt)", abs(CT.soft_iou(p, t) - exp) < TOL, CT.soft_iou(p, t))
    check("soft-IoU(t,t) = 1", abs(CT.soft_iou(t, t) - 1) < TOL)
    try:
        CT.soft_iou(p, np.zeros((4, 4)))
        raised = False
    except ValueError:
        raised = True
    check("soft-IoU refuses empty (negative/unknown) target", raised)
    # 6) coarse prediction = sigmoid(P(logits))
    rng = np.random.default_rng(0)
    lg = rng.standard_normal((2, 4, 64, 64)) * 3
    cp = CT.coarse_prediction(lg)
    man = 1 / (1 + np.exp(-lg.reshape(2, 4, 16, 4, 16, 4).mean(axis=(3, 5))))
    alt = (1 / (1 + np.exp(-lg))).reshape(2, 4, 16, 4, 16, 4).mean(axis=(3, 5))
    check("coarse prediction = sigmoid(avgpool4(logits)) (not avgpool(sigmoid))",
          cp.shape == (2, 4, 16, 16) and np.abs(cp - man).max() < TOL and np.abs(cp - alt).max() > 1e-3)
    # 7) masked loss: unknown channel 무시
    tg = rng.random((2, 4, 16, 16))
    obs = np.array([[True, False, True, False], [False, True, False, False]])
    l0 = CT.masked_bce(lg[..., :16, :16], tg, obs)
    lg2 = lg[..., :16, :16].copy()
    lg2[0, 1] += 10
    lg2[1, 3] -= 7
    l1 = CT.masked_bce(lg2, tg, obs)
    lg3 = lg[..., :16, :16].copy()
    lg3[0, 0] += 1
    check("masked BCE ignores unknown channels, responds to observed", abs(l0 - l1) < TOL
          and abs(CT.masked_bce(lg3, tg, obs) - l0) > 1e-6)
    # 8) 집계: 영상 안 관측 클래스 평균 → patient macro, 클래스별 별도
    scores = np.array([[0.2, np.nan, 0.6, np.nan], [np.nan, 0.9, np.nan, np.nan], [0.1, 0.3, 0.5, 0.7]])
    ob = ~np.isnan(scores)
    ag = CT.aggregate(scores, ob, np.array(["1", "2", "3"]))
    exp_macro = np.mean([0.4, 0.9, 0.4])
    check("aggregation: image mean over observed classes, then patient macro",
          abs(ag["patient_macro"] - exp_macro) < TOL, ag["patient_macro"])
    check("aggregation: per-class means over observed images only",
          np.allclose(ag["per_class"], [0.15, 0.6, 0.55, 0.7]), ag["per_class"])
    sm = CT.score_matrix(np.ones((1, 4, 4, 4)), np.ones((1, 4, 4, 4)), np.array([[True, False, True, False]]))
    check("score_matrix: unknown -> NaN (excluded)", np.isnan(sm[0, 1]) and np.isnan(sm[0, 3]) and sm[0, 0] == 1)

    # 9) 실제 NIH target (iter_006 산출물)
    z = np.load(args.targets)
    man_rows = json.load(open(args.manifest))
    split, obsv, pid = z["split"], z["observed"], z["patient_id"]
    check("NIH targets: 160 images, 4 classes, fine 64 / coarse 16",
          z["fine"].shape == (160, 4, 64, 64) and z["coarse"].shape == (160, 4, 16, 16) and list(z["classes"]) ==
          CT.MAIN_CLASSES)
    dmax = max(np.abs(z["coarse"][i, k] - T.coarse_from_fine(z["fine"][i, k])).max()
               for i in range(160) for k in range(4))
    check("NIH targets: coarse vs fine 4x4 mean <= 1e-10", dmax <= TOL, dmax)
    by = {r["image"]: r for r in man_rows}
    leak, n_multi = 0.0, 0
    for i, img in enumerate(z["image_id"]):
        r = by[str(img)]
        labs = {a["label"] for a in r["annotation"]}
        n_multi += len(labs) > 1
        for k, c in enumerate(CT.MAIN_CLASSES):
            assert obsv[i, k] == (c in labs)
            own = [a["xyxy"] for a in r["annotation"] if a["label"] == c]
            # 자기 클래스 box를 1px 팽창한 영역 밖 질량 = 0 (다른 클래스 box 누출 없음)
            if own:
                m = np.zeros((1024, 1024))
                for x0, y0, x1, y1 in own:
                    m[max(0, int(np.floor(y0)) - 1):int(np.ceil(y1)) + 1, max(0, int(np.floor(x0)) - 1):int(np.ceil(x1)) + 1] = 1
                outside = T.mask_occupancy(m) == 0
                leak = max(leak, float(z["fine"][i, k][outside].sum()))
    check("NIH targets: observed mask == class has bbox; no mass outside own-class box region (independent raster)",
          leak == 0.0, {"leak": leak, "n_multiclass_images": n_multi})
    # 10) 위치 prior: train·관측만
    prior = CT.location_prior(z["coarse"], obsv, split)
    z2 = z["coarse"].copy()
    z2[split != "train"] = 99.0
    z2[(split == "train") & ~obsv[:, 0], 0] = 99.0
    prior2 = CT.location_prior(z2, obsv, split)
    check("location prior uses train observed targets only", np.abs(prior - prior2).max() == 0 and prior.shape == (4, 16, 16))
    # 11) image-swap derangement
    donor = CT.image_swap_derangement(pid, split, obsv)
    donor_b = CT.image_swap_derangement(pid, split, obsv)
    okd = True
    for i in range(160):
        for k in range(4):
            d = donor[i, k]
            if not obsv[i, k]:
                okd &= d == -1
                continue
            okd &= (d >= 0 and d != i and pid[d] != pid[i] and split[d] == split[i] and obsv[d, k])
    perm_ok = all(sorted(donor[obsv[:, k] & (split == s), k].tolist()) ==
                  sorted(np.where(obsv[:, k] & (split == s))[0].tolist())
                  for k in range(4) for s in ("train", "validation", "test"))
    check("image-swap: fixed derangement within split & class, other patient, bijective, deterministic",
          okd and perm_ok and np.array_equal(donor, donor_b))
    # 12) patient bootstrap: 모든 방법에 같은 index
    idx = CT.bootstrap_indices(48, B=500)
    idx2 = CT.bootstrap_indices(48, B=500)
    a = rng.random(48)
    ci = CT.paired_bootstrap_ci(a + 0.05, a, idx)
    check("bootstrap: deterministic shared patient indices; paired constant shift CI = shift",
          np.array_equal(idx, idx2) and abs(ci["ci_low"] - 0.05) < 1e-12 and abs(ci["ci_high"] - 0.05) < 1e-12, ci)

    n_fail = sum(not r["pass"] for r in RESULTS)
    with open(args.out, "w") as fh:
        json.dump({"n": len(RESULTS), "n_fail": n_fail, "tol": TOL, "results": RESULTS}, fh, indent=1, ensure_ascii=False)
    print(f"class target tests: {len(RESULTS) - n_fail}/{len(RESULTS)} pass")
    if n_fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
