"""iter_069 실제 중단·재개 검사 (두 모델 병렬, 모델당 GPU 1장). 기술 요청 14건 사용.

절차: (1) w0 3행 저장 직후 강제 종료(답변 행은 저장, .cost 행 없음) (2) w0 재시작 후 2행째에 torn tail로 종료
      (3) w1이 torn tail 파일을 읽으며(완결 행만 인식) 2건 처리 (4) w0 재시작: torn tail 보존·제거 후 나머지 완료
      (5) verify: 중복·누락 0, protocol 연결 / 기준 tech 실행과 suffix token 일치 (6) 중간 손상 행 거부.
결과: results/iter_069/tests/resume_<model>.json
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import threading

import m65_run as B

RESULT = {}
PROTO = {"medgemma": "results/iter_069/protocol/protocol_medgemma_v2.json", "qwen": "results/iter_069/protocol/protocol_qwen_v2.json"}
GPU = {"medgemma": "0", "qwen": "1"}
REQ = "results/iter_069/data/requests_tech.jsonl"


def worker(model, od, w, *extra):
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=GPU[model])
    p = subprocess.run([sys.executable, "dd69_run.py", "worker", "--model", model, "--requests", REQ, "--protocol", PROTO[model],
                        "--out-dir", od, "--worker", str(w), *extra], env=env, capture_output=True, text=True)
    return p.returncode, p.stdout[-300:] + p.stderr[-300:]


def run(model):
    od = f"results/iter_069/tests/resume_{model}"
    steps = []
    steps.append(("w0 die-after-3-writes", worker(model, od, 0, "--die-after-write", "3")[0]))
    steps.append(("w0 restart torn-after-2", worker(model, od, 0, "--torn-after", "2")[0]))
    raw = open(f"{od}/worker0.jsonl", "rb").read()
    torn = bool(raw) and not raw.endswith(b"\n")
    n_complete_before_w1 = len(B.read_jsonl(f"{od}/worker0.jsonl"))
    steps.append(("w1 limit2 while w0 has torn tail", worker(model, od, 1, "--limit", "2")[0]))
    steps.append(("w0 restart finish", worker(model, od, 0)[0]))
    corrupt = glob.glob(f"{od}/worker0.jsonl.corrupt_*")
    p = subprocess.run([sys.executable, "dd69_run.py", "verify", "--model", model, "--protocol", PROTO[model], "--out-dir", od, "--requests", REQ],
                       env=dict(os.environ, CUDA_VISIBLE_DEVICES=GPU[model]), capture_output=True, text=True)
    ver = json.load(open(f"{od}/verify.json"))
    ref = {}
    for f in glob.glob(f"results/iter_069/gen/tech_{model}/worker*.jsonl"):
        for r in B.read_jsonl(f):
            ref[r["rid"]] = r["attempts"][-1]["suffix_ids"]
    cur = {}
    for f in glob.glob(f"{od}/worker*.jsonl"):
        for r in B.read_jsonl(f):
            cur[r["rid"]] = r["attempts"][-1]["suffix_ids"]
    tok_mismatch = [k for k in ref if cur.get(k) != ref[k]]
    # 중간 손상 행 거부
    cd = f"results/iter_069/tests/resume_{model}_midcorrupt"
    os.makedirs(cd, exist_ok=True)
    lines = open(f"{od}/worker0.jsonl").read().splitlines()
    lines[0] = lines[0][:40] + "#CORRUPT#" + lines[0][40:]
    open(f"{cd}/worker0.jsonl", "w").write("\n".join(lines) + "\n")
    rc_mid, _ = worker(model, cd, 1, "--limit", "1")
    RESULT[model] = {"steps": steps, "torn_tail_existed_before_w1": torn, "n_complete_rows_before_w1": n_complete_before_w1,
                     "preserved_corrupt_tail_files": len(corrupt), "verify_rc": p.returncode, "verify": {k: v for k, v in ver.items() if k != "record_file_sha256"},
                     "n_records": ver["n_records"], "n_unique": len(cur), "token_mismatch_vs_tech_run": tok_mismatch,
                     "mid_corruption_worker_rc": rc_mid, "mid_corruption_rejected": rc_mid != 0}


def main():
    ts = [threading.Thread(target=run, args=(m,)) for m in ("medgemma", "qwen")]
    [t.start() for t in ts]
    [t.join() for t in ts]
    ok = True
    for m, r in RESULT.items():
        exp_ok = (r["verify_rc"] == 0 and r["n_records"] == 14 and r["n_unique"] == 14 and not r["token_mismatch_vs_tech_run"]
                  and r["torn_tail_existed_before_w1"] and r["preserved_corrupt_tail_files"] >= 1 and r["mid_corruption_rejected"]
                  and r["steps"][0][1] == 9 and r["steps"][1][1] == 9)
        r["pass"] = exp_ok
        ok &= exp_ok
        with open(f"results/iter_069/tests/resume_{m}.json", "x") as f:
            json.dump(r, f, indent=1)
        print(m, "PASS" if exp_ok else "FAIL", {k: r[k] for k in ("steps", "n_records", "token_mismatch_vs_tech_run", "mid_corruption_rejected")})
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
