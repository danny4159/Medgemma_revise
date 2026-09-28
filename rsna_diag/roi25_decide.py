"""iter_025 D768 gate 판정: 계획에 사전 고정한 절대 기준으로만 판정한다 (report 내용을 그대로 재검증).

기준: (1) 8개 (ckpt x condition) 조합 모두 semantic valid >= 0.95.
      (2) M0/B0 각각 OB_I, OB_T의 전체 질문 정확도 >= 0.90 (24명 x 4문항=96, 최소 87/96).
OC의 높은 점수로 OB 실패를 대체하지 않는다 (OC는 gate 계산에 포함하지 않는다).
"""
import hashlib
import json
import os

OUT = os.environ.get("ROI25_RUN_ROOT", "results/iter_025")
FMT_MIN_VALID = 0.95
ORACLE_MIN_ACC = 0.90
CONDITIONS = ("OB_I", "OB_T", "OC_I", "OC_T")
GATE_CONDITIONS = ("OB_I", "OB_T")


def _sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def atomic_json(obj, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, default=str)
    os.replace(tmp, path)


def _checks(report):
    vr = report["valid_rates"]
    fmt_ok = {k: vr[k]["rate"] >= FMT_MIN_VALID for ckpt in ("M0", "B0") for k in [f"{ckpt}_{c}" for c in CONDITIONS]}
    format_ok = all(fmt_ok.values())
    qa = report["question_accuracy"]
    oracle_ok = {}
    for ckpt in ("M0", "B0"):
        for c in GATE_CONDITIONS:
            k = f"{ckpt}_{c}"
            acc = qa[k]["acc"]
            oracle_ok[k] = acc is not None and acc >= ORACLE_MIN_ACC
    oracle_pass = all(oracle_ok.values())
    return {"fmt_valid_rates": {k: vr[k]["rate"] for k in vr}, "fmt_ok_by_key": fmt_ok, "format_ok": format_ok,
            "oracle_question_accuracy": {k: qa[k]["acc"] for k in oracle_ok}, "oracle_ok_by_key": oracle_ok,
            "oracle_pass": oracle_pass, "passed": bool(format_ok and oracle_pass)}


def decide_d(report_path=None, out_path=None):
    report_path = report_path or f"{OUT}/eval/report_D.json"
    out_path = out_path or f"{OUT}/decide/D_decision.json"
    if os.path.exists(out_path):
        raise RuntimeError(f"{out_path} exists (not overwriting)")
    report = json.load(open(report_path))
    checks = _checks(report)
    decision = {"stage": "D", "report_path": report_path, "report_sha256": _sha_file(report_path), **checks}
    atomic_json(decision, out_path)
    return decision


def recheck(decision_path):
    d = json.load(open(decision_path))
    report_path = d["report_path"]
    if not os.path.exists(report_path):
        raise RuntimeError(f"decision {decision_path} refers to missing report {report_path}")
    cur_sha = _sha_file(report_path)
    if cur_sha != d["report_sha256"]:
        raise RuntimeError(f"report {report_path} changed since decision {decision_path} was made")
    report = json.load(open(report_path))
    recomputed = _checks(report)
    if recomputed["passed"] != d["passed"]:
        raise RuntimeError(f"decision {decision_path} field 'passed' does not match recomputed value")
    return d


if __name__ == "__main__":
    print(json.dumps(decide_d(), default=str))
