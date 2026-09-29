"""det_train.py 실제 CLI의 거부·완료·lock·비유한 중단 검사 (natten_py310 env, GPU 1장).

iter_034 tests/lock_check.py(sha256 c9e30d14...)의 flock 검사를 포함해 확장했다. 각 사례는 새 프로세스로
det_train.py를 실행하고 종료 코드와 stderr의 거부 사유를 확인한다. 원본 결과 파일은 수정하지 않는다
(변조 사례는 이번 결과 경로의 사본에서만 만든다).
"""
import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time

import torch

BASE = "/SSD1_1TB/home/milab/daniel/08_medgemma/research"
TRAIN = f"{BASE}/rsna_diag/det_train.py"
PY = sys.executable
OLD_FORMAT1 = f"{BASE}/results/iter_033/sanity/resume_ckpt.pt"


def common(mb, epochs=6, drop=("4",)):
    return ["--manifest", "D32", "--epochs", str(epochs), "--effective_batch", "8", "--microbatch", str(mb),
            "--seed", "999", "--lr", "0.005", "--lr_drop_epochs", *drop, "--device", "0"]


def run(cmd, env_extra=None):
    env = dict(os.environ)
    env.update(env_extra or {})
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return r.returncode, (r.stdout + r.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--microbatch", type=int, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    C = common(a.microbatch)
    cases = {}

    def case(name, rc, text, expect_rc, expect_substr):
        ok = (rc == expect_rc if isinstance(expect_rc, int) else rc != 0) and (expect_substr is None or expect_substr in text)
        cases[name] = {"rc": rc, "ok": ok, "expect_rc": expect_rc, "expect": expect_substr,
                       "tail": text.strip().splitlines()[-2:]}

    X = os.path.join(a.out, "X")
    rc, t = run([PY, TRAIN, "train", "--run_dir", X, "--fresh", "--stop_after", "2"] + C)
    case("base_stop_after_2", rc, t, 3, "stop_after_reached")
    rc, t = run([PY, TRAIN, "train", "--run_dir", X, "--fresh"] + C)
    case("fresh_on_existing_refused", rc, t, "nonzero", "--fresh refused")
    rc, t = run([PY, TRAIN, "train", "--run_dir", X] + [x if x != "0.005" else "0.01" for x in C])
    case("config_change_refused", rc, t, "nonzero", "config mismatch")
    rc, t = run([PY, TRAIN, "train", "--run_dir", X] + C, {"DET_TEST_INPUT_SALT": "x"})
    case("input_change_refused", rc, t, "nonzero", "input digest mismatch")
    rc, t = run([PY, TRAIN, "train", "--run_dir", X] + C, {"DET_TEST_SOURCE_SALT": "x"})
    case("source_change_refused", rc, t, "nonzero", "source digest mismatch")
    rc, t = run([PY, TRAIN, "train", "--run_dir", os.path.join(a.out, "nockpt")] + C)
    case("resume_without_checkpoint_refused", rc, t, "nonzero", "no checkpoint")

    ck = torch.load(os.path.join(X, "ckpt_latest.pt"), map_location="cpu", weights_only=False)
    tam = os.path.join(a.out, "tampered")
    os.makedirs(tam, exist_ok=True)
    variants = {}
    c1 = dict(ck); c1.pop("ds_rng_state"); variants["missing_ds_rng_state"] = (c1, "missing required state")
    c2 = dict(ck); c2["perm"] = list(reversed(ck["perm"])); variants["tampered_permutation"] = (c2, "permutation")
    c3 = dict(ck); c3["optimizer"] = {**ck["optimizer"], "param_groups": [
        {**g, "lr": g["lr"] * 2} for g in ck["optimizer"]["param_groups"]]}; variants["tampered_lr"] = (c3, "lr")
    c4 = dict(ck); c4.pop("rng"); variants["missing_rng"] = (c4, "missing required state")
    for name, (obj, msg) in variants.items():
        p = os.path.join(tam, f"{name}.pt")
        torch.save(obj, p)
        rc, t = run([PY, TRAIN, "train", "--run_dir", os.path.join(a.out, f"init_{name}"), "--init_from", p] + C)
        case(name + "_refused", rc, t, "nonzero", msg)
    del ck
    rc, t = run([PY, TRAIN, "train", "--run_dir", os.path.join(a.out, "init_format1"), "--init_from", OLD_FORMAT1] + C)
    case("format1_without_migration_refused", rc, t, "nonzero", "requires --migration")

    # 중복 소유: 첫 프로세스가 lock을 잡고 새 segment를 기록한 뒤 두 번째 실행
    p = subprocess.Popen([PY, TRAIN, "train", "--run_dir", X] + C, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    t0 = time.time()
    while time.time() - t0 < 300:
        segs = json.load(open(os.path.join(X, "segments.json")))
        if len(segs) >= 2:
            break
        time.sleep(0.3)
    rc, t = run([PY, TRAIN, "train", "--run_dir", X] + C)
    case("concurrent_owner_refused", rc, t, "nonzero", "locked by another live process")
    p.send_signal(signal.SIGTERM)
    out, _ = p.communicate()
    case("first_owner_sigterm_safe_stop", p.returncode, out, 3, "sigterm_stop")

    # 비유한 loss: step 전에 실패, update 미소비
    nd = os.path.join(a.out, "nan")
    rc, t = run([PY, TRAIN, "train", "--run_dir", nd, "--fresh"] + C, {"DET_TEST_NAN_AT": "5"})
    case("nonfinite_abort", rc, t, "nonzero", "non-finite")
    nf = os.path.join(nd, "nonfinite.json")
    recs = [json.loads(l) for l in open(os.path.join(nd, "log_seg000.jsonl")) if l.strip()]
    cases["nonfinite_not_consumed"] = {"ok": os.path.exists(nf) and max(r["update"] for r in recs) == 4
                                       and torch.load(os.path.join(nd, "ckpt_latest.pt"), map_location="cpu",
                                                      weights_only=False)["update_idx"] == 4,
                                       "last_logged": max(r["update"] for r in recs)}

    # 완료 marker
    Y = os.path.join(a.out, "Y")
    CY = common(a.microbatch, epochs=1, drop=())
    CY = [x for x in CY if x != "--lr_drop_epochs"]
    rc, t = run([PY, TRAIN, "train", "--run_dir", Y, "--fresh"] + CY)
    case("complete_run", rc, t, 0, "\"done\": true")
    rc, t = run([PY, TRAIN, "verify", "--run_dir", Y])
    case("verify_ok", rc, t, 0, "verified")
    rc, t = run([PY, TRAIN, "train", "--run_dir", Y] + CY)
    case("train_on_complete_refused", rc, t, "nonzero", "already complete")
    Yb = os.path.join(a.out, "Y_tampered")
    shutil.copytree(Y, Yb)
    os.remove(os.path.join(Yb, "train.lock"))
    comp = json.load(open(os.path.join(Yb, "complete.json")))
    comp["canonical_log_digest"] = "0" * 64
    json.dump(comp, open(os.path.join(Yb, "complete.json"), "w"))
    rc, t = run([PY, TRAIN, "verify", "--run_dir", Yb])
    case("tampered_complete_marker_refused", rc, t, "nonzero", "canonical_log_digest mismatch")
    rc, t = run([PY, TRAIN, "train", "--run_dir", Yb] + CY)
    case("train_on_tampered_complete_refused", rc, t, "nonzero", "mismatch")

    allok = all(v["ok"] for v in cases.values())
    json.dump({"all_ok": allok, "cases": cases}, open(os.path.join(a.out, "cli_result.json"), "w"), indent=2)
    print(json.dumps({"all_ok": allok, "cases": {k: (v["ok"], v.get("rc")) for k, v in cases.items()}}, indent=1))
    sys.exit(0 if allok else 1)


if __name__ == "__main__":
    main()
