"""iter_048 mg45_launch.py 보완 검사 (실제 프로세스 fixture): (c) barrier 전 child 사망 -> launcher가 자기 child만 종료하고 실패로 끝남,
(a) 기존 launch_protocol과 다른 config로 같은 out-dir 재호출 -> 거부(기존 파일 불변), (b) 같은 out-dir 동시 launcher -> 거부.
GPU 1장(물리 --gpu 인자)을 사용한다. 결과: results/iter_048/tests/launch_tests.json (덮어쓰기 거부).
python pg48_launchtests.py --gpu 1 --out results/iter_048/tests/launch_tests.json
"""
import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time

CKPT = "results/iter_046/train/U/weights_e5.pth"
BASE = ["python", "mg45_launch.py", "--set", "D24", "--ckpt", "A_final", "--ckpt-path", CKPT, "--workers", "2", "--batch", "4", "--post-thr", "0.8", "--warmup-d8", "--barrier"]


def children(pid):
    out = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True).stdout.split()
    return [int(x) for x in out]


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpu", default="1")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("exists")
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=a.gpu)
    root = "results/iter_048/tests/launch"
    res = {}
    # (c) barrier 전 child 사망
    dc = f"{root}/c_child_death"
    p = subprocess.Popen(BASE + ["--gpus", a.gpu, "--out-dir", dc, "--peak-gb", "4"], env=env, stdout=open(f"{root}_c.stdout", "w"), stderr=subprocess.STDOUT)
    victim = None
    t0 = time.time()
    while time.time() - t0 < 60 and victim is None:
        ch = children(p.pid)
        if len(ch) >= 2:
            victim = ch[1]
        time.sleep(0.5)
    all_children = children(p.pid)
    os.kill(victim, signal.SIGKILL)
    t_kill = time.time()
    try:
        rc = p.wait(timeout=180)
        hung = False
    except subprocess.TimeoutExpired:
        rc, hung = None, True
        p.kill()
    left = [c for c in all_children if alive(c)]
    partial = [f for f in os.listdir(dc) if f.startswith("partial_")]
    pj = json.load(open(os.path.join(dc, partial[0]))) if partial else {}
    res["c_child_death_before_barrier"] = {"launcher_rc": rc, "hung": hung, "seconds_to_exit_after_kill": time.time() - t_kill, "leftover_child_pids": left,
                                           "partial_json_aborted_field": pj.get("aborted"), "no_completion": not os.path.exists(os.path.join(dc, "completion.json")),
                                           "ok": rc not in (0, None) and not hung and not left and bool(pj.get("aborted")) and not os.path.exists(os.path.join(dc, "completion.json"))}
    # (a) config mismatch on same out-dir (batch 4 -> 2)
    lp = os.path.join(dc, "launch_protocol.json")
    before = hashlib.sha256(open(lp, "rb").read()).hexdigest()
    cmd = [x if x != "4" else "2" for x in BASE]
    r = subprocess.run(cmd + ["--gpus", a.gpu, "--out-dir", dc, "--peak-gb", "4"], env=env, capture_output=True, text=True, timeout=120)
    res["a_config_mismatch_rejected"] = {"rc": r.returncode, "message": (r.stderr + r.stdout)[-200:], "launch_protocol_unchanged": hashlib.sha256(open(lp, "rb").read()).hexdigest() == before,
                                         "ok": r.returncode != 0 and "config mismatch" in (r.stderr + r.stdout) and hashlib.sha256(open(lp, "rb").read()).hexdigest() == before}
    # (b) 동시 launcher
    db = f"{root}/b_concurrent"
    p1 = subprocess.Popen(BASE + ["--gpus", a.gpu, "--out-dir", db, "--peak-gb", "4"], env=env, stdout=open(f"{root}_b.stdout", "w"), stderr=subprocess.STDOUT)
    time.sleep(8)
    r2 = subprocess.run(BASE + ["--gpus", a.gpu, "--out-dir", db, "--peak-gb", "4"], env=env, capture_output=True, text=True, timeout=120)
    rc1 = p1.wait(timeout=600)
    comp = os.path.exists(os.path.join(db, "completion.json"))
    res["b_concurrent_launcher_rejected"] = {"second_rc": r2.returncode, "message": (r2.stderr + r2.stdout)[-200:], "first_launcher_rc": rc1, "first_completed": comp,
                                             "ok": r2.returncode != 0 and "another launcher" in (r2.stderr + r2.stdout) and rc1 == 0 and comp}
    res["all_ok"] = all(v["ok"] for v in res.values() if isinstance(v, dict))
    res["mg45_launch_sha256"] = hashlib.sha256(open("mg45_launch.py", "rb").read()).hexdigest()
    json.dump(res, open(a.out, "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
