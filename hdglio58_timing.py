"""iter_058: D6 paired 전체 pipeline 비용 측정(HD-GLIO vs U8) 및 U8 기술 검사.
python hdglio58_timing.py u8check        # U8 D6 전체: PNG 동일성 + iter_056 답변과 대조 (GPU1)
python hdglio58_timing.py blocks         # 3 block x 2 order, 동일 GPU 순차, block/order별 GPU 균형
출력: results/iter_058/timing/
"""
import json
import os
import subprocess
import sys
import time

ROOT = os.path.abspath(".")
PYV = f"{ROOT}/results/environments/hdglio58/bin/python"
PARAMS = f"{ROOT}/results/iter_058/external/weights/params"
OUT = f"{ROOT}/results/iter_058/timing"
BLOCKS = [["BRATS_053", "BRATS_199"], ["BRATS_368", "BRATS_380"], ["BRATS_037", "BRATS_455"]]


def smi():
    r = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
                       capture_output=True, text=True)
    return r.stdout.strip().splitlines()


def run_u8(cases, gpu, out, check=False):
    os.makedirs(out, exist_ok=True)
    cj = f"{out}/cases.json"
    json.dump(cases, open(cj, "w"))
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(gpu), U8_CHECK_PNG="1" if check else "0")
    t = time.perf_counter()
    r = subprocess.run([sys.executable, f"{ROOT}/hdglio58_u8.py", "D", cj, out], env=env, stdout=open(f"{out}/stdout.log", "w"),
                       stderr=subprocess.STDOUT)
    return {"rc": r.returncode, "wall_s": time.perf_counter() - t}


def run_hd(cases, gpu, out):
    os.makedirs(out, exist_ok=True)
    cj = f"{out}/cases.json"
    json.dump(cases, open(cj, "w"))
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(gpu), HD_GLIO_PARAMS=PARAMS, HDG_PROCS="2")
    t = time.perf_counter()
    r = subprocess.run([PYV, f"{ROOT}/hdglio58_pred.py", f"{ROOT}/results/iter_058/hd/input_D", f"{out}/pred", cj, f"{out}/timing.json"],
                       env=env, stdout=open(f"{out}/stdout.log", "w"), stderr=subprocess.STDOUT)
    return {"rc": r.returncode, "wall_s": time.perf_counter() - t}


def u8check():
    cases = json.load(open("results/iter_058/hd/D_cases.json"))
    res = run_u8(cases, 1, f"{OUT}/u8check", check=True)
    print(res)


def blocks():
    ev = []
    for b, cs in enumerate(BLOCKS):
        for o, order in enumerate((("U8", "HD"), ("HD", "U8"))):
            gpu = (b + o) % 2
            snap = {"smi_before": smi(), "loadavg": os.getloadavg()}
            rec = {"block": b, "order": "->".join(order), "cases": cs, "gpu": gpu, **snap, "runs": {}}
            for name in order:
                d = f"{OUT}/b{b}_o{o}_{name}"
                rec["runs"][name] = (run_u8 if name == "U8" else run_hd)(cs, gpu, d)
                rec["runs"][name]["start_order_index"] = order.index(name)
                rec["runs"][name]["dir"] = d
            ev.append(rec)
            json.dump(ev, open(f"{OUT}/blocks.json", "w"), indent=1)
            print(rec["block"], rec["order"], {k: v["wall_s"] for k, v in rec["runs"].items()}, flush=True)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    {"u8check": u8check, "blocks": blocks}[sys.argv[1]]()
