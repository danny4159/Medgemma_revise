"""iter_019 D8/E48 실행 파이프라인. 단계 순서: manifest -> protocol -> phase1 생성 -> S2 생성 -> baseline(C/N) -> 평가 -> gate 판정.

사용: python -m rsna_diag.mi19_pipeline --split D --workers 2 --peak-gb 10 [--gpus 0,1]
"""
import argparse
import json
import os
import sys

from . import mi19_baseline as B
from . import mi19_eval as E
from . import mi19_protocol as P
from . import mi19_requests as Q
from . import mi19_run as RUN

DATA_DIR = "results/iter_020/data"
RUN_ROOT = "results/iter_020"


def run_split(split, workers, peak_gb, gpus, out_root=RUN_ROOT, time_limit=None, max_requests=None):
    """phase1(J_RT,J_TR,A,O,S1) 5개 condition을 하나의 요청 파일로 합쳐 모델을 한 번만 로드한다.
    S2는 S1 완료 record가 필요하므로 별도 phase(protocol)로 분리한다."""
    manifest = json.load(open(f"{DATA_DIR}/manifest.json"))
    split_map = json.load(open(f"{DATA_DIR}/split.json"))
    pids = split_map[split]
    os.makedirs(f"{out_root}/requests", exist_ok=True)
    os.makedirs(f"{out_root}/protocols", exist_ok=True)
    proto_path = f"{out_root}/protocols/{split}_phase1.json"
    cfg, _ = P.static_cfg()
    built = Q.build_phase1(manifest, pids, cfg)
    phase1_path = f"{out_root}/requests/{split}__phase1.jsonl"
    if not os.path.exists(phase1_path):
        all_rows = [r for rows in built.values() for r in rows]
        Q.write_rows(all_rows, phase1_path)
    if not os.path.exists(proto_path):
        P.create(proto_path, extra=[phase1_path, f"{DATA_DIR}/manifest.json", f"{DATA_DIR}/split.json"],
                 note=f"{split} phase1 (J_RT,J_TR,A,O,S1 merged)")
    out_dir1 = f"{out_root}/gen/{split}__phase1"
    rc1 = RUN.main_run(requests=phase1_path, out_dir=out_dir1, protocol=proto_path, workers=workers, gpus=gpus,
                       peak_gb=peak_gb, time_limit=time_limit, max_requests=max_requests)
    results_phase1 = {"phase1": {"out_dir": out_dir1, "rc": rc1}}
    if rc1 != 0:
        # phase1이 완료되지 않으면 S1 record가 불완전할 수 있다(중단된 attempt의 부분 출력).
        # S2를 구성하지 않고 여기서 멈춘다: phase1 실패 시 S2를 시작하지 않는다.
        results_phase1["S2"] = {"out_dir": None, "rc": None, "skipped_reason": "phase1_incomplete"}
        return results_phase1, phase1_path, None, manifest, pids
    # phase 2: S2 (검증된 S1 완료 record 필요)
    s1_records = {rid: r for rid, r in E.load_records(out_dir1).items() if r.get("condition") == "S1"}
    s2_rows = Q.build_s2(manifest, pids, cfg, s1_records)
    s2_path = f"{out_root}/requests/{split}__S2.jsonl"
    if not os.path.exists(s2_path):
        Q.write_rows(s2_rows, s2_path)
    proto2_path = f"{out_root}/protocols/{split}_phase2.json"
    if not os.path.exists(proto2_path):
        P.create(proto2_path, extra=[s2_path, f"{DATA_DIR}/manifest.json", f"{DATA_DIR}/split.json"], note=f"{split} phase2")
    out_dir_s2 = f"{out_root}/gen/{split}__S2"
    rc2 = RUN.main_run(requests=s2_path, out_dir=out_dir_s2, protocol=proto2_path, workers=workers, gpus=gpus,
                       peak_gb=peak_gb, time_limit=time_limit, max_requests=max_requests)
    results_phase1["S2"] = {"out_dir": out_dir_s2, "rc": rc2}
    return results_phase1, phase1_path, s2_path, manifest, pids


def evaluate_split(split, phase1_path, s2_path, manifest, pids, out_root=RUN_ROOT):
    out_dir1 = f"{out_root}/gen/{split}__phase1"
    phase1_rows = Q.load_rows(phase1_path)
    rows_by_cond = {}
    for cond in ("J_RT", "J_TR", "A", "O", "S1"):
        rows_by_cond[cond] = [r for r in phase1_rows if r["condition"] == cond]
    records = dict(E.load_records(out_dir1))
    s2_rows = Q.load_rows(s2_path)
    rows_by_cond["S2"] = s2_rows
    records.update(E.load_records(f"{out_root}/gen/{split}__S2"))
    ev = {}
    for cond in ("J_RT", "J_TR", "A", "O", "S2"):
        ev[cond] = E.evaluate_condition(rows_by_cond[cond], records, manifest, cond)
    ev["C"] = E.evaluate_baseline(manifest, pids, lambda m, inst: (B.condition_C(inst["ref_box_norm"]), {"status": "ok"}), "C")

    def n_fn(m, inst):
        return B.condition_N(m["R"]["path"], m["T"]["path"], inst["ref_box_norm"], tuple(m["pad_top_left_side"]))
    ev["N"] = E.evaluate_baseline(manifest, pids, n_fn, "N")
    pair = {c: E.pair_success_rate(rows) for c, rows in ev.items()}
    h = E.compute_H(pids, ev["O"], ev["J_RT"], ev["J_TR"])
    fmt_stats = {}
    for c in ("J_RT", "J_TR", "O"):
        rid_by_pat_lab = {(row["patient"], row["label"]): row["request_id"] for row in rows_by_cond[c]}
        n = len(ev[c])
        n_valid_single = sum(1 for r in ev[c] if r.get("parse_status") == "valid_nonempty" and r.get("box") is not None
                             and not r.get("missing"))
        n_cap = sum(1 for r in ev[c] if not r.get("missing")
                   and records.get(rid_by_pat_lab.get((r["patient"], r["label"])), {}).get("finish_reason") == "length")
        fmt_stats[c] = {"n": n, "n_valid_single": n_valid_single, "valid_rate": n_valid_single / n if n else float("nan"),
                        "n_final_cap_hit": n_cap, "cap_rate": n_cap / n if n else float("nan")}
    report = {"split": split, "n_patients": len(pids), "H": h, "pair_success": {c: {k: v for k, v in d.items() if k != "per_patient"}
                                                                                for c, d in pair.items()},
             "format_stats": fmt_stats, "n_missing_by_cond": {c: sum(1 for r in rows if r.get("missing")) for c, rows in ev.items()}}
    diffs = {}
    for other in ("C", "N", "S2", "A"):
        diffs[f"{other}_vs_J_RT"] = E.paired_diff(pair[other]["per_patient"], pair["J_RT"]["per_patient"], pids)
    report["pair_success_diffs_vs_J_RT"] = diffs
    return report, ev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True, choices=["D", "E", "F"])
    ap.add_argument("--workers", type=int, required=True)
    ap.add_argument("--peak-gb", type=float, required=True)
    ap.add_argument("--gpus", default=None)
    ap.add_argument("--time-limit", type=float, default=None)
    ap.add_argument("--max-requests", type=int, default=None)
    a = ap.parse_args()
    res, phase1_path, s2_path, manifest, pids = run_split(a.split, a.workers, a.peak_gb, a.gpus,
                                                          time_limit=a.time_limit, max_requests=a.max_requests)
    print(json.dumps({"run": res}, indent=1, default=str))
    ok = all(v["rc"] == 0 for v in res.values())
    if not ok:
        print(json.dumps({"status": "generation_incomplete_or_failed"}))
        sys.exit(2)
    report, ev = evaluate_split(a.split, phase1_path, s2_path, manifest, pids)
    out_path = f"{RUN_ROOT}/report_{a.split}.json"
    json.dump({"report": report}, open(out_path, "w"), indent=1, default=str)
    json.dump(ev, open(f"{RUN_ROOT}/eval_raw_{a.split}.json", "w"), indent=1, default=str)
    print(json.dumps(report, indent=1, default=str))


if __name__ == "__main__":
    main()
