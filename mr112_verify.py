"""iter_112 독립 재계산: mr112_eval.py / rsna_diag.metrics를 import하지 않고 원시 scores·manifest·gt에서 주요 수치와 bootstrap CI를 다시 계산한다.
(같은 규칙·같은 seed 고정, 구현은 numpy lexsort 기반.) 결과 파일과 비교해 PASS/FAIL을 기록한다."""
import json
import math
import sys

import numpy as np

import os
D = os.environ.get("MR112_DIR", "results/iter_112")


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u > 0 else 0.0


def main(report_path, out_path, d=None):
    global D
    D = d or D
    man =json.load(open(f"{D}/data/manifest.json"))
    gt = json.load(open(f"{D}/data/gt.json"))
    sc = {}
    for l in open(f"{D}/scores/main_scores.jsonl"):
        r = json.loads(l)
        assert r["request_id"] not in sc, "중복 record"
        sc[r["request_id"]] = r["mean_logprob"]
    rows = {r["id"]: r for r in man["rows"]}
    full = {q["id"]: sc[q["request_id"]] for q in man["requests"] if q["group"] == "main" and q["kind"] == "full"}
    pid, di, conf, reg, fl, err = [], [], [], [], [], []
    for q in man["requests"]:
        if q["group"] != "main" or q["kind"] != "region":
            continue
        b = [x for x in rows[q["id"]]["boxes"] if x["det_index"] == q["det_index"]][0]
        m = max([iou(b["xyxy_px"], g) for g in gt[q["id"]]["boxes_xyxy_px"]] or [0.0])
        pid.append(q["id"]); di.append(q["det_index"]); conf.append(b["score"]); reg.append(sc[q["request_id"]]); fl.append(full[q["id"]])
        err.append(m < 0.3)
    N = len(pid)
    uniq = sorted(set(pid))
    pidx = np.array([uniq.index(p) for p in pid])
    pstr = np.array([int(p.split("_")[1]) for p in pid])  # id 숫자부분: 사전식 정렬과 동일 순서(고정 자릿수)
    di = np.array(di); conf = np.array(conf); reg = np.array(reg); fl = np.array(fl); err = np.array(err)

    def cap(sel, K, which):
        s, c = conf[sel], None
        keys = {"conf": (di[sel], pstr[sel], conf[sel]),
                "region": (di[sel], pstr[sel], conf[sel], reg[sel]),
                "full": (di[sel], pstr[sel], conf[sel], fl[sel])}[which]
        o = np.lexsort(keys)  # 마지막 key가 1차
        return int(err[sel][o[:K]].sum()), o[:K]

    allidx = np.arange(N)
    K = math.ceil(0.25 * N)
    c_conf, _ = cap(allidx, K, "conf")
    c_reg, _ = cap(allidx, K, "region")
    c_full, _ = cap(allidx, K, "full")
    got = dict(N=N, K=K, n_err=int(err.sum()), captured_conf=c_conf, captured_region=c_reg, captured_full=c_full,
               diff_region_conf=(c_reg - c_conf) / N, diff_region_full=(c_reg - c_full) / N)
    # bootstrap (같은 rng 호출 순서)
    rng = np.random.default_rng(112017)
    by = {u: np.where(pidx == i)[0] for i, u in enumerate(uniq)}
    d1, d2 = [], []
    for _ in range(10000):
        pick = rng.integers(0, len(uniq), len(uniq))
        sel = np.concatenate([by[uniq[k]] for k in pick])
        copy = np.concatenate([np.full(len(by[uniq[k]]), c) for c, k in enumerate(pick)])
        n = len(sel)
        Kb = math.ceil(0.25 * n)
        res = []
        for which in ("conf", "region", "full"):
            base = {"conf": (di[sel], pstr[sel], conf[sel]), "region": (di[sel], pstr[sel], conf[sel], reg[sel]),
                    "full": (di[sel], pstr[sel], conf[sel], fl[sel])}[which]
            o = np.lexsort((copy,) + base)
            res.append(int(err[sel][o[:Kb]].sum()))
        d1.append((res[1] - res[0]) / n)
        d2.append((res[1] - res[2]) / n)
    got["diff_region_conf_ci"] = [float(np.percentile(d1, 2.5)), float(np.percentile(d1, 97.5))]
    got["diff_region_full_ci"] = [float(np.percentile(d2, 2.5)), float(np.percentile(d2, 97.5))]
    rep = json.load(open(report_path))
    p, b = rep["primary"], rep["boot"]
    chk = {
        "N/K/n_err": (p["N"], p["K"], p["n_err"]) == (got["N"], got["K"], got["n_err"]),
        "captured": (p["captured_conf"], p["captured_region"], p["captured_full"]) == (c_conf, c_reg, c_full),
        "diffs": abs(p["diff_region_conf"] - got["diff_region_conf"]) < 1e-12 and abs(p["diff_region_full"] - got["diff_region_full"]) < 1e-12,
        "ci_conf": max(abs(x - y) for x, y in zip(b["diff_region_conf_ci"], got["diff_region_conf_ci"])) < 1e-12,
        "ci_full": max(abs(x - y) for x, y in zip(b["diff_region_full_ci"], got["diff_region_full_ci"])) < 1e-12,
    }
    json.dump(dict(independent=got, checks=chk, all_pass=all(chk.values())), open(out_path, "w"), indent=1)
    print(chk, got)
    sys.exit(0 if all(chk.values()) else 1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
