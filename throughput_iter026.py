"""iter_026 D 처리량 비교: 같은 24요청 부분집합을 2 worker(1/GPU)와 4 worker(2/GPU)로 비교한다 (계상 외, throughput probe).
사용: python throughput_iter026.py {2w|4w}
"""
import json
import os
import subprocess
import sys
import time

from rsna_diag import roi26_requests as Q, roi26_protocol as P

mode = sys.argv[1]
n_workers = 2 if mode == "2w" else 4
gpus = [0, 1]

rows_all = Q.load_rows("results/iter_026/requests/D_V__M0.jsonl")
rows_all += Q.load_rows("results/iter_026/requests/D_O__M0.jsonl")
rows = sorted(rows_all, key=lambda r: r["request_id"])[:24]
out_dir = f"results/iter_026/throughput/{mode}"
os.makedirs(out_dir, exist_ok=True)
rp = f"{out_dir}/probe.jsonl"
with open(rp, "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")

P.create(f"{out_dir}/protocol.json", extra=[rp], note=f"throughput probe {mode}")

procs = []
t0 = time.time()
for k in range(n_workers):
    g = gpus[k % len(gpus)]
    cmd = [sys.executable, "-m", "rsna_diag.roi26_gen", "--requests", rp, "--out-dir", out_dir, "--worker", str(k),
           "--protocol", f"{out_dir}/protocol.json"]
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(g), CUDA_DEVICE_ORDER="PCI_BUS_ID")
    procs.append(subprocess.Popen(cmd, env=env, stdout=open(f"{out_dir}/w{k}.out.log", "w"),
                                  stderr=open(f"{out_dir}/w{k}.err.log", "w")))

peak = {}
while any(p.poll() is None for p in procs):
    r = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used", "--format=csv,noheader,nounits"],
                       capture_output=True, text=True)
    for ln in r.stdout.strip().splitlines():
        i, u = [x.strip() for x in ln.split(",")]
        peak[i] = max(peak.get(i, 0), int(u))
    time.sleep(3)
wall = time.time() - t0
codes = [p.returncode for p in procs]
print(json.dumps({"mode": mode, "n_workers": n_workers, "n_requests": len(rows), "wall_s": wall,
                  "req_per_min": len(rows) / wall * 60, "returncodes": codes, "peak_used_mib": peak}))
