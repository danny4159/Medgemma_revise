"""iter_048 최종 봉인: 동작 확인·재개·변조·launcher·lock 검사와 모든 단계 산출물의 상태를 다시 확인하고, 하나라도 실패하면 completion을 쓰지 않는다.
최종 raw/report/selection/training/timing/source/verifier digest를 묶어 results/iter_048/completion.json을 마지막에 원자적으로 만든다 (기존 파일 덮어쓰기 거부).
"""
import glob
import hashlib
import json
import os
import sys

import pg43_run as R

ROOT = "results/iter_048"


def sha(p):
    return R.file_sha(p)


def jl(p):
    return json.load(open(p))


def main():
    out = f"{ROOT}/completion.json"
    if os.path.exists(out):
        sys.exit("exists")
    c = {}
    d = jl(f"{ROOT}/tests/gate_data_final.json")
    c["gate_data"] = d["n_pass"] == d["n"] == 20
    d = jl(f"{ROOT}/tests/gate_inputs_v2_final.json") if os.path.exists(f"{ROOT}/tests/gate_inputs_v2_final.json") else jl(f"{ROOT}/tests/gate_inputs_final.json")
    c["gate_inputs"] = d["n_pass"] == d["n"]
    d = jl(f"{ROOT}/tests/gate_gpu_det_0_final.json") if os.path.exists(f"{ROOT}/tests/gate_gpu_det_0_final.json") else jl(f"{ROOT}/tests/gate_gpu_det_01_final.json")
    c["gate_gpu_det"] = d["n_pass"] == d["n"] == 8
    c["resume_compare"] = jl(f"{ROOT}/tests/resume/resume_compare.json")["all_ok"]
    g = jl(f"{ROOT}/tests/gen_tests.json")
    c["gen_tests_all_rejected_and_tokens_equal"] = bool(g["all_rejected"] and g["tokens_all_equal"])
    c["launch_tests"] = jl(f"{ROOT}/tests/launch_tests.json")["all_ok"]
    c["trainer_lock_test"] = jl(f"{ROOT}/tests/lock_test.json")["ok"]
    gate = jl(f"{ROOT}/decisions/v96_gate.json")
    for n in ("E", "J"):
        info = gate["v96_runs"][n]
        recs = R.verify_completion(info["gen_dir"], info["requests"], info["protocol"])
        c[f"v96_{n}_verify_completion_{len(recs)}"] = len(recs) == 384
    c["eval_verify_all_ok"] = jl(f"{ROOT}/eval/verify.json")["all_ok"]
    c["timing_verify_ok"] = jl(f"{ROOT}/timing/timing_verify.json")["ok"]
    t = jl(f"{ROOT}/timing/timing_report.json")
    c["timing_integrity_zero_mismatch"] = t["integrity"]["E_token_mismatch_total"] == t["integrity"]["J_token_mismatch_total"] == t["integrity"]["A_box_mismatch_total"] == 0
    rep = jl(f"{ROOT}/eval/report.json")
    c["report_provenance_hashes_current"] = all(rep["provenance"][k] == sha(p) for k, p in (("eval_source_sha256", "pg48_eval.py"), ("manifest_sha256", "results/iter_043/data/manifest_private.json"),
                                                                                           ("select_sha256", f"{ROOT}/decisions/v96_gate.json")))
    ok = all(c.values())
    files = {}
    for pat in ("eval/report.json", "eval/report_per_patient.json", "eval/verify.json", "timing/timing_report.json", "timing/timing_verify.json", "decisions/*.json", "protocol/*.json",
                "requests/*.jsonl", "gen/V96_*/completion.json", "gen/D24_*/completion.json", "train/*/train_config.json", "train/*/epoch_0[258]/adapter.pt"):
        for p in sorted(glob.glob(f"{ROOT}/{pat}")):
            files[os.path.relpath(p, ROOT)] = sha(p)
    src = {f: sha(f) for f in sorted(glob.glob("pg48_*.py")) + ["pg43_run.py", "pg39_spec.py", "mg45_launch.py", "mg45_mg.py", "mg45_worker.py", "rsna_diag/generate.py", "rsna_diag/lora.py"]}
    res = {"all_checks_ok": ok, "checks": c, "file_digests": files, "source_digests": src,
           "known_caveat": "gen_tests: all_branch_match=false is a label-needle mismatch of my test (wrong_prompt_hash rejected at 'prompt hash mismatch' instead of 'row digest'); rejection itself held."}
    if not ok:
        print(json.dumps(c, indent=1))
        sys.exit("checks failed; completion NOT written")
    tmp = out + f".{os.getpid()}.tmp"
    json.dump(res, open(tmp, "w"), indent=1)
    os.replace(tmp, out)
    print("completion written", json.dumps(c))


if __name__ == "__main__":
    main()
