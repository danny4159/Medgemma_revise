"""iter_045 MedGrounder worker launcher (기본 python에서 실행; worker는 격리 venv python subprocess).

python mg45_launch.py --set D24 --ckpt P --out-dir results/iter_045/mg/D24_P_w2b1 --workers 2 --gpus 0,1 --batch 1 [--post-thr T] [--barrier] [--warmup-d8]

- worker k는 허용 GPU 집합(CUDA_VISIBLE_DEVICES 상속) 안의 gpus[k % len(gpus)]에 매핑한다. 실제 여유 메모리 큰 장치부터 배정하고
  GPU별 (worker 수 x (peak-gb + 2GiB))가 현재 free 안에 들어와야 시작한다 (다른 프로세스 점유 포함).
- completion.json은 모든 worker 정상 종료 + 예상 (환자x문장) 집합과 정확히 일치(누락/중복/잉여 0)일 때만 원자적으로 작성한다. 이미 있으면 거부.
- --barrier: worker가 모델 로딩+warm-up 후 ready를 쓰면 launcher가 go 시각을 기록하고 workload wall = max(worker done) - go 로 측정한다.
"""
import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(HERE, "results", "environments", "medgrounder_iter045", "bin", "python")
MAN = "results/iter_043/data/manifest_private.json"
CODE = ["mg45_mg.py", "mg45_worker.py", "mg45_launch.py"]


def file_sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def gpu_free_mib():
    r = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,memory.total", "--format=csv,noheader,nounits"],
                       capture_output=True, text=True, check=True)
    return {int(l.split(",")[0]): (int(l.split(",")[2]) - int(l.split(",")[1])) for l in r.stdout.strip().splitlines()}


def expected_ids(setname, ckpt):
    man = json.load(open(MAN))
    ents = man["D24"] if setname in ("D8", "D24") else man[setname]
    if setname == "D8":
        keep = set(man["D8"])
        ents = [e for e in ents if e["PatientID"] in keep]
    sys.path.insert(0, HERE)
    import hashlib as h
    return {h.sha256(f"{setname}|{ckpt}|{e['PatientID']}|{t}".encode()).hexdigest()[:32] for e in ents for t in ("qA", "qB")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True)
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--workers", type=int, required=True)
    ap.add_argument("--gpus", default=None)
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--post-thr", type=float, default=None)
    ap.add_argument("--warmup-d8", action="store_true")
    ap.add_argument("--barrier", action="store_true")
    ap.add_argument("--peak-gb", type=float, default=4.0)
    ap.add_argument("--max-items", type=int, default=None)
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    if os.path.exists(os.path.join(a.out_dir, "completion.json")):
        sys.exit("completion.json exists: use a new out-dir")
    allowed = [int(x) for x in os.environ["CUDA_VISIBLE_DEVICES"].split(",")] if os.environ.get("CUDA_VISIBLE_DEVICES") else None
    if allowed is None:
        sys.exit("CUDA_VISIBLE_DEVICES not set; refusing to pick devices")
    gpus = [int(x) for x in a.gpus.split(",")] if a.gpus else allowed
    if not set(gpus) <= set(allowed):
        sys.exit(f"--gpus {gpus} not within allowed {allowed}")
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
    proto = {"code": {f: file_sha(os.path.join(HERE, f)) for f in CODE}, "manifest_sha256": file_sha(os.path.join(HERE, MAN)),
             "ckpt_sha256": file_sha(os.path.join(HERE, "results/iter_045/external/weights",
                                                  "medgrounder_pretrain_imagenome.pth" if a.ckpt == "P" else "medgrounder_finetune_ms.pth")),
             "args": vars(a), "mapping": mapping, "free_mib_before": free}
    pp = os.path.join(a.out_dir, "launch_protocol.json")
    if not os.path.exists(pp):
        json.dump(proto, open(pp, "x"), indent=1)
    t0 = time.time()
    procs = {}
    for k in range(a.workers):
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(mapping[k]))
        cmd = [PY, "mg45_worker.py", "--set", a.set, "--ckpt", a.ckpt, "--out-dir", a.out_dir, "--worker", str(k),
               "--n-workers", str(a.workers), "--batch", str(a.batch)]
        if a.post_thr is not None:
            cmd += ["--post-thr", str(a.post_thr)]
        if a.warmup_d8:
            cmd += ["--warmup-d8"]
        if bdir:
            cmd += ["--barrier", bdir]
        if a.max_items is not None:
            cmd += ["--max-items", str(a.max_items)]
        procs[k] = subprocess.Popen(cmd, cwd=HERE, env=env, stdout=open(os.path.join(a.out_dir, f"worker{k}.stdout"), "a"),
                                    stderr=open(os.path.join(a.out_dir, f"worker{k}.stderr"), "a"))
    rl = open(os.path.join(a.out_dir, "resource_log.jsonl"), "a")
    t_go = None
    last_sample = 0
    while any(p.poll() is None for p in procs.values()):
        if bdir and t_go is None:
            if all(os.path.exists(os.path.join(bdir, f"ready.{k}")) for k in range(a.workers)):
                t_go = time.time()
                tmpg = os.path.join(bdir, f"go.{os.getpid()}.tmp")  # 원자적 작성 (worker가 쓰는 도중의 빈 파일을 읽는 경쟁 방지; 1차 시도에서 실제 발생)
                json.dump({"t": t_go}, open(tmpg, "w"))
                os.replace(tmpg, os.path.join(bdir, "go"))
            elif any(p.poll() is not None for p in procs.values()):
                break
        time.sleep(0.02 if (bdir and t_go is None) else 0.5)
        if time.time() - last_sample > 5:
            last_sample = time.time()
            used = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
                                  capture_output=True, text=True).stdout.strip().splitlines()
            rl.write(json.dumps({"t": round(time.time() - t0, 1), "gpu": used}) + "\n")
            rl.flush()
    codes = [procs[k].wait() for k in range(a.workers)]
    wall = time.time() - t0
    recs = []
    for fn in sorted(glob.glob(os.path.join(a.out_dir, "raw_worker*.jsonl"))):
        for ln in open(fn, "rb").read().split(b"\n")[:-1]:
            if ln.strip():
                recs.append(json.loads(ln))
    ids = [r["request_id"] for r in recs]
    want = expected_ids(a.set, a.ckpt)
    complete = a.max_items is None and len(ids) == len(set(ids)) and set(ids) == want
    # GPU별 점유 구간 (worker 요청 구간 합집합) -- timing용
    iv = {}
    for r in recs:
        iv.setdefault(mapping[r["worker"]], []).append((r["t_dispatch"], r["t_done"]))

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

    res = {"exit_codes": codes, "launcher_wall_s_incl_loading": wall, "n_records": len(recs), "n_unique": len(set(ids)), "n_expected": len(want),
           "complete": complete, "workers": a.workers, "mapping": mapping, "batch": a.batch,
           "device_seconds_request_union": sum(union(v) for v in iv.values()) if iv else None,
           "t_go": t_go, "peak_alloc_gb_max": max((r["peak_alloc_gb"] for r in recs), default=None)}
    if bdir:
        dn = [json.load(open(p))["t"] for p in glob.glob(os.path.join(bdir, "done.*"))]
        res["workload_wall_s"] = (max(dn) - t_go) if (dn and t_go) else None
    if complete and all(c == 0 for c in codes):
        res["raw_file_sha256"] = {os.path.basename(f): file_sha(f) for f in sorted(glob.glob(os.path.join(a.out_dir, "raw_worker*.jsonl")))}
        res["launch_protocol_sha256"] = file_sha(pp)
        tmp = os.path.join(a.out_dir, f"completion.{os.getpid()}.tmp")
        json.dump(res, open(tmp, "w"), indent=1)
        os.replace(tmp, os.path.join(a.out_dir, "completion.json"))
        print("completion", json.dumps({k: res[k] for k in ("exit_codes", "n_unique", "launcher_wall_s_incl_loading", "workload_wall_s") if k in res}))
    else:
        json.dump(res, open(os.path.join(a.out_dir, f"partial_{int(time.time())}.json"), "w"), indent=1)
        print("NOT complete", json.dumps({k: res[k] for k in ("exit_codes", "n_unique", "n_expected")}))
        sys.exit(1)


if __name__ == "__main__":
    main()
