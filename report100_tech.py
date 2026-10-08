"""iter_100 기술 검사(D8 12요청): 2 worker 처리량·peak, 가능하면 4 worker, 중단(limit)→재개, 완료 후 재실행, 요청/완료 변조 거부, worker 수 간 token 정합성.

내용 정답률은 gate가 아니다. 각 단계는 새 out 디렉터리를 쓰고 기존 결과를 덮어쓰지 않는다. 단계는 --step으로 하나씩 실행한다(재시작 가능).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from report86_common import read_jsonl_complete, save, sha

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results" / "iter_100"
REQ = OUT / "data" / "D8" / "requests.json"
TECH = OUT / "tech"


class Sampler(threading.Thread):
    """1초 간격으로 GPU별 used 메모리와 프로세스별 점유를 기록한다(관측 peak)."""

    def __init__(self):
        super().__init__(daemon=True)
        self.stop = threading.Event()
        self.peak = {}
        self.proc_peak = {}
        self.n = 0

    def run(self):
        while not self.stop.is_set():
            try:
                g = subprocess.check_output(["nvidia-smi", "--query-gpu=index,memory.used", "--format=csv,noheader,nounits"], text=True)
                for ln in g.splitlines():
                    i, u = [x.strip() for x in ln.split(",")]
                    self.peak[i] = max(self.peak.get(i, 0), int(u))
                p = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"], text=True)
                for ln in p.splitlines():
                    if ln.strip():
                        pid, u = [x.strip() for x in ln.split(",")]
                        self.proc_peak[pid] = max(self.proc_peak.get(pid, 0), int(u))
                self.n += 1
            except Exception:
                pass
            self.stop.wait(1.0)


RESUME_REQ = TECH / "requests_resume8.json"


def resume_requests():
    """재개 검사용 8요청: D8의 N/T 조건만(비EOS 확장이 없던 짧은 요청). 기준은 D8_w2의 같은 요청 token."""
    if not RESUME_REQ.exists():
        TECH.mkdir(parents=True, exist_ok=True)
        save(RESUME_REQ, [r for r in json.loads(REQ.read_text()) if r["id"].endswith("|N") or r["id"].endswith("|T")])
    return RESUME_REQ


def gen(args, out, log, req=None):
    cmd = [sys.executable, "report100_gen.py", "launch", "--requests", str(req or REQ), "--out", str(out)] + args
    with open(str(log) + ".out", "x") as so, open(str(log) + ".err", "x") as se:
        t = time.monotonic()
        rc = subprocess.run(cmd, stdout=so, stderr=se, cwd=str(ROOT)).returncode
    return rc, time.monotonic() - t


def recs(out, workers):
    r = []
    for s in range(workers):
        r += read_jsonl_complete(Path(out) / f"worker_{s}.jsonl")
    return r


def toks(r):
    return [x["suffix_ids"] for x in r["attempts"]]


def summarize(out, workers, wall, smp):
    r = recs(out, workers)
    n_new = [x["attempts"][-1]["n_new"] for x in r]
    return dict(n_records=len(r), n_unique=len(set(x["id"] for x in r)), all_eos=all(x["attempts"][-1]["ended_eos"] for x in r),
                n_attempts=[len(x["attempts"]) for x in r], input_tokens=[len(x["input_ids"]) for x in r], new_tokens=n_new,
                wall_s=wall, req_per_min=len(r) / wall * 60 if wall else None, gpu_peak_used_mib=smp.peak, proc_peak_mib=smp.proc_peak,
                gpus=sorted(set(x["gpu"] for x in r)))


def step(name, args, workers, req=None):
    out = OUT / "gen" / name
    if out.exists():
        raise SystemExit("exists: %s" % out)
    TECH.mkdir(parents=True, exist_ok=True)
    smp = Sampler()
    smp.start()
    rc, wall = gen(args + ["--workers", str(workers)], out, TECH / name, req)
    smp.stop.set()
    res = dict(name=name, rc=rc, workers=workers, args=args, **(summarize(out, workers, wall, smp) if out.exists() else dict(wall_s=wall)))
    save(TECH / f"{name}.json", res)
    print(json.dumps({k: res[k] for k in ("name", "rc", "n_records", "req_per_min", "gpu_peak_used_mib") if k in res}))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["w2", "w4", "resume_a", "resume_b", "rerun", "tamper"])
    ap.add_argument("--peak-mib", type=int, default=12000)
    a = ap.parse_args()
    pk = ["--peak-mib", str(a.peak_mib)]
    if a.step == "w2":
        step("D8_w2", pk, 2)
    elif a.step == "w4":
        step("D8_w4", pk, 4)
    elif a.step == "resume_a":
        step("D8_resume", pk + ["--limit", "2"], 2, resume_requests())
    elif a.step == "resume_b":
        out = OUT / "gen" / "D8_resume"
        smp = Sampler()
        smp.start()
        rc, wall = gen(pk + ["--workers", "2"], out, TECH / "D8_resume_b", resume_requests())
        smp.stop.set()
        res = dict(name="D8_resume_b", rc=rc, **summarize(out, 2, wall, smp))
        save(TECH / "D8_resume_b.json", res)
        print(json.dumps({k: res[k] for k in ("rc", "n_records")}))
    elif a.step == "rerun":
        out = OUT / "gen" / "D8_w2"
        before = dict((p.name, sha(p)) for p in sorted(out.glob("worker_*.jsonl")))
        rc, wall = gen(pk + ["--workers", "2"], out, TECH / "D8_w2_rerun")
        after = dict((p.name, sha(p)) for p in sorted(out.glob("worker_*.jsonl")))
        save(TECH / "D8_w2_rerun.json", dict(rc=rc, unchanged=before == after, wall_s=wall))
        print(rc, before == after)
    elif a.step == "tamper":
        base = OUT / "gen" / "D8_w2"
        res = {}
        # (1) 다른 요청 파일로 같은 출력 경로 재실행 -> 거부
        sub = TECH / "requests_subset.json"
        save(sub, json.loads(REQ.read_text())[:11])
        cmd = [sys.executable, "report100_gen.py", "launch", "--requests", str(sub), "--out", str(base), "--workers", "2"] + pk
        with open(str(TECH / "tamper_requests.out"), "x") as so, open(str(TECH / "tamper_requests.err"), "x") as se:
            res["changed_requests_rc"] = subprocess.run(cmd, stdout=so, stderr=se, cwd=str(ROOT)).returncode
        # (2) 완료 사본의 worker 출력 한 글자 변조 -> 거부(원본은 건드리지 않고 복사본에서 시험)
        cp = OUT / "gen" / "D8_w2_tampered_copy"
        shutil.copytree(base, cp, ignore=shutil.ignore_patterns("launcher.lock", "worker_*.lock", "*.log"))
        w = cp / "worker_0.jsonl"
        data = w.read_text()
        w.write_text(data.replace('"text": "', '"text": "X', 1))
        cmd = [sys.executable, "report100_gen.py", "launch", "--requests", str(REQ), "--out", str(cp), "--workers", "2"] + pk
        with open(str(TECH / "tamper_output.out"), "x") as so, open(str(TECH / "tamper_output.err"), "x") as se:
            res["tampered_output_rc"] = subprocess.run(cmd, stdout=so, stderr=se, cwd=str(ROOT)).returncode
        # (3) 요청 prompt 변조 사본
        rq = json.loads(REQ.read_text())
        rq[0]["prompt"] += " "
        bad = TECH / "requests_prompt_changed.json"
        save(bad, rq)
        cmd = [sys.executable, "report100_gen.py", "launch", "--requests", str(bad), "--out", str(base), "--workers", "2"] + pk
        with open(str(TECH / "tamper_prompt.out"), "x") as so, open(str(TECH / "tamper_prompt.err"), "x") as se:
            res["changed_prompt_rc"] = subprocess.run(cmd, stdout=so, stderr=se, cwd=str(ROOT)).returncode
        res["original_unchanged"] = sha(base / "worker_0.jsonl") == json.loads((base / "completion.json").read_text())["files"][str(base / "worker_0.jsonl")]
        save(TECH / "tamper_result.json", res)
        print(res)


if __name__ == "__main__":
    main()
