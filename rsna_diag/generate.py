"""MedGemma 1.5 실제 생성 runner (iter_010 v2). batch=1, bf16, greedy, 요청 단위 append/재개.

- GT는 읽지 않는다 (infer manifest의 id/image만 사용).
- cap 래더: 1000 -> (EOS 없이 상한 도달 시) 2000 -> 4000. 각 시도를 record.attempts에 보존한다.
- 재개: 모든 기존 worker 출력(완료 요청 포함)을 현재 입력·model/adapter·prompt·config·protocol과 대조하고, 중복·충돌·잉여는 중단한다.
- worker별 출력 gen_worker{k}.jsonl, 환자 단위 flock claim, worker lock. --protocol(잠긴 protocol 경로)은 필수.
사용: CUDA_VISIBLE_DEVICES=<물리 gpu> python -m rsna_diag.generate --manifest ... --prompts ... --out-dir D --worker K --protocol P [--adapter DIR]
     (보통 run_shards가 호출한다)
"""
import argparse
import hashlib
import json
import os
import sys
import time

import numpy as np
from PIL import Image

from . import geometry, prompts as P

MODEL_ID = "google/medgemma-1.5-4b-it"
MODEL_REVISION = "91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b"
HF_HOME = "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache"
CAPS = [1000, 2000, 4000]
PREPROC_VERSION = "value_preserving_v1"
RUNNER_VERSION = "iter010_gen_v2"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def load_model():
    os.environ.setdefault("HF_HOME", HF_HOME)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    import torch
    import transformers
    torch.manual_seed(0)
    proc = transformers.AutoProcessor.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
    model = transformers.AutoModelForImageTextToText.from_pretrained(
        MODEL_ID, revision=MODEL_REVISION, dtype=torch.bfloat16, device_map="cuda")
    model.eval()
    return torch, proc, model


def env_info(torch, proc, model):
    import transformers
    import PIL
    ip = proc.image_processor
    gc = model.generation_config
    return {
        "model_id": MODEL_ID, "model_revision": MODEL_REVISION,
        "commit_hash": getattr(model.config, "_commit_hash", None),
        "name_or_path": model.config._name_or_path,
        "transformers": transformers.__version__, "torch": torch.__version__, "PIL": PIL.__version__,
        "numpy": np.__version__, "dtype": str(model.dtype),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "gpu_name": torch.cuda.get_device_name(0),
        "gpu_uuid": _uuid(torch),
        "processor_class": type(proc).__name__, "image_processor_class": type(ip).__name__,
        "image_size": str(getattr(ip, "size", None)), "do_pan_and_scan": getattr(ip, "do_pan_and_scan", None),
        "do_resize": getattr(ip, "do_resize", None), "do_rescale": getattr(ip, "do_rescale", None),
        "rescale_factor": getattr(ip, "rescale_factor", None), "do_normalize": getattr(ip, "do_normalize", None),
        "image_mean": getattr(ip, "image_mean", None), "image_std": getattr(ip, "image_std", None),
        "image_seq_length": getattr(proc, "image_seq_length", None),
        "generation_config": gc.to_dict(),
        "eos_token_id": gc.eos_token_id,
        "chat_template_sha256": sha((proc.chat_template or "").encode()),
        "preprocess": PREPROC_VERSION, "runner": RUNNER_VERSION,
    }


def _uuid(torch):
    try:
        return str(torch.cuda.get_device_properties(0).uuid)
    except Exception:
        return None


def load_image(path):
    """PNG(L uint8) -> 값 보존 RGB -> 정사각 padding. returns (PIL RGB, affine, pixel sha)."""
    arr = np.asarray(Image.open(path))
    rgb = geometry.to_uint8_rgb_preserving(arr)
    padded, aff = geometry.pad_square(rgb)
    return Image.fromarray(padded), aff, sha(padded.tobytes())


def build_inputs(proc, image, prompt):
    msgs = [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": prompt}]}]
    return proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True, return_dict=True,
                                    return_tensors="pt")


def generate(torch, proc, model, inp, cap, eos_ids):
    dev = "cuda"
    x = {k: (v.to(dev, dtype=torch.bfloat16) if k == "pixel_values" else v.to(dev)) for k, v in inp.items()}
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    with torch.no_grad():
        out = model.generate(**x, max_new_tokens=cap, do_sample=False)
    torch.cuda.synchronize()
    dt = time.time() - t0
    n_in = x["input_ids"].shape[1]
    ids = out[0, n_in:].tolist()
    ended = len(ids) > 0 and ids[-1] in eos_ids
    return {"cap": cap, "suffix_ids": ids, "n_new": len(ids), "ended_eos": bool(ended),
            "finish_reason": "eos" if ended else "length", "runtime_s": dt,
            "peak_mem_alloc_gb": torch.cuda.max_memory_allocated() / 2**30,
            "peak_mem_reserved_gb": torch.cuda.max_memory_reserved() / 2**30}


def run_request(torch, proc, model, eos_ids, item, pname, prompt, caps=CAPS):
    image, aff, px = load_image(item["image"])
    inp = build_inputs(proc, image, prompt)
    ids_in = inp["input_ids"][0].tolist()
    attempts = []
    for cap in caps:
        a = generate(torch, proc, model, inp, cap, eos_ids)
        if attempts:
            prev = attempts[-1]["suffix_ids"]
            a["prefix_matches_previous"] = a["suffix_ids"][:len(prev)] == prev
        attempts.append(a)
        if a["ended_eos"]:
            break
    fin = attempts[-1]
    for a in attempts:
        a["suffix_text_raw"] = proc.tokenizer.decode(a["suffix_ids"], skip_special_tokens=False)
    return {
        "id": item["id"], "prompt_name": pname, "prompt_sha256": P.digest(prompt),
        "image": item["image"], "image_file_sha256": item.get("file_sha256"), "input_pixel_sha256": px,
        "pad_affine_top_left_side": list(aff), "n_input_tokens": len(ids_in), "input_ids": ids_in,
        "input_ids_sha256": sha(json.dumps(ids_in).encode()),
        "suffix_ids": fin["suffix_ids"], "suffix_text_raw": fin["suffix_text_raw"],
        "n_output_tokens": fin["n_new"], "finish_reason": fin["finish_reason"], "ended_eos": fin["ended_eos"],
        "final_cap": fin["cap"], "attempts": [{k: v for k, v in a.items() if k != "suffix_ids"} for a in attempts],
        "runtime_s_total": sum(a["runtime_s"] for a in attempts),
        "peak_mem_alloc_gb_max": max(a["peak_mem_alloc_gb"] for a in attempts),
    }


def build_inputs_text(proc, prompt):
    """image 없는 text-only chat 구성 (official notebook messages 구조에서 image content만 뺀 형태)."""
    msgs = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
    return proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=True, return_dict=True,
                                    return_tensors="pt")


def run_request_text(torch, proc, model, eos_ids, item_id, pname, prompt, caps=CAPS):
    """image 필드가 없는 text-only 요청. generate.run_request의 image 경로와 record 필드를 최대한 맞춘다."""
    inp = build_inputs_text(proc, prompt)
    if "pixel_values" in inp:
        raise RunError("text-only chat template unexpectedly produced pixel_values")
    ids_in = inp["input_ids"][0].tolist()
    attempts = []
    for cap in caps:
        a = generate(torch, proc, model, inp, cap, eos_ids)
        if attempts:
            prev = attempts[-1]["suffix_ids"]
            a["prefix_matches_previous"] = a["suffix_ids"][:len(prev)] == prev
        attempts.append(a)
        if a["ended_eos"]:
            break
    fin = attempts[-1]
    for a in attempts:
        a["suffix_text_raw"] = proc.tokenizer.decode(a["suffix_ids"], skip_special_tokens=False)
    return {
        "id": item_id, "prompt_name": pname, "prompt_sha256": P.digest(prompt),
        "image": None, "image_file_sha256": None, "input_pixel_sha256": None,
        "pad_affine_top_left_side": None, "n_input_tokens": len(ids_in), "input_ids": ids_in,
        "input_ids_sha256": sha(json.dumps(ids_in).encode()),
        "suffix_ids": fin["suffix_ids"], "suffix_text_raw": fin["suffix_text_raw"],
        "n_output_tokens": fin["n_new"], "finish_reason": fin["finish_reason"], "ended_eos": fin["ended_eos"],
        "final_cap": fin["cap"], "attempts": [{k: v for k, v in a.items() if k != "suffix_ids"} for a in attempts],
        "runtime_s_total": sum(a["runtime_s"] for a in attempts),
        "peak_mem_alloc_gb_max": max(a["peak_mem_alloc_gb"] for a in attempts),
        "modality": "text",
    }


def run_request_modal(torch, proc, model, eos_ids, row, caps=CAPS):
    """row: image 조건이면 image/file_sha256를, text 조건이면 modality='text'만 요구한다."""
    if row["modality"] == "image":
        rec = run_request(torch, proc, model, eos_ids, {"id": row["id"], "image": row["image"],
                                                          "file_sha256": row["file_sha256"]},
                           row["condition"], row["prompt"], caps=caps)
        rec["modality"] = "image"
        return rec
    if row["modality"] == "text":
        return run_request_text(torch, proc, model, eos_ids, row["id"], row["condition"], row["prompt"], caps=caps)
    raise RunError(f"unknown modality {row['modality']!r}")


CFG_KEYS = ("model_id", "model_revision", "dtype", "transformers", "torch", "preprocess", "chat_template_sha256",
            "eos_token_id", "do_pan_and_scan", "image_size")


def config_digest(env, prompts_used):
    core = {k: env[k] for k in CFG_KEYS}
    core["prompts"] = {k: P.digest(v) for k, v in prompts_used.items()}
    core["caps"] = CAPS
    core["do_sample"] = False
    core["runner"] = RUNNER_VERSION
    return sha(json.dumps(core, sort_keys=True, default=str).encode()), core


def static_env():
    """모델 weight 없이 (processor + generation_config만으로) config digest에 쓰는 환경 값. env_info의 같은 키와 일치해야 한다."""
    os.environ.setdefault("HF_HOME", HF_HOME)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    import torch
    import transformers
    proc = transformers.AutoProcessor.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
    gc = transformers.GenerationConfig.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
    ip = proc.image_processor
    return {"model_id": MODEL_ID, "model_revision": MODEL_REVISION, "dtype": str(torch.bfloat16),
            "transformers": transformers.__version__, "torch": torch.__version__, "preprocess": PREPROC_VERSION,
            "chat_template_sha256": sha((proc.chat_template or "").encode()), "eos_token_id": gc.eos_token_id,
            "do_pan_and_scan": getattr(ip, "do_pan_and_scan", None), "image_size": str(getattr(ip, "size", None))}


def static_config():
    """protocol에 잠그는 (config core, digest). 세 prompt 전체 기준."""
    d, core = config_digest(static_env(), P.all_prompts())
    return core, d


def request_id(model_revision, adapter_digest, split, item_id, prompt_sha):
    return sha(f"{model_revision}|{adapter_digest or 'base'}|{split}|{item_id}|{prompt_sha}".encode())[:32]


class RunError(RuntimeError):
    pass


def read_records(path):
    out = []
    if os.path.exists(path):
        with open(path) as f:
            for ln in f:
                if ln.strip():
                    out.append(json.loads(ln))
    return out


def validate_existing(files_records, items, pnames, prompts_used, cdig, adapter_digest, protocol_digest, image_pixel_sha,
                      accept_protocols=()):
    """기존 모든 worker 출력 record를 현재 입력·model/adapter·prompt·config·protocol과 대조한다 (완료 요청 포함).

    files_records: {파일명: [record...]}. items: 이번 manifest의 항목 list. image_pixel_sha(path)->현재 입력 pixel sha.
    누락은 허용(재개 대상)하나 중복·충돌·기대 집합 밖 record는 RunError. returns {(id, prompt): record}.
    accept_protocols: 검증된 부모 실행(migration manifest로 연결)의 protocol digest. 생성 config digest가 같을 때만 허용한다.
    """
    ok_protocols = {protocol_digest, *accept_protocols}
    by_item = {i["id"]: i for i in items}
    seen, done = {}, {}
    pdig = {p: P.digest(prompts_used[p]) for p in pnames}
    for fn, recs in files_records.items():
        for r in recs:
            key = (r.get("id"), r.get("prompt_name"))
            it = by_item.get(key[0])
            if it is None or key[1] not in pnames:
                raise RunError(f"unexpected record {key} in {fn}: not in current request set")
            rid = request_id(MODEL_REVISION, adapter_digest, it.get("split"), key[0], pdig[key[1]])
            if r.get("request_id") != rid:
                raise RunError(f"request_id mismatch for {key} in {fn} (model/adapter/split/prompt provenance differs)")
            if r["request_id"] in seen:
                raise RunError(f"duplicate request {key}: {seen[r['request_id']]} and {fn}")
            seen[r["request_id"]] = fn
            for f_, want in (("config_digest", cdig), ("adapter_digest", adapter_digest), ("prompt_sha256", pdig[key[1]])):
                if r.get(f_) != want:
                    raise RunError(f"{f_} mismatch for {key} in {fn}: {r.get(f_)} != {want}")
            if r.get("protocol_digest") not in ok_protocols:
                raise RunError(f"protocol_digest mismatch for {key} in {fn}: {r.get('protocol_digest')}")
            if r["input_pixel_sha256"] != image_pixel_sha(it["image"]):
                raise RunError(f"input image changed since completion for {key}; refusing to reuse stale record")
            if it.get("file_sha256") and r.get("image_file_sha256") != it["file_sha256"]:
                raise RunError(f"image file sha differs from manifest for {key}")
            done[key] = r
    return done


def load_adapter(torch, model, adapter_dir):
    """adapter_dir/adapter.pt (state, config) -> model에 LoRA 적용 후 로드. returns adapter digest."""
    from . import lora
    blob = torch.load(os.path.join(adapter_dir, "adapter.pt"), map_location="cpu", weights_only=True)
    cfg = blob["config"]
    lora.apply_lora(model, cfg["r"], cfg["alpha"], 0.0)
    lora.load_lora_state(model, blob["state"])
    model.eval()
    dg = lora.state_digest(blob["state"])
    if blob.get("digest") and blob["digest"] != dg:
        raise RunError("adapter digest mismatch (file corrupted)")
    return dg


def main():
    from . import lock_protocol, queue_lock
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--ids", default=None, help="json list of ids (기본: manifest 전체)")
    ap.add_argument("--prompts", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--worker", type=int, required=True)
    ap.add_argument("--protocol", required=True, help="잠긴 protocol json 경로 (필수). 불일치 시 실행하지 않는다")
    ap.add_argument("--adapter", default=None, help="LoRA adapter 디렉터리 (없으면 base)")
    ap.add_argument("--time-limit", type=float, default=None)
    ap.add_argument("--max-requests", type=int, default=None)
    ap.add_argument("--parent-dir", default=None, help="검증 후 재사용할 부모 gen_worker*.jsonl 디렉터리 (읽기 전용; 새 요청은 out-dir에만 쓴다)")
    ap.add_argument("--parent-protocol", default=None, help="부모 실행의 protocol 파일 (config digest가 현재와 같아야 함)")
    a = ap.parse_args()
    if bool(a.parent_dir) != bool(a.parent_protocol):
        sys.exit("--parent-dir and --parent-protocol must be given together")
    pdig_protocol = lock_protocol.verify(a.protocol)
    items = [json.loads(ln) for ln in open(a.manifest) if ln.strip()]
    if a.ids:
        keep = set(json.load(open(a.ids)))
        missing = keep - {i["id"] for i in items}
        if missing:
            sys.exit(f"ids not in manifest: {sorted(missing)[:3]}")
        items = [i for i in items if i["id"] in keep]
    if len({i["id"] for i in items}) != len(items):
        sys.exit("duplicate ids in manifest")
    items = sorted(items, key=lambda i: i["id"])
    allp = P.all_prompts()
    pnames = a.prompts.split(",")
    prompts_used = {p: allp[p] for p in pnames}
    os.makedirs(a.out_dir, exist_ok=True)
    info = queue_lock.my_info(worker=a.worker)
    wl = os.path.join(a.out_dir, f"worker{a.worker}.lock")
    lk, own, _ = queue_lock.try_lock(wl, info)
    if lk is None:
        sys.exit(f"worker {a.worker} already running: {own}")
    try:
        run_worker(a, items, pnames, prompts_used, pdig_protocol, info)
    finally:
        lk.release()


def run_worker(a, items, pnames, prompts_used, pdig_protocol, info):
    from . import lock_protocol, queue_lock  # iter_013: 부모 재사용 분기의 lock_protocol NameError 수정
    torch, proc, model = load_model()
    adapter_digest = load_adapter(torch, model, a.adapter) if a.adapter else None
    env = env_info(torch, proc, model)
    cdig, core = config_digest(env, prompts_used)
    full_cdig = json.load(open(a.protocol))["locked"]["generation_config_digest"]
    cdig_all, _ = config_digest(env, P.all_prompts())
    if cdig_all != full_cdig:
        sys.exit("runtime generation config digest != protocol digest")
    eos = env["eos_token_id"]
    eos_ids = set(eos if isinstance(eos, list) else [eos])
    env_path = os.path.join(a.out_dir, f"gen_worker{a.worker}.jsonl.env.json")
    if not os.path.exists(env_path):
        json.dump({"env": env, "config": core, "config_digest": cdig, "adapter_digest": adapter_digest,
                   "protocol_digest": pdig_protocol, "worker": a.worker}, open(env_path, "w"), indent=1, default=str)
    import glob
    parent_files, accept = [], ()
    if a.parent_dir:
        pdg_parent = lock_protocol.digest_of(a.parent_protocol)
        if lock_protocol.locked_config_digest(a.parent_protocol) != full_cdig:
            sys.exit("parent protocol generation config digest differs from current protocol")
        parent_files = sorted(glob.glob(os.path.join(a.parent_dir, "gen_worker*.jsonl")))
        accept = (pdg_parent,)

    def read_all():
        return {f: read_records(f) for f in parent_files + sorted(glob.glob(os.path.join(a.out_dir, "gen_worker*.jsonl")))}
    files = read_all()
    cache = {}

    def px(path):
        if path not in cache:
            cache[path] = load_image(path)[2]
        return cache[path]

    done = validate_existing(files, items, pnames, prompts_used, cdig, adapter_digest, pdig_protocol, px, accept)
    out = os.path.join(a.out_dir, f"gen_worker{a.worker}.jsonl")
    claim_dir = os.path.join(a.out_dir, "claims")
    os.makedirs(claim_dir, exist_ok=True)
    log = open(out + ".log", "a")
    t_start, n_done = time.time(), 0
    pdig = {p: P.digest(prompts_used[p]) for p in pnames}
    stop = False
    for it in items:
        if stop:
            break
        if all((it["id"], pn) in done for pn in pnames):
            continue
        clk, prev, reclaimed = queue_lock.try_lock(os.path.join(claim_dir, it["id"] + ".claim"), info)
        if clk is None:
            continue
        try:
            if reclaimed:
                log.write(json.dumps({"event": "claim_reclaimed_from_dead_owner", "id": it["id"], "prev_owner": prev}) + "\n")
            # 다른 worker가 방금 끝냈을 수 있다: claim 뒤 재검증 (완료 요청 포함)
            done = validate_existing(read_all(), items, pnames, prompts_used, cdig, adapter_digest, pdig_protocol, px, accept)
            for pn in pnames:
                if (it["id"], pn) in done:
                    continue
                if (a.time_limit and time.time() - t_start > a.time_limit) or (a.max_requests is not None and n_done >= a.max_requests):
                    log.write(json.dumps({"event": "stop", "done_this_run": n_done}) + "\n")
                    stop = True
                    break
                try:
                    rec = run_request(torch, proc, model, eos_ids, it, pn, prompts_used[pn])
                except torch.cuda.OutOfMemoryError as e:
                    log.write(json.dumps({"event": "oom", "id": it["id"], "prompt": pn, "err": str(e)[:200]}) + "\n")
                    log.flush()
                    raise
                rec.update({"request_id": request_id(MODEL_REVISION, adapter_digest, it.get("split"), it["id"], pdig[pn]),
                            "split": it.get("split"), "adapter_digest": adapter_digest, "protocol_digest": pdig_protocol,
                            "config_digest": cdig, "worker": a.worker, "ts": time.time(), "gpu_uuid": env.get("gpu_uuid")})
                with open(out, "a") as f:
                    f.write(json.dumps(rec) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                done[(it["id"], pn)] = rec
                n_done += 1
                log.write(json.dumps({"event": "done", "id": it["id"], "prompt": pn, "n_out": rec["n_output_tokens"],
                                      "finish": rec["finish_reason"], "runtime_s": round(rec["runtime_s_total"], 1),
                                      "peak_gb": round(rec["peak_mem_alloc_gb_max"], 2),
                                      "elapsed": round(time.time() - t_start, 1)}) + "\n")
                log.flush()
        finally:
            clk.release()
    print(f"worker {a.worker}: finished; {n_done} new requests this run", flush=True)


if __name__ == "__main__":
    main()


