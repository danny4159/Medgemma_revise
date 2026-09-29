"""본학습 epoch checkpoint 평가 감시 실행기 (natten_py310 env, GPU 1장).

계획 일정: V100 epoch 6/12/18/22/26(연장 시 32/38), V400 epoch 12/26(연장 시 38). 학습 프로세스와 다른 GPU에서
immutable epoch model(epoch_XX/model.pt, 원자 저장)을 평가한다. 각 model.pt의 update_idx·config·source·input digest를
학습 run_config.json과 대조한 뒤 det_eval.py run(→completion)과 scan을 실행한다. 이미 완료된 평가는 completion을 재검증해
건너뛴다. 학습이 target에 도달하지 못한 채 끝나면(학습 프로세스 종료·complete.json 없음) 오류로 종료한다.
"""
import argparse
import json
import os
import subprocess
import sys
import time

import torch

BASE = "/SSD1_1TB/home/milab/daniel/08_medgemma/research"
EVAL = f"{BASE}/rsna_diag/det_eval.py"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run_dir", required=True)
    ap.add_argument("--out_root", required=True)
    ap.add_argument("--jobs", nargs="+", required=True, help="epoch:manifest, 예 6:V100 12:V400")
    ap.add_argument("--batch_size", type=int, default=4)
    ap.add_argument("--n_workers", type=int, default=1)
    ap.add_argument("--worker_gpus", default="0")
    ap.add_argument("--train_pid_file", default=None)
    a = ap.parse_args()
    jobs = [(int(x.split(":")[0]), x.split(":")[1]) for x in a.jobs]
    os.makedirs(a.out_root, exist_ok=True)
    t_wait = time.time()
    while not os.path.exists(os.path.join(a.run_dir, "run_config.json")):
        if time.time() - t_wait > 1800:
            raise RuntimeError("training run_config.json did not appear")
        time.sleep(10)
    rc_cfg = json.load(open(os.path.join(a.run_dir, "run_config.json")))
    upe = rc_cfg["updates_per_epoch"]
    log = open(os.path.join(a.out_root, "watch.log"), "a")
    for ep, man in jobs:
        mp = os.path.join(a.run_dir, f"epoch_{ep:02d}", "model.pt")
        while not os.path.exists(mp):
            # 연장(--extend) 중에는 이전 완료 marker가 남아 있으므로, 완료 update가 이 epoch 이상일 때만 누락으로 본다.
            cp = os.path.join(a.run_dir, "complete.json")
            if os.path.exists(cp) and json.load(open(cp))["total_updates"] >= ep * upe and not os.path.exists(mp):
                raise RuntimeError(f"training complete but {mp} missing")
            time.sleep(30)
        meta = torch.load(mp, map_location="cpu", weights_only=False)
        chk = {"update_idx": meta.get("update_idx") == ep * upe, "config": meta.get("config_digest") == rc_cfg["config_digest"],
               "source": meta.get("source_digest") == rc_cfg["source_digest"], "input": meta.get("input_digest") == rc_cfg["input_digest"]}
        del meta
        if not all(chk.values()):
            raise RuntimeError(f"epoch {ep} model metadata mismatch: {chk}")
        out = os.path.join(a.out_root, f"{man}_e{ep:02d}")
        t0 = time.time()
        rc = subprocess.run([sys.executable, EVAL, "run", "--manifest", man, "--checkpoint", mp, "--out_dir", out,
                             "--batch_size", str(a.batch_size), "--n_workers", str(a.n_workers), "--worker_gpus", a.worker_gpus]).returncode
        if rc != 0:
            raise RuntimeError(f"eval run failed epoch {ep} {man} rc={rc}")
        if not os.path.exists(os.path.join(out, "threshold_scan.json")):
            rc = subprocess.run([sys.executable, EVAL, "scan", "--out_dir", out, "--manifest", man]).returncode
            if rc != 0:
                raise RuntimeError(f"scan failed epoch {ep} {man} rc={rc}")
        log.write(json.dumps({"epoch": ep, "manifest": man, "checks": chk, "wall_s": time.time() - t0, "t": time.time()}) + "\n")
        log.flush()
    print(json.dumps({"done": True, "jobs": a.jobs}))


if __name__ == "__main__":
    main()
