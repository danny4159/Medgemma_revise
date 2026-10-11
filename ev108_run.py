"""iter_108 다중 영상 생성 runner + launcher (MedGemma 1.5 bf16, frozen, greedy; 결과는 results/iter_108 아래에만 쓴다).

기존 pg43_run의 소유권(flock)·부분 행 복구·record digest·occupancy 패턴을 재사용하고, 이번 경로에서 다음을 보완한다:
 - 요청 행 전체 재구성(request_id 재계산), 영상 목록(역할·file/pixel hash) 검증, 다중 영상 chat 입력과 영상별 tensor hash 기록
 - 가중치 파일 내용 sha256을 protocol에 잠그고 worker가 시작 시 다시 계산해 대조 (파일 크기만으로 계승하지 않음)
 - launcher: 허용 GPU 집합 검사, 시작 직전 실제 여유 메모리와 이미 배정한 worker 예약(peak+2GiB) 합산, admission 실패·attempt 종료 상태 보존
 - completion은 전 요청 집합·영상·tensor 연결을 검증한 뒤에만 쓴다
worker:  CUDA_VISIBLE_DEVICES=<물리 gpu> python ev108_run.py worker --requests R --protocol P --out-dir D --worker K
launcher: python ev108_run.py launch --requests R --protocol P --out-dir D --workers N --peak-gb X [--gpus 0,1]
protocol: python ev108_run.py protocol --requests R --out P [--gate G] [--lock files...]
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

import ev108_spec as S
from pg43_run import (sha_bytes, file_sha, canon, read_records, repair_tail, try_flock, gpu_free_mib, allowed_gpus, _union_len,
                      record_digest, row_digest)
from rsna_diag import generate as G
from rsna_diag import geometry

ROOT = Path(__file__).resolve().parent
R108 = ROOT / "results/iter_108"
CODE_FILES = ["ev108_run.py", "ev108_spec.py", "ev108_data.py", "ev108_build.py", "ev108_eval.py", "ev108_report.py", "pg43_run.py",
              "rsna_diag/generate.py", "rsna_diag/geometry.py", "rsna_diag/qa_spec.py", "rsna_diag/prompts.py"]
RUNNER = "ev108_run_v1"
COND_ROLES = {"F": ["orig"], "D": ["orig", "orig_dup"], "T": ["orig", "crop_pred"], "C": ["orig", "crop_center"], "L": ["crop_pred"]}
SNAP = ROOT.parent / "hf_cache/hub/models--google--medgemma-1.5-4b-it/snapshots" / G.MODEL_REVISION
STAGES = ("FREPRO", "TECH", "P180R", "E600R")


class RunError(RuntimeError):
    pass


# ---------------- 요청 ----------------
def expected_request_id(row):
    fields = {"patient": row["patient"], "cond": row["cond"], "target": row["target"], "prompt_sha256": row["prompt_sha256"],
              "caps": row["caps"], "images": [(i["role"], i["pixel_sha256"]) for i in row["images"]], "model_revision": G.MODEL_REVISION}
    return S.sha(S.canon(fields))[:32]


def read_requests(path):
    rows = [json.loads(l) for l in open(path) if l.strip()]
    ids = [r["request_id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise RunError("duplicate request_id")
    ok = {}
    for r in rows:
        if r["stage"] not in STAGES:
            raise RunError(f"bad stage {r['request_id']}")
        if r["request_id"] != expected_request_id(r):
            raise RunError(f"request_id does not match row fields {r['request_id']}")
        if S.sha(r["prompt"]) != r["prompt_sha256"]:
            raise RunError(f"prompt hash mismatch {r['request_id']}")
        if [i["role"] for i in r["images"]] != COND_ROLES[r["cond"]]:
            raise RunError(f"image roles != condition {r['request_id']}")
        if r["cond"] == "D" and r["images"][0]["pixel_sha256"] != r["images"][1]["pixel_sha256"]:
            raise RunError(f"D images differ {r['request_id']}")
        if r["cond"] == "L" and r["target"] != "O":
            raise RunError("L is O only")
        if r["prompt"] != (S.core_prompt(r["target"]) if r["cond"] == "F" else S.prompt_for(r["cond"], r["target"])):
            raise RunError(f"prompt != fixed template {r['request_id']}")
        ok[r["request_id"]] = r
    return rows


def load_img(path):
    """PNG -> 값 보존 RGB -> 정사각 padding. returns (PIL RGB, pixel sha). F 기존 경로(generate.load_image)와 동일."""
    img, _, px = G.load_image(str(ROOT / path) if not os.path.isabs(path) else path)
    return img, px


def weights_digests(snap=SNAP):
    return {p.name: {"sha256": file_sha(p.resolve()), "size": p.resolve().stat().st_size} for p in sorted(Path(snap).iterdir())}


# ---------------- protocol ----------------
def make_protocol(requests_path, out_path, gate=None, lock=(), weights_ref=None):
    rows = read_requests(requests_path)
    core, cdig = static_config()
    img_set = sorted({(i["path"], i["file_sha256"], i["pixel_sha256"]) for r in rows for i in r["images"]})
    for p, fh, ph in img_set:
        if file_sha(ROOT / p) != fh or load_img(p)[1] != ph:
            raise RunError(f"image changed before protocol lock: {p}")
    if weights_ref:
        wd = json.load(open(weights_ref))["files"]
    else:
        wd = weights_digests()
    d = {"runner": RUNNER, "created": time.time(), "code": {f: file_sha(f) for f in CODE_FILES}, "locked_files": {f: file_sha(f) for f in lock},
         "requests_path": requests_path, "requests_sha256": file_sha(requests_path), "n_requests": len(rows),
         "images_digest": sha_bytes(canon(img_set).encode()), "n_by_cond": {c: sum(r["cond"] == c for r in rows) for c in COND_ROLES},
         "stages": sorted({r["stage"] for r in rows}), "generation_config_digest": cdig, "generation_config": core, "weights": wd,
         "model_revision": G.MODEL_REVISION, "gate": None}
    if gate:
        g = json.load(open(gate))
        if g.get("run") is not True:
            raise RunError(f"gate does not permit: {gate}")
        d["gate"] = {"path": gate, "sha256": file_sha(gate)}
    if os.path.exists(out_path):
        raise RunError(f"protocol exists: {out_path}")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    tmp = out_path + f".{os.getpid()}.tmp"
    json.dump(d, open(tmp, "w"), indent=1)
    os.replace(tmp, out_path)
    return d


def static_config():
    env = G.static_env()
    core = {k: env[k] for k in G.CFG_KEYS}
    core.update({"caps": S.CAPS, "do_sample": False, "runner": RUNNER, "guide_dtc": S.sha(S.GUIDE_DTC), "guide_l": S.sha(S.GUIDE_L)})
    return core, sha_bytes(canon(core).encode())


def verify_protocol(path, requests_path):
    p = json.load(open(path))
    bad = [f for f, h in p["code"].items() if file_sha(f) != h]
    if bad:
        raise RunError(f"code changed since protocol lock: {bad}")
    badl = [f for f, h in p["locked_files"].items() if file_sha(f) != h]
    if badl:
        raise RunError(f"locked file changed: {badl}")
    if file_sha(requests_path) != p["requests_sha256"]:
        raise RunError("requests file changed since protocol lock")
    if p.get("gate") and (file_sha(p["gate"]["path"]) != p["gate"]["sha256"] or json.load(open(p["gate"]["path"])).get("run") is not True):
        raise RunError("stage gate decision missing/changed/not permitting")
    return sha_bytes(canon(p).encode()), p


def verify_weights(proto):
    t = time.time()
    now = weights_digests()
    if now != proto["weights"]:
        raise RunError("weight/asset content digest differs from protocol lock")
    return time.time() - t


# ---------------- records ----------------
def validate_records(files, rows_by_id, pdig, cdig, px):
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
            if r.get("protocol_digest") != pdig or r.get("config_digest") != cdig:
                raise RunError(f"protocol/config mismatch {rid}")
            if any(r.get(k) != row.get(k) for k in ("cond", "patient", "target", "kind", "stage")):
                raise RunError(f"record identity != row {rid}")
            if r.get("input_pixel_sha256") != [i["pixel_sha256"] for i in row["images"]] or r.get("n_images") != len(row["images"]):
                raise RunError(f"record image hashes != row {rid}")
            for i in row["images"]:
                if px(i["path"]) != i["pixel_sha256"]:
                    raise RunError(f"current image pixel hash differs {i['path']}")
            if r.get("n_image_tokens") != r["image_seq_length"] * len(row["images"]) or r.get("n_pixel_values") != len(row["images"]):
                raise RunError(f"image token/tensor count != images {rid}")
            if r.get("adapter_digest") is not None:
                raise RunError("adapter must be absent (frozen base)")
            done[rid] = r
    return done


def build_inputs_multi(proc, images, prompt):
    content = [{"type": "image", "image": im} for im in images] + [{"type": "text", "text": prompt}]
    return proc.apply_chat_template([{"role": "user", "content": content}], add_generation_prompt=True, tokenize=True,
                                    return_dict=True, return_tensors="pt")


def tensor_shas(pv):
    return [sha_bytes(np.ascontiguousarray(pv[i].float().cpu().numpy()).tobytes()) for i in range(pv.shape[0])]


# ---------------- worker ----------------
def worker_main(a):
    pdig, proto = verify_protocol(a.protocol, a.requests)
    rows = read_requests(a.requests)
    rows_by_id = {r["request_id"]: r for r in rows}
    os.makedirs(a.out_dir, exist_ok=True)
    out_dir = Path(a.out_dir).resolve()
    out_dir.relative_to(R108)
    if (out_dir / "completion.json").exists():
        raise RunError("completion.json exists: refuse to rerun into a completed out-dir")
    wl = try_flock(str(out_dir / f"worker{a.worker}.lock"))
    if wl is None:
        sys.exit(f"worker {a.worker} already running")
    t_proc_start = time.time()
    wv_s = verify_weights(proto)
    torch, proc, model = G.load_model()
    t_model_ready = time.time()
    env = G.env_info(torch, proc, model)
    core = {k: env[k] for k in G.CFG_KEYS}
    core.update({"caps": S.CAPS, "do_sample": False, "runner": RUNNER, "guide_dtc": S.sha(S.GUIDE_DTC), "guide_l": S.sha(S.GUIDE_L)})
    cdig = sha_bytes(canon(core).encode())
    if cdig != proto["generation_config_digest"]:
        sys.exit("runtime generation config digest != protocol")
    eos = env["eos_token_id"]
    eos_ids = set(eos if isinstance(eos, list) else [eos])
    seq_len = proc.image_seq_length
    img_tok = model.config.image_token_index  # <image_soft_token> (processor.image_token_id는 <start_of_image>)
    if img_tok != proc.tokenizer.convert_tokens_to_ids("<image_soft_token>"):
        sys.exit("image soft token id mismatch")
    envp = out_dir / f"gen_worker{a.worker}.jsonl.env.json"
    if not envp.exists():
        json.dump({"env": env, "config_digest": cdig, "protocol_digest": pdig, "worker": a.worker,
                   "physical_cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES")}, open(envp, "w"), indent=1, default=str)
    cache = {}

    def px(path):
        if path not in cache:
            cache[path] = load_img(path)[1]
        return cache[path]

    def read_all():
        return {f: read_records(f) for f in sorted(glob.glob(str(out_dir / "gen_worker*.jsonl")))}

    out = str(out_dir / f"gen_worker{a.worker}.jsonl")
    repair_tail(out)
    done = validate_records(read_all(), rows_by_id, pdig, cdig, px)
    cdir = out_dir / "claims"
    cdir.mkdir(exist_ok=True)
    log = open(out + ".log", "a")
    t0, n_new = time.time(), 0
    for row in sorted(rows, key=lambda r: r["order_key"]):
        if row["request_id"] in done:
            continue
        if a.max_requests is not None and n_new >= a.max_requests:
            break
        fd = try_flock(str(cdir / (row["request_id"] + ".claim")))
        if fd is None:
            continue
        try:
            done = validate_records(read_all(), rows_by_id, pdig, cdig, px)
            if row["request_id"] in done:
                continue
            tw = time.time()
            try:
                loaded = [load_img(i["path"]) for i in row["images"]]
                inp = build_inputs_multi(proc, [x[0] for x in loaded], row["prompt"])
                ids_in = inp["input_ids"][0].tolist()
                n_img_tok = sum(1 for t in ids_in if t == img_tok)
                if "pixel_values" not in inp or inp["pixel_values"].shape[0] != len(row["images"]) or n_img_tok != seq_len * len(row["images"]):
                    raise RunError(f"image tensor/token count mismatch {row['request_id']}: pv={tuple(inp['pixel_values'].shape)} tok={n_img_tok}")
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
            rec = {"request_id": row["request_id"], "row_digest": row_digest(row), "stage": row["stage"], "cond": row["cond"],
                   "patient": row["patient"], "target": row["target"], "kind": row["kind"], "prompt_sha256": row["prompt_sha256"],
                   "n_images": len(row["images"]), "input_pixel_sha256": [x[1] for x in loaded], "image_seq_length": seq_len,
                   "n_image_tokens": n_img_tok, "n_pixel_values": int(inp["pixel_values"].shape[0]),
                   "pixel_values_sha256_per_image": tensor_shas(inp["pixel_values"]), "pixel_values_shape": list(inp["pixel_values"].shape),
                   "input_keys": sorted(inp.keys()), "n_input_tokens": len(ids_in),
                   "input_ids_sha256": sha_bytes(json.dumps(ids_in).encode()),
                   "suffix_ids": fin["suffix_ids"], "suffix_text_raw": fin["suffix_text_raw"], "n_output_tokens": fin["n_new"],
                   "finish_reason": fin["finish_reason"], "ended_eos": fin["ended_eos"], "final_cap": fin["cap"],
                   "attempts": [{k: v for k, v in at.items() if k != "suffix_ids"} for at in attempts],
                   "runtime_s_total": sum(at["runtime_s"] for at in attempts), "wall_s": time.time() - tw, "t_start": tw,
                   "peak_mem_alloc_gb_max": max(at["peak_mem_alloc_gb"] for at in attempts),
                   "peak_mem_reserved_gb_max": max(at["peak_mem_reserved_gb"] for at in attempts),
                   "protocol_digest": pdig, "config_digest": cdig, "adapter_digest": None, "worker": a.worker, "ts": time.time(),
                   "gpu_uuid": env.get("gpu_uuid")}
            rec["record_digest"] = record_digest(rec)
            with open(out, "a") as f:
                f.write(json.dumps(rec) + "\n")
                f.flush()
                os.fsync(f.fileno())
            done[row["request_id"]] = rec
            n_new += 1
            log.write(json.dumps({"event": "done", "rid": row["request_id"], "cond": row["cond"], "n_out": rec["n_output_tokens"],
                                  "finish": rec["finish_reason"], "runtime_s": round(rec["runtime_s_total"], 2),
                                  "peak_gb": round(rec["peak_mem_alloc_gb_max"], 2), "elapsed": round(time.time() - t0, 1)}) + "\n")
            log.flush()
        finally:
            os.close(fd)
    tp = out_dir / f"worker{a.worker}.timing.{int(t_proc_start)}.{os.getpid()}.json"
    json.dump({"worker": a.worker, "pid": os.getpid(), "t_proc_start": t_proc_start, "t_model_ready": t_model_ready, "t_end": time.time(),
               "n_new": n_new, "load_s": t_model_ready - t_proc_start, "weights_verify_s": wv_s,
               "physical_cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES")}, open(tp, "x"), indent=1)
    print(f"worker {a.worker}: finished; {n_new} new requests", flush=True)


# ---------------- 검증 (평가 진입점) ----------------
def verify_records(out_dir, requests_path, protocol_path):
    """completion 없이도 호출 가능한 전수 검증: 요청 집합 정확 일치, record digest, 영상 file/pixel, tensor/토큰 연결. returns recs."""
    pdig, proto = verify_protocol(protocol_path, requests_path)
    rows = read_requests(requests_path)
    rows_by_id = {r["request_id"]: r for r in rows}
    cdig = proto["generation_config_digest"]
    cache = {}

    def px(path):
        if path not in cache:
            if file_sha(ROOT / path) != next(i["file_sha256"] for r in rows for i in r["images"] if i["path"] == path):
                raise RunError(f"current image file hash differs {path}")
            cache[path] = load_img(path)[1]
        return cache[path]

    files = {f: read_records(f) for f in sorted(glob.glob(os.path.join(out_dir, "gen_worker*.jsonl")))}
    done = validate_records(files, rows_by_id, pdig, cdig, px)
    if set(done) != set(rows_by_id):
        raise RunError(f"request set mismatch: missing {len(set(rows_by_id) - set(done))}")
    # 같은 환자의 첫 영상 tensor는 D/T/C(및 F)에서 동일해야 한다
    first = {}
    for r in done.values():
        if r["cond"] in ("D", "T", "C", "F"):
            first.setdefault(r["patient"], set()).add(r["pixel_values_sha256_per_image"][0])
    bad = [p for p, s in first.items() if len(s) != 1]
    if bad:
        raise RunError(f"original-image tensor differs across conditions for {bad[:3]}")
    for r in done.values():
        if r["cond"] == "D" and r["pixel_values_sha256_per_image"][0] != r["pixel_values_sha256_per_image"][1]:
            raise RunError("D duplicate image tensors differ")
    return list(done.values()), proto, pdig


def verify_completion(out_dir, requests_path, protocol_path):
    recs, proto, pdig = verify_records(out_dir, requests_path, protocol_path)
    comp = json.load(open(os.path.join(out_dir, "completion.json")))
    if comp.get("protocol_digest") != pdig or any(c != 0 for c in comp["exit_codes"]) or comp["n_requests"] != len(recs):
        raise RunError("completion protocol/exit code/count invalid")
    files_now = sorted(os.path.basename(f) for f in glob.glob(os.path.join(out_dir, "gen_worker*.jsonl")))
    if files_now != sorted(comp["worker_file_sha256"]) or any(comp["worker_file_sha256"][os.path.basename(f)] != file_sha(f)
                                                              for f in glob.glob(os.path.join(out_dir, "gen_worker*.jsonl"))):
        raise RunError("worker files differ from completion")
    return recs


# ---------------- launcher ----------------
def occupancy(recs, out_dir, mapping, wall):
    req_iv, proc_iv = {}, {}
    for r in recs:
        req_iv.setdefault(mapping[r["worker"]], []).append((r["t_start"], r["ts"]))
    for fn in glob.glob(os.path.join(out_dir, "worker*.timing.*.json")):
        t = json.load(open(fn))
        if t["worker"] in mapping:
            proc_iv.setdefault(mapping[t["worker"]], []).append((t["t_proc_start"], t["t_end"]))
    tmin = min(s for iv in req_iv.values() for s, _ in iv)
    tmax = max(e for iv in req_iv.values() for _, e in iv)
    return {"device_seconds_generate_union": sum(_union_len(iv) for iv in req_iv.values()),
            "device_seconds_incl_loading_union": sum(_union_len(iv) for iv in proc_iv.values()) if proc_iv else None,
            "n_gpus_used": len(req_iv), "first_request_start_to_last_end_s": tmax - tmin, "launcher_wall_s_incl_loading": wall}


def next_attempt(out_dir):
    nums = [int(Path(p).name.split("_")[1].split(".")[0]) for p in glob.glob(os.path.join(out_dir, "launch_*.start.json"))]
    return max(nums) + 1 if nums else 0


def launch_main(a):
    out_dir = Path(a.out_dir).resolve()
    out_dir.relative_to(R108)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdig, proto = verify_protocol(a.protocol, a.requests)
    if (out_dir / "completion.json").exists():
        raise RunError("completion.json exists; use a new attempt dir")
    lk = try_flock(str(out_dir / "launch.lock"))
    if lk is None:
        sys.exit("another launcher owns this out-dir")
    attempt = next_attempt(str(out_dir))
    state = {"attempt": attempt, "t_start": time.time(), "workers": a.workers, "peak_gb": a.peak_gb, "requests": a.requests, "protocol": a.protocol,
             "protocol_digest": pdig, "inherited_cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"), "status": "started"}
    json.dump(state, open(out_dir / f"launch_{attempt:03d}.start.json", "x"), indent=1)

    def end(extra):
        state.update(extra)
        state["t_end"] = time.time()
        json.dump(state, open(out_dir / f"launch_{attempt:03d}.end.json", "x"), indent=1, default=str)

    try:
        gpus = allowed_gpus()
        if a.gpus:
            sel = [int(x) for x in a.gpus.split(",")]
            if not set(sel) <= set(gpus):
                raise RunError(f"--gpus {sel} not within inherited allowed set {gpus}")
            gpus = sel
        free = gpu_free_mib()
        if any(g not in free for g in gpus):
            raise RunError(f"allowed gpus {gpus} not all visible to nvidia-smi {sorted(free)}")
        state["free_mib_before"] = free
        gpus = sorted(gpus, key=lambda g: (-free[g], g))
        per = {}
        for k in range(a.workers):
            per.setdefault(gpus[k % len(gpus)], []).append(k)
        for g, ws in per.items():
            need = len(ws) * (a.peak_gb + 2.0) * 1024
            if free[g] < need:
                state["admission"] = {"refused": True, "gpu": g, "free_mib": free[g], "need_mib": need, "workers": ws}
                raise RunError(f"admission refused: gpu {g}: free {free[g]}MiB < need {need:.0f}MiB for workers {ws}")
        mapping = {k: gpus[k % len(gpus)] for k in range(a.workers)}
        state["admission"] = {"refused": False, "mapping": mapping, "per_gpu_need_mib": {g: len(ws) * (a.peak_gb + 2.0) * 1024 for g, ws in per.items()}}
        procs = {}
        t0 = time.time()
        for k in range(a.workers):
            env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(mapping[k]))
            cmd = [sys.executable, "ev108_run.py", "worker", "--requests", a.requests, "--protocol", a.protocol, "--out-dir", str(out_dir),
                   "--worker", str(k)]
            if a.max_requests is not None:
                cmd += ["--max-requests", str(a.max_requests)]
            procs[k] = subprocess.Popen(cmd, env=env, cwd=ROOT, stdout=open(out_dir / f"worker{k}.a{attempt}.stdout", "a"),
                                        stderr=open(out_dir / f"worker{k}.a{attempt}.stderr", "a"))
            time.sleep(a.stagger)
        rl = open(out_dir / f"resource_log.a{attempt}.jsonl", "a")
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
        for fn in sorted(glob.glob(str(out_dir / "gen_worker*.jsonl"))):
            recs += read_records(fn)
        uniq = len({r["request_id"] for r in recs})
        cost = {"sum_request_wall_s": sum(r["wall_s"] for r in recs), "sum_generate_runtime_s": sum(r["runtime_s_total"] for r in recs),
                "n_records_with_retry": sum(len(r["attempts"]) > 1 for r in recs),
                "peak_mem_reserved_gb_max": max(r["peak_mem_reserved_gb_max"] for r in recs),
                "peak_mem_alloc_gb_max": max(r["peak_mem_alloc_gb_max"] for r in recs),
                "n_not_eos_final": sum(not r["ended_eos"] for r in recs),
                "new_tokens_all_attempts": sum(at["n_new"] for r in recs for at in r["attempts"])}
        cost.update(occupancy(recs, str(out_dir), mapping, wall))
        res = {"cost": cost, "exit_codes": codes, "wall_s": wall, "n_records": len(recs), "n_unique": uniq, "n_requests": len(rows),
               "workers": a.workers, "mapping": mapping, "protocol_digest": pdig, "attempt": attempt}
        if a.max_requests is None and all(c == 0 for c in codes) and uniq == len(rows) == len(recs):
            verify_records(str(out_dir), a.requests, a.protocol)  # 봉인 전 전수 검증
            res["worker_file_sha256"] = {os.path.basename(f): file_sha(f) for f in sorted(glob.glob(str(out_dir / "gen_worker*.jsonl")))}
            tmp = out_dir / f"completion.{os.getpid()}.tmp"
            json.dump(res, open(tmp, "w"), indent=1)
            os.replace(tmp, out_dir / "completion.json")
            end({"status": "completed", "result": {k: res[k] for k in ("exit_codes", "wall_s", "n_unique")}})
            print("completion written", json.dumps({k: res[k] for k in ("exit_codes", "wall_s", "n_unique")}))
        else:
            json.dump(res, open(out_dir / f"partial_a{attempt}.json", "w"), indent=1)
            end({"status": "incomplete", "result": {k: res[k] for k in ("exit_codes", "wall_s", "n_unique", "n_requests")}})
            print("NOT complete", json.dumps({k: res[k] for k in ("exit_codes", "wall_s", "n_unique", "n_requests")}))
            sys.exit(1)
    except BaseException as e:
        if not (out_dir / f"launch_{attempt:03d}.end.json").exists():
            end({"status": "error", "error": repr(e)[:500]})
        raise


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    w, l, pp = sub.add_parser("worker"), sub.add_parser("launch"), sub.add_parser("protocol")
    pp.add_argument("--requests", required=True)
    pp.add_argument("--out", required=True)
    pp.add_argument("--gate", default=None)
    pp.add_argument("--lock", nargs="*", default=[])
    pp.add_argument("--weights-ref", default=None, help="이미 계산해 둔 weights digest json (files 키)")
    for s in (w, l):
        s.add_argument("--requests", required=True)
        s.add_argument("--protocol", required=True)
        s.add_argument("--out-dir", required=True)
        s.add_argument("--max-requests", type=int, default=None)
    w.add_argument("--worker", type=int, required=True)
    l.add_argument("--workers", type=int, required=True)
    l.add_argument("--gpus", default=None)
    l.add_argument("--peak-gb", type=float, required=True)
    l.add_argument("--stagger", type=float, default=20.0)
    a = ap.parse_args()
    if a.cmd == "protocol":
        make_protocol(a.requests, a.out, gate=a.gate, lock=a.lock, weights_ref=a.weights_ref)
        return
    (worker_main if a.cmd == "worker" else launch_main)(a)


if __name__ == "__main__":
    main()
