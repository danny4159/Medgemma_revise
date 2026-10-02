"""iter_048 timing 독립 재계산 (pg48_time_report를 호출하지 않는 별도 구현; 원시 timing 파일에서 device-seconds union, throughput, p95, 비율의 t(5) 95% CI를 다시 계산).
python pg48_timing_verify.py --report results/iter_048/timing/timing_report.json --out results/iter_048/timing/timing_verify.json
"""
import argparse
import glob
import json
import os
import sys

import numpy as np

ROOT = "results/iter_048/timing"


def union(iv):
    iv = sorted(iv)
    tot, cs, ce = 0.0, None, None
    for s, e in iv:
        if ce is None or s > ce:
            if ce is not None:
                tot += ce - cs
            cs, ce = s, e
        else:
            ce = max(ce, e)
    return tot + (ce - cs if ce is not None else 0.0)


def rows(p):
    return [json.loads(l) for l in open(p, "rb").read().split(b"\n")[:-1] if l.strip()]


def block(k, att, s):
    d = f"{ROOT}/block{k}_a{att}_{s}"
    comp = json.load(open(f"{d}/completion.json"))
    t_go = comp["t_go"]
    dn = [json.load(open(p))["t"] for p in glob.glob(f"{d}/barrier/done.*")]
    wall = max(dn) - t_go
    mapping = {int(k_): v for k_, v in comp["mapping"].items()}
    if s in ("E", "J"):
        recs = [r for f in sorted(glob.glob(f"{d}/ctime_worker*.jsonl")) for r in rows(f)]
        per = {}
        for r in recs:
            per[r["patient"]] = (r["worker"], r["t_patient_dispatch"], r["t_patient_done"])
        iv = {}
        for w, a, b in per.values():
            iv.setdefault(mapping[w], set()).add((a, b))
        dev = sum(union(v) for v in iv.values())
        lat = [b - a for _, a, b in per.values()]
    else:
        recs = [r for f in sorted(glob.glob(f"{d}/raw_worker*.jsonl")) for r in rows(f)]
        iv = {}
        for r in recs:
            iv.setdefault(mapping[r["worker"]], []).append((r["t_dispatch"], r["t_done"]))
        dev = sum(union(v) for v in iv.values())
        pp = {}
        for r in recs:
            a, b = pp.get(r["patient"], (1e30, 0.0))
            pp[r["patient"]] = (min(a, r["t_dispatch"]), max(b, r["t_orig_done"]))
        lat = [b - a for a, b in pp.values()]
        assert len(pp) == 96
    return {"dev": dev, "thr": 96 / wall * 60, "p95": float(np.percentile(lat, 95)), "wall": wall}


def ratio(num, den, key):
    lr = np.log([num[k][key] / den[k][key] for k in range(1, 7)])
    m, se = lr.mean(), lr.std(ddof=1) / np.sqrt(6)
    t = 2.5705818366147395  # t(0.975, df=5) (scipy 미설치; 표준값)
    return [float(np.exp(m)), float(np.exp(m - t * se)), float(np.exp(m + t * se))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("exists")
    rep = json.load(open(a.report))
    att = rep["attempts_used"]
    B = {s: {k: block(k, att[k - 1], s) for k in range(1, 7)} for s in ("E", "J", "A")}
    res, ok, mx = {}, True, 0.0
    for num, den in (("J", "E"), ("A", "E"), ("J", "A")):
        for key, rk in (("dev", "device_seconds"), ("thr", "throughput"), ("p95", "p95_latency")):
            mine = ratio(B[num], B[den], key)
            th = rep["ratios"][f"{num}/{den}"][rk]
            d = max(abs(mine[0] - th["ratio"]), abs(mine[1] - th["lo95"]), abs(mine[2] - th["hi95"]))
            res[f"{num}/{den}:{rk}"] = {"mine": mine, "max_abs_diff_vs_report": d}
            mx = max(mx, d)
    # 블록별 개별 값 대조
    bd = 0.0
    for s in B:
        for k in range(1, 7):
            r = rep["blocks"][s][str(k)]
            bd = max(bd, abs(B[s][k]["dev"] - r["device_seconds"]), abs(B[s][k]["thr"] - r["throughput_patients_per_min"]), abs(B[s][k]["p95"] - r["p95_latency_s"]))
    out = {"ratios": res, "max_ratio_diff": mx, "max_block_value_diff": bd, "ok": bool(mx < 1e-9 and bd < 1e-9), "blocks": {s: {str(k): v for k, v in B[s].items()} for s in B}}
    json.dump(out, open(a.out, "w"), indent=1)
    print(json.dumps({k: out[k] for k in ("max_ratio_diff", "max_block_value_diff", "ok")}))


if __name__ == "__main__":
    main()
