"""MedGemma 1.5 실제 생성 runner (iter_009). batch=1, bf16, greedy, 요청 단위 append/재개.

- GT는 읽지 않는다 (infer manifest의 id/image만 사용).
- cap 래더: 1000 -> (EOS 없이 상한 도달 시) 2000 -> 4000. 각 시도를 record.attempts에 보존한다.
- 재개: 같은 (id, prompt)의 기존 record가 있으면 config_digest를 대조해, 다르면 중단한다 (덮어쓰지 않음).
사용: CUDA_VISIBLE_DEVICES=<물리 gpu> python -m rsna_diag.generate --manifest ... --prompts ... --ids ... --out ... [--shard k/n] [--time-limit S]
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
RUNNER_VERSION = "iter009_gen_v1"


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


def config_digest(env, prompts_used):
    core = {k: env[k] for k in ("model_id", "model_revision", "dtype", "transformers", "torch", "preprocess",
                                "chat_template_sha256", "eos_token_id", "do_pan_and_scan", "image_size")}
    core["prompts"] = {k: P.digest(v) for k, v in prompts_used.items()}
    core["caps"] = CAPS
    core["do_sample"] = False
    core["runner"] = RUNNER_VERSION
    return sha(json.dumps(core, sort_keys=True, default=str).encode()), core


def read_done(path):
    done = {}
    if os.path.exists(path):
        for ln in open(path):
            if ln.strip():
                r = json.loads(ln)
                done[(r["id"], r["prompt_name"])] = r
    return done


def stale_records(done, cdig):
    return [k for k, r in done.items() if r.get("config_digest") != cdig]


def main():
    ap =argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--ids", default=None, help="json list of ids (기본: manifest 전체)")
    ap.add_argument("--prompts", default="official_long,concise,legacy_detect")
    ap.add_argument("--out", required=True)
    ap.add_argument("--shard", default="0/1")
    ap.add_argument("--time-limit", type=float, default=None, help="초. 요청 사이에 확인하여 안전하게 종료")
    ap.add_argument("--max-requests", type=int, default=None)
    ap.add_argument("--claim-dir", default=None, help="작업 큐 모드: 환자 단위 원자적 claim 파일로 worker 간 부하 균등화 (출력 규약 불변)")
    ap.add_argument("--carry", default=None, help="이미 완료된 record glob (config_digest·입력 sha 일치 시에만 재사용, 새 파일에 복사하지 않음)")
    a = ap.parse_args()
    k, n = map(int, a.shard.split("/"))
    items = [json.loads(ln) for ln in open(a.manifest) if ln.strip()]
    if a.ids:
        keep = set(json.load(open(a.ids)))
        items = [i for i in items if i["id"] in keep]
    items = sorted(items, key=lambda i: i["id"])
    if not a.claim_dir:
        items = items[k::n]
    allp = P.all_prompts()
    pnames = a.prompts.split(",")
    prompts_used = {p: allp[p] for p in pnames}
    torch, proc, model = load_model()
    env = env_info(torch, proc, model)
    cdig, core = config_digest(env, prompts_used)
    eos = env["eos_token_id"]
    eos_ids = set(eos if isinstance(eos, list) else [eos])
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    env_path = a.out + ".env.json"
    if not os.path.exists(env_path):
        json.dump({"env": env, "config": core, "config_digest": cdig, "shard": a.shard}, open(env_path, "w"),
                  indent=1, default=str)
    done = read_done(a.out)
    if a.carry or a.claim_dir:
        import glob
        pats = [a.carry] if a.carry else []
        if a.claim_dir:  # 이전 실행에서 다른 worker가 끝낸 요청도 완료로 인정 (config/입력 sha 검증은 아래에서 동일하게 수행)
            pats.append(os.path.join(os.path.dirname(a.out), "gen_shard*.jsonl"))
        for cf in sorted(f for pt in pats for f in glob.glob(pt)):
            if os.path.abspath(cf) == os.path.abspath(a.out):
                continue
            if cf.endswith((".env.json", ".log")):
                continue
            for k2, r2 in read_done(cf).items():
                done.setdefault(k2, r2)
    bad = stale_records(done, cdig)
    if bad:
        sys.exit(f"stale/mismatched records {bad[:3]}: config_digest differs; refusing to resume/overwrite")
    log = open(a.out + ".log", "a")
    t_start, n_done, todo = time.time(), 0, 0
    for it in items:
        if a.claim_dir and not all((it["id"], pn) in done for pn in pnames):
            os.makedirs(a.claim_dir, exist_ok=True)
            try:
                os.close(os.open(os.path.join(a.claim_dir, it["id"] + ".claim"), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            except FileExistsError:
                continue
        elif a.claim_dir:
            continue
        for pn in pnames:
            todo += 1
            if (it["id"], pn) in done:
                if done[(it["id"], pn)]["input_pixel_sha256"] != load_image(it["image"])[2]:
                    sys.exit(f"input image changed since completion for {it['id']}; refusing to reuse stale record")
                continue
            if a.time_limit and time.time() - t_start > a.time_limit:
                log.write(json.dumps({"event": "time_limit_stop", "done_this_run": n_done}) + "\n")
                print(f"time limit reached after {n_done} requests", flush=True)
                return
            if a.max_requests is not None and n_done >= a.max_requests:
                return
            try:
                rec = run_request(torch, proc, model, eos_ids, it, pn, prompts_used[pn])
            except torch.cuda.OutOfMemoryError as e:
                log.write(json.dumps({"event": "oom", "id": it["id"], "prompt": pn, "err": str(e)[:200]}) + "\n")
                log.flush()
                torch.cuda.empty_cache()
                raise
            rec["config_digest"] = cdig
            rec["shard"] = a.shard
            rec["ts"] = time.time()
            with open(a.out, "a") as f:
                f.write(json.dumps(rec) + "\n")
            n_done += 1
            log.write(json.dumps({"event": "done", "id": it["id"], "prompt": pn, "n_out": rec["n_output_tokens"],
                                  "finish": rec["finish_reason"], "runtime_s": round(rec["runtime_s_total"], 1),
                                  "peak_gb": round(rec["peak_mem_alloc_gb_max"], 2),
                                  "elapsed": round(time.time() - t_start, 1)}) + "\n")
            log.flush()
    print(f"shard {a.shard}: finished; {n_done} new requests this run of {todo} total", flush=True)


if __name__ == "__main__":
    main()
