"""iter_019 다중 영상 생성 worker. qa_gen.py의 재개·claim·검증 패턴을 다중 image 요청에 맞게 일반화한다.

- 시작 시: mi19_protocol.verify, 요청 파일이 protocol에 잠긴 파일과 같은지, 각 행의 request_id 재계산·config digest,
  모든 영상의 현재 file/pixel hash(raw file sha256 + padded 이후 hash는 generate.load_image가 재계산).
- 재개: 완료 record 포함 모든 worker 파일을 요청 행과 대조. 중복·잉여·id/prompt/images/config 불일치·입력 변경·잘린 JSONL은 중단.
사용: CUDA_VISIBLE_DEVICES=<gpu> python -m rsna_diag.mi19_gen --requests R --out-dir D --worker K --protocol P
"""
import argparse
import glob
import json
import os
import re
import sys
import time

from . import generate, mi19_protocol, mi19_requests as Q, queue_lock


class GenError(RuntimeError):
    pass


def read_strict(path, repair_tail=False, tolerate_tail=False):
    if not os.path.exists(path):
        return []
    raw = open(path, "rb").read()
    lines = raw.split(b"\n")
    tail = lines[-1]
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
            raise GenError(f"truncated last line (no newline) in {path}; rerun with --repair-tail")
    recs = []
    for k, ln in enumerate(body):
        if ln.strip():
            try:
                recs.append(json.loads(ln))
            except ValueError as e:
                raise GenError(f"corrupt JSON line {k} in {path}") from e
    return recs


def _worker_of(path):
    m = re.fullmatch(r"gen_worker(\d+)\.jsonl", os.path.basename(path))
    return int(m.group(1)) if m else None


def _has_tail(path):
    if not os.path.exists(path):
        return False
    data = open(path, "rb").read()
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


def validate_records(files_records, rows, cdig, protocol_digest, pixel_sha):
    by = {r["request_id"]: r for r in rows}
    done = {}
    for fn, recs in files_records.items():
        for r in recs:
            rid = r.get("request_id")
            row = by.get(rid)
            if row is None:
                raise GenError(f"unexpected record {rid} in {fn}: not in current request set")
            if rid in done:
                raise GenError(f"duplicate record {rid} in {fn}")
            for k, want in (("prompt_sha256", row["prompt_sha256"]), ("config_digest", cdig),
                            ("protocol_digest", protocol_digest), ("patient", row["patient"]),
                            ("condition", row["condition"]), ("label", row["label"]), ("n_images", len(row["images"]))):
                if r.get(k) != want:
                    raise GenError(f"{k} mismatch for {rid} in {fn}: {r.get(k)!r} != {want!r}")
            for i, im in enumerate(row["images"]):
                rim = r["images"][i]
                if rim.get("file_sha256") != im["file_sha256"] or rim.get("path") != im["path"]:
                    raise GenError(f"image[{i}] mismatch for {rid} in {fn}")
                if rim.get("input_pixel_sha256") != pixel_sha(im["path"]):
                    raise GenError(f"input image changed since generation for {rid} image[{i}]")
            done[rid] = r
    return done


def check_inputs(rows):
    seen = {}
    for r in rows:
        for im in r["images"]:
            key = im["path"]
            if key in seen:
                continue
            if generate.sha(open(key, "rb").read()) != im["file_sha256"]:
                raise GenError(f"file sha changed for {key}")
            seen[key] = 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--requests", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--worker", type=int, required=True)
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--time-limit", type=float, default=None)
    ap.add_argument("--max-requests", type=int, default=None)
    ap.add_argument("--repair-tail", action="store_true")
    a = ap.parse_args()
    pdig = mi19_protocol.verify(a.protocol)
    if json.load(open(a.protocol))["locked"]["files"].get(a.requests) != generate.sha(open(a.requests, "rb").read()):
        sys.exit(f"request file {a.requests} is not locked in {a.protocol} (or changed)")
    cfg, _ = mi19_protocol.static_cfg()
    rows = Q.load_rows(a.requests, cfg)
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
    env = generate.env_info(torch, proc, model)
    cdig, core = generate.config_digest(env, {})
    if cdig != cfg:
        raise GenError("runtime generation config digest != protocol config digest")
    eos = env["eos_token_id"]
    eos_ids = set(eos if isinstance(eos, list) else [eos])
    with open(os.path.join(a.out_dir, f"gen_worker{a.worker}.jsonl.env.json"), "w") as f:
        json.dump({"env": env, "config_digest": cdig, "protocol_digest": pdig, "worker": a.worker,
                   "requests": a.requests}, f, indent=1, default=str)
    cache = {}

    def px(path):
        if path not in cache:
            cache[path] = generate.load_image(path)[2]
        return cache[path]

    def read_all(repair, live=False):
        return read_all_owned(a.out_dir, a.worker, repair, live, info)

    done = validate_records(read_all(a.repair_tail), rows, cdig, pdig, px)
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
            done = validate_records(read_all(False, live=True), rows, cdig, pdig, px)
            if row["request_id"] in done:
                continue
            try:
                rec = generate.run_request_multi(torch, proc, model, eos_ids,
                                                 {"id": row["id"], "images": row["images"]}, row["condition"], row["prompt"])
            except torch.cuda.OutOfMemoryError as e:
                log.write(json.dumps({"event": "oom", "request_id": row["request_id"], "err": str(e)[:200]}) + "\n")
                log.flush()
                raise
            rec.update({"request_id": row["request_id"], "patient": row["patient"], "condition": row["condition"],
                        "label": row["label"], "config_digest": cdig, "protocol_digest": pdig, "worker": a.worker,
                        "ts": time.time(), "gpu_uuid": env.get("gpu_uuid")})
            with open(out, "a") as f:
                f.write(json.dumps(rec) + "\n")
                f.flush()
                os.fsync(f.fileno())
            done[row["request_id"]] = rec
            n_done += 1
            log.write(json.dumps({"event": "done", "request_id": row["request_id"], "n_out": rec["n_output_tokens"],
                                  "finish": rec["finish_reason"], "runtime_s": round(rec["runtime_s_total"], 2),
                                  "peak_gb": round(rec["peak_mem_alloc_gb_max"], 2), "elapsed": round(time.time() - t0, 1)}) + "\n")
            log.flush()
        finally:
            clk.release()
    print(f"worker {a.worker}: finished; {n_done} new requests this run", flush=True)


if __name__ == "__main__":
    main()
