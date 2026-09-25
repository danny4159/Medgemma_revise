"""iter_012 본실험 파이프라인 (iter_010 사전 고정 규칙 유지, 재개 가능·단계별 근거 검증). 사용: python -m rsna_diag.pipeline

단계 (건너뛰기는 파일 존재가 아니라 현재 근거의 재검증을 통과할 때만):
 1. seed17 두 LR을 5 epochs까지 새 run-dir에서 처음부터 학습 (GPU당 학습 1개). select.load_epochs 통과 시에만 완료로 본다.
 2. extend 판정: select.payload를 원시 근거에서 재계산해 파일에 쓰거나(없을 때) 기존 파일과 완전히 같은지 검증.
 3. 연장이면 두 LR 모두 8 epochs, 그 뒤 seed17 LR·checkpoint pick (같은 방식).
 4. seed 29, 43을 선택 LR·E로 학습 (GPU0: seed29, GPU1: seed43), seed별 pick.
 5. 생성 경로 점검: development thr24로 4 worker(2 GPU x 2) base 두 prompt + 선택 seed17 adapter concise를 생성해
    완료·오류·GPU 전체 점유를 확인하고 iter_010 thr_w4 출력과 대조한다. 사전 기준(아래 MEM_LIMIT_MIB)으로 worker 수를 정한다.
 6. base validation 생성(iter_010 부모 record 검증 후 연결) -> comparator (확인 결과를 보기 전에 고정)
 7. confirm base(official_long/concise x 800) + SFT 3 seed(concise x 800) 생성
 8. final_eval confirm (comparator·extend·pick을 모두 재계산 검증)
실패하면 예외로 중단한다. 재실행하면 검증을 통과한 단계만 건너뛴다. pipeline.lock으로 단일 소유를 강제한다
(train.lock은 학습 child가 run-dir별로 잡으며 pipeline은 train.lock을 보유하지 않으므로 교착하지 않는다).
"""
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

from . import eval_gate, final_eval, inputs, queue_lock, select as SEL
from .run_shards import gpu_snapshot

R = "results/iter_012"
PROT = f"{R}/protocols/main_protocol.json"
OLD_PROT = "results/iter_010/protocols/main_protocol.json"
MAN = "results/iter_010/manifests/infer_manifest.jsonl"
GTP = "results/iter_010/manifests/gt_manifest.json"
IDS = "results/iter_010/manifests/{}_ids.json"
THR_IDS = "results/iter_010/pilot/thr24_ids.json"  # iter_009 development 24명 (iter_009 manifest)
THR_MAN = "results/iter_009/manifests/infer_manifest.jsonl"
THR_GT = "results/iter_009/manifests/gt_manifest.json"
THR_REF = "results/iter_010/pilot/thr_w4"
LOG = f"{R}/pipeline.log"
STATUS = f"{R}/pipeline_status.json"
GPUS = ("0", "1")
MEM_LIMIT_MIB = 24576 - 2 * 2048  # 2 worker/GPU 채택 조건: GPU 전체 점유 최대 + worker당 2GiB 여유 <= 24GiB
FREE_BEFORE_MIB = 2000  # 학습·생성 시작 전 허용 GPU의 기존 점유 상한 (다른 작업과 섞지 않는다)


def log(msg):
    line = f"[{time.strftime('%F %T')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def status(stage, **kw):
    tmp = STATUS + ".tmp"
    json.dump({"stage": stage, "ts": time.time(), "time": time.strftime("%F %T"), **kw}, open(tmp, "w"), indent=1)
    os.replace(tmp, STATUS)


def sh(cmd, check=True):
    log("RUN " + " ".join(cmd))
    p = subprocess.run(cmd)
    log(f"rc={p.returncode}")
    if check and p.returncode != 0:
        raise RuntimeError(f"command failed rc={p.returncode}: {' '.join(cmd)}")
    return p.returncode


def wait_gpus_free(gpus=GPUS):
    """시작 직전 허용 GPU의 실제 점유를 확인한다. 다른 작업이 점유 중이면 기다린다 (종료시키지 않는다)."""
    while True:
        rows, apps = gpu_snapshot({int(g) for g in gpus})
        busy = [r for r in rows if r["mem_used_mib"] > FREE_BEFORE_MIB]
        if not busy:
            log(f"gpus free: {[(r['index'], r['uuid'], r['mem_used_mib']) for r in rows]}")
            return rows
        log(f"waiting for GPU memory to be released: {busy} apps={apps}")
        time.sleep(120)


def wait_unlocked(run_dirs):
    """실행 중인 학습(run-dir train.lock 보유)이 끝날 때까지 기다린다. lock을 빼앗지 않는다."""
    import fcntl
    while True:
        busy = []
        for d in run_dirs:
            lp = os.path.join(d, "train.lock")
            if os.path.exists(lp):
                fd = os.open(lp, os.O_RDONLY)  # 읽기 전용 probe: 파일 내용을 바꾸지 않는다
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except BlockingIOError:
                    busy.append((d, open(lp).read()[:200]))
                finally:
                    os.close(fd)
        if not busy:
            return
        log(f"waiting for live train owners: {busy}")
        time.sleep(120)


def run_dir(lr, seed):
    return f"{R}/train/lr{lr}_s{seed}"


def trained_ok(d, epochs):
    """epoch 1..epochs 전체가 원시 근거로 검증되면 True. 파일이 없거나 불완전하면 False. 근거 불일치(변조 등)는 예외로 중단."""
    if not os.path.exists(os.path.join(d, "train_config.json")):
        return False
    for e in range(1, epochs + 1):
        if not os.path.exists(os.path.join(d, f"epoch_{e:02d}", "val_metrics.json")):
            return False
    SEL.load_epochs(d, epochs, PROT)
    return True


def ensure_trained(name, runs, epochs):
    """runs: [(gpu, lr, seed)]. 모두 검증되면 건너뛰고, 아니면 launch.py로 동시에 학습(재개)한다."""
    dirs = [run_dir(lr, seed) for _, lr, seed in runs]
    wait_unlocked(dirs)
    if all(trained_ok(d, epochs) for d in dirs):
        log(f"{name}: epochs 1..{epochs} verified for all runs")
        return
    wait_gpus_free(tuple(sorted({str(g) for g, _, _ in runs})))
    jobs = []
    for gpu, lr, seed in runs:
        d = run_dir(lr, seed)
        jobs.append({"gpu": str(gpu), "module": "rsna_diag.train", "log": f"{d}.log",
                     "args": ["--run-dir", d, "--lr", lr, "--seed", str(seed), "--epochs", str(epochs), "--protocol", PROT, "--microbatch", "2"]})
    tag = f"{name}_e{epochs}_{time.strftime('%Y%m%d_%H%M%S')}"
    jp = f"{R}/train/jobs_{tag}.json"
    os.makedirs(f"{R}/train", exist_ok=True)
    json.dump(jobs, open(jp, "w"), indent=1)
    status("train", name=name, epochs=epochs, jobs=jp)
    sh([sys.executable, "-m", "rsna_diag.launch", "--jobs", jp, "--log-dir", f"{R}/train/launch_{tag}"])
    for d in dirs:
        if not trained_ok(d, epochs):
            raise RuntimeError(f"{d}: epochs 1..{epochs} not verified after training")


def select_file(mode, runs, epochs, out):
    pl = SEL.payload(mode, runs, PROT, epochs)
    st = SEL.write_or_verify(out, pl)
    log(f"{mode} {out}: {st}")
    return json.load(open(out))


def items_for(ids_path, split, man=MAN, gtp=GTP):
    it, _ = inputs.load_items(man, gtp, ids_path, split, exact=split is not None)
    return it


def gen(out_dir, ids, split, prompts, workers, adapter=None, parent=None, man=MAN, gtp=GTP):
    """생성 완료 여부는 eval_gate.verify_gen(요청 집합·provenance·completion)로만 판단한다."""
    items = items_for(ids, split, man, gtp)
    pn = prompts.split(",")
    par = (parent, OLD_PROT) if parent else (None, None)
    try:
        eval_gate.verify_gen(out_dir, items, pn, adapter, PROT, *par)
        log(f"{out_dir}: verified complete")
        return
    except (eval_gate.GateError, FileNotFoundError) as e:
        log(f"{out_dir}: not complete/verified ({str(e)[:160]}) -> run_shards")
    wait_gpus_free()
    status("generate", out_dir=out_dir, workers=workers)
    cmd = [sys.executable, "-m", "rsna_diag.run_shards", "--manifest", man, "--ids", ids, "--out-dir", out_dir, "--protocol", PROT,
           "--prompts", prompts, "--workers", str(workers)]
    if adapter:
        cmd += ["--adapter", adapter]
    if parent:
        cmd += ["--parent-dir", parent, "--parent-protocol", OLD_PROT]
    sh(cmd)
    eval_gate.verify_gen(out_dir, items, pn, adapter, PROT, *par)


def peak_total(out_dir):
    """run_shards resource_log에서 GPU별 전체 점유(nvidia-smi memory.used, 다른 프로세스 포함) 최대."""
    mx = {}
    for ln in open(os.path.join(out_dir, "resource_log.jsonl")):
        for r in json.loads(ln)["gpus"]:
            mx[r["index"]] = max(mx.get(r["index"], 0), r["mem_used_mib"])
    return mx


def gen_check(adapter17):
    """생성 경로 점검 (development thr24). worker 수 결정은 메모리·오류·완료 기준만 사용한다 (평가 점수 미사용)."""
    dec_p = f"{R}/gen_check/decision.json"
    if os.path.exists(dec_p):
        dec = json.load(open(dec_p))
        log(f"gen_check decision exists: workers={dec['workers']}")
        return dec["workers"]
    os.makedirs(f"{R}/gen_check", exist_ok=True)
    thr_items = items_for(THR_IDS, None, THR_MAN, THR_GT)
    rep = {}
    for name, prompts, adapter in (("base_w4", "official_long,concise", None), ("sft17_w4", "concise", adapter17)):
        d = f"{R}/gen_check/{name}"
        gen(d, THR_IDS, None, prompts, 4, adapter, man=THR_MAN, gtp=THR_GT)
        last = json.load(open(os.path.join(d, "last_run.json")))
        recs = eval_gate.verify_gen(d, thr_items, prompts.split(","), adapter, PROT)
        rt = [r["runtime_s_total"] for r in recs.values()]
        rep[name] = {"n_requests": len(recs), "wall_s": last["wall_s"], "requests_per_min": len(recs) / last["wall_s"] * 60,
                     "returncodes": last["returncodes"], "gpu_total_used_max_mib": peak_total(d),
                     "worker_peak_alloc_gb_max": max(r["peak_mem_alloc_gb_max"] for r in recs.values()),
                     "max_request_runtime_s": max(rt), "max_output_tokens": max(r["n_output_tokens"] for r in recs.values()),
                     "n_cap_extended": sum(len(r["attempts"]) > 1 for r in recs.values())}
    ref = {}
    for f in glob.glob(os.path.join(THR_REF, "gen_worker*.jsonl")):
        for ln in open(f):
            if ln.strip():
                r = json.loads(ln)
                ref[(r["id"], r["prompt_name"])] = r["suffix_ids"]
    cur = eval_gate.verify_gen(f"{R}/gen_check/base_w4", thr_items, ["official_long", "concise"], None, PROT)
    same = sum(1 for k, r in cur.items() if ref.get(k) == r["suffix_ids"])
    rep["base_w4_vs_iter010_thr_w4"] = {"n_compared": sum(1 for k in cur if k in ref), "n_identical_output_tokens": same}
    mem_ok = all(v <= MEM_LIMIT_MIB for n in ("base_w4", "sft17_w4") for v in rep[n]["gpu_total_used_max_mib"].values())
    workers = 4 if mem_ok else 2
    dec = {"workers": workers, "mem_limit_mib": MEM_LIMIT_MIB, "mem_ok_for_4_workers": mem_ok, "report": rep,
           "rule": "4 workers (2 per GPU) iff every GPU's max total used <= 24576-2*2048 MiB and all requests completed without worker failure; "
                   "2-worker throughput reused from iter_010 (1.39 req/min on the same thr24 set)",
           "iter010_reference_req_per_min": {"w2": 1.39, "w4": 2.73}}
    tmp = dec_p + ".tmp"
    json.dump(dec, open(tmp, "w"), indent=1)
    os.replace(tmp, dec_p)
    log(f"gen_check: workers={workers} {json.dumps(rep)[:600]}")
    return workers


def copy_parent(src_glob, dst):
    """iter_010 base_val 부모 record의 읽기 전용 사본. 이미 있으면 원본과 sha가 같은지만 확인한다."""
    os.makedirs(dst, exist_ok=True)
    for f in sorted(glob.glob(src_glob)):
        t = os.path.join(dst, os.path.basename(f))
        h = hashlib.sha256(open(f, "rb").read()).hexdigest()
        if os.path.exists(t):
            if hashlib.sha256(open(t, "rb").read()).hexdigest() != h:
                raise RuntimeError(f"parent copy {t} differs from source {f}")
        else:
            shutil.copy2(f, t)
            os.chmod(t, 0o444)
            log(f"copied parent record file {f} -> {t}")


def main():
    os.makedirs(R, exist_ok=True)
    lk, own, _ = queue_lock.try_lock(os.path.join(os.path.realpath(R), "pipeline.lock"), queue_lock.my_info(role="pipeline"))
    if lk is None:
        sys.exit(f"another pipeline owns {R}: {own}")
    try:
        run()
    finally:
        lk.release()


def run():
    os.makedirs(f"{R}/select", exist_ok=True)
    os.makedirs(f"{R}/final", exist_ok=True)
    seed17 = [(0, "1e-4", 17), (1, "2e-4", 17)]
    d17 = [run_dir(lr, s) for _, lr, s in seed17]
    # 1-2. seed17 5 epochs, 연장 판정
    ensure_trained("seed17", seed17, 5)
    ext_p = f"{R}/select/extend.json"
    extend = select_file("extend", d17, 5, ext_p)["extend"]
    E = 8 if extend else 5
    log(f"extend={extend} -> total epochs E={E}")
    if extend:
        ensure_trained("seed17", seed17, 8)
    # 3. LR pick
    pick17 = f"{R}/select/pick_seed17.json"
    sel17 = select_file("pick", d17, E, pick17)
    lr = sel17["runs"][sel17["selected_run"]]["lr"]
    lr_s = {1e-4: "1e-4", 2e-4: "2e-4"}[lr]
    log(f"selected lr {lr_s} (seed 17 run {sel17['selected_run']}, epoch {sel17['runs'][sel17['selected_run']]['best_epoch']})")
    # 4. seeds 29, 43
    others = [(0, lr_s, 29), (1, lr_s, 43)]
    ensure_trained("seeds29_43", others, E)
    sel = {17: pick17}
    for _, _, s in others:
        p = f"{R}/select/pick_seed{s}.json"
        select_file("pick", [run_dir(lr_s, s)], E, p)
        sel[s] = p
    # 5. 생성 경로 점검 -> worker 수
    workers = gen_check(sel17["runs"][sel17["selected_run"]]["adapter_dir"])
    # 6. base validation + comparator
    par = f"{R}/base_val_parent"
    copy_parent("results/iter_010/base_val/gen_worker*.jsonl", par)
    gen(f"{R}/base_val", IDS.format("validation"), "validation", "official_long,concise", workers, parent=par)
    comp_p = f"{R}/final/comparator.json"
    pl = final_eval.comparator_payload(f"{R}/base_val", PROT, par, OLD_PROT)
    log(f"comparator {SEL.write_or_verify(comp_p, pl)}: {pl['comparator']}")
    # 7. confirm generations (선택·comparator 고정 뒤)
    status("confirm_generation")
    gen(f"{R}/confirm_base", IDS.format("confirm"), "confirm", "official_long,concise", workers)
    sft_args = []
    for s in (17, 29, 43):
        j = json.load(open(sel[s]))
        adapter = j["runs"][j["selected_run"]]["adapter_dir"]
        gen(f"{R}/confirm_sft_seed{s}", IDS.format("confirm"), "confirm", "concise", workers, adapter=adapter)
        sft_args.append(f"{s}:{sel[s]}:{R}/confirm_sft_seed{s}")
    # 8. final
    out = f"{R}/final/confirm_result.json"
    if os.path.exists(out):
        log(f"{out} exists (not overwritten)")
    else:
        sh([sys.executable, "-m", "rsna_diag.final_eval", "confirm", "--comparator", comp_p, "--extend", ext_p, "--conf-base",
            f"{R}/confirm_base", "--protocol", PROT, "--sft", *sft_args, "--out", out])
    status("complete")
    log("PIPELINE COMPLETE")


if __name__ == "__main__":
    main()
