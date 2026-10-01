"""iter_048 E/J paired timing worker/launcher (mg45_ctime 기반; mg45_ctime.py는 보존). 기본(medgemma) python 실행.

환자 단위 작업: worker가 환자 claim(O_EXCL 영구 claim)을 얻은 시점이 dispatch, 그 환자의 요청(E: I-short qA,qB 순차 2개 / J: J-short 1개)을 생성하고
JSON parse + canvas->원본 정규화 좌표 변환 + 환자 결과 결합을 마친 시각이 done이다. 요청은 results/iter_048/requests/requests_{SET}.jsonl (adapter는 launch 인자).
보완(iter_045 mg45_ctime 대비): (1) out-dir이 비어 있지 않거나 launch_protocol.json이 있으면 거부 (재개 금지: 기술 실패 block은 새 attempt dir에서 전체 재측정),
(2) 시작 시 launcher가 out-dir 배타 flock을 잡는다, (3) worker 하나라도 barrier 전에 죽으면 launcher가 자기 child만 종료하고 실패로 끝낸다 (barrier 대기 hang 방지),
(4) 워커가 adapter digest/file sha를 launch_protocol과 대조한다, (5) record에 request별 suffix_ids·input hash를 남겨 고정 정확도 출력과 대조한다.

사용: python pg48_ctime.py launch --system E|J --order AB|BA --adapter DIR --out-dir DIR --workers 4 --gpus 0,1 --barrier --warmup-n 8 --set V96|D24 [--peak-gb 10]
"""
import argparse
import fcntl
import glob
import hashlib
import json
import os
import signal
import subprocess
import sys
import time

REQ = {"V96": "results/iter_048/requests/requests_V96.jsonl", "D24": "results/iter_048/requests/requests_D24.jsonl"}
MAN = "results/iter_043/data/manifest_private.json"
CODE = ["pg48_ctime.py", "pg43_run.py", "pg43_eval.py", "pg39_spec.py", "rsna_diag/generate.py", "rsna_diag/lora.py", "rsna_diag/parse.py", "rsna_diag/geometry.py"]


def sha_b(b):
    return hashlib.sha256(b).hexdigest()


def file_sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def want_cond(system, order):
    return "I-short" if system == "E" else ("J-short" if order == "AB" else "J-short-rev")


def load_rows(setname, system, order):
    cond = want_cond(system, order)
    rows = [r for r in (json.loads(l) for l in open(REQ[setname]) if l.strip()) if r["cond"] == cond]
    by_p = {}
    for r in rows:
        by_p.setdefault(r["patient"], []).append(r)
    return rows, by_p


def worker(a):
    from rsna_diag import generate as G
    import pg39_spec as S39
    import pg43_eval as EV
    from rsna_diag import parse
    t_proc = time.time()
    lp = json.load(open(os.path.join(a.out_dir, "launch_protocol.json")))
    rows, by_p = load_rows(a.set, a.system, a.order)
    torch, proc, model = G.load_model()
    adig = G.load_adapter(torch, model, a.adapter)
    if adig != lp["adapter_digest"] or file_sha(os.path.join(a.adapter, "adapter.pt")) != lp["adapter_file_sha256"]:
        sys.exit("adapter digest/file sha != launch protocol")
    env = G.env_info(torch, proc, model)
    if env["model_revision"] != lp["model_revision"] or env["chat_template_sha256"] != lp["chat_template_sha256"]:
        sys.exit("runtime model revision/chat template != launch protocol")
    eos = env["eos_token_id"]
    eos_ids = set(eos if isinstance(eos, list) else [eos])
    t_ready = time.time()
    man = json.load(open(MAN))
    ents = {e["PatientID"]: e for e in man["V96"] + man["D24"]}

    def do_request(row):
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
        tg = row["targets"]
        pr = S39.parse_ids(txt, fin["ended_eos"], set(tg))
        e = ents[row["patient"]]
        boxes = {t: ([EV.canvas_to_norm_xyxy(b, aff, e["h"], e["w"]) for b in pr["groups"][t]] if pr["status"] in parse.VALID else []) for t in tg}
        return {"suffix_ids": fin["suffix_ids"], "suffix_text_raw": txt, "ended_eos": fin["ended_eos"], "n_output_tokens": fin["n_new"], "final_cap": fin["cap"],
                "status": pr["status"], "boxes_orig_xyxy": boxes, "input_pixel_sha256": pxs, "n_input_tokens": len(ids_in), "input_ids_sha256": sha_b(json.dumps(ids_in).encode()),
                "attempts": [{k: v for k, v in at.items() if k != "suffix_ids"} for at in attempts],
                "peak_mem_alloc_gb_max": max(at["peak_mem_alloc_gb"] for at in attempts), "peak_mem_reserved_gb_max": max(at["peak_mem_reserved_gb"] for at in attempts)}

    if a.warmup_n:
        d24 = {e["PatientID"]: e for e in man["D24"]}
        d8 = sorted(man["D8"])[: max(1, a.warmup_n // 2)]
        import pg39_spec as S
        for p in d8:
            e = d24[p]
            if a.system == "E":
                reqs = [{"patient": p, "image": e["image"], "prompt": S.prompt_I_short(e["sentences"][t], t), "caps": S.CAPS_IC, "targets": [t]} for t in ("qA", "qB")]
            else:
                order = [("qA", e["sentences"]["qA"]), ("qB", e["sentences"]["qB"])]
                if a.order == "BA":
                    order = order[::-1]
                reqs = [{"patient": p, "image": e["image"], "prompt": S.prompt_J_short(order), "caps": S.CAPS_J, "targets": ["qA", "qB"]}]
            for r in reqs:
                do_request(r)
        torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    t_warm = time.time()
    open(os.path.join(a.barrier, f"ready.{a.worker}"), "w").write(json.dumps({"t": time.time(), "pid": os.getpid()}))
    gof = os.path.join(a.barrier, "go")
    while not os.path.exists(gof):
        time.sleep(0.005)
    t_go = json.load(open(gof))["t"]
    out = os.path.join(a.out_dir, f"ctime_worker{a.worker}.jsonl")
    cdir = os.path.join(a.out_dir, "claims")
    os.makedirs(cdir, exist_ok=True)
    n_new = 0
    with open(out, "a") as f:
        for p in sorted(by_p):
            try:
                fd = os.open(os.path.join(cdir, p + ".claim"), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, json.dumps({"worker": a.worker, "t": time.time()}).encode())
                os.close(fd)
            except FileExistsError:
                continue
            t_disp = time.time()
            res = []
            for row in sorted(by_p[p], key=lambda r: r["targets"][0]):
                t_req = time.time()
                r = do_request(row)
                r.update({"request_id": row["request_id"], "patient": p, "targets": row["targets"], "cond": row["cond"], "t_req_start": t_req, "t_req_done": time.time()})
                res.append(r)
            # 환자 결과 결합 (두 문장 box 집합)
            combined = {}
            for r in res:
                combined.update(r["boxes_orig_xyxy"])
            t_done = time.time()
            for r in res:
                r.update({"t_patient_dispatch": t_disp, "t_patient_done": t_done, "worker": a.worker, "gpu_uuid": env.get("gpu_uuid"), "patient_combined_n_boxes": {t: len(b) for t, b in combined.items()},
                          "cuda_visible": os.environ.get("CUDA_VISIBLE_DEVICES"), "adapter_digest": adig})
                f.write(json.dumps(r) + "\n")
                n_new += 1
            f.flush()
            os.fsync(f.fileno())
    t_end = time.time()
    open(os.path.join(a.barrier, f"done.{a.worker}"), "w").write(json.dumps({"t": t_end, "n_new": n_new}))
    json.dump({"worker": a.worker, "t_proc_start": t_proc, "t_model_ready": t_ready, "t_warm_done": t_warm, "t_go": t_go, "t_end": t_end, "load_s": t_ready - t_proc, "n_new": n_new,
               "peak_alloc_gb": torch.cuda.max_memory_allocated() / 2**30, "peak_reserved_gb": torch.cuda.max_memory_reserved() / 2**30,
               "cuda_visible": os.environ.get("CUDA_VISIBLE_DEVICES"), "adapter_digest": adig}, open(os.path.join(a.out_dir, f"worker{a.worker}.meta.{int(t_proc)}.json"), "x"), indent=1)
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
    lock_fd = os.open(os.path.join(a.out_dir, "launch.lock"), os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit("another launcher owns this out-dir")
    stray = [f for f in os.listdir(a.out_dir) if f not in ("launch.lock",)]
    if stray:
        sys.exit(f"out-dir not empty (resume is not supported for timing blocks; use a new attempt dir): {stray[:5]}")
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
    import torch
    blob = torch.load(os.path.join(a.adapter, "adapter.pt"), map_location="cpu", weights_only=True)
    from rsna_diag import generate as G, lora
    if lora.state_digest(blob["state"]) != blob["digest"]:
        sys.exit("adapter digest mismatch (corrupt)")
    st = G.static_env()
    bdir = os.path.join(a.out_dir, "barrier")
    os.makedirs(bdir)
    rows, by_p = load_rows(a.set, a.system, a.order)
    lp = {"system": a.system, "order": a.order, "set": a.set, "adapter": a.adapter, "adapter_digest": blob["digest"], "adapter_file_sha256": file_sha(os.path.join(a.adapter, "adapter.pt")),
          "model_revision": st["model_revision"], "chat_template_sha256": st["chat_template_sha256"], "mapping": mapping, "free_mib_before": free, "args": vars(a),
          "code_sha256": {f: file_sha(f) for f in CODE}, "requests_sha256": file_sha(REQ[a.set]), "n_patients": len(by_p), "n_requests": len(rows)}
    json.dump(lp, open(os.path.join(a.out_dir, "launch_protocol.json"), "x"), indent=1)
    t0 = time.time()
    procs = {}
    for k in range(a.workers):
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(mapping[k]))
        cmd = [sys.executable, "pg48_ctime.py", "worker", "--system", a.system, "--order", a.order, "--adapter", a.adapter, "--set", a.set, "--out-dir", a.out_dir,
               "--worker", str(k), "--warmup-n", str(a.warmup_n), "--barrier", bdir]
        procs[k] = subprocess.Popen(cmd, env=env, stdout=open(os.path.join(a.out_dir, f"worker{k}.stdout"), "a"), stderr=open(os.path.join(a.out_dir, f"worker{k}.stderr"), "a"))

    def kill_children():
        for p in procs.values():
            if p.poll() is None:
                p.terminate()
        for p in procs.values():
            try:
                p.wait(timeout=30)
            except subprocess.TimeoutExpired:
                p.kill()

    signal.signal(signal.SIGTERM, lambda *_: (kill_children(), sys.exit(143)))
    rl = open(os.path.join(a.out_dir, "resource_log.jsonl"), "a")
    t_go, last, aborted = None, 0, None
    while any(p.poll() is None for p in procs.values()):
        if t_go is None:
            dead = [k for k, p in procs.items() if p.poll() is not None]
            if dead:  # barrier 전에 child가 끝났다 (정상 종료라도 ready를 못 썼으면 실패)
                if not all(os.path.exists(os.path.join(bdir, f"ready.{k}")) for k in range(a.workers)):
                    aborted = f"worker(s) {dead} exited before barrier (rc={[procs[k].returncode for k in dead]})"
                    kill_children()
                    break
            if all(os.path.exists(os.path.join(bdir, f"ready.{k}")) for k in range(a.workers)):
                t_go = time.time()
                tmpg = os.path.join(bdir, f"go.{os.getpid()}.tmp")
                json.dump({"t": t_go}, open(tmpg, "w"))
                os.replace(tmpg, os.path.join(bdir, "go"))
        time.sleep(0.02 if t_go is None else 0.5)
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
    ids = [r["request_id"] for r in recs]
    want = {r["request_id"] for r in rows}
    complete = aborted is None and len(ids) == len(set(ids)) and set(ids) == want
    iv = {}
    for r in recs:
        iv.setdefault(mapping[r["worker"]], set()).add((r["t_patient_dispatch"], r["t_patient_done"]))
    res = {"exit_codes": codes, "aborted": aborted, "launcher_wall_s_incl_loading": wall, "n_records": len(recs), "n_unique": len(set(ids)), "n_expected": len(want), "complete": complete,
           "workers": a.workers, "mapping": mapping, "t_go": t_go, "device_seconds_union": sum(union(v) for v in iv.values()) if iv else None,
           "launch_protocol_sha256": file_sha(os.path.join(a.out_dir, "launch_protocol.json"))}
    metas = [json.load(open(p)) for p in glob.glob(os.path.join(a.out_dir, "worker*.meta.*.json"))]
    if metas:
        res["peak_alloc_gb_max"] = max(m["peak_alloc_gb"] for m in metas)
        res["peak_reserved_gb_max"] = max(m["peak_reserved_gb"] for m in metas)
        res["cold_load_s"] = {m["worker"]: m["load_s"] for m in metas}
    dn = [json.load(open(p))["t"] for p in glob.glob(os.path.join(bdir, "done.*"))]
    res["workload_wall_s"] = (max(dn) - t_go) if (dn and t_go) else None
    if complete and all(c == 0 for c in codes):
        res["worker_file_sha256"] = {os.path.basename(f): file_sha(f) for f in sorted(glob.glob(os.path.join(a.out_dir, "ctime_worker*.jsonl")))}
        tmp = os.path.join(a.out_dir, f"completion.{os.getpid()}.tmp")
        json.dump(res, open(tmp, "w"), indent=1)
        os.replace(tmp, os.path.join(a.out_dir, "completion.json"))
        print("completion", json.dumps({k: res[k] for k in ("exit_codes", "n_unique", "launcher_wall_s_incl_loading", "workload_wall_s")}))
    else:
        json.dump(res, open(os.path.join(a.out_dir, f"partial_{int(time.time())}.json"), "w"), indent=1)
        print("NOT complete", json.dumps({k: res[k] for k in ("exit_codes", "aborted", "n_unique", "n_expected")}))
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("worker")
    l = sub.add_parser("launch")
    for s in (w, l):
        s.add_argument("--system", choices=["E", "J"], required=True)
        s.add_argument("--order", choices=["AB", "BA"], default="AB")
        s.add_argument("--adapter", required=True)
        s.add_argument("--out-dir", required=True)
        s.add_argument("--set", default="V96", choices=["V96", "D24"])
        s.add_argument("--warmup-n", type=int, default=8)
    w.add_argument("--worker", type=int, required=True)
    w.add_argument("--barrier", required=True)
    l.add_argument("--workers", type=int, required=True)
    l.add_argument("--gpus", default=None)
    l.add_argument("--barrier", action="store_true", help="항상 barrier를 사용한다 (인자는 호환용)")
    l.add_argument("--peak-gb", type=float, default=10.0)
    a = ap.parse_args()
    {"worker": worker, "launch": launch}[a.cmd](a)


if __name__ == "__main__":
    main()
