"""iter_027 처리량 비교: 고정 D 24요청(M0 12 + B0 12, 균형)을 2 worker(1/GPU)와 4 worker(2/GPU)로 비교한다.
iter_026의 throughput_iter026.py는 M0-only였다(리뷰 결함). 이번은 M0/B0를 섞어 실제 E200_extra 생성 구성과 맞춘다.
사용: python throughput_iter027.py {2w|4w}
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

m0_rows = sorted(Q.load_rows("results/iter_026/requests/D_V__M0.jsonl"), key=lambda r: r["request_id"])[:12]
b0_rows = sorted(Q.load_rows("results/iter_026/requests/D_V__B0.jsonl"), key=lambda r: r["request_id"])[:12]
rows = m0_rows + b0_rows
out_dir = f"results/iter_027/throughput/{mode}"
os.makedirs(out_dir, exist_ok=True)

procs = []
t0 = time.time()
per_ckpt_gpu_workers = {}
for ckpt, ck_rows in (("M0", m0_rows), ("B0", b0_rows)):
    rp = f"{out_dir}/probe_{ckpt}.jsonl"
    with open(rp, "w") as f:
        for r in ck_rows:
            f.write(json.dumps(r) + "\n")
    protocol_path = f"{out_dir}/protocol_{ckpt}.json"
    adapter = Q.CKPT_SPEC[ckpt]
    P.create(protocol_path, extra=[rp], note=f"iter_027 throughput probe {mode} {ckpt}")
    half = n_workers // 2
    for k in range(half):
        g = gpus[len(procs) % len(gpus)]
        cmd = [sys.executable, "-m", "rsna_diag.roi26_gen", "--requests", rp, "--out-dir", f"{out_dir}/{ckpt}", "--worker", str(k),
               "--protocol", protocol_path]
        if adapter:
            cmd += ["--adapter", adapter]
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(g), CUDA_DEVICE_ORDER="PCI_BUS_ID")
        os.makedirs(f"{out_dir}/{ckpt}", exist_ok=True)
        procs.append(subprocess.Popen(cmd, env=env, stdout=open(f"{out_dir}/{ckpt}_w{k}.out.log", "w"),
                                      stderr=open(f"{out_dir}/{ckpt}_w{k}.err.log", "w")))

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
result = {"mode": mode, "n_workers": n_workers, "n_requests": len(rows), "wall_s": wall,
          "req_per_min": len(rows) / wall * 60, "returncodes": codes, "peak_used_mib": peak}
json.dump(result, open(f"{out_dir}/result.json", "w"), indent=1)
print(json.dumps(result))
