"""iter_114 nr114_cure 실행 경로 실제 검사 (T4: 개발 4개 요청): 중단·재개(완료 행 보존)+손상 tail, 동시 launcher 거부, 요청 집합/digest 변조 거부, 허용 GPU 밖 배치 거부.
결과 results/iter_114/tests/cure_runtime_checks.json (새 파일)."""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import nr114_cure as C
from report86_common import sha_obj, read_jsonl_complete

RES = {}
PY = sys.executable
BASE = ["launch", "--stage", "T4", "--workers", "1", "--placement", "0", "--stagger", "1"]


def run(out, extra=()):
    return subprocess.run([PY, str(C.ROOT / "nr114_cure.py")] + BASE + ["--out", out] + list(extra), cwd=C.ROOT, capture_output=True, text=True)


def expect_fail(fn, label):
    try:
        fn()
    except BaseException as e:
        RES[label] = {"rejected": True, "error": repr(e)[:160]}
        return
    RES[label] = {"rejected": False}


def main():
    out = C.R114 / "cure/T4_resume"
    p = run(str(out), ["--limit", "2"])
    f = C.shard_dir(out, 0) / "outputs.jsonl"
    rows1 = read_jsonl_complete(f)
    RES["resume_part1"] = {"rc": p.returncode, "n_records": len(rows1), "completion_exists": (C.shard_dir(out, 0) / "completion.json").exists()}
    with f.open("ab") as fh:
        fh.write(b'{"id": "torn')
    p = run(str(out))
    partials = list(C.shard_dir(out, 0).glob("outputs.jsonl.partial.*"))
    recs = read_jsonl_complete(f)
    ref = {}
    for s in (0, 1):
        for r in read_jsonl_complete(C.R114 / f"cure/T4_w2/cure/shard{s}/outputs.jsonl"):
            ref[r["id"]] = r
    RES["resume_part2"] = {"rc": p.returncode, "n_partial_files": len(partials), "completion": (out / "completion.json").exists(), "n_records": len(recs),
                          "first_rows_preserved": [r["record_digest"] for r in recs[:len(rows1)]] == [r["record_digest"] for r in rows1],
                          "suffix_ids_equal_to_T4_w2": all(r["attempts"][-1]["suffix_ids"] == ref[r["id"]]["attempts"][-1]["suffix_ids"] for r in recs),
                          "executions": sum(1 for l in (C.shard_dir(out, 0) / "executions.jsonl").read_text().splitlines() if '"start"' in l),
                          "stderr_tail": p.stderr[-200:]}
    # 동시 launcher
    out2 = C.R114 / "cure/T4_concurrent"
    cmd = [PY, str(C.ROOT / "nr114_cure.py")] + BASE + ["--out", str(out2)]
    p1 = subprocess.Popen(cmd, cwd=C.ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(8)
    p2 = subprocess.run(cmd, cwd=C.ROOT, capture_output=True, text=True)
    p1.communicate()
    RES["concurrent_launcher"] = {"second_rc": p2.returncode, "blocked": "BlockingIOError" in p2.stderr, "first_rc": p1.returncode,
                                  "first_complete": (out2 / "completion.json").exists()}
    # 변조
    t = C.R114 / "cure/T4_tamper"
    if t.exists():
        shutil.rmtree(t)
    shutil.copytree(out, t)
    sd = sha_obj(C.scientific_protocol("T4", 1))
    d = C.shard_dir(t, 0)
    rows = (d / "outputs.jsonl").read_text().splitlines()

    def write(r):
        (d / "outputs.jsonl").write_text("\n".join(r) + "\n")

    def verify():
        c = json.loads((d / "completion.json").read_text())
        c["files"]["outputs.jsonl"] = C.sha(d / "outputs.jsonl")
        (d / "completion.json").write_text(json.dumps(c))
        C.verify_completion(d, "T4", 0, 1, sd)

    r0 = json.loads(rows[0])
    r0["text"] = r0["text"] + " [0.1,0.1,0.2,0.2]"
    write([json.dumps(r0)] + rows[1:])
    expect_fail(verify, "tamper_text_edit")
    write(rows[1:])
    expect_fail(verify, "tamper_missing_request")
    write(rows + [rows[0]])
    expect_fail(verify, "tamper_duplicate")
    r1 = json.loads(rows[1])
    r1["id"] = "x|CURE|pg-f9"
    r1["record_digest"] = C.record_digest(r1)
    write(rows[:1] + [json.dumps(r1)] + rows[2:])
    expect_fail(verify, "tamper_foreign_id")
    r2 = json.loads(rows[2])
    r2["protocol_digest"] = "f" * 64
    r2["record_digest"] = C.record_digest(r2)
    write(rows[:2] + [json.dumps(r2)] + rows[3:])
    expect_fail(verify, "tamper_protocol_digest")
    write(rows)
    # 저장된 scientific protocol 의 source hash 변조 → worker 거부(모델 적재 전)
    sp = json.loads((d / "scientific_protocol.json").read_text())
    sp["scientific"]["source_sha256"]["pg43_run.py"] = "0" * 64
    (d / "scientific_protocol.json").write_text(json.dumps(sp))
    env = dict(os.environ)
    env["CUDA_VISIBLE_DEVICES"] = "0,1"
    pw = subprocess.run([str(C.CURE_PY), str(C.ROOT / "nr114_cure.py"), "worker", "--stage", "T4", "--out", str(t), "--gpu", "0", "--shard", "0", "--nshards", "1"],
                        cwd=C.ROOT, capture_output=True, text=True, env=env)
    RES["tamper_stored_protocol_source"] = {"rc": pw.returncode, "rejected_before_model_load": "protocol/source/shard mismatch" in pw.stderr}
    p = subprocess.run([PY, str(C.ROOT / "nr114_cure.py"), "launch", "--stage", "T4", "--workers", "1", "--placement", "7", "--out", str(C.R114 / "cure/T4_badgpu")],
                       cwd=C.ROOT, capture_output=True, text=True)
    RES["placement_outside_allowed"] = {"rc": p.returncode, "rejected": "placement outside allowed" in p.stderr or "AssertionError" in p.stderr}
    with (C.R114 / "tests/cure_runtime_checks.json").open("x") as fh:
        json.dump(RES, fh, indent=1)
    print(json.dumps(RES, indent=1))


if __name__ == "__main__":
    main()
