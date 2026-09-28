"""iter_023 protocol 잠금: qa_protocol.py의 광범위한 REQUIRED_CODE(ev17/cx18/qa_data/MRI 등 미반입 모듈)를 요구하지 않는
명시적 profile. 이번 실행이 실제로 import하는 코드만 잠근다. qa_protocol.py는 import하지 않는다 (필요 없음).

- create: 코드(REQUIRED_CODE 전부 존재해야 함) + 명시한 extra 파일(요청·manifest 등)의 sha256과 생성 config digest를 잠근다.
- verify: 잠긴 모든 파일이 존재하고 sha가 같으며 config digest가 현재 processor/generation_config와 같아야 통과. returns protocol digest.
사용: python -m rsna_diag.roi23_protocol --out P --extra F ... [--note TEXT]
"""
import argparse
import json
import os
import sys

from . import generate, lock_protocol

SCHEMA = "iter023_roi23_protocol_v1"
REQUIRED_CODE = [
    "rsna_diag/__init__.py", "rsna_diag/geometry.py", "rsna_diag/parse.py", "rsna_diag/metrics.py",
    "rsna_diag/lora.py", "rsna_diag/generate.py", "rsna_diag/prompts.py", "rsna_diag/queue_lock.py",
    "rsna_diag/lock_protocol.py", "rsna_diag/inputs.py", "rsna_diag/eval_gate.py", "rsna_diag/qa_spec.py",
    "rsna_diag/qa_requests.py",
    "rsna_diag/roi23_spec.py", "rsna_diag/roi23_protocol.py", "rsna_diag/roi23_data.py",
    "rsna_diag/roi23_requests.py", "rsna_diag/roi23_gen.py", "rsna_diag/roi23_run.py",
    "rsna_diag/roi23_eval.py", "rsna_diag/roi23_pipeline.py", "rsna_diag/roi23_decide.py",
]


def static_cfg():
    d, core = generate.config_digest(generate.static_env(), {})
    return d, core


def current(extra=()):
    missing = [f for f in list(REQUIRED_CODE) + list(extra) if not os.path.isfile(f)]
    if missing:
        raise RuntimeError(f"required protocol files missing: {missing}")
    d, core = static_cfg()
    return {"schema": SCHEMA, "files": {f: lock_protocol.sha(f) for f in list(REQUIRED_CODE) + list(extra)},
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
    missing_req = [f for f in REQUIRED_CODE if f not in lk["files"]]
    if missing_req:
        raise RuntimeError(f"protocol does not lock required files: {missing_req}")
    extra = [f for f in lk["files"] if f not in REQUIRED_CODE]
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
