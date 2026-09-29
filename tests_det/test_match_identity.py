"""metrics.match(상보성 GT identity 기준)의 독립 exhaustive 대조 (기본 medgemma env).

iter_033 tests/test_det_match.py(sha256 e6ae4026...)는 무작위 비동점 사례 위주였고 handcrafted_tie가 실제 동점이
아니었다. 이번 검사는 규약(최대 cardinality → 총 IoU(1e-12 초과 개선만 갱신) → GT 순서로 본 pred index tuple의
사전순 최소, 미매칭은 모든 index보다 뒤)을 itertools.product 열거로 따로 구현해 다음을 비교한다.
  1. 실제 동점: 같은 IoU의 pred 두 개, 한 pred가 두 GT와 같은 IoU, 겹친 GT, 동일 좌표 중복 pred.
  2. 정수 격자로 동점을 자주 만드는 무작위 사례 2,000개(IoU 0.3/0.5).
  3. 저장 VLM 목록: iter_012 confirm800 SFT seed17/29/43 및 base 두 prompt(양성, IoU 0.3/0.5).
  4. 선택적으로 detector raw_preds(threshold 적용)의 양성 목록.
det_match.bounded_match(DP)는 cardinality·총 IoU만 같아야 하며 identity 차이는 따로 센다(분석에는 쓰지 않음).
"""
import argparse
import glob
import itertools
import json
import os
import random
import sys

BASE = "/SSD1_1TB/home/milab/daniel/08_medgemma/research"
sys.path.insert(0, BASE)
from rsna_diag import metrics as M, det_match as DM, parse as PA  # noqa: E402


def iou(a, b):
    ih = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iw = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ih * iw
    u = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1]) + max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1]) - i
    return i / u if u > 0 else 0.0


def brute(pred, gt, thr):
    cands = [[pi for pi in range(len(pred)) if iou(pred[pi], g) >= thr] + [None] for g in gt]
    best_key, best = None, []
    for combo in itertools.product(*cands):
        used = [c for c in combo if c is not None]
        if len(used) != len(set(used)):
            continue
        card = len(used)
        tot = 0.0
        for gi, pi in enumerate(combo):
            if pi is not None:
                tot += iou(pred[pi], gt[gi])
        if best_key is None or card > best_key[0] or (card == best_key[0] and tot > best_key[1] + 1e-12):
            best_key, best = (card, tot), [(gi, pi) for gi, pi in enumerate(combo) if pi is not None]
    return best, best_key


def compare(pred, gt, thr, stats, tag):
    if len(gt) == 0:
        return
    m = M.match(pred, gt, thr)
    b, key = brute(pred, gt, thr)
    stats["n"] += 1
    if sorted(m) != sorted(b):
        stats["identity_mismatch"].append({"tag": tag, "thr": thr, "match": m, "brute": b})
    if len(gt) <= 4 and pred:
        d = DM.bounded_match(pred, gt, thr)
        tot_d = sum(iou(pred[p], gt[g]) for g, p in d)
        if len(d) != (key[0] if key else 0) or (key and abs(tot_d - key[1]) > 1e-9):
            stats["dp_card_or_total_mismatch"].append({"tag": tag, "thr": thr})
        elif sorted(d) != sorted(b):
            stats["dp_identity_diff_only"] += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--det_raw", nargs="*", default=[], help="raw_preds_dir:threshold")
    a = ap.parse_args()
    stats = {"n": 0, "identity_mismatch": [], "dp_card_or_total_mismatch": [], "dp_identity_diff_only": 0}
    hand = {
        "equal_iou_two_preds": ([[0, 0, 10, 10], [0, 0, 10, 10]], [[0, 0, 10, 10]]),
        "mirror_equal_iou": ([[0, 0, 10, 12], [0, -2, 10, 10]], [[0, 0, 10, 10]]),
        "one_pred_two_gt_equal": ([[0, 0, 10, 10]], [[0, 0, 10, 12], [0, -2, 10, 10]]),
        "overlapping_gt_two_preds": ([[0, 0, 10, 10], [0, 2, 10, 12]], [[0, 1, 10, 11], [0, 0, 10, 10]]),
        "dup_preds_overlapping_gt": ([[0, 0, 10, 10], [0, 0, 10, 10], [0, 5, 10, 15]], [[0, 0, 10, 10], [0, 3, 10, 13]]),
        "chain_tie": ([[0, 0, 10, 10], [0, 5, 10, 15], [0, 10, 10, 20]], [[0, 2, 10, 12], [0, 7, 10, 17]]),
    }
    hand_res = {}
    for k, (p, g) in hand.items():
        for thr in (0.3, 0.5):
            before = len(stats["identity_mismatch"])
            compare(p, g, thr, stats, f"hand:{k}")
            hand_res[f"{k}@{thr}"] = {"match": M.match(p, g, thr), "ok": len(stats["identity_mismatch"]) == before}
    rng = random.Random(20260929)
    for t in range(2000):
        ng, npd = rng.randint(1, 4), rng.randint(0, 7)
        mk = lambda: (lambda y, x, h, w: [y, x, y + h, x + w])(rng.randrange(0, 10) * 5, rng.randrange(0, 10) * 5,
                                                                 rng.randrange(2, 6) * 5, rng.randrange(2, 6) * 5)
        g = [mk() for _ in range(ng)]
        p = [mk() for _ in range(npd)]
        if rng.random() < 0.3 and p:
            p.append(list(p[0]))
        compare(p, g, rng.choice((0.3, 0.5)), stats, f"rand{t}")
    gt = json.load(open(f"{BASE}/results/iter_010/manifests/gt_manifest.json"))
    ids = json.load(open(f"{BASE}/results/iter_010/manifests/confirm_ids.json"))
    pos = [i for i in ids if gt[i]["category"] == "opacity"]
    n_vlm = 0
    for d, prompts in (("confirm_sft_seed17", ["concise"]), ("confirm_sft_seed29", ["concise"]), ("confirm_sft_seed43", ["concise"]),
                       ("confirm_base", ["concise", "official_long"])):
        recs = {}
        for f in sorted(glob.glob(f"{BASE}/results/iter_012/{d}/gen_worker*.jsonl")):
            for l in open(f):
                r = json.loads(l); recs[(r["id"], r["prompt_name"])] = r
        for pr in prompts:
            for i in pos:
                r = recs[(i, pr)]
                pp = PA.parse_response(r["suffix_text_raw"], r["ended_eos"])
                boxes = pp["boxes"] if pp["status"] in PA.VALID else []
                g = [b["yxyx_norm"] for b in gt[i]["boxes"]]
                for thr in (0.3, 0.5):
                    compare(boxes, g, thr, stats, f"{d}:{pr}:{i}")
                    n_vlm += 1
    n_det = 0
    for item in a.det_raw:
        dd, thr_s = item.rsplit(":", 1)
        from rsna_diag import det_lib as D
        raw = json.load(open(os.path.join(dd, "raw_preds.json")))
        pr = D.preds_to_norm_yxyx(raw, gt, float(thr_s))
        for i, v in pr.items():
            if gt[i]["category"] != "opacity":
                continue
            g = [b["yxyx_norm"] for b in gt[i]["boxes"]]
            for thr in (0.3, 0.5):
                compare(v["boxes"], g, thr, stats, f"det:{dd}:{i}")
                n_det += 1
    out = {"n_compared": stats["n"], "n_vlm_cases": n_vlm, "n_det_cases": n_det,
           "identity_mismatch_count": len(stats["identity_mismatch"]), "identity_mismatch_examples": stats["identity_mismatch"][:10],
           "dp_card_or_total_mismatch_count": len(stats["dp_card_or_total_mismatch"]),
           "dp_identity_diff_only": stats["dp_identity_diff_only"], "handcrafted": hand_res,
           "pass": len(stats["identity_mismatch"]) == 0 and len(stats["dp_card_or_total_mismatch"]) == 0}
    json.dump(out, open(a.out, "w"), indent=2)
    print(json.dumps({k: v for k, v in out.items() if k not in ("identity_mismatch_examples", "handcrafted")}, indent=1))
    sys.exit(0 if out["pass"] else 1)


if __name__ == "__main__":
    main()
