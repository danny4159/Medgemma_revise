"""iter_106 실행 경로 검사: (1) 통제된 중단→torn tail→재개, 기존 D4_w2와 token 일치, (2) completion/출력 변조 거부, (3) 요청 집합 변조·중복 거부.
결과: results/iter_106/tests/run_path_tests.json (새 파일만). 사용: python lk106_runtests.py"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import lk106_run as R
from report86_common import ROOT, sha_obj, save, read_jsonl_complete, record_digest

BASE = R.R106 / "gen/D4_w2"
RES = R.R106 / "gen/D4_resume"
TESTS = R.R106 / "tests"


def launch(out, limit=0):
    cmd = [sys.executable, str(ROOT / "lk106_run.py"), "launch", "--stage", "D4", "--out", str(out), "--workers", "2", "--stagger", "5"]
    if limit:
        cmd += ["--limit", str(limit)]
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def outs(d, k):
    return read_jsonl_complete(R.shard_dir(d, "CURE", k) / "outputs.jsonl")


def main():
    res = []

    def chk(name, ok, detail=None):
        res.append({"name": name, "pass": bool(ok), "detail": detail})
        print(name, ok, flush=True)

    p1 = launch(RES, limit=2)
    n_after_limit = [len(outs(RES, k)) for k in (0, 1)]
    chk("limit_run_partial", p1.returncode == 0 and n_after_limit == [2, 2] and not (RES / "completion_CURE.json").exists(), {"rc": p1.returncode, "n": n_after_limit})
    # torn tail: 개행 없는 부분 행을 shard0 끝에 붙인다
    with (R.shard_dir(RES, "CURE", 0) / "outputs.jsonl").open("a") as f:
        f.write('{"id": "torn-partial", "text": "unfinished')
    p2 = launch(RES)
    chk("resume_completes", p2.returncode == 0 and (RES / "completion_CURE.json").exists(), {"rc": p2.returncode, "stderr": p2.stderr[-300:]})
    sd = sha_obj(R.scientific_protocol("D4", "CURE", 2))
    ok_all = True
    ntok = 0
    for k in (0, 1):
        R.verify_completion(R.shard_dir(RES, "CURE", k), "D4", "CURE", k, 2, sd)
        a = {r["id"]: r for r in outs(RES, k)}
        b = {r["id"]: r for r in outs(BASE, k)}
        ok_all &= set(a) == set(b) and len(a) == 12
        for i in a:
            ntok += 1
            ok_all &= a[i]["attempts"][-1]["suffix_ids"] == b[i]["attempts"][-1]["suffix_ids"]
    chk("resume_tokens_equal_baseline", ok_all, {"n_compared": ntok})
    ev = [json.loads(l) for l in (R.shard_dir(RES, "CURE", 0) / "executions.jsonl").read_text().splitlines() if l]
    starts = [e for e in ev if e["event"] == "start"]
    chk("two_executions_recorded", len(starts) == 2 and starts[0]["n_done_before"] == 0 and starts[1]["n_done_before"] == 2, [e["n_done_before"] for e in starts])
    # 변조 거부: 정상 사본에서 하나씩 변조하고 verify_completion이 AssertionError를 내야 한다
    def mutate(name, fn):
        d = TESTS / f"mut_{name}"
        shutil.copytree(BASE / "cure/shard0", d / "cure/shard0")
        fn(d / "cure/shard0")
        try:
            R.verify_completion(d / "cure/shard0", "D4", "CURE", 0, 2, sd)
            chk(f"reject_{name}", False, "accepted")
        except (AssertionError, KeyError, json.JSONDecodeError, FileNotFoundError, ValueError) as e:
            chk(f"reject_{name}", True, type(e).__name__ + ": " + str(e)[:80])

    # 정상 사본은 통과해야 한다
    d = TESTS / "mut_control"
    shutil.copytree(BASE / "cure/shard0", d / "cure/shard0")
    try:
        R.verify_completion(d / "cure/shard0", "D4", "CURE", 0, 2, sd)
        chk("accept_control_copy", True)
    except Exception as e:
        chk("accept_control_copy", False, str(e))

    def edit_text(sd_):
        rs = [json.loads(l) for l in (sd_ / "outputs.jsonl").read_text().splitlines()]
        rs[0]["text"] = rs[0]["text"] + " x"
        (sd_ / "outputs.jsonl").write_text("\n".join(json.dumps(r) for r in rs) + "\n")

    def edit_text_fix_digest(sd_):  # 내용·record_digest까지 고쳐도 completion의 파일 hash가 막아야 한다
        rs = [json.loads(l) for l in (sd_ / "outputs.jsonl").read_text().splitlines()]
        rs[0]["text"] = rs[0]["text"] + " x"
        rs[0]["record_digest"] = record_digest(rs[0])
        (sd_ / "outputs.jsonl").write_text("\n".join(json.dumps(r) for r in rs) + "\n")

    def drop_row(sd_):
        rs = (sd_ / "outputs.jsonl").read_text().splitlines()
        (sd_ / "outputs.jsonl").write_text("\n".join(rs[:-1]) + "\n")

    def dup_row(sd_):
        rs = (sd_ / "outputs.jsonl").read_text().splitlines()
        (sd_ / "outputs.jsonl").write_text("\n".join(rs + [rs[0]]) + "\n")

    def edit_completion_hash(sd_):
        c = json.loads((sd_ / "completion.json").read_text())
        c["files"]["outputs.jsonl"] = "0" * 64
        (sd_ / "completion.json").write_text(json.dumps(c))

    def fake_prompt_and_rehash(sd_):  # 요청 prompt 변조를 완료 hash까지 맞춰도 요청 집합 대조가 막아야 한다
        rs = [json.loads(l) for l in (sd_ / "outputs.jsonl").read_text().splitlines()]
        rs[0]["prompt"] = rs[0]["prompt"] + " "
        rs[0]["record_digest"] = record_digest(rs[0])
        (sd_ / "outputs.jsonl").write_text("\n".join(json.dumps(r) for r in rs) + "\n")
        c = json.loads((sd_ / "completion.json").read_text())
        from report86_common import sha
        c["files"]["outputs.jsonl"] = sha(sd_ / "outputs.jsonl")
        (sd_ / "completion.json").write_text(json.dumps(c))

    for name, fn in (("text_edit", edit_text), ("text_edit_digest_fixed", edit_text_fix_digest), ("drop_row", drop_row), ("dup_row", dup_row),
                     ("completion_hash", edit_completion_hash), ("prompt_change_rehashed", fake_prompt_and_rehash)):
        mutate(name, fn)
    out = TESTS / "run_path_tests.json"
    save(out, {"all_pass": all(r["pass"] for r in res), "checks": res})
    print("ALL", all(r["pass"] for r in res))
    return 0 if all(r["pass"] for r in res) else 1


if __name__ == "__main__":
    sys.exit(main())
