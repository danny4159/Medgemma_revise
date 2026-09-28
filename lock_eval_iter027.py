"""iter_027 평가 입력 잠금: eval_iter026.py의 report가 실제로 어떤 코드·원시 데이터에서 나왔는지 독립적으로
기록한다. iter_026 리뷰는 평가·decision 진입점(eval_iter026.py, decide_iter026_*.py)과 원시 bbox
completion, checkpoint manifest가 protocol에 잠기지 않는다고 지적했다. roi26_protocol.REQUIRED_CODE는
생성 경로 전용이라 바꾸지 않고, 이번 평가 단계 전용 잠금을 별도로 만든다(생성 protocol과 동일한 sha 방식 재사용).
사용: python lock_eval_iter027.py {E60|E200} --out results/iter_027/eval_protocol_{stage}.json
"""
import argparse
import glob
import json
import os
import sys

from rsna_diag import lock_protocol

EVAL_CODE = [
    "eval_iter026.py", "decide_iter026_d.py", "decide_iter026_e60.py", "decide_iter026_e200.py",
    "rsna_diag/roi26_eval.py", "rsna_diag/roi26_decide.py", "rsna_diag/roi26_data.py",
    "rsna_diag/roi23_data.py", "rsna_diag/roi23_spec.py", "rsna_diag/parse.py", "rsna_diag/metrics.py",
]


def stage_gen_dirs(stage):
    if stage == "E60":
        return ["E60_V__M0", "E60_V__B0", "E60_RD__M0"]
    if stage == "E200":
        return ["E60_V__M0", "E60_V__B0", "E60_RD__M0", "E200_extra_V__M0", "E200_extra_V__B0", "E200_extra_RD__M0"]
    raise SystemExit(f"unknown stage {stage}")


def verify(path):
    old = json.load(open(path))
    stage = old["stage"]
    cur = build_files(stage)
    diff = {k: (old["files"].get(k), v) for k, v in cur.items() if old["files"].get(k) != v}
    missing = [k for k in old["files"] if k not in cur]
    if diff or missing:
        raise SystemExit(f"EVAL LOCK MISMATCH diff={json.dumps(diff, indent=1)[:2000]} missing={missing}")
    print("verify ok", path, "n_files", len(cur))


def build_files(stage):
    files = {}
    for f in EVAL_CODE:
        files[f] = lock_protocol.sha(f)
    for name in stage_gen_dirs(stage):
        cp = f"results/iter_026/gen/{name}/completion.json"
        if not os.path.exists(cp):
            raise SystemExit(f"missing completion.json for {name}; generation not finished (execution gap, cannot lock eval inputs yet)")
        files[cp] = lock_protocol.sha(cp)
        for gf in sorted(glob.glob(f"results/iter_026/gen/{name}/gen_worker*.jsonl")):
            files[gf] = lock_protocol.sha(gf)
        rp = f"results/iter_026/requests/{name}.jsonl"
        if os.path.exists(rp):
            files[rp] = lock_protocol.sha(rp)
    for extra in ("results/iter_023/manifests/sets.json", "results/iter_023/manifests/labels.json",
                  "results/iter_026/manifests/checkpoints.json", "results/iter_010/manifests/validation_ids.json"):
        if os.path.exists(extra):
            files[extra] = lock_protocol.sha(extra)
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["E60", "E200"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--verify-only", action="store_true")
    a = ap.parse_args()
    if a.verify_only:
        return verify(a.out)

    files = build_files(a.stage)
    obj = {"schema": "iter027_eval_lock_v1", "stage": a.stage, "files": files}
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(obj, open(a.out, "w"), indent=1, default=str)
    print("locked", a.out, "n_files", len(files))


if __name__ == "__main__":
    sys.exit(main())
