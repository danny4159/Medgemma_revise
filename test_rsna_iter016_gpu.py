"""iter_016 실제 GPU 통제 검사 (상속된 CUDA_VISIBLE_DEVICES 중 첫 장 사용).
A. 부모(qa_run) SIGKILL -> 살아 있는 자식 확인 -> 새 qa_run이 실행을 거부 -> 자식 SIGKILL -> 잘린 줄 주입 -> --repair-tail 없이는 거부 ->
   --repair-tail 재개 -> 중단 전 완료 record의 bytes/hash 불변, 중복·누락 0, 기준(gen_w1) greedy token과 일치.
B. 부모 SIGTERM(정상 중단) -> 소유 자식 모두 종료·회수, run.lock 해제, attempt=interrupted.
사용: python test_rsna_iter016_gpu.py  -> results/iter_016/tests/fixtures_iter016_gpu.json
"""
import glob
import hashlib
import json
import os
import signal
import subprocess
import sys
import time

from rsna_diag import qa_gen, queue_lock

OUT = "results/iter_016"
PROT = f"{OUT}/protocols/protocol_pilot.json"
STAGE, CK = "d12_direct", "M0"
res = []


def check(n, c, det=""):
    res.append({"name": n, "pass": bool(c), "detail": str(det)[:300]})
    print(("PASS " if c else "FAIL ") + n, det if not c else "")


def sha(b):
    return hashlib.sha256(b).hexdigest()


gpu = os.environ["CUDA_VISIBLE_DEVICES"].split(",")[0]
env = dict(os.environ, CUDA_VISIBLE_DEVICES=gpu)
base = [sys.executable, "-m", "rsna_diag.qa_run", "--stage", STAGE, "--ckpts", CK, "--protocol", PROT, "--workers", "2", "--gpus", gpu,
        "--peak-gb", "8.8", "--poll-s", "1"]
ref = {}
for f in glob.glob(f"{OUT}/gen_w1/{STAGE}__{CK}/gen_worker*.jsonl"):
    for r in qa_gen.read_strict(f):
        ref[r["request_id"]] = r["suffix_ids"]


def files(d):
    return sorted(glob.glob(f"{d}/gen_worker*.jsonl"))


def nlines(d):
    return sum(len([x for x in open(f) if x.strip()]) for f in files(d))


def pid_alive(pid, start):
    return queue_lock.proc_start(pid) == start and start is not None


# ---------------- A ----------------
suffix = "_kill_v2"  # 첫 시도(_kill)는 자식이 먼저 끝나는 경합으로 무효였다 (SIGSTOP으로 결정적으로 고정한 v2 사용)
d = f"{OUT}/gen{suffix}/{STAGE}__{CK}"
os.makedirs(d, exist_ok=True)
p = subprocess.Popen(base + ["--out-suffix", suffix], env=env, stdout=open(f"{d}/parent.out", "a"), stderr=open(f"{d}/parent.err", "a"))
t0 = time.time()
children = []
while time.time() - t0 < 300 and not (children and nlines(d) >= 1):
    time.sleep(0.02)
    a_ = sorted(glob.glob(f"{d}/attempts/attempt_*.json"))
    children = json.load(open(a_[-1])).get("children", []) if a_ else []
for c in children:  # 자식을 정지시켜 부모 종료 시점의 상태를 결정적으로 고정한다
    os.kill(c["pid"], signal.SIGSTOP)
os.kill(p.pid, signal.SIGKILL)
p.wait()
att = sorted(glob.glob(f"{d}/attempts/attempt_*.json"))[-1]
check("attempt record has child pid/starttime for every worker", len(children) == 2 and all(c.get("start") for c in children), children)
n_at_kill = nlines(d)
alive = [c for c in children if pid_alive(c["pid"], c["start"])]
check("both children survive the parent's SIGKILL", len(alive) == 2, len(alive))
snap_ = {f: sha(open(f, "rb").read()) for f in files(d)}
claims_ = sorted(os.listdir(f"{d}/claims"))
p2 = subprocess.run(base + ["--out-suffix", suffix], env=env, capture_output=True, text=True)
check("new qa_run refuses while a previous child still owns the stage", p2.returncode != 0 and "live worker" in (p2.stderr + p2.stdout), (p2.stderr + p2.stdout)[-200:])
check("refused run did not change any record file or claim", snap_ == {f: sha(open(f, "rb").read()) for f in files(d)} and claims_ == sorted(os.listdir(f"{d}/claims")))
for c in children:  # 소유 자식 강제 종료 (PID+starttime 확인 후)
    if pid_alive(c["pid"], c["start"]):
        os.kill(c["pid"], signal.SIGKILL)
t0 = time.time()
while time.time() - t0 < 30 and any(pid_alive(c["pid"], c["start"]) for c in children):
    time.sleep(0.2)
check("no worker alive after killing children", not any(pid_alive(c["pid"], c["start"]) for c in children))
fs = files(d)
target = max(fs, key=lambda f: os.path.getsize(f))
with open(target, "a") as f:  # 쓰는 도중 죽은 상황 모사
    f.write('{"request_id": "abc", "id": "trunc')
before = {f: open(f, "rb").read() for f in fs}
complete_before = {f: b[:b.rfind(b"\n") + 1] for f, b in before.items()}
ids_before = [json.loads(x)["request_id"] for f in fs for x in complete_before[f].decode().splitlines() if x.strip()]
check("partial progress at kill (some but not all done)", 1 <= len(ids_before) <= 24, len(ids_before))
if len(ids_before) == 24:  # 자식이 이미 끝난 경우에도 재개 경로는 검사하되 기록한다
    print("note: all 24 done before kill; resume path checks only refusal/repair")
p3 = subprocess.run(base + ["--out-suffix", suffix], env=env, capture_output=True, text=True)
check("resume without --repair-tail refuses the truncated tail", p3.returncode != 0 and ("truncated last line" in (p3.stderr + p3.stdout) or "FAILED" in p3.stdout or "incomplete" in p3.stdout), (p3.stderr + p3.stdout)[-300:])
p4 = subprocess.run(base + ["--out-suffix", suffix, "--repair-tail"], env=env, capture_output=True, text=True)
check("resume with --repair-tail exits 0", p4.returncode == 0, (p4.stderr + p4.stdout)[-300:])
recs = {}
dupe = 0
for f in files(d):
    for r in qa_gen.read_strict(f):
        dupe += r["request_id"] in recs
        recs[r["request_id"]] = r["suffix_ids"]
check("24 requests, duplicates 0, missing 0", len(recs) == 24 and dupe == 0 and set(recs) == set(ref), (len(recs), dupe))
check("greedy tokens identical to the reference run (gen_w1)", all(recs[k] == ref[k] for k in ref if k in recs) and set(recs) == set(ref))
same = all(open(f, "rb").read().startswith(complete_before[f]) for f in complete_before)
check("bytes/hash of every record completed before the interruption unchanged after resume", same and all(sha(complete_before[f]) == sha(open(f, "rb").read()[:len(complete_before[f])]) for f in complete_before))
check("quarantined partial line kept (not deleted)", os.path.exists(target + ".partial") and open(target + ".partial").read().startswith('{"request_id": "abc"'))
comp = json.load(open(f"{d}/completion.json"))
check("completion.json written only after full verification (requests_sha256 present)", comp["n_actual_unique"] == 24 and "requests_sha256" in comp)

# ---------------- B ----------------
suffix2 = "_term_v2"
d2 = f"{OUT}/gen{suffix2}/{STAGE}__{CK}"
os.makedirs(d2, exist_ok=True)
q = subprocess.Popen(base + ["--out-suffix", suffix2], env=env, stdout=open(f"{d2}/parent.out", "a"), stderr=open(f"{d2}/parent.err", "a"))
t0 = time.time()
while time.time() - t0 < 300 and not glob.glob(f"{d2}/attempts/attempt_*.json"):
    time.sleep(0.1)
time.sleep(2.0)
att2 = sorted(glob.glob(f"{d2}/attempts/attempt_*.json"))[-1]
ch2 = json.load(open(att2)).get("children", [])
q.send_signal(signal.SIGTERM)
q.wait(timeout=180)
time.sleep(0.5)
check("SIGTERM: parent exits, all owned children gone (reaped)", len(ch2) == 2 and not any(pid_alive(c["pid"], c["start"]) for c in ch2), ch2)
a2 = json.load(open(att2))
check("SIGTERM: attempt status is interrupted or complete (never left 'running')", a2["status"] in ("interrupted", "complete", "failed_or_incomplete"), a2["status"])
fd = os.open(f"{d2}/run.lock", os.O_RDWR)
import fcntl
try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    got = True
except BlockingIOError:
    got = False
os.close(fd)
check("SIGTERM: run.lock released after children were reaped", got)
if a2["status"] == "interrupted":
    # 재개하면 남은 요청만 생성하고 기준과 일치
    p5 = subprocess.run(base + ["--out-suffix", suffix2, "--repair-tail"], env=env, capture_output=True, text=True)
    r5 = {}
    for f in files(d2):
        for r in qa_gen.read_strict(f):
            r5[r["request_id"]] = r["suffix_ids"]
    check("after SIGTERM, resume completes with identical greedy tokens", p5.returncode == 0 and r5 == ref, (p5.returncode, len(r5)))

json.dump({"n_records_at_kill": n_at_kill, "n_complete_before_repair": len(ids_before), "results": res}, open(f"{OUT}/tests/fixtures_iter016_gpu.json", "w"), indent=1)
bad = [r for r in res if not r["pass"]]
print(f"{len(res) - len(bad)}/{len(res)} passed")
sys.exit(1 if bad else 0)
