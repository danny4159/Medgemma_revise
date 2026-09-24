"""여러 GPU 작업(학습/평가)을 물리 GPU에 배정해 동시에 실행하고 모두 끝날 때까지 기다린다 (iter_010).

jobs json: [{"gpu": "0", "module": "rsna_diag.train", "args": [...], "log": "path"}, ...]
- gpu는 상속된 CUDA_VISIBLE_DEVICES(허용 집합) 안이어야 한다. 같은 GPU에 여러 job 가능 (메모리는 호출자가 사전 실측으로 보장).
- 자원 로그(resource_log.jsonl)를 --log-dir에 주기적으로 append. 종료 코드는 job별로 launch_result.json에 기록한다.
사용: python -m rsna_diag.launch --jobs jobs.json --log-dir DIR
"""
import argparse
import json
import os
import subprocess
import sys
import time

from .run_shards import gpu_snapshot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--log-dir", required=True)
    a = ap.parse_args()
    allowed = [int(x) for x in os.environ.get("CUDA_VISIBLE_DEVICES", "0,1").split(",")]
    jobs = json.load(open(a.jobs))
    os.makedirs(a.log_dir, exist_ok=True)
    procs = []
    for j in jobs:
        if int(j["gpu"]) not in allowed:
            sys.exit(f"gpu {j['gpu']} not within allowed {allowed}")
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(j["gpu"]))
        os.makedirs(os.path.dirname(j["log"]), exist_ok=True)
        procs.append(subprocess.Popen([sys.executable, "-m", j["module"], *j["args"]], env=env,
                                      stdout=open(j["log"], "a"), stderr=subprocess.STDOUT))
    t0 = time.time()
    rl = open(os.path.join(a.log_dir, "resource_log.jsonl"), "a")
    rows0, _ = gpu_snapshot(set(allowed))
    # 논리(CUDA_VISIBLE_DEVICES) index와 물리 장치 uuid의 대응을 기록한다 (허용 집합 안의 index만 사용)
    gpu_map = {r["index"]: r["uuid"] for r in rows0}
    started = [{"gpu": j["gpu"], "gpu_uuid": gpu_map.get(int(j["gpu"])), "pid": p.pid, "module": j["module"], "log": j["log"]}
               for j, p in zip(jobs, procs)]
    json.dump({"allowed": allowed, "gpu_uuid_map": gpu_map, "children": started, "host": os.uname().nodename, "t_start": t0},
              open(os.path.join(a.log_dir, "launch_children.json"), "w"), indent=1)
    try:
        while any(p.poll() is None for p in procs):
            rows, apps = gpu_snapshot(set(allowed))
            rl.write(json.dumps({"t": time.time() - t0, "gpus": rows, "compute_apps": apps}) + "\n")
            rl.flush()
            time.sleep(30)
    finally:  # 중단(예: SIGINT)되어도 소유 child의 현재 상태를 기록한다. child는 종료시키지 않는다.
        res = [{"gpu": j["gpu"], "module": j["module"], "pid": p.pid, "returncode": p.poll(), "log": j["log"]} for j, p in zip(jobs, procs)]
        json.dump({"jobs": res, "wall_s": time.time() - t0, "all_finished": all(p.poll() is not None for p in procs)},
                  open(os.path.join(a.log_dir, "launch_result.json"), "w"), indent=1)
    print(json.dumps(res))
    sys.exit(0 if all(p.returncode == 0 for p in procs) else 1)


if __name__ == "__main__":
    main()
