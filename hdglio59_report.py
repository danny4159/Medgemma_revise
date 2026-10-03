"""iter_059: 완료된 D6 paired timing(results/iter_059/timing/pair_*.json)과 실패 attempt를 집계한다. CPU only.
python hdglio59_report.py OUT.json
- loading 포함 비용(주): 6개 HD subprocess wall 합 / 6개 U8 subprocess wall 합.
- steady-state(보조, 동일 실행 내 직접 event): U8 = pipeline_end-pipeline_start, HD = (pipeline_end-pipeline_start)-(model load 구간).
- 실패 attempt 비용은 별도 보존. 유리한 loading 조건·block 선택 없음. CI 없음(소표본, 방향 일관성만 기록).
"""
import glob
import json
import sys

import hdglio59_common as C

BASE = "results/iter_059/timing"


def run_stats(r):
    s = json.load(open(f"{r['dir']}/summary.json"))
    ev = {x["event"]: x["t"] for x in s["events"] if "case" not in x}
    ps = ev["proc_start"]
    load = ev["load_model_end"] - ev["load_model_start"]
    pipe = ev["pipeline_end"] - ev["pipeline_start"]
    steady = pipe - load if r["kind"] == "HD" else pipe  # HD: load 구간이 pipeline 내부, U8: pipeline 이전
    return {"kind": r["kind"], "wall_s": r["wall_s"], "startup_s": ps - r["parent_start_epoch"], "load_model_s": load, "pipeline_span_s": pipe,
            "steady_s": steady, "tail_s": r["parent_end_epoch"] - ev["pipeline_end"], "peak_reserved_MiB": r["peak_reserved_MiB"],
            "physical_gpu": r["physical_gpu"], "per_case_saved": [(x["case"], x["t"] - ev["pipeline_start"]) for x in s["events"] if x["event"] == "answer_saved"]}


def main():
    pairs = [json.load(open(f)) for f in sorted(glob.glob(f"{BASE}/pair_b*_o*.json"))]
    if len(pairs) != 6:
        raise C.TechError(f"expected 6 complete pairs, got {len(pairs)}")
    rows = []
    for p in pairs:
        st = {k: run_stats(v) for k, v in p["runs"].items()}
        rows.append({"block": p["block"], "order": p["order"], "attempt": p["attempt"], "gpu": p["logical_gpu"], "cases": p["cases"],
                     "HD": st["HD"], "U8": st["U8"], "ratio_wall": st["HD"]["wall_s"] / st["U8"]["wall_s"],
                     "ratio_steady": st["HD"]["steady_s"] / st["U8"]["steady_s"]})
    sum_hd = sum(r["HD"]["wall_s"] for r in rows)
    sum_u8 = sum(r["U8"]["wall_s"] for r in rows)
    sh = sum(r["HD"]["steady_s"] for r in rows)
    su = sum(r["U8"]["steady_s"] for r in rows)
    # 실패 attempt 비용
    failed = []
    for f in sorted(glob.glob(f"{BASE}/attempt_b*_o*_a*.json")):
        a = json.load(open(f))
        if not a["complete"]:
            failed.append({"file": f, "block": a["block"], "order": a["order"], "attempt": a["attempt"],
                           "runs": {k: {"wall_s": v["wall_s"], "rc": v["rc"], "error": v.get("error")} for k, v in a["runs"].items()}})
    ratios = [r["ratio_wall"] for r in rows]
    sr = [r["ratio_steady"] for r in rows]
    rep = {"n_pairs": len(rows), "n_hd_volumes": 2 * len(rows), "n_u8_slab_requests": 12 * len(rows),
           "loading_included": {"sum_hd_wall_s": sum_hd, "sum_u8_wall_s": sum_u8, "ratio_hd_over_u8": sum_hd / sum_u8,
                                "block_ratio_min": min(ratios), "block_ratio_max": max(ratios), "all_blocks_le_1": all(x <= 1 for x in ratios)},
           "steady_state": {"sum_hd_s": sh, "sum_u8_s": su, "ratio_hd_over_u8": sh / su, "block_ratio_min": min(sr), "block_ratio_max": max(sr),
                            "all_blocks_le_1": all(x <= 1 for x in sr)},
           "by_order": {o: {"ratio_wall": sum(r["HD"]["wall_s"] for r in rows if r["order"] == o) / sum(r["U8"]["wall_s"] for r in rows if r["order"] == o)}
                        for o in sorted({r["order"] for r in rows})},
           "per_case_hd_wall_s": sum_hd / (2 * len(rows)), "per_case_u8_wall_s": sum_u8 / (2 * len(rows)),
           "failed_attempts": failed, "rows": rows,
           "note": "loading 포함 = 외부 subprocess 전체 wall(import·모델 load 포함). steady = 동일 실행 내 직접 event. HD는 4 sequence 전체 volume, U8는 FLAIR 구간당 8장이라 정보 조건이 다르다."}
    C.atomic_json(sys.argv[1], rep)
    print(json.dumps({k: v for k, v in rep.items() if k not in ("rows",)}, indent=1, default=str))


if __name__ == "__main__":
    main()
