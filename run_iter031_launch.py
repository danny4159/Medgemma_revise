"""iter_031 실행기: rsna_diag.risk30 worker를 여러 프로세스로 띄우고 모두 끝날 때까지 기다린다.

run_iter030_launch.py를 이어받아 다음을 보강한다:
- 같은 out-dir에 이미 완료된 launch_result.json이 있으면 거부한다 (기존 로그·결과 덮어쓰기 금지).
- --decide-c/--accept-protocol을 각 worker에 전달한다 (split=E gate, D24 재사용 protocol 허용).
- 실행 직전 nvidia-smi로 GPU 여유 메모리를 기록한다.

백그라운드(&, nohup) 실행이 불가능한 환경이므로, 여기서 subprocess로 worker들을 동시에 띄우고
wait한다. 각 worker는 --gpu(물리 index)와 --worker(논리 worker id, claim 파일 접미사)를 받는다.
같은 GPU에 여러 worker를 배치할 수 있다 (물리 index 재사용, worker id는 서로 달라야 함).
"""
import argparse
import json
import os
import subprocess
import sys
import time


def gpu_snapshot():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index,uuid,memory.total,memory.used,memory.free", "--format=csv,noheader"],
            text=True, timeout=20)
        return out.strip()
    except Exception as e:
        return f"nvidia-smi failed: {e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-manifest", required=True)
    ap.add_argument("--split", required=True, choices=["C", "E", "D24"])
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--gpus", required=True, help="worker별 물리 GPU, 콤마구분 (예: 0,1 or 0,0,1,1)")
    ap.add_argument("--tasks", default="O,F")
    ap.add_argument("--ids", default=None)
    ap.add_argument("--time-limit", type=float, default=None)
    ap.add_argument("--decide-c", default=None)
    ap.add_argument("--accept-protocol", nargs="*", default=[])
    a = ap.parse_args()

    os.makedirs(a.out_dir, exist_ok=True)
    result_path = f"{a.out_dir}/launch_result.json"
    if os.path.exists(result_path):
        prev = json.load(open(result_path))
        if all(r["returncode"] == 0 for r in prev.get("results", [])):
            raise SystemExit(f"refusing to overwrite completed launch_result.json at {result_path}")

    snap_before = gpu_snapshot()

    gpus = a.gpus.split(",")
    n_workers = len(gpus)
    procs = []
    t0 = time.time()
    for w, gpu in enumerate(gpus):
        cmd = [sys.executable, "-m", "rsna_diag.risk30",
               "--source-manifest", a.source_manifest, "--split", a.split,
               "--out-dir", a.out_dir, "--worker", str(w), "--protocol", a.protocol,
               "--adapter", a.adapter, "--gpu", gpu, "--tasks", a.tasks]
        if a.ids:
            cmd += ["--ids", a.ids]
        if a.time_limit:
            cmd += ["--time-limit", str(a.time_limit)]
        if a.decide_c:
            cmd += ["--decide-c", a.decide_c]
        if a.accept_protocol:
            cmd += ["--accept-protocol"] + a.accept_protocol
        log_path = f"{a.out_dir}/launch_worker{w}.stdout.log"
        err_path = f"{a.out_dir}/launch_worker{w}.stderr.log"
        procs.append({"w": w, "gpu": gpu, "cmd": cmd,
                      "p": subprocess.Popen(cmd, stdout=open(log_path, "w"), stderr=open(err_path, "w")),
                      "log": log_path, "err": err_path})

    results = []
    for entry in procs:
        rc = entry["p"].wait()
        results.append({"worker": entry["w"], "gpu": entry["gpu"], "returncode": rc,
                        "cmd": entry["cmd"], "log": entry["log"], "err": entry["err"]})
    wall = time.time() - t0
    snap_after = gpu_snapshot()
    out = {"n_workers": n_workers, "wall_s": wall, "results": results,
          "gpu_snapshot_before": snap_before, "gpu_snapshot_after": snap_after}
    print(json.dumps(out, indent=1))
    with open(result_path, "w") as f:
        json.dump(out, f, indent=1)
    if any(r["returncode"] != 0 for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
