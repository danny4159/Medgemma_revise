"""탐색적 오류 분해 진단 (iter_009). 주평가·주지표를 바꾸지 않는다. 결과는 exploratory로만 보고한다.

- 좌표 규약 대안(x/y 뒤바뀜, 좌우/상하 반전)을 GT에 적용했을 때 max-IoU가 개선되는지: 사용법(축·좌우) 오류 vs 내용 오류 구분.
- 예측 박스 크기/중심 분포, 반복 loop(박스 수 과다) 비율, 예측이 GT 좌/우 폐야 어느 쪽인지 (좌우 일치율).
사용: python -m rsna_diag.diagnostics --gen ... --split development --out results/iter_009/dev/diagnostics.json
"""
import argparse
import json

import numpy as np

from . import metrics as M, parse as PA
from .evaluate import PROMPTS, gt_boxes, load_gen


def transforms(b):
    y0, x0, y1, x1 = b
    return {"as_is": [y0, x0, y1, x1], "swap_xy": [x0, y0, x1, y1],
            "mirror_lr": [y0, 1000 - x1, y1, 1000 - x0], "flip_ud": [1000 - y1, x0, 1000 - y0, x1],
            "rot180": [1000 - y1, 1000 - x1, 1000 - y0, 1000 - x0]}


def center(b):
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", required=True)
    ap.add_argument("--split", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--gt", default="results/iter_009/manifests/gt_manifest.json")
    a = ap.parse_args()
    gt = json.load(open(a.gt))
    recs = load_gen(a.gen)
    pos = sorted(i for i, g in gt.items() if g["split"] == a.split and g["category"] == "opacity")
    out = {"split": a.split, "note": "exploratory; 주평가/주지표 변경 없음", "prompts": {}}
    for p in PROMPTS:
        ids, alt = [], {k: [] for k in transforms([0, 0, 1, 1])}
        n_boxes, sizes, gsizes, cdist, side_match, side_n = [], [], [], [], 0, 0
        loops = 0
        for i in pos:
            r = recs.get((i, p))
            if r is None:
                continue
            pr = PA.parse_response(r["suffix_text_raw"], r["ended_eos"])
            if r["n_output_tokens"] > 1000 or len(pr["boxes"]) > 10:
                loops += 1
            if pr["status"] != "valid_nonempty":
                continue
            g = gt_boxes(gt[i])
            ids.append(i)
            n_boxes.append(len(pr["boxes"]))
            for name in alt:
                alt[name].append(max(M.iou(transforms(b)[name], gb) for b in pr["boxes"] for gb in g))
            sizes.append(M.union_area(pr["boxes"]) / 1e6)
            gsizes.append(M.union_area(g) / 1e6)
            pc = np.mean([center(b) for b in pr["boxes"]], axis=0)
            gc = np.mean([center(b) for b in g], axis=0)
            cdist.append(float(np.hypot(*(pc - gc))))
            if len(pr["boxes"]) == 1 and len(g) == 1:  # 단일 박스끼리: 좌우 반쪽 일치
                side_n += 1
                side_match += int((center(pr["boxes"][0])[1] < 500) == (center(g[0])[1] < 500))
        f = lambda v: float(np.mean(v)) if len(v) else None
        out["prompts"][p] = {
            "n_valid_nonempty_positive": len(ids),
            "mean_max_iou_by_convention": {k: f(v) for k, v in alt.items()},
            "frac_max_iou_ge_0.3_by_convention": {k: (float(np.mean(np.array(v) >= 0.3)) if v else None) for k, v in alt.items()},
            "mean_n_pred": f(n_boxes), "pred_union_area_frac_mean": f(sizes), "gt_union_area_frac_mean": f(gsizes),
            "center_distance_mean_(0-1000 units)": f(cdist), "center_distance_median": float(np.median(cdist)) if cdist else None,
            "single_box_side_agreement": {"k": side_match, "n": side_n},
            "n_looping_or_long_outputs": loops}
    json.dump(out, open(a.out, "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
