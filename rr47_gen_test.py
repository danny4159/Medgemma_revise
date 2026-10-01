"""iter_047 D8 실행 검사: (1) 2/4 worker 출력 정합성, (2) 실제 SIGKILL 중단·재개, (3) 변조·중복·누락·wrong config·동시 launcher 거부.
python rr47_gen_test.py compare  --a DIR --b DIR --out JSON
python rr47_gen_test.py resume   --base DIR --out-dir DIR --requests R --protocol P --workers 4 --kill-after N --out JSON
python rr47_gen_test.py tamper   --src DIR --protocol P --requests R --out JSON
결과 JSON은 기존 파일을 덮어쓰지 않는다.
"""
import argparse
import glob
import json
import os
import shutil
import signal
import subprocess
import sys
import time

import pg43_run as PR
import rr47_run


def load(d):
    recs = {}
    for f in sorted(glob.glob(os.path.join(d, "gen_worker*.jsonl"))):
        for r in PR.read_records(f):
            recs[r["request_id"]] = r
    return recs


def write_new(path, obj):
    if os.path.exists(path):
        sys.exit(f"refuse to overwrite {path}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(obj, open(path + ".tmp", "w"), indent=1, default=str)
    os.replace(path + ".tmp", path)


def compare(a, b):
    A, B = load(a), load(b)
    common = sorted(set(A) & set(B))
    mism = [r for r in common if A[r]["suffix_ids"] != B[r]["suffix_ids"] or A[r]["input_ids_sha256"] != B[r]["input_ids_sha256"]]
    return dict(a=a, b=b, n_a=len(A), n_b=len(B), n_common=len(common), token_mismatch=len(mism), mismatched_ids=mism[:10],
                only_a=len(set(A) - set(B)), only_b=len(set(B) - set(A)))


def resume(a):
    if os.path.exists(a.out_dir):
        sys.exit("resume out-dir exists")
    cmd = [sys.executable, "pg43_run.py", "launch", "--requests", a.requests, "--protocol", a.protocol, "--out-dir", a.out_dir,
           "--workers", str(a.workers), "--peak-gb", "8.5"]
    p = subprocess.Popen(cmd, start_new_session=True, stdout=open(a.out_dir + ".launch1.stdout", "w"), stderr=subprocess.STDOUT)
    n = 0
    t0 = time.time()
    while time.time() - t0 < 900:
        time.sleep(3)
        n = sum(len(PR.read_records(f)) for f in glob.glob(os.path.join(a.out_dir, "gen_worker*.jsonl")))
        if n >= a.kill_after or p.poll() is not None:
            break
    killed = p.poll() is None
    if killed:
        os.killpg(p.pid, signal.SIGKILL)
    p.wait()
    time.sleep(5)
    n_at_kill = sum(len(PR.read_records(f)) for f in glob.glob(os.path.join(a.out_dir, "gen_worker*.jsonl")))
    partial_bytes = []
    for f in glob.glob(os.path.join(a.out_dir, "gen_worker*.jsonl")):
        data = open(f, "rb").read()
        partial_bytes.append(dict(file=os.path.basename(f), ends_with_newline=data.endswith(b"\n") or not data))
    p2 = subprocess.run(cmd, capture_output=True, text=True)
    comp = os.path.exists(os.path.join(a.out_dir, "completion.json"))
    res = compare(a.base, a.out_dir)
    res.update(killed_midrun=killed, records_at_kill=n_at_kill, partial_tails=partial_bytes, relaunch_rc=p2.returncode, relaunch_stdout=p2.stdout[-300:],
               completion_written=comp, repair_logs=sorted(os.path.basename(f) for f in glob.glob(os.path.join(a.out_dir, "*.repair.log"))),
               preserved_partial_files=sorted(os.path.basename(f) for f in glob.glob(os.path.join(a.out_dir, "*.partial.*.bin"))))
    if comp:
        rr47_run.verify(a.out_dir, "D8", a.protocol)
        res["verify_after_resume"] = "ok"
    return res


def expect_reject(name, fn, out):
    try:
        fn()
        out.append(dict(name=name, rejected=False))
    except PR.RunError as e:
        out.append(dict(name=name, rejected=True, error=str(e)[:160]))
    except Exception as e:  # 다른 종류의 오류는 의도한 검증 분기가 아니므로 기록하되 거부로 세지 않는다
        out.append(dict(name=name, rejected=False, other_error=repr(e)[:200]))


def tamper(a):
    root = os.path.join(os.path.dirname(a.src.rstrip("/")), "tamper_work_" + os.path.splitext(os.path.basename(a.out))[0])
    if os.path.exists(root):
        sys.exit("tamper_work exists")
    res = []
    shutil.copytree(a.src, root + "_base")
    base = root + "_base"
    stage = "D8"
    # 0. 변조 전 정상 확인
    rr47_run.verify(base, stage, a.protocol)
    res.append(dict(name="unmodified copy verifies", rejected=False, expected_pass=True))
    files = sorted(glob.glob(os.path.join(base, "gen_worker*.jsonl")))

    def fresh(tag):
        d = f"{root}_{tag}"
        shutil.copytree(base, d)
        return d

    d = fresh("digest")  # record 내용 변경 (digest 불일치)
    f = sorted(glob.glob(os.path.join(d, "gen_worker*.jsonl")))[0]
    lines = open(f).read().split("\n")
    r = json.loads(lines[0])
    r["suffix_text_raw"] = r["suffix_text_raw"].replace("absent", "present", 1)
    lines[0] = json.dumps(r)
    open(f, "w").write("\n".join(lines))
    expect_reject("edited record content (record_digest/file hash)", lambda: rr47_run.verify(d, stage, a.protocol), res)
    d = fresh("dup")  # 중복 record
    f = sorted(glob.glob(os.path.join(d, "gen_worker*.jsonl")))[0]
    first = open(f).read().split("\n")[0]
    open(f, "a").write(first + "\n")
    expect_reject("duplicated record line", lambda: rr47_run.verify(d, stage, a.protocol), res)
    d = fresh("miss")  # 누락 record
    f = sorted(glob.glob(os.path.join(d, "gen_worker*.jsonl")))[0]
    ln = open(f).read().split("\n")
    open(f, "w").write("\n".join(ln[1:]))
    expect_reject("missing record line", lambda: rr47_run.verify(d, stage, a.protocol), res)
    d = fresh("exit")  # completion 종료 코드 변조
    c = json.load(open(os.path.join(d, "completion.json")))
    c["exit_codes"][0] = 1
    json.dump(c, open(os.path.join(d, "completion.json"), "w"))
    expect_reject("completion exit code != 0", lambda: rr47_run.verify(d, stage, a.protocol), res)
    d = fresh("proto")  # wrong config: 다른 코드 hash의 구 protocol
    expect_reject("wrong protocol (v1, code locked at different hash)", lambda: rr47_run.verify(d, stage, "results/iter_047/protocol/protocol_D8_v1.json"), res)
    d = fresh("reqs")  # 요청 파일 변조
    req2 = d + "/requests_altered.jsonl"
    rows = open(a.requests).read().split("\n")
    r0 = json.loads(rows[0])
    r0["prompt"] = r0["prompt"] + " "
    rows[0] = json.dumps(r0, sort_keys=True)
    open(req2, "w").write("\n".join(rows))
    expect_reject("altered request file vs protocol lock", lambda: PR.verify_completion(d, req2, a.protocol), res)
    d = fresh("adapter")  # record가 adapter를 썼다고 변조 -> digest 불일치
    f = sorted(glob.glob(os.path.join(d, "gen_worker*.jsonl")))[0]
    lines = open(f).read().split("\n")
    r = json.loads(lines[0])
    r["adapter_digest"] = "deadbeef"
    lines[0] = json.dumps(r)
    open(f, "w").write("\n".join(lines))
    expect_reject("record claims adapter use", lambda: rr47_run.verify(d, stage, a.protocol), res)
    # --- 공격자가 completion의 worker 파일 hash까지 맞춘 경우: 파일 hash가 아니라 record 내부 검증 분기가 실패해야 한다 ---
    def rehash(d):
        c = json.load(open(os.path.join(d, "completion.json")))
        for fn in c["worker_file_sha256"]:
            c["worker_file_sha256"][fn] = PR.file_sha(os.path.join(d, fn))
        json.dump(c, open(os.path.join(d, "completion.json"), "w"))

    def edit_first(d, fn_edit, redigest):
        f = sorted(glob.glob(os.path.join(d, "gen_worker*.jsonl")))[0]
        lines = open(f).read().split("\n")
        r = json.loads(lines[0])
        fn_edit(r)
        if redigest:
            r["record_digest"] = PR.record_digest(r)
        lines[0] = json.dumps(r)
        open(f, "w").write("\n".join(lines))
        rehash(d)

    def branch(name, d, want, edit=None, redigest=False, dup=False, drop=False):
        if edit:
            edit_first(d, edit, redigest)
        f = sorted(glob.glob(os.path.join(d, "gen_worker*.jsonl")))[0]
        if dup:
            open(f, "a").write(open(f).read().split("\n")[0] + "\n")
            rehash(d)
        if drop:
            open(f, "w").write("\n".join(open(f).read().split("\n")[1:]))
            rehash(d)
        try:
            rr47_run.verify(d, stage, a.protocol)
            res.append(dict(name=name, rejected=False))
        except PR.RunError as e:
            res.append(dict(name=name, rejected=(want in str(e)), want=want, error=str(e)[:160]))

    branch("[inner] edited content, completion rehashed -> record digest", fresh("b1"), "record digest mismatch",
           edit=lambda r: r.__setitem__("suffix_text_raw", r["suffix_text_raw"] + " "))
    branch("[inner] duplicated line, rehashed -> request set", fresh("b2"), "request set mismatch", dup=True)
    branch("[inner] dropped line, rehashed -> request set", fresh("b3"), "request set mismatch", drop=True)
    branch("[inner] adapter digest set + record re-digested -> adapter/protocol digest", fresh("b4"), "adapter/protocol digest mismatch",
           edit=lambda r: r.__setitem__("adapter_digest", "deadbeef"), redigest=True)
    branch("[inner] row digest edited + re-digested -> record digest", fresh("b5"), "record digest mismatch",
           edit=lambda r: r.__setitem__("row_digest", "00" * 32), redigest=True)
    branch("[inner] prompt hash edited + re-digested -> prompt hash", fresh("b6"), "prompt hash mismatch",
           edit=lambda r: r.__setitem__("prompt_sha256", "11" * 32), redigest=True)

    def txt_edit(d):
        for f in sorted(glob.glob(os.path.join(d, "gen_worker*.jsonl"))):
            lines = open(f).read().split("\n")
            for k, ln in enumerate(lines):
                if ln.strip() and json.loads(ln)["modality"] == "text":
                    r = json.loads(ln)
                    r["n_image_tokens"] = 5
                    r["record_digest"] = PR.record_digest(r)
                    lines[k] = json.dumps(r)
                    open(f, "w").write("\n".join(lines))
                    rehash(d)
                    return
    d = fresh("b7")
    txt_edit(d)
    try:
        rr47_run.verify(d, stage, a.protocol)
        res.append(dict(name="[inner] text-only record with image tokens", rejected=False))
    except PR.RunError as e:
        res.append(dict(name="[inner] text-only record with image tokens", rejected=("text-only record carries image input" in str(e)), error=str(e)[:160]))
    # 동시 launcher: 같은 out-dir launch.lock 을 잡고 있는 동안 두 번째 launcher는 거부해야 한다
    ld = f"{root}_lock"
    os.makedirs(ld)
    fd = PR.try_flock(os.path.join(ld, "launch.lock"))
    r2 = subprocess.run([sys.executable, "pg43_run.py", "launch", "--requests", a.requests, "--protocol", a.protocol, "--out-dir", ld, "--workers", "1"],
                        capture_output=True, text=True)
    os.close(fd)
    res.append(dict(name="concurrent launcher on locked out-dir", rejected=(r2.returncode != 0 and "another launcher" in (r2.stdout + r2.stderr)), rc=r2.returncode,
                    msg=(r2.stdout + r2.stderr)[-120:]))
    r3 = subprocess.run([sys.executable, "pg43_run.py", "launch", "--requests", a.requests, "--protocol", a.protocol, "--out-dir", base, "--workers", "1"],
                        capture_output=True, text=True)
    res.append(dict(name="launch into a completed out-dir", rejected=(r3.returncode != 0 and "completion.json exists" in (r3.stdout + r3.stderr)), rc=r3.returncode))
    tests = [x for x in res if not x.get("expected_pass")]
    return dict(results=res, all_rejected=all(x["rejected"] for x in tests), n_tests=len(tests), root=root)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compare")
    c.add_argument("--a", required=True)
    c.add_argument("--b", required=True)
    c.add_argument("--out", required=True)
    r = sub.add_parser("resume")
    for k in ("base", "out-dir", "requests", "protocol", "out"):
        r.add_argument("--" + k, required=True)
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--kill-after", type=int, default=40)
    t = sub.add_parser("tamper")
    for k in ("src", "protocol", "requests", "out"):
        t.add_argument("--" + k, required=True)
    a = ap.parse_args()
    if a.cmd == "compare":
        write_new(a.out, compare(a.a, a.b))
    elif a.cmd == "resume":
        write_new(a.out, resume(a))
    else:
        write_new(a.out, tamper(a))


if __name__ == "__main__":
    main()
