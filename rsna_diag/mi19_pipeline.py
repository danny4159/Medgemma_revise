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

DATA_DIR = "results/iter_021/data"
RUN_ROOT = "results/iter_021"


def _reuse_or_write_rows(rows, path):
    """path가 이미 있으면 rows를 재구성한 request_id 집합/내용과 파일 내용을 비교해 정확히
    같을 때만 재사용한다(존재 여부만으로 건너뛰지 않는다). 다르면 하드에러로 중단한다."""
    if not os.path.exists(path):
        Q.write_rows(rows, path)
        return
    existing = [json.loads(ln) for ln in open(path) if ln.strip()]
    want_by_id = {r["request_id"]: r for r in rows}
    have_by_id = {r["request_id"]: r for r in existing}
    if set(want_by_id) != set(have_by_id):
        raise RuntimeError(
            f"{path}: existing request file id set differs from reconstructed rows "
            f"(missing={sorted(set(want_by_id) - set(have_by_id))[:5]}, "
            f"extra={sorted(set(have_by_id) - set(want_by_id))[:5]})")
    for rid, want in want_by_id.items():
        have = have_by_id[rid]
        if want.get("prompt_sha256") != have.get("prompt_sha256") or want.get("images") != have.get("images") \
                or want.get("config_digest") != have.get("config_digest"):
            raise RuntimeError(f"{path}: existing request {rid} content differs from reconstructed row")


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
    all_rows = [r for rows in built.values() for r in rows]
    _reuse_or_write_rows(all_rows, phase1_path)
    if os.path.exists(proto_path):
        P.verify(proto_path)  # 기존 protocol이 있으면 현재 코드/자료와 여전히 일치하는지 재검증한다.
    else:
        P.create(proto_path, extra=[phase1_path], note=f"{split} phase1 (J_RT,J_TR,A,O,S1 merged)")
    out_dir1 = f"{out_root}/gen/{split}__phase1"
    rc1 = RUN.main_run(requests=phase1_path, out_dir=out_dir1, protocol=proto_path, workers=workers, gpus=gpus,
                       peak_gb=peak_gb, time_limit=time_limit, max_requests=max_requests)
    results_phase1 = {"phase1": {"out_dir": out_dir1, "rc": rc1}}
    if rc1 != 0:
        # phase1이 완료되지 않으면 S1 record가 불완전할 수 있다(중단된 attempt의 부분 출력).
        # S2를 구성하지 않고 여기서 멈춘다: phase1 실패 시 S2를 시작하지 않는다.
        results_phase1["S2"] = {"out_dir": None, "rc": None, "skipped_reason": "phase1_incomplete"}
        return results_phase1, phase1_path, None, manifest, pids
    # phase1이 rc==0이어도 completion.json이 실제로 있어야 "검증된 완료"로 취급한다 (RUN.run_stage는
    # rc==0을 완료 시에만 반환하지만, main_run을 통한 프로그램적 호출 경로도 동일 계약을 강제한다).
    completion1_path = os.path.join(out_dir1, "completion.json")
    if not os.path.exists(completion1_path):
        raise RuntimeError(f"phase1 rc==0 but no completion.json at {completion1_path}; refusing to build S2")
    # phase 2: S2 (검증된 S1 완료 record 필요). S1 원본 record와 completion을 그대로 읽어 사용하고,
    # 같은 request_id가 S1과 S2 사이에서 충돌하면(있을 수 없지만) 조용히 덮어쓰지 않는다.
    s1_all = E.load_records(out_dir1)  # load_records 자체가 중복 request_id면 예외를 낸다
    s1_records = {rid: r for rid, r in s1_all.items() if r.get("condition") == "S1"}
    s2_rows = Q.build_s2(manifest, pids, cfg, s1_records)
    s2_path = f"{out_root}/requests/{split}__S2.jsonl"
    _reuse_or_write_rows(s2_rows, s2_path)
    proto2_path = f"{out_root}/protocols/{split}_phase2.json"
    if os.path.exists(proto2_path):
        P.verify(proto2_path)
    else:
        P.create(proto2_path, extra=[s2_path, proto_path, completion1_path], note=f"{split} phase2 (S1={proto_path})")
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
