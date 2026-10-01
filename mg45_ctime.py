"""iter_045 C(MedGemma+LoRA seed17 epoch03) timing worker/launcher. 기본(medgemma) python 실행.

환자 단위 작업: worker가 환자 claim(flock)을 얻은 시점이 dispatch이고, 그 환자의 두 문장 요청을 순차 생성·후처리(JSON parse + canvas->원본 좌표 변환)한 뒤의
시각이 done이다. 요청 입력은 기존 C V96 요청(results/iter_040/requests/requests_V96.jsonl, prompt/cap/adapter 불변)이며 greedy 출력은
기존 192개 token과 대조한다 (불일치는 조사 대상; 기존 정확도 출력은 대체하지 않는다).
timing worker는 pg43_run과 달리 claim마다 전체 record를 재검증하지 않는다(검증은 block 종료 후 launcher가 수행): 비용 측정에 장부 검증 시간을 넣지 않기 위함.

사용:
  python mg45_ctime.py launch --out-dir DIR --workers 4 --gpus 0,1 [--barrier] [--warmup-n 8] [--peak-gb 9] [--set V96|D24]
  (worker는 launcher가 호출: python mg45_ctime.py worker ...)
"""
import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys
import time

REQ = {"V96": "results/iter_040/requests/requests_V96.jsonl"}
PROTO = "results/iter_040/protocol/protocol_C.json"
MAN = "results/iter_043/data/manifest_private.json"


def sha_b(b):
    return hashlib.sha256(b).hexdigest()


def file_sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def try_flock(path):
    import fcntl
    fd = os.open(path, os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return fd


def load_rows(setname):
    rows = [json.loads(l) for l in open(REQ[setname]) if l.strip()]
    by_p = {}
    for r in rows:
        by_p.setdefault(r["patient"], []).append(r)
    return rows, by_p


def worker(a):
    from rsna_diag import generate as G
    import pg39_spec as S39
    import pg43_eval as E
    from rsna_diag import parse
    t_proc = time.time()
    proto = json.load(open(PROTO))
    rows, by_p = load_rows(a.set)
    torch, proc, model = G.load_model()
    adig = G.load_adapter(torch, model, proto["adapter"]["path"])
    if adig != proto["adapter"]["digest"]:
        sys.exit("adapter digest != protocol")
    env = G.env_info(torch, proc, model)
    for k, v in proto["generation_config"].items():
        if k in env and k not in ("runner", "image_size") and env[k] != v:
            sys.exit(f"runtime env {k}={env[k]!r} != protocol {v!r}")  # 생성 설정 불일치는 fatal (chat template/model revision/dtype 등)
    eos = env["eos_token_id"]
    eos_ids = set(eos if isinstance(eos, list) else [eos])
    t_ready = time.time()
    man = json.load(open(MAN))
    ents = {e["PatientID"]: e for e in man["V96"] + man["D24"]}  # warm-up(D8)와 본 작업(V96) 환자 모두 포함

    def do_request(row, record_dir=None):
        image, aff, pxs = G.load_image(row["image"])
        inp = G.build_inputs(proc, image, row["prompt"])
        ids_in = inp["input_ids"][0].tolist()
        attempts = []
        for cap in row["caps"]:
            at = G.generate(torch, proc, model, inp, cap, eos_ids)
            attempts.append(at)
            if at["ended_eos"]:
                break
        fin = attempts[-1]
        txt = proc.tokenizer.decode(fin["suffix_ids"], skip_special_tokens=False)
        # 후처리: 공통 parser로 box 추출 후 canvas->원본 정규화 xyxy (평가와 같은 함수)
        t = row["targets"][0]
        pr = S39.parse_ids(txt, fin["ended_eos"], {t})
        boxes = [E.canvas_to_norm_xyxy(b, aff, ents[row["patient"]]["h"], ents[row["patient"]]["w"]) for b in pr["groups"][t]] if pr["status"] in parse.VALID else []
        return {"suffix_ids": fin["suffix_ids"], "suffix_text_raw": txt, "ended_eos": fin["ended_eos"], "n_output_tokens": fin["n_new"],
                "final_cap": fin["cap"], "status": pr["status"], "boxes_orig_xyxy": boxes, "input_pixel_sha256": pxs,
                "n_input_tokens": len(ids_in), "input_ids_sha256": sha_b(json.dumps(ids_in).encode()),
                "attempts": [{k: v for k, v in at.items() if k != "suffix_ids"} for at in attempts],
                "peak_mem_alloc_gb_max": max(at["peak_mem_alloc_gb"] for at in attempts),
                "peak_mem_reserved_gb_max": max(at["peak_mem_reserved_gb"] for at in attempts)}

    if a.warmup_n:
        d8 = sorted(man["D8"])[: max(1, a.warmup_n // 2)]
        d24 = {e["PatientID"]: e for e in man["D24"]}
        for p in d8:
            for t in ("qA", "qB"):
                row = {"patient": p, "image": d24[p]["image"], "prompt": S39.prompt_I_short(d24[p]["sentences"][t], t),
                       "caps": [1000, 2000, 4000], "targets": [t]}
                do_request(row)
        torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    t_warm = time.time()
    if a.barrier:
        open(os.path.join(a.barrier, f"ready.{a.worker}"), "w").write(json.dumps({"t": time.time(), "pid": os.getpid()}))
        gof = os.path.join(a.barrier, "go")
        while not os.path.exists(gof):
            time.sleep(0.005)
        t_go = json.load(open(gof))["t"]
    else:
        t_go = None
    out = os.path.join(a.out_dir, f"ctime_worker{a.worker}.jsonl")
    cdir = os.path.join(a.out_dir, "claims")
    os.makedirs(cdir, exist_ok=True)
    n_new = 0
    with open(out, "a") as f:
        for p in sorted(by_p):
            try:  # 영구 claim (O_EXCL): flock은 claim 보유 worker가 종료하면 풀려 꼬리 구간에서 같은 환자를 다른 worker가 다시 처리하는 중복이 실제 발생했다 (block1_a1_C)
                fd = os.open(os.path.join(cdir, p + ".claim"), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, json.dumps({"worker": a.worker, "t": time.time()}).encode())
                os.close(fd)
            except FileExistsError:
                continue
            t_disp = time.time()
            res = {}
            for row in sorted(by_p[p], key=lambda r: r["targets"][0]):
                t_req = time.time()
                r = do_request(row)
                r.update({"request_id": row["request_id"], "patient": p, "target": row["targets"][0], "t_req_start": t_req, "t_req_done": time.time()})
                res[row["targets"][0]] = r
            t_done = time.time()
            for t, r in res.items():
                r.update({"t_patient_dispatch": t_disp, "t_patient_done": t_done, "worker": a.worker, "gpu_uuid": env.get("gpu_uuid"),
                          "cuda_visible": os.environ.get("CUDA_VISIBLE_DEVICES")})
                f.write(json.dumps(r) + "\n")
                n_new += 1
            f.flush()
            os.fsync(f.fileno())
    t_end = time.time()
    if a.barrier:
        open(os.path.join(a.barrier, f"done.{a.worker}"), "w").write(json.dumps({"t": t_end, "n_new": n_new}))
    json.dump({"worker": a.worker, "t_proc_start": t_proc, "t_model_ready": t_ready, "t_warm_done": t_warm, "t_go": t_go, "t_end": t_end, "load_s": t_ready - t_proc,
               "n_new": n_new, "peak_alloc_gb": torch.cuda.max_memory_allocated() / 2**30, "peak_reserved_gb": torch.cuda.max_memory_reserved() / 2**30,
               "cuda_visible": os.environ.get("CUDA_VISIBLE_DEVICES"), "adapter_digest": adig},
              open(os.path.join(a.out_dir, f"worker{a.worker}.meta.{int(t_proc)}.json"), "x"), indent=1)
    print(f"worker {a.worker}: {n_new} requests", flush=True)


def gpu_free_mib():
    r = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,memory.total", "--format=csv,noheader,nounits"], capture_output=True, text=True, check=True)
    return {int(l.split(",")[0]): (int(l.split(",")[2]) - int(l.split(",")[1])) for l in r.stdout.strip().splitlines()}


def union(ivs):
    tot, cs, ce = 0.0, None, None
    for s_, e_ in sorted(ivs):
        if ce is None or s_ > ce:
            if ce is not None:
                tot += ce - cs
            cs, ce = s_, e_
        else:
            ce = max(ce, e_)
    return tot + ((ce - cs) if ce is not None else 0.0)


def launch(a):
    os.makedirs(a.out_dir, exist_ok=True)
    if os.path.exists(os.path.join(a.out_dir, "completion.json")):
        sys.exit("completion exists")
    allowed = [int(x) for x in os.environ["CUDA_VISIBLE_DEVICES"].split(",")] if os.environ.get("CUDA_VISIBLE_DEVICES") else None
    if allowed is None:
        sys.exit("CUDA_VISIBLE_DEVICES not set")
    gpus = [int(x) for x in a.gpus.split(",")] if a.gpus else allowed
    if not set(gpus) <= set(allowed):
        sys.exit("--gpus not within allowed")
    free = gpu_free_mib()
    gpus = sorted(gpus, key=lambda g: (-free[g], g))
    mapping = {k: gpus[k % len(gpus)] for k in range(a.workers)}
    per = {}
    for k, g in mapping.items():
        per.setdefault(g, []).append(k)
    for g, ws in per.items():
        need = len(ws) * (a.peak_gb + 2.0) * 1024
        if free[g] < need:
            sys.exit(f"gpu {g}: free {free[g]}MiB < need {need:.0f}MiB for workers {ws}")
    bdir = os.path.join(a.out_dir, "barrier") if a.barrier else None
    if bdir:
        os.makedirs(bdir, exist_ok=True)
    json.dump({"mapping": mapping, "free_mib_before": free, "args": vars(a), "code_sha256": file_sha("mg45_ctime.py"),
               "protocol_sha256": file_sha(PROTO), "requests_sha256": file_sha(REQ[a.set])}, open(os.path.join(a.out_dir, "launch_protocol.json"), "x"), indent=1)
    t0 = time.time()
    procs = {}
    for k in range(a.workers):
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(mapping[k]))
        cmd = [sys.executable, "mg45_ctime.py", "worker", "--set", a.set, "--out-dir", a.out_dir, "--worker", str(k), "--warmup-n", str(a.warmup_n)]
        if bdir:
            cmd += ["--barrier", bdir]
        procs[k] = subprocess.Popen(cmd, env=env, stdout=open(os.path.join(a.out_dir, f"worker{k}.stdout"), "a"), stderr=open(os.path.join(a.out_dir, f"worker{k}.stderr"), "a"))
    rl = open(os.path.join(a.out_dir, "resource_log.jsonl"), "a")
    t_go, last = None, 0
    while any(p.poll() is None for p in procs.values()):
        if bdir and t_go is None:
            if all(os.path.exists(os.path.join(bdir, f"ready.{k}")) for k in range(a.workers)):
                t_go = time.time()
                tmpg = os.path.join(bdir, f"go.{os.getpid()}.tmp")
                json.dump({"t": t_go}, open(tmpg, "w"))
                os.replace(tmpg, os.path.join(bdir, "go"))
            elif any(p.poll() is not None for p in procs.values()):
                break
        time.sleep(0.02 if (bdir and t_go is None) else 0.5)
        if time.time() - last > 5:
            last = time.time()
            used = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,utilization.gpu", "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout.strip().splitlines()
            rl.write(json.dumps({"t": round(time.time() - t0, 1), "gpu": used}) + "\n")
            rl.flush()
    codes = [procs[k].wait() for k in range(a.workers)]
    wall = time.time() - t0
    recs = []
    for fn in sorted(glob.glob(os.path.join(a.out_dir, "ctime_worker*.jsonl"))):
        recs += [json.loads(l) for l in open(fn, "rb").read().split(b"\n")[:-1] if l.strip()]
    rows, by_p = load_rows(a.set)
    ids = [r["request_id"] for r in recs]
    want = {r["request_id"] for r in rows}
    complete = len(ids) == len(set(ids)) and set(ids) == want
    iv = {}
    for r in recs:
        iv.setdefault(mapping[r["worker"]], set()).add((r["t_patient_dispatch"], r["t_patient_done"]))
    res = {"exit_codes": codes, "launcher_wall_s_incl_loading": wall, "n_records": len(recs), "n_unique": len(set(ids)), "n_expected": len(want), "complete": complete,
           "workers": a.workers, "mapping": mapping, "t_go": t_go,
           "device_seconds_union": sum(union(v) for v in iv.values()) if iv else None,
           "peak_alloc_gb_max": None}
    metas = [json.load(open(p)) for p in glob.glob(os.path.join(a.out_dir, "worker*.meta.*.json"))]
    if metas:
        res["peak_alloc_gb_max"] = max(m["peak_alloc_gb"] for m in metas)
        res["peak_reserved_gb_max"] = max(m["peak_reserved_gb"] for m in metas)
        res["cold_load_s"] = {m["worker"]: m["load_s"] for m in metas}
    if bdir:
        dn = [json.load(open(p))["t"] for p in glob.glob(os.path.join(bdir, "done.*"))]
        res["workload_wall_s"] = (max(dn) - t_go) if (dn and t_go) else None
    if complete and all(c == 0 for c in codes):
        res["worker_file_sha256"] = {os.path.basename(f): file_sha(f) for f in sorted(glob.glob(os.path.join(a.out_dir, "ctime_worker*.jsonl")))}
        tmp = os.path.join(a.out_dir, f"completion.{os.getpid()}.tmp")
        json.dump(res, open(tmp, "w"), indent=1)
        os.replace(tmp, os.path.join(a.out_dir, "completion.json"))
        print("completion", json.dumps({k: res[k] for k in ("exit_codes", "n_unique", "launcher_wall_s_incl_loading", "workload_wall_s") if k in res}))
    else:
        json.dump(res, open(os.path.join(a.out_dir, f"partial_{int(time.time())}.json"), "w"), indent=1)
        print("NOT complete", json.dumps({k: res[k] for k in ("exit_codes", "n_unique", "n_expected")}))
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("worker")
    l = sub.add_parser("launch")
    for s in (w, l):
        s.add_argument("--out-dir", required=True)
        s.add_argument("--set", default="V96")
        s.add_argument("--warmup-n", type=int, default=8)
    w.add_argument("--worker", type=int, required=True)
    w.add_argument("--barrier", default=None)
    l.add_argument("--workers", type=int, required=True)
    l.add_argument("--gpus", default=None)
    l.add_argument("--barrier", action="store_true")
    l.add_argument("--peak-gb", type=float, default=9.0)
    a = ap.parse_args()
    {"worker": worker, "launch": launch}[a.cmd](a)


if __name__ == "__main__":
    main()
