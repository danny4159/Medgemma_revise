"""동일 GPU 단독 resident latency 비교: detector vs MedGemma B0 (기본 medgemma env).

원본: results/iter_034/latency_bench.py (sha256 a0809d67...; 그 원본 iter_033 latency_bench.py). 원본은 CUDA_VISIBLE_DEVICES를
"1"로 하드코딩하고 B0만 측정했다. 이번 변경:
- run: 상속된 허용 GPU 집합에서 논리 index 하나를 골라 두 모델을 각각 별도 프로세스로 단독 resident 실행한다.
  반복 3회, 반복마다 순서를 교차(det→B0, B0→det, det→B0). 각 프로세스는 로드 시간 기록, warmup 8, L64 64건.
  detector는 det_eval.py latency(detector 전용 env), B0는 이 파일의 b0 명령(기본 env).
- b0: 공식 processor 경로(apply_chat_template 텍스트 + processor(text, images))와 wrapper(build_inputs)의 전체
  tensor key/shape/dtype/value 대조, 저장 validation 출력(iter_012 seed17 epoch05)의 input_ids·suffix token 재현을
  확인한 뒤 end-to-end(영상 읽기·전처리·생성·decode)와 모델 생성 구간을 synchronize로 잰다(cap ladder·greedy 유지).
- stress: 저장 validation 출력 중 가장 긴 응답 4건을 재생성해 긴 출력의 시간·peak와 token 재현을 기록한다.
"""
import argparse
import json
import os
import subprocess
import sys
import time

import numpy as np

BASE = "/SSD1_1TB/home/milab/daniel/08_medgemma/research"
sys.path.insert(0, BASE)
DET_PY = "/home/test/.conda/envs/natten_py310/bin/python"
ADAPTER = f"{BASE}/results/iter_012/train/lr2e-4_s17/epoch_05"
B0_VAL = f"{ADAPTER}/val_gen/gen_worker0.jsonl"


def stats(x):
    return {"mean": float(np.mean(x)), "p50": float(np.percentile(x, 50)), "p95": float(np.percentile(x, 95))}


def official_tensor_check(proc, torch, GEN, ids, infer, stored, prompt):
    """공식 processor 경로(chat template 텍스트 렌더링 + processor(text, images))와 wrapper(build_inputs) 대조.
    렌더링 텍스트에 이미 <bos>가 있으므로 add_special_tokens=False가 HF 권장 경로다(True면 BOS가 중복된다).
    iter_035 첫 latency 실행의 검사기는 이 인자를 빠뜨려 길이 361 대 360으로 불일치를 기록했다(검사기 결함)."""
    tens = []
    for i in ids:
        img, aff, px = GEN.load_image(f"{BASE}/{infer[i]['image']}")
        w = GEN.build_inputs(proc, img, prompt)
        msgs = [{"role": "user", "content": [{"type": "image", "image": img}, {"type": "text", "text": prompt}]}]
        text = proc.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
        o = proc(text=text, images=[img], return_tensors="pt", add_special_tokens=False)
        o_default = proc(text=text, images=[img], return_tensors="pt")
        same_keys = sorted(w.keys()) == sorted(o.keys())
        eq = same_keys and all(w[k].shape == o[k].shape and w[k].dtype == o[k].dtype and torch.equal(w[k], o[k]) for k in w)
        tens.append({"id": i, "keys": sorted(w.keys()), "shapes": {k: list(w[k].shape) for k in w},
                     "dtypes": {k: str(w[k].dtype) for k in w}, "equal": bool(eq),
                     "n_bos_wrapper": int((w["input_ids"][0] == proc.tokenizer.bos_token_id).sum()),
                     "default_add_special_len": int(o_default["input_ids"].shape[1]),
                     "input_ids_eq_stored": w["input_ids"][0].tolist() == stored[i]["input_ids"]})
    return tens


def cmd_tensorcheck(a):
    os.environ.setdefault("HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    import torch
    import transformers
    from rsna_diag import generate as GEN, prompts as P
    proc = transformers.AutoProcessor.from_pretrained(GEN.MODEL_ID, revision=GEN.MODEL_REVISION)
    ids = json.load(open(f"{BASE}/results/iter_033/data/L64.json"))["ids"]
    infer = {}
    for l in open(f"{BASE}/results/iter_010/manifests/infer_manifest.jsonl"):
        r = json.loads(l); infer[r["id"]] = r
    stored = {}
    for l in open(B0_VAL):
        r = json.loads(l); stored[r["id"]] = r
    tens = official_tensor_check(proc, torch, GEN, ids, infer, stored, P.CONCISE)
    out = {"n": len(tens), "all_equal": all(x["equal"] for x in tens), "all_input_ids_eq_stored": all(x["input_ids_eq_stored"] for x in tens),
           "rows": tens}
    json.dump(out, open(a.out, "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}))


def cmd_b0(a):
    from rsna_diag import generate as GEN, prompts as P
    ids = json.load(open(f"{BASE}/results/iter_033/data/L64.json"))["ids"]
    infer = {}
    for l in open(f"{BASE}/results/iter_010/manifests/infer_manifest.jsonl"):
        r = json.loads(l); infer[r["id"]] = r
    stored = {}
    for l in open(B0_VAL):
        r = json.loads(l); stored[r["id"]] = r
    import torch
    torch.cuda.synchronize() if torch.cuda.is_available() else None
    t = time.time()
    torch, proc, model = GEN.load_model()
    dig = GEN.load_adapter(torch, model, ADAPTER)
    torch.cuda.synchronize()
    load_s = time.time() - t
    if dig != stored[ids[0]]["adapter_digest"]:
        raise RuntimeError("adapter digest differs from stored validation outputs")
    eos = {proc.tokenizer.eos_token_id, proc.tokenizer.convert_tokens_to_ids("<end_of_turn>")}
    prompt = P.CONCISE
    tens = official_tensor_check(proc, torch, GEN, ids[:8], infer, stored, prompt)
    rows, repro = [], []
    torch.cuda.reset_peak_memory_stats()
    for k, i in enumerate(ids[:8] + ids):
        item = {"id": i, "image": f"{BASE}/{infer[i]['image']}", "file_sha256": infer[i]["file_sha256"]}
        torch.cuda.synchronize()
        t0 = time.time()
        rec = GEN.run_request(torch, proc, model, eos, item, "concise", prompt)
        torch.cuda.synchronize()
        dt = time.time() - t0
        if k >= 8:
            rows.append({"id": i, "end_to_end_s": dt, "model_s": rec["runtime_s_total"], "n_out": rec["n_output_tokens"],
                         "final_cap": rec["final_cap"]})
            repro.append(rec["suffix_ids"] == stored[i]["suffix_ids"])
    out = {"model": "B0", "adapter_digest": dig, "load_s": load_s, "n": len(rows), "warmup": 8, "precision": "bf16",
           "official_tensor_check": tens, "official_tensor_all_equal": all(x["equal"] for x in tens),
           "stored_input_ids_equal": all(x["input_ids_eq_stored"] for x in tens),
           "stored_suffix_reproduced": int(sum(repro)), "n_repro_checked": len(repro),
           "end_to_end": stats([r["end_to_end_s"] for r in rows]), "model_only": stats([r["model_s"] for r in rows]),
           "peak_alloc_mib": torch.cuda.max_memory_allocated() / 2**20, "peak_reserved_mib": torch.cuda.max_memory_reserved() / 2**20,
           "gpu": torch.cuda.get_device_name(0), "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"), "rows": rows}
    if a.stress:
        longest = sorted(stored.values(), key=lambda r: -r["n_output_tokens"])[:4]
        st = []
        for r in longest:
            item = {"id": r["id"], "image": f"{BASE}/{r['image']}", "file_sha256": r["image_file_sha256"]}
            torch.cuda.reset_peak_memory_stats()
            rec = GEN.run_request(torch, proc, model, eos, item, "concise", prompt)
            st.append({"id": r["id"], "stored_n_out": r["n_output_tokens"], "n_out": rec["n_output_tokens"],
                       "runtime_s": rec["runtime_s_total"], "final_cap": rec["final_cap"], "ended_eos": rec["ended_eos"],
                       "suffix_equal_stored": rec["suffix_ids"] == r["suffix_ids"],
                       "peak_alloc_mib": torch.cuda.max_memory_allocated() / 2**20})
        out["long_output_stress"] = st
    json.dump(out, open(a.out, "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k not in ("rows", "official_tensor_check")}))


def cmd_run(a):
    gpus = os.environ["CUDA_VISIBLE_DEVICES"].split(",")
    phys = gpus[a.gpu]
    os.makedirs(a.out_dir, exist_ok=True)
    smi = subprocess.run(["nvidia-smi", "--query-gpu=index,uuid,memory.used,memory.total", "--format=csv,noheader"],
                         capture_output=True, text=True).stdout
    runs = []
    for rep in range(3):
        order = ["det", "b0"] if rep % 2 == 0 else ["b0", "det"]
        for m in order:
            outp = os.path.join(a.out_dir, f"rep{rep}_{m}.json")
            env = dict(os.environ, CUDA_VISIBLE_DEVICES=phys, PYTHONUNBUFFERED="1")
            if m == "det":
                c = [DET_PY, f"{BASE}/rsna_diag/det_eval.py", "latency", "--manifest", "L64", "--checkpoint", a.det_checkpoint, "--out", outp]
            else:
                c = [sys.executable, os.path.abspath(__file__), "b0", "--out", outp] + (["--stress"] if rep == 0 else [])
            with open(os.path.join(a.out_dir, f"rep{rep}_{m}.log"), "w") as f:
                rc = subprocess.run(c, env=env, stdout=f, stderr=subprocess.STDOUT).returncode
            runs.append({"rep": rep, "model": m, "rc": rc, "out": outp})
            if rc != 0:
                raise RuntimeError(f"latency {m} rep{rep} failed rc={rc}")
    agg = {}
    for m in ("det", "b0"):
        rs = [json.load(open(r["out"])) for r in runs if r["model"] == m]
        e2e = [x["end_to_end_s"] for r in rs for x in r["rows"]]
        mo = [x["model_s"] for r in rs for x in r["rows"]]
        agg[m] = {"end_to_end": stats(e2e), "model_only": stats(mo), "load_s": [r["load_s"] for r in rs],
                  "peak_alloc_mib_max": max(r["peak_alloc_mib"] for r in rs), "peak_reserved_mib_max": max(r["peak_reserved_mib"] for r in rs),
                  "n_requests": len(e2e)}
    b0 = [json.load(open(r["out"])) for r in runs if r["model"] == "b0"]
    res = {"gpu_logical": a.gpu, "gpu_physical": phys, "nvidia_smi_before": smi, "runs": runs, "aggregate": agg,
           "speedup_det_over_b0_end_to_end_mean": agg["b0"]["end_to_end"]["mean"] / agg["det"]["end_to_end"]["mean"],
           "speedup_det_over_b0_model_mean": agg["b0"]["model_only"]["mean"] / agg["det"]["model_only"]["mean"],
           "b0_checks": {"official_tensor_all_equal": all(r["official_tensor_all_equal"] for r in b0),
                         "stored_input_ids_equal": all(r["stored_input_ids_equal"] for r in b0),
                         "stored_suffix_reproduced": [f"{r['stored_suffix_reproduced']}/{r['n_repro_checked']}" for r in b0]},
           "long_output_stress": b0[0].get("long_output_stress"),
           "note": "detector FP32(torchvision) vs B0 bf16(transformers, greedy·cap ladder). 단독 batch1 latency이며 batch 처리량과 별개."}
    json.dump(res, open(os.path.join(a.out_dir, "latency_summary.json"), "w"), indent=2)
    print(json.dumps({k: v for k, v in res.items() if k not in ("runs", "nvidia_smi_before")}, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("b0"); p.add_argument("--out", required=True); p.add_argument("--stress", action="store_true")
    p.set_defaults(func=cmd_b0)
    p = sub.add_parser("tensorcheck"); p.add_argument("--out", required=True); p.set_defaults(func=cmd_tensorcheck)
    p = sub.add_parser("run"); p.add_argument("--gpu", type=int, required=True); p.add_argument("--det_checkpoint", required=True)
    p.add_argument("--out_dir", required=True); p.set_defaults(func=cmd_run)
    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
