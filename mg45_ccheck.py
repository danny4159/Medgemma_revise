"""iter_045: C timing block 출력의 token 정합성(기존 iter_040 C 192 출력 대비)·EOS·입력 hash·자원 요약.

python mg45_ccheck.py DIR [DIR ...]   (결과는 stdout JSON; 저장은 호출자가 필요 시 리다이렉트하지 않고 timing 리포트가 읽는다)
"""
import glob
import json
import sys

import numpy as np

OLD = "results/iter_040/gen/C"


def old_records():
    old = {}
    for f in glob.glob(OLD + "/gen_worker*.jsonl"):
        for l in open(f):
            r = json.loads(l)
            old[r["request_id"]] = r
    return old


def check(d, old=None):
    old = old or old_records()
    recs = []
    for f in sorted(glob.glob(d + "/ctime_worker*.jsonl")):
        recs += [json.loads(l) for l in open(f)]
    mm = [r["request_id"] for r in recs if r["suffix_ids"] != old[r["request_id"]]["suffix_ids"]]
    c = json.load(open(d + "/completion.json"))
    lat = {}
    for r in recs:
        lat[r["patient"]] = r["t_patient_done"] - r["t_patient_dispatch"]
    lv = np.array(list(lat.values()))
    rl = [json.loads(x) for x in open(d + "/resource_log.jsonl")]
    gmax = {}
    for r in rl:
        for g in r["gpu"]:
            i, used, _ = [int(x) for x in g.split(",")]
            gmax[i] = max(gmax.get(i, 0), used)
    return {"dir": d, "n": len(recs), "token_mismatch": len(mm), "mismatch_ids": mm[:5], "all_eos": all(r["ended_eos"] for r in recs),
            "input_pixel_equal": all(r["input_pixel_sha256"] == old[r["request_id"]]["input_pixel_sha256"] for r in recs),
            "n_retry": sum(len(r["attempts"]) > 1 for r in recs),
            "workload_wall_s": c.get("workload_wall_s"), "device_seconds_union": c.get("device_seconds_union"),
            "patients_per_min": 96 / c["workload_wall_s"] * 60 if c.get("workload_wall_s") else None,
            "latency_s": {"mean": float(lv.mean()), "p50": float(np.percentile(lv, 50)), "p95": float(np.percentile(lv, 95))},
            "peak_alloc_gb_max": c.get("peak_alloc_gb_max"), "peak_reserved_gb_max": c.get("peak_reserved_gb_max"),
            "gpu_used_mib_max_sampled": gmax, "cold_load_s": c.get("cold_load_s"), "mapping": c["mapping"]}


if __name__ == "__main__":
    old = old_records()
    for d in sys.argv[1:]:
        print(json.dumps(check(d, old), indent=1))
