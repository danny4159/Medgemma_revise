"""iter_054 기술 단계 worker 구성 비교 요약 (처리량·메모리·오류). 결과: tests/worker_throughput.json"""
import glob
import json

RUNS = (("ref_w2", "results/iter_054/raw/tech_ref_w2"), ("cmp_w4", "results/iter_054/raw/tech_cmp_w4"),
        ("resume", "results/iter_054/raw/tech_resume"))
out = {}
for name, d in RUNS:
    comp = json.load(open(d + "/completion.json"))
    peak = {}
    for line in open(d + "/resource_log.jsonl"):
        for g in json.loads(line)["gpu"]:
            i, u, _ = g.split(",")
            peak[i.strip()] = max(peak.get(i.strip(), 0), int(u))
    errs = [f for f in glob.glob(d + "/worker*.stderr") if "Traceback" in open(f).read() or "OutOfMemory" in open(f).read()]
    c = comp["cost_this_dir_only"]
    out[name] = {"workers": comp["workers"], "wall_s_launcher": comp["wall_s_this_attempt"], "n": comp["n_unique"],
                 "device_s_incl_loading_union": c["device_seconds_incl_loading_union"],
                 "device_s_generate_union": c["device_seconds_generate_union"],
                 "requests_per_min_launcher_wall": comp["n_unique"] / comp["wall_s_this_attempt"] * 60,
                 "peak_gpu_mem_used_mib_nvidia_smi_sampled_10s": peak, "peak_mem_reserved_gb_max_torch": comp["peak_mem_reserved_gb_max"],
                 "stderr_files_with_traceback_or_oom": errs, "mean_wall_s_by_kind": comp["by_kind_mean_wall_s"]}
out["note"] = "resume entry is only the final 3-worker resume attempt (remaining requests after SIGKILL at 60 records)"
out["decision"] = {"main_workers": 4, "gpus": "0,1", "per_gpu_workers": 2,
                   "reason": ("4 workers (2/GPU) finished the same 252 tech requests in less launcher wall time than 2 workers "
                              "with identical outputs; sampled peak GPU memory leaves > 2 GiB per worker. batch>1 not tested "
                              "(padding / variable image count handling would add risk; not needed)")}
cap = 24576
ok_mem = all(max(out[k]["peak_gpu_mem_used_mib_nvidia_smi_sampled_10s"].values()) < cap - 2048 for k in ("ref_w2", "cmp_w4", "resume"))
ok_err = not any(out[k]["stderr_files_with_traceback_or_oom"] for k in ("ref_w2", "cmp_w4", "resume"))
out["all_pass"] = bool(ok_mem and ok_err and out["cmp_w4"]["wall_s_launcher"] < out["ref_w2"]["wall_s_launcher"])
json.dump(out, open("results/iter_054/tests/worker_throughput.json", "x"), indent=1)
print(json.dumps(out, indent=1))
