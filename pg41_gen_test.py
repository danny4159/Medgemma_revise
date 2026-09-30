"""iter_041 생성 runner(adapter·부분 행 보존 복구·완료 검증·2/4 worker) GPU 검사. pg40_gen_test 기반(출처 SHA 18fdae2e).
GPU는 상속된 CUDA_VISIBLE_DEVICES 안에서만 쓰며(launch 기본), 하드코딩하지 않는다. 결과 경로는 --base 인자.

python pg41_gen_test.py --adapter <dir> --requests results/iter_041/requests/requests_D8_B.jsonl --base results/iter_041/tests/gen --out results/iter_041/tests/gen_test.json
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import time

import pg41_run as R

BASE = None
RES = []


def check(name, ok, detail=None):
    RES.append({"name": name, "pass": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name, json.dumps(detail, default=str)[:400], flush=True)


def run(cmd, **kw):
    return subprocess.run([sys.executable, "pg41_run.py"] + cmd, capture_output=True, text=True, **kw)


def toks(out_dir):
    d = {}
    import glob
    for fn in sorted(glob.glob(os.path.join(out_dir, "gen_worker*.jsonl"))):
        for r in R.read_records(fn):
            d[r["request_id"]] = r["suffix_ids"]
    return d


def resource_peak(out_dir):
    mx = {}
    p = os.path.join(out_dir, "resource_log.jsonl")
    if os.path.exists(p):
        for l in open(p):
            for g in json.loads(l)["gpu"]:
                i, u, _ = [x.strip() for x in g.split(",")]
                mx[i] = max(mx.get(i, 0), int(u))
    return mx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--requests", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--old-gen", required=True, help="iter_040 gen dir of the same adapter (old-path token comparison)")
    ap.add_argument("--old-requests", required=True)
    ap.add_argument("--old-protocol", required=True)
    ap.add_argument("--lock", nargs="*", default=[])
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("output exists")
    global BASE
    BASE = a.base
    os.makedirs(BASE, exist_ok=True)
    sub = [json.loads(l) for l in open(a.requests)]
    a.n = len(sub)
    req = a.requests
    proto = f"{BASE}/protocol_adapter.json"
    R.make_protocol(req, proto, adapter=a.adapter, lock=a.lock)
    # 1) 2 worker (GPU당 1)
    d2, d4 = f"{BASE}/w2", f"{BASE}/w4"
    t = time.time()
    r2 = run(["launch", "--requests", req, "--protocol", proto, "--out-dir", d2, "--workers", "2", "--peak-gb", "10"])
    w2 = time.time() - t
    check("launch_2_workers_completes_with_completion_json", r2.returncode == 0 and os.path.exists(f"{d2}/completion.json"), {"wall_s": w2, "err": r2.stderr[-300:]})
    recs2 = R.verify_completion(d2, req, proto)
    check("verify_completion_passes_adapter_records", len(recs2) == a.n and all(x["adapter_digest"] for x in recs2))
    # 2) 4 worker (GPU당 2)
    t = time.time()
    r4 = run(["launch", "--requests", req, "--protocol", proto, "--out-dir", d4, "--workers", "4", "--peak-gb", "10"])
    w4 = time.time() - t
    ok4 = r4.returncode == 0 and os.path.exists(f"{d4}/completion.json")
    check("launch_4_workers_completes_or_refused_by_memory_margin", ok4 or "free" in (r4.stdout + r4.stderr), {"wall_s": w4, "out": (r4.stdout + r4.stderr)[-200:]})
    same = None
    if ok4:
        t2, t4 = toks(d2), toks(d4)
        same = t2 == t4
        check("token_identical_2_vs_4_workers", same, {"n": len(t2)})
        check("throughput_recorded", True, {"req_per_min_2w_wall": a.n / w2 * 60, "req_per_min_4w_wall": a.n / w4 * 60, "peak_mib_2w": resource_peak(d2),
                                            "peak_mib_4w": resource_peak(d4)})
    # 3) adapter 독립 로드 경로(학습기와 같은 apply_lora+load_lora_state, dropout 0.05 eval)로 생성한 token과 일치
    import torch
    from rsna_diag import generate as G, lora
    torch_, proc, model = G.load_model()
    blob = torch_.load(os.path.join(a.adapter, "adapter.pt"), map_location="cpu", weights_only=True)
    lora.apply_lora(model, 16, 32, 0.05)
    lora.load_lora_state(model, blob["state"])
    model.eval()
    env = G.env_info(torch_, proc, model)
    eos = env["eos_token_id"]
    eos_ids = set(eos if isinstance(eos, list) else [eos])
    ref = {}
    pick = [r for c in ("I-short", "J-short", "J-short-rev") for r in [x for x in sub if x["cond"] == c][:2]]
    for r in pick:
        image, aff, px = G.load_image(r["image"])
        inp = G.build_inputs(proc, image, r["prompt"])
        at = G.generate(torch_, proc, model, inp, r["caps"][0], eos_ids)
        ref[r["request_id"]] = at["suffix_ids"]
    t2 = toks(d2)
    check("adapter_generation_equals_trainer_style_load_path_tokens", all(ref[k] == t2[k] for k in ref), {"n": len(ref), "conds": sorted({r["cond"] for r in pick})})
    del model
    torch_.cuda.empty_cache()
    # 3b) 기존 iter_040 경로(pg40_run)로 생성·저장된 같은 adapter의 I-short 출력과 token 대조 (기존 요청 8건 재실행)
    old_rows = [json.loads(l) for l in open(a.old_requests)]
    old_rows = sorted(old_rows, key=lambda r: r["order_key"])[:8]
    reqo = f"{BASE}/requests_oldpath8.jsonl"
    with open(reqo, "x") as f:
        for r in old_rows:
            f.write(json.dumps(r) + "\n")
    protoo = f"{BASE}/protocol_oldpath8.json"
    R.make_protocol(reqo, protoo, adapter=a.adapter, lock=a.lock)
    do = f"{BASE}/oldpath8"
    ro = run(["launch", "--requests", reqo, "--protocol", protoo, "--out-dir", do, "--workers", "2", "--peak-gb", "10"])
    old_tok = {}
    for fn in sorted(os.listdir(a.old_gen)):
        if fn.startswith("gen_worker") and fn.endswith(".jsonl"):
            for r in R.read_records(os.path.join(a.old_gen, fn)):
                old_tok[r["request_id"]] = r["suffix_ids"]
    new_tok = toks(do)
    check("same_adapter_new_runner_tokens_equal_stored_iter040_output", ro.returncode == 0 and len(new_tok) == 8 and all(new_tok[k] == old_tok[k] for k in new_tok), {"n": len(new_tok), "err": ro.stderr[-200:]})
    # 4) 강제 종료 후 재개 + 부분 행 복구
    d3 = f"{BASE}/kill"
    cmd = [sys.executable, "pg41_run.py", "launch", "--requests", req, "--protocol", proto, "--out-dir", d3, "--workers", "2", "--peak-gb", "10"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    t0 = time.time()
    while time.time() - t0 < 900:
        n = sum(len(R.read_records(os.path.join(d3, f))) for f in os.listdir(d3) if f.startswith("gen_worker") and f.endswith(".jsonl")) if os.path.isdir(d3) else 0
        if n >= 6:
            break
        time.sleep(3)
    os.killpg(p.pid, signal.SIGKILL)
    p.wait()
    time.sleep(3)
    partial_files = [os.path.join(d3, f) for f in os.listdir(d3) if f.startswith("gen_worker") and f.endswith(".jsonl")]
    n_before = sum(len(R.read_records(f)) for f in partial_files)
    with open(partial_files[0], "a") as f:
        f.write('{"request_id": "torn", "x": ')  # 부분 행 시뮬레이션
    check("killed_before_completion", not os.path.exists(f"{d3}/completion.json") and 6 <= n_before < a.n, {"n_before": n_before})
    r3 = subprocess.run(cmd, capture_output=True, text=True)
    check("relaunch_after_kill_completes", r3.returncode == 0 and os.path.exists(f"{d3}/completion.json"), {"err": r3.stderr[-300:]})
    recs3 = R.verify_completion(d3, req, proto)
    tk3, tk2 = toks(d3), toks(d2)
    check("resumed_run_no_duplicates_and_tokens_equal_baseline", len(recs3) == a.n == len(tk3) and tk3 == tk2)
    check("partial_row_repaired_with_log_and_original_bytes_preserved", any(os.path.exists(f + ".repair.log") for f in partial_files) and any(fn.find(".partial.") >= 0 for fn in os.listdir(d3)))
    # 5) 변조 거부
    import shutil
    dt = f"{BASE}/tamper"
    shutil.copytree(d2, dt, ignore=shutil.ignore_patterns("*.lock", "claims"))
    fn = os.path.join(dt, "gen_worker0.jsonl")
    lines = open(fn).read().splitlines()
    rec = json.loads(lines[0])
    rec["suffix_text_raw"] = rec["suffix_text_raw"] + " "
    lines[0] = json.dumps(rec)
    open(fn, "w").write("\n".join(lines) + "\n")
    try:
        R.verify_completion(dt, req, proto)
        rej = False
    except R.RunError:
        rej = True
    check("modified_record_rejected_by_completion_verification", rej)
    dt2 = f"{BASE}/rerun_completed"
    r5 = run(["launch", "--requests", req, "--protocol", proto, "--out-dir", d2, "--workers", "2"])
    check("rerun_into_completed_dir_refused", r5.returncode != 0)
    json.dump({"results": RES, "n_pass": sum(x["pass"] for x in RES), "n": len(RES)}, open(a.out, "w"), indent=1, default=str)
    print(f"{sum(x['pass'] for x in RES)}/{len(RES)} PASS")


if __name__ == "__main__":
    main()
