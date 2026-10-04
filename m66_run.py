"""iter_066 W 질문 F/J 두 후보(PRESENT/ABSENT) answer-likelihood scoring runner.

재사용(반입본): msd56_run(load_model/env_info/build_inputs=iter_065 생성과 동일 입력), mc54_run(extend_inputs/hidden_last/head_fp32),
pg43_run(sha/canon/read_records/repair_tail/try_flock/_union_len/allowed_gpus/gpu_free_mib).
쓰지 않는 것: 과거 worker/launcher/비용 sidecar/완료 판정, MediConfusion CLI, 단일 영상 prefix.

점수 정의(고정): 후보 문자열 y의 score = 답변 token 위치 평균 log P (prefix·EOS 제외), bf16 hidden → fp32 lm_head → log_softmax.
선택은 평가기에서만(PRESENT mean_ll > ABSENT mean_ll이면 PRESENT, 동률 ABSENT). worker는 GT/labels를 읽지 않는다.

서브명령: build | protocol | tech | worker | launch
소유권: out-dir launch.lock / worker{K}.lock / claims/<rid>.claim(flock, 죽은 소유자 자동 회수). 재개: 모든 기존 record를 현재 요청·protocol·config로 재검증.
"""
import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys
import time

os.environ.setdefault("HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import msd56_run as M  # noqa: E402
import mc54_run as C  # noqa: E402
import pg43_run as P43  # noqa: E402

RUNNER = "m66_run_v1"
ROOT = "results/iter_066"
SRC65 = "results/iter_065"
CANDS = ["PRESENT", "ABSENT"]
CODE_FILES = ["m66_run.py", "m65_data.py", "msd56_data.py", "msd56_run.py", "mc54_run.py", "pg43_run.py", "rsna_diag/generate.py"]
CONDS = ("F", "J")
# 사전 고정한 기술 검사 허용 오차(구현 시점, 어떤 E 결과도 보기 전)
TOL_INDEP_MEAN = 2e-2   # 결합 forward vs 독립 token-by-token fp32 head 평균 log-prob 차이(nats)
TOL_NATIVE = 0.15       # fp32 head vs 모델 native bf16 logits head
TOL_BATCH = 5e-2        # 후보 batch2(right-padding) vs batch1 평균 log-prob 차이
RunError = P43.RunError
sha_bytes, file_sha, canon, record_digest = P43.sha_bytes, P43.file_sha, P43.canon, P43.record_digest
read_records, repair_tail, try_flock = P43.read_records, P43.repair_tail, P43.try_flock
EVAL_KEYS = ("gt", "answer", "label", "truth", "coverage", "pred")


def jl(p):
    return [json.loads(l) for l in open(p) if l.strip()]


def row_digest(row):
    return sha_bytes(canon(row).encode())


def atomic_write_json(path, obj):
    if os.path.exists(path):
        raise RunError(f"refuse to overwrite {path}")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "x") as f:
        json.dump(obj, f, indent=1, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# ---------------- requests ----------------
def read_requests(path):
    rows = jl(path)
    ids = [r["request_id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise RunError("duplicate request_id")
    for r in rows:
        if any(k in r for k in EVAL_KEYS):
            raise RunError(f"inference row carries evaluation field {r['request_id']}")
        if r["q"] != "W" or r["cond"] not in CONDS or r["candidates"] != CANDS:
            raise RunError(f"bad row {r['request_id']}")
        if len(r["images"]) != (16 if r["cond"] == "J" else 8) or len(r["images"]) != len(r["image_file_sha256"]):
            raise RunError(f"image count {r['request_id']}")
        if r["prompt_sha256"] != sha_bytes(r["prompt"].encode()):
            raise RunError(f"prompt hash {r['request_id']}")
    return rows


def cmd_build(a):
    """iter_065 requests/target_manifest(읽기 전용)에서 W×{F,J} 요청만 추출. labels는 읽지 않는다."""
    import m65_data as S
    src = jl(f"{SRC65}/data/requests_{a.split}.jsonl")
    tm = json.load(open(f"{SRC65}/data/target_manifest_{a.split}.json"))
    by = {(t["case"], t["slab"]): t for t in tm["slabs"]}
    out = []
    for r in src:
        if r["q"] != "W" or r["cond"] not in CONDS:
            continue
        t = by[(r["case"], r["slab"])]
        F, T = t["F_png"], t["T_png"]
        want = F if r["cond"] == "F" else [x for pr in zip(F, T) for x in pr]
        shas = t["F_png_sha256"] if r["cond"] == "F" else [x for pr in zip(t["F_png_sha256"], t["T_png_sha256"]) for x in pr]
        if r["images"] != want or r["prompt"] != S.prompt(r["cond"], "W"):
            raise RunError(f"source row != manifest {r['rid']}")
        if [file_sha(p) for p in r["images"]] != shas:
            raise RunError(f"png hash != manifest {r['rid']}")
        out.append({"request_id": r["rid"], "case": r["case"], "slab": r["slab"], "q": "W", "cond": r["cond"], "images": r["images"],
                    "image_file_sha256": shas, "prompt": r["prompt"], "prompt_sha256": sha_bytes(r["prompt"].encode()),
                    "candidates": CANDS, "order_key": sha_bytes(("m66|" + r["rid"]).encode())})
    if os.path.exists(a.out):
        raise RunError("refuse to overwrite " + a.out)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    tmp = a.out + ".tmp"
    with open(tmp, "x") as f:
        for r in out:
            f.write(json.dumps(r) + "\n")
    os.replace(tmp, a.out)
    print(a.split, "rows", len(out), "cases", len({r["case"] for r in out}))


# ---------------- protocol ----------------
def model_file_digest():
    """모델 snapshot 파일 size+sha256. (size, mtime_ns)가 같으면 캐시된 sha 사용, 아니면 재hash."""
    import m65_run as R
    cache_p = f"{ROOT}/protocol/model_files_cache.json"
    cache = json.load(open(cache_p)) if os.path.exists(cache_p) else {}
    st = R.model_files("medgemma", False)
    out, dirty = {}, False
    for f, ent in st.items():
        c = cache.get(f)
        if c and c["size"] == ent["size"] and c["mtime_ns"] == ent["mtime_ns"]:
            out[f] = c
        else:
            real = os.path.realpath(os.path.join(R.snapshot_dir("medgemma"), f))
            out[f] = {**ent, "sha256": file_sha(real)}
            dirty = True
    if dirty:
        os.makedirs(os.path.dirname(cache_p), exist_ok=True)
        tmp = f"{cache_p}.{os.getpid()}.tmp"
        json.dump(out, open(tmp, "w"), indent=1)
        os.replace(tmp, cache_p)
    return out


def static_config(cand_batch):
    core = {"model_id": M.MODEL_ID, "model_revision": M.MODEL_REVISION, "dtype": "bfloat16", "runner": RUNNER, "candidates": CANDS,
            "score": "mean token logP over answer tokens; bf16 hidden -> fp32 lm_head -> log_softmax; EOS/prefix excluded",
            "cand_batch": cand_batch, "input": "msd56_run.build_inputs (iter_065 generation 입력과 동일)"}
    return core, sha_bytes(canon(core).encode())


def eval_lock_files(stage):
    s = {"D": "D", "E12": "E12", "E36": "E36"}[stage.split("_")[0]]
    d = [f"{SRC65}/data/labels_{s}.json", f"{SRC65}/data/target_manifest_{s}.json", f"{SRC65}/data/requests_{s}.jsonl",
         "results/iter_056/data/cases.json", "results/iter_056/data/case_order.json"]
    return d


def make_protocol(stage, requests_path, out_path, cand_batch, gate=None):
    rows = read_requests(requests_path)
    core, cdig = static_config(cand_batch)
    mf = model_file_digest()
    imgs = sorted({(p, h) for r in rows for p, h in zip(r["images"], r["image_file_sha256"])})
    for p, h in imgs:
        if file_sha(p) != h:
            raise RunError(f"image changed {p}")
    d = {"runner": RUNNER, "stage": stage, "requests_path": requests_path, "requests_sha256": file_sha(requests_path), "n_requests": len(rows),
         "code": {f: file_sha(f) for f in CODE_FILES}, "locked_files": {f: file_sha(f) for f in eval_lock_files(stage)},
         "images_digest": sha_bytes(canon(imgs).encode()), "model_files": mf, "config": core, "config_digest": cdig, "gate": None}
    if gate:
        g = json.load(open(gate))
        if g.get("run") is not True or g.get("for_stage") != stage.split("_")[0]:
            raise RunError(f"gate does not permit stage {stage}: {gate}")
        for name, ent in g["evidence"].items():
            if file_sha(ent["path"]) != ent["sha256"]:
                raise RunError(f"gate evidence changed {name}")
        d["gate"] = {"path": gate, "sha256": file_sha(gate)}
    elif stage.split("_")[0] != "D":
        raise RunError("E stages require --gate")
    atomic_write_json(out_path, d)
    print("protocol", out_path, sha_bytes(canon(d).encode())[:16])


def verify_protocol(path, requests_path, full_model=False):
    p = json.load(open(path))
    for grp in ("code", "locked_files"):
        bad = [f for f, h in p[grp].items() if file_sha(f) != h]
        if bad:
            raise RunError(f"{grp} changed since lock: {bad}")
    if file_sha(requests_path) != p["requests_sha256"] or p["requests_path"] != requests_path:
        raise RunError("requests differ from protocol")
    cur = model_file_digest()
    if cur != p["model_files"]:
        raise RunError("model files differ from protocol")
    if p["gate"] and file_sha(p["gate"]["path"]) != p["gate"]["sha256"]:
        raise RunError("gate changed")
    if sha_bytes(canon(p["config"]).encode()) != p["config_digest"]:
        raise RunError("config digest tampered")
    return sha_bytes(canon(p).encode()), p


# ---------------- scoring ----------------
def check_boundary(proc, inp):
    """prefix 끝 'model\\n'과 후보 token 경계: encode(tail+cand)==encode(tail)+encode(cand), 그리고 입력 마지막 token이 tail과 일치."""
    tk = proc.tokenizer
    tail = "<start_of_turn>model\n"
    tail_ids = tk.encode(tail, add_special_tokens=False)
    ids = inp["input_ids"][0].tolist()
    if ids[-len(tail_ids):] != tail_ids:
        raise RunError("prefix does not end with generation prompt")
    ans = {}
    for c in CANDS:
        a = tk.encode(c, add_special_tokens=False)
        if tk.encode(tail + c, add_special_tokens=False) != tail_ids + a:
            raise RunError(f"token boundary mismatch for {c}")
        ans[c] = a
    return ans


def score_candidate(torch, model, inp, ans_ids):
    """batch1: prefix+ans를 한 번 forward. 위치 j(=L0-1+j) hidden이 ans[j]를 예측(causal shift)."""
    n = len(ans_ids)
    x = C.to_dev(torch, C.extend_inputs(torch, inp, ans_ids))
    with torch.no_grad():
        h = C.hidden_last(model, x, n + 1)[:n]
        lp = torch.log_softmax(C.head_fp32(model, h), dim=-1)
        lpn = torch.log_softmax(model.lm_head(h).float(), dim=-1)
    tgt = torch.tensor(ans_ids, device=lp.device)
    tl = lp.gather(1, tgt[:, None])[:, 0].tolist()
    tln = lpn.gather(1, tgt[:, None])[:, 0].tolist()
    return {"ans_ids": ans_ids, "token_logps": tl, "sum_ll": sum(tl), "mean_ll": sum(tl) / n, "native_token_logps": tln,
            "native_mean_ll": sum(tln) / n, "n_ans_tokens": n}


def score_pair_batch2(torch, model, inp, ans, order):
    """두 후보를 right-padding batch 2로 한 번에 forward(영상 pixel_values는 batch 순서대로 반복)."""
    Ls = [len(ans[c]) for c in order]
    nmax = max(Ls)
    ids0 = inp["input_ids"]
    rows, masks, tts = [], [], []
    for c in order:
        n = len(ans[c])
        pad = nmax - n
        a = torch.tensor([ans[c] + [0] * pad], dtype=ids0.dtype)
        rows.append(torch.cat([ids0, a], 1))
        masks.append(torch.cat([inp["attention_mask"], torch.ones((1, n), dtype=inp["attention_mask"].dtype),
                                torch.zeros((1, pad), dtype=inp["attention_mask"].dtype)], 1))
        tts.append(torch.zeros((1, ids0.shape[1] + nmax), dtype=inp["token_type_ids"].dtype))
    x = dict(inp)
    x["input_ids"], x["attention_mask"] = torch.cat(rows, 0), torch.cat(masks, 0)
    tt = torch.cat(tts, 0)
    tt[:, :ids0.shape[1]] = inp["token_type_ids"]
    x["token_type_ids"] = tt
    x["pixel_values"] = torch.cat([inp["pixel_values"]] * 2, 0)
    x = C.to_dev(torch, x)
    L0 = ids0.shape[1]
    out = {}
    with torch.no_grad():
        hs = model.model(**x, use_cache=False)[0]
        for bi, c in enumerate(order):
            n = len(ans[c])
            h = hs[bi, L0 - 1:L0 - 1 + n, :]
            lp = torch.log_softmax(C.head_fp32(model, h), dim=-1)
            tgt = torch.tensor(ans[c], device=lp.device)
            tl = lp.gather(1, tgt[:, None])[:, 0].tolist()
            out[c] = {"ans_ids": ans[c], "token_logps": tl, "sum_ll": sum(tl), "mean_ll": sum(tl) / n, "n_ans_tokens": n}
    return out


def per_image_pixel_sha(inp):
    pv = inp["pixel_values"].float()
    return [sha_bytes(pv[i].numpy().tobytes()) for i in range(pv.shape[0])]


def prepare(torch, proc, model, row):
    """생성과 동일한 입력(msd56_run.build_inputs) + 구조 검사. returns inp, meta, ans."""
    t0 = time.time()
    inp = M.build_inputs(proc, row)
    ids = inp["input_ids"][0].tolist()
    n_img = sum(1 for t in ids if t == model.config.image_token_index)
    if n_img != 256 * len(row["images"]) or inp["pixel_values"].shape[0] != len(row["images"]):
        raise RunError(f"input structure mismatch {row['request_id']}")
    if "token_type_ids" not in inp or int(inp["attention_mask"].min()) != 1:
        raise RunError("unexpected padding/token_type in prefix")
    ans = check_boundary(proc, inp)
    meta = {"n_input_tokens": len(ids), "n_image_tokens": n_img, "n_images": len(row["images"]),
            "input_ids_sha": sha_bytes(json.dumps(ids).encode()), "img_pixel_sha": per_image_pixel_sha(inp),
            "input_keys": sorted(inp.keys()), "prep_s": time.time() - t0}
    return inp, meta, ans


def compute(torch, proc, model, row, cand_batch, order=None):
    inp, meta, ans = prepare(torch, proc, model, row)
    order = order or list(CANDS)
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    if cand_batch == 2:
        cs = score_pair_batch2(torch, model, inp, ans, order)
    else:
        cs = {c: score_candidate(torch, model, inp, ans[c]) for c in order}
    torch.cuda.synchronize()
    meta.update({"score_s": time.time() - t0, "peak_mem_alloc_gb": torch.cuda.max_memory_allocated() / 2**30,
                 "peak_mem_reserved_gb": torch.cuda.max_memory_reserved() / 2**30})
    return {c: cs[c] for c in CANDS}, meta


# ---------------- 검증 ----------------
def validate_records(files, rows_by_id, pdig, cdig, shas):
    done = {}
    for fn, recs in files.items():
        for r in recs:
            rid = r.get("request_id")
            row = rows_by_id.get(rid)
            if row is None:
                raise RunError(f"unexpected record {rid} in {fn}")
            if rid in done:
                raise RunError(f"duplicate record {rid}")
            if r.get("record_digest") != record_digest(r):
                raise RunError(f"record digest mismatch {rid}")
            if r.get("row_digest") != row_digest(row) or r.get("protocol_digest") != pdig or r.get("config_digest") != cdig:
                raise RunError(f"row/protocol/config mismatch {rid}")
            if r["image_file_sha256"] != row["image_file_sha256"] or [shas(p) for p in row["images"]] != row["image_file_sha256"]:
                raise RunError(f"image hash mismatch {rid}")
            if r["n_image_tokens"] != 256 * len(row["images"]) or sorted(r["scores"]) != sorted(CANDS):
                raise RunError(f"bad record structure {rid}")
            done[rid] = r
    return done


def ev(out_dir, **kw):
    kw.setdefault("t", time.time())
    kw.setdefault("pid", os.getpid())
    fd = os.open(os.path.join(out_dir, "events.jsonl"), os.O_CREAT | os.O_WRONLY | os.O_APPEND)
    os.write(fd, (json.dumps(kw) + "\n").encode())
    os.close(fd)


def load_runtime(proto):
    torch, proc, model = M.load_model()
    tc = model.config.get_text_config()
    if getattr(tc, "final_logit_softcapping", None) is not None:
        raise RunError("final_logit_softcapping set: fp32 head path invalid")
    return torch, proc, model


# ---------------- worker ----------------
def worker_main(a):
    if a.gpu is not None:  # 시험용: 상속된 허용 집합 안에서만 GPU 지정 (torch import 전)
        if a.gpu not in P43.allowed_gpus() or "torch" in sys.modules:
            raise RunError("--gpu outside allowed set or torch already imported")
        os.environ["CUDA_VISIBLE_DEVICES"] = str(a.gpu)
        os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
    pdig, proto = verify_protocol(a.protocol, a.requests)
    rows = read_requests(a.requests)
    rows_by_id = {r["request_id"]: r for r in rows}
    os.makedirs(a.out_dir, exist_ok=True)
    if os.path.exists(os.path.join(a.out_dir, "completion.json")):
        raise RunError("completion.json exists: refuse to rerun into a completed out-dir")
    wl = try_flock(os.path.join(a.out_dir, f"worker{a.worker}.lock"))
    if wl is None:
        sys.exit(f"worker {a.worker} already running")
    attempt = os.environ.get("M66_ATTEMPT", "manual")
    gpu = os.environ.get("CUDA_VISIBLE_DEVICES")
    ev(a.out_dir, event="worker_start", worker=a.worker, attempt=attempt, gpu=gpu)
    t_l = time.time()
    torch, proc, model = load_runtime(proto)
    env = M.env_info(torch, proc, model)
    load_s = time.time() - t_l
    cdig = proto["config_digest"]
    cand_batch = proto["config"]["cand_batch"]
    ev(a.out_dir, event="model_ready", worker=a.worker, attempt=attempt, gpu=gpu, load_s=load_s)
    envp = os.path.join(a.out_dir, f"worker{a.worker}.env.{attempt}.json")
    json.dump({"env": env, "protocol_digest": pdig, "worker": a.worker, "physical_cuda_visible_devices": gpu, "load_s": load_s},
              open(envp, "w"), indent=1, default=str)
    cache = {}

    def shas(p):
        if p not in cache:
            cache[p] = file_sha(p)
        return cache[p]

    def read_all():
        return {f: read_records(f) for f in sorted(glob.glob(os.path.join(a.out_dir, "worker*.jsonl")))}

    out = os.path.join(a.out_dir, f"worker{a.worker}.jsonl")
    repair_tail(out)
    done = validate_records(read_all(), rows_by_id, pdig, cdig, shas)
    cdir = os.path.join(a.out_dir, "claims")
    os.makedirs(cdir, exist_ok=True)
    n_new, t0 = 0, time.time()
    try:
        for row in sorted(rows, key=lambda r: r["order_key"]):
            if row["request_id"] in done:
                continue
            if a.max_requests is not None and n_new >= a.max_requests:
                break
            fd = try_flock(os.path.join(cdir, row["request_id"] + ".claim"))
            if fd is None:
                continue
            try:
                done = validate_records(read_all(), rows_by_id, pdig, cdig, shas)
                if row["request_id"] in done:
                    continue
                t_req = time.time()
                scores, meta = compute(torch, proc, model, row, cand_batch)
                rec = {"request_id": row["request_id"], "row_digest": row_digest(row), "case": row["case"], "slab": row["slab"],
                       "cond": row["cond"], "image_file_sha256": row["image_file_sha256"], "scores": scores, **meta,
                       "wall_s": time.time() - t_req, "t_start": t_req, "ts": time.time(), "protocol_digest": pdig,
                       "config_digest": cdig, "worker": a.worker, "pid": os.getpid(), "attempt": attempt,
                       "gpu_uuid": env.get("gpu_uuid"), "cand_batch": cand_batch}
                rec["record_digest"] = record_digest(rec)
                if a.die_after_write is not None and n_new + 1 >= a.die_after_write:  # 시험용
                    b = (json.dumps(rec) + "\n").encode()
                    fdo = os.open(out, os.O_WRONLY | os.O_APPEND | os.O_CREAT)
                    os.write(fdo, b[:len(b) // 2] if a.die_mode == "torn" else b)
                    os.fsync(fdo)
                    os._exit(9)
                fdo = os.open(out, os.O_WRONLY | os.O_APPEND | os.O_CREAT)
                b = (json.dumps(rec) + "\n").encode()
                if os.write(fdo, b) != len(b):
                    raise IOError("short write")
                os.fsync(fdo)
                os.close(fdo)
                done[row["request_id"]] = rec
                n_new += 1
                print(f"w{a.worker} {n_new} {row['request_id']} {time.time() - t0:.0f}s", flush=True)
            finally:
                os.close(fd)
    finally:
        ev(a.out_dir, event="worker_end", worker=a.worker, attempt=attempt, gpu=gpu, n_new=n_new)
    print(f"worker {a.worker}: finished; {n_new} new requests", flush=True)


# ---------------- 완료 검증 ----------------
def verify_completion(out_dir, requests_path, protocol_path):
    comp = json.load(open(os.path.join(out_dir, "completion.json")))
    pdig, proto = verify_protocol(protocol_path, requests_path)
    rows = read_requests(requests_path)
    rows_by_id = {r["request_id"]: r for r in rows}
    if comp["protocol_digest"] != pdig or any(c != 0 for c in comp["exit_codes"]):
        raise RunError("completion protocol/exit code invalid")
    files = sorted(glob.glob(os.path.join(out_dir, "worker*.jsonl")))
    if sorted(os.path.basename(f) for f in files) != sorted(comp["worker_file_sha256"]):
        raise RunError("worker file set differs from completion")
    recs = []
    for fn in files:
        if file_sha(fn) != comp["worker_file_sha256"][os.path.basename(fn)]:
            raise RunError(f"worker file changed after completion {fn}")
        recs += read_records(fn)
    ids = [r["request_id"] for r in recs]
    if len(ids) != len(set(ids)) or set(ids) != set(rows_by_id) or len(ids) != comp["n_requests"]:
        raise RunError("completion: request set mismatch")
    cache = {}

    def shas(p):
        if p not in cache:
            cache[p] = file_sha(p)
        return cache[p]
    validate_records({"all": recs}, rows_by_id, pdig, proto["config_digest"], shas)
    return recs, proto, comp


def cost_report(out_dir):
    """GPU별: loading 포함 프로세스 구간 합집합 vs 요청 구간 합집합. worker_end 없는 프로세스는 하한(마지막 record ts)."""
    evs = jl(os.path.join(out_dir, "events.jsonl")) if os.path.exists(os.path.join(out_dir, "events.jsonl")) else []
    recs = []
    for fn in sorted(glob.glob(os.path.join(out_dir, "worker*.jsonl"))):
        recs += read_records(fn)
    last_ts, req_iv, proc_iv, nolb = {}, {}, {}, 0
    for r in recs:
        last_ts[r["pid"]] = max(last_ts.get(r["pid"], 0), r["ts"])
        req_iv.setdefault(r["gpu_uuid"], []).append((r["t_start"], r["ts"]))
    by = {}
    for e in evs:
        if e["event"].startswith("worker"):
            by.setdefault(e["pid"], []).append(e)
        elif e["event"] == "model_ready":
            by.setdefault(e["pid"], []).append(e)
    uuid_of = {r["pid"]: r["gpu_uuid"] for r in recs}
    for pid, es in by.items():
        st = [e for e in es if e["event"] == "worker_start"]
        en = [e for e in es if e["event"] == "worker_end"]
        if not st:
            continue
        if en:
            te = en[0]["t"]
        else:
            nolb += 1
            te = max([last_ts.get(pid, 0)] + [e["t"] for e in es])
        proc_iv.setdefault(uuid_of.get(pid) or st[0]["gpu"], []).append((st[0]["t"], te))
    return {"device_seconds_incl_loading_union": sum(P43._union_len(v) for v in proc_iv.values()),
            "device_seconds_request_union": sum(P43._union_len(v) for v in req_iv.values()),
            "sum_request_wall_s": sum(r["wall_s"] for r in recs), "sum_score_s": sum(r["score_s"] for r in recs),
            "sum_prep_s": sum(r["prep_s"] for r in recs), "n_records": len(recs), "n_procs_without_end_lower_bound": nolb,
            "peak_mem_reserved_gb_max": max([r["peak_mem_reserved_gb"] for r in recs] or [0])}


# ---------------- launcher ----------------
def launch_main(a):
    pdig, proto = verify_protocol(a.protocol, a.requests)
    os.makedirs(a.out_dir, exist_ok=True)
    if os.path.exists(os.path.join(a.out_dir, "completion.json")):
        raise RunError("completion.json exists; use a new out-dir")
    lk = try_flock(os.path.join(a.out_dir, "launch.lock"))
    if lk is None:
        sys.exit("another launcher owns this out-dir")
    allowed = P43.allowed_gpus()
    gpus = [int(x) for x in a.gpus.split(",")] if a.gpus else allowed
    if not set(gpus) <= set(allowed):
        sys.exit(f"--gpus {gpus} not within inherited allowed set {allowed}")
    free = P43.gpu_free_mib()
    gpus = sorted(gpus, key=lambda g: (-free[g], g))
    per = {}
    for k in range(a.workers):
        per.setdefault(gpus[k % len(gpus)], []).append(k)
    for g, ws in per.items():
        need = len(ws) * (a.peak_gb + 2.0) * 1024
        if free[g] < need:
            sys.exit(f"gpu {g}: free {free[g]}MiB < need {need:.0f}MiB for workers {ws}")
    mapping = {k: gpus[k % len(gpus)] for k in range(a.workers)}
    attempt = f"a{int(time.time())}_{os.getpid()}"
    uuids = subprocess.run(["nvidia-smi", "--query-gpu=index,uuid", "--format=csv,noheader"], capture_output=True, text=True).stdout
    ev(a.out_dir, event="launch_start", worker=-1, attempt=attempt, workers=a.workers, mapping=mapping, free_mib_before=free,
       allowed=allowed, gpu_uuids=uuids.strip().splitlines(), peak_gb_assumed=a.peak_gb, max_requests=a.max_requests)
    procs, t0 = {}, time.time()
    for k in range(a.workers):
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(mapping[k]), CUDA_DEVICE_ORDER="PCI_BUS_ID", M66_ATTEMPT=attempt)
        cmd = [sys.executable, "m66_run.py", "worker", "--requests", a.requests, "--protocol", a.protocol, "--out-dir", a.out_dir,
               "--worker", str(k)]
        if a.max_requests is not None:
            cmd += ["--max-requests", str(a.max_requests)]
        procs[k] = subprocess.Popen(cmd, env=env, stdout=open(os.path.join(a.out_dir, f"worker{k}.{attempt}.stdout"), "a"),
                                    stderr=open(os.path.join(a.out_dir, f"worker{k}.{attempt}.stderr"), "a"))
    rl = open(os.path.join(a.out_dir, "resource_log.jsonl"), "a")
    peak = {}
    while any(p.poll() is None for p in procs.values()):
        time.sleep(5)
        used = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
                              capture_output=True, text=True).stdout.strip().splitlines()
        rl.write(json.dumps({"attempt": attempt, "t": round(time.time() - t0, 1), "gpu": used}) + "\n")
        rl.flush()
        for l in used:
            i, m, _ = [x.strip() for x in l.split(",")]
            peak[int(i)] = max(peak.get(int(i), 0), int(m))
    codes = [procs[k].returncode for k in range(a.workers)]
    wall = time.time() - t0  # worker 종료(각 record는 fsync 후 진행) 이후 부모 측정
    ev(a.out_dir, event="launch_end", worker=-1, attempt=attempt, exit_codes=codes, wall_s=wall, peak_used_mib=peak)
    recs = []
    for fn in sorted(glob.glob(os.path.join(a.out_dir, "worker*.jsonl"))):
        recs += read_records(fn)
    n_unique = len({r["request_id"] for r in recs})
    if a.max_requests is None and all(c == 0 for c in codes) and n_unique == proto["n_requests"] == len(recs):
        res = {"exit_codes": codes, "wall_s_this_attempt": wall, "n_records": len(recs), "n_unique": n_unique, "n_requests": proto["n_requests"],
               "workers": a.workers, "mapping": mapping, "protocol_digest": pdig, "attempt": attempt, "peak_used_mib_by_gpu": peak,
               "worker_file_sha256": {os.path.basename(f): file_sha(f) for f in sorted(glob.glob(os.path.join(a.out_dir, "worker*.jsonl")))},
               "cost_all_attempts": cost_report(a.out_dir), "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        atomic_write_json(os.path.join(a.out_dir, "completion.json"), res)
        print("completion written", json.dumps({k: res[k] for k in ("exit_codes", "wall_s_this_attempt", "n_unique")}))
    else:
        atomic_write_json(os.path.join(a.out_dir, f"partial_{attempt}.json"),
                          {"exit_codes": codes, "wall_s": wall, "n_unique": n_unique, "n_requests": proto["n_requests"], "attempt": attempt})
        print("NOT complete", codes, n_unique, proto["n_requests"])
        sys.exit(0 if a.max_requests is not None else 1)


# ---------------- tech (D 전용 기술 검증; GT 미사용) ----------------
def cmd_tech(a):
    """D 실제 입력: (1) 생성 입력과 input_ids/pixel/파일 hash 일치 (2) token 경계 (3) 결합 forward vs 독립 token-by-token
    (4) fp32 head vs native (5) 후보 순서 교환 (6) batch2 vs batch1 (7) 생성 첫 token과의 대응(참고)."""
    pdig, proto = verify_protocol(a.protocol, a.requests)
    rows = read_requests(a.requests)
    gen = {}
    for f in glob.glob(f"{SRC65}/gen/D_medgemma/worker*.jsonl"):
        for r in read_records(f):
            gen[r["rid"]] = r
    torch, proc, model = load_runtime(proto)
    tc = model.config.get_text_config()
    cfg = {"final_logit_softcapping": getattr(tc, "final_logit_softcapping", None),
           "tie_word_embeddings": bool(getattr(model.config, "tie_word_embeddings", getattr(tc, "tie_word_embeddings", False))),
           "lm_head_weight_shape": list(model.lm_head.weight.shape)}
    res, fails = [], 0
    t_all = time.time()
    for ix, row in enumerate(sorted(rows, key=lambda r: r["order_key"])):
        heavy = ix % 3 == 0  # 고정 규칙: order_key 순 3번째마다(24항목, F/J 혼합)에 독립 token-by-token·native·batch2 검사
        inp, meta, ans = prepare(torch, proc, model, row)
        g = gen[row["request_id"]]
        item = {"rid": row["request_id"], "cond": row["cond"]}
        item["ok_input_ids"] = meta["input_ids_sha"] == g["input_ids_sha"]
        item["ok_pixel"] = meta["img_pixel_sha"] == g["img_pixel_sha"]
        item["ok_files"] = row["image_file_sha256"] == g["image_file_sha"]
        item["ok_ntok"] = meta["n_input_tokens"] == g["n_input_tokens"]
        sc = {c: score_candidate(torch, model, inp, ans[c]) for c in CANDS}
        # 독립 token-by-token: prefix+ans[:j] 의 마지막 위치(logits_to_keep=1) 분포에서 ans[j]
        ind, nat = {}, {}
        for c in (CANDS if heavy else []):
            tl, tln = [], []
            for j in range(len(ans[c])):
                x = C.to_dev(torch, C.extend_inputs(torch, inp, ans[c][:j])) if j else C.to_dev(torch, inp)
                with torch.no_grad():
                    h = C.hidden_last(model, x, 1)
                    lg = C.head_fp32(model, h)[0]
                    ln = model.lm_head(h)[0].float()
                tl.append((lg[ans[c][j]] - torch.logsumexp(lg, 0)).item())
                tln.append((ln[ans[c][j]] - torch.logsumexp(ln, 0)).item())
            ind[c], nat[c] = sum(tl) / len(tl), sum(tln) / len(tln)
        item["heavy"] = heavy
        item["indep_diff"] = {c: abs(sc[c]["mean_ll"] - ind[c]) for c in CANDS} if heavy else {"-": 0.0}
        item["native_diff"] = {c: abs(sc[c]["mean_ll"] - nat[c]) for c in CANDS} if heavy else {"-": 0.0}
        item["native_head_in_forward_diff"] = {c: abs(sc[c]["mean_ll"] - sc[c]["native_mean_ll"]) for c in CANDS}
        # 후보 순서 교환(batch1은 후보별 독립 forward — 결정성 확인) 및 batch2 두 순서
        sw = {c: score_candidate(torch, model, inp, ans[c]) for c in reversed(CANDS)}
        item["swap_b1_diff"] = {c: abs(sc[c]["mean_ll"] - sw[c]["mean_ll"]) for c in CANDS}
        if heavy:
            b2a = score_pair_batch2(torch, model, inp, ans, CANDS)
            b2b = score_pair_batch2(torch, model, inp, ans, list(reversed(CANDS)))
            item["b2_vs_b1"] = {c: abs(sc[c]["mean_ll"] - b2a[c]["mean_ll"]) for c in CANDS}
            item["b2_order_swap"] = {c: abs(b2a[c]["mean_ll"] - b2b[c]["mean_ll"]) for c in CANDS}
        else:
            item["b2_vs_b1"] = item["b2_order_swap"] = {"-": 0.0}
        # 생성된 첫 token 대응(참고, 실패 판정 아님)
        first = g["attempts"][-1]["suffix_ids"][:1]
        item["gen_first_token_in_cands"] = bool(first) and first[0] in {ans[c][0] for c in CANDS}
        item["pick_matches_gen_first"] = None
        if first:
            pick = max(CANDS, key=lambda c: (sc[c]["mean_ll"], c == "ABSENT"))
            item["pick_matches_gen_first"] = first[0] == ans[pick][0]
        ok = (item["ok_input_ids"] and item["ok_pixel"] and item["ok_files"] and item["ok_ntok"]
              and max(item["indep_diff"].values()) < TOL_INDEP_MEAN and max(item["native_diff"].values()) < TOL_NATIVE
              and max(item["swap_b1_diff"].values()) == 0.0)
        item["ok"] = bool(ok)
        item["b2_within_tol"] = bool(max(item["b2_vs_b1"].values()) < TOL_BATCH and max(item["b2_order_swap"].values()) < TOL_BATCH)
        fails += not ok
        item["mean_ll"] = {c: sc[c]["mean_ll"] for c in CANDS}
        res.append(item)
        print(item["rid"], item["ok"], f"indep{max(item['indep_diff'].values()):.4f} b2{max(item['b2_vs_b1'].values()):.4f}", flush=True)
    out = {"protocol_digest": pdig, "requests_sha256": file_sha(a.requests), "n_checked": len(res), "fails": fails,
           "all_pass": fails == 0 and len(res) == len(rows), "model_config": cfg, "answer_token_ids": ans,
           "tolerances": {"indep_mean": TOL_INDEP_MEAN, "native": TOL_NATIVE, "batch2": TOL_BATCH},
           "max_indep_diff": max(max(r["indep_diff"].values()) for r in res), "max_native_diff": max(max(r["native_diff"].values()) for r in res),
           "n_heavy": sum(r["heavy"] for r in res), "max_b2_vs_b1": max(max(r["b2_vs_b1"].values()) for r in res), "b2_all_within_tol": all(r["b2_within_tol"] for r in res),
           "n_gen_first_token_in_cands": sum(r["gen_first_token_in_cands"] for r in res),
           "n_pick_matches_gen_first": sum(bool(r["pick_matches_gen_first"]) for r in res), "wall_s": time.time() - t_all, "details": res}
    atomic_write_json(a.out, out)
    print("tech fails", fails, "of", len(res), "max indep", out["max_indep_diff"], "max b2", out["max_b2_vs_b1"])
    if fails:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--split", required=True, choices=["D", "E12", "E36"])
    b.add_argument("--out", required=True)
    p = sub.add_parser("protocol")
    p.add_argument("--stage", required=True)
    p.add_argument("--requests", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--cand-batch", type=int, default=1, choices=[1, 2])
    p.add_argument("--gate", default=None)
    t = sub.add_parser("tech")
    t.add_argument("--requests", required=True)
    t.add_argument("--protocol", required=True)
    t.add_argument("--out", required=True)
    w, l = sub.add_parser("worker"), sub.add_parser("launch")
    for s in (w, l):
        s.add_argument("--requests", required=True)
        s.add_argument("--protocol", required=True)
        s.add_argument("--out-dir", required=True)
        s.add_argument("--max-requests", type=int, default=None)
    w.add_argument("--worker", type=int, required=True)
    w.add_argument("--gpu", type=int, default=None)
    w.add_argument("--die-after-write", type=int, default=None)
    w.add_argument("--die-mode", default="whole", choices=["whole", "torn"])
    l.add_argument("--workers", type=int, required=True)
    l.add_argument("--gpus", default=None)
    l.add_argument("--peak-gb", type=float, default=14.0)
    a = ap.parse_args()
    if a.cmd == "build":
        cmd_build(a)
    elif a.cmd == "protocol":
        make_protocol(a.stage, a.requests, a.out, a.cand_batch, a.gate)
    elif a.cmd == "tech":
        cmd_tech(a)
    elif a.cmd == "worker":
        worker_main(a)
    else:
        launch_main(a)


if __name__ == "__main__":
    main()
