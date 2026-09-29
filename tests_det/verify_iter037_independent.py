"""iter_037 독립 수치 대조. det37 report.json의 표를 원시 raw_preds.json과 SFT 응답에서 자체 구현으로 다시 계산한다.

독립 구현: IoU, itertools 열거 matching(최대 cardinality→총 IoU→사전순, det_match/metrics.match 미사용),
padding 좌표 변환(geometry 미사용), F1·lesion recall·FP·통합 FP 범주·상보성·SFT-only 4범주·R·pair IoU0.5 통과율.
공유(독립 아님): SFT 응답 parser(parse.parse_response), 영상 크기 img_hw는 raw_preds 기록, GT manifest, 선택 threshold(LOCK 파일).
bootstrap CI는 이 검증에서 다시 계산하지 않는다(회귀 검사와 iter_036 리뷰의 독립 재계산에 의존).
사용: python tests_det/verify_iter037_independent.py --split V400|confirm800 --report <report.json> --out <새 json> (덮어쓰기 거부)"""
import argparse
import itertools
import json
import os
import sys

BASE = "/SSD1_1TB/home/milab/daniel/08_medgemma/research"
sys.path.insert(0, BASE)
from rsna_diag import parse as PA  # noqa: E402  (parser만 공유)

SEL = {17: f"{BASE}/results/iter_035/select/seed17/v400_selection.json", 29: f"{BASE}/results/iter_035/select/seed29/v400_selection.json"}
RAWDIR = {"confirm800": {17: "results/iter_035/confirm800/det17", 29: "results/iter_035/confirm800/det29"},
          "V400": {17: "results/iter_035/eval/seed17/V400_e18", 29: "results/iter_035/eval/seed29/V400_e26"}}
SFTDIR = {"confirm800": {s: f"results/iter_012/confirm_sft_seed{s}" for s in (17, 29, 43)},
          "V400": {17: "results/iter_012/train/lr2e-4_s17/epoch_05/val_gen"}}
IDS = {"confirm800": "results/iter_010/manifests/confirm_ids.json", "V400": "results/iter_010/manifests/validation_ids.json"}


def iou(a, b):
    ih = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iw = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ih * iw
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u > 0 else 0.0


def pairs(pred, gt, thr):
    """{gi: pi} 열거 matching."""
    if not pred or not gt:
        return {}
    cands = [[p for p in range(len(pred)) if iou(pred[p], g) >= thr] + [None] for g in gt]
    best, bk = {}, None
    for combo in itertools.product(*cands):
        used = [c for c in combo if c is not None]
        if len(used) != len(set(used)):
            continue
        k = (len(used), sum(iou(pred[c], gt[gi]) for gi, c in enumerate(combo) if c is not None))
        if bk is None or k[0] > bk[0] or (k[0] == bk[0] and k[1] > bk[1] + 1e-12):
            bk, best = k, {gi: c for gi, c in enumerate(combo) if c is not None}
    return best


def to_norm(box, h, w):
    side = max(h, w)
    top = (side - h) // 2 if h < w else 0
    left = (side - w) // 2 if w < h else 0
    x0, y0, x1, y1 = box
    return [(y0 + top) * 1000.0 / side, (x0 + left) * 1000.0 / side, (y1 + top) * 1000.0 / side, (x1 + left) * 1000.0 / side]


def f1(tp, npred, ngt):
    p = tp / npred if npred else 0.0
    r = tp / ngt if ngt else 0.0
    return 2 * p * r / (p + r) if p + r > 0 else 0.0


def fp_cats(pred, gt, thr):
    pr = pairs(pred, gt, thr)
    mp_, mg = set(pr.values()), set(pr)
    c = {"competes_for_matched_gt": 0, "near_miss_0.1_to_thr": 0, "no_gt_within_0.1": 0}
    for pi, b in enumerate(pred):
        if pi in mp_:
            continue
        m = max((iou(b, g) for g in gt), default=0.0)
        if m >= thr:
            c["competes_for_matched_gt"] += 1
        elif m >= 0.1:
            c["near_miss_0.1_to_thr"] += 1
        else:
            c["no_gt_within_0.1"] += 1
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True, choices=["V400", "confirm800"])
    ap.add_argument("--report", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        raise FileExistsError(a.out)
    rep = json.load(open(a.report))
    gtm = json.load(open(f"{BASE}/results/iter_010/manifests/gt_manifest.json"))
    ids = json.load(open(f"{BASE}/{IDS[a.split]}"))
    if rep["n_ids"] != len(ids):
        raise ValueError("report n_ids differs (D24 report is not verified here)")
    gt = {i: [b["yxyx_norm"] for b in gtm[i]["boxes"]] for i in ids}
    cat = {i: gtm[i]["category"] for i in ids}
    pos = [i for i in ids if cat[i] == "opacity"]
    sft = {}
    for s, d in SFTDIR[a.split].items():
        recs = {}
        for fn in sorted(os.listdir(f"{BASE}/{d}")):
            if fn.startswith("gen_worker") and fn.endswith(".jsonl"):
                for ln in open(f"{BASE}/{d}/{fn}"):
                    r = json.loads(ln)
                    recs[r["id"]] = r
        sft[s] = {}
        for i in ids:
            p = PA.parse_response(recs[i]["suffix_text_raw"], recs[i]["ended_eos"])
            sft[s][i] = (p["status"], p["boxes"] if p["status"] in PA.VALID else [])
    out = {"mismatches": [], "n_compared": 0}

    def cmp(name, new, old):
        out["n_compared"] += 1
        ok = (abs(new - old) <= 1e-8) if isinstance(new, float) or isinstance(old, float) else new == old
        if not ok:
            out["mismatches"].append({"name": name, "independent": new, "report": old})

    def model_numbers(preds):
        """preds {id: boxes} -> 독립 계산 표."""
        f3, f5, tp3, tp5, ngt = [], [], 0, 0, 0
        for i in pos:
            p3, p5 = len(pairs(preds[i], gt[i], 0.3)), len(pairs(preds[i], gt[i], 0.5))
            f3.append(f1(p3, len(preds[i]), len(gt[i]))); f5.append(f1(p5, len(preds[i]), len(gt[i])))
            tp3 += p3; tp5 += p5; ngt += len(gt[i])
        fp = {}
        for name, sub in (("all", ids), *[(c, [i for i in ids if cat[i] == c]) for c in ("opacity", "normal", "not_normal_no_opacity")]):
            fp[name] = {}
            for t in (0.3, 0.5):
                tot = {"competes_for_matched_gt": 0, "near_miss_0.1_to_thr": 0, "no_gt_within_0.1": 0}
                for i in sub:
                    for k, v in fp_cats(preds[i], gt[i], t).items():
                        tot[k] += v
                fp[name][t] = tot
        return {"f1@0.3": sum(f3) / len(f3), "f1@0.5": sum(f5) / len(f5), "tp@0.3": tp3, "tp@0.5": tp5, "n_gt": ngt, "fp": fp}

    def check_table(tag, ind, tab):
        cmp(f"{tag} f1@0.3", ind["f1@0.3"], tab["f1@0.3"])
        cmp(f"{tag} f1@0.5", ind["f1@0.5"], tab["f1@0.5"])
        cmp(f"{tag} tp@0.3", ind["tp@0.3"], tab["lesion@0.3"]["tp"])
        cmp(f"{tag} tp@0.5", ind["tp@0.5"], tab["lesion@0.5"]["tp"])
        cmp(f"{tag} n_gt", ind["n_gt"], tab["lesion@0.3"]["n_gt"])
        for name, blk in ind["fp"].items():
            rn = "all800" if name == "all" and len(ids) == 800 else name
            for t, c in blk.items():
                rc = tab["fp"][rn][f"iou{t}"]
                for k, v in c.items():
                    cmp(f"{tag} fp {rn} iou{t} {k}", v, rc[k])
                cmp(f"{tag} fp {rn} iou{t} total", sum(c.values()), rc["n_fp_total"])

    for s in sft:
        check_table(f"sft{s}", model_numbers({i: sft[s][i][1] for i in ids}), rep["tables"][f"sft{s}"])
    for d in (17, 29):
        raw = json.load(open(f"{BASE}/{RAWDIR[a.split][d]}/raw_preds.json"))
        allc = {i: [(to_norm(b, *raw[i]["img_hw"]), s_) for b, s_, l in zip(raw[i]["boxes_xyxy_px"], raw[i]["scores"], raw[i]["labels"])] for i in ids}
        sel = json.load(open(SEL[d]))
        ops = {"selected": sel["selected"]["threshold"], **{f"fp_budget_{b}": r["threshold"] for b, r in sel["fp_budgets"].items() if r}}
        for opn, thr in ops.items():
            key = f"det{d}__{opn}"
            unit = rep["detector"][key]
            cmp(f"{key} threshold", thr, unit["threshold"])
            selb = {i: [b for b, s_ in allc[i] if s_ >= thr] for i in ids}
            check_table(key, model_numbers(selb), unit["table"])
            # 상보성 / 분해 / R / pair
            for s in sft:
                blk = unit["vs_sft"][f"sft{s}"]
                for t in (0.3, 0.5):
                    cnt = {"both_hit": 0, "detector_only": 0, "sft_only": 0, "both_miss": 0}
                    cats = {c: 0 for c in ("matching_competition", "threshold_excluded", "adjacent_localization_error", "no_stored_candidate_coverage")}
                    r_num = 0
                    for i in pos:
                        dh, sh = set(pairs(selb[i], gt[i], t)), set(pairs(sft[s][i][1], gt[i], t))
                        for gi, g in enumerate(gt[i]):
                            k = ("both_hit" if gi in dh and gi in sh else "detector_only" if gi in dh else "sft_only" if gi in sh else "both_miss")
                            cnt[k] += 1
                            if k == "sft_only":
                                if any(iou(b, g) >= t for b in selb[i]):
                                    c = "matching_competition"
                                else:
                                    m = max((iou(b, g) for b, _ in allc[i]), default=0.0)
                                    c = "threshold_excluded" if m >= t else "adjacent_localization_error" if m >= 0.1 else "no_stored_candidate_coverage"
                                cats[c] += 1
                                r_num += c in ("adjacent_localization_error", "no_stored_candidate_coverage")
                    for k, v in cnt.items():
                        cmp(f"{key} sft{s} iou{t} {k}", v, blk["complementarity"][f"iou{t}"][k])
                    for k, v in cats.items():
                        cmp(f"{key} sft{s} iou{t} cat {k}", v, blk["decomposition"][f"iou{t}"]["category_counts"][k])
                    cmp(f"{key} sft{s} iou{t} r_numerator", r_num, blk["decomposition"][f"iou{t}"]["r_numerator"])
            # pair 표
            for model, pr in [("detector", selb)] + [(f"sft{s}", {i: sft[s][i][1] for i in ids}) for s in sft]:
                n = p05 = rem = 0
                for i in pos:
                    p3 = pairs(pr[i], gt[i], 0.3)
                    h5 = set(pairs(pr[i], gt[i], 0.5))
                    for gi, pi in p3.items():
                        n += 1
                        p05 += iou(pr[i][pi], gt[i][gi]) >= 0.5
                        rem += gi in h5
                sm = unit["pair_summary"][model]
                cmp(f"{key} {model} pair n", n, sm["n_pairs_iou0.3"])
                cmp(f"{key} {model} pair pass0.5 rate", p05 / n, sm["pair_pass_iou0.5_rate"])
                cmp(f"{key} {model} rematch rate", rem / n, sm["gt_hit_by_independent_rematch_0.5_rate"])
    out["pass"] = not out["mismatches"]
    print(json.dumps({"n_compared": out["n_compared"], "n_mismatch": len(out["mismatches"]), "pass": out["pass"]}))
    tmp = a.out + ".tmp"
    json.dump(out, open(tmp, "w"), indent=1)
    os.link(tmp, a.out)
    os.unlink(tmp)
    sys.exit(0 if out["pass"] else 1)


if __name__ == "__main__":
    main()
