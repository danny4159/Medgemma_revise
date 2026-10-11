"""iter_111 독립 재계산. 원 출력(labels.json, det raw_preds.json, SFT 원 worker 파일, Q_O 원 worker 파일)에서 출발하고
ev111_core/ev109_extract/rsna_diag.metrics를 import하지 않는다(bare Yes/No 외의 비정형 응답만 저장 추출값과 대조).
결과: results/iter_111/eval/verify.json (새 파일)."""
import glob
import itertools
import json
import os
import re
import sys

import numpy as np

R = "results"
OUT = f"{R}/iter_111/eval/verify_v2.json"


def iou(a, b):
    y0, x0, y1, x1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    i = max(0, y1 - y0) * max(0, x1 - x0)
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u > 0 else 0.0


def tp_max(pred, gt, thr):
    best = 0
    for r in range(min(len(pred), len(gt)) + 1):
        for gi in itertools.combinations(range(len(gt)), r):
            for pi in itertools.permutations(range(len(pred)), r):
                if all(iou(pred[p], gt[g]) >= thr for g, p in zip(gi, pi)):
                    best = max(best, r)
    return best


def rows(p):
    return [json.loads(x) for x in open(p) if x.strip()]


def main():
    if os.path.exists(OUT):
        sys.exit("exists")
    sets = json.load(open(f"{R}/iter_016/manifests/sets.json"))["E600"]
    labels = json.load(open(f"{R}/iter_016/manifests/labels.json"))
    cat = {i: c for c, v in sets.items() for i in v}
    ids = sorted(cat)
    det = json.load(open(f"{R}/iter_035/confirm800/det17/raw_preds.json"))
    img = {r["id"]: r["image"] for r in rows(f"{R}/iter_016/manifests/infer_manifest.jsonl")}
    from PIL import Image
    # Q_O 원 응답 (record), SFT 원 응답
    O = {}
    for st in ("e180_plain__M0", "e600x_plain__M0"):
        for p in sorted(glob.glob(f"{R}/iter_016/gen/{st}/gen_worker*.jsonl")):
            for r in rows(p):
                if r["target"] == "O":
                    assert r["id"] not in O
                    O[r["id"]] = r["suffix_text_raw"]
    SFT = {}
    for p in sorted(glob.glob(f"{R}/iter_012/confirm_sft_seed17/gen_worker*.jsonl")):
        for r in rows(p):
            if r["prompt_name"] == "concise" and r["id"] in cat:
                SFT[r["id"]] = r["suffix_text_raw"]
    stored = {x["id"]: x for x in json.load(open(f"{R}/iter_111/eval/per_patient.json"))}
    rep = json.load(open(f"{R}/iter_111/eval/report.json"))
    EOT = "<end_of_turn>"
    mism = []
    ans, Y, typ, smax, smin, inS = {}, {}, {}, {}, {}, {}
    nonbare = []
    for i in ids:
        t = O[i]
        m = re.fullmatch(r"\s*(yes|no)\s*\.?\s*", t.replace(EOT, ""), re.I)
        if m:
            a = m.group(1).lower()
        else:
            nonbare.append(i)
            a = stored[i]["ans"]  # 비정형: 저장 추출값 사용(아래에서 원문 출력)
        ans[i] = a
        h, w = Image.open(img[i]).size
        side, top, left = max(h, w), (max(h, w) - h) // 2 if h < w else 0, (max(h, w) - w) // 2 if w < h else 0
        d = det[i]
        boxes, sc = [], []
        for b, s, l in zip(d["boxes_xyxy_px"], d["scores"], d["labels"]):
            if l == 1 and s >= 0.70:
                x0, y0, x1, y1 = b
                boxes.append([(y0 + top) * 1000 / side, (x0 + left) * 1000 / side, (y1 + top) * 1000 / side, (x1 + left) * 1000 / side])
                sc.append(s)
        gt = [b["yxyx_norm"] for b in labels[i]["boxes"]]
        inS[i] = bool(boxes)
        if boxes:
            tp = tp_max(boxes, gt, 0.3)
            ok = (len(gt) == 0 and False) or (len(gt) > 0 and tp == len(gt) == len(boxes))
            Y[i] = not ok
            typ[i] = "correct" if ok else ("neg_claim" if not gt else "pos_location")
            smax[i], smin[i] = max(sc), min(sc)
    S = [i for i in ids if inS[i]]
    res = [i for i in S if ans[i] is not None]
    flagged = [i for i in res if ans[i] == "no"]
    k = len(flagged)

    def conf_found(key, only=None):
        sc = sorted(res, key=lambda i: key[i])
        if k == 0:
            return 0.0
        if k >= len(sc):
            return float(sum(1 for i in sc if Y[i] and (only is None or typ[i] == only)))
        v = key[sc[k - 1]]
        lo = [i for i in sc if key[i] < v]
        tie = [i for i in sc if key[i] == v]
        f = lambda L: sum(1 for i in L if Y[i] and (only is None or typ[i] == only))
        return f(lo) + (k - len(lo)) / len(tie) * f(tie)
    out = dict(n_S=len(S), k=k, n_unres=len(S) - len(res))
    vlm = sum(1 for i in flagged if Y[i])
    out.update(found_vlm=vlm, found_conf=conf_found(smax), found_confmin=conf_found(smin),
               vlm_pos=sum(1 for i in flagged if Y[i] and typ[i] == "pos_location"), conf_pos=conf_found(smax, "pos_location"),
               ep=(vlm - conf_found(smax)) / len(S))
    e = rep["endpoint_point"]
    cmp = []
    for a, b in (("n_S", "n_S"), ("k", "k"), ("n_unres", "n_unres"), ("found_vlm", "found_vlm"), ("found_conf", "found_conf"),
                 ("found_confmin", "found_confmin"), ("vlm_pos", "vlm_pos_location"), ("conf_pos", "conf_pos_location"), ("ep", "ep")):
        cmp.append(dict(name=a, indep=out[a], stored=e[b], ok=abs(out[a] - e[b]) < 1e-9))
    # 환자별 Y·type·답 일치
    pp_bad = [i for i in ids if stored[i]["ans"] != ans[i] or stored[i]["det_nonempty"] != inS[i] or (inS[i] and (stored[i]["Y"] != Y[i] or stored[i]["type"] != typ[i]))]
    # reader/SFT/joint 일부: SFT loc joint at 0.3 전체
    def sft_boxes(t):
        t = t.replace(EOT, "").strip()
        if t == "[]":
            return []
        return [x["box_2d"] for x in json.loads(t)]
    sj = 0
    for i in ids:
        b = sft_boxes(SFT[i])
        gt = [x["yxyx_norm"] for x in labels[i]["boxes"]]
        ok = (len(b) == 0) if not gt else (tp_max(b, gt, 0.3) == len(gt) == len(b))
        sj += ok
    cmp.append(dict(name="sft_loc_joint_n@0.3", indep=sj, stored=rep["systems"]["sft_loc_iou0.3"]["all"]["joint_n"], ok=sj == rep["systems"]["sft_loc_iou0.3"]["all"]["joint_n"]))
    # reader 존재 정확도 (resolved)
    ra = [(ans[i] == "yes") == bool(labels[i]["boxes"]) for i in ids if ans[i] is not None]
    cmp.append(dict(name="reader_existence_acc", indep=float(np.mean(ra)), stored=rep["systems"]["det_indep_iou0.3"]["all"]["existence_acc"],
                    ok=abs(float(np.mean(ra)) - rep["systems"]["det_indep_iou0.3"]["all"]["existence_acc"]) < 1e-12))
    # 독립 부트스트랩 (같은 seed 같은 index 표집)
    rng = np.random.default_rng(11117)
    idx = rng.integers(0, len(ids), size=(10000, len(ids)), dtype=np.int32)
    eps = []
    for b in range(10000):
        samp = [ids[j] for j in idx[b]]
        Sb = [i for i in samp if inS[i]]
        rb = [i for i in Sb if ans[i] is not None]
        kb = sum(1 for i in rb if ans[i] == "no")
        vb = sum(1 for i in rb if ans[i] == "no" and Y[i])
        srt = sorted(rb, key=lambda i: smax[i])
        if kb == 0 or not srt:
            cf = 0.0
        elif kb >= len(srt):
            cf = float(sum(Y[i] for i in srt))
        else:
            v = smax[srt[kb - 1]]
            lo = [i for i in srt if smax[i] < v]
            tie = [i for i in srt if smax[i] == v]
            cf = sum(Y[i] for i in lo) + (kb - len(lo)) / len(tie) * sum(Y[i] for i in tie)
        eps.append((vb - cf) / len(Sb))
    lo, hi = float(np.percentile(eps, 2.5)), float(np.percentile(eps, 97.5))
    cmp.append(dict(name="boot_ci_lo", indep=lo, stored=rep["bootstrap"]["ep"]["ci95"][0], ok=abs(lo - rep["bootstrap"]["ep"]["ci95"][0]) < 1e-12))
    cmp.append(dict(name="boot_ci_hi", indep=hi, stored=rep["bootstrap"]["ep"]["ci95"][1], ok=abs(hi - rep["bootstrap"]["ep"]["ci95"][1]) < 1e-12))
    nb = {i: O[i][:100] for i in nonbare}
    ok = all(c["ok"] for c in cmp) and not pp_bad
    json.dump(dict(all_ok=ok, checks=cmp, per_patient_mismatch=pp_bad, nonbare_reader_responses=nb), open(OUT, "w"), indent=1, ensure_ascii=False)
    print("all_ok", ok, [c["name"] for c in cmp if not c["ok"]], len(pp_bad), len(nonbare))


if __name__ == "__main__":
    main()
