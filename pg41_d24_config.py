"""iter_041 D24 2 worker vs 4 worker 비교 (처리량·GPU 점유·token 정합성·형식). V96 점수는 사용하지 않는다.

python pg41_d24_config.py --out results/iter_041/decisions/d24_worker_config.json
"""
import argparse
import collections
import json
import os
import sys

import pg39_spec as S
import pg41_run as R

REQ = "results/iter_041/requests/requests_D24_C.jsonl"
PROTO = "results/iter_041/protocol/protocol_D24_C.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("output exists")
    res, toks = {}, {}
    for w in (2, 4):
        d = "results/iter_041/gen/D24_C_%dw" % w
        comp = json.load(open(d + "/completion.json"))
        recs = R.verify_completion(d, REQ, PROTO)
        toks[w] = {r["request_id"]: r["suffix_ids"] for r in recs}
        mx = {}
        for l in open(d + "/resource_log.jsonl"):
            for g in json.loads(l)["gpu"]:
                i, u, _ = [x.strip() for x in g.split(",")]
                mx[i] = max(mx.get(i, 0), int(u))
        c = comp["cost"]
        st = collections.Counter("%s|%s" % (r["cond"], S.parse_ids(r["suffix_text_raw"], r["ended_eos"], set(r["targets"]))["status"]) for r in recs)
        res[w] = {"launcher_wall_s": comp["wall_s"], "req_per_min_incl_load": 96 / comp["wall_s"] * 60,
                  "first_start_to_last_end_s": c["first_request_start_to_last_end_s"],
                  "req_per_min_gen_only": 96 / c["first_request_start_to_last_end_s"] * 60,
                  "devsec_generate": c["device_seconds_generate_union"], "devsec_incl_load": c["device_seconds_incl_loading_union"],
                  "peak_gpu_mib": mx, "max_peak_alloc_gb_per_req": max(r["peak_mem_alloc_gb_max"] for r in recs),
                  "max_out_tokens": max(r["n_output_tokens"] for r in recs), "n_retry": c["n_records_with_retry"],
                  "sum_request_wall_s": c["sum_request_wall_s"], "n_eos": sum(r["ended_eos"] for r in recs), "status": dict(st),
                  "free_mib_before": json.load(open(d + "/launch_children.json"))["free_mib_before"]}
    res["n_token_mismatch_2w_vs_4w"] = sum(toks[2][k] != toks[4][k] for k in toks[2])
    res["same_request_set"] = set(toks[2]) == set(toks[4])
    res["speedup_wall_incl_load"] = res[2]["launcher_wall_s"] / res[4]["launcher_wall_s"]
    res["speedup_gen_only"] = res[2]["first_start_to_last_end_s"] / res[4]["first_start_to_last_end_s"]
    res["note"] = "D24 C 96요청(I qA/qB, J-AB, J-BA). 구성 선택은 이 D 처리량·메모리·오류·token 정합성으로만 한다(V96 점수 미사용)."
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(res, open(a.out, "x"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
