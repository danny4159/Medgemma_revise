"""iter_019 protocol 잠금: 코드·manifest·split·요청 파일·생성 config digest를 고정한다 (qa_protocol과 동일한 필수-실패 규약).

사용: python -m rsna_diag.mi19_protocol --out P --extra F ... [--note TEXT]
"""
import argparse
import json
import os
import sys

from . import generate, lock_protocol, mi19_data

SCHEMA = "iter021_mi19_protocol_v1"
REQUIRED_CODE = [
    "rsna_diag/__init__.py", "rsna_diag/geometry.py", "rsna_diag/parse.py", "rsna_diag/metrics.py",
    "rsna_diag/generate.py", "rsna_diag/prompts.py", "rsna_diag/queue_lock.py", "rsna_diag/lock_protocol.py",
    "rsna_diag/mi19_mha.py", "rsna_diag/mi19_render.py", "rsna_diag/mi19_data.py", "rsna_diag/mi19_manifest.py",
    "rsna_diag/mi19_spec.py", "rsna_diag/mi19_requests.py", "rsna_diag/mi19_protocol.py", "rsna_diag/mi19_gen.py",
    "rsna_diag/mi19_run.py", "rsna_diag/mi19_baseline.py", "rsna_diag/mi19_eval.py", "rsna_diag/mi19_pipeline.py",
]
# 자료 provenance는 선택적 --extra가 아니라 항상 필수로 잠근다 (gate/manifest/split이 바뀌면
# protocol이 반드시 이를 감지해야 한다). DATA_DIR은 mi19_data.DATA_DIR로 매 반복(iter_021 등) 갱신된다.
REQUIRED_DATA = [
    f"{mi19_data.DATA_DIR}/gate.json",
    f"{mi19_data.DATA_DIR}/manifest.json",
    f"{mi19_data.DATA_DIR}/split.json",
]


def static_cfg():
    return generate.config_digest(generate.static_env(), {})


def current(extra=()):
    all_req = list(REQUIRED_CODE) + list(REQUIRED_DATA) + list(extra)
    missing = [f for f in all_req if not os.path.isfile(f)]
    if missing:
        raise RuntimeError(f"required protocol files missing: {missing}")
    d, core = static_cfg()
    return {"schema": SCHEMA, "files": {f: lock_protocol.sha(f) for f in all_req},
            "generation_config_digest": d, "generation_config": core}


def create(out, extra=(), note=""):
    if os.path.exists(out):
        raise RuntimeError(f"protocol exists (not overwriting): {out}")
    cur = current(extra)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump({"locked": cur, "note": note}, open(out, "w"), indent=1, default=str)
    return lock_protocol.locked_digest(cur)


def verify(path):
    if not path or not os.path.exists(path):
        raise RuntimeError(f"protocol file missing: {path!r}")
    old = json.load(open(path))
    lk = old["locked"]
    if lk.get("schema") != SCHEMA:
        raise RuntimeError(f"protocol schema {lk.get('schema')!r} != {SCHEMA}")
    missing_req = [f for f in list(REQUIRED_CODE) + list(REQUIRED_DATA) if f not in lk["files"]]
    if missing_req:
        raise RuntimeError(f"protocol does not lock required files: {missing_req}")
    extra = [f for f in lk["files"] if f not in REQUIRED_CODE and f not in REQUIRED_DATA]
    cur = current(extra)
    diff = {k: (lk["files"].get(k), v) for k, v in cur["files"].items() if lk["files"].get(k) != v}
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
