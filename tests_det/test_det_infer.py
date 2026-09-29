"""det_eval.py 추론 실행기의 중단·재개·tail 복구·변조 거부 검사 (natten_py310 env, GPU 1장).

고정 D24(iter_033 D32의 앞 24명)에 기존 iter_034 epoch_02 model(읽기 전용)을 사용한다. 재개 정확 비교는
batch 1(재개 뒤 batch 구성이 달라지지 않도록)로 하며, 같은 GPU에 worker 2개를 배치한다.
  REF: 중단 없는 실행 → completion.
  T:   부모에 SIGTERM(기록 6건 이상 확인 뒤) → 자식 전달·안전 종료 → shard에 불완전 tail 삽입 → 재실행 →
       손상 tail 보존 파일·정확한 ID 집합·REF와 bit 동일 결과.
  K:   부모 SIGKILL → PDEATHSIG로 worker 종료 → 재실행 완료·REF와 동일.
  변조: 다른 checkpoint로 완료 경로 재사용, source 변경 후 부분 결과 재개, 중복 줄, 내부 손상 줄,
       completion/raw_preds 변조, checkpoint 변경을 각각 거부해야 한다.
"""
import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time

BASE = "/SSD1_1TB/home/milab/daniel/08_medgemma/research"
EVAL = f"{BASE}/rsna_diag/det_eval.py"
PY = sys.executable
CK = f"{BASE}/results/iter_034/train/full_seed17/epoch_02/model.pt"
CK_OTHER = f"{BASE}/results/iter_034/train/full_seed17/epoch_01/model.pt"


def cmd(out, ck=CK, bs=1):
    return [PY, EVAL, "run", "--manifest", "D24", "--checkpoint", ck, "--out_dir", out, "--batch_size", str(bs),
            "--n_workers", "2", "--worker_gpus", "0,0"]


def run(c, env=None):
    """worker 오류는 worker 로그에 남으므로 해당 out_dir의 worker 로그 끝부분도 함께 반환한다."""
    e = dict(os.environ); e.update(env or {})
    r = subprocess.run(c, capture_output=True, text=True, env=e)
    txt = r.stdout + r.stderr
    if "--out_dir" in c:
        out = c[c.index("--out_dir") + 1]
        for w in (0, 1):
            p = os.path.join(out, f"worker{w:02d}.log")
            if os.path.exists(p):
                txt += open(p).read()[-3000:]
    return r.returncode, txt


def nlines(out):
    n = 0
    for w in (0, 1):
        p = os.path.join(out, f"preds_w{w:02d}.jsonl")
        if os.path.exists(p):
            n += sum(1 for l in open(p, "rb") if l.endswith(b"\n"))
    return n


def interrupt(out, sig, at=6):
    p = subprocess.Popen(cmd(out), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    t0 = time.time()
    while nlines(out) < at and p.poll() is None and time.time() - t0 < 600:
        time.sleep(0.2)
    n_at = nlines(out)
    p.send_signal(sig)
    rc = p.wait()
    time.sleep(3)
    return rc, n_at


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    sys.path.insert(0, BASE)
    from rsna_diag import det_eval as E
    C = {}

    def case(name, ok, **kw):
        C[name] = {"ok": bool(ok), **kw}

    ref = os.path.join(a.out, "REF")
    rc, t = run(cmd(ref))
    case("ref_complete", rc == 0, rc=rc)
    R, comp, ids = E.load_verified(ref, "D24", CK)
    case("ref_exact_id_set", list(R) == ids and len(ids) == 24)

    T = os.path.join(a.out, "T")
    rc, n_at = interrupt(T, signal.SIGTERM)
    n_after = nlines(T)
    case("sigterm_parent_safe_stop", rc == 3 and 0 < n_after < 24 and not os.path.exists(os.path.join(T, "completion.json")),
         rc=rc, n_at_signal=n_at, n_after=n_after)
    with open(os.path.join(T, "preds_w00.jsonl"), "ab") as f:
        f.write(b'{"id": "tra_BROKEN", "boxes_xy')
    rc, t = run(cmd(T))
    kept = [x for x in os.listdir(T) if "corrupt_tail" in x]
    RT, _, _ = E.load_verified(T, "D24", CK)
    case("resume_after_corrupt_tail", rc == 0 and len(kept) == 1 and RT == R, rc=rc, corrupt_kept=kept,
         equal_to_ref=RT == R)

    K = os.path.join(a.out, "K")
    rc, n_at = interrupt(K, signal.SIGKILL)
    time.sleep(2)
    alive = subprocess.run(["pgrep", "-f", f"det_eval.py worker .*{K}"], capture_output=True, text=True).stdout.strip()
    rc2, t = run(cmd(K))
    RK, _, _ = E.load_verified(K, "D24", CK)
    case("sigkill_parent_workers_terminated_and_resume", not alive and rc2 == 0 and RK == R, orphan_workers=alive, rc=rc2)

    rc, t = run(cmd(ref, ck=CK_OTHER))
    case("reuse_complete_with_other_checkpoint_refused", rc != 0 and "unexpected checkpoint" in t, rc=rc)

    P = os.path.join(a.out, "P_partial")
    rc, n_at = interrupt(P, signal.SIGTERM)
    rc, t = run(cmd(P), {"DET_TEST_SOURCE_SALT": "x"})
    case("resume_with_changed_source_refused", rc != 0, rc=rc)
    rc, t = run(cmd(P, ck=CK_OTHER))
    case("resume_with_changed_checkpoint_refused", rc != 0, rc=rc)
    rc, t = run(cmd(P, bs=4))
    case("resume_with_changed_batch_refused", rc != 0, rc=rc)

    Dd = os.path.join(a.out, "dup")
    shutil.copytree(ref, Dd)
    os.remove(os.path.join(Dd, "completion.json"))
    line = open(os.path.join(Dd, "preds_w00.jsonl")).readline()
    with open(os.path.join(Dd, "preds_w00.jsonl"), "a") as f:
        f.write(line)
    rc, t = run(cmd(Dd))
    case("duplicate_line_refused", rc != 0 and "duplicate" in t, rc=rc)

    Ib = os.path.join(a.out, "internal")
    shutil.copytree(ref, Ib)
    os.remove(os.path.join(Ib, "completion.json"))
    lines = open(os.path.join(Ib, "preds_w01.jsonl")).readlines()
    lines[2] = lines[2][:30] + "\n"
    open(os.path.join(Ib, "preds_w01.jsonl"), "w").writelines(lines)
    rc, t = run(cmd(Ib))
    case("internal_corrupt_line_refused", rc != 0 and "corrupt internal line" in t, rc=rc)

    Cm = os.path.join(a.out, "comp_tamper")
    shutil.copytree(ref, Cm)
    rp = json.load(open(os.path.join(Cm, "raw_preds.json")))
    k0 = next(iter(rp)); rp[k0]["scores"] = [s * 0.5 for s in rp[k0]["scores"]]
    json.dump(rp, open(os.path.join(Cm, "raw_preds.json"), "w"))
    rc, t = run([PY, EVAL, "check", "--out_dir", Cm])
    case("tampered_raw_preds_refused", rc != 0 and "raw_preds sha256 mismatch" in t, rc=rc)
    Cs = os.path.join(a.out, "shard_tamper")
    shutil.copytree(ref, Cs)
    with open(os.path.join(Cs, "preds_w00.jsonl"), "a") as f:
        f.write("\n")
    rc, t = run([PY, EVAL, "check", "--out_dir", Cs])
    case("tampered_shard_after_completion_refused", rc != 0 and "changed after completion" in t, rc=rc)

    allok = all(v["ok"] for v in C.values())
    json.dump({"all_ok": allok, "cases": C, "checkpoint": CK}, open(os.path.join(a.out, "infer_result.json"), "w"), indent=2)
    print(json.dumps({"all_ok": allok, "cases": {k: v["ok"] for k, v in C.items()}}, indent=1))
    sys.exit(0 if allok else 1)


if __name__ == "__main__":
    main()
