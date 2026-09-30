"""D24에서 retrieval 4개 설정을 비교하고 하나를 잠근다 (V96은 보지 않는다). 동률: k=1 -> word 순.
python pg43_select_retrieval.py --out results/iter_043/retrieval/selection.json
"""
import argparse
import json
import os
import sys

import pg43_retrieval as R
import pg43_prep as PREP


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("output exists")
    mp = "results/iter_043/data/manifest_private.json"
    man = json.load(open(mp))
    idx = R.build(man)
    res = {}
    for s in R.SETTINGS:
        pred = R.predictions(idx, man["D24"], s)
        m3, vals3 = R.patient_mean_f1(pred, man["D24"], 0.3)
        m5, _ = R.patient_mean_f1(pred, man["D24"], 0.5)
        res[f"{s[0]}_k{s[1]}"] = {"f1_03_D24": m3, "f1_05_D24": m5, "per_patient_f1_03": vals3}
    best = max(R.TIE_ORDER[::-1], key=lambda s: 0)  # placeholder to keep TIE_ORDER referenced
    top = max(v["f1_03_D24"] for v in res.values())
    cands = [s for s in R.TIE_ORDER if abs(res[f"{s[0]}_k{s[1]}"]["f1_03_D24"] - top) < 1e-12]
    chosen = cands[0]
    out = {"chosen": {"kind": chosen[0], "k": chosen[1]}, "scores": {k: {kk: vv for kk, vv in v.items() if kk != "per_patient_f1_03"} for k, v in res.items()},
           "per_patient_f1_03": {k: v["per_patient_f1_03"] for k, v in res.items()},
           "selection_rule": "argmax mean patient F1@0.3 on D24; ties -> k=1 first, word first",
           "manifest_sha256": PREP.fsha(mp), "retrieval_source_sha256": PREP.fsha("pg43_retrieval.py"),
           "select_source_sha256": PREP.fsha("pg43_select_retrieval.py"), "V96_not_used": True}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(out, open(a.out, "x"), indent=1)
    print(json.dumps({"chosen": out["chosen"], "scores": out["scores"]}, indent=1))


if __name__ == "__main__":
    main()
