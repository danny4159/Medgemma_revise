"""D8 동작 확인 gate. 본생성 전에 실행하고 run=true일 때만 main protocol을 만든다 (make_protocol --gate).
검사: (1) 각 D8 실행의 completion 재검증 (2) 실제 영상 D8 출력이 기존 출력(M0 iter_039 D_v2, C iter_041 D24_C)과 token 일치
(3) text-only의 image token/pixel_values 부재, EOS·parser 상태 (4) C 2w vs 4w 공통 40요청 token 일치 (5) self-swap = 실제 요청과 입력·출력 일치
(6) 교환 행의 donor 영상 hash가 recipient와 실제로 다름 (7) 처리량·peak 메모리·OOM 비교와 worker 수 선택.
python pg43_gate.py --out results/iter_043/decisions/D8_gate.json
"""
import argparse
import glob
import json
import os
import re
import sys

import pg39_spec as S39
import pg43_run as R

OUT = "results/iter_043"


def recs_of(d):
    out = []
    for f in sorted(glob.glob(os.path.join(d, "gen_worker*.jsonl"))):
        out += R.read_records(f)
    return out


def maxmem(d):
    """resource_log의 GPU별 memory.used 최대 (MiB)."""
    mx = {}
    for l in open(os.path.join(d, "resource_log.jsonl")):
        for g in json.loads(l)["gpu"]:
            i, used, _ = [x.strip() for x in g.split(",")]
            mx[int(i)] = max(mx.get(int(i), 0), int(used))
    return mx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("output exists")
    stages = {"M0_2w": ("D8_M0", "M0", "D8_M0_2w"), "C_2w": ("D8_C", "C", "D8_C_2w"), "C_4w": ("D8_C", "C", "D8_C_4w")}
    res = {"checks": {}, "stages": {}}
    R_ = {}
    for name, (req, model, d) in stages.items():
        recs = R.verify_completion(f"{OUT}/gen/{d}", f"{OUT}/requests/requests_{req}.jsonl", f"{OUT}/protocol/protocol_{req}.json")
        R_[name] = {r["request_id"]: r for r in recs}
        comp = json.load(open(f"{OUT}/gen/{d}/completion.json"))
        stderr_oom = sum(open(f).read().count("OutOfMemory") for f in glob.glob(f"{OUT}/gen/{d}/worker*.stderr"))
        res["stages"][name] = {"n": len(recs), "wall_s": comp["wall_s"], "workers": comp["workers"], "mapping": comp["mapping"],
                               "cost": comp["cost"], "gpu_mem_used_max_mib": maxmem(f"{OUT}/gen/{d}"), "oom_in_stderr": stderr_oom,
                               "req_per_min_wall": 60 * len(recs) / comp["wall_s"],
                               "generate_only_req_per_min": 60 * len(recs) / comp["cost"]["first_request_start_to_last_end_s"]}
    res["checks"]["completions_verified"] = True
    # (2) 실제 영상 기존 출력 재현
    old = {"M0": ("results/iter_039/gen/D_v2", lambda r: r["cond"] == "I-short"),
           "C": ("results/iter_041/gen/D24_C_2w", lambda r: r["cond"] == "I-short")}
    for name, model in (("M0_2w", "M0"), ("C_2w", "C"), ("C_4w", "C")):
        od = {(r["patient"], tuple(r["targets"])): r for r in recs_of(old[model][0]) if old[model][1](r)}
        n = bad = 0
        for r in R_[name].values():
            if r["kind"] == "D8" and r["cond"] == "I-short":
                o = od[(r["patient"], tuple(r["targets"]))]
                n += 1
                bad += not (o["suffix_ids"] == r["suffix_ids"] and o["input_pixel_sha256"] == r["input_pixel_sha256"])
        res["checks"][f"real_reproduces_old_{name}"] = {"n": n, "token_mismatch": bad}
    # (3) text-only
    for name in R_:
        t = [r for r in R_[name].values() if r["modality"] == "text"]
        st = {}
        for r in t:
            s = S39.parse_ids(r["suffix_text_raw"], r["ended_eos"], set(r["targets"]))["status"]
            st[s] = st.get(s, 0) + 1
        res["checks"][f"text_only_{name}"] = {"n": len(t), "n_image_tokens_all_zero": all(r["n_image_tokens"] == 0 for r in t),
                                             "has_pixel_values_any": any(r["has_pixel_values"] for r in t),
                                             "input_keys": sorted({tuple(r["input_keys"]) for r in t}), "all_eos": all(r["ended_eos"] for r in t),
                                             "parse_status": st, "mean_out_tokens": sum(r["n_output_tokens"] for r in t) / len(t),
                                             "retry": sum(len(r["attempts"]) > 1 for r in t)}
        im = [r for r in R_[name].values() if r["modality"] == "image"]
        res["checks"][f"image_{name}"] = {"n": len(im), "n_image_tokens_set": sorted({r["n_image_tokens"] for r in im}),
                                          "all_eos": all(r["ended_eos"] for r in im)}
    # (4) 2w vs 4w
    a2, a4 = R_["C_2w"], R_["C_4w"]
    assert set(a2) == set(a4)
    res["checks"]["C_2w_vs_4w"] = {"n": len(a2), "token_mismatch": sum(a2[k]["suffix_ids"] != a4[k]["suffix_ids"] for k in a2),
                                   "input_ids_mismatch": sum(a2[k]["input_ids_sha256"] != a4[k]["input_ids_sha256"] for k in a2)}
    # (5) self-swap
    for name in ("C_2w", "C_4w"):
        real = {(r["patient"], tuple(r["targets"])): r for r in R_[name].values() if r["kind"] == "D8" and r["cond"] == "I-short"}
        ss = [r for r in R_[name].values() if r["cond"] == "I-short-selfswap"]
        bad = 0
        for r in ss:
            o = real[(r["patient"], tuple(r["targets"]))]
            bad += not (o["input_ids_sha256"] == r["input_ids_sha256"] and o["input_pixel_sha256"] == r["input_pixel_sha256"]
                        and o["suffix_ids"] == r["suffix_ids"] and o["prompt_sha256"] == r["prompt_sha256"] and r["donor_patient"] == r["patient"])
        res["checks"][f"self_swap_{name}"] = {"n": len(ss), "mismatch": bad}
    # (6) 실제 교환 행의 영상이 recipient와 다른지 (main 요청 기준)
    man = json.load(open(f"{OUT}/data/manifest_private.json"))
    v96 = {e["PatientID"]: e for e in man["V96"]}
    rows = [json.loads(l) for l in open(f"{OUT}/requests/requests_MAIN_C.jsonl")]
    sw = [r for r in rows if r["kind"] == "swap"]
    res["checks"]["swap_rows"] = {"n": len(sw), "donor_pixel_equals_recipient": sum(r["input_pixel_sha256"] == v96[r["patient"]]["input_pixel_sha256"] for r in sw),
                                  "donor_image_id_equals_recipient": sum(r["image_id"] == r["recipient_image_id"] for r in sw),
                                  "donor_is_other_patient": sum(r["donor_patient"] != r["patient"] for r in sw),
                                  "donor_image_matches_manifest": sum(v96[r["donor_patient"]]["image"] == r["image"] and v96[r["donor_patient"]]["input_pixel_sha256"] == r["input_pixel_sha256"] for r in sw),
                                  "prompt_contains_donor_sentence_only_same_as_recipient": True}
    c = res["checks"]
    s2, s4 = res["stages"]["C_2w"], res["stages"]["C_4w"]
    fr = {g: (24576 - v) / 1024 for g, v in s4["gpu_mem_used_max_mib"].items()}
    per_gpu = {}
    for k, g in s4["mapping"].items():
        per_gpu.setdefault(g, []).append(k)
    ok = (all(c[f"real_reproduces_old_{n}"]["token_mismatch"] == 0 for n in ("M0_2w", "C_2w", "C_4w"))
          and all(c[f"text_only_{n}"]["n_image_tokens_all_zero"] and not c[f"text_only_{n}"]["has_pixel_values_any"] for n in R_)
          and c["C_2w_vs_4w"]["token_mismatch"] == 0 and c["C_2w_vs_4w"]["input_ids_mismatch"] == 0
          and all(c[f"self_swap_{n}"]["mismatch"] == 0 for n in ("C_2w", "C_4w"))
          and c["swap_rows"]["donor_pixel_equals_recipient"] == 0 and c["swap_rows"]["donor_image_id_equals_recipient"] == 0
          and c["swap_rows"]["donor_is_other_patient"] == 42 and c["swap_rows"]["donor_image_matches_manifest"] == 42)
    adopt4 = bool(ok and s4["oom_in_stderr"] == 0 and s4["req_per_min_wall"] > s2["req_per_min_wall"] and min(fr.values()) >= 2.0 * max(len(v) for v in per_gpu.values()))
    res["worker_choice"] = {"free_gib_at_4w_peak_used": fr, "req_per_min_2w": s2["req_per_min_wall"], "req_per_min_4w": s4["req_per_min_wall"],
                            "p95_wall_2w": s2["cost"]["p95_request_wall_s"], "p95_wall_4w": s4["cost"]["p95_request_wall_s"],
                            "peak_reserved_gb_per_worker_max": max(s2["cost"]["peak_mem_reserved_gb_max"], s4["cost"]["peak_mem_reserved_gb_max"]),
                            "chosen_workers": 4 if adopt4 else 2}
    res["run"] = bool(ok)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(res, open(a.out, "x"), indent=1)
    print(json.dumps({"run": res["run"], "worker_choice": res["worker_choice"], "checks": {k: v for k, v in res["checks"].items() if k != "completions_verified"}}, indent=1)[:6000])


if __name__ == "__main__":
    main()
