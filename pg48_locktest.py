"""iter_048 학습 run-dir 배타 lock 검사: 다른 live 프로세스가 같은 run-dir lock을 잡고 있을 때 pg48_train.py train이 모델 로딩 전에 거부하는지 확인한다 (GPU 불필요).
python pg48_locktest.py --out results/iter_048/tests/lock_test.json
"""
import argparse
import json
import os
import subprocess
import sys
import time

from rsna_diag import queue_lock


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("exists")
    d = "results/iter_048/tests/lock_run"
    os.makedirs(d, exist_ok=True)
    lk, own, rec = queue_lock.try_lock(os.path.join(os.path.realpath(d), "train.lock"), queue_lock.my_info(role="locktest_holder"))
    assert lk is not None
    t0 = time.time()
    r = subprocess.run([sys.executable, "pg48_train.py", "train", "--run-dir", d, "--protocol", "results/iter_048/protocol/train_protocol_v1.json", "--mode", "joint",
                        "--init-adapter", "results/iter_040/train2/C_s17/epoch_03", "--epochs", "1", "--max-patients", "8"], capture_output=True, text=True, timeout=300)
    dt = time.time() - t0
    lk.release()
    out = {"second_trainer_rc": r.returncode, "seconds": dt, "message": (r.stderr + r.stdout)[-250:],
           "ok": r.returncode != 0 and "owned by another live process" in (r.stderr + r.stdout) and dt < 60 and not os.path.exists(os.path.join(d, "train_config.json"))}
    json.dump(out, open(a.out, "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
