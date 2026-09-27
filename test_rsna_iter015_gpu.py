"""iter_015 실제 GPU 통제 검사: SIGKILL 중단 -> 잘린 줄 거부 -> --repair-tail 재개 -> 남은 요청만 생성, 중복 0, 1/2 worker 출력 일치는 pilot_compare.json.
사용: python test_rsna_iter015_gpu.py  (허용 GPU: 상속된 CUDA_VISIBLE_DEVICES 중 첫 장 사용)
"""
import glob
import json
import os
import signal
import subprocess
import sys
import time

from rsna_diag import qa_gen

OUT = "results/iter_015"
PROT = f"{OUT}/protocols/protocol_d36_v2.json"
STAGE, CK = "d36_plain", "M0"
suffix = "_kill"
d = f"{OUT}/gen{suffix}/{STAGE}__{CK}"
res = []


def check(n, c, det=""):
    res.append({"name": n, "pass": bool(c), "detail": str(det)[:300]})
    print(("PASS " if c else "FAIL ") + n, det if not c else "")


gpu = os.environ["CUDA_VISIBLE_DEVICES"].split(",")[0]
os.makedirs(d, exist_ok=True)
cmd = [sys.executable, "-m", "rsna_diag.qa_gen", "--requests", f"{OUT}/requests/{STAGE}__{CK}.jsonl", "--out-dir", d, "--worker", "0", "--protocol", PROT]
p = subprocess.Popen(cmd, env=dict(os.environ, CUDA_VISIBLE_DEVICES=gpu), stdout=open(f"{d}/w0.out", "a"), stderr=open(f"{d}/w0.err", "a"))
f0 = f"{d}/gen_worker0.jsonl"
t0 = time.time()
while time.time() - t0 < 300:
    n = len(open(f0).readlines()) if os.path.exists(f0) else 0
    if n >= 10:
        break
    time.sleep(0.2)
os.kill(p.pid, signal.SIGKILL)
p.wait()
n_killed = len(open(f0).readlines())
check("worker killed mid-run with partial progress", 10 <= n_killed < 72, n_killed)
with open(f0, "a") as f:  # 쓰는 도중 죽은 상황을 모사: 개행 없는 잘린 줄
    f.write('{"request_id": "abc", "id": "trunc')
p2 = subprocess.run(cmd, env=dict(os.environ, CUDA_VISIBLE_DEVICES=gpu), capture_output=True, text=True)
check("resume refuses truncated JSONL tail", p2.returncode != 0 and "truncated last line" in p2.stderr, p2.stderr[-200:])
p3 = subprocess.run(cmd + ["--repair-tail"], env=dict(os.environ, CUDA_VISIBLE_DEVICES=gpu), capture_output=True, text=True)
check("resume with --repair-tail exits 0", p3.returncode == 0, p3.stderr[-300:])
recs = qa_gen.read_strict(f0)
ids = [r["request_id"] for r in recs]
check("all 72 requests done, no duplicates", len(ids) == 72 == len(set(ids)), (len(ids), len(set(ids))))
check("first n_killed records untouched (not regenerated)", [r["request_id"] for r in recs[:n_killed]] == ids[:n_killed])
check("quarantined partial line kept", os.path.exists(f0 + ".partial"))
ev = [json.loads(l) for l in open(f0 + ".log")]
check("resume generated only the remaining requests", 71 <= sum(e.get("event") == "done" for e in ev) <= 72, sum(e.get("event") == "done" for e in ev))
json.dump({"n_killed_at": n_killed, "results": res}, open(f"{OUT}/tests/fixtures_iter015_gpu_resume.json", "w"), indent=1)
bad = [r for r in res if not r["pass"]]
print(f"{len(res) - len(bad)}/{len(res)} passed")
sys.exit(1 if bad else 0)
