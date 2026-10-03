"""iter_056 강제 중단·재개 검사 (D 요청, 별도 out-dir). worker를 SIGKILL로 죽이고 torn tail을 붙인 뒤 launch로 재개해
기존 D 본 실행(results/iter_056/gen/D)과 suffix token 일치·중복/누락 없음·부분 행 보존·claim 회수를 확인한다.
결과: results/iter_056/tests/resume_test2.json
"""
import glob
import json
import os
import signal
import subprocess
import sys
import time

import msd56_run as R

REQ, PROT = "results/iter_056/data/requests_D.jsonl", "results/iter_056/data/protocol_D_v2.json"
OUT = "results/iter_056/gen/D_resume_test2"
os.makedirs(OUT, exist_ok=True)
env = dict(os.environ, CUDA_VISIBLE_DEVICES="0")
p = subprocess.Popen([sys.executable, "msd56_run.py", "worker", "--requests", REQ, "--protocol", PROT, "--out-dir", OUT, "--worker", "0"],
                     env=env, stdout=open(f"{OUT}/kill_run.stdout.log", "a"), stderr=subprocess.STDOUT)
t0 = time.time()
while time.time() - t0 < 300:
    time.sleep(2)
    n = len(R.read_jsonl(f"{OUT}/gen_worker0.jsonl"))
    if n >= 12:
        break
p.send_signal(signal.SIGKILL)
p.wait()
n_before = len(R.read_jsonl(f"{OUT}/gen_worker0.jsonl"))
with open(f"{OUT}/gen_worker0.jsonl", "ab") as f:  # torn tail: 개행 없는 부분 행
    f.write(b'{"rid": "torn_partial_row", "mod')
subprocess.run([sys.executable, "msd56_run.py", "launch", "--requests", REQ, "--protocol", PROT, "--out-dir", OUT, "--gpus", "0,1",
                "--peak-gb", "11.5", "--worker-offset", "0"], check=True)
main = {r["rid"]: r for r in R.read_jsonl_all("results/iter_056/gen/D")} if hasattr(R, "read_jsonl_all") else {}
if not main:
    for fn in glob.glob("results/iter_056/gen/D/gen_worker*.jsonl"):
        for r in R.read_jsonl(fn):
            main[r["rid"]] = r
res_recs = {}
dups = 0
for fn in glob.glob(f"{OUT}/gen_worker*.jsonl"):
    for r in R.read_jsonl(fn):
        dups += r["rid"] in res_recs
        res_recs[r["rid"]] = r
rows = R.load_requests(REQ)
mismatch = [rid for rid, r in res_recs.items() if r["suffix_ids"] != main[rid]["suffix_ids"]]
res = {"killed_after_records": n_before, "partial_files": sorted(glob.glob(f"{OUT}/*.partial.*.bin")), "n_records": len(res_recs),
       "n_requests": len(rows), "duplicates": dups, "missing": len(rows) - len(res_recs), "token_mismatch_vs_D_main": len(mismatch),
       "workers_in_first_attempt": 1,
       "ok": dups == 0 and len(res_recs) == len(rows) and not mismatch and bool(glob.glob(f"{OUT}/*.partial.*.bin"))}
json.dump(res, open("results/iter_056/tests/resume_test2.json", "w"), indent=1)
print(res)
