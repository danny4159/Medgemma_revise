"""iter_046 실행 driver (기본 python). 각 단계는 재개 가능한 단위이며 이미 완료·검증된 산출물은 건너뛴다.

  lock                         학습 전 protocol 잠금 (write-once)
  train --trajs S,U --to N     학습 trajectory들을 병렬(GPU당 1 프로세스, 허용 GPU 집합 안에서 여유 큰 순) 로 epoch N까지
  evald24 --trajs S,U --epoch N   checkpoint weights_eN을 D24에서 평가(공식 inference 경로 mg45_launch/worker, 장치 병렬)
GPU 배정은 상속된 CUDA_VISIBLE_DEVICES 안에서만 한다. 병렬화는 가설·표본·selection 규칙을 바꾸지 않는다.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(HERE, "results", "environments", "medgrounder_iter045", "bin", "python")
ROOT = "results/iter_046"
MICROBATCH = 8
SAVE_EPOCHS = {5: "2,5", 15: "10,15", 30: "20,25,30"}
LOCK_FILES = ["mg46_train.py", "mg46_gates.py", "mg46_run.py", "mg46_eval.py", "mg46_vrun.py", "mg45_mg.py", "mg45_worker.py", "mg45_launch.py", "mg45_eval.py", "pg39_spec.py",
              "rsna_diag/metrics.py", "rsna_diag/parse.py", "rsna_diag/geometry.py", "rsna_diag/__init__.py", "results/iter_043/data/manifest_private.json",
              "results/iter_040/data/manifest_train_private.jsonl", "results/iter_040/data/selection_lock.json", "results/iter_045/external/code_manifest.json",
              "results/iter_045/external/weights/weights_manifest.json", "results/iter_045/external/text_encoder_manifest.json",
              "results/iter_045/external/weights/medgrounder_pretrain_imagenome.pth", "results/iter_045/decisions/D24_select.json",
              "agent_plan_md", "agent_plan_json",
              "results/iter_046/tests/gate_data_v2.json", "results/iter_046/tests/gate_matcher.json", "results/iter_046/tests/gate_aug.json",
              "results/iter_046/tests/gate_accum_v3.json", "results/iter_046/tests/gate_accum_fp64.json", "results/iter_046/tests/gate_step.json",
              "results/iter_046/tests/gate_overfit.json", "results/iter_046/tests/gate_throughput_fp32.json", "results/iter_046/tests/gate_throughput_bf16.json",
              "results/iter_046/tests/resume/resume_compare.json", "results/iter_046/tests/regress_P_vs_iter045.json", "results/iter_046/tests/regress_P_vs_iter045_final_worker.json",
              "results/iter_046/tests/lock_test/lock_result.json", "results/iter_046/protocol/mg45_amendment.json", "results/iter_046/protocol/mg45_amendment_v2.json"]
PLAN = {"agent_plan_md": "../agent/runs/iter_046/plan.md", "agent_plan_json": "../agent/runs/iter_046/plan.json"}


def fsha(p):
    p = PLAN.get(p, p)
    h = hashlib.sha256()
    with open(os.path.join(HERE, p), "rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


def gpu_free():
    r = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,memory.total", "--format=csv,noheader,nounits"], capture_output=True, text=True, check=True)
    return {int(l.split(",")[0]): int(l.split(",")[2]) - int(l.split(",")[1]) for l in r.stdout.strip().splitlines()}


def allowed_gpus():
    cv = os.environ.get("CUDA_VISIBLE_DEVICES")
    if not cv:
        sys.exit("CUDA_VISIBLE_DEVICES not set")
    return [int(x) for x in cv.split(",")]


def assign(n, need_mib):
    free = gpu_free()
    gp = sorted(allowed_gpus(), key=lambda g: (-free[g], g))
    mp = {k: gp[k % len(gp)] for k in range(n)}
    per = {}
    for k, g in mp.items():
        per[g] = per.get(g, 0) + 1
    for g, c in per.items():
        if free[g] < c * (need_mib + 2048):
            sys.exit(f"gpu {g} free {free[g]} MiB < {c}x({need_mib}+2048)")
    return mp, free


def cmd_lock(a):
    p = f"{ROOT}/protocol/protocol_lock.json"
    if os.path.exists(os.path.join(HERE, p)):
        sys.exit("protocol lock exists")
    git_head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    lock = {"locked_at": time.time(), "git_head_at_lock": git_head, "files": {f: fsha(f) for f in LOCK_FILES},
            "env": {"python": PY, "pip_freeze_sha256": fsha("results/iter_045/env/pip_freeze_after_extra.txt"),
                    "official_repo_revision": "a0aad98d67018838fe160acbe1f7c3851fddeacc", "text_encoder_revision": "c3648aa87af95837c809e6f0c5f85d08160db437"},
            "training": {"init": "MG-P pretrain_imagenome (strict)", "seed": 17, "trajs": {"S": "base/backbone 1e-5, text 5e-5 (official base.yaml)", "U": "all groups 1e-5 (paper)"},
                         "optimizer": "AdamW betas(0.9,0.999) eps1e-8 wd1e-4 clip0.1", "effective_batch": 32, "microbatch": MICROBATCH, "precision": "fp32 (bf16 loss differed 7% at init; no speed gain)",
                         "horizon_epochs": 15, "warmup_frac": 0.01, "steps_per_epoch": 20, "phase1_epochs": 5, "phase1_eval_epochs": [2, 5], "phase2_epochs": 15, "phase2_eval_epochs": [10, 15],
                         "supp": "optimizer state kept, LR 0.5x peak -> 0 linear over 15 epochs, eval 20/25/30; only if supp rule", "loss": "official groundability CE 1 + L1 5 + GIoU 2, eos 0.1, matcher 1/5/2 (strict)"},
            "selection_rules_source": "mg46_eval.py docstring (locked file hash)", "thresholds": [0.2, 0.4, 0.6, 0.8], "fixed_threshold": 0.4,
            "branch": "after phase1 select trajectory by rank; continue to 15; supp iff mg46_eval supp rule; V96 only after final_selection.json",
            "plan_sha_note": "plan.md/plan.json are agent files hashed above"}
    os.makedirs(os.path.dirname(os.path.join(HERE, p)), exist_ok=True)
    json.dump(lock, open(os.path.join(HERE, p), "x"), indent=1)
    print("locked", len(lock["files"]), "files")


def check_lock():
    lock = json.load(open(os.path.join(HERE, f"{ROOT}/protocol/protocol_lock.json")))
    bad = [f for f, h in lock["files"].items() if fsha(f) != h]
    if bad:
        sys.exit(f"locked file changed: {bad}")
    return lock


def cfg_of(traj):
    return {"S": "S", "U": "U"}[traj]


def cmd_train(a):
    check_lock()
    trajs = a.trajs.split(",")
    save = SAVE_EPOCHS[a.to]
    mp, free = assign(len(trajs), 10 * 1024)
    procs = {}
    for k, tj in enumerate(trajs):
        out = f"{ROOT}/train/{tj}"
        done = os.path.join(HERE, out, f"reached_epoch{a.to}.json")
        if os.path.exists(done):
            print(tj, "already reached", a.to)
            continue
        cmd = [PY, "mg46_train.py", "train", "--traj", tj, "--out", out, "--lr-cfg", cfg_of(tj), "--target-epoch", str(a.to), "--save-epochs", save,
               "--microbatch", str(MICROBATCH), "--ckpt-every", "10"]
        if a.supp:
            cmd.append("--supp")
        log = os.path.join(HERE, ROOT, "logs", f"train_{tj}_to{a.to}_{int(time.time())}.log")
        os.makedirs(os.path.dirname(log), exist_ok=True)
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(mp[k]))
        procs[tj] = (subprocess.Popen(cmd, cwd=HERE, env=env, stdout=open(log, "wb"), stderr=subprocess.STDOUT), log, mp[k])
        print("started", tj, "gpu", mp[k], "free MiB before", free[mp[k]], "log", log, flush=True)
    t0 = time.time()
    rl = open(os.path.join(HERE, ROOT, "logs", f"resource_train_to{a.to}_{int(t0)}.jsonl"), "a")
    while any(p.poll() is None for p, _, _ in procs.values()):
        time.sleep(15)
        used = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,utilization.gpu", "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout.strip().splitlines()
        rl.write(json.dumps({"t": round(time.time() - t0, 1), "gpu": used}) + "\n")
        rl.flush()
    rcs = {tj: p.wait() for tj, (p, _, _) in procs.items()}
    print("rc", rcs, "wall", round(time.time() - t0, 1))
    for tj, (p, log, g) in procs.items():
        lines = open(log, errors="replace").read().replace("\r", "\n").splitlines()
        print(tj, "|", " | ".join(l for l in lines if l.startswith("epoch") or "ERROR" in l or "resumed" in l))
    if any(rc != 0 for rc in rcs.values()):
        sys.exit(1)


def cmd_evald24(a):
    check_lock()
    trajs = a.trajs.split(",")
    todo = []
    for tj in trajs:
        label = f"A_{tj}_e{a.epoch}"
        d = os.path.join(HERE, ROOT, "eval_d24", label)
        if os.path.exists(os.path.join(d, "completion.json")):
            print(label, "completion exists")
            continue
        todo.append((tj, label))
    mp, free = assign(max(len(todo), 1), 4 * 1024)
    procs = []
    for k, (tj, label) in enumerate(todo):
        w = f"{ROOT}/train/{tj}/weights_e{a.epoch}.pth"
        cmd = [sys.executable, "mg45_launch.py", "--set", "D24", "--ckpt", label, "--ckpt-path", w, "--out-dir", f"{ROOT}/eval_d24/{label}", "--workers", "1",
               "--gpus", str(mp[k]), "--batch", "4", "--peak-gb", "4"]
        log = os.path.join(HERE, ROOT, "logs", f"evald24_{label}_{int(time.time())}.log")
        procs.append((label, subprocess.Popen(cmd, cwd=HERE, env=dict(os.environ), stdout=open(log, "wb"), stderr=subprocess.STDOUT), log))
        print("started", label, "gpu", mp[k], flush=True)
    bad = False
    for label, p, log in procs:
        rc = p.wait()
        print(label, "rc", rc, open(log).read().strip().splitlines()[-1:])
        bad |= rc != 0
    if bad:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("lock")
    t = sub.add_parser("train")
    t.add_argument("--trajs", required=True)
    t.add_argument("--to", type=int, required=True, choices=[5, 15, 30])
    t.add_argument("--supp", action="store_true")
    e = sub.add_parser("evald24")
    e.add_argument("--trajs", required=True)
    e.add_argument("--epoch", type=int, required=True)
    a = ap.parse_args()
    {"lock": cmd_lock, "train": cmd_train, "evald24": cmd_evald24}[a.cmd](a)


if __name__ == "__main__":
    main()
