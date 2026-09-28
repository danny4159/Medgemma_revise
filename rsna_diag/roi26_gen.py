"""iter_026 전용 생성 worker (roi25_gen.py 기반, 동일 claim/재개/변조 거부 규약)."""
import argparse
import glob
import json
import os
import re
import sys
import time

from . import generate, roi26_protocol as qa_protocol, roi26_requests as Q, queue_lock


class QAError(RuntimeError):
    pass


def read_strict(path, repair_tail=False, tolerate_tail=False):
    if not os.path.exists(path):
        return []
    raw = open(path, "rb").read()
    lines = raw.split(b"\n")
    tail = lines[-1]
    recs = []
    body = lines[:-1]
    if tail.strip() and tolerate_tail:
        pass
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
    out = {}
    for f in sorted(glob.glob(os.path.join(out_dir, "gen_worker*.jsonl"))):
        w = _worker_of(f)
        if w == my_worker or not _has_tail(f):
            out[f] = read_strict(f, repair_tail=repair and w == my_worker and not live)
            continue
        lk, _, _ = queue_lock.try_lock(os.path.join(out_dir, f"worker{w}.lock"), info)
        if lk is None:
            out[f] = read_strict(f, tolerate_tail=True)
        else:
            try:
                out[f] = read_strict(f, repair_tail=repair and not live, tolerate_tail=live)
            finally:
                lk.release()
    return out


def validate_records(files_records, rows, cdig, adapter_digest, protocol_digest, pixel_sha):
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
            for k, want in (("prompt_sha256", row["prompt_sha256"]), ("adapter_digest", adapter_digest),
                            ("config_digest", cdig), ("protocol_digest", protocol_digest), ("id", row["id"]),
                            ("condition", row["condition"]), ("checkpoint", row["checkpoint"]),
                            ("target", row["target"]), ("modality", row["modality"])):
                if r.get(k) != want:
                    raise QAError(f"{k} mismatch for {rid} in {fn}: {r.get(k)!r} != {want!r}")
            if row["modality"] == "image":
                if r.get("image_file_sha256") != row["file_sha256"]:
                    raise QAError(f"image_file_sha256 mismatch for {rid} in {fn}")
                if r.get("input_pixel_sha256") != pixel_sha(row["image"]):
                    raise QAError(f"input image changed since generation for {rid}")
            else:
                if r.get("image") is not None or r.get("image_file_sha256") is not None or r.get("input_pixel_sha256") is not None:
                    raise QAError(f"text-only record {rid} in {fn} carries image fields")
            done[rid] = r
    return done


def check_inputs(rows):
    from . import inputs
    seen = {}
    for r in rows:
        if r["modality"] == "text":
            if r.get("image") is not None or r.get("file_sha256") is not None or r.get("pixel_sha256") is not None:
                raise QAError(f"text-only row {r['id']}/{r['request_id']} carries image fields")
            continue
        if r["modality"] != "image":
            raise QAError(f"unknown modality {r['modality']!r} for {r['request_id']}")
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
    ap.add_argument("--allowed-edits", default=None,
                    help="생성과 무관한 코드(예: 평가 전용 파일)의 사전 검토된 hash 변경을 허용하는 JSON 파일 경로")
    a = ap.parse_args()
    allowed_edits = json.load(open(a.allowed_edits)) if a.allowed_edits else None
    pdig = qa_protocol.verify(a.protocol, allowed_edits=allowed_edits)
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
            done = validate_records(read_all(False, live=True), rows, cdig, adapter_digest, pdig, px)
            if row["request_id"] in done:
                continue
            try:
                rec = generate.run_request_modal(torch, proc, model, eos_ids, row)
            except torch.cuda.OutOfMemoryError as e:
                log.write(json.dumps({"event": "oom", "request_id": row["request_id"], "err": str(e)[:200]}) + "\n")
                log.flush()
                raise
            rec.update({"request_id": row["request_id"], "split": row["split"], "checkpoint": row["checkpoint"],
                        "target": row["target"], "condition": row["condition"],
                        "adapter_digest": adapter_digest, "protocol_digest": pdig, "config_digest": cdig,
                        "worker": a.worker, "ts": time.time(), "gpu_uuid": env.get("gpu_uuid"), "stage": row["stage"],
                        "modality": row["modality"]})
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
