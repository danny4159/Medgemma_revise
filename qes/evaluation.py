"""Annotation-based evaluation. selector 출력이 고정된 뒤에만 호출한다."""
import itertools
import json
import os

import numpy as np

from .data import DATA_DIR, FINDINGS, GRID, tile_boxes
from .selection import argmax_tie_low

NT = GRID * GRID
PAIR_IOU_MAX = 0.1
PAIR_U_LOSS_MIN = 0.25


def load_annotations(data_dir=DATA_DIR, findings=FINDINGS):
    """file -> {'W','H','boxes': {finding: [xyxy,...]}} (질문 bank의 소견만)."""
    meta = json.load(open(os.path.join(data_dir, "meta.json")))
    out = {}
    for m in meta:
        boxes = {}
        for b in m["bounding_boxes_pixel_xyxy"]:
            if b["class_name"] in findings:
                boxes.setdefault(b["class_name"], []).append(
                    (b["x_min"], b["y_min"], b["x_max"], b["y_max"]))
        out[m["file"]] = {"W": m["orig_width"], "H": m["orig_height"], "boxes": boxes}
    return out


def _span(a0, a1, n):
    """pixel center 규칙: 좌표 [a0,a1)에 center(k+0.5)가 들어가는 pixel k 범위."""
    lo = int(np.ceil(a0 - 0.5))
    hi = int(np.ceil(a1 - 0.5))
    return max(lo, 0), min(max(hi, 0), n)


def union_mask(boxes, W, H):
    m = np.zeros((H, W), dtype=bool)
    for x0, y0, x1, y1 in boxes:
        c0, c1 = _span(x0, x1, W)
        r0, r1 = _span(y0, y1, H)
        m[r0:r1, c0:c1] = True
    return m


class GeomImage:
    def __init__(self, W, H, boxes_by_finding):
        self.W, self.H = W, H
        self.tiles = tile_boxes(W, H)
        self.G = {q: union_mask(bx, W, H) for q, bx in boxes_by_finding.items()}
        self.stats = {q: self._tile_stats(g) for q, g in self.G.items()}

    def _tile_stats(self, g):
        area_g = int(g.sum())
        iou, cov = [], []
        for x0, y0, x1, y1 in self.tiles:
            inter = int(g[y0:y1, x0:x1].sum())
            area_r = (x1 - x0) * (y1 - y0)
            iou.append(inter / (area_r + area_g - inter))
            cov.append(inter / area_g)
        iou = np.array(iou)
        best = float(iou.max())
        return {"iou": iou, "cov": np.array(cov), "U": iou / best, "oracle_iou": best,
                "best_tile": argmax_tie_low(iou)[0], "area_g": area_g}

    def region_iou(self, a, b):
        ga, gb = self.G[a], self.G[b]
        return float((ga & gb).sum() / (ga | gb).sum())


def build_geometry(ann):
    return {f: GeomImage(a["W"], a["H"], a["boxes"]) for f, a in ann.items()}


def positive_combos(geo):
    return [(img, q) for img in sorted(geo) for q in FINDINGS if q in geo[img].G]


def classify_pairs(geo):
    pairs = []
    for img in sorted(geo):
        pos = [q for q in FINDINGS if q in geo[img].G]
        for a, b in itertools.combinations(pos, 2):
            sa, sb = geo[img].stats[a], geo[img].stats[b]
            riou = geo[img].region_iou(a, b)
            loss_a = 1.0 - sa["U"][sb["best_tile"]]
            loss_b = 1.0 - sb["U"][sa["best_tile"]]
            distinct = (riou <= PAIR_IOU_MAX and sa["best_tile"] != sb["best_tile"]
                        and loss_a >= PAIR_U_LOSS_MIN and loss_b >= PAIR_U_LOSS_MIN)
            pairs.append({"image": img, "a": a, "b": b, "region_iou": riou,
                          "best_a": sa["best_tile"], "best_b": sb["best_tile"],
                          "U_loss_a": float(loss_a), "U_loss_b": float(loss_b), "distinct": bool(distinct)})
    return pairs


def macro(values_by_combo):
    """(img,q)->value 를 영상 내부 평균 후 영상 macro-average."""
    per_img = {}
    for (img, q), v in values_by_combo.items():
        per_img.setdefault(img, []).append(v)
    img_means = {img: float(np.mean(v)) for img, v in per_img.items()}
    return float(np.mean(list(img_means.values()))), img_means


def location_prior_tiles(geo):
    """평가 영상을 제외한 동일 소견 annotation들의 평균 U가 최고인 tile (GT 기반 개발용 비교군)."""
    out = {}
    for img, q in positive_combos(geo):
        others = [o for o in geo if o != img and q in geo[o].G]
        mean_u = np.mean([geo[o].stats[q]["U"] for o in others], axis=0)
        out[(img, q)] = argmax_tie_low(mean_u)[0]
    return out


def evaluate(selection, geo, methods):
    combos = positive_combos(geo)
    prior = location_prior_tiles(geo)
    metric_names = ["U", "iou", "cov"]
    res = {"n_combos": len(combos), "n_images": len({c[0] for c in combos}), "methods": {}, "per_combo": []}

    def tile_metrics(img, q, t):
        s = geo[img].stats[q]
        return {k: float(s[k][t]) for k in metric_names}

    rows = {}
    for img, q in combos:
        s = geo[img].stats[q]
        row = {"image": img, "finding": q, "oracle_iou": s["oracle_iou"], "best_tile": s["best_tile"],
               "area_frac": s["area_g"] / (geo[img].W * geo[img].H)}
        for meth in methods:
            t = selection[img][q][meth]
            row[meth] = {"tile": t, **tile_metrics(img, q, t)}
            donors = [j for j in selection if j != img]
            row[meth]["image_swap"] = {k: float(np.mean([geo[img].stats[q][k][selection[j][q][meth]]
                                                         for j in donors])) for k in metric_names}
            others = [o for o in FINDINGS if o != q and o in geo[img].G]
            if others:
                row[meth]["question_swap"] = {k: float(np.mean([geo[img].stats[q][k][selection[img][o][meth]]
                                                               for o in others])) for k in metric_names}
        row["uniform"] = {k: float(np.mean(s[k])) for k in metric_names}
        row["location_prior"] = {"tile": prior[(img, q)], **tile_metrics(img, q, prior[(img, q)])}
        rows[(img, q)] = row
        res["per_combo"].append(row)

    def agg(getter):
        vals = {c: getter(rows[c]) for c in combos}
        vals = {c: v for c, v in vals.items() if v is not None}
        m, per_img = macro(vals)
        return {"macro": m, "per_image": per_img, "n_combos": len(vals)}

    for meth in methods + ["uniform", "location_prior"]:
        res["methods"][meth] = {k: agg(lambda r, k=k, meth=meth: r[meth][k]) for k in metric_names}
    for meth in methods:
        res["methods"][meth]["image_swap"] = {k: agg(lambda r, k=k, meth=meth: r[meth]["image_swap"][k])
                                              for k in metric_names}
        res["methods"][meth]["question_swap"] = {
            k: agg(lambda r, k=k, meth=meth: r[meth].get("question_swap", {}).get(k)) for k in metric_names}
    res["methods"]["oracle_iou"] = agg(lambda r: r["oracle_iou"])
    return res


def pair_scores(selection, geo, pairs, methods):
    out = {}
    for meth in methods:
        per = []
        for p in pairs:
            img, a, b = p["image"], p["a"], p["b"]
            Ua, Ub = geo[img].stats[a]["U"], geo[img].stats[b]["U"]
            Ra, Rb = selection[img][a][meth], selection[img][b][meth]
            S = ((Ua[Ra] - Ua[Rb]) + (Ub[Rb] - Ub[Ra])) / 2.0
            per.append({**p, "S": float(S), "tile_a": Ra, "tile_b": Rb, "same_tile": Ra == Rb})
        strata = {}
        for name, flt in (("distinct", True), ("other", False)):
            sub = [x for x in per if x["distinct"] == flt]
            by_img = {}
            for x in sub:
                by_img.setdefault(x["image"], []).append(x["S"])
            img_means = {k: float(np.mean(v)) for k, v in by_img.items()}
            strata[name] = {"n_pairs": len(sub), "n_images": len(by_img),
                            "macro_S": float(np.mean(list(img_means.values()))) if img_means else None,
                            "per_image": img_means,
                            "frac_same_tile": float(np.mean([x["same_tile"] for x in sub])) if sub else None}
        out[meth] = {"pairs": per, **strata}
    return out


def criteria(ev, ps, prefix_ok=True):
    M = ev["methods"]
    U = lambda m: M[m]["U"]["macro"]
    I = lambda m: M[m]["iou"]["macro"]
    c = {}
    best_base = max(U("D_blur"), U("crop_conf"), U("uniform"), U("location_prior"))
    c1a = U("C_blur") >= best_base + 0.05
    c1b = I("C_blur") >= max(I("D_blur"), I("crop_conf"))
    c["1"] = {"pass": bool(c1a and c1b), "U_C_blur": U("C_blur"), "best_baseline_U": best_base,
              "iou_C_blur": I("C_blur"), "best_iou_Dblur_crop": max(I("D_blur"), I("crop_conf"))}
    pi_c, pi_d = M["C_blur"]["U"]["per_image"], M["D_blur"]["U"]["per_image"]
    n_pos = sum(1 for k in pi_c if pi_c[k] - pi_d[k] > 0)
    swap = M["C_blur"]["image_swap"]["U"]["macro"]
    c["2"] = {"pass": bool(n_pos >= 6 and U("C_blur") >= swap + 0.05), "n_images_C_gt_D": n_pos,
              "n_images": len(pi_c), "U_C_blur": U("C_blur"), "U_image_swap": swap}
    s_c = ps["C_blur"]["distinct"]["macro_S"]
    s_base = max(ps["D_blur"]["distinct"]["macro_S"], ps["crop_conf"]["distinct"]["macro_S"])
    c["3"] = {"pass": bool(s_c > 0 and s_c >= s_base + 0.10), "S_C_blur": s_c, "best_S_Dblur_crop": s_base}
    c["4"] = {"pass": bool(U("C_mean") >= max(U("D_mean"), U("crop_conf"))), "U_C_mean": U("C_mean"),
              "U_D_mean": U("D_mean"), "U_crop_conf": U("crop_conf")}
    c["all_pass"] = all(c[k]["pass"] for k in ("1", "2", "3", "4"))
    return c
