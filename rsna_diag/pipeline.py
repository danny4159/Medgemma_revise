"""iter_011 본실험 파이프라인 (사전 고정 규칙, 재개 가능·단계별 완료 검사). 사용: python -m rsna_diag.pipeline

단계 (각 단계는 산출물이 이미 유효하면 건너뛴다; 모든 판정은 select/final_eval의 gate를 통과한 값만 쓴다):
 1. seed17 두 LR을 5 epochs까지 (GPU당 학습 1개; 이미 train.lock을 잡은 실행이 있으면 종료를 기다린다)
 2. select extend: 어느 LR이라도 사전 규칙을 만족하면 두 LR 모두 8 epochs로 연장
 3. select pick(seed17 두 run) -> LR 고정, 총 epoch E 고정
 4. seed 29, 43을 선택 LR/E로 학습 (GPU0: seed29, GPU1: seed43), seed별 pick
 5. base validation 생성(부모 133행 검증 후 연결, 나머지 신규) -> comparator 고정 (확인 결과를 보기 전에)
 6. confirm base(official_long/concise x 800) + SFT 3 seed(concise x 800) 생성 (run_shards 2 GPU x 2 worker)
 7. final_eval confirm
어느 단계든 실패하면 예외로 중단한다 (성공으로 넘기지 않는다). 재실행하면 완료된 단계는 건너뛰고 이어간다.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import time

from . import queue_lock

R = "results/iter_011"
PROT = f"{R}/protocols/main_protocol.json"
OLD_PROT = "results/iter_010/protocols/main_protocol.json"
MAN = "results/iter_010/manifests/infer_manifest.jsonl"
IDS = "results/iter_010/manifests/{}_ids.json"
LOG = f"{R}/pipeline.log"
WORKERS = 4  # 2 GPU x 2 worker: iter_010 실측(24명x2 prompt)에서 2 worker 대비 처리량 약 1.97배, 출력 일치


def log(msg):
    line = f"[{time.strftime('%F %T')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def sh(cmd, check=True):
    log("RUN " + " ".join(cmd))
    p = subprocess.run(cmd)
    log(f"rc={p.returncode}")
    if check and p.returncode != 0:
        raise RuntimeError(f"command failed rc={p.returncode}: {' '.join(cmd)}")
    return p.returncode


def wait_unlocked(run_dirs):
    """실행 중인 학습(run-dir train.lock 보유)이 끝날 때까지 기다린다. lock을 빼앗지 않는다."""
    while True:
        busy = []
        for d in run_dirs:
            lp = os.path.join(d, "train.lock")
            if os.path.exists(lp):
                lk, own, _ = queue_lock.try_lock(lp, queue_lock.my_info(role="pipeline_probe"))
                if lk is None:
                    busy.append((d, own))
                else:
                    lk.release()
        if not busy:
            return
        log(f"waiting for live train owners: {busy}")
        time.sleep(120)


def has_epoch(d, e):
    return os.path.exists(f"{d}/epoch_{e:02d}/val_metrics.json")


def train_jobs(name, runs, epochs, migrations=None):
    """runs: [(gpu, lr, seed)]. launch.py로 동시에 학습하고 종료 코드를 모두 확인한다."""
    jobs = []
    for gpu, lr, seed in runs:
        d = f"{R}/train/lr{lr}_s{seed}"
        args = ["--run-dir", d, "--lr", lr, "--seed", str(seed), "--epochs", str(epochs), "--protocol", PROT, "--microbatch", "2"]
        if migrations and (lr, seed) in migrations:
            args += ["--migration", migrations[(lr, seed)]]
        jobs.append({"gpu": str(gpu), "module": "rsna_diag.train", "log": f"{d}.log", "args": args})
    jp = f"{R}/train/jobs_{name}.json"
    json.dump(jobs, open(jp, "w"), indent=1)
    sh([sys.executable, "-m", "rsna_diag.launch", "--jobs", jp, "--log-dir", f"{R}/train/launch_{name}"])


def ensure_trained(name, runs, epochs, migrations=None):
    dirs = [f"{R}/train/lr{lr}_s{seed}" for _, lr, seed in runs]
    wait_unlocked(dirs)
    if all(has_epoch(d, epochs) for d in dirs):
        log(f"{name}: all runs already have epoch {epochs} validation")
        return
    train_jobs(f"{name}_e{epochs}", runs, epochs, migrations)
    if not all(has_epoch(d, epochs) for d in dirs):
        raise RuntimeError(f"{name}: epoch {epochs} validation missing after training")


def gen(out_dir, ids, prompts, adapter=None, parent=None):
    comp = f"{out_dir}/completion.json"
    if os.path.exists(comp):
        log(f"{out_dir}: completion exists")
        return
    cmd = [sys.executable, "-m", "rsna_diag.run_shards", "--manifest", MAN, "--ids", ids, "--out-dir", out_dir, "--protocol", PROT,
           "--prompts", prompts, "--workers", str(WORKERS)]
    if adapter:
        cmd += ["--adapter", adapter]
    if parent:
        cmd += ["--parent-dir", parent, "--parent-protocol", OLD_PROT]
    sh(cmd)
    if not os.path.exists(comp):
        raise RuntimeError(f"{out_dir}: no completion.json after run_shards")


def main():
    os.makedirs(R, exist_ok=True)
    mig = {("1e-4", 17): f"{R}/recovery/migration_lr1e-4_s17.json", ("2e-4", 17): f"{R}/recovery/migration_lr2e-4_s17.json"}
    seed17 = [(0, "1e-4", 17), (1, "2e-4", 17)]
    d17 = [f"{R}/train/lr{lr}_s17" for _, lr, _ in seed17]
    # 1. seed17, 5 epochs
    ensure_trained("seed17", seed17, 5, mig)
    # 2. extend?
    ext_p = f"{R}/select/extend.json"
    os.makedirs(f"{R}/select", exist_ok=True)
    if not os.path.exists(ext_p):
        sh([sys.executable, "-m", "rsna_diag.select", "extend", "--runs", *d17, "--epochs", "5", "--protocol", PROT, "--out", ext_p])
    extend = json.load(open(ext_p))["extend"]
    E = 8 if extend else 5
    log(f"extend={extend} -> total epochs E={E}")
    if extend:
        ensure_trained("seed17", seed17, 8, mig)
    # 3. LR pick (seed 17)
    pick17 = f"{R}/select/pick_seed17.json"
    if not os.path.exists(pick17):
        sh([sys.executable, "-m", "rsna_diag.select", "pick", "--runs", *d17, "--epochs", str(E), "--protocol", PROT, "--out", pick17])
    sel17 = json.load(open(pick17))
    lr = sel17["runs"][sel17["selected_run"]]["lr"]
    lr_s = {1e-4: "1e-4", 2e-4: "2e-4"}[lr]
    log(f"selected lr {lr_s} (seed 17 run {sel17['selected_run']}, epoch {sel17['runs'][sel17['selected_run']]['best_epoch']})")
    # 4. seeds 29, 43
    others = [(0, lr_s, 29), (1, lr_s, 43)]
    ensure_trained("seeds29_43", others, E)
    sel = {17: pick17}
    for _, _, s in others:
        d = f"{R}/train/lr{lr_s}_s{s}"
        p = f"{R}/select/pick_seed{s}.json"
        if not os.path.exists(p):
            sh([sys.executable, "-m", "rsna_diag.select", "pick", "--runs", d, "--epochs", str(E), "--protocol", PROT, "--out", p])
        sel[s] = p
    # seed17: 선택 LR run의 checkpoint만 확인 대상 (pick17의 selected_run이 이미 그 run)
    # 5. base validation + comparator
    par = f"{R}/base_val/parent"
    if not os.path.exists(par):
        os.makedirs(par)
        for f in sorted(glob.glob("results/iter_010/base_val/gen_worker*.jsonl")):
            dst = os.path.join(par, os.path.basename(f))
            shutil.copy2(f, dst)
            os.chmod(dst, 0o444)
        log("copied iter_010 base_val parent records (read-only copies)")
    gen(f"{R}/base_val", IDS.format("validation"), "official_long,concise", parent=par)
    comp_p = f"{R}/final/comparator.json"
    os.makedirs(f"{R}/final", exist_ok=True)
    if not os.path.exists(comp_p):
        sh([sys.executable, "-m", "rsna_diag.final_eval", "comparator", "--val-base", f"{R}/base_val", "--protocol", PROT,
            "--parent-dir", par, "--parent-protocol", OLD_PROT, "--out", comp_p])
    # 6. confirm generations
    gen(f"{R}/confirm_base", IDS.format("confirm"), "official_long,concise")
    sft_args = []
    for s in (17, 29, 43):
        j = json.load(open(sel[s]))
        adapter = j["runs"][j["selected_run"]]["adapter_dir"]
        gen(f"{R}/confirm_sft_seed{s}", IDS.format("confirm"), "concise", adapter=adapter)
        sft_args.append(f"{s}:{sel[s]}:{R}/confirm_sft_seed{s}")
    # 7. final
    out = f"{R}/final/confirm_result.json"
    if not os.path.exists(out):
        sh([sys.executable, "-m", "rsna_diag.final_eval", "confirm", "--comparator", comp_p, "--conf-base", f"{R}/confirm_base",
            "--protocol", PROT, "--sft", *sft_args, "--out", out])
    log("PIPELINE COMPLETE")


if __name__ == "__main__":
    main()
