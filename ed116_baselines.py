"""iter_116 생성 없는 단순 대조(K/B/G/M) 기술. 잠금된 ed116_eval/ed116_spec를 그대로 사용한다 (N/E/R/T/S는 MAIN 생성이 있어야 계산 가능).
사용: python ed116_baselines.py <출력 json> ('x' 모드)"""
import json
import os
import sys

import ed116_eval as EV

PROV = "results/iter_116/provenance"
POL = ("K", "B", "G", "M")
CATS = ("opacity", "normal", "not_normal_no_opacity")


def main(out):
    rows = dict((r["id"], r) for r in json.load(open(f"{PROV}/ledger_nogt.json"))["rows"])
    gt = json.load(open(f"{PROV}/gt.json"))
    sel = json.load(open("results/iter_116/lock/selection.json"))
    res = dict(note="생성 없는 저장 출력 기반 단순 대조(K/B/G/M). N/E/R/T/S는 MAIN 미생성으로 계산하지 않음.")
    for g, ids in (("mismatch", sel["mismatch"]), ("control", sel["control"])):
        ps = [EV.make_patient(rows[i], gt[i], {}) for i in ids]
        pt = [EV.point_scalars(p) for p in ps]
        d = dict(n=len(ps))
        for name in ("correct", "correction", "harm"):
            d[name] = dict((q, sum(x[f"{name}_{q}"] for x in pt)) for q in POL)
        d["joint03"] = dict((q, sum(x[f"joint03_{q}"] for x in pt)) for q in ("K", "B"))
        d["joint05"] = dict((q, sum(x[f"joint05_{q}"] for x in pt)) for q in ("K", "B"))
        d["by_category_correct"] = {}
        for c in CATS:
            k_ = [k for k, p in enumerate(ps) if p["cat"] == c]
            d["by_category_correct"][c] = dict([("n", len(k_))] + [(q, sum(pt[k][f"correct_{q}"] for k in k_)) for q in POL])
        res[g] = d
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(res, open(out, "x"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
