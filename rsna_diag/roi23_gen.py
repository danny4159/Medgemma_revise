"""iter_015/016 요청 행렬(qa_requests) 전용 생성 worker. generate.py의 모델 로더·adapter 로더·run_request(cap 래더 1000/2000/4000)를 재사용하고,
요청 식별·재개 검증·claim만 request 단위로 새로 구현한다 (환자마다 prompt/evidence가 달라 전역 prompt 이름으로 식별할 수 없다).

- 시작 시: qa_protocol.verify, 요청 파일이 protocol에 잠긴 파일과 같은지, 각 행의 request_id 재계산·config digest, 모든 영상의 현재 file/pixel hash.
- adapter digest(tensor 재계산)가 모든 행의 adapter_digest와 같아야 한다 (base면 None).
- 재개: 완료 record를 포함해 모든 worker 파일을 요청 행과 대조한다. 중복·잉여·id/prompt/adapter/config/protocol 불일치·입력 hash 변경·잘린 JSONL은 중단.
  --repair-tail: 마지막 줄이 개행 없이 잘렸을 때만 그 줄을 *.partial로 옮기고 계속한다 (기록을 지우지 않는다).
  iter_016 소유권: repair는 (a) 내 worker 파일(내 lock 보유) 또는 (b) 작성 worker가 종료돼 그 worker lock을 내가 확보한 파일에만 한다.
  살아 있는 다른 worker의 파일은 읽기에서 개행 없는 마지막 줄만 유보하고 절대 수정하지 않는다.
사용: CUDA_VISIBLE_DEVICES=<gpu> python -m rsna_diag.qa_gen --requests R --out-dir D --worker K --protocol P [--adapter DIR]
"""
import argparse
import glob
import json
import os
import re
import sys
import time

from . import generate, roi23_protocol as qa_protocol, roi23_requests as Q, queue_lock


class QAError(RuntimeError):
    pass


def read_strict(path, repair_tail=False, tolerate_tail=False):
    """JSONL을 읽는다. 잘린/깨진 줄은 QAError (repair_tail이면 개행 없는 마지막 줄만 격리)."""
    if not os.path.exists(path):
        return []
    raw = open(path, "rb").read()
    lines = raw.split(b"\n")
    tail = lines[-1]
    recs = []
    body = lines[:-1]
    if tail.strip() and tolerate_tail:
        pass  # 다른 살아 있는 worker가 쓰는 중인 마지막 줄 (개행 전)은 아직 완료 요청이 아니다
    elif tail.strip():
        if repair_tail:
            with open(path + ".partial", "ab") as f:
                f.write(tail + b"\n")
            with open(path, "wb") as f:
                f.write(b"\n".join(body) + (b"\n" if body else b""))
        else:
            raise QAError(f"truncated last line (no newline) in {path}; rerun with --repair-tail to quarantine it")
    for k, ln in enumerate(body):
        if ln.strip():
            try:
                recs.append(json.loads(ln))
            except ValueError as e:
                raise QAError(f"corrupt JSON line {k} in {path}") from e
    return recs


def _worker_of(path):
    m = re.fullmatch(r"gen_worker(\d+)\.jsonl", os.path.basename(path))
    return int(m.group(1)) if m else None


def _has_tail(path):
    if not os.path.exists(path):
        return False
    with open(path, "rb") as f:
        data = f.read()
    return bool(data.split(b"\n")[-1].strip())


def read_all_owned(out_dir, my_worker, repair, live, info):
    """out_dir의 모든 gen_worker*.jsonl을 읽는다. 잘린 마지막 줄의 처리:
    내 파일 -> repair 옵션이 있으면 격리·복구, 없으면 오류(live=False). 다른 worker 파일 -> 그 worker의 lock을 non-blocking으로 시도해
    확보되면(작성자 종료) repair 옵션에 따라 복구/오류, 확보 실패(작성자 생존)이면 읽기에서만 유보하고 수정하지 않는다.
    tail이 없는 파일은 lock을 건드리지 않는다 (동시에 시작하는 worker의 lock을 잠시라도 가로채지 않는다)."""
    out = {}
    for f in sorted(glob.glob(os.path.join(out_dir, "gen_worker*.jsonl"))):
        w = _worker_of(f)
        if w == my_worker or not _has_tail(f):
            out[f] = read_strict(f, repair_tail=repair and w == my_worker and not live)
            continue
        lk, _, _ = queue_lock.try_lock(os.path.join(out_dir, f"worker{w}.lock"), info)
        if lk is None:
            out[f] = read_strict(f, tolerate_tail=True)  # 살아 있는 writer: 수정 금지
        else:
            try:  # 작성자가 종료했고 lock을 내가 잡고 있다
                out[f] = read_strict(f, repair_tail=repair and not live, tolerate_tail=live)
            finally:
                lk.release()
    return out


def validate_records(files_records, rows, cdig, adapter_digest, protocol_digest, pixel_sha):
    """모든 기존 record를 현재 요청 행과 대조. returns {request_id: record}. 누락은 허용, 중복·잉여·불일치는 QAError."""
    by = {r["request_id"]: r for r in rows}
    done = {}
    for fn, recs in files_records.items():
        for r in recs:
            rid = r.get("request_id")
            row = by.get(rid)
            if row is None:
                raise QAError(f"unexpected record {rid} in {fn}: not in current request set")
            if rid in done:
                raise QAError(f"duplicate record {rid} in {fn}")
            for k, want in (("prompt_sha256", row["prompt_sha256"]), ("adapter_digest", adapter_digest), ("config_digest", cdig),
                            ("protocol_digest", protocol_digest), ("id", row["id"]), ("condition", row["condition"]),
                            ("checkpoint", row["checkpoint"]), ("target", row["target"]), ("fmt", row["fmt"]),
                            ("image_file_sha256", row["file_sha256"])):
                if r.get(k) != want:
                    raise QAError(f"{k} mismatch for {rid} in {fn}: {r.get(k)!r} != {want!r}")
            if r.get("input_pixel_sha256") != pixel_sha(row["image"]):
                raise QAError(f"input image changed since generation for {rid}")
            done[rid] = r
    return done


def check_inputs(rows):
    """현재 영상의 raw pixel/file sha를 요청 행과 대조한다 (전처리 전 원본 uint8 hash)."""
    from . import inputs
    seen = {}
    for r in rows:
        key = r["image"]
        if key in seen:
            continue
        if generate.sha(open(key, "rb").read()) != r["file_sha256"]:
            raise QAError(f"file sha changed for {r['id']}")
        if inputs.raw_pixel_sha(key) != r["pixel_sha256"]:
            raise QAError(f"pixel sha changed for {r['id']}")
        seen[key] = 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--requests", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--worker", type=int, required=True)
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--time-limit", type=float, default=None)
    ap.add_argument("--max-requests", type=int, default=None)
    ap.add_argument("--repair-tail", action="store_true")
    a = ap.parse_args()
    pdig = qa_protocol.verify(a.protocol)
    if json.load(open(a.protocol))["locked"]["files"].get(a.requests) != generate.sha(open(a.requests, "rb").read()):
        sys.exit(f"request file {a.requests} is not locked in {a.protocol} (or changed)")
    cfg, _ = qa_protocol.static_cfg()
    rows = Q.load_rows(a.requests, cfg)
    if len({(r["checkpoint"], r["adapter_digest"]) for r in rows}) != 1:
        sys.exit("one run must contain one checkpoint")
    check_inputs(rows)
    os.makedirs(a.out_dir, exist_ok=True)
    info = queue_lock.my_info(worker=a.worker)
    lk, own, _ = queue_lock.try_lock(os.path.join(a.out_dir, f"worker{a.worker}.lock"), info)
    if lk is None:
        sys.exit(f"worker {a.worker} already running: {own}")
    try:
        run_worker(a, rows, pdig, cfg, info)
    finally:
        lk.release()


def run_worker(a, rows, pdig, cfg, info):
    torch, proc, model = generate.load_model()
    adapter_digest = generate.load_adapter(torch, model, a.adapter) if a.adapter else None
    if adapter_digest != rows[0]["adapter_digest"]:
        raise QAError(f"loaded adapter digest {adapter_digest} != requests {rows[0]['adapter_digest']}")
    env = generate.env_info(torch, proc, model)
    cdig, core = generate.config_digest(env, {})
    if cdig != cfg:
        raise QAError("runtime generation config digest != protocol config digest")
    eos = env["eos_token_id"]
    eos_ids = set(eos if isinstance(eos, list) else [eos])
    with open(os.path.join(a.out_dir, f"gen_worker{a.worker}.jsonl.env.json"), "w") as f:
        json.dump({"env": env, "config_digest": cdig, "adapter_digest": adapter_digest, "protocol_digest": pdig,
                   "worker": a.worker, "requests": a.requests}, f, indent=1, default=str)
    cache = {}

    def px(path):
        if path not in cache:
            cache[path] = generate.load_image(path)[2]
        return cache[path]

    def read_all(repair, live=False):
        return read_all_owned(a.out_dir, a.worker, repair, live, info)

    done = validate_records(read_all(a.repair_tail), rows, cdig, adapter_digest, pdig, px)
    out = os.path.join(a.out_dir, f"gen_worker{a.worker}.jsonl")
    claim_dir = os.path.join(a.out_dir, "claims")
    os.makedirs(claim_dir, exist_ok=True)
    log = open(out + ".log", "a")
    t0, n_done = time.time(), 0
    # id 순서 고정 (worker 간 충돌을 줄이기 위해 worker 번호로 시작 위치를 나누지 않고 claim으로만 경쟁한다)
    for row in sorted(rows, key=lambda r: r["request_id"]):
        if row["request_id"] in done:
            continue
        if (a.time_limit and time.time() - t0 > a.time_limit) or (a.max_requests is not None and n_done >= a.max_requests):
            log.write(json.dumps({"event": "stop", "done_this_run": n_done}) + "\n")
            break
        clk, prev, reclaimed = queue_lock.try_lock(os.path.join(claim_dir, row["request_id"] + ".claim"), info)
        if clk is None:
            continue
        try:
            if reclaimed:
                log.write(json.dumps({"event": "claim_reclaimed_from_dead_owner", "request_id": row["request_id"], "prev_owner": prev}) + "\n")
            done = validate_records(read_all(False, live=True), rows, cdig, adapter_digest, pdig, px)  # claim 뒤 재검증 (다른 worker가 방금 끝냈을 수 있다)
            if row["request_id"] in done:
                continue
            try:
                rec = generate.run_request(torch, proc, model, eos_ids, {"id": row["id"], "image": row["image"], "file_sha256": row["file_sha256"]},
                                           row["condition"], row["prompt"])
            except torch.cuda.OutOfMemoryError as e:
                log.write(json.dumps({"event": "oom", "request_id": row["request_id"], "err": str(e)[:200]}) + "\n")
                log.flush()
                raise
            rec.update({"request_id": row["request_id"], "split": row["split"], "checkpoint": row["checkpoint"], "target": row["target"],
                        "fmt": row["fmt"], "condition": row["condition"], "adapter_digest": adapter_digest, "protocol_digest": pdig,
                        "config_digest": cdig, "worker": a.worker, "ts": time.time(), "gpu_uuid": env.get("gpu_uuid"),
                        "stage": row["stage"]})
            with open(out, "a") as f:
                f.write(json.dumps(rec) + "\n")
                f.flush()
                os.fsync(f.fileno())
            done[row["request_id"]] = rec
            n_done += 1
            log.write(json.dumps({"event": "done", "request_id": row["request_id"], "n_out": rec["n_output_tokens"], "finish": rec["finish_reason"],
                                  "runtime_s": round(rec["runtime_s_total"], 2), "peak_gb": round(rec["peak_mem_alloc_gb_max"], 2),
                                  "elapsed": round(time.time() - t0, 1)}) + "\n")
            log.flush()
        finally:
            clk.release()
    print(f"worker {a.worker}: finished; {n_done} new requests this run", flush=True)


if __name__ == "__main__":
    main()
