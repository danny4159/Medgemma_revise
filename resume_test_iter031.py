"""iter_031 통제된 중단·재개 검증: 실제 subprocess를 하드킬(SIGKILL)한 뒤 같은 out-dir로 재개해
완전성·중복 없음·최종 token 일치·lock 회수를 확인한다. results/iter_031/D24/resume_test/에 저장한다.
"""
import glob
import json
import os
import signal
import subprocess
import sys
import time

OUT = "results/iter_031/D24/resume_test"
IDS_FILE = os.path.join(OUT, "ids.json")


def main():
    os.makedirs(OUT, exist_ok=True)
    sm = json.load(open("results/iter_030/source_manifest.json"))
    from rsna_diag import risk30_source as RS
    d24 = RS.select_d24(sm)
    ids = [it["id"] for it in (d24["one_box"][:3] + d24["two_box"][:3])]
    json.dump(ids, open(IDS_FILE, "w"))

    base_cmd = [sys.executable, "-m", "rsna_diag.risk30",
               "--source-manifest", "results/iter_030/source_manifest.json", "--split", "D24",
               "--out-dir", OUT, "--worker", "0", "--protocol", "results/iter_031/protocol_v2.json",
               "--adapter", "results/iter_012/train/lr2e-4_s17/epoch_05", "--gpu", "0",
               "--tasks", "O,F", "--ids", IDS_FILE]

    log1 = open(os.path.join(OUT, "kill1.stdout.log"), "w")
    err1 = open(os.path.join(OUT, "kill1.stderr.log"), "w")
    p1 = subprocess.Popen(base_cmd, stdout=log1, stderr=err1)
    gen_path = os.path.join(OUT, "gen_worker0.jsonl")

    # 첫 record가 쓰일 때까지 기다렸다가(모델 로딩 포함, 최대 180s) 조금 더 진행시킨 뒤 SIGKILL한다.
    t0 = time.time()
    n_seen = 0
    while time.time() - t0 < 180:
        if os.path.exists(gen_path):
            n_seen = sum(1 for ln in open(gen_path) if ln.strip())
            if n_seen >= 1:
                break
        time.sleep(2)
    time.sleep(8)  # 몇 개 더 처리하도록 여유를 준다 (강제 종료 시점을 mid-run으로 만들기 위함)
    p1.send_signal(signal.SIGKILL)
    p1.wait()
    n_before_resume = sum(1 for ln in open(gen_path) if ln.strip()) if os.path.exists(gen_path) else 0

    lock_path = os.path.join(OUT, "worker_0.lock")
    lock_content_after_kill = open(lock_path).read() if os.path.exists(lock_path) else None

    # 재개: 같은 out-dir, 같은 worker id로 다시 실행 (완료까지 기다린다)
    log2 = open(os.path.join(OUT, "resume1.stdout.log"), "w")
    err2 = open(os.path.join(OUT, "resume1.stderr.log"), "w")
    p2 = subprocess.Popen(base_cmd, stdout=log2, stderr=err2)
    rc2 = p2.wait()

    from rsna_diag import risk30
    items = [it for it in (d24["one_box"] + d24["two_box"]) if it["id"] in set(ids)]
    comp = risk30.check_completion(OUT, items, tasks=("O", "F"))
    recs = risk30.load_all(OUT)  # raises on duplicates
    n_bad_o = sum(1 for (pid, t), r in recs.items() if t == "O" and not r["reproduced_expected_suffix"])
    n_bad_fprefix = sum(1 for (pid, t), r in recs.items() if t == "F" and not r["prefix_matches_O"])

    report = {
        "n_seen_before_kill_wait": n_seen, "n_records_at_kill_time": n_before_resume,
        "lock_content_after_kill_raw": lock_content_after_kill,
        "resume_returncode": rc2, "completion": comp, "n_records_final": len(recs),
        "n_bad_o_reproduce": n_bad_o, "n_bad_f_prefix": n_bad_fprefix,
        "expected_records": len(items) * 2,
    }
    ok = (comp["ok"] and len(recs) == len(items) * 2 and n_bad_o == 0 and n_bad_fprefix == 0
         and n_before_resume < len(items) * 2 and rc2 == 0)
    report["ok"] = ok
    json.dump(report, open(os.path.join(OUT, "resume_test_report.json"), "w"), indent=1)
    print(json.dumps(report, indent=1))
    if not ok:
        raise SystemExit("resume test did not meet expectations")


if __name__ == "__main__":
    main()
