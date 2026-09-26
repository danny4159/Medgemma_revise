"""1-worker vs 2-worker 생성 pilot 비교 요약. 사용: python -m rsna_diag.gen_compare W1_DIR W2_DIR OUT"""
import glob
import json
import sys


def load(d):
    out = {}
    for f in glob.glob(f"{d}/gen_worker*.jsonl"):
        for line in open(f):
            r = json.loads(line)
            out[r["id"]] = r
    return out


def peak(d):
    m = 0
    for line in open(f"{d}/resource_log.jsonl"):
        for g in json.loads(line)["gpus"]:
            m = max(m, g["mem_used_mib"])
    return m


def main():
    d1, d2, out = sys.argv[1:4]
    a, b = load(d1), load(d2)
    w1, w2 = (json.load(open(f"{d}/last_run.json"))["wall_s"] for d in (d1, d2))
    res = {"n_requests": len(a), "w1_wall_s": w1, "w2_wall_s": w2, "req_per_min_w1": len(a) / w1 * 60, "req_per_min_w2": len(b) / w2 * 60,
           "greedy_token_identical": sum(a[k]["suffix_ids"] == b[k]["suffix_ids"] for k in a if k in b), "id_set_mismatch": len(set(a) ^ set(b)),
           "gpu_peak_used_mib_w1": peak(d1), "gpu_peak_used_mib_w2": peak(d2), "worker_peak_alloc_gb_max_w2": max(r["peak_mem_alloc_gb_max"] for r in b.values()),
           "max_output_tokens_w2": max(r["n_output_tokens"] for r in b.values()), "all_eos_w2": all(r["ended_eos"] for r in b.values())}
    json.dump(res, open(out, "w"), indent=1)
    print(res)


if __name__ == "__main__":
    main()
