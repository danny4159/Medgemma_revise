"""iter_114 MG 개발 입력(DEV MSPC 47개)에서 worker/batch 구성 비교: 출력 정합성(박스·점수 최대 차이)·wall·peak 메모리. test 입력은 쓰지 않는다."""
import json
import sys
from pathlib import Path

import nr114_mg as N


def info(run, nw):
    d = N.R114 / "mg" / run
    recs, _ = N.verify_all(d, "DEV", "MSPC", nw)
    launch = json.loads(next(iter(sorted(d.glob("launch_*.json")))).read_text())
    ev = []
    for k in range(nw):
        ev += [json.loads(l) for l in (d / f"executions{k}.jsonl").read_text().splitlines() if l]
    ends = [e for e in ev if e["event"] == "end"]
    starts = [e for e in ev if e["event"] == "start"]
    return {r["item_key"]: r for r in recs}, {
        "launcher_wall_s": launch["wall_s"], "gen_wall_s_max": max(e["wall_s"] for e in ends), "model_load_s_max": max(e["load_s"] for e in starts),
        "peak_reserved_gb_max": max(e["peak_reserved_gb"] for e in ends), "peak_alloc_gb_max": max(e["peak_alloc_gb"] for e in ends),
        "gpus": launch["mapping"], "items_per_s_generation": len(recs) / max(e["wall_s"] for e in ends)}


def main():
    cfgs = {"w1b4": ("DEV_MSPC_w1b4", 1), "w1b8": ("DEV_MSPC_w1b8", 1), "w2b4": ("DEV_MSPC_w2b4", 2)}
    data = {k: info(*v) for k, v in cfgs.items()}
    base = data["w1b4"][0]
    out = {}
    for k, (recs, meta) in data.items():
        mb = ms = 0.0
        nb = 0
        for key, r in recs.items():
            a, b = r["detection"], base[key]["detection"]
            nb += int(len(a["boxes_orig_xyxy"]) != len(b["boxes_orig_xyxy"]))
            for (s1, b1), (s2, b2) in zip(sorted(zip(a["scores"], a["boxes_orig_xyxy"]), reverse=True), sorted(zip(b["scores"], b["boxes_orig_xyxy"]), reverse=True)):
                ms = max(ms, abs(s1 - s2))
                mb = max(mb, max(abs(x - y) for x, y in zip(b1, b2)))
        out[k] = {**meta, "vs_w1b4": {"n_count_mismatch": nb, "max_box_diff": mb, "max_score_diff": ms}}
    p = N.R114 / "dev" / "mg_config_compare.json"
    with p.open("x") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    sys.exit(main())
