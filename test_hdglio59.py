"""iter_059 fixture: 사용 경로(hdglio59_common / hdglio59_timing)의 실패 거부 검사. 실패가 하나라도 있으면 nonzero exit.
python test_hdglio59.py results/iter_059/tests/fixtures.json
"""
import json
import os
import shutil
import sys
import tempfile

import hdglio59_common as C
import hdglio59_timing as T

R = {}


def expect_raises(name, fn, exc=Exception):
    try:
        fn()
        R[name] = {"pass": False, "why": "no exception"}
    except exc as e:
        R[name] = {"pass": True, "msg": str(e)[:120]}


def expect_ok(name, fn):
    try:
        v = fn()
        R[name] = {"pass": True, "value": str(v)[:120]}
    except Exception as e:  # noqa: BLE001
        R[name] = {"pass": False, "why": repr(e)}


def make_run(d, kind, cases, summary=True, extra=None, bad_slabs=False):
    os.makedirs(d)
    pref = "hd_" if kind == "HD" else "u8_"
    for c in cases:
        ans = [{"slab": i, "answer": "PRESENT", "ended_eos": True} for i in range(6)]
        if bad_slabs:
            ans = ans[:5]
        json.dump({"case": c, "answers": ans}, open(f"{d}/{pref}{c}.json", "w"))
    if extra:
        json.dump({"answers": []}, open(f"{d}/{pref}{extra}.json", "w"))
    if summary:
        json.dump({"cases": cases}, open(f"{d}/summary.json", "w"))


def main():
    tmp = tempfile.mkdtemp()
    cs = ["A", "B"]
    # GPU mapping / admission
    allowed = C.allowed_physical("0,1")
    expect_ok("gpu_in_allowed", lambda: C.pick_gpu(1, allowed))
    expect_raises("gpu_outside_allowed", lambda: C.pick_gpu(2, allowed), C.TechError)
    expect_raises("cvd_unset", lambda: C.allowed_physical(""), C.TechError)
    tbl = {"0": {"uuid": "u0", "used_mib": 15000, "total_mib": 24576}, "1": {"uuid": "u1", "used_mib": 100, "total_mib": 24576}}
    expect_raises("memory_insufficient", lambda: C.admit(tbl, "0", 9728), C.TechError)
    expect_ok("memory_sufficient", lambda: C.admit(tbl, "1", 9728))
    expect_raises("gpu_missing_in_table", lambda: C.admit(tbl, "5", 100), C.TechError)
    # run dir collision
    d = f"{tmp}/run1"
    os.makedirs(d)
    expect_raises("existing_run_dir_rejected", lambda: C.new_run_dir(d), FileExistsError)
    expect_ok("new_run_dir_ok", lambda: C.new_run_dir(f"{tmp}/sub/run2"))
    # digest lock: source/checkpoint/config mismatch, request tamper
    lock = {"code": {"a.py": "x"}, "checkpoint": {"m": "y"}}
    expect_raises("source_digest_mismatch", lambda: C.check_locked(lock["code"], {"a.py": "z"}), C.TechError)
    expect_raises("checkpoint_digest_mismatch", lambda: C.check_locked(lock["checkpoint"], {"m": "q"}), C.TechError)
    expect_raises("locked_file_missing", lambda: C.check_locked(lock["code"], {}), C.TechError)
    expect_ok("digest_match", lambda: C.check_locked(lock["code"], {"a.py": "x"}))
    req = {"requests_E": "h1"}
    expect_raises("request_tamper", lambda: C.check_locked(req, {"requests_E": "h2"}), C.TechError)
    # completion / partial output
    make_run(f"{tmp}/ok", "HD", cs)
    expect_ok("complete_run", lambda: C.verify_run("HD", f"{tmp}/ok", cs))
    make_run(f"{tmp}/part", "HD", cs, summary=False)
    expect_raises("partial_output_not_complete", lambda: C.verify_run("HD", f"{tmp}/part", cs), C.TechError)
    make_run(f"{tmp}/miss", "U8", ["A"])
    expect_raises("missing_case", lambda: C.verify_run("U8", f"{tmp}/miss", cs), C.TechError)
    make_run(f"{tmp}/extra", "HD", cs, extra="Z")
    expect_raises("unexpected_extra_output", lambda: C.verify_run("HD", f"{tmp}/extra", cs), C.TechError)
    make_run(f"{tmp}/slab", "HD", cs, bad_slabs=True)
    expect_raises("bad_slab_count", lambda: C.verify_run("HD", f"{tmp}/slab", cs), C.TechError)
    # GT checks (실제 iter_056 자료의 정상 통과 + 변조 거부)
    chosen = json.load(open("results/iter_056/data/cases.json"))["chosen"]
    gt = json.load(open("results/iter_056/data/gt_slabs.json"))["rows"]
    expect_ok("gt_real_D", lambda: C.check_gt_rows(gt, chosen, "D"))
    expect_ok("gt_real_E", lambda: C.check_gt_rows(gt, chosen, "E"))
    expect_raises("gt_duplicate_key", lambda: C.check_gt_rows(gt + [dict(gt[0])], chosen, "D"), C.TechError)
    sw = [dict(g) for g in gt]
    first_d = next(g for g in sw if g["split"] == "D")
    first_d["split"] = "E"  # case/split 교환
    expect_raises("gt_case_split_exchange", lambda: C.check_gt_rows(sw, chosen, "D"), C.TechError)
    expect_raises("gt_missing_slab", lambda: C.check_gt_rows([g for g in gt if not (g["case"] == gt[0]["case"] and g["slab"] == 3)], chosen, gt[0]["split"]), C.TechError)
    # worker 실패: pair가 첫 실패에서 중단하고 새 attempt는 새 경로를 쓴다
    calls = []

    def fake_run_one(kind, cases, logical, run_dir, allowed, extra_env=None):
        calls.append(run_dir)
        C.new_run_dir(run_dir)
        return {"kind": kind, "cases": cases, "rc": 1 if kind == "HD" else 0, "wall_s": 1.0, "dir": run_dir, "logical_gpu": logical,
                "physical_gpu": "0", "parent_start_epoch": 0, "parent_end_epoch": 1}

    orig_run_one, orig_digests, orig_table = T.run_one, C.current_digests, C.gpu_table
    T.run_one = fake_run_one
    C.gpu_table = lambda: {}
    try:
        lk = {"code": C.current_digests()}
        r0 = T.pair(0, 1, 0, f"{tmp}/t", lk, ["0", "1"])  # order HD->U8, HD가 먼저 실패
        r1 = T.pair(0, 1, 1, f"{tmp}/t", lk, ["0", "1"])
        R["worker_failure_stops_pair"] = {"pass": (not r0["complete"]) and list(r0["runs"]) == ["HD"] and not r0["runs"]["HD"]["complete"]}
        R["retry_uses_new_attempt_dir"] = {"pass": len(set(calls)) == len(calls) == 2 and "_a1_" in calls[1] and not r1["complete"]}
    finally:
        T.run_one, C.gpu_table = orig_run_one, orig_table
    expect_raises("locked_code_changed_before_pair", lambda: T.pair(0, 0, 0, f"{tmp}/t2", {"code": {"hdglio59_hd.py": "bad"}}, ["0", "1"]), C.TechError)
    shutil.rmtree(tmp, ignore_errors=True)
    out = sys.argv[1]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    n = len(R)
    ok = sum(1 for v in R.values() if v["pass"])
    json.dump({"passed": ok, "total": n, "results": R}, open(out, "w"), indent=1)
    print(f"{ok}/{n}")
    for k, v in R.items():
        if not v["pass"]:
            print("FAIL", k, v)
    sys.exit(0 if ok == n else 1)


if __name__ == "__main__":
    main()
