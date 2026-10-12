"""iter_114 MedGrounder(대상 A_U_e5 / 대조 MSPC) 추론 worker + launcher.

공식 소스(mg45_mg.py, iter_046 승인 범위: 공식 build_medgrounder/InferencePostProcessor/run_wbf/val transform, strict load)를 그대로 호출한다.
- 아키텍처 cfg 는 공식 conf_pretrain_imagenome.yaml 과 conf_finetune_mspc.yaml 이 resume 줄만 다르므로 동일 cfg 를 쓰고 checkpoint 는 명시 경로 + sha256 잠금으로 연결한다.
- threshold 0.8, WBF IoU 0.1 고정. GT/extra 는 이 모듈에 들어오지 않는다(요청은 영상·문장뿐).
- 요청 ID 는 (stage, model, ImageID, finding_index) 로 정해지고, item i % n_workers == worker 인 정적 분할 + worker flock 으로 중복/충돌을 막는다.
- 출력은 worker별 raw_worker{k}.jsonl (요청마다 record_digest, fsync), 손상된 마지막 행은 보존(.partial) 후 잘라낸다.
- 완료: 모든 worker 가 정확한 요청 집합을 채웠고 digest 가 맞을 때만 completion.json.
사용 (venv python 으로 worker, 시스템 python 으로 launch):
  python nr114_mg.py launch --stage DEV --model MSPC --workers 1 --batch 4 [--tag w1b4]
"""
import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
R114 = HERE / "results/iter_114"
DATA = R114 / "data"
R107 = HERE / "results/iter_107/data"
VENV_PY = HERE / "results/environments/medgrounder_iter045/bin/python"
CKPT = {
    "A": {"path": HERE / "results/iter_046/train/U/weights_e5.pth", "sha256": "b9c2bccd04dde8b7445aa5f60e082a0c93f1f2412af8a583a4ca5ee207c8718a"},
    "MSPC": {"path": R114 / "external/weights/medgrounder_finetune_mspc.pth", "sha256": "ec33f4a642dad324eb980d2984574566b385e6592af22df461989d96a83295c2"},
}
THR = "0.8"
STAGES = ("DEV", "DEV4", "INIT", "EXPAND")
EXEC_SOURCES = ["nr114_mg.py", "mg45_mg.py"]
MG_CODE_MANIFEST = HERE / "results/iter_045/external/code_manifest.json"
MARGIN_MIB = 2048
PEAK_MIB = 4000  # 실측(iter_046 batch4 peak reserved 1.33GiB) 대비 여유를 둔 admission 값. 이번 DEV 실측으로 재확인한다.


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


def sha_obj(o):
    return hashlib.sha256(json.dumps(o, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def save_new(p, obj):
    p = Path(p)
    tmp = p.with_name(p.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False))
    if p.exists():
        tmp.unlink()
        raise FileExistsError(p)
    os.link(tmp, p)  # 원자적 새 파일 생성(기존 파일 덮어쓰기 금지)
    tmp.unlink()


# ------------------------------------------------------------------ 요청
def stage_items(stage):
    if stage in ("DEV", "DEV4"):
        items = json.loads((R107 / "items.json").read_text())
        for it in items:
            it["_u8"] = it["u8_image"]
        if stage == "DEV4":
            keys = json.loads((R107 / "cohort_summary.json").read_text())["tech_first4_item_keys"]
            m = {it["item_key"]: it for it in items}
            items = [m[k] for k in keys]
    else:
        items = json.loads((DATA / "items.json").read_text())
        want = "init" if stage == "INIT" else "expand"
        items = [it for it in items if it["stage"] == want]
        for it in items:
            it["_u8"] = str(HERE / it["image_meta"]["path"])
    return sorted(items, key=lambda it: it["item_key"])


def request_id(stage, model, it):
    return hashlib.sha256(f"iter114|{stage}|{model}|{it['ImageID']}|{it['finding_index']}".encode()).hexdigest()[:32]


def requests_for(stage, model):
    return [{"request_id": request_id(stage, model, it), "item_key": it["item_key"], "ImageID": it["ImageID"], "finding_index": it["finding_index"],
             "sentence_sha256": hashlib.sha256(it["sentence"].encode()).hexdigest(), "u8_pixel_sha256": it["image_meta"]["u8_pixel_sha256"]}
            for it in stage_items(stage)]


def items_digest(stage):
    return sha_obj([{k: it[k] for k in ("item_key", "ImageID", "finding_index", "sentence_sha256")} | {"u8": it["image_meta"]["u8_pixel_sha256"]}
                    for it in stage_items(stage)])


def scientific_protocol(stage, model, nworkers):
    return {"stage": stage, "model": model, "nworkers": nworkers, "thr": THR, "wbf_iou": 0.1, "ckpt_sha256": CKPT[model]["sha256"],
            "requests_sha256": sha_obj(requests_for(stage, model)), "items_sha256": items_digest(stage),
            "source_sha256": {f: sha_file(HERE / f) for f in EXEC_SOURCES},
            "official_code_manifest_sha256": sha_file(MG_CODE_MANIFEST), "official_code_sha": json.loads(MG_CODE_MANIFEST.read_text())["sha"],
            "arch_cfg": "conf_pretrain_imagenome.yaml (== conf_finetune_mspc.yaml except resume)"}


def record_digest(r):
    return sha_obj({k: v for k, v in r.items() if k not in ("record_digest", "exec")})


def read_complete(path):
    """완결된(개행으로 끝나는) 행만 읽는다."""
    if not os.path.exists(path):
        return []
    data = open(path, "rb").read()
    lines = data.split(b"\n")[:-1]
    return [json.loads(l) for l in lines if l.strip()]


def repair_tail(path):
    if not os.path.exists(path):
        return 0
    data = open(path, "rb").read()
    if data and not data.endswith(b"\n"):
        tail = data.rsplit(b"\n", 1)[-1]
        keep = f"{path}.partial.{int(time.time())}.{os.getpid()}.bin"
        with open(keep, "xb") as f:
            f.write(tail)
        with open(path, "r+b") as f:
            f.truncate(len(data) - len(tail))
        return len(tail)
    return 0


def shard_target(stage, model, k, n):
    items = stage_items(stage)
    mine = {items[i]["item_key"] for i in range(len(items)) if i % n == k}
    return [q for q in requests_for(stage, model) if q["item_key"] in mine]


def load_own(path, reqmap, digest):
    recs = read_complete(path)
    ids = [r["request_id"] for r in recs]
    assert len(ids) == len(set(ids)), "duplicate request_id in own output"
    for r in recs:
        q = reqmap.get(r["request_id"])
        assert q is not None, "record outside request set"
        assert r["protocol_digest"] == digest, "protocol digest mismatch"
        assert r["record_digest"] == record_digest(r), "record digest mismatch (tampered)"
        for k in ("item_key", "ImageID", "finding_index", "sentence_sha256", "u8_pixel_sha256"):
            assert r[k] == q[k], f"record {k} differs from request"
        assert r["ckpt_sha256"] == CKPT[r["model"]]["sha256"]
    return recs


# ------------------------------------------------------------------ worker (venv python)
def worker(a):
    out = Path(a.out_dir).resolve()
    out.relative_to(R114)
    allowed = os.environ["CUDA_VISIBLE_DEVICES"].split(",")
    assert a.gpu in allowed, f"gpu {a.gpu} not in inherited CUDA_VISIBLE_DEVICES {allowed}"
    os.environ["CUDA_VISIBLE_DEVICES"] = a.gpu
    sci = scientific_protocol(a.stage, a.model, a.n_workers)
    digest = sha_obj(sci)
    out.mkdir(parents=True, exist_ok=True)
    lock = (out / f"worker{a.worker}.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    rawp = out / f"raw_worker{a.worker}.jsonl"
    repair_tail(str(rawp))
    meta = {"scientific": sci, "scientific_digest": digest, "worker": a.worker}
    mp = out / f"scientific_protocol{a.worker}.json"
    if mp.exists():
        assert json.loads(mp.read_text()) == json.loads(json.dumps(meta)), "resume: protocol/source/shard mismatch (before model load)"
    else:
        save_new(mp, meta)
    target = shard_target(a.stage, a.model, a.worker, a.n_workers)
    reqmap = {q["request_id"]: q for q in target}
    if (out / f"completion{a.worker}.json").exists():
        c = json.loads((out / f"completion{a.worker}.json").read_text())
        for name, h in c["files"].items():
            assert sha_file(out / name) == h, "completion file hash differs"
        recs = load_own(rawp, reqmap, digest)
        assert {r["request_id"] for r in recs} == set(reqmap)
        return 0
    done = {r["request_id"] for r in load_own(rawp, reqmap, digest)}
    todo_q = [q for q in target if q["request_id"] not in done]
    if a.limit:
        todo_q = todo_q[:a.limit]
    items = {it["item_key"]: it for it in stage_items(a.stage)}
    ck = CKPT[a.model]
    t_proc = time.time()
    import torch
    import mg45_mg as M
    t_ck = time.time()
    assert sha_file(ck["path"]) == ck["sha256"], "checkpoint sha256 changed"
    sha_s = time.time() - t_ck
    dev = torch.device("cuda:0")
    t_ld = time.time()
    model, cfg, load = M.load_model("MSPC" if a.model == "MSPC" else "A_U_e5", dev, str(ck["path"]))
    assert not load["missing"] and not load["unexpected"], load
    tf = M.val_transform()
    load_s = time.time() - t_ld
    torch.cuda.reset_peak_memory_stats()
    ev = (out / f"executions{a.worker}.jsonl").open("a", buffering=1)
    ev.write(json.dumps({"event": "start", "time": time.time(), "pid": os.getpid(), "gpu_physical": a.gpu, "n_todo": len(todo_q), "n_target": len(target),
                         "n_done_before": len(done), "python": sys.executable, "torch": torch.__version__, "batch": a.batch,
                         "load_s": load_s, "ckpt_sha_s": sha_s, "strict_load": {k: load[k] for k in ("n_state_keys",)}}) + "\n")
    cache, saved = {}, 0
    t_start = time.time()
    with rawp.open("a", buffering=1) as f:
        for s in range(0, len(todo_q), a.batch):
            grp = todo_q[s:s + a.batch]
            t0 = time.time()
            imgs, affs, shas = [], [], []
            for q in grp:
                it = items[q["item_key"]]
                if it["ImageID"] not in cache:
                    ten, aff, u8 = M.prepare(it["_u8"], tf)
                    assert u8 == it["image_meta"]["u8_pixel_sha256"], f"decoded pixel hash != manifest {it['ImageID']}"
                    cache[it["ImageID"]] = (ten, aff, u8)
                ten, aff, u8 = cache[it["ImageID"]]
                imgs.append(ten); affs.append(aff); shas.append(u8)
            t1 = time.time()
            lg, bx = M.forward(model, imgs, [items[q["item_key"]]["sentence"] for q in grp], dev)
            t2 = time.time()
            det = M.postprocess(lg, bx, float(THR))
            t3 = time.time()
            for i, q in enumerate(grp):
                d = det[i]
                boxes = M.canvas_cxcywh_to_orig_xyxy(d["boxes"], affs[i])
                rec = {"request_id": q["request_id"], "stage": a.stage, "model": a.model, "item_key": q["item_key"], "ImageID": q["ImageID"],
                       "finding_index": q["finding_index"], "sentence_sha256": q["sentence_sha256"], "u8_pixel_sha256": shas[i],
                       "ckpt_sha256": ck["sha256"], "protocol_digest": digest, "aff": affs[i], "logits": lg[i].tolist(),
                       "pred_boxes_cxcywh": bx[i].tolist(), "detection": {"boxes_orig_xyxy": boxes, "scores": d["scores"], "pre_wbf_n": d["pre_wbf_n"]},
                       "batch": a.batch, "group_n": len(grp), "worker": a.worker, "n_workers": a.n_workers,
                       "t_dispatch": t0, "t_loaded": t1, "t_forward_done": t2, "t_done": t3 + 0.0,
                       "exec": {"gpu": a.gpu, "pid": os.getpid(), "torch": torch.__version__, "peak_alloc_gb": torch.cuda.max_memory_allocated() / 2**30}}
                rec["record_digest"] = record_digest(rec)
                f.write(json.dumps(rec) + "\n")
                f.flush()
                os.fsync(f.fileno())
                saved += 1
    ev.write(json.dumps({"event": "end", "time": time.time(), "saved": saved, "wall_s": time.time() - t_start,
                         "peak_alloc_gb": torch.cuda.max_memory_allocated() / 2**30, "peak_reserved_gb": torch.cuda.max_memory_reserved() / 2**30,
                         "proc_s": time.time() - t_proc}) + "\n")
    recs = load_own(rawp, reqmap, digest)
    if {r["request_id"] for r in recs} == set(reqmap) and not (out / f"completion{a.worker}.json").exists():
        save_new(out / f"completion{a.worker}.json", {
            "stage": a.stage, "model": a.model, "worker": a.worker, "n_workers": a.n_workers, "n_own_records": len(recs),
            "files": {f"raw_worker{a.worker}.jsonl": sha_file(rawp), f"scientific_protocol{a.worker}.json": sha_file(mp)},
            "executions": sum(1 for l in (out / f"executions{a.worker}.jsonl").read_text().splitlines() if '"start"' in l)})
    print(json.dumps({"worker": a.worker, "saved": saved, "total": len(recs), "of": len(target)}))
    return 0


# ------------------------------------------------------------------ launcher (system python)
def smi_free():
    raw = subprocess.check_output(["nvidia-smi", "--query-gpu=index,memory.free,memory.used,memory.total", "--format=csv,noheader,nounits"], text=True)
    return {x.split(",")[0].strip(): [int(v) for v in x.split(",")[1:]] for x in raw.splitlines()}


def verify_all(out, stage, model, n):
    out = Path(out)
    digest = sha_obj(scientific_protocol(stage, model, n))
    recs = []
    for k in range(n):
        c = json.loads((out / f"completion{k}.json").read_text())
        for name, h in c["files"].items():
            assert sha_file(out / name) == h, f"completion file hash differs {name}"
        target = shard_target(stage, model, k, n)
        reqmap = {q["request_id"]: q for q in target}
        r = load_own(out / f"raw_worker{k}.jsonl", reqmap, digest)
        assert {x["request_id"] for x in r} == set(reqmap), "record set != expected request set"
        recs += r
    want = {q["request_id"] for q in requests_for(stage, model)}
    assert {r["request_id"] for r in recs} == want and len(recs) == len(want), "global request set mismatch (missing/extra/duplicate)"
    return recs, digest


def launch(a):
    out = Path(a.out_dir).resolve()
    out.relative_to(R114)
    out.mkdir(parents=True, exist_ok=True)
    allowed = os.environ["CUDA_VISIBLE_DEVICES"].split(",")
    with (out / "launcher.lock").open("a") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
        sd = sha_obj(scientific_protocol(a.stage, a.model, a.workers))
        mp = out / "mapping.json"
        want = {"stage": a.stage, "model": a.model, "workers": a.workers, "scientific_digest": sd, "batch_tag": a.tag}
        if mp.exists():
            assert json.loads(mp.read_text()) == want, "launcher mapping/protocol changed"
        else:
            save_new(mp, want)
        pending = [k for k in range(a.workers) if not (out / f"completion{k}.json").exists()]
        if not pending:
            verify_all(out, a.stage, a.model, a.workers)
            return 0
        placement = a.placement.split(",") if a.placement else None
        if placement:
            assert len(placement) >= len(pending) and set(placement) <= set(allowed), ("placement outside allowed", placement, allowed)
        attempt = len(list(out.glob("launch_*.json")))
        procs, logs, adm, codes = [], [], [], {}
        t0 = time.monotonic()
        status, err = "started", None
        try:
            for n, k in enumerate(pending):
                st = smi_free()
                apps = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"], text=True)
                actual = {int(x.split(",")[0]): int(x.split(",")[1]) for x in apps.splitlines() if x.strip()}
                choices = {g: st[g][0] - sum(max(0, PEAK_MIB - actual.get(p.pid, 0)) + MARGIN_MIB for kk, p, gg in procs if gg == g and p.poll() is None) for g in allowed}
                gpu = placement[n] if placement else max(choices, key=choices.get)
                adm.append({"job": k, "choices_free_mib": choices, "chosen": gpu, "need_mib": PEAK_MIB + MARGIN_MIB, "smi": st})
                assert choices[gpu] >= PEAK_MIB + MARGIN_MIB, ("memory admission refused", choices)
                cmd = [str(VENV_PY), str(HERE / "nr114_mg.py"), "worker", "--stage", a.stage, "--model", a.model, "--out-dir", str(out), "--gpu", gpu,
                       "--worker", str(k), "--n-workers", str(a.workers), "--batch", str(a.batch)] + (["--limit", str(a.limit)] if a.limit else [])
                so, se = (out / f"launch{attempt}_w{k}.stdout.log").open("x"), (out / f"launch{attempt}_w{k}.stderr.log").open("x")
                logs += [so, se]
                env = dict(os.environ, HF_HUB_OFFLINE="1", NO_ALBUMENTATIONS_UPDATE="1")
                procs.append((k, subprocess.Popen(cmd, cwd=HERE, env=env, stdout=so, stderr=se), gpu))
            codes = {f"w{k}": p.wait() for k, p, _ in procs}
            status = "finished"
        except BaseException as e:
            status, err = "failed", repr(e)
            raise
        finally:
            for _, p, _ in procs:
                if p.poll() is None:
                    p.terminate()
            for _, p, _ in procs:
                p.wait()
            for f in logs:
                f.close()
            save_new(out / f"launch_{attempt:03}.json", {"status": status, "error": err, "codes": codes, "wall_s": time.monotonic() - t0,
                                                          "mapping": {f"w{k}": g for k, _, g in procs}, "scientific_digest": sd, "allowed": allowed,
                                                          "admission": adm, "batch": a.batch, "script_sha256": sha_file(__file__)})
        assert all(c == 0 for c in codes.values()), codes
        if all((out / f"completion{k}.json").exists() for k in range(a.workers)):
            recs, _ = verify_all(out, a.stage, a.model, a.workers)
            if not (out / "completion.json").exists():
                save_new(out / "completion.json", {"stage": a.stage, "model": a.model, "workers": a.workers, "scientific_digest": sd, "n_records": len(recs),
                                                   "files": {f"completion{k}.json": sha_file(out / f"completion{k}.json") for k in range(a.workers)}})
            return 0
        return 0 if a.limit else 2


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["worker", "launch"])
    p.add_argument("--stage", choices=STAGES, required=True)
    p.add_argument("--model", choices=list(CKPT), required=True)
    p.add_argument("--out-dir", dest="out_dir")
    p.add_argument("--tag", default="")
    p.add_argument("--gpu")
    p.add_argument("--worker", type=int, default=0)
    p.add_argument("--n-workers", type=int, default=1)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--batch", type=int, default=4)
    p.add_argument("--placement", default="")
    p.add_argument("--limit", type=int, default=0)
    a = p.parse_args()
    if not a.out_dir:
        a.out_dir = str(R114 / "mg" / f"{a.stage}_{a.model}_{a.tag or 'w%db%d' % (a.workers, a.batch)}")
    sys.exit(worker(a) if a.command == "worker" else launch(a))
