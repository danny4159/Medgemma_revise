"""det_train.py 실제 CLI의 재개 동등성 검사 (natten_py310 env, GPU 1장).

iter_034 tests/resume_check.py(sha256 0e5db96b...)를 대체한다. 원본은 fresh 반복 간 loss 차이에 3배 여유를 둔
판정으로 PASS를 기록했으나, 이번 계획은 동일 checkpoint에서 시작한 연속 실행과 새 프로세스 재개를 직접 대조한다.

D32, effective batch 8(4 update/epoch), 6 epoch=24 update, warmup 4 update, LR 감소 16 update(epoch 4).
저장·재개 경계: 2(warmup 중 epoch0 중간), 6(epoch1 중간), 15(LR 감소 직전). 각 경계 뒤 3 update를 비교한다.

--mode det: torch 결정적 알고리즘. 연속 A와 재개 R_k가 control·입력·loss·grad_norm·parameter·optimizer
            digest까지 bit 단위로 같아야 한다(주 gate). A2(반복)로 결정성 자체도 확인한다. 실제 SIGTERM(진행
            기록 연동)과 SIGKILL(orphan 로그) 뒤 재개도 A와 bit 단위로 대조한다.
--mode prod: 본학습 kernel. 같은 snapshot에서 재개한 R1_k·R2_k의 차이로 반복 변동을 먼저 기록하고(tolerance
            파일을 A 비교 전에 저장), control·입력 정확 일치와 첫 재개 update loss 허용오차를 판정한다.
            이후 update의 수치 차이는 반복 변동 대비 비율로 보고한다(정보용).
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import time

BASE = "/SSD1_1TB/home/milab/daniel/08_medgemma/research"
TRAIN = f"{BASE}/rsna_diag/det_train.py"
PY = sys.executable
BOUNDS = [2, 6, 15]
NCMP = 3
CTRL = ["update", "epoch", "pos", "sample_ids", "flips", "lr_applied", "lr_next", "input_digest"]


def common(mb, det):
    c = ["--manifest", "D32", "--epochs", "6", "--effective_batch", "8", "--microbatch", str(mb), "--seed", "999",
         "--lr", "0.005", "--lr_drop_epochs", "4", "--warmup_epochs", "1", "--device", "0", "--trace"]
    return c + (["--deterministic"] if det else [])


def run(cmd, log):
    with open(log, "a") as f:
        f.write(f"\n$ {' '.join(cmd)}\n"); f.flush()
        r = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    return r.returncode


def seg_records(run_dir):
    sys.path.insert(0, BASE)
    from rsna_diag import det_train as T
    recs, orph = T.canonical_log(run_dir)
    return {r["update"]: r for r in recs}, orph


def raw_count(run_dir):
    n = 0
    for fn in os.listdir(run_dir):
        if fn.startswith("log_seg") and fn.endswith(".jsonl"):
            with open(os.path.join(run_dir, fn)) as f:
                n += sum(1 for l in f if l.strip())
    return n


def digest_at(run_dir, u):
    p = os.path.join(run_dir, f"ckpt_u{u:05d}.digest.json")
    return json.load(open(p)) if os.path.exists(p) else None


def compare(A, R, updates):
    out = []
    for u in updates:
        a, r = A[u], R[u]
        out.append({"update": u, "ctrl_equal": all(a.get(k) == r.get(k) for k in CTRL),
                    "loss_diff": abs(a["loss"] - r["loss"]), "grad_diff": abs(a["grad_norm"] - r["grad_norm"]),
                    "params_equal": a["params_digest"] == r["params_digest"]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["det", "prod"], required=True)
    ap.add_argument("--microbatch", type=int, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    det = a.mode == "det"
    os.makedirs(a.out, exist_ok=True)
    log = os.path.join(a.out, "commands.log")
    C = common(a.microbatch, det)
    res = {"mode": a.mode, "microbatch": a.microbatch, "bounds": BOUNDS, "n_compare": NCMP}
    save_pts = sorted(set(BOUNDS + [k + NCMP for k in BOUNDS]))

    dA = os.path.join(a.out, "A")
    res["A_rc"] = run([PY, TRAIN, "train", "--run_dir", dA, "--fresh", "--save_at"] + [str(x) for x in save_pts] + C, log)
    A, _ = seg_records(dA)
    res["A_n"] = len(A)

    rdirs = {}
    reps = ["R1"] if det else ["R1", "R2"]
    for k in BOUNDS:
        for rep in reps:
            d = os.path.join(a.out, f"{rep}_k{k:02d}")
            rc = run([PY, TRAIN, "train", "--run_dir", d, "--init_from", os.path.join(dA, f"ckpt_u{k:05d}.pt"),
                      "--prefix_log", os.path.join(dA, "log_seg000.jsonl"), "--stop_after", str(k + NCMP),
                      "--save_at", str(k + NCMP)] + C, log)
            rdirs[(rep, k)] = d
            res[f"{rep}_k{k}_rc"] = rc

    if det:
        dA2 = os.path.join(a.out, "A2")
        res["A2_rc"] = run([PY, TRAIN, "train", "--run_dir", dA2, "--fresh", "--stop_after", "18"] + C, log)
        A2, _ = seg_records(dA2)
        rep_cmp = compare(A, A2, range(18))
        res["det_repeat_A_vs_A2_all_exact"] = all(x["ctrl_equal"] and x["loss_diff"] == 0 and x["grad_diff"] == 0
                                                  and x["params_equal"] for x in rep_cmp)
        res["det_repeat_max_loss_diff"] = max(x["loss_diff"] for x in rep_cmp)
        gate = True
        res["resume"] = {}
        for k in BOUNDS:
            R, _ = seg_records(rdirs[("R1", k)])
            cmp_ = compare(A, R, range(k, k + NCMP))
            dA_ = digest_at(dA, k + NCMP)
            dR_ = digest_at(rdirs[("R1", k)], k + NCMP)
            opt_eq = dA_ is not None and dR_ is not None and dA_ == dR_
            ok = all(x["ctrl_equal"] and x["loss_diff"] == 0 and x["grad_diff"] == 0 and x["params_equal"] for x in cmp_) and opt_eq
            res["resume"][f"k{k}"] = {"per_update": cmp_, "digest_at_k+3_equal(params,opt,lr,sched)": opt_eq, "exact": ok}
            gate = gate and ok
        # 실제 SIGTERM: 진행 기록(update 5 완료)을 확인한 뒤 신호 → 안전 저장 → 새 프로세스 재개 → 완료·verify
        dS = os.path.join(a.out, "S_sigterm")
        with open(log, "a") as f:
            p = subprocess.Popen([PY, TRAIN, "train", "--run_dir", dS, "--fresh"] + C, stdout=f, stderr=subprocess.STDOUT)
            while raw_count(dS) < 6 if os.path.isdir(dS) else True:
                if p.poll() is not None:
                    break
                time.sleep(0.2)
            n_at_signal = raw_count(dS)
            p.send_signal(signal.SIGTERM)
            rcS1 = p.wait()
        res["S_n_records_when_signalled"] = n_at_signal
        res["S_stop_rc"] = rcS1
        res["S_resume_rc"] = run([PY, TRAIN, "train", "--run_dir", dS] + C, log)
        res["S_verify_rc"] = run([PY, TRAIN, "verify", "--run_dir", dS], log)
        S, orphS = seg_records(dS)
        segsS = json.load(open(os.path.join(dS, "segments.json")))
        res["S_resume_start_update"] = segsS[-1]["start_update"]
        cmpS = compare(A, S, range(24))
        res["S_all_exact_vs_A"] = all(x["ctrl_equal"] and x["loss_diff"] == 0 and x["grad_diff"] == 0 and x["params_equal"] for x in cmpS)
        res["S_orphans"] = orphS
        # SIGKILL: 마지막 checkpoint(epoch 경계) 이후 기록이 orphan으로 남는지와 canonical 재구성 확인
        dK = os.path.join(a.out, "K_sigkill")
        with open(log, "a") as f:
            p = subprocess.Popen([PY, TRAIN, "train", "--run_dir", dK, "--fresh"] + C, stdout=f, stderr=subprocess.STDOUT)
            while raw_count(dK) < 6 if os.path.isdir(dK) else True:
                if p.poll() is not None:
                    break
                time.sleep(0.2)
            p.send_signal(signal.SIGKILL)
            res["K_kill_rc"] = p.wait()
        res["K_n_records_before_resume"] = raw_count(dK)
        res["K_resume_rc"] = run([PY, TRAIN, "train", "--run_dir", dK] + C, log)
        res["K_verify_rc"] = run([PY, TRAIN, "verify", "--run_dir", dK], log)
        K, orphK = seg_records(dK)
        segsK = json.load(open(os.path.join(dK, "segments.json")))
        res["K_resume_start_update"] = segsK[-1]["start_update"]
        res["K_orphans"] = orphK
        cmpK = compare(A, K, range(24))
        res["K_all_exact_vs_A"] = all(x["ctrl_equal"] and x["loss_diff"] == 0 and x["grad_diff"] == 0 and x["params_equal"] for x in cmpK)
        res["gate_pass"] = bool(gate and res["det_repeat_A_vs_A2_all_exact"] and res["A_rc"] == 0 and res["A2_rc"] == 3
                                and all(res[f"R1_k{k}_rc"] == 3 for k in BOUNDS)
                                and res["S_stop_rc"] == 3 and res["S_resume_rc"] == 0 and res["S_verify_rc"] == 0
                                and res["S_all_exact_vs_A"] and 0 < res["S_resume_start_update"] < 24
                                and res["K_resume_rc"] == 0 and res["K_verify_rc"] == 0 and res["K_all_exact_vs_A"]
                                and res["K_orphans"] > 0)
    else:
        # 1) 반복 변동 먼저: 같은 snapshot의 R1 vs R2
        noise = {}
        for k in BOUNDS:
            R1, _ = seg_records(rdirs[("R1", k)])
            R2, _ = seg_records(rdirs[("R2", k)])
            c = compare(R1, R2, range(k, k + NCMP))
            noise[f"k{k}"] = c
        first_noise = max(noise[f"k{k}"][0]["loss_diff"] for k in BOUNDS)
        tol = {"rule": "first resumed update: |loss_A - loss_R| <= max(1e-6, max_k |loss_R1 - loss_R2| at first update); "
                       "control/input exact. later updates reported as ratio to repeat noise (informational).",
               "tol_first_update_loss": max(1e-6, first_noise), "fixed_before_A_comparison": True,
               "noise_per_update": noise, "t": time.time()}
        with open(os.path.join(a.out, "tolerance.json"), "w") as f:
            json.dump(tol, f, indent=2)
        # 2) A 대비
        gate = True
        res["resume"] = {}
        for k in BOUNDS:
            per = {}
            for rep in reps:
                R, _ = seg_records(rdirs[(rep, k)])
                per[rep] = compare(A, R, range(k, k + NCMP))
            ctrl_ok = all(x["ctrl_equal"] for rep in reps for x in per[rep])
            first_ok = all(per[rep][0]["loss_diff"] <= tol["tol_first_update_loss"] for rep in reps)
            later_ar = max(x["loss_diff"] for rep in reps for x in per[rep][1:])
            later_noise = max(x["loss_diff"] for x in noise[f"k{k}"][1:])
            res["resume"][f"k{k}"] = {"per_update": per, "ctrl_input_exact": ctrl_ok, "first_update_within_tol": first_ok,
                                      "later_max_loss_diff_A_vs_R": later_ar, "later_max_loss_diff_R1_vs_R2": later_noise}
            gate = gate and ctrl_ok and first_ok
        res["gate_pass"] = bool(gate and res["A_rc"] == 0 and all(res[f"{rep}_k{k}_rc"] == 3 for k in BOUNDS for rep in reps))
    with open(os.path.join(a.out, "resume_result.json"), "w") as f:
        json.dump(res, f, indent=2)
    print(json.dumps({k: v for k, v in res.items() if k != "resume"}, indent=1))
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "per_update"} for k, v in res.get("resume", {}).items()}, indent=1))
    sys.exit(0 if res["gate_pass"] else 1)


if __name__ == "__main__":
    main()
