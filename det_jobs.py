"""detector 작업 실행기 (기본 medgemma Python에서 실행).

계획(iter_033 §0, iter_035 §1·§6)에 따라 detector 코드는 기존 detector 전용 환경
(/home/test/.conda/envs/natten_py310/bin/python)을 subprocess로 명시 호출해 실행한다.
이 실행기는 임의 명령 전달기가 아니다: research/rsna_diag/det_*.py와 research/tests_det/*.py만 실행하고,
상속된 CUDA_VISIBLE_DEVICES 허용 집합 안에서 논리 index→물리 GPU를 배정한다.

spec(JSON): {"name": str, "out_dir": str, "stages": [[job, ...], ...]}
  job: {"name", "script"(research 기준 상대경로), "args": [...], "gpu": 논리 index 또는 null,
        "ok_rc": [0], "env": {"DET_TEST_SOURCE_SALT": ...}(허용 키만)}
stage 안의 job은 동시에, stage는 순서대로 실행한다. job 실패 시 이후 stage를 시작하지 않는다.
진행 상태는 out_dir/status.json(60초 주기)에 GPU 메모리·마지막 로그와 함께 기록하고, 모든 자식의 실제
종료 코드를 out_dir/result.json에 남긴다. SIGTERM/SIGINT를 받으면 자식에게 SIGTERM을 전달하고 기다린다.
"""
import json
import os
import signal
import subprocess
import sys
import time

BASE = "/SSD1_1TB/home/milab/daniel/08_medgemma/research"
DET_PY = "/home/test/.conda/envs/natten_py310/bin/python"
ALLOWED_PREFIX = ("rsna_diag/det_", "tests_det/")
ALLOWED_ENV = {"DET_TEST_SOURCE_SALT"}
_STOP = {"flag": False}


def _h(signum, frame):
    _STOP["flag"] = True


def allowed_gpus():
    v = os.environ.get("CUDA_VISIBLE_DEVICES")
    if v is None or v.strip() == "":
        raise RuntimeError("CUDA_VISIBLE_DEVICES not set; refusing to pick GPUs outside the inherited set")
    return [x.strip() for x in v.split(",") if x.strip()]


def gpu_mem():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=index,uuid,memory.used,memory.total,utilization.gpu",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=30).stdout
        return [dict(zip(["index", "uuid", "used_mib", "total_mib", "util"], [s.strip() for s in l.split(",")]))
                for l in out.strip().splitlines()]
    except Exception as e:  # noqa: BLE001
        return str(e)


def tail(path, n=2):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 4000))
            return f.read().decode(errors="replace").strip().splitlines()[-n:]
    except Exception:
        return []


def launch(job, out_dir, gpus):
    script = job["script"]
    if not script.startswith(ALLOWED_PREFIX) or ".." in script or not script.endswith(".py"):
        raise RuntimeError(f"script not allowed: {script}")
    path = os.path.join(BASE, script)
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    env = dict(os.environ)
    if job.get("gpu") is not None:
        g = int(job["gpu"])
        if g < 0 or g >= len(gpus):
            raise RuntimeError(f"gpu index {g} outside inherited set {gpus}")
        env["CUDA_VISIBLE_DEVICES"] = gpus[g]
    for k, v in (job.get("env") or {}).items():
        if k not in ALLOWED_ENV:
            raise RuntimeError(f"env key not allowed: {k}")
        env[k] = v
    env["PYTHONUNBUFFERED"] = "1"
    log = os.path.join(out_dir, f"{job['name']}.log")
    fh = open(log, "a")
    fh.write(f"\n=== launch {time.strftime('%Y-%m-%d %H:%M:%S')} gpu_logical={job.get('gpu')} "
             f"physical={env.get('CUDA_VISIBLE_DEVICES')} ===\n")
    fh.flush()
    p = subprocess.Popen([DET_PY, path] + [str(a) for a in job.get("args", [])], cwd=BASE, env=env,
                         stdout=fh, stderr=subprocess.STDOUT, start_new_session=False)
    return {"job": job, "proc": p, "log": log, "fh": fh, "t0": time.time(),
            "physical_gpu": env.get("CUDA_VISIBLE_DEVICES")}


def main():
    spec = json.load(open(sys.argv[1]))
    out_dir = spec["out_dir"]
    os.makedirs(out_dir, exist_ok=True)
    gpus = allowed_gpus()
    signal.signal(signal.SIGTERM, _h)
    signal.signal(signal.SIGINT, _h)
    results = []
    status_path = os.path.join(out_dir, "status.json")
    t_start = time.time()
    failed = False
    for si, stage in enumerate(spec["stages"]):
        if failed or _STOP["flag"]:
            for job in stage:
                results.append({"name": job["name"], "stage": si, "rc": None, "skipped": True})
            continue
        running = [launch(j, out_dir, gpus) for j in stage]
        last_status = 0.0
        while True:
            alive = [r for r in running if r["proc"].poll() is None]
            if _STOP["flag"]:
                for r in alive:
                    r["proc"].send_signal(signal.SIGTERM)
            if time.time() - last_status >= 60 or not alive:
                st = {"spec": spec["name"], "stage": si, "elapsed_s": round(time.time() - t_start),
                      "gpus_inherited": gpus, "gpu": gpu_mem(), "stop_requested": _STOP["flag"],
                      "jobs": [{"name": r["job"]["name"], "pid": r["proc"].pid, "rc": r["proc"].poll(),
                                "physical_gpu": r["physical_gpu"], "elapsed_s": round(time.time() - r["t0"]),
                                "tail": tail(r["log"])} for r in running]}
                tmp = status_path + ".tmp"
                with open(tmp, "w") as f:
                    json.dump(st, f, indent=1)
                os.replace(tmp, status_path)
                last_status = time.time()
            if not alive:
                break
            time.sleep(5)
        for r in running:
            rc = r["proc"].wait()
            r["fh"].close()
            ok = rc in r["job"].get("ok_rc", [0])
            results.append({"name": r["job"]["name"], "stage": si, "rc": rc, "ok": ok, "pid": r["proc"].pid,
                            "physical_gpu": r["physical_gpu"], "wall_s": round(time.time() - r["t0"], 1),
                            "log": r["log"]})
            if not ok:
                failed = True
    res = {"spec": spec["name"], "all_ok": (not failed) and not _STOP["flag"]
           and all(r.get("ok") for r in results), "stopped": _STOP["flag"],
           "wall_s": round(time.time() - t_start, 1), "jobs": results}
    with open(os.path.join(out_dir, "result.json"), "w") as f:
        json.dump(res, f, indent=2)
    print(json.dumps(res, indent=1))
    sys.exit(0 if res["all_ok"] else 1)


if __name__ == "__main__":
    main()
