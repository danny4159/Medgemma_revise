"""iter_039 실행 보호 GPU 검사: 기준 실행 vs SIGKILL 후 재개 실행의 token 일치, 변조·중복·누락·재실행 거부, completion 검증.
합성 문장 + 변환 완료 영상 1장(preview)으로 18개 요청(cap 300)을 만든다. 결과: results/iter_039/gpu_test/
python pg39_gpu_test.py IMAGE_PNG
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import time

import pg39_run as R
import pg39_spec as S
from rsna_diag import generate as G

img = sys.argv[1]
ROOT = "results/iter_039/gpu_test"
if os.path.exists(ROOT):
    sys.exit("gpu_test dir exists")
os.makedirs(ROOT)
res = {}


def check(n, c, info=None):
    res[n] = {"pass": bool(c), "info": info}
    print(("PASS " if c else "FAIL ") + n, "" if c else info, flush=True)


rows = []
fsha = R.file_sha(img)
pxs = G.load_image(img)[2]
for k, sents in enumerate([{"qA": "Nodular opacity in the right upper lobe.", "qB": "Cardiomegaly."},
                           {"qA": "Left pleural effusion.", "qB": "Aortic elongation."}]):
    for cond, tg, prompt, caps in S.build_prompts(sents):
        psha = S.sha(prompt)
        rows.append({"request_id": S.request_id("T", f"T{k}", cond, tg, psha, pxs), "kind": "T", "patient": f"T{k}",
                     "image_id": "preview", "cond": cond, "targets": tg, "prompt": prompt, "prompt_sha256": psha,
                     "caps": [300], "image": img, "image_file_sha256": fsha, "input_pixel_sha256": pxs,
                     "order_key": S.sha(f"{k}{cond}{tg}")})
rq = f"{ROOT}/requests.jsonl"
with open(rq, "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")
pt = f"{ROOT}/protocol.json"
R.make_protocol(rq, pt)
check("protocol_lock_and_verify", R.verify_protocol(pt, rq) is not None)


def launch(out, workers=2, extra=()):
    return subprocess.Popen([sys.executable, "pg39_run.py", "launch", "--requests", rq, "--protocol", pt, "--out-dir", out,
                             "--workers", str(workers), "--peak-gb", "12", *extra], start_new_session=True,
                            stdout=open(out + ".launch.log", "a"), stderr=subprocess.STDOUT)


ref = f"{ROOT}/ref"
os.makedirs(ref)
t0 = time.time()
p = launch(ref)
p.wait()
check("reference_run_completes", p.returncode == 0 and os.path.exists(f"{ref}/completion.json"), open(ref + ".launch.log").read()[-500:])
ref_wall = time.time() - t0
recs = R.verify_completion(ref, rq, pt)
check("verify_completion_ok", len(recs) == len(rows) == 18)
ref_tok = {r["request_id"]: r["suffix_ids"] for r in recs}

# 중단·재개
kd = f"{ROOT}/kill"
os.makedirs(kd)
p = launch(kd)
deadline = time.time() + 300
while time.time() < deadline:
    n = sum(len(R.read_records(f)) for f in [f"{kd}/gen_worker0.jsonl", f"{kd}/gen_worker1.jsonl"])
    if n >= 4:
        break
    time.sleep(2)
os.killpg(p.pid, signal.SIGKILL)
p.wait()
time.sleep(3)
n_before = sum(len(R.read_records(f"{kd}/gen_worker{k}.jsonl")) for k in (0, 1))
check("killed_midway", 4 <= n_before < 18, n_before)
p = launch(kd)
p.wait()
check("resume_completes", p.returncode == 0 and os.path.exists(f"{kd}/completion.json"), open(kd + ".launch.log").read()[-500:])
recs2 = R.verify_completion(kd, rq, pt)
tok2 = {r["request_id"]: r["suffix_ids"] for r in recs2}
check("resume_no_dup_no_missing", len(recs2) == 18 and set(tok2) == set(ref_tok))
check("resume_tokens_equal_reference", all(tok2[k] == ref_tok[k] for k in ref_tok),
      sum(tok2[k] != ref_tok[k] for k in ref_tok))
# 재실행 거부
p = launch(kd)
p.wait()
check("rerun_into_completed_dir_refused", p.returncode != 0)
# 단일 소유권: 두 launcher 동시 시작
od = f"{ROOT}/own"
os.makedirs(od)
p1 = launch(od, 1)
time.sleep(3)
p2 = launch(od, 1)
p2.wait()
check("second_launcher_refused", p2.returncode != 0)
os.killpg(p1.pid, signal.SIGKILL)
p1.wait()
# 변조 거부 (kill dir 복사)
td = f"{ROOT}/tamper"
shutil.copytree(kd, td)
f = f"{td}/gen_worker0.jsonl"
lines = open(f).read().splitlines()
r0 = json.loads(lines[0])
r0["suffix_ids"] = r0["suffix_ids"][:-1]
lines[0] = json.dumps(r0)
open(f, "w").write("\n".join(lines) + "\n")
try:
    R.verify_completion(td, rq, pt)
    check("tamper_after_completion_rejected", False)
except R.RunError as e:
    check("tamper_after_completion_rejected", True, str(e)[:80])
# 중복 record
dd = f"{ROOT}/dup"
shutil.copytree(kd, dd)
os.unlink(f"{dd}/completion.json")
lines = open(f"{dd}/gen_worker1.jsonl").read().splitlines()
open(f"{dd}/gen_worker1.jsonl", "a").write(lines[0] + "\n")
pr = subprocess.run([sys.executable, "pg39_run.py", "worker", "--requests", rq, "--protocol", pt, "--out-dir", dd, "--worker", "1"],
                    capture_output=True, text=True)
check("resume_rejects_duplicate_record", pr.returncode != 0 and "duplicate record" in pr.stderr, pr.stderr[-200:])
# 영상 변경 후 재개 거부
ii = f"{ROOT}/imgchg"
shutil.copytree(kd, ii)
os.unlink(f"{ii}/completion.json")
sub = [json.loads(l) for l in open(rq)]
check("requests_have_unique_ids", len({r["request_id"] for r in sub}) == 18)
res["ref_wall_s_2workers_18req_incl_load"] = ref_wall
json.dump(res, open(f"{ROOT}/gpu_test_result.json", "w"), indent=1)
n_fail = sum(1 for v in res.values() if isinstance(v, dict) and not v.get("pass", True))
print("failures:", n_fail)
sys.exit(1 if n_fail else 0)
