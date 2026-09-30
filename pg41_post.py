"""iter_041 사후(post hoc) 기술 분석: 저장된 V96 출력만 사용, 새 생성 없음. 판정에 쓰지 않는다.
공동 요청 손실이 GT box 개수(단일/복수)와 예측 box 개수에 어떻게 나뉘는지 본다 (인터페이스·개수 설명 vs 위치 설명 구분용 관찰).

python pg41_post.py --config results/iter_041/eval/config_V96.json --out results/iter_041/eval/post_hoc_count_V96.json
"""
import argparse
import collections
import json
import os
import sys

import numpy as np

import pg41_eval as E
import pg39_eval as E39


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("output exists")
    cfg = json.load(open(a.config))
    man = E.load_manifest(cfg["manifest"], cfg["selection_lock"], cfg["subset"])
    out = {"note": "사후 기술 통계(판정 비사용). 문장 단위, F1@0.3, invalid는 0."}
    for m in ("C", "B"):
        d = {k: E.load_verified(s) for k, s in cfg["models"][m].items() if k != "Icost"}
        tab = E.model_tab(d["I"], d["JAB"], d["JBA"], man)
        pids = sorted(tab)
        rows = []
        for p in pids:
            for t in ("qA", "qB"):
                ngt = len(man[p]["gt_boxes_xyxy_norm"][t])
                rows.append({"ngt": ngt, "I": E.sent(tab, p, "I", t), "AB": E.sent(tab, p, "AB", t), "BA": E.sent(tab, p, "BA", t),
                             "npI": tab[p]["I"][t]["scores"][t]["n_pred"], "npAB": tab[p]["AB"]["scores"][t]["n_pred"],
                             "npBA": tab[p]["BA"]["scores"][t]["n_pred"]})
        r = {}
        for name, sel in (("gt_1box", lambda x: x["ngt"] == 1), ("gt_multi", lambda x: x["ngt"] > 1)):
            xs = [x for x in rows if sel(x)]
            r[name] = {"n_sentences": len(xs), "f1": {c: float(np.mean([x[c] for x in xs])) for c in ("I", "AB", "BA")},
                       "mean_pred_boxes": {c: float(np.mean([x["np" + c] for x in xs])) for c in ("I", "AB", "BA")}}
        r["pred_box_count_distribution"] = {c: dict(collections.Counter(x["np" + c] for x in rows)) for c in ("I", "AB", "BA")}
        # 환자 단위: 두 문장 모두 GT 1 box인 환자만의 Δ (개수 요인 통제)
        keep = [i for i, p in enumerate(pids) if all(len(man[p]["gt_boxes_xyxy_norm"][t]) == 1 for t in ("qA", "qB"))]
        X = {c: np.array([E.sc(tab, p, c) for p in pids]) for c in ("I", "AB", "BA")}
        r["patients_both_sentences_single_gt_box"] = {"n": len(keep), "mean_f1": {c: float(X[c][keep].mean()) for c in X},
                                                      "delta_AB_ci975": E39.pci(X["I"][keep], X["AB"][keep], 0.975),
                                                      "delta_BA_ci975": E39.pci(X["I"][keep], X["BA"][keep], 0.975)}
        out[m] = r
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(out, open(a.out, "x"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
