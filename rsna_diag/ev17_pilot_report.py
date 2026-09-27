"""iter_017 D12 동작 확인·worker 구성 비교 요약. 정확도는 보지 않고 형식·정합성·처리량·메모리만 기록한다.
사용: python -m rsna_diag.ev17_pilot_report A_ROOT B_ROOT STAGE OUT_JSON
"""
import collections
import json
import sys

from . import qa_pilot, qa_spec as S


def peak_used(stage_dir):
    peak = {}
    for ln in open(f"{stage_dir}/resource_log.jsonl"):
        d = json.loads(ln)
        for g, v in d["gpus"].items():
            if isinstance(v, dict) and "used_mib" in v:
                peak[g] = max(peak.get(g, 0), v["used_mib"])
    return peak


def format_table(stage_dir, requests):
    rows = {}
    for ln in open(requests):
        r = json.loads(ln)
        rows[r["request_id"]] = r
    recs = qa_pilot.load(stage_dir)
    st = collections.Counter()
    for k, x in recs.items():
        row = rows[k]
        s, _a, _c = S.parse_semantic(row["target"], "plain", x["suffix_text_raw"], x["ended_eos"])
        st[f"{row['condition']}/{row['target']}/{s}"] += 1
    caps = collections.Counter(x["final_cap"] for x in recs.values())
    return {"status": dict(sorted(st.items())), "max_output_tokens": max(x["n_output_tokens"] for x in recs.values()), "final_caps": dict(caps),
            "max_request_s": max(x["runtime_s_total"] for x in recs.values()), "peak_alloc_gb": max(x["peak_mem_alloc_gb_max"] for x in recs.values())}


if __name__ == "__main__":
    a, b, stage, out = sys.argv[1:5]
    r = qa_pilot.compare(a, b, stage, ("M0",))
    r["gpu_peak_used_mib"] = {"A": peak_used(f"{a}/{stage}__M0"), "B": peak_used(f"{b}/{stage}__M0")}
    r["format"] = {"A": format_table(f"{a}/{stage}__M0", f"results/iter_017/requests/{stage}__M0.jsonl"),
                   "B": format_table(f"{b}/{stage}__M0", f"results/iter_017/requests/{stage}__M0.jsonl")}
    json.dump(r, open(out, "w"), indent=1)
    print(json.dumps({"totals": r["totals"], "identical": r["all_identical"], "gpu_peak_used_mib": r["gpu_peak_used_mib"], "M0": r["ckpts"]["M0"]}, indent=1))
    print(json.dumps(r["format"]["B"], indent=1))
