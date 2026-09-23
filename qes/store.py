"""Prediction cache validation, explicit run queue and device-minute ledger.

재개(runner)와 집계(selector)가 같은 `validate_predictions`를 쓴다.
"""
import json
import math
import os
import time

# 같은 입력의 반복 결과가 이 값보다 다르면 conflicting duplicate로 본다.
DUP_TOL = 0.0

# 주평가(m)·민감도(m_fp32head)·scoring 검사에 쓰는 모든 결과 필드 (iter_005: 중복 비교와 digest 대상).
# 비결과 metadata(seconds, ts, phase)는 중복 비교·digest에서 제외한다. 같은 입력의 재실행은
# 실행 시간이 달라도 결과 필드가 같으면 일관된 중복으로 본다.
RESULT_FIELDS = ["m", "m_fp32head", "lp_yes", "lp_no", "p_yes_plus_no", "top1_token", "n_tokens",
                 "n_image_tokens", "pixel_values_shape", "prompt_intact"]
FLOAT_RESULT_FIELDS = ["m", "m_fp32head", "lp_yes", "lp_no", "p_yes_plus_no"]


def _result_problem(rec):
    miss = [f for f in RESULT_FIELDS if f not in rec]
    if miss:
        return "missing_result_field"
    for f in FLOAT_RESULT_FIELDS:
        x = rec[f]
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
            return "non_finite_result"
    return None


def _result_key(rec):
    return {f: rec[f] for f in RESULT_FIELDS}

UNCOUNTED_SESSION_PENALTY_MIN = 2.0  # 비정상 종료 세션의 미계상 구간에 보수적으로 부과


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def append_jsonl(path, rec):
    with open(path, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def write_json_atomic(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def validate_predictions(requests, records, config_sha256, scorer_version):
    """요청별로 유효한 결과를 하나 고른다.

    유효 조건: status ok, id가 manifest에 있고 request/config/input hash와 scorer version이 모두 일치.
    같은 id의 유효 결과가 여러 개인데 margin이 다르면 conflict로 두고 채택하지 않는다.
    """
    req_by_id = {r["id"]: r for r in requests}
    valid, rejected, conflicts, dup_ok = {}, [], [], 0
    for rec in records:
        rid = rec.get("id")
        r = req_by_id.get(rid)
        reason = None
        if r is None:
            reason = "unknown_id"
        elif rec.get("status") != "ok":
            reason = f"status_{rec.get('status')}"
        elif rec.get("request_sha256") != r["request_sha256"]:
            reason = "request_hash_mismatch"
        elif rec.get("config_sha256") != config_sha256 or r["config_sha256"] != config_sha256:
            reason = "config_hash_mismatch"
        elif rec.get("input_pixel_sha256") != r["input_pixel_sha256"]:
            reason = "input_hash_mismatch"
        elif rec.get("scorer_version") != scorer_version:
            reason = "scorer_version_mismatch"
        else:
            reason = _result_problem(rec)
        if reason:
            rejected.append({"id": rid, "reason": reason})
            continue
        if rid in valid:
            a, b = _result_key(valid[rid]), _result_key(rec)
            diff = [f for f in RESULT_FIELDS
                    if (abs(a[f] - b[f]) > DUP_TOL if f in FLOAT_RESULT_FIELDS else a[f] != b[f])]
            if diff:
                conflicts.append({"id": rid, "fields": diff, "values": [{f: a[f] for f in diff}, {f: b[f] for f in diff}]})
            else:
                dup_ok += 1
            continue
        valid[rid] = rec
    conflict_ids = {c["id"] for c in conflicts}
    for rid in conflict_ids:
        valid.pop(rid, None)
    missing = [r["id"] for r in requests if r["id"] not in valid]
    return {
        "valid": valid,
        "rejected": rejected,
        "conflicts": conflicts,
        "duplicates_consistent": dup_ok,
        "missing": missing,
        "status": "complete" if not missing and not conflicts else "incomplete",
    }


def plan_queue(requests, done_ids, allowed_ids=None, limit=None):
    """실행할 요청 목록을 한 번에 명시적으로 만든다 (반복 중 재할당하지 않는다)."""
    q = [r for r in requests if r["id"] not in done_ids]
    if allowed_ids is not None:
        allowed = set(allowed_ids)
        q = [r for r in q if r["id"] in allowed]
    if limit is not None:
        q = q[:limit]
    return q


class Ledger:
    """device-minute 사용량 checkpoint. 매 요청 완료 시 저장한다.

    세션 시작 시 open=True로 기록하고 정상/예외 종료 시 close한다. 다음 실행에서 open 상태로 남은
    세션이 발견되면 마지막 checkpoint 이후 구간을 알 수 없으므로 penalty를 추가 계상한다.
    """

    def __init__(self, path, n_devices=1):
        self.path = path
        self.n_devices = n_devices
        self.data = {"sessions": [], "cap_minutes": None}
        if os.path.exists(path):
            with open(path) as f:
                self.data = json.load(f)
        for s in self.data["sessions"]:
            if s.get("open"):
                s["open"] = False
                s["closed_by"] = "recovered_unclosed"
                s["uncounted_penalty_min"] = UNCOUNTED_SESSION_PENALTY_MIN
        self.cur = None

    def total_minutes(self):
        tot = 0.0
        for s in self.data["sessions"]:
            tot += s.get("device_minutes", 0.0) + s.get("uncounted_penalty_min", 0.0)
        return tot

    def start(self, note):
        self.t0 = time.time()
        self.cur = {"note": note, "start": self.t0, "last_checkpoint": self.t0, "open": True,
                    "device_minutes": 0.0, "n_requests": 0, "inflight": None, "n_devices": self.n_devices}
        self.data["sessions"].append(self.cur)
        self.save()

    def mark_inflight(self, what):
        self.cur["inflight"] = what
        self.checkpoint()

    def checkpoint(self, n_done_delta=0, **extra):
        now = time.time()
        self.cur["last_checkpoint"] = now
        self.cur["device_minutes"] = (now - self.t0) / 60.0 * self.n_devices
        self.cur["n_requests"] += n_done_delta
        self.cur.update(extra)
        self.save()

    def close(self, how):
        self.cur["inflight"] = None
        self.cur["open"] = False
        self.cur["closed_by"] = how
        self.checkpoint()

    def save(self):
        write_json_atomic(self.path, self.data)
