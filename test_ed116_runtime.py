"""iter_116 실행 경로 검사 (CPU): 재개 보존, 부분 행 복구, 0건 비용 집계, 변조 거부, 2/4 worker token 일치, 비용 귀속.
사용: python test_ed116_runtime.py <출력 json>  (작업 사본은 results/iter_116/tests/tamper_work 아래에만 만든다)"""
import glob
import hashlib
import json
import os
import shutil
import sys

import pg43_run as RUN

G = "results/iter_116/gen"
REQ = "results/iter_116/requests"
PRO = "results/iter_116/protocol"
W = "results/iter_116/tests/tamper_work_v2"
R = []


def chk(name, ok, detail=None):
    R.append(dict(name=name, passed=bool(ok), detail=detail))
    print(("PASS " if ok else "FAIL ") + name, "" if ok else detail)


def load(d):
    out = {}
    for f in sorted(glob.glob(d + "/gen_worker*.jsonl")):
        for ln in open(f):
            if ln.strip():
                r = json.loads(ln)
                out[r["request_id"]] = r
    return out


def must_fail(name, fn):
    try:
        fn()
    except Exception as e:
        chk(name, True, f"{type(e).__name__}: {str(e)[:100]}")
        return
    chk(name, False, "예외 없음")


def fresh(case):
    d = f"{W}/{case}"
    if os.path.exists(d):
        raise SystemExit(f"{d} exists")
    shutil.copytree(f"{G}/TECH_w2", d)
    return d


def main(out):
    T = "results/iter_116/requests/TECH.jsonl"
    P = f"{PRO}/protocol_TECH.json"
    # 1. 정상 완료 검증
    for d in ("TECH_w2", "TECH_w4"):
        recs = RUN.verify_completion(f"{G}/{d}", T, P)
        chk(f"verify_completion_{d}", len(recs) == 48)
    a, b = load(f"{G}/TECH_w2"), load(f"{G}/TECH_w4")
    chk("w2_vs_w4_suffix_tokens_identical", set(a) == set(b) and all(a[k]["suffix_ids"] == b[k]["suffix_ids"] for k in a))
    chk("w2_vs_w4_input_ids_identical", all(a[k]["input_ids_sha256"] == b[k]["input_ids_sha256"] for k in a))
    # text-only 요청에는 영상 입력이 없고 R/T 텍스트가 같다
    rows = [json.loads(l) for l in open(T)]
    byk = {(r["patient"], r["cond"]): r for r in rows}
    chk("R_T_prompt_identical_all12", all(byk[(p, "R")]["prompt"] == byk[(p, "T")]["prompt"] for p in {r["patient"] for r in rows}))
    chk("T_records_no_image_inputs", all(r["n_image_tokens"] == 0 and r["has_pixel_values"] is False and r["input_pixel_sha256"] is None
                                         for r in a.values() if r["cond"] == "T"))
    chk("image_records_have_image_inputs", all(r["n_image_tokens"] > 0 and r["has_pixel_values"] is True for r in a.values() if r["cond"] != "T"))
    diffs = {a[byk[(p, "R")]["request_id"]]["n_input_tokens"] - a[byk[(p, "T")]["request_id"]]["n_input_tokens"] - a[byk[(p, "R")]["request_id"]]["n_image_tokens"]
             for p in {r["patient"] for r in rows}}
    # R−T 입력 길이 차이 = 영상 soft token 수 + 영상 표식 token 상수(관측 3). 환자마다 일정해야 한다 (텍스트는 동일).
    chk("R_vs_T_input_token_difference_is_image_tokens_plus_constant", len(diffs) == 1, sorted(diffs))
    # 2. 재개 (RESUME8)
    rd = f"{G}/RESUME8"
    pre = open("results/iter_116/tests_resume_before_sha.txt").read().strip()
    w0 = open(f"{rd}/gen_worker0.jsonl", "rb").read()
    n_pre = None
    for n in range(len(w0), 0, -1):
        if w0[:n].endswith(b"\n") and hashlib.sha256(w0[:n]).hexdigest() == pre:
            n_pre = n
            break
    chk("resume_completed_rows_preserved_byte_exact", n_pre is not None, n_pre)
    rl = glob.glob(f"{rd}/gen_worker0.jsonl.repair.log")
    chk("resume_torn_tail_repaired_and_preserved", bool(rl) and bool(glob.glob(f"{rd}/gen_worker0.jsonl.partial.*.bin")))
    rr = RUN.verify_completion(rd, f"{REQ}/RESUME8.jsonl", f"{PRO}/protocol_RESUME8.json")
    chk("resume_no_missing_duplicate", len(rr) == 8 and len({r["request_id"] for r in rr}) == 8)
    ra = load(rd)
    chk("resume_tokens_equal_TECH_w2", all(ra[k]["suffix_ids"] == a[k]["suffix_ids"] for k in ra), len(ra))
    cj = json.load(open(f"{rd}/completion.json"))
    chk("resume_attempt_files_preserved", len(glob.glob(f"{rd}/launch_children.a*.json")) == 2 and len(glob.glob(f"{rd}/partial_*.json")) == 1)
    chk("resume_cost_this_attempt_vs_total", cj["cost_this_attempt"]["n_records"] == 5 and cj["cost"]["n_records"] == 8, [cj["cost_this_attempt"]["n_records"], cj["cost"]["n_records"]])
    gpus = {r.get("physical_gpu") for r in rr}
    chk("records_carry_physical_gpu", None not in gpus and gpus <= {"0", "1"}, sorted(map(str, gpus)))
    # 3. 0건 비용 집계
    z = RUN.cost_summary([])
    chk("cost_summary_empty_records", z["n_records"] == 0 and z["peak_mem_reserved_gb_max"] is None)
    oc = RUN.occupancy([], "results/iter_116/gen/TECH_w2", {0: 0}, 1.0)
    chk("occupancy_empty_records", oc["n_gpus_used"] == 0 and oc["first_request_start_to_last_end_s"] == 0.0)
    # 재개 후 GPU 귀속: mapping과 다른 물리 GPU를 기록한 record는 mapping이 아니라 record 값을 쓴다
    recs = list(load(f"{G}/TECH_w4").values())
    wrong_map = {0: 1, 1: 1, 2: 1, 3: 1}
    oc2 = RUN.occupancy(recs, f"{G}/TECH_w4", wrong_map, 1.0)
    chk("occupancy_uses_record_physical_gpu_not_launch_mapping", oc2["n_gpus_used"] == 2, oc2["n_gpus_used"])
    # 4. 변조 거부
    os.makedirs(W, exist_ok=True)
    d = fresh("record_text")
    fn = sorted(glob.glob(d + "/gen_worker*.jsonl"))[0]
    L = open(fn).read().split("\n")
    r0 = json.loads(L[0])
    r0["suffix_text_raw"] = "Yes.<end_of_turn>"
    L[0] = json.dumps(r0)
    open(fn, "w").write("\n".join(L))
    must_fail("tamper_record_text_rejected", lambda: RUN.verify_completion(d, T, P))
    d = fresh("drop_record")
    fn = sorted(glob.glob(d + "/gen_worker*.jsonl"))[0]
    L = open(fn).read().split("\n")
    open(fn, "w").write("\n".join(L[1:]))
    must_fail("missing_record_rejected", lambda: RUN.verify_completion(d, T, P))
    d = fresh("dup_record")
    fn = sorted(glob.glob(d + "/gen_worker*.jsonl"))[0]
    L = open(fn).read().split("\n")
    open(fn, "w").write("\n".join(L[:-1] + [L[0]]) + "\n")
    must_fail("duplicate_record_rejected", lambda: RUN.verify_completion(d, T, P))
    d = fresh("requests_prompt")
    rq = f"{d}/requests_mod.jsonl"
    rr_ = [json.loads(l) for l in open(T)]
    rr_[0]["prompt"] += " Extra."
    open(rq, "w").write("".join(json.dumps(x, sort_keys=True) + "\n" for x in rr_))
    must_fail("modified_requests_rejected", lambda: RUN.verify_completion(d, rq, P))
    d = fresh("protocol_code")
    pm = f"{d}/protocol_mod.json"
    pj = json.load(open(P))
    pj["code"]["pg43_run.py"] = "0" * 64
    json.dump(pj, open(pm, "w"))
    must_fail("source_hash_change_rejected", lambda: RUN.verify_completion(d, T, pm))
    d = fresh("locked_file")
    pm = f"{d}/protocol_mod.json"
    pj = json.load(open(P))
    k = next(iter(pj["locked_files"]))
    pj["locked_files"][k] = "0" * 64
    json.dump(pj, open(pm, "w"))
    must_fail("locked_file_change_rejected", lambda: RUN.verify_completion(d, T, pm))
    d = fresh("image_pixel")
    rq = f"{d}/requests_mod.jsonl"
    rr_ = [json.loads(l) for l in open(T)]
    i0 = next(i for i, x in enumerate(rr_) if x["modality"] == "image")
    rr_[i0]["input_pixel_sha256"] = "1" * 64
    open(rq, "w").write("".join(json.dumps(x, sort_keys=True) + "\n" for x in rr_))
    must_fail("image_pixel_hash_mismatch_rejected", lambda: RUN.verify_completion(d, rq, P))
    d = fresh("completion_code")
    cj = json.load(open(f"{d}/completion.json"))
    cj["exit_codes"] = [1, 0]
    json.dump(cj, open(f"{d}/completion.json", "w"))
    must_fail("bad_exit_code_rejected", lambda: RUN.verify_completion(d, T, P))
    # MAIN protocol은 tech gate가 run=false이면 만들어지지 않는다
    def mk():
        RUN.make_protocol(f"{REQ}/MAIN.jsonl", f"{W}/protocol_MAIN_should_not_exist.json", gate="results/iter_116/tech/tech_gate.json")
    must_fail("main_protocol_refused_when_tech_gate_false", mk)
    chk("main_protocol_not_created", not os.path.exists(f"{W}/protocol_MAIN_should_not_exist.json") and not os.path.exists(f"{PRO}/protocol_MAIN.json"))
    n_ok = sum(x["passed"] for x in R)
    json.dump(dict(n=len(R), n_pass=n_ok, checks=R), open(out, "x"), indent=1)
    print(n_ok, "/", len(R))
    sys.exit(0 if n_ok == len(R) else 1)


if __name__ == "__main__":
    main(sys.argv[1])
