"""iter_041 실행 driver (순차 launcher 호출, 재개 가능: 완료된 job은 건너뛰고, 진행 중이던 job은 같은 out-dir에서 이어 실행).

stage d24: D24 x C adapter 96요청을 2 worker(GPU당 1)와 4 worker(GPU당 2)로 각각 실행 (처리량·메모리·token 정합성 비교; V96 점수는 쓰지 않음).
stage v96: 고정 큐 순서 C:JAB -> C:Icost -> C:JBA -> B:JAB -> B:JBA 를 --workers 구성으로 실행.
protocol은 새로 만들고(존재하면 hash 재검증 후 재사용), 평가 GT manifest·selection lock·pg41_rules.py를 --lock으로 잠근다.

python run_iter041.py --stage d24
python run_iter041.py --stage v96 --workers 4 --peak-gb 10
"""
import argparse
import json
import os
import subprocess
import sys

R = "results/iter_041"
ADAPTER = {"C": "results/iter_040/train2/C_s17/epoch_03", "B": "results/iter_040/train2/B_lr1e-4_s17/epoch_05"}
LOCK = ["results/iter_039/data/manifest_private.jsonl", "results/iter_040/data/manifest_eval_private.jsonl",
        "results/iter_040/data/selection_lock.json", "pg41_rules.py", "pg39_spec.py"]


def sh(cmd):
    print(">>", " ".join(cmd), flush=True)
    return subprocess.run(cmd).returncode


def ensure_protocol(req, proto, adapter):
    if os.path.exists(proto):
        return True
    return sh([sys.executable, "pg41_run.py", "protocol", "--requests", req, "--out", proto, "--adapter", adapter, "--lock"] + LOCK) == 0


def job(name, req, model, workers, peak, out_dir):
    proto = f"{R}/protocol/protocol_{name}.json"
    os.makedirs(f"{R}/protocol", exist_ok=True)
    if os.path.exists(f"{out_dir}/completion.json"):
        print("skip (complete):", out_dir)
        return 0
    if not ensure_protocol(req, proto, ADAPTER[model]):
        return 1
    return sh([sys.executable, "pg41_run.py", "launch", "--requests", req, "--protocol", proto, "--out-dir", out_dir,
               "--workers", str(workers), "--peak-gb", str(peak)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=["d24", "v96"])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--peak-gb", type=float, default=9.0)
    a = ap.parse_args()
    rq = f"{R}/requests"
    if a.stage == "d24":
        # 같은 protocol(=같은 요청·adapter)을 두 out-dir에서 사용: protocol 이름은 job 이름 공유
        req = f"{rq}/requests_D24_C.jsonl"
        proto = f"{R}/protocol/protocol_D24_C.json"
        os.makedirs(f"{R}/protocol", exist_ok=True)
        if not ensure_protocol(req, proto, ADAPTER["C"]):
            sys.exit(1)
        for w in (2, 4):
            out = f"{R}/gen/D24_C_{w}w"
            if os.path.exists(f"{out}/completion.json"):
                continue
            if sh([sys.executable, "pg41_run.py", "launch", "--requests", req, "--protocol", proto, "--out-dir", out,
                   "--workers", str(w), "--peak-gb", str(a.peak_gb)]) != 0:
                sys.exit(f"D24 {w}w failed")
        return
    order = [("V96_C_JAB", "V96_JAB", "C"), ("V96_C_Icost", "V96_Icost", "C"), ("V96_C_JBA", "V96_JBA", "C"),
             ("V96_B_JAB", "V96_JAB", "B"), ("V96_B_JBA", "V96_JBA", "B")]
    for name, rqn, model in order:
        rc = job(name, f"{rq}/requests_{rqn}.jsonl", model, a.workers, a.peak_gb, f"{R}/gen/{name}")
        if rc != 0:
            sys.exit(f"{name} failed rc={rc}")
    json.dump({"queue_order": [o[0] for o in order], "workers": a.workers, "peak_gb_assumed": a.peak_gb},
              open(f"{R}/gen/v96_run_order.json", "x"), indent=1)


if __name__ == "__main__":
    main()
