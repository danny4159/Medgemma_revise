"""iter_054 기술 단계 실행 orchestrator (backgrounding 없이 subprocess로 순차 실행).
 1) protocol_tech 생성(코드·자료 잠금) 2) ref_w2: GPU당 worker 1개(총 2) 3) cmp_w4: GPU당 worker 2개(총 4)
 4) resume: worker 2개로 시작 → ≥N record 시점에 SIGKILL → 찢어진 행 주입 → worker 3개로 재개(매핑 변경)
각 실행은 같은 tech 요청 252건·같은 protocol을 쓴다. 정확도는 보지 않는다."""
import json
import os
import signal
import subprocess
import sys
import time

REQ = "results/iter_054/data/requests.jsonl"
PROTO = "results/iter_054/protocol/protocol_tech.json"
PEAK = "9.0"


def launch(out, workers, extra=()):
    cmd = [sys.executable, "mc54_run.py", "launch", "--stage", "tech", "--requests", REQ, "--protocol", PROTO, "--out-dir", out,
           "--workers", str(workers), "--peak-gb", PEAK, *extra]
    t = time.time()
    r = subprocess.run(cmd)
    return {"cmd": cmd, "rc": r.returncode, "wall_s": time.time() - t}


def n_records(out):
    import glob
    n = 0
    for f in glob.glob(os.path.join(out, "gen_worker*.jsonl")):
        n += sum(1 for l in open(f, "rb").read().split(b"\n")[:-1] if l.strip())
    return n


def main():
    log = {}
    if not os.path.exists(PROTO):
        subprocess.run([sys.executable, "mc54_run.py", "protocol", "--stage", "tech", "--requests", REQ, "--out", PROTO], check=True)
    which = sys.argv[1]
    if which == "ref_w2":
        log[which] = launch("results/iter_054/raw/tech_ref_w2", 2)
    elif which == "cmp_w4":
        log[which] = launch("results/iter_054/raw/tech_cmp_w4", 4)
    elif which == "resume":
        out = "results/iter_054/raw/tech_resume"
        cmd = [sys.executable, "mc54_run.py", "launch", "--stage", "tech", "--requests", REQ, "--protocol", PROTO, "--out-dir", out,
               "--workers", "2", "--peak-gb", PEAK]
        p = subprocess.Popen(cmd, start_new_session=True)
        t0 = time.time()
        while p.poll() is None and n_records(out) < 60 and time.time() - t0 < 900:
            time.sleep(1)
        killed_at = n_records(out)
        os.killpg(p.pid, signal.SIGKILL)  # launcher와 worker 전체
        p.wait()
        time.sleep(3)
        # 찢어진 부분 행 주입 (SIGKILL이 write 도중이 아니었을 수 있으므로 시뮬레이션): worker0 파일 끝에 개행 없는 조각
        w0 = os.path.join(out, "gen_worker0.jsonl")
        if os.path.exists(w0):
            with open(w0, "ab") as f:
                f.write(b'{"request_id": "torn_partial_row", "kind": "g')
        log[which] = {"killed_at_records": killed_at, "records_after_kill": n_records(out), "torn_injected": os.path.exists(w0)}
        log[which]["resume_launch"] = launch(out, 3)
        # 같은 out-dir에서 launcher.lock 은 flock이라 이전 launcher 종료로 자동 해제
    else:
        sys.exit("arg: ref_w2|cmp_w4|resume")
    json.dump(log, open(f"results/iter_054/raw/tech_runlog_{which}.json", "x"), indent=1)
    print(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
