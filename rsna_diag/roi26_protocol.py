"""iter_026 protocol 잠금 (roi25_protocol.py 기반): 이번 실행이 실제로 import하는 코드와 필요한 source manifest/원시 bbox 파일을 잠근다."""
import argparse
import json
import os
import sys

from . import generate, lock_protocol

SCHEMA = "iter026_roi26_protocol_v1"
REQUIRED_CODE = [
    "rsna_diag/__init__.py", "rsna_diag/geometry.py", "rsna_diag/parse.py", "rsna_diag/metrics.py",
    "rsna_diag/lora.py", "rsna_diag/generate.py", "rsna_diag/prompts.py", "rsna_diag/queue_lock.py",
    "rsna_diag/lock_protocol.py", "rsna_diag/inputs.py", "rsna_diag/eval_gate.py", "rsna_diag/qa_spec.py",
    "rsna_diag/roi23_spec.py", "rsna_diag/roi23_data.py",
    "rsna_diag/roi26_spec.py", "rsna_diag/roi26_data.py", "rsna_diag/roi26_protocol.py", "rsna_diag/roi26_requests.py",
    "rsna_diag/roi26_gen.py", "rsna_diag/roi26_run.py", "rsna_diag/roi26_eval.py", "rsna_diag/roi26_decide.py",
]
REQUIRED_DATA = [
    "results/iter_023/manifests/sets.json", "results/iter_023/manifests/labels.json",
    "results/iter_010/manifests/infer_manifest.jsonl", "results/iter_010/manifests/gt_manifest.json",
    "results/iter_010/manifests/validation_ids.json",
    "results/iter_015/manifests/infer_manifest.jsonl", "results/iter_015/manifests/labels.json",
    "results/iter_015/manifests/sets.json",
    "results/iter_009/source/official/cxr_anatomy_localization_with_hugging_face.ipynb",
]


def static_cfg():
    d, core = generate.config_digest(generate.static_env(), {})
    return d, core


def current(extra=()):
    files = list(REQUIRED_CODE) + list(REQUIRED_DATA) + list(extra)
    missing = [f for f in files if not os.path.isfile(f)]
    if missing:
        raise RuntimeError(f"required protocol files missing: {missing}")
    d, core = static_cfg()
    return {"schema": SCHEMA, "files": {f: lock_protocol.sha(f) for f in files},
            "generation_config_digest": d, "generation_config": core}


def create(out, extra=(), note=""):
    if os.path.exists(out):
        raise RuntimeError(f"protocol exists (not overwriting): {out}")
    cur = current(extra)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump({"locked": cur, "note": note}, open(out, "w"), indent=1, default=str)
    return lock_protocol.locked_digest(cur)


def verify(path, allowed_edits=None):
    if not path or not os.path.exists(path):
        raise RuntimeError(f"protocol file missing: {path!r}")
    old = json.load(open(path))
    lk = old["locked"]
    if lk.get("schema") != SCHEMA:
        raise RuntimeError(f"protocol schema {lk.get('schema')!r} != {SCHEMA}")
    missing_req = [f for f in list(REQUIRED_CODE) + list(REQUIRED_DATA) if f not in lk["files"]]
    if missing_req:
        raise RuntimeError(f"protocol does not lock required files: {missing_req}")
    extra = [f for f in lk["files"] if f not in list(REQUIRED_CODE) + list(REQUIRED_DATA)]
    cur = current(extra)
    allowed_edits = allowed_edits or {}
    diff = {}
    for k, v in cur["files"].items():
        if lk["files"].get(k) == v:
            continue
        e = allowed_edits.get(k)
        if e and e.get("reason") and e.get("before") == lk["files"].get(k) and e.get("after") == v:
            continue
        diff[k] = (lk["files"].get(k), v)
    if diff or lk["generation_config_digest"] != cur["generation_config_digest"]:
        raise RuntimeError("LOCK MISMATCH " + json.dumps(diff, indent=1)[:2000])
    return lock_protocol.locked_digest(lk)


def locked_file_sha(path, f):
    return json.load(open(path))["locked"]["files"].get(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--extra", nargs="*", default=[])
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    print("locked", a.out, create(a.out, a.extra, a.note))


if __name__ == "__main__":
    sys.exit(main())
