"""det_compare 결과의 독립 재계산 (기본 medgemma env).

공유하는 것은 승인된 strict parser(parse.parse_response)와 좌표 변환(geometry)뿐이다. matching은 itertools 열거
(test_match_identity.brute), F1·FP·상보성 집계와 bootstrap percentile은 여기서 따로 구현한다. bootstrap index는
같은 정의(np.random.default_rng(20260924).integers(0, n, (10000, n)))를 따로 생성해 CI를 비교한다.
"""
import argparse
import glob
import json
import sys

import numpy as np

BASE = "/SSD1_1TB/home/milab/daniel/08_medgemma/research"
sys.path.insert(0, BASE)
sys.path.insert(0, f"{BASE}/tests_det")
from rsna_diag import parse as PA, geometry as G  # noqa: E402
from test_match_identity import brute  # noqa: E402


def f1(pred, gt, thr):
    pairs, key = brute(pred, gt, thr) if gt else ([], None)
    tp = len(pairs)
    p = tp / len(pred) if pred else 0.0
    r = tp / len(gt) if gt else 0.0
    return (2 * p * r / (p + r) if p + r > 0 else 0.0), tp, {g for g, _ in pairs}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--analysis", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    an = json.load(open(a.analysis))
    gt = json.load(open(f"{BASE}/results/iter_010/manifests/gt_manifest.json"))
    ids = json.load(open(f"{BASE}/results/iter_010/manifests/confirm_ids.json"))
    pos = [i for i in ids if gt[i]["category"] == "opacity"]
    sel = json.load(open(an["provenance"]["detector17"]["selection"]))
    thr = sel["selected"]["threshold"]
    det_dir = an["provenance"]["detector17"]["confirm_dir"]
    raw = json.load(open(f"{det_dir}/raw_preds.json"))
    det = {}
    for i in ids:
        r = raw[i]
        h, w = r["img_hw"]
        top, left, side = G.pad_offsets(h, w)
        det[i] = [G.canvas_to_norm(b, top, left, side) for b, s, l in zip(r["boxes_xyxy_px"], r["scores"], r["labels"]) if l == 1 and s >= thr]
    recs = {}
    for f in sorted(glob.glob(f"{BASE}/results/iter_012/confirm_sft_seed17/gen_worker*.jsonl")):
        for l in open(f):
            x = json.loads(l); recs[x["id"]] = x
    b0 = {}
    for i in ids:
        pp = PA.parse_response(recs[i]["suffix_text_raw"], recs[i]["ended_eos"])
        b0[i] = pp["boxes"] if pp["status"] in PA.VALID else []
    res = {}
    idx = np.random.default_rng(20260924).integers(0, len(pos), size=(10000, len(pos)), dtype=np.int32)
    for t in (0.3, 0.5):
        dv = np.array([f1(det[i], [b["yxyx_norm"] for b in gt[i]["boxes"]], t)[0] for i in pos])
        bv = np.array([f1(b0[i], [b["yxyx_norm"] for b in gt[i]["boxes"]], t)[0] for i in pos])
        d = dv - bv
        m = d[idx].mean(axis=1)
        res[f"f1@{t}"] = {"det": float(dv.mean()), "b0": float(bv.mean()), "diff": float(d.mean()),
                          "ci97.5": [float(np.percentile(m, 1.25)), float(np.percentile(m, 98.75))]}
        # 상보성
        rows = []
        for i in pos:
            g = [b["yxyx_norm"] for b in gt[i]["boxes"]]
            dh = f1(det[i], g, t)[2]; sh = f1(b0[i], g, t)[2]
            rows.append([len(dh - sh), len(sh - dh), len(g)])
        rr = np.array(rows, float)
        res[f"comp@{t}"] = {"detector_only_rate": float(rr[:, 0].sum() / rr[:, 2].sum()), "sft_only_rate": float(rr[:, 1].sum() / rr[:, 2].sum())}
    fpd = []
    fpb = []
    for i in ids:
        g = [b["yxyx_norm"] for b in gt[i]["boxes"]]
        fpd.append(len(det[i]) - (f1(det[i], g, 0.3)[1] if g else 0))
        fpb.append(len(b0[i]) - (f1(b0[i], g, 0.3)[1] if g else 0))
    fd = np.array(fpd, float) - np.array(fpb, float)
    idx8 = np.random.default_rng(20260924).integers(0, len(ids), size=(10000, len(ids)), dtype=np.int32)
    mm = fd[idx8].mean(axis=1)
    res["fp_increase"] = {"diff": float(fd.mean()), "ci95": [float(np.percentile(mm, 2.5)), float(np.percentile(mm, 97.5))]}
    P = an["primary_detector17_minus_B0"]
    chk = {}
    for t in ("0.3", "0.5"):
        k = f"f1@{t}"
        chk[k] = abs(P[k]["diff"] - res[k]["diff"]) < 1e-12 and all(abs(x - y) < 1e-12 for x, y in zip(P[k]["ci97.5"], res[k]["ci97.5"]))
        c = an["complementarity"][f"iou{t}"]
        chk[f"comp@{t}"] = abs(c["detector_only_rate"] - res[f"comp@{t}"]["detector_only_rate"]) < 1e-12 and abs(c["sft_only_rate"] - res[f"comp@{t}"]["sft_only_rate"]) < 1e-12
    F = an["fp_increase_detector17_minus_B0_all800"]
    chk["fp_increase"] = abs(F["diff"] - res["fp_increase"]["diff"]) < 1e-12 and all(abs(x - y) < 1e-12 for x, y in zip(F["ci95"], res["fp_increase"]["ci95"]))
    out = {"independent": res, "match_saved": chk, "pass": all(chk.values())}
    json.dump(out, open(a.out, "w"), indent=2)
    print(json.dumps(out, indent=1))
    sys.exit(0 if out["pass"] else 1)


if __name__ == "__main__":
    main()
