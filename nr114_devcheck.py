"""iter_114 개발 47개(iter_107 항목)에서 MSPC 대조의 기초 위치 적합성과 대상 MG(A_U_e5)의 저장 출력 회귀를 확인한다 (CPU, 모델 미사용).

사전 기준(계획): MSPC 의 union IoU>=0.3 항목 수가 A 의 통과 수보다 0.10*N 넘게 낮지 않다(A 32/47 → 최소 28/47).
주의: DEV 47개는 PadChest-GR *train* split 이므로 MSPC 배포본이 학습에 쓴 영상일 수 있다. 이 점검은 자산·좌표 연결과 하한 확인이지 비편향 성능이 아니다.
출력: results/iter_114/dev/devcheck.json (새 파일).
"""
import json
import math
import sys
from pathlib import Path

import nr107_geom as G
import nr114_mg as N

OUT = N.R114 / "dev"


def load(run):
    recs, digest = N.verify_all(N.R114 / "mg" / run, "DEV", "A" if run.startswith("DEV_A") else "MSPC", 1)
    return {r["item_key"]: r for r in recs}


def stats(boxes_by_item, items):
    n_pass, ious, empty, rec_m, rec_g = 0, [], 0, 0, 0
    for it in items:
        b = boxes_by_item[it["item_key"]]
        iou = G.union_iou(b, it["gt"]) if b else 0.0
        n_pass += int(iou >= 0.3)
        ious.append(iou)
        empty += int(not b)
        m, ng, _ = G.match_recall(b, it["gt"], 0.3) if b else (0, len(it["gt"]), 0)
        rec_m += m
        rec_g += ng
    return {"n": len(items), "union_iou_ge_0.3": n_pass, "mean_union_iou": sum(ious) / len(ious), "n_empty": empty, "box_recall@0.3": rec_m / rec_g,
            "matched_gt": rec_m, "total_gt": rec_g}


def main():
    items = json.loads((N.R107 / "items.json").read_text())
    runs = {"A": sys.argv[1], "MSPC": sys.argv[2]}
    A, M = load(runs["A"]), load(runs["MSPC"])
    old = {it["item_key"]: it["mg"]["0.8"] for it in items}
    max_box, max_sc, cnt_mismatch = 0.0, 0.0, 0
    for it in items:
        a = A[it["item_key"]]["detection"]
        o = old[it["item_key"]]
        if len(a["boxes_orig_xyxy"]) != len(o["boxes"]):
            cnt_mismatch += 1
            continue
        # 순서 의존을 피하기 위해 score 내림차순 정렬 뒤 비교
        sa = sorted(zip(a["scores"], a["boxes_orig_xyxy"]), reverse=True)
        so = sorted(zip(o["scores"], o["boxes"]), reverse=True)
        for (s1, b1), (s2, b2) in zip(sa, so):
            max_sc = max(max_sc, abs(s1 - s2))
            max_box = max(max_box, max(abs(x - y) for x, y in zip(b1, b2)))
    bad_boxes = [k for k, r in M.items() if not all(math.isfinite(v) for b in r["detection"]["boxes_orig_xyxy"] for v in b)]
    bad_valid = [k for k, r in M.items() if not all(0 <= b[0] < b[2] <= 1 and 0 <= b[1] < b[3] <= 1 for b in r["detection"]["boxes_orig_xyxy"])]
    sa = stats({k: r["detection"]["boxes_orig_xyxy"] for k, r in A.items()}, items)
    sm = stats({k: r["detection"]["boxes_orig_xyxy"] for k, r in M.items()}, items)
    old_stats = stats({k: o["boxes"] for k, o in old.items()}, items)
    floor = math.ceil(old_stats["union_iou_ge_0.3"] - 0.10 * len(items))
    res = {"runs": runs, "n_items": len(items), "A_new_vs_stored_iter046": {"count_mismatch_items": cnt_mismatch, "max_abs_box_diff": max_box, "max_abs_score_diff": max_sc},
           "A_stored_iter046": old_stats, "A_new": sa, "MSPC": sm, "pass_floor_for_MSPC": floor, "plan_floor": 28,
           "MSPC_nonfinite_box_items": bad_boxes, "MSPC_out_of_range_box_items": bad_valid,
           "MSPC_meets_floor": sm["union_iou_ge_0.3"] >= floor,
           "caveat": "DEV items come from PadChest-GR train split: MSPC may have been trained on them; floor check validates asset/coordinate linkage only."}
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "devcheck.json"
    with p.open("x") as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
