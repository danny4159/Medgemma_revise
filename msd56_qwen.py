"""iter_056 조건부 모델 대조: Qwen3-VL-4B-Instruct (공식 model card Transformers 경로). MedGemma 요청 파일의 부분집합(DENSE/O8/TEXT에 쓰인 rid)을
동일 PNG·동일 PROMPT로 실행한다. 모델별 processor/visual token 차이는 record(n_image_tokens)에 그대로 기록한다. prompt/parser/cap은 MedGemma와 동일(수정 없음).
생성은 MedGemma와 같은 greedy (model card의 sampling 권장값과 다름: 대조 일관성을 위한 고정 선택).

  python msd56_qwen.py subset --split D|E            -> data/requests_qwen_{split}.jsonl
  python msd56_qwen.py lock --requests R --out P
  python msd56_qwen.py worker|launch|verify  (msd56_run과 같은 인자)
공유: msd56_run의 load_requests/validate_existing/FileLock/repair_tail/launch 인프라. GT를 읽지 않는다(subset 단계만 cond_map 사용).
"""
import argparse
import json
import os
import subprocess
import sys
import time

import msd56_run as R

MODEL_ID = "Qwen/Qwen3-VL-4B-Instruct"
MODEL_REVISION = "ebb281ec70b05090aa6165b016eac8ec08e71b17"
CACHE = "results/environments/qwen3vl_cache"
RUNNER = "msd56_qwen_v1"
CODE = ["msd56_qwen.py", "msd56_run.py", "msd56_data.py"]
DATA = R.DATA


def cmd_subset(a):
    cmap = json.load(open(f"{DATA}/cond_map_{a.split}.json"))
    keep = {c["rid"] for c in cmap if c["cond"] in ("DENSE", "O8", "TEXT")}
    rows = [json.loads(ln) for ln in open(f"{DATA}/requests_{a.split}.jsonl")]
    sub = [r for r in rows if r["rid"] in keep]
    with open(f"{DATA}/requests_qwen_{a.split}.jsonl", "w") as f:
        for r in sub:
            f.write(json.dumps(r) + "\n")
    print(a.split, "qwen unique requests", len(sub), "cond rows", sum(1 for c in cmap if c["cond"] in ("DENSE", "O8", "TEXT")))


def cmd_lock(a):
    rows = R.load_requests(a.requests)
    prot = {"runner": RUNNER, "model_id": MODEL_ID, "model_revision": MODEL_REVISION, "caps": R.CAPS,
            "prompt_sha256": R.sha(R.PROMPT.encode()), "requests_file": a.requests,
            "requests_sha256": R.sha(open(a.requests, "rb").read()), "n_requests": len(rows),
            "code": R.file_digests(CODE), "locked_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if os.path.exists(a.out):
        raise R.RunError(f"{a.out} exists")
    open(a.out, "w").write(json.dumps(prot, indent=1))


def verify_protocol(path, requests):
    p = json.load(open(path))
    for f, d in p["code"].items():
        if R.sha(open(f, "rb").read()) != d:
            raise R.RunError(f"code digest changed: {f}")
    if R.sha(open(requests, "rb").read()) != p["requests_sha256"] or p["requests_file"] != requests:
        raise R.RunError("requests digest mismatch")
    if p["model_revision"] != MODEL_REVISION or p["prompt_sha256"] != R.sha(R.PROMPT.encode()) or p["caps"] != R.CAPS:
        raise R.RunError("model/prompt/caps mismatch")
    return R.sha(open(path, "rb").read()), p


def load_model():
    os.environ["HF_HOME"] = os.path.abspath(CACHE + "_home")
    os.environ["HF_HUB_CACHE"] = os.path.abspath(CACHE)
    os.environ["HF_HUB_OFFLINE"] = "1"
    import torch
    import transformers
    torch.manual_seed(0)
    proc = transformers.AutoProcessor.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
    model = transformers.Qwen3VLForConditionalGeneration.from_pretrained(MODEL_ID, revision=MODEL_REVISION, dtype=torch.bfloat16,
                                                                         device_map="cuda")
    model.eval()
    return torch, proc, model


def build_inputs(proc, row):
    return R.build_inputs(proc, row)  # 동일 messages 구조: [image...] + text, 공식 apply_chat_template 경로


def run_request(torch, proc, model, eos_ids, row):
    inp = build_inputs(proc, row)
    ids_in = inp["input_ids"][0].tolist()
    img_id = model.config.image_token_id
    n_img_tok = sum(1 for t in ids_in if t == img_id)
    if row["modality"] == "text" and ("pixel_values" in inp or n_img_tok):
        raise R.RunError("text request has image inputs")
    if row["modality"] == "image":
        grid = inp["image_grid_thw"]
        if grid.shape[0] != len(row["images"]):
            raise R.RunError("image count mismatch")
        merge = proc.image_processor.merge_size
        want = int((grid.prod(dim=1) // (merge ** 2)).sum())
        if want != n_img_tok:
            raise R.RunError(f"image token mismatch {want} vs {n_img_tok}")
    attempts = []
    for cap in R.CAPS:
        x = {k: (v.to("cuda", dtype=torch.bfloat16) if k == "pixel_values" else v.to("cuda")) for k, v in inp.items()}
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
        t0 = time.time()
        with torch.no_grad():
            out = model.generate(**x, max_new_tokens=cap, do_sample=False, top_p=None, top_k=None, temperature=None)
        torch.cuda.synchronize()
        dt = time.time() - t0
        ids = out[0, x["input_ids"].shape[1]:].tolist()
        ended = len(ids) > 0 and ids[-1] in eos_ids
        attempts.append({"cap": cap, "suffix_ids": ids, "n_new": len(ids), "ended_eos": bool(ended), "runtime_s": dt, "t_start": t0,
                         "t_end": t0 + dt, "peak_mem_alloc_gb": torch.cuda.max_memory_allocated() / 2**30,
                         "peak_mem_reserved_gb": torch.cuda.max_memory_reserved() / 2**30})
        if ended:
            break
    fin = attempts[-1]
    for at in attempts:
        at["suffix_text_raw"] = proc.tokenizer.decode(at["suffix_ids"], skip_special_tokens=False)
    text = fin["suffix_text_raw"]
    clean = text.replace("<|im_end|>", "")
    return {"rid": row["rid"], "modality": row["modality"], "n_images": len(row["images"]), "n_input_tokens": len(ids_in),
            "n_image_tokens": n_img_tok, "input_ids_sha256": R.sha(json.dumps(ids_in).encode()),
            "pixel_values_shape": list(inp["pixel_values"].shape) if "pixel_values" in inp else None,
            "image_grid_thw": inp["image_grid_thw"].tolist() if "image_grid_thw" in inp else None,
            "input_pixel_sha256": R.image_pixel_sha(row["images"]) if row["images"] else None,
            "image_file_sha256": row["image_file_sha256"], "suffix_ids": fin["suffix_ids"], "suffix_text_raw": text,
            "answer": R.parse_answer(clean), "ended_eos": fin["ended_eos"], "final_cap": fin["cap"],
            "attempts": [{k: v for k, v in at.items() if k != "suffix_ids"} for at in attempts],
            "runtime_s_total": sum(at["runtime_s"] for at in attempts),
            "peak_mem_alloc_gb_max": max(at["peak_mem_alloc_gb"] for at in attempts),
            "peak_mem_reserved_gb_max": max(at["peak_mem_reserved_gb"] for at in attempts)}


def cmd_worker(a):
    rows = R.load_requests(a.requests)
    pdig, _ = verify_protocol(a.protocol, a.requests)
    os.makedirs(a.out_dir, exist_ok=True)
    wl = R.FileLock(os.path.join(a.out_dir, f"worker{a.worker}.lock"))
    if not wl.try_acquire():
        sys.exit(f"worker {a.worker} already running")
    out = os.path.join(a.out_dir, f"gen_worker{a.worker}.jsonl")
    R.repair_tail(out)
    t_l = time.time()
    torch, proc, model = load_model()
    t_load = time.time() - t_l
    eos = model.generation_config.eos_token_id
    eos_ids = set(eos if isinstance(eos, list) else [eos])
    import transformers
    env = {"model_id": MODEL_ID, "revision": MODEL_REVISION, "transformers": transformers.__version__, "torch": torch.__version__,
           "gpu_uuid": str(torch.cuda.get_device_properties(0).uuid), "eos": sorted(eos_ids),
           "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"), "runner": RUNNER,
           "image_processor": str(proc.image_processor.to_dict())[:600], "generation_config": model.generation_config.to_dict()}
    attempt_id = str(int(time.time()))
    with open(os.path.join(a.out_dir, f"worker{a.worker}.env.json"), "a") as f:
        f.write(json.dumps({"attempt": attempt_id, "env": env, "load_s": t_load, "pid": os.getpid()}, default=str) + "\n")
    R.validate_existing(a.out_dir, rows, pdig)
    cdir = os.path.join(a.out_dir, "claims")
    os.makedirs(cdir, exist_ok=True)
    log = open(out + ".log", "a")
    n_new, t0 = 0, time.time()
    for row in rows:
        if a.max_requests is not None and n_new >= a.max_requests:
            break
        cl = R.FileLock(os.path.join(cdir, row["rid"] + ".claim"))
        if not cl.try_acquire():
            continue
        try:
            if row["rid"] in R.validate_existing(a.out_dir, rows, pdig):
                continue
            rec = run_request(torch, proc, model, eos_ids, row)
            rec.update({"protocol_digest": pdig, "worker": a.worker, "attempt_id": attempt_id, "ts": time.time(), "gpu_uuid": env["gpu_uuid"]})
            with open(out, "a") as f:
                f.write(json.dumps(rec) + "\n")
                f.flush()
                os.fsync(f.fileno())
            n_new += 1
            log.write(json.dumps({"event": "done", "rid": row["rid"], "n_images": rec["n_images"], "n_img_tok": rec["n_image_tokens"],
                                  "ans": rec["answer"], "eos": rec["ended_eos"], "s": round(rec["runtime_s_total"], 2),
                                  "elapsed": round(time.time() - t0, 1)}) + "\n")
            log.flush()
        finally:
            cl.release()
    json.dump({"worker": a.worker, "attempt": attempt_id, "n_new": n_new, "load_s": t_load, "elapsed_s": time.time() - t0},
              open(os.path.join(a.out_dir, f"worker{a.worker}.attempt_{attempt_id}.done.json"), "w"))


def cmd_launch(a):
    rows = R.load_requests(a.requests)
    verify_protocol(a.protocol, a.requests)
    gpus = [int(x) for x in a.gpus.split(",")]
    allowed = {int(x) for x in os.environ.get("CUDA_VISIBLE_DEVICES", "0,1").split(",")}
    if not set(gpus) <= allowed:
        sys.exit("gpus not allowed")
    free = R.gpu_free_mib()
    need = {}
    for g in gpus:
        need[g] = need.get(g, 0) + (a.peak_gb + 2.0) * 1024
    for g, n in need.items():
        if n > free[g]:
            sys.exit(f"GPU {g}: need {n:.0f} MiB > free {free[g]} MiB")
    os.makedirs(a.out_dir, exist_ok=True)
    ll = R.FileLock(os.path.join(a.out_dir, "launch.lock"))
    if not ll.try_acquire():
        sys.exit("launcher already running")
    t0 = time.time()
    procs = []
    for k, g in enumerate(gpus):
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(g))
        cmd = [sys.executable, "msd56_qwen.py", "worker", "--requests", a.requests, "--protocol", a.protocol, "--out-dir", a.out_dir,
               "--worker", str(k + a.worker_offset)]
        if a.max_requests is not None:
            cmd += ["--max-requests", str(a.max_requests)]
        procs.append((k + a.worker_offset, g, subprocess.Popen(cmd, env=env, stdout=open(os.path.join(a.out_dir, f"worker{k + a.worker_offset}.stdout.log"), "a"),
                                                              stderr=subprocess.STDOUT)))
    peak, ns = {}, 0
    while any(p.poll() is None for _, _, p in procs):
        time.sleep(5)
        o = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used", "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout
        for l in o.strip().splitlines():
            i, u = l.split(",")
            peak[int(i)] = max(peak.get(int(i), 0), int(u))
        ns += 1
    rcs = {k: p.returncode for k, _, p in procs}
    comp = {"gpus": gpus, "worker_exit_codes": rcs, "wall_s": time.time() - t0, "peak_gpu_used_mib_sampled": peak, "n_samples": ns,
            "peak_gb_assumed": a.peak_gb}
    json.dump(comp, open(os.path.join(a.out_dir, f"launch_{int(t0)}.json"), "w"), indent=1)
    ll.release()
    print(comp)
    if any(rc != 0 for rc in rcs.values()):
        sys.exit(1)


def cmd_verify(a):
    rows = R.load_requests(a.requests)
    pdig, _ = verify_protocol(a.protocol, a.requests)
    seen = R.validate_existing(a.out_dir, rows, pdig)
    ok = len(seen) == len(rows)
    print(json.dumps({"n_requests": len(rows), "n_records": len(seen), "ok": ok}))
    if not ok:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("subset")
    s.add_argument("--split", required=True)
    s = sp.add_parser("lock")
    s.add_argument("--requests", required=True)
    s.add_argument("--out", required=True)
    for n in ("worker", "launch", "verify"):
        s = sp.add_parser(n)
        s.add_argument("--requests", required=True)
        s.add_argument("--protocol", required=True)
        s.add_argument("--out-dir", required=True)
        if n == "worker":
            s.add_argument("--worker", type=int, required=True)
            s.add_argument("--max-requests", type=int, default=None)
        if n == "launch":
            s.add_argument("--gpus", required=True)
            s.add_argument("--peak-gb", type=float, default=14.0)
            s.add_argument("--worker-offset", type=int, default=0)
            s.add_argument("--max-requests", type=int, default=None)
    a = ap.parse_args()
    {"subset": cmd_subset, "lock": cmd_lock, "worker": cmd_worker, "launch": cmd_launch, "verify": cmd_verify}[a.cmd](a)


if __name__ == "__main__":
    main()
