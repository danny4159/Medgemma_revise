"""iter_041 생성 runner + launcher (pg40_run 기반; pg40_run.py는 iter_040 산출물 검증용으로 수정하지 않고 보존).

pg40_run 대비 iter_041 변경: (1) protocol에 평가 GT manifest·selection lock·평가 소스 등 임의 파일 digest 잠금(--lock),
(2) 부분 행 복구 시 잘라낸 원본 바이트를 별도 파일(.partial.<ts>.bin)로 보존, (3) record에 t_start·worker 타이밍 파일(모델 로딩/종료 시각) 추가,
(4) verify_completion이 현재 영상 file/pixel hash, record 필드-요청 행 일치, 잠금 파일, worker 파일 hash를 모두 재검증,
(5) launcher가 wall·GPU별 점유 구간(device-seconds)을 completion에 기록. iter_039/iter_040 결과·protocol은 읽기만 한다.

worker:  CUDA_VISIBLE_DEVICES=<물리 gpu> python pg41_run.py worker --requests R --protocol P --out-dir D --worker K
launcher: python pg41_run.py launch --requests R --protocol P --out-dir D --workers N [--peak-gb 14]
- 소유권: launch.lock (flock, 프로세스 종료 시 자동 해제) / worker{K}.lock / 요청별 claims/<rid>.claim (flock: 죽은 소유자의 claim은 자동 회수).
- 재개: 시작 시와 claim 직후 모든 기존 record를 요청 행·prompt·config·protocol·현재 영상 pixel hash·record digest와 대조한다.
  중복·잉여·변조는 중단한다. 기존 결과는 덮어쓰지 않는다 (out-dir이 completion을 가지면 재실행 거부).
- GT/labels는 읽지 않는다.
"""
import argparse
import fcntl
import glob
import hashlib
import json
import os
import subprocess
import sys
import time

from rsna_diag import generate as G

CODE_FILES = ["pg41_run.py", "pg39_spec.py", "pg39_data.py", "rsna_diag/generate.py", "rsna_diag/geometry.py",
              "rsna_diag/parse.py", "rsna_diag/prompts.py", "rsna_diag/lora.py", "rsna_diag/queue_lock.py"]
RUNNER = "pg41_run_v1"


class RunError(RuntimeError):
    pass


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def file_sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def canon(o):
    return json.dumps(o, sort_keys=True, ensure_ascii=False, default=str)


def read_requests(path):
    rows = [json.loads(l) for l in open(path) if l.strip()]
    ids = [r["request_id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise RunError("duplicate request_id in requests file")
    return rows


def row_digest(row):
    return sha_bytes(canon(row).encode())


# ---------------- protocol ----------------
def gate_ok(path):
    d = json.load(open(path))
    return d.get("run") is True


def make_protocol(requests_path, out_path, adapter=None, gate=None, extra=None, lock=None):
    """잠금: 코드 파일 hash, 요청 파일 hash, 영상 hash 목록 digest, 생성 config digest, 추가 잠금 파일(GT manifest·평가 소스 등)."""
    rows = read_requests(requests_path)
    core, cdig = static_config()
    locked = {f: file_sha(f) for f in (lock or [])}
    d = {"runner": RUNNER, "locked_files": locked, "code": {f: file_sha(f) for f in CODE_FILES}, "requests_sha256": file_sha(requests_path),
         "requests_path": requests_path, "n_requests": len(rows),
         "images_digest": sha_bytes(canon(sorted({(r["image"], r["image_file_sha256"], r["input_pixel_sha256"])
                                                   for r in rows})).encode()),
         "generation_config_digest": cdig, "generation_config": core, "extra": extra or {}, "adapter": None, "gate": None}
    if adapter:
        import torch
        from rsna_diag import lora
        blob = torch.load(os.path.join(adapter, "adapter.pt"), map_location="cpu", weights_only=True)
        dg = lora.state_digest(blob["state"])
        if dg != blob["digest"]:
            raise RunError("adapter digest mismatch (file corrupted)")
        d["adapter"] = {"path": adapter, "digest": dg, "file_sha256": file_sha(os.path.join(adapter, "adapter.pt"))}
    if gate:
        if not gate_ok(gate):
            raise RunError(f"gate decision does not permit this stage: {gate}")
        d["gate"] = {"decision_path": gate, "decision_sha256": file_sha(gate)}
    if os.path.exists(out_path):
        raise RunError(f"protocol exists: {out_path}")
    tmp = out_path + f".{os.getpid()}.tmp"
    json.dump(d, open(tmp, "w"), indent=1)
    os.replace(tmp, out_path)
    return d


def static_config():
    env = G.static_env()
    core = {k: env[k] for k in G.CFG_KEYS}
    core.update({"caps_IC": [1000, 2000, 4000], "caps_J": [2000, 4000, 8000], "do_sample": False, "runner": RUNNER})
    return core, sha_bytes(canon(core).encode())


def verify_protocol(path, requests_path):
    p = json.load(open(path))
    bad = [f for f, h in p["code"].items() if file_sha(f) != h]
    if bad:
        raise RunError(f"code changed since protocol lock: {bad}")
    badl = [f for f, h in p.get("locked_files", {}).items() if file_sha(f) != h]
    if badl:
        raise RunError(f"locked file changed since protocol lock: {badl}")
    if file_sha(requests_path) != p["requests_sha256"]:
        raise RunError("requests file changed since protocol lock")
    if p.get("adapter") and file_sha(os.path.join(p["adapter"]["path"], "adapter.pt")) != p["adapter"]["file_sha256"]:
        raise RunError("adapter file changed since protocol lock")
    if p.get("gate") and (file_sha(p["gate"]["decision_path"]) != p["gate"]["decision_sha256"] or not gate_ok(p["gate"]["decision_path"])):
        raise RunError("stage gate decision missing/changed/not permitting")
    return sha_bytes(canon(p).encode()), p


# ---------------- record validation ----------------
def record_digest(rec):
    return sha_bytes(canon({k: v for k, v in rec.items() if k != "record_digest"}).encode())


def read_records(path):
    """완결된 행(개행으로 끝난 행)만 읽는다. 다른 worker가 쓰는 중인 마지막 부분 행은 무시한다. 중간 행이 깨져 있으면 예외."""
    out = []
    if os.path.exists(path):
        with open(path, "rb") as f:
            data = f.read()
        for ln in data.split(b"\n")[:-1]:
            if ln.strip():
                out.append(json.loads(ln))
    return out


def repair_tail(path):
    """자신의 파일 끝에 개행 없는 부분 행이 있으면(이전 프로세스 비정상 종료) 잘라내고 잘라낸 바이트 수를 반환한다."""
    if not os.path.exists(path):
        return 0
    with open(path, "rb") as f:
        data = f.read()
    tail = data.rsplit(b"\n", 1)[-1] if b"\n" in data else data
    if not data.endswith(b"\n") and tail:
        ts = time.time()
        keep = f"{path}.partial.{int(ts)}.{os.getpid()}.bin"
        with open(keep, "xb") as f:  # 원본 바이트 보존 (덮어쓰기 금지)
            f.write(tail)
            f.flush()
            os.fsync(f.fileno())
        with open(path, "r+b") as f:
            f.truncate(len(data) - len(tail))
        with open(path + ".repair.log", "a") as f:
            f.write(json.dumps({"ts": ts, "truncated_bytes": len(tail), "preserved_as": keep,
                                "preserved_sha256": sha_bytes(tail)}) + "\n")
        return len(tail)
    return 0


def validate_records(files, rows_by_id, pdig, cdig, px, adig=None):
    """files {path: [records]}. returns {request_id: record}. 이상이 있으면 RunError."""
    done = {}
    for fn, recs in files.items():
        for r in recs:
            rid = r.get("request_id")
            row = rows_by_id.get(rid)
            if row is None:
                raise RunError(f"unexpected record {rid} in {fn}")
            if rid in done:
                raise RunError(f"duplicate record {rid} in {fn}")
            if r.get("record_digest") != record_digest(r):
                raise RunError(f"record digest mismatch (tampered?) {rid} in {fn}")
            if r.get("row_digest") != row_digest(row) or r.get("prompt_sha256") != row["prompt_sha256"]:
                raise RunError(f"request row/prompt mismatch {rid}")
            if r.get("adapter_digest") != adig:
                raise RunError(f"adapter digest mismatch {rid}")
            if r.get("protocol_digest") != pdig or r.get("config_digest") != cdig:
                raise RunError(f"protocol/config mismatch {rid}")
            if r.get("input_pixel_sha256") != row["input_pixel_sha256"] or px(row["image"]) != row["input_pixel_sha256"]:
                raise RunError(f"input pixel hash mismatch {rid}")
            if any(r.get(k) != row[k] for k in ("cond", "patient", "targets", "kind", "image")):
                raise RunError(f"record identity fields != request row {rid}")
            done[rid] = r
    return done


# ---------------- worker ----------------
def try_flock(path):
    fd = os.open(path, os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    os.ftruncate(fd, 0)
    os.write(fd, json.dumps({"pid": os.getpid(), "ts": time.time()}).encode())
    return fd


def worker_main(a):
    pdig, proto = verify_protocol(a.protocol, a.requests)
    rows = read_requests(a.requests)
    rows_by_id = {r["request_id"]: r for r in rows}
    os.makedirs(a.out_dir, exist_ok=True)
    if os.path.exists(os.path.join(a.out_dir, "completion.json")):
        raise RunError("completion.json exists: refuse to rerun into a completed out-dir")
    wl = try_flock(os.path.join(a.out_dir, f"worker{a.worker}.lock"))
    if wl is None:
        sys.exit(f"worker {a.worker} already running")
    t_proc_start = time.time()
    torch, proc, model = G.load_model()
    adig = None
    if proto.get("adapter"):
        adig = G.load_adapter(torch, model, proto["adapter"]["path"])
        if adig != proto["adapter"]["digest"]:
            sys.exit("loaded adapter digest != protocol")
    t_model_ready = time.time()
    env = G.env_info(torch, proc, model)
    core = {k: env[k] for k in G.CFG_KEYS}
    core.update({"caps_IC": [1000, 2000, 4000], "caps_J": [2000, 4000, 8000], "do_sample": False, "runner": RUNNER})
    cdig = sha_bytes(canon(core).encode())
    if cdig != proto["generation_config_digest"]:
        sys.exit("runtime generation config digest != protocol")
    eos = env["eos_token_id"]
    eos_ids = set(eos if isinstance(eos, list) else [eos])
    envp = os.path.join(a.out_dir, f"gen_worker{a.worker}.jsonl.env.json")
    if not os.path.exists(envp):
        json.dump({"env": env, "config_digest": cdig, "protocol_digest": pdig, "worker": a.worker,
                   "physical_cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES")}, open(envp, "w"),
                  indent=1, default=str)
    cache = {}

    def px(path):
        if path not in cache:
            cache[path] = G.load_image(path)[2]
        return cache[path]

    def read_all():
        return {f: read_records(f) for f in sorted(glob.glob(os.path.join(a.out_dir, "gen_worker*.jsonl")))}

    out = os.path.join(a.out_dir, f"gen_worker{a.worker}.jsonl")
    repair_tail(out)
    done = validate_records(read_all(), rows_by_id, pdig, cdig, px, adig)
    cdir = os.path.join(a.out_dir, "claims")
    os.makedirs(cdir, exist_ok=True)
    log = open(out + ".log", "a")
    t0, n_new = time.time(), 0
    for row in sorted(rows, key=lambda r: r["order_key"]):
        if row["request_id"] in done:
            continue
        if a.max_requests is not None and n_new >= a.max_requests:
            break
        fd = try_flock(os.path.join(cdir, row["request_id"] + ".claim"))
        if fd is None:
            continue
        try:
            done = validate_records(read_all(), rows_by_id, pdig, cdig, px, adig)
            if row["request_id"] in done:
                continue
            tw = time.time()
            t_start_req = tw
            try:
                image, aff, pxs = G.load_image(row["image"])
                inp = G.build_inputs(proc, image, row["prompt"])
                ids_in = inp["input_ids"][0].tolist()
                attempts = []
                for cap in row["caps"]:
                    at = G.generate(torch, proc, model, inp, cap, eos_ids)
                    if attempts:
                        at["prefix_matches_previous"] = at["suffix_ids"][:len(attempts[-1]["suffix_ids"])] == attempts[-1]["suffix_ids"]
                    attempts.append(at)
                    if at["ended_eos"]:
                        break
            except torch.cuda.OutOfMemoryError as e:
                log.write(json.dumps({"event": "oom", "rid": row["request_id"], "err": str(e)[:200]}) + "\n")
                log.flush()
                raise
            fin = attempts[-1]
            for at in attempts:
                at["suffix_text_raw"] = proc.tokenizer.decode(at["suffix_ids"], skip_special_tokens=False)
            rec = {"request_id": row["request_id"], "row_digest": row_digest(row), "cond": row["cond"],
                   "patient": row["patient"], "targets": row["targets"], "kind": row["kind"],
                   "prompt_sha256": row["prompt_sha256"], "image": row["image"],
                   "input_pixel_sha256": pxs, "pad_affine_top_left_side": list(aff),
                   "n_input_tokens": len(ids_in), "input_ids_sha256": sha_bytes(json.dumps(ids_in).encode()),
                   "suffix_ids": fin["suffix_ids"], "suffix_text_raw": fin["suffix_text_raw"],
                   "n_output_tokens": fin["n_new"], "finish_reason": fin["finish_reason"], "ended_eos": fin["ended_eos"],
                   "final_cap": fin["cap"],
                   "attempts": [{k: v for k, v in at.items() if k != "suffix_ids"} for at in attempts],
                   "runtime_s_total": sum(at["runtime_s"] for at in attempts), "wall_s": time.time() - tw, "t_start": t_start_req,
                   "peak_mem_alloc_gb_max": max(at["peak_mem_alloc_gb"] for at in attempts),
                   "peak_mem_reserved_gb_max": max(at["peak_mem_reserved_gb"] for at in attempts),
                   "protocol_digest": pdig, "config_digest": cdig, "adapter_digest": adig, "worker": a.worker, "ts": time.time(),
                   "gpu_uuid": env.get("gpu_uuid")}
            rec["record_digest"] = record_digest(rec)
            with open(out, "a") as f:
                f.write(json.dumps(rec) + "\n")
                f.flush()
                os.fsync(f.fileno())
            done[row["request_id"]] = rec
            n_new += 1
            log.write(json.dumps({"event": "done", "rid": row["request_id"], "cond": row["cond"], "n_out": rec["n_output_tokens"],
                                  "finish": rec["finish_reason"], "runtime_s": round(rec["runtime_s_total"], 1),
                                  "peak_gb": round(rec["peak_mem_alloc_gb_max"], 2), "elapsed": round(time.time() - t0, 1)}) + "\n")
            log.flush()
        finally:
            os.close(fd)
    tp = os.path.join(a.out_dir, f"worker{a.worker}.timing.{int(t_proc_start)}.{os.getpid()}.json")
    json.dump({"worker": a.worker, "pid": os.getpid(), "t_proc_start": t_proc_start, "t_model_ready": t_model_ready,
               "t_end": time.time(), "n_new": n_new, "load_s": t_model_ready - t_proc_start,
               "physical_cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES")}, open(tp, "x"), indent=1)
    print(f"worker {a.worker}: finished; {n_new} new requests", flush=True)


# ---------------- launcher ----------------
def gpu_free_mib():
    r = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,memory.total", "--format=csv,noheader,nounits"],
                       capture_output=True, text=True, check=True)
    return {int(l.split(",")[0]): (int(l.split(",")[2]) - int(l.split(",")[1])) for l in r.stdout.strip().splitlines()}


def allowed_gpus():
    v = os.environ.get("CUDA_VISIBLE_DEVICES")
    if not v:
        raise RunError("CUDA_VISIBLE_DEVICES not set; refusing to pick devices")
    return [int(x) for x in v.split(",")]


def verify_completion(out_dir, requests_path, protocol_path):
    """평가 진입점용: completion 내용·요청 집합·record digest를 다시 검증한다. returns records list."""
    comp = json.load(open(os.path.join(out_dir, "completion.json")))
    pdig, proto = verify_protocol(protocol_path, requests_path)
    rows = read_requests(requests_path)
    rows_by_id = {r["request_id"]: r for r in rows}
    if comp.get("protocol_digest") != pdig or any(c != 0 for c in comp["exit_codes"]):
        raise RunError("completion protocol/exit code invalid")
    recs = []
    for fn in sorted(glob.glob(os.path.join(out_dir, "gen_worker*.jsonl"))):
        if comp["worker_file_sha256"].get(os.path.basename(fn)) != file_sha(fn):
            raise RunError(f"worker file changed after completion: {fn}")
        recs += read_records(fn)
    ids = [r["request_id"] for r in recs]
    if len(ids) != len(set(ids)) or set(ids) != set(rows_by_id) or len(ids) != comp["n_requests"]:
        raise RunError("completion: request set mismatch (missing/duplicate/extra)")
    want_ad = (proto.get("adapter") or {}).get("digest")
    files_now = sorted(os.path.basename(f) for f in glob.glob(os.path.join(out_dir, "gen_worker*.jsonl")))
    if files_now != sorted(comp["worker_file_sha256"]):
        raise RunError("completion: worker file set differs from completion record")
    img_ok = {}
    for r in recs:
        row = rows_by_id[r["request_id"]]
        if r["record_digest"] != record_digest(r) or r["row_digest"] != row_digest(row):
            raise RunError("completion: record digest mismatch")
        if r.get("adapter_digest") != want_ad or r.get("protocol_digest") != pdig:
            raise RunError("completion: adapter/protocol digest mismatch in record")
        if r.get("config_digest") != proto["generation_config_digest"]:
            raise RunError("completion: generation config digest mismatch in record")
        if r.get("prompt_sha256") != row["prompt_sha256"] or sha_bytes(row["prompt"].encode()) != row["prompt_sha256"]:
            raise RunError("completion: prompt hash mismatch")
        if any(r.get(k) != row[k] for k in ("cond", "patient", "targets", "kind", "image")):
            raise RunError("completion: record identity fields != request row")
        if row["image"] not in img_ok:  # 현재 영상 file/pixel hash 재검증
            if file_sha(row["image"]) != row["image_file_sha256"]:
                raise RunError(f"completion: current image file hash mismatch {row['image']}")
            img_ok[row["image"]] = G.load_image(row["image"])[2]
        if img_ok[row["image"]] != row["input_pixel_sha256"] or r["input_pixel_sha256"] != row["input_pixel_sha256"]:
            raise RunError(f"completion: current image pixel hash mismatch {row['image']}")
    return recs


def _union_len(iv):
    iv = sorted(iv)
    tot, cur_s, cur_e = 0.0, None, None
    for s_, e_ in iv:
        if cur_e is None or s_ > cur_e:
            if cur_e is not None:
                tot += cur_e - cur_s
            cur_s, cur_e = s_, e_
        else:
            cur_e = max(cur_e, e_)
    if cur_e is not None:
        tot += cur_e - cur_s
    return tot


def occupancy(recs, out_dir, mapping, launcher_wall_s):
    """GPU별로 worker 요청 구간(t_start~ts)의 합집합 길이(겹침은 중복 합산 안 함)와 worker 프로세스 구간(모델 로딩 포함)의 합집합을 합산한다."""
    gpu_of = {k: mapping[k] for k in mapping}
    req_iv, proc_iv = {}, {}
    for r in recs:
        g = gpu_of[r["worker"]]
        req_iv.setdefault(g, []).append((r["t_start"], r["ts"]))
    for fn in glob.glob(os.path.join(out_dir, "worker*.timing.*.json")):
        t = json.load(open(fn))
        g = gpu_of[t["worker"]]
        proc_iv.setdefault(g, []).append((t["t_proc_start"], t["t_end"]))
    tmin = min(s_ for iv in req_iv.values() for s_, _ in iv)
    tmax = max(e_ for iv in req_iv.values() for _, e_ in iv)
    return {"device_seconds_generate_union": sum(_union_len(iv) for iv in req_iv.values()),
            "device_seconds_incl_loading_union": sum(_union_len(iv) for iv in proc_iv.values()) if proc_iv else None,
            "n_gpus_used": len(req_iv), "first_request_start_to_last_end_s": tmax - tmin,
            "launcher_wall_s_incl_loading": launcher_wall_s}


def launch_main(a):
    pdig, proto = verify_protocol(a.protocol, a.requests)
    os.makedirs(a.out_dir, exist_ok=True)
    if os.path.exists(os.path.join(a.out_dir, "completion.json")):
        raise RunError("completion.json exists in out-dir; use a new attempt dir")
    lk = try_flock(os.path.join(a.out_dir, "launch.lock"))
    if lk is None:
        sys.exit("another launcher owns this out-dir")
    gpus = allowed_gpus()
    if a.gpus:
        sel = [int(x) for x in a.gpus.split(",")]
        if not set(sel) <= set(gpus):
            sys.exit(f"--gpus {sel} not within inherited allowed set {gpus}")
        gpus = sel
    free = gpu_free_mib()
    per = {}
    for k in range(a.workers):
        g = gpus[k % len(gpus)]
        per.setdefault(g, []).append(k)
    for g, ws in per.items():
        need = len(ws) * (a.peak_gb + 2.0) * 1024
        if free[g] < need:
            sys.exit(f"gpu {g}: free {free[g]}MiB < need {need:.0f}MiB for workers {ws}")
    mapping = {k: gpus[k % len(gpus)] for k in range(a.workers)}
    json.dump({"mapping_worker_to_physical_gpu": mapping, "free_mib_before": free, "allowed": gpus,
               "peak_gb_assumed": a.peak_gb}, open(os.path.join(a.out_dir, "launch_children.json"), "w"), indent=1)
    procs = {}
    t0 = time.time()
    for k in range(a.workers):
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(mapping[k]))
        cmd = [sys.executable, "pg41_run.py", "worker", "--requests", a.requests, "--protocol", a.protocol,
               "--out-dir", a.out_dir, "--worker", str(k)]
        if a.max_requests is not None:
            cmd += ["--max-requests", str(a.max_requests)]
        procs[k] = subprocess.Popen(cmd, env=env, stdout=open(os.path.join(a.out_dir, f"worker{k}.stdout"), "a"),
                                    stderr=open(os.path.join(a.out_dir, f"worker{k}.stderr"), "a"))
    rl = open(os.path.join(a.out_dir, "resource_log.jsonl"), "a")
    while any(p.poll() is None for p in procs.values()):
        time.sleep(15)
        used = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
                              capture_output=True, text=True).stdout.strip().splitlines()
        rl.write(json.dumps({"t": round(time.time() - t0, 1), "gpu": used}) + "\n")
        rl.flush()
    codes = [procs[k].returncode for k in range(a.workers)]
    wall = time.time() - t0
    rows = read_requests(a.requests)
    recs = []
    for fn in sorted(glob.glob(os.path.join(a.out_dir, "gen_worker*.jsonl"))):
        recs += read_records(fn)
    n_done = len({r["request_id"] for r in recs})
    allr = [r for r in recs]
    cost = {"sum_request_wall_s": sum(r["wall_s"] for r in allr), "sum_generate_runtime_s": sum(r["runtime_s_total"] for r in allr),
            "n_records_with_retry": sum(len(r["attempts"]) > 1 for r in allr),
            "new_tokens_all_attempts": sum(at["n_new"] for r in allr for at in r["attempts"]),
            "new_tokens_final": sum(r["n_output_tokens"] for r in allr)}
    cost.update(occupancy(recs, out_dir=a.out_dir, mapping=mapping, launcher_wall_s=wall))
    res = {"cost": cost, "exit_codes": codes, "wall_s": wall, "n_records": len(recs), "n_unique": n_done, "n_requests": len(rows),
           "workers": a.workers, "mapping": mapping, "protocol_digest": pdig}
    if a.max_requests is None and all(c == 0 for c in codes) and n_done == len(rows) == len(recs):
        res["worker_file_sha256"] = {os.path.basename(f): file_sha(f)
                                     for f in sorted(glob.glob(os.path.join(a.out_dir, "gen_worker*.jsonl")))}
        tmp = os.path.join(a.out_dir, f"completion.{os.getpid()}.tmp")
        json.dump(res, open(tmp, "w"), indent=1)
        os.replace(tmp, os.path.join(a.out_dir, "completion.json"))
        print("completion written", json.dumps({k: res[k] for k in ("exit_codes", "wall_s", "n_unique")}))
    else:
        json.dump(res, open(os.path.join(a.out_dir, f"partial_{int(time.time())}.json"), "w"), indent=1)
        print("NOT complete", json.dumps({k: res[k] for k in ("exit_codes", "wall_s", "n_unique", "n_requests")}))
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("worker")
    l = sub.add_parser("launch")
    pp = sub.add_parser("protocol")
    pp.add_argument("--requests", required=True)
    pp.add_argument("--out", required=True)
    pp.add_argument("--adapter", default=None, help="adapter 디렉터리 (adapter.pt 포함)")
    pp.add_argument("--gate", default=None, help="run=true decision artifact (후속 단계만)")
    pp.add_argument("--lock", nargs="*", default=[], help="추가로 hash 잠글 파일 (GT manifest, selection lock, 평가 소스 등)")
    for s in (w, l):
        s.add_argument("--requests", required=True)
        s.add_argument("--protocol", required=True)
        s.add_argument("--out-dir", required=True)
        s.add_argument("--max-requests", type=int, default=None)
    w.add_argument("--worker", type=int, required=True)
    l.add_argument("--workers", type=int, required=True)
    l.add_argument("--gpus", default=None, help="허용 집합 안의 부분집합 (예: 0 또는 0,1)")
    l.add_argument("--peak-gb", type=float, default=14.0)
    a = ap.parse_args()
    if a.cmd == "protocol":
        make_protocol(a.requests, a.out, adapter=a.adapter, gate=a.gate, lock=a.lock)
        return
    (worker_main if a.cmd == "worker" else launch_main)(a)


if __name__ == "__main__":
    main()
