"""iter_114 nr114_mg 실행 경로 실제 검사: 완료 행 포함 중단·재개, 손상 tail 복구, 동시 launcher 거부, 요청 집합·protocol 변조 거부, 허용 GPU 밖 배치 거부.
모두 results/iter_114/mg/test_* 와 results/iter_114/tests 아래 새 경로에서 실행한다. DEV(MSPC, 47개)만 사용.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import nr114_mg as N

OUT = N.R114 / "tests"
RES = {}


def run(args, **kw):
    return subprocess.run([sys.executable, str(N.HERE / "nr114_mg.py")] + args, cwd=N.HERE, capture_output=True, text=True, **kw)


def cmp_with(ref_dir, d, nw=1, tol=1e-4):
    ref, _ = N.verify_all(ref_dir, "DEV", "MSPC", 1)
    got, _ = N.verify_all(d, "DEV", "MSPC", nw)
    r = {x["item_key"]: x for x in ref}
    g = {x["item_key"]: x for x in got}
    assert set(r) == set(g)
    mx = 0.0
    for k in r:
        a, b = r[k]["detection"], g[k]["detection"]
        assert len(a["boxes_orig_xyxy"]) == len(b["boxes_orig_xyxy"])
        for (s1, b1), (s2, b2) in zip(sorted(zip(a["scores"], a["boxes_orig_xyxy"]), reverse=True), sorted(zip(b["scores"], b["boxes_orig_xyxy"]), reverse=True)):
            mx = max(mx, abs(s1 - s2), max(abs(x - y) for x, y in zip(b1, b2)))
    return mx


def expect_fail(fn, label):
    try:
        fn()
    except BaseException as e:  # noqa
        RES[label] = {"rejected": True, "error": repr(e)[:200]}
        return
    RES[label] = {"rejected": False}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ref = N.R114 / "mg/DEV_MSPC_w1b4"
    # 1) 중단(limit) -> 손상 tail 주입 -> 재개
    d = N.R114 / "mg/DEV_MSPC_t2_resume"
    p = run(["launch", "--stage", "DEV", "--model", "MSPC", "--workers", "1", "--batch", "4", "--tag", "t2_resume", "--limit", "10", "--placement", "0"])
    rows1 = N.read_complete(d / "raw_worker0.jsonl")
    n1 = len(rows1)
    RES["resume_part1"] = {"rc": p.returncode, "n_records_after_limit": n1, "completion_exists": (d / "completion.json").exists()}
    with (d / "raw_worker0.jsonl").open("ab") as f:
        f.write(b'{"request_id": "torn')
    p = run(["launch", "--stage", "DEV", "--model", "MSPC", "--workers", "1", "--batch", "4", "--tag", "t2_resume", "--placement", "0"])
    partials = list(d.glob("raw_worker0.jsonl.partial.*"))
    RES["resume_part2"] = {"rc": p.returncode, "n_partial_files": len(partials), "partial_bytes": [x.stat().st_size for x in partials],
                          "completion_exists": (d / "completion.json").exists(), "stderr_tail": p.stderr[-300:]}
    RES["resume_part2"]["max_diff_vs_uninterrupted"] = cmp_with(ref, d)
    recs = N.read_complete(d / "raw_worker0.jsonl")
    RES["resume_part2"]["first_rows_preserved"] = [r["record_digest"] for r in recs[:n1]] == [r["record_digest"] for r in rows1]
    RES["resume_part2"]["executions"] = sum(1 for l in (d / "executions0.jsonl").read_text().splitlines() if '"start"' in l)
    RES["resume_part2"]["unique_ids"] = len({r["request_id"] for r in recs})
    # 2) 완료된 실행의 재호출은 기존 출력을 변경하지 않는다
    before = N.sha_file(d / "raw_worker0.jsonl")
    p = run(["launch", "--stage", "DEV", "--model", "MSPC", "--workers", "1", "--batch", "4", "--tag", "t2_resume", "--placement", "0"])
    RES["rerun_completed"] = {"rc": p.returncode, "raw_unchanged": N.sha_file(d / "raw_worker0.jsonl") == before}
    # 3) 동시 launcher 거부
    d2 = N.R114 / "mg/DEV_MSPC_t2_concurrent"
    cmd = [sys.executable, str(N.HERE / "nr114_mg.py"), "launch", "--stage", "DEV", "--model", "MSPC", "--workers", "1", "--batch", "4", "--tag", "t2_concurrent", "--placement", "0"]
    p1 = subprocess.Popen(cmd, cwd=N.HERE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(3)
    p2 = subprocess.run(cmd, cwd=N.HERE, capture_output=True, text=True)
    o1 = p1.communicate()
    RES["concurrent_launcher"] = {"second_rc": p2.returncode, "second_blocked": "BlockingIOError" in p2.stderr or "Resource temporarily" in p2.stderr,
                                  "first_rc": p1.returncode, "first_complete": (d2 / "completion.json").exists(), "second_stderr_tail": p2.stderr[-200:]}
    # 4) 변조 거부 (완료 사본 위에서)
    t = N.R114 / "mg/test_tamper"
    if t.exists():
        shutil.rmtree(t)
    shutil.copytree(d, t)
    rows = (t / "raw_worker0.jsonl").read_text().splitlines()

    def write_rows(r):
        (t / "raw_worker0.jsonl").write_text("\n".join(r) + "\n")

    def verify():
        # completion 의 file hash 도 맞춰 다시 쓴 변조(공격자가 completion 을 갱신)에도 내용 검사가 막는지 본다
        c = json.loads((t / "completion0.json").read_text())
        c["files"]["raw_worker0.jsonl"] = N.sha_file(t / "raw_worker0.jsonl")
        (t / "completion0.json").write_text(json.dumps(c))
        N.verify_all(t, "DEV", "MSPC", 1)

    r0 = json.loads(rows[0])
    r0["detection"]["scores"] = [0.99] * len(r0["detection"]["scores"])
    write_rows([json.dumps(r0)] + rows[1:])
    expect_fail(verify, "tamper_score_edit")
    write_rows(rows[1:])
    expect_fail(verify, "tamper_missing_request")
    write_rows(rows + [rows[0]])
    expect_fail(verify, "tamper_duplicate_request")
    r1 = json.loads(rows[1])
    r1["request_id"] = "0" * 32
    r1["record_digest"] = N.record_digest(r1)
    write_rows(rows[:1] + [json.dumps(r1)] + rows[2:])
    expect_fail(verify, "tamper_foreign_request_id")
    r2 = json.loads(rows[2])
    r2["protocol_digest"] = "f" * 64
    r2["record_digest"] = N.record_digest(r2)
    write_rows(rows[:2] + [json.dumps(r2)] + rows[3:])
    expect_fail(verify, "tamper_protocol_digest")
    write_rows(rows)
    # protocol(source) 변조: 저장된 scientific_protocol 의 source hash 를 바꾸면 worker 가 모델 적재 전에 거부
    sp = json.loads((t / "scientific_protocol0.json").read_text())
    sp["scientific"]["source_sha256"]["mg45_mg.py"] = "0" * 64
    (t / "scientific_protocol0.json").write_text(json.dumps(sp))
    pw = subprocess.run([str(N.VENV_PY), str(N.HERE / "nr114_mg.py"), "worker", "--stage", "DEV", "--model", "MSPC", "--out-dir", str(t), "--gpu", "0",
                         "--worker", "0", "--n-workers", "1", "--batch", "4"], cwd=N.HERE, capture_output=True, text=True,
                        env=dict(os.environ, HF_HUB_OFFLINE="1"))
    RES["tamper_stored_protocol_source"] = {"worker_rc": pw.returncode, "rejected_before_model_load": "protocol/source/shard mismatch" in pw.stderr}
    # 5) 허용 GPU 밖 배치 거부
    p = run(["launch", "--stage", "DEV4", "--model", "A", "--workers", "1", "--batch", "4", "--tag", "t2_badgpu", "--placement", "5"])
    RES["placement_outside_allowed"] = {"rc": p.returncode, "rejected": "placement outside allowed" in p.stderr}
    with (OUT / "mg_runtime_checks.json").open("x") as f:
        json.dump(RES, f, indent=1)
    print(json.dumps(RES, indent=1))


if __name__ == "__main__":
    main()
