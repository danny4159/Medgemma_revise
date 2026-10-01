"""iter_048 timing 보고 (CPU). 6 block x {E,J,A}의 완결성·정상 exit·raw digest를 검증하고 device-seconds / throughput / p95 latency 비율의 block paired t(5) 95% CI를 계산한다.

비용 지표 (block마다, 같은 V96 96환자 전체):
  device_seconds = GPU별 환자(요청) 처리 구간 합집합의 합 (겹침 중복 합산 없음; E/J: 환자 dispatch~완성, A: 요청 dispatch~원본좌표 변환 완료)
  throughput = 96 / barrier(go) 이후 전체 workload wall x 60 (환자/분)
  p95 latency = 환자 첫 dispatch부터 결과 완성까지(service latency)의 p95 (np.percentile 기본 선형 보간)
비율의 CI: block별 log-ratio의 t(5) 95% CI (환자 latency bootstrap으로 대체하지 않는다). 기술 실패 attempt는 원본을 보존하고 ledger에 남긴다.
timing 출력과 고정 정확도 출력 대조(token/box 일치)를 함께 보고한다 (불일치를 무시하지 않는다).
python pg48_time_report.py --attempts 1 1 1 1 1 1 --out results/iter_048/timing/timing_report.json
"""
import argparse
import glob
import hashlib
import json
import os
import sys

import numpy as np

ROOT = "results/iter_048/timing"
GATE = "results/iter_048/decisions/v96_gate.json"
T5 = 2.5705818366147395  # scipy.stats.t.ppf(0.975, 5)


def file_sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def read_jsonl(path):
    return [json.loads(l) for l in open(path, "rb").read().split(b"\n")[:-1] if l.strip()]


def fixed_records(gate):
    import pg43_run as R
    out = {}
    for n in ("E", "J"):
        info = gate["v96_runs"][n]
        recs = R.verify_completion(info["gen_dir"], info["requests"], info["protocol"])
        out[n] = {r["request_id"]: r for r in recs}
    return out


def load_block(k, att, system, fixed, jorder):
    d = os.path.join(ROOT, f"block{k}_a{att}_{system}")
    comp = json.load(open(os.path.join(d, "completion.json")))
    assert all(c == 0 for c in comp["exit_codes"]) and comp.get("complete") and not comp.get("aborted"), f"{d}: not a clean completion"
    assert comp["n_unique"] == comp["n_expected"] == (192 if system != "J" else 96), f"{d}: counts"
    lp_path = os.path.join(d, "launch_protocol.json")
    assert comp["launch_protocol_sha256"] == file_sha(lp_path) if "launch_protocol_sha256" in comp else True
    out = {"dir": d, "device_seconds": None, "workload_wall_s": comp["workload_wall_s"], "cold_load": comp.get("cold_load_s"), "launcher_wall_s_incl_loading": comp["launcher_wall_s_incl_loading"],
           "peak_alloc_gb_max": comp.get("peak_alloc_gb_max"), "peak_reserved_gb_max": comp.get("peak_reserved_gb_max"), "workers": comp["workers"], "mapping": comp["mapping"]}
    if system in ("E", "J"):
        lp = json.load(open(lp_path))
        assert lp["adapter_digest"] == fixed["adapters"][system]["digest"], f"{d}: adapter != selection"
        for fn, sha in comp["worker_file_sha256"].items():
            assert file_sha(os.path.join(d, fn)) == sha, f"{d}: worker file changed"
        recs = []
        for fn in sorted(glob.glob(os.path.join(d, "ctime_worker*.jsonl"))):
            recs += read_jsonl(fn)
        assert len({r["request_id"] for r in recs}) == len(recs)
        out["device_seconds"] = comp["device_seconds_union"]
        by_p = {}
        for r in recs:
            by_p[r["patient"]] = (r["t_patient_dispatch"], r["t_patient_done"])
        assert len(by_p) == 96
        lat = np.array([b - a for a, b in by_p.values()])
        mism = sum(r["suffix_ids"] != fixed["records"][system][r["request_id"]]["suffix_ids"] for r in recs)
        out["token_mismatch_vs_fixed"] = int(mism)
        out["n_compared"] = len(recs)
        out["eos_all"] = all(r["ended_eos"] for r in recs)
        out["n_boxes_total"] = int(sum(len(b) for r in recs for b in r["boxes_orig_xyxy"].values()))
    else:
        for fn, sha in comp["raw_file_sha256"].items():
            assert file_sha(os.path.join(d, fn)) == sha, f"{d}: raw file changed"
        recs = []
        for fn in sorted(glob.glob(os.path.join(d, "raw_worker*.jsonl"))):
            recs += read_jsonl(fn)
        assert len(recs) == 192 and len({r["request_id"] for r in recs}) == 192
        out["device_seconds"] = comp["device_seconds_request_union"]
        by_p = {}
        for r in recs:
            a_, b_ = by_p.get(r["patient"], (1e30, 0.0))
            by_p[r["patient"]] = (min(a_, r["t_dispatch"]), max(b_, r["t_orig_done"]))
        assert len(by_p) == 96
        lat = np.array([b - a for a, b in by_p.values()])
        out["n_boxes_total"] = int(sum(len(r["detections"]["0.8"]["boxes_orig_xyxy"]) for r in recs))
        # 고정 A 출력 대조 (iter_046 raw, threshold 0.8 box)
        import pg48_import as IM
        av = IM.load_a_v96()
        mism = 0
        for r in recs:
            f = av["records"][(r["patient"], r["target"])]
            mism += r["detections"]["0.8"]["boxes_orig_xyxy"] != f["detections"]["0.8"]["boxes_orig_xyxy"] or r["ckpt_sha256"] != IM.A_SHA
        out["box_mismatch_vs_fixed"] = int(mism)
        out["n_compared"] = len(recs)
    out["throughput_patients_per_min"] = 96 / comp["workload_wall_s"] * 60
    out["p95_latency_s"] = float(np.percentile(lat, 95))
    out["mean_latency_s"] = float(lat.mean())
    out["p50_latency_s"] = float(np.percentile(lat, 50))
    return out


def ratio_ci(num, den, key):
    lr = np.log(np.array([num[k][key] / den[k][key] for k in sorted(num)]))
    m, s = lr.mean(), lr.std(ddof=1)
    h = T5 * s / np.sqrt(len(lr))
    return {"ratio": float(np.exp(m)), "lo95": float(np.exp(m - h)), "hi95": float(np.exp(m + h)), "n_blocks": len(lr), "per_block": [float(np.exp(x)) for x in lr]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--attempts", nargs=6, type=int, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("exists")
    gate = json.load(open(GATE))
    fixed = {"adapters": gate["adapters"], "records": fixed_records(gate)}
    blocks = {s: {} for s in ("E", "J", "A")}
    for k in range(1, 7):
        jorder = "AB" if k % 2 == 1 else "BA"
        for s in ("E", "J", "A"):
            blocks[s][k] = load_block(k, a.attempts[k - 1], s, fixed, jorder)
    ledger = sorted(os.path.basename(d) for d in glob.glob(os.path.join(ROOT, "block*_a*_*")))
    rep = {"blocks": {s: {str(k): v for k, v in blocks[s].items()} for s in blocks}, "attempts_used": a.attempts, "all_block_dirs_incl_failed_attempts": ledger, "ratios": {}}
    for num, den in (("J", "E"), ("A", "E"), ("J", "A")):
        rep["ratios"][f"{num}/{den}"] = {"device_seconds": ratio_ci(blocks[num], blocks[den], "device_seconds"),
                                          "throughput": ratio_ci(blocks[num], blocks[den], "throughput_patients_per_min"),
                                          "p95_latency": ratio_ci(blocks[num], blocks[den], "p95_latency_s")}
    rep["integrity"] = {"E_token_mismatch_total": sum(b["token_mismatch_vs_fixed"] for b in blocks["E"].values()), "J_token_mismatch_total": sum(b["token_mismatch_vs_fixed"] for b in blocks["J"].values()),
                        "A_box_mismatch_total": sum(b["box_mismatch_vs_fixed"] for b in blocks["A"].values()),
                        "E_eos_all": all(b["eos_all"] for b in blocks["E"].values()), "J_eos_all": all(b["eos_all"] for b in blocks["J"].values())}
    rep["config"] = json.load(open("results/iter_048/decisions/timing_config.json"))
    rep["gate_sha256"] = file_sha(GATE)
    rep["source_sha256"] = {"pg48_time_report.py": file_sha("pg48_time_report.py")}
    json.dump(rep, open(a.out, "w"), indent=1)
    print(json.dumps({k: {m: (round(v["ratio"], 4), round(v["lo95"], 4), round(v["hi95"], 4)) for m, v in r.items()} for k, r in rep["ratios"].items()}, indent=1))
    print(rep["integrity"])


if __name__ == "__main__":
    main()
