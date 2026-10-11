"""iter_108 실행 경로 검사: worker 구성 간 정합성, 변조 거부, SIGKILL 후 재개, admission 거부 기록.
선행: gen/TECH/{w2,w4,resume} completion. 결과: results/iter_108/tests/runtime_checks.json (새 파일만).
kill/admission 시험은 gen/TECH/kill, gen/TECH/admission 에 새로 생성한다."""
import copy
import glob
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import ev108_run as RUN
import ev108_spec as S

ROOT = RUN.ROOT
REQ = "results/iter_108/data/requests_TECH.jsonl"
PRO = "results/iter_108/protocol/protocol_TECH.json"
GEN = ROOT / "results/iter_108/gen/TECH"
CHECKS = []


def check(name, ok, detail=None):
    CHECKS.append({"name": name, "pass": bool(ok), "detail": detail})


def recs_of(d):
    out = {}
    for f in sorted(glob.glob(str(Path(d) / "gen_worker*.jsonl"))):
        for l in open(f):
            if l.strip():
                r = json.loads(l)
                out[r["request_id"]] = r
    return out


def same_outputs(a, b):
    ra, rb = recs_of(a), recs_of(b)
    keys = ("suffix_ids", "input_ids_sha256", "pixel_values_sha256_per_image", "ended_eos", "final_cap")
    return set(ra) == set(rb) and all(all(ra[k][f] == rb[k][f] for f in keys) for k in ra), len(ra)


def expect_reject(name, fn):
    try:
        fn()
        check(name, False, "not rejected")
    except RUN.RunError as e:
        check(name, True, str(e)[:120])
    except Exception as e:  # noqa
        check(name, False, f"unexpected {type(e).__name__}: {str(e)[:120]}")


def main():
    out = Path(sys.argv[1])
    if out.exists():
        sys.exit("exists")
    base = GEN / "w2"
    for d in ("w2", "w4", "resume"):
        RUN.verify_completion(str(GEN / d), REQ, PRO)
    check("completion_verified_w2_w4_resume", True)
    for d in ("w4", "resume"):
        ok, n = same_outputs(base, GEN / d)
        check(f"outputs_identical_w2_vs_{d}", ok, n)
    # 처리량/메모리 비교 (생성 구간 합집합, 첫 요청~마지막 종료)
    perf = {}
    for d in ("w2", "w4"):
        c = json.load(open(GEN / d / "completion.json"))
        perf[d] = {"workers": c["workers"], "wall_s_incl_loading": c["wall_s"], "first_to_last_s": c["cost"]["first_request_start_to_last_end_s"],
                   "req_per_min_generation_window": 42 / c["cost"]["first_request_start_to_last_end_s"] * 60,
                   "peak_reserved_gb": c["cost"]["peak_mem_reserved_gb_max"], "sum_generate_s": c["cost"]["sum_generate_runtime_s"],
                   "device_s_incl_loading": c["cost"]["device_seconds_incl_loading_union"]}
    # 변조 거부 (w2 사본)
    tdir = ROOT / "results/iter_108/tests/tamper"
    tdir.mkdir(parents=True, exist_ok=True)

    def fresh(name):
        d = tdir / name
        if d.exists():
            shutil.rmtree(d)
        shutil.copytree(base, d, ignore=shutil.ignore_patterns("claims", "*.lock"))
        return d

    def edit_first_record(d, fn):
        f = sorted(glob.glob(str(d / "gen_worker*.jsonl")))[0]
        lines = open(f).read().splitlines()
        r = json.loads(lines[0])
        fn(r)
        lines[0] = json.dumps(r)
        open(f, "w").write("\n".join(lines) + "\n")

    d = fresh("text")
    edit_first_record(d, lambda r: r.update(suffix_text_raw="No<end_of_turn>"))
    expect_reject("tamper_output_text_rejected", lambda: RUN.verify_completion(str(d), REQ, PRO))
    d = fresh("digest_fixed_but_hash_changed")
    edit_first_record(d, lambda r: (r.update(suffix_text_raw="No<end_of_turn>"), r.update(record_digest=RUN.record_digest(r))))
    expect_reject("tamper_record_with_recomputed_digest_but_completion_hash_rejected", lambda: RUN.verify_completion(str(d), REQ, PRO))
    d = fresh("dup")
    f = sorted(glob.glob(str(d / "gen_worker*.jsonl")))[0]
    first = open(f).readline()
    with open(f, "a") as fh:
        fh.write(first)
    expect_reject("tamper_duplicate_record_rejected", lambda: RUN.verify_completion(str(d), REQ, PRO))
    d = fresh("missing")
    f = sorted(glob.glob(str(d / "gen_worker*.jsonl")))[0]
    ls = open(f).read().splitlines()
    open(f, "w").write("\n".join(ls[1:]) + "\n")
    expect_reject("tamper_missing_record_rejected", lambda: RUN.verify_completion(str(d), REQ, PRO))
    d = fresh("pixel")
    edit_first_record(d, lambda r: r.update(input_pixel_sha256=["0" * 64] * len(r["input_pixel_sha256"])))
    expect_reject("tamper_image_hash_field_rejected", lambda: RUN.verify_completion(str(d), REQ, PRO))
    d = fresh("tensorcount")
    edit_first_record(d, lambda r: r.update(n_image_tokens=r["n_image_tokens"] - 256))
    expect_reject("tamper_image_token_count_rejected", lambda: RUN.verify_completion(str(d), REQ, PRO))
    # 요청·protocol·가중치 lock 변조
    alt_req = tdir / "requests_altered.jsonl"
    rows = [json.loads(l) for l in open(ROOT / REQ)]
    rows[0]["prompt"] += " "
    alt_req.write_text("".join(json.dumps(r) + "\n" for r in rows))
    expect_reject("altered_requests_file_rejected_by_protocol", lambda: RUN.verify_protocol(PRO, str(alt_req)))
    # 영상(crop) 파일 hash 변조: 사본 요청 행의 file hash를 바꾸면 현재 영상 대조에서 거부
    rows = [json.loads(l) for l in open(ROOT / REQ)]
    rows[0]["images"][-1]["file_sha256"] = "1" * 64
    alt2 = tdir / "requests_filehash.jsonl"
    alt2.write_text("".join(json.dumps(r) + "\n" for r in rows))
    p = json.load(open(ROOT / PRO))
    p2 = tdir / "protocol_filehash.json"
    p["requests_sha256"] = RUN.file_sha(str(alt2))
    json.dump(p, open(p2, "w"))
    expect_reject("image_file_hash_mismatch_rejected", lambda: RUN.verify_records(str(base), str(alt2), str(p2)))
    pw = json.load(open(ROOT / PRO))
    pw["weights"]["model-00001-of-00002.safetensors"]["sha256"] = "0" * 64
    pwp = tdir / "protocol_weights.json"
    json.dump(pw, open(pwp, "w"))
    expect_reject("weights_digest_mismatch_rejected", lambda: RUN.verify_weights(json.load(open(pwp))))
    check("weights_digest_match_real", RUN.verify_weights(json.load(open(ROOT / PRO))) > 0)
    # SIGKILL 후 재개 (torn tail은 kill 후 부분 행을 덧붙여 재현)
    kd = GEN / "kill"
    kd.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="0")
    pr = subprocess.Popen([sys.executable, "ev108_run.py", "worker", "--requests", REQ, "--protocol", PRO, "--out-dir", str(kd), "--worker", "0"],
                          cwd=ROOT, env=env, stdout=open(kd / "worker0.kill.stdout", "a"), stderr=open(kd / "worker0.kill.stderr", "a"))
    t0 = time.time()
    n = 0
    while time.time() - t0 < 400 and pr.poll() is None:
        time.sleep(1)
        fn = kd / "gen_worker0.jsonl"
        n = sum(1 for _ in open(fn)) if fn.exists() else 0
        if n >= 7:
            break
    killed = pr.poll() is None
    if killed:
        pr.send_signal(signal.SIGKILL)
        pr.wait()
    with open(kd / "gen_worker0.jsonl", "ab") as fh:
        fh.write(b'{"request_id": "partial-torn')
    n_before = sum(1 for l in open(kd / "gen_worker0.jsonl") if l.strip().endswith("}"))
    pre_digests = {r_["request_id"]: r_["record_digest"] for r_ in RUN.read_records(str(kd / "gen_worker0.jsonl"))}
    check("kill_happened_with_partial_records", killed and 7 <= n_before < 42, {"n_complete_lines": n_before, "killed": killed})
    rc = subprocess.run([sys.executable, "ev108_run.py", "launch", "--requests", REQ, "--protocol", PRO, "--out-dir", str(kd), "--workers", "2",
                         "--peak-gb", "12"], cwd=ROOT).returncode
    check("resume_after_kill_completes", rc == 0 and (kd / "completion.json").exists(), rc)
    if (kd / "completion.json").exists():
        RUN.verify_completion(str(kd), REQ, PRO)
        ok, n_ = same_outputs(base, kd)
        check("outputs_identical_w2_vs_kill_resume", ok, n_)
        repair = list(kd.glob("gen_worker0.jsonl.repair.log"))
        check("torn_tail_preserved_and_logged", bool(repair) and bool(list(kd.glob("gen_worker0.jsonl.partial.*.bin"))))
        fin = recs_of(kd)
        check("pre_kill_records_preserved", all(fin.get(k, {}).get("record_digest") == v for k, v in pre_digests.items()) and len(pre_digests) >= 7, len(pre_digests))
    # admission 거부 기록
    ad = GEN / "admission"
    rc = subprocess.run([sys.executable, "ev108_run.py", "launch", "--requests", REQ, "--protocol", PRO, "--out-dir", str(ad), "--workers", "4", "--peak-gb", "30"],
                        cwd=ROOT, capture_output=True).returncode
    ends = sorted(glob.glob(str(ad / "launch_*.end.json")))
    st = json.load(open(ends[-1])) if ends else {}
    check("admission_refusal_recorded", rc != 0 and st.get("status") == "error" and st.get("admission", {}).get("refused") is True, st.get("admission"))
    check("no_completion_written_on_refusal", not (ad / "completion.json").exists())
    json.dump({"n": len(CHECKS), "n_pass": sum(c["pass"] for c in CHECKS), "perf": perf, "checks": CHECKS}, open(out, "x"), indent=1, default=str)
    print(f"{sum(c['pass'] for c in CHECKS)}/{len(CHECKS)} pass")
    print(json.dumps(perf, indent=1))
    for c in CHECKS:
        if not c["pass"]:
            print("FAIL", c["name"], str(c["detail"])[:200])


if __name__ == "__main__":
    main()
