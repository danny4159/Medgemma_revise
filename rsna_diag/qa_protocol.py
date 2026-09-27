"""iter_015/016 protocol 잠금. 기존 lock_protocol과 달리 필수 파일이 없으면 조용히 생략하지 않고 실패한다.

- create: 코드(REQUIRED_CODE 전부 존재해야 함) + 명시한 extra 파일(요청·manifest 등)의 sha256과 생성 config digest를 잠근다. 기존 파일은 덮어쓰지 않는다.
- verify: 잠긴 모든 파일이 존재하고 sha가 같으며 config digest가 현재 processor/generation_config와 같아야 통과. returns protocol digest.
- locked_file_sha(path, file): 잠긴 파일 목록에서 특정 파일의 sha (runner가 자신의 요청 파일이 잠겨 있는지 확인).
사용: python -m rsna_diag.qa_protocol --out P --extra F ... [--note TEXT]
"""
import argparse
import json
import os
import sys

from . import generate, lock_protocol

SCHEMA = "iter016_qa_protocol_v1"  # iter_017도 같은 스키마 (REQUIRED_CODE에 ev17_* 추가)
# 반입한 16개 파일 + 이번 반복의 신규 모듈. 하나라도 없으면 실패한다.
REQUIRED_CODE = [
    "rsna_diag/__init__.py", "rsna_diag/geometry.py", "rsna_diag/parse.py", "rsna_diag/metrics.py", "rsna_diag/sft_eval.py",
    "rsna_diag/lora.py", "rsna_diag/generate.py", "rsna_diag/prompts.py", "rsna_diag/queue_lock.py", "rsna_diag/lock_protocol.py",
    "rsna_diag/inputs.py", "rsna_diag/eval_gate.py", "rsna_diag/run_shards.py", "rsna_diag/on_gpu.py", "rsna_diag/rsna_data.py",
    "rsna_diag/dicom_min.py",
    "rsna_diag/qa_spec.py", "rsna_diag/qa_data.py", "rsna_diag/qa_protocol.py", "rsna_diag/qa_requests.py", "rsna_diag/qa_gen.py",
    "rsna_diag/qa_run.py",
    # iter_017: evidence 정보 수준(U/B/K/L/X) 진단
    "rsna_diag/ev17_spec.py", "rsna_diag/ev17_requests.py", "rsna_diag/ev17_analysis.py", "rsna_diag/ev17_reuse.py",
    # iter_016: semantic parser(qa_spec)·평가·보고·재사용 검증·확대 결정 코드
    "rsna_diag/qa_eval.py", "rsna_diag/qa_report.py", "rsna_diag/qa_reuse.py", "rsna_diag/qa_scope.py", "rsna_diag/qa_pilot.py",
    # iter_018: CheXpert target-scope 진단(질문 대상 범위 문구 이후의 다른 finding 손상). 과거(iter_015~017) protocol은
    # 이 파일들이 존재하지 않던 시점의 REQUIRED_CODE로 잠겼으므로, 이 추가 이후에는 현재 qa_protocol.py로 재검증되지
    # 않는다(이미 ev17_* 추가 때도 iter_016 protocol에 동일하게 발생한 기존 관례). 과거 반복은 해당 시점의 코드
    # 커밋에서만 재검증한다.
    "rsna_diag/cx18_spec.py", "rsna_diag/cx18_data.py", "rsna_diag/cx18_requests.py", "rsna_diag/cx18_analysis.py",
    "rsna_diag/cx18_run.py",
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
    """잠긴 모든 파일이 존재하고 sha가 같아야 통과 (파일명만으로 허용하는 우회는 없다).
    allowed_edits: {파일: {"before": 잠긴 sha, "after": 현재 sha, "reason": 사유}} 형태의 명시적 허용. before가 잠긴 값, after가 현재 값과
    정확히 같을 때만 그 파일의 차이를 허용하고, 사유가 없거나 hash가 다르면 실패한다. 반환 digest는 항상 잠긴 목록의 digest이다."""
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
