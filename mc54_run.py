"""iter_054 MediConfusion 단일 영상 진단 runner: MC 생성 / GD A-B logit / PS 답변 평균 log likelihood.

재사용(iter_053 보존본): rsna_diag.generate의 load_model/build_inputs/build_inputs_text/generate/env_info/static_env,
pg43_run의 순수 helper(digest·record I/O·부분 행 보존·flock·GPU 조회), queue_lock 계열. 기존 CLI·gate·비용 집계·load_image(padding)는 쓰지 않는다.

소유권: out-dir launch.lock / worker{K}.lock / claims/<rid>.claim (flock; 죽은 소유자 claim 자동 회수).
재개: 시작 시와 claim 직후 모든 기존 record(부모 dir 포함)를 요청 행·prompt·config·protocol·현재 영상 pixel hash·record digest와 대조한다.
worker 수·GPU 매핑은 attempt마다 바꿀 수 있고, attempt/worker 이벤트는 append 파일에 남겨 비용을 모든 attempt에서 같은 범위로 집계한다.

사용:
  python mc54_run.py protocol --stage tech|main --requests R --out P [--gate G] [--parent-out-dir D --parent-protocol P0]
  python mc54_run.py launch --stage tech|main --requests R --protocol P --out-dir D --workers N [--gpus 0,1] [--peak-gb 12]
  (worker는 launcher가 호출) GT·정답·pair 대응은 읽지 않는다.
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import time

os.environ.setdefault("HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import pg43_run as P43  # noqa: E402  순수 helper만 사용
from rsna_diag import generate as G  # noqa: E402
import mc54_spec as S  # noqa: E402

RUNNER = "mc54_run_v1"
CODE_FILES = ["mc54_run.py", "mc54_spec.py", "mc54_requests.py", "mc54_build.py", "mc54_gate.py", "pg43_run.py",
              "rsna_diag/generate.py", "rsna_diag/geometry.py", "rsna_diag/prompts.py", "rsna_diag/queue_lock.py"]
DATA_FILES = ["results/iter_054/data/eval_manifest.json", "results/iter_054/data/images_info.json",
              "results/iter_054/data/data_report.json", "results/iter_054/data/fetch_manifest.json",
              "results/iter_054/source/source_manifest.json", "results/iter_054/source/data__dataset.json"]
RunError = P43.RunError
sha_bytes, file_sha, canon, record_digest = P43.sha_bytes, P43.file_sha, P43.canon, P43.record_digest
read_records, repair_tail, try_flock = P43.read_records, P43.repair_tail, P43.try_flock


def jl(p):
    return [json.loads(l) for l in open(p) if l.strip()]


def row_digest(row):
    return sha_bytes(canon(row).encode())


def read_requests(path):
    rows = jl(path)
    ids = [r["request_id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise RunError("duplicate request_id")
    for r in rows:
        if any(k in r for k in ("pair", "truth", "caption", "correct", "category")):
            raise RunError(f"inference row carries evaluation fields {r['request_id']}")
        if r["modality"] == "image":
            if not (r.get("image") and r.get("image_file_sha256") and r.get("input_pixel_sha256")):
                raise RunError(f"image row without hash {r['request_id']}")
        elif r["modality"] == "text":
            if any(r.get(k) is not None for k in ("image", "image_file_sha256", "input_pixel_sha256")):
                raise RunError(f"text row carries image fields {r['request_id']}")
        else:
            raise RunError("bad modality")
        if r["kind"] not in ("mc", "gd", "ps"):
            raise RunError("bad kind")
        if (r["kind"] == "ps") != (r.get("assistant_text") is not None):
            raise RunError("assistant_text only for ps")
        if r["prompt_sha256"] != S.sha(r["prompt"]):
            raise RunError(f"prompt hash {r['request_id']}")
    return rows


def rebuild_check(requests_path):
    """잠긴 source·영상 정보·eval pair 목록에서 요청 행을 재구성해 요청 파일과 완전히 대조한다."""
    import mc54_requests as R
    ds = json.load(open("results/iter_054/source/data__dataset.json"))
    ii = {int(k): v for k, v in json.load(open("results/iter_054/data/images_info.json")).items()}
    ev = json.load(open("results/iter_054/data/eval_manifest.json"))
    avail = {p for p, m in ev["pairs"].items() if m["available"]}
    tech = {p for p, m in ev["pairs"].items() if m["tech"]}
    rows, evalmap = R.build(ds, ii, avail, tech)
    got = jl(requests_path)
    if [json.dumps(r, sort_keys=True, ensure_ascii=False) for r in rows] != [json.dumps(r, sort_keys=True, ensure_ascii=False) for r in got]:
        raise RunError("requests file != rebuilt from locked sources")
    if evalmap != ev["requests"]:
        raise RunError("eval mapping != rebuilt")
    for loc, v in ii.items():  # 현재 영상 file hash
        if file_sha(v["path"]) != v["file_sha256"]:
            raise RunError(f"image file changed {v['path']}")
    return len(rows)


# ---------------- protocol ----------------
def static_config():
    env = G.static_env()
    core = {k: env[k] for k in G.CFG_KEYS}
    core.update({"caps_mc": S.CAPS_MC, "do_sample": False, "runner": RUNNER, "spec": S.SPEC_VERSION,
                 "dtype_scoring": "bf16 forward, fp32 log_softmax"})
    return core, sha_bytes(canon(core).encode())


def gate_check(gate_path):
    g = json.load(open(gate_path))
    if g.get("run") is not True:
        raise RunError("technical gate run != true")
    for name, ent in g["evidence"].items():
        if file_sha(ent["path"]) != ent["sha256"]:
            raise RunError(f"gate evidence changed: {name}")
        if ent.get("require_all_pass") and json.load(open(ent["path"])).get("all_pass") is not True:
            raise RunError(f"gate evidence not all_pass: {name}")
    return g


def make_protocol(stage, requests_path, out_path, gate=None, parent_out=None, parent_protocol=None):
    n = rebuild_check(requests_path)
    rows = read_requests(requests_path)
    core, cdig = static_config()
    d = {"runner": RUNNER, "stage": stage, "requests_path": requests_path, "requests_sha256": file_sha(requests_path), "n_requests": n,
         "n_stage_requests": sum(stage == "main" or r["stage"] == "tech" for r in rows),
         "code": {f: file_sha(f) for f in CODE_FILES}, "data": {f: file_sha(f) for f in DATA_FILES},
         "generation_config_digest": cdig, "generation_config": core, "gate": None, "parent": None}
    if stage == "main":
        if not (gate and parent_out and parent_protocol):
            raise RunError("main stage requires --gate, --parent-out-dir and --parent-protocol")
        g = gate_check(gate)
        d["gate"] = {"path": gate, "sha256": file_sha(gate)}
        pp = json.load(open(parent_protocol))
        if pp["stage"] != "tech" or pp["requests_sha256"] != d["requests_sha256"] or pp["generation_config_digest"] != cdig:
            raise RunError("parent protocol is not a compatible tech protocol")
        verify_completion(parent_out, requests_path, parent_protocol)
        d["parent"] = {"out_dir": parent_out, "protocol_path": parent_protocol, "protocol_file_sha256": file_sha(parent_protocol),
                       "protocol_digest": sha_bytes(canon(pp).encode()),
                       "completion_sha256": file_sha(os.path.join(parent_out, "completion.json"))}
        if g.get("tech_protocol_sha256") != file_sha(parent_protocol):
            raise RunError("gate does not reference this parent protocol")
    if os.path.exists(out_path):
        raise RunError(f"protocol exists {out_path}")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp = out_path + f".{os.getpid()}.tmp"
    with open(tmp, "x") as f:
        json.dump(d, f, indent=1)
    os.replace(tmp, out_path)
    return d


def verify_protocol(path, requests_path):
    p = json.load(open(path))
    for grp in ("code", "data"):
        bad = [f for f, h in p[grp].items() if file_sha(f) != h]
        if bad:
            raise RunError(f"{grp} changed since protocol lock: {bad}")
    if file_sha(requests_path) != p["requests_sha256"] or p["requests_path"] != requests_path:
        raise RunError("requests file changed / differs from protocol")
    if p["stage"] == "main":
        if file_sha(p["gate"]["path"]) != p["gate"]["sha256"]:
            raise RunError("gate changed")
        gate_check(p["gate"]["path"])
        par = p["parent"]
        if file_sha(par["protocol_path"]) != par["protocol_file_sha256"] or file_sha(os.path.join(par["out_dir"], "completion.json")) != par["completion_sha256"]:
            raise RunError("parent protocol/completion changed")
    return sha_bytes(canon(p).encode()), p


# ---------------- model-side computation ----------------
def load_rgb(path):
    from PIL import Image
    import numpy as np
    im = Image.open(path)
    im.load()
    if im.mode not in ("RGB", "L"):
        raise RunError(f"unsupported image mode {im.mode}")
    rgb = im.convert("RGB")
    arr = np.asarray(rgb)
    return rgb, S.sha(arr.tobytes() + str(arr.shape).encode())


def build_prefix(proc, row, img):
    """user turn(+generation prompt). 영상 row는 official 순서 [image, text], text-only는 text만."""
    if row["modality"] == "image":
        return G.build_inputs(proc, img, row["prompt"])
    return G.build_inputs_text(proc, row["prompt"])


def prefix_string(proc, row):
    content = ([{"type": "image"}] if row["modality"] == "image" else []) + [{"type": "text", "text": row["prompt"]}]
    return proc.apply_chat_template([{"role": "user", "content": content}], tokenize=False, add_generation_prompt=True)


def to_dev(torch, inp):
    return {k: (v.to("cuda", dtype=torch.bfloat16) if k == "pixel_values" else v.to("cuda")) for k, v in inp.items()}


def extend_inputs(torch, inp, ans_ids):
    """prefix 입력 뒤에 답변 token을 이어 붙인다 (attention_mask=1, token_type_ids=0)."""
    n = len(ans_ids)
    a = torch.tensor([ans_ids], dtype=inp["input_ids"].dtype)
    out = dict(inp)
    out["input_ids"] = torch.cat([inp["input_ids"], a], dim=1)
    out["attention_mask"] = torch.cat([inp["attention_mask"], torch.ones((1, n), dtype=inp["attention_mask"].dtype)], dim=1)
    if "token_type_ids" in inp:
        out["token_type_ids"] = torch.cat([inp["token_type_ids"], torch.zeros((1, n), dtype=inp["token_type_ids"].dtype)], dim=1)
    return out


def last_logits(torch, model, x, keep, native=False):
    """마지막 keep 위치의 logits [keep, V] (fp32). 기본은 마지막 hidden state에서 lm_head를 fp32로 계산한다
    (bf16 logits는 크기 ~20에서 0.125 간격으로 양자화되어 A/B margin의 가짜 동점이 생김). Gemma3는 final softcapping=None, tied lm_head.
    native=True면 모델 forward의 bf16 logits (검사·민감도용)."""
    with torch.no_grad():
        if native:
            return model(**x, use_cache=False, logits_to_keep=keep).logits[0].float()
        return head_fp32(model, hidden_last(model, x, keep))


def hidden_last(model, x, keep):
    return model.model(**x, use_cache=False)[0][0, -keep:, :]  # bf16 [keep, H]


def head_fp32(model, h):
    import torch
    W = model.lm_head.weight
    hf = h.float()
    return torch.cat([hf @ W[i:i + 32768].float().T for i in range(0, W.shape[0], 32768)], dim=1)


def do_gd(torch, proc, model, inp, ab_ids):
    x = to_dev(torch, inp)
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    with torch.no_grad():
        h = hidden_last(model, x, 1)
        lg = head_fp32(model, h)[0]
        nat = model.lm_head(h)[0].float()
    lse = torch.logsumexp(lg, dim=0)
    torch.cuda.synchronize()
    la, lb = lg[ab_ids[0]].item(), lg[ab_ids[1]].item()
    top = torch.topk(lg, 5)
    return {"logit_A": la, "logit_B": lb, "lse": lse.item(), "logp_A": la - lse.item(), "logp_B": lb - lse.item(),
            "shown_margin": la - lb, "native_bf16_shown_margin": (nat[ab_ids[0]] - nat[ab_ids[1]]).item(),
            "head": "fp32_lm_head_from_bf16_hidden", "argmax_id": int(lg.argmax().item()), "top5_ids": top.indices.tolist(),
            "top5_logits": top.values.tolist(), "runtime_s": time.time() - t0,
            "peak_mem_alloc_gb": torch.cuda.max_memory_allocated() / 2**30,
            "peak_mem_reserved_gb": torch.cuda.max_memory_reserved() / 2**30}


def do_ps(torch, proc, model, inp, row):
    tk = proc.tokenizer
    ans_ids = tk.encode(row["assistant_text"], add_special_tokens=False)
    pre = prefix_string(proc, row)
    joint = tk.encode(pre + row["assistant_text"], add_special_tokens=False)
    pre_ids = tk.encode(pre, add_special_tokens=False)
    boundary_ok = joint == pre_ids + ans_ids
    if not boundary_ok:
        raise RunError(f"PS token boundary mismatch for {row['request_id']}")
    n = len(ans_ids)
    x = to_dev(torch, extend_inputs(torch, inp, ans_ids))
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    with torch.no_grad():
        h = hidden_last(model, x, n + 1)[:n]  # 위치 j는 답변 token j를 예측
        lp = torch.log_softmax(head_fp32(model, h), dim=-1)
        lpn = torch.log_softmax(model.lm_head(h).float(), dim=-1)
    tgt = torch.tensor(ans_ids, device=lp.device)
    tl = lp.gather(1, tgt[:, None])[:, 0].tolist()
    tln = lpn.gather(1, tgt[:, None])[:, 0].tolist()
    torch.cuda.synchronize()
    return {"ans_ids": ans_ids, "token_logps": tl, "sum_ll": sum(tl), "mean_ll": S.mean_ll(tl), "n_ans_tokens": n,
            "native_bf16_mean_ll": S.mean_ll(tln), "native_bf16_sum_ll": sum(tln), "head": "fp32_lm_head_from_bf16_hidden",
            "boundary_ok": boundary_ok, "runtime_s": time.time() - t0,
            "peak_mem_alloc_gb": torch.cuda.max_memory_allocated() / 2**30,
            "peak_mem_reserved_gb": torch.cuda.max_memory_reserved() / 2**30}


def do_mc(torch, proc, model, inp, eos_ids, caps):
    attempts = []
    for cap in caps:
        at = G.generate(torch, proc, model, inp, cap, eos_ids)
        if attempts:
            at["prefix_matches_previous"] = at["suffix_ids"][:len(attempts[-1]["suffix_ids"])] == attempts[-1]["suffix_ids"]
        attempts.append(at)
        if at["ended_eos"]:
            break
    for at in attempts:
        at["suffix_text_raw"] = proc.tokenizer.decode(at["suffix_ids"], skip_special_tokens=False)
    fin = attempts[-1]
    return {"suffix_ids": fin["suffix_ids"], "suffix_text_raw": fin["suffix_text_raw"], "n_output_tokens": fin["n_new"],
            "finish_reason": fin["finish_reason"], "ended_eos": fin["ended_eos"], "final_cap": fin["cap"],
            "attempts": [{k: v for k, v in at.items() if k != "suffix_ids"} for at in attempts],
            "runtime_s": sum(at["runtime_s"] for at in attempts),
            "peak_mem_alloc_gb": max(at["peak_mem_alloc_gb"] for at in attempts),
            "peak_mem_reserved_gb": max(at["peak_mem_reserved_gb"] for at in attempts)}


def compute_request(torch, proc, model, row, eos_ids, img_tok, ab_ids):
    """returns (payload, meta). 입력 검사: text-only는 image token·pixel 없음, 영상은 둘 다 있음."""
    if row["modality"] == "image":
        img, pxs = load_rgb(row["image"])
        if pxs != row["input_pixel_sha256"]:
            raise RunError(f"input pixel hash changed {row['request_id']}")
    else:
        img, pxs = None, None
    inp = build_prefix(proc, row, img)
    ids_in = inp["input_ids"][0].tolist()
    n_img = sum(1 for t in ids_in if t == img_tok)
    has_pv = "pixel_values" in inp
    if row["modality"] == "text" and (has_pv or n_img != 0 or any(k.startswith("pixel") or "image" in k for k in inp)):
        raise RunError(f"text-only input carries image tensors/tokens {row['request_id']}")
    if row["modality"] == "image" and (not has_pv or n_img != 256):
        raise RunError(f"image input lacks pixel_values or has unexpected image token count {n_img} {row['request_id']}")
    if row["kind"] == "mc":
        pay = do_mc(torch, proc, model, inp, eos_ids, row["caps"])
    elif row["kind"] == "gd":
        pay = do_gd(torch, proc, model, inp, ab_ids)
    else:
        pay = do_ps(torch, proc, model, inp, row)
    meta = {"n_image_tokens": n_img, "has_pixel_values": has_pv, "input_keys": sorted(inp.keys()), "input_pixel_sha256": pxs,
            "n_input_tokens": len(ids_in), "input_ids_sha256": sha_bytes(json.dumps(ids_in).encode())}
    return pay, meta


# ---------------- validation ----------------
def validate_records(files, rows_by_id, ok_pdigs, cdig, px):
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
                raise RunError(f"record digest mismatch {rid} in {fn}")
            if r.get("row_digest") != row_digest(row) or r.get("prompt_sha256") != row["prompt_sha256"]:
                raise RunError(f"row/prompt mismatch {rid}")
            if r.get("protocol_digest") not in ok_pdigs or r.get("config_digest") != cdig:
                raise RunError(f"protocol/config mismatch {rid}")
            if any(r.get(k) != row.get(k) for k in ("kind", "cond", "modality", "image")):
                raise RunError(f"record identity != row {rid}")
            if row["modality"] == "image":
                if r.get("input_pixel_sha256") != row["input_pixel_sha256"] or px(row["image"]) != row["input_pixel_sha256"]:
                    raise RunError(f"input pixel hash mismatch {rid}")
                if r.get("n_image_tokens") != 256 or r.get("has_pixel_values") is not True:
                    raise RunError(f"image record bad image tokens {rid}")
            elif r.get("input_pixel_sha256") is not None or r.get("n_image_tokens") != 0 or r.get("has_pixel_values") is not False:
                raise RunError(f"text-only record carries image input {rid}")
            done[rid] = r
    return done


def ev(out_dir, **kw):
    """append-only 이벤트 로그(attempt 비용 집계용). O_APPEND 단일 write."""
    kw.setdefault("t", time.time())
    kw.setdefault("pid", os.getpid())
    fd = os.open(os.path.join(out_dir, "events.jsonl"), os.O_CREAT | os.O_WRONLY | os.O_APPEND)
    os.write(fd, (json.dumps(kw) + "\n").encode())
    os.close(fd)


# ---------------- worker ----------------
def worker_main(a):
    pdig, proto = verify_protocol(a.protocol, a.requests)
    if proto["stage"] != a.stage:
        raise RunError("stage differs from protocol")
    rows = read_requests(a.requests)
    rows_by_id = {r["request_id"]: r for r in rows}
    todo_rows = [r for r in rows if a.stage == "main" or r["stage"] == "tech"]
    ok_pdigs = {pdig}
    parent_files = []
    if proto["parent"]:
        ok_pdigs.add(proto["parent"]["protocol_digest"])
        parent_files = sorted(glob.glob(os.path.join(proto["parent"]["out_dir"], "gen_worker*.jsonl")))
    os.makedirs(a.out_dir, exist_ok=True)
    if os.path.exists(os.path.join(a.out_dir, "completion.json")):
        raise RunError("completion.json exists: refuse to rerun into a completed out-dir")
    wl = try_flock(os.path.join(a.out_dir, f"worker{a.worker}.lock"))
    if wl is None:
        sys.exit(f"worker {a.worker} already running")
    attempt = os.environ.get("MC54_ATTEMPT", "manual")
    gpu = os.environ.get("CUDA_VISIBLE_DEVICES")
    t_proc = time.time()
    ev(a.out_dir, event="worker_start", worker=a.worker, attempt=attempt, gpu=gpu)
    torch, proc, model = G.load_model()
    env = G.env_info(torch, proc, model)
    core = {k: env[k] for k in G.CFG_KEYS}
    core.update({"caps_mc": S.CAPS_MC, "do_sample": False, "runner": RUNNER, "spec": S.SPEC_VERSION,
                 "dtype_scoring": "bf16 forward, fp32 log_softmax"})
    cdig = sha_bytes(canon(core).encode())
    if cdig != proto["generation_config_digest"]:
        sys.exit("runtime generation config digest != protocol")
    eos = env["eos_token_id"]
    eos_ids = set(eos if isinstance(eos, list) else [eos])
    img_tok = getattr(model.config, "image_token_id", None) or getattr(model.config, "image_token_index", None)
    ab_ids = [proc.tokenizer.encode(c, add_special_tokens=False) for c in ("A", "B")]
    if any(len(x) != 1 for x in ab_ids):
        sys.exit("A/B are not single tokens in this tokenizer")
    ab_ids = [x[0] for x in ab_ids]
    envp = os.path.join(a.out_dir, f"gen_worker{a.worker}.jsonl.env.json")
    if not os.path.exists(envp):
        json.dump({"env": env, "config_digest": cdig, "protocol_digest": pdig, "worker": a.worker, "ab_token_ids": ab_ids,
                   "physical_cuda_visible_devices": gpu}, open(envp, "w"), indent=1, default=str)
    ev(a.out_dir, event="model_ready", worker=a.worker, attempt=attempt, gpu=gpu)
    cache = {}

    def px(path):
        if path not in cache:
            cache[path] = load_rgb(path)[1]
        return cache[path]

    def read_all():
        own = sorted(glob.glob(os.path.join(a.out_dir, "gen_worker*.jsonl")))
        return {f: read_records(f) for f in parent_files + own}

    out = os.path.join(a.out_dir, f"gen_worker{a.worker}.jsonl")
    repair_tail(out)
    done = validate_records(read_all(), rows_by_id, ok_pdigs, cdig, px)
    cdir = os.path.join(a.out_dir, "claims")
    os.makedirs(cdir, exist_ok=True)
    log = open(out + ".log", "a")
    t0, n_new = time.time(), 0
    try:
        for row in sorted(todo_rows, key=lambda r: r["order_key"]):
            if row["request_id"] in done:
                continue
            if a.max_requests is not None and n_new >= a.max_requests:
                break
            fd = try_flock(os.path.join(cdir, row["request_id"] + ".claim"))
            if fd is None:
                continue
            try:
                done = validate_records(read_all(), rows_by_id, ok_pdigs, cdig, px)
                if row["request_id"] in done:
                    continue
                t_req = time.time()
                try:
                    pay, meta = compute_request(torch, proc, model, row, eos_ids, img_tok, ab_ids)
                except torch.cuda.OutOfMemoryError as e:
                    log.write(json.dumps({"event": "oom", "rid": row["request_id"], "err": str(e)[:200]}) + "\n")
                    log.flush()
                    raise
                rec = {"request_id": row["request_id"], "row_digest": row_digest(row), "kind": row["kind"], "cond": row["cond"],
                       "modality": row["modality"], "image": row["image"], "image_file_sha256": row["image_file_sha256"],
                       "prompt_sha256": row["prompt_sha256"], "payload": pay, **meta, "wall_s": time.time() - t_req,
                       "t_start": t_req, "ts": time.time(), "protocol_digest": pdig, "config_digest": cdig, "worker": a.worker,
                       "pid": os.getpid(), "attempt": attempt, "gpu_uuid": env.get("gpu_uuid")}
                rec["record_digest"] = record_digest(rec)
                with open(out, "a") as f:
                    f.write(json.dumps(rec) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                done[row["request_id"]] = rec
                n_new += 1
                log.write(json.dumps({"event": "done", "rid": row["request_id"], "cond": row["cond"],
                                      "wall_s": round(rec["wall_s"], 3), "elapsed": round(time.time() - t0, 1)}) + "\n")
                log.flush()
            finally:
                os.close(fd)
    finally:
        ev(a.out_dir, event="worker_end", worker=a.worker, attempt=attempt, gpu=gpu, n_new=n_new, t_proc_start=t_proc,
           load_s=None)
    print(f"worker {a.worker}: finished; {n_new} new requests", flush=True)


# ---------------- 완료 검증 / 비용 ----------------
def verify_completion(out_dir, requests_path, protocol_path):
    comp = json.load(open(os.path.join(out_dir, "completion.json")))
    pdig, proto = verify_protocol(protocol_path, requests_path)
    rebuild_check(requests_path)
    rows = read_requests(requests_path)
    stage = proto["stage"]
    want_rows = [r for r in rows if stage == "main" or r["stage"] == "tech"]
    rows_by_id = {r["request_id"]: r for r in want_rows}
    if comp.get("protocol_digest") != pdig or comp.get("stage") != stage or any(c != 0 for c in comp["exit_codes"]):
        raise RunError("completion protocol/stage/exit code invalid")
    files = sorted(glob.glob(os.path.join(out_dir, "gen_worker*.jsonl")))
    if sorted(os.path.basename(f) for f in files) != sorted(comp["worker_file_sha256"]):
        raise RunError("worker file set differs from completion")
    recs = []
    for fn in files:
        if comp["worker_file_sha256"][os.path.basename(fn)] != file_sha(fn):
            raise RunError(f"worker file changed after completion {fn}")
        recs += read_records(fn)
    ok_pdigs = {pdig}
    if proto["parent"]:
        ok_pdigs.add(proto["parent"]["protocol_digest"])
        for fn in sorted(glob.glob(os.path.join(proto["parent"]["out_dir"], "gen_worker*.jsonl"))):
            if comp["parent_worker_file_sha256"].get(os.path.basename(fn)) != file_sha(fn):
                raise RunError("parent worker file changed")
            recs += read_records(fn)
    ids = [r["request_id"] for r in recs]
    if len(ids) != len(set(ids)) or set(ids) != set(rows_by_id) or len(ids) != comp["n_requests"]:
        raise RunError("completion: request set mismatch (missing/duplicate/extra)")
    cache = {}

    def px(path):
        if path not in cache:
            cache[path] = load_rgb(path)[1]
        return cache[path]
    validate_records({"all": recs}, rows_by_id, ok_pdigs, proto["generation_config_digest"], px)
    for r in recs:
        row = rows_by_id[r["request_id"]]
        if row["modality"] == "image" and r["image_file_sha256"] != row["image_file_sha256"]:
            raise RunError("record image file sha != row")
        if r["kind"] == "ps" and not r["payload"]["boundary_ok"]:
            raise RunError("ps boundary flag false")
    return recs


def cost_report(out_dirs):
    """모든 attempt를 같은 범위로 집계한다. GPU별 (loading 포함 프로세스 구간 합집합) vs (요청 generation 구간 합집합).
    worker_end가 없는(강제 종료) 프로세스는 마지막 record ts(없으면 model_ready/start)를 종료로 쓰는 하한이다."""
    proc_iv, req_iv, per_attempt, lower_bound_procs = {}, {}, {}, 0
    n_rec = 0
    for d in out_dirs:
        evs = jl(os.path.join(d, "events.jsonl")) if os.path.exists(os.path.join(d, "events.jsonl")) else []
        recs = []
        for fn in sorted(glob.glob(os.path.join(d, "gen_worker*.jsonl"))):
            recs += read_records(fn)
        n_rec += len(recs)
        by_pid = {}
        for e in evs:
            by_pid.setdefault((e["pid"], e["worker"]), []).append(e)
        last_ts = {}
        for r in recs:
            last_ts[r["pid"]] = max(last_ts.get(r["pid"], 0), r["ts"])
            req_iv.setdefault(r["gpu_uuid"], []).append((r["t_start"], r["ts"]))
        for (pid, w), es in by_pid.items():
            st = [e for e in es if e["event"] == "worker_start"]
            en = [e for e in es if e["event"] == "worker_end"]
            if not st:
                continue
            t_s = st[0]["t"]
            if en:
                t_e = en[0]["t"]
            else:
                lower_bound_procs += 1
                mr = [e["t"] for e in es if e["event"] == "model_ready"]
                t_e = max([last_ts.get(pid, 0)] + mr + [t_s])
            gpu = st[0]["gpu"]
            proc_iv.setdefault(gpu, []).append((t_s, t_e))
            per_attempt.setdefault(st[0]["attempt"], []).append({"worker": w, "pid": pid, "gpu": gpu, "t_s": t_s, "t_e": t_e,
                                                                 "ended_normally": bool(en)})
    return {"device_seconds_incl_loading_union": sum(P43._union_len(v) for v in proc_iv.values()),
            "device_seconds_generate_union": sum(P43._union_len(v) for v in req_iv.values()),
            "n_gpu_groups_proc": len(proc_iv), "n_records": n_rec, "n_procs_without_end_lower_bound": lower_bound_procs,
            "sum_request_wall_s": None, "attempts": per_attempt}


# ---------------- launcher ----------------
def launch_main(a):
    pdig, proto = verify_protocol(a.protocol, a.requests)
    if proto["stage"] != a.stage:
        raise RunError("stage differs from protocol")
    rebuild_check(a.requests)
    os.makedirs(a.out_dir, exist_ok=True)
    if os.path.exists(os.path.join(a.out_dir, "completion.json")):
        raise RunError("completion.json exists in out-dir; use a new attempt dir")
    lk = try_flock(os.path.join(a.out_dir, "launch.lock"))
    if lk is None:
        sys.exit("another launcher owns this out-dir")
    allowed = P43.allowed_gpus()
    gpus = allowed
    if a.gpus:
        sel = [int(x) for x in a.gpus.split(",")]
        if not set(sel) <= set(allowed):
            sys.exit(f"--gpus {sel} not within inherited allowed set {allowed}")
        gpus = sel
    free = P43.gpu_free_mib()
    if any(g not in free for g in gpus):
        sys.exit("allowed gpus not all visible to nvidia-smi")
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
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(mapping[k]), MC54_ATTEMPT=attempt)
        cmd = [sys.executable, "mc54_run.py", "worker", "--stage", a.stage, "--requests", a.requests, "--protocol", a.protocol,
               "--out-dir", a.out_dir, "--worker", str(k)]
        if a.max_requests is not None:
            cmd += ["--max-requests", str(a.max_requests)]
        procs[k] = subprocess.Popen(cmd, env=env, stdout=open(os.path.join(a.out_dir, f"worker{k}.{attempt}.stdout"), "a"),
                                    stderr=open(os.path.join(a.out_dir, f"worker{k}.{attempt}.stderr"), "a"))
    rl = open(os.path.join(a.out_dir, "resource_log.jsonl"), "a")
    while any(p.poll() is None for p in procs.values()):
        time.sleep(10)
        used = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
                              capture_output=True, text=True).stdout.strip().splitlines()
        rl.write(json.dumps({"attempt": attempt, "t": round(time.time() - t0, 1), "gpu": used}) + "\n")
        rl.flush()
    codes = [procs[k].returncode for k in range(a.workers)]
    wall = time.time() - t0
    ev(a.out_dir, event="launch_end", worker=-1, attempt=attempt, exit_codes=codes, wall_s=wall)
    rows = read_requests(a.requests)
    want = [r for r in rows if a.stage == "main" or r["stage"] == "tech"]
    recs = []
    for fn in sorted(glob.glob(os.path.join(a.out_dir, "gen_worker*.jsonl"))):
        recs += read_records(fn)
    if proto["parent"]:
        pf = sorted(glob.glob(os.path.join(proto["parent"]["out_dir"], "gen_worker*.jsonl")))
        for fn in pf:
            recs += read_records(fn)
    n_unique = len({r["request_id"] for r in recs})
    if a.max_requests is None and all(c == 0 for c in codes) and n_unique == len(want) == len(recs):
        dirs = [a.out_dir] + ([proto["parent"]["out_dir"]] if proto["parent"] else [])
        res = {"stage": a.stage, "exit_codes": codes, "wall_s_this_attempt": wall, "n_records": len(recs), "n_unique": n_unique,
               "n_requests": len(want), "workers": a.workers, "mapping": mapping, "protocol_digest": pdig, "attempt": attempt,
               "worker_file_sha256": {os.path.basename(f): file_sha(f) for f in sorted(glob.glob(os.path.join(a.out_dir, "gen_worker*.jsonl")))},
               "parent_worker_file_sha256": ({os.path.basename(f): file_sha(f) for f in pf} if proto["parent"] else {}),
               "cost_all_attempts": cost_report(dirs), "cost_this_dir_only": cost_report([a.out_dir]),
               "sum_request_wall_s_all_records": sum(r["wall_s"] for r in recs),
               "peak_mem_reserved_gb_max": max(r["payload"]["peak_mem_reserved_gb"] for r in recs),
               "by_kind_mean_wall_s": {k: sum(r["wall_s"] for r in recs if r["kind"] == k) / max(1, sum(r["kind"] == k for r in recs))
                                       for k in ("mc", "gd", "ps")},
               "n_mc_retries": sum(len(r["payload"]["attempts"]) > 1 for r in recs if r["kind"] == "mc"),
               "n_forward_calls": sum(r["kind"] in ("gd", "ps") for r in recs),
               "n_generate_calls_all_attempts": sum(len(r["payload"]["attempts"]) for r in recs if r["kind"] == "mc")}
        tmp = os.path.join(a.out_dir, f"completion.{os.getpid()}.tmp")
        json.dump(res, open(tmp, "w"), indent=1)
        os.replace(tmp, os.path.join(a.out_dir, "completion.json"))
        print("completion written", json.dumps({k: res[k] for k in ("exit_codes", "wall_s_this_attempt", "n_unique")}))
    else:
        json.dump({"exit_codes": codes, "wall_s": wall, "n_unique": n_unique, "n_requests": len(want), "attempt": attempt},
                  open(os.path.join(a.out_dir, f"partial_{attempt}.json"), "w"), indent=1)
        print("NOT complete", codes, n_unique, len(want))
        sys.exit(0 if a.max_requests is not None else 1)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    w, l, pp = sub.add_parser("worker"), sub.add_parser("launch"), sub.add_parser("protocol")
    pp.add_argument("--stage", required=True, choices=["tech", "main"])
    pp.add_argument("--requests", required=True)
    pp.add_argument("--out", required=True)
    pp.add_argument("--gate", default=None)
    pp.add_argument("--parent-out-dir", default=None)
    pp.add_argument("--parent-protocol", default=None)
    for s in (w, l):
        s.add_argument("--stage", required=True, choices=["tech", "main"])
        s.add_argument("--requests", required=True)
        s.add_argument("--protocol", required=True)
        s.add_argument("--out-dir", required=True)
        s.add_argument("--max-requests", type=int, default=None)
    w.add_argument("--worker", type=int, required=True)
    l.add_argument("--workers", type=int, required=True)
    l.add_argument("--gpus", default=None)
    l.add_argument("--peak-gb", type=float, default=12.0)
    a = ap.parse_args()
    if a.cmd == "protocol":
        make_protocol(a.stage, a.requests, a.out, a.gate, a.parent_out_dir, a.parent_protocol)
        return
    (worker_main if a.cmd == "worker" else launch_main)(a)


if __name__ == "__main__":
    main()
