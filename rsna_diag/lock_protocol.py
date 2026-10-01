"""실행 protocol 잠금 (iter_010): 코드·manifest·prompt·생성 config digest를 파일로 고정하고, 실행 진입점에서 강제 검증한다.

- 경로는 항상 명시한다 (기본값 없음). 존재하면 현재 digest와 대조해 불일치 시 실패한다 (덮어쓰지 않음).
- verify(path) -> protocol digest (sha256 of locked 내용). generate/train/run_shards는 시작 시 verify를 호출하며 실패하면 실행하지 않는다.
사용: python -m rsna_diag.lock_protocol --out PATH [--extra FILE ...] [--check]
"""
import argparse
import hashlib
import json
import os
import sys

from . import prompts as P

CODE = ["rsna_diag/generate.py", "rsna_diag/parse.py", "rsna_diag/metrics.py", "rsna_diag/evaluate.py", "rsna_diag/geometry.py",
        "rsna_diag/prompts.py", "rsna_diag/rsna_data.py", "rsna_diag/dicom_min.py", "rsna_diag/run_shards.py",
        "rsna_diag/queue_lock.py", "rsna_diag/lock_protocol.py", "rsna_diag/lora.py", "rsna_diag/sft_data.py", "rsna_diag/train.py",
        "rsna_diag/baselines.py", "rsna_diag/launch.py", "rsna_diag/select.py", "rsna_diag/final_eval.py", "rsna_diag/sft_eval.py",
        "rsna_diag/data_gate.py", "rsna_diag/build_data.py", "rsna_diag/inputs.py", "rsna_diag/eval_gate.py", "rsna_diag/migrate.py",
        "rsna_diag/pipeline.py"]  # iter_012: 단계 순서·건너뛰기 검증을 담당하는 pipeline도 잠근다
DATA = ["results/iter_010/manifests/infer_manifest.jsonl", "results/iter_010/manifests/gt_manifest.json",
        "results/iter_010/manifests/exclusion_previous_patients.json", "results/iter_010/manifests/reserve_patients.json",
        "results/iter_009/source/official/cxr_anatomy_localization_with_hugging_face.ipynb"]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def locked_digest(locked):
    return hashlib.sha256(json.dumps(locked, sort_keys=True, default=str).encode()).hexdigest()


def digest_of(path):
    """코드 상태를 검증하지 않고 protocol 파일의 digest만 계산한다 (부모 실행의 원본 protocol 식별용)."""
    return locked_digest(json.load(open(path))["locked"])


def locked_config_digest(path):
    return json.load(open(path))["locked"]["generation_config_digest"]


def current(extra=()):
    from . import generate
    files = [f for f in CODE + DATA + list(extra) if os.path.exists(f)]
    d = {"files": {f: sha(f) for f in files}, "prompts": {k: P.digest(v) for k, v in P.all_prompts().items()}}
    core, cdig = generate.static_config()
    d["generation_config_digest"] = cdig
    d["generation_config"] = core
    return d


def verify(path):
    """protocol 파일이 없거나 현재 상태와 다르면 예외. returns protocol digest."""
    if not path or not os.path.exists(path):
        raise RuntimeError(f"protocol file missing: {path!r}")
    old = json.load(open(path))
    cur = current(extra=[f for f in old["locked"]["files"] if f not in CODE + DATA])
    diff = {k: (old["locked"]["files"].get(k), v) for k, v in cur["files"].items() if old["locked"]["files"].get(k) != v}
    diff.update({k: (v, None) for k, v in old["locked"]["files"].items() if k not in cur["files"]})
    if diff or old["locked"]["prompts"] != cur["prompts"] or old["locked"]["generation_config_digest"] != cur["generation_config_digest"]:
        raise RuntimeError("LOCK MISMATCH " + json.dumps(diff, indent=1)[:2000])
    return locked_digest(old["locked"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--extra", nargs="*", default=[])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    if os.path.exists(a.out):
        print("lock verified", verify(a.out))
        return
    if a.check:
        print("no lock yet")
        return
    cur = current(a.extra)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump({"locked": cur, "note": a.note}, open(a.out, "w"), indent=1, default=str)
    print("locked", a.out, locked_digest(cur))


if __name__ == "__main__":
    sys.exit(main())
