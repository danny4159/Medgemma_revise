"""iter_012 실제 모델 GPU 재개 검사 (MedGemma 1.5, 실제 train.py 경로). 실행: python test_rsna_iter012_gpu.py
-> results/iter_012/tests/fixtures_iter012_gpu.json, 실행 산출물 results/iter_012/pilot/. 판정 기준은 실행 전 gpu_gate_config.json에 고정한다.

두 LR을 각각 한 GPU에 고정하고 (1e-4 -> GPU0, 2e-4 -> GPU1), 같은 GPU 안에서 같은 시작점의 무중단 U1·U2와 재개 R을 순차 비교한다.
  D (결정적 kernel, pilot16/eff4/3 epochs/val8): R은 6개 프로세스로 끊는다 —
     step2 직후(epoch1 중간) 종료 -> epoch1 adapter 저장 직후 종료 -> epoch2 validation 3요청 뒤 종료 -> step10 직후(epoch3 중간) 종료
     -> epoch3 adapter 저장 직후 종료 -> 마지막 validation 복구 후 정상 종료.
  M (결정적 kernel, 본학습 설정 train 2,400/eff16/microbatch2/workers3, validation 없음): U1·U2는 4 step, R은 step2 직후 종료 후 4 step까지.
  N (본학습 기본 kernel, D와 같은 pilot·같은 중단 순서): 부동소수 궤적 차이는 참고 기록, 비부동소수 상태(batch·token·LR·RNG·optimizer step)의
     정확한 일치와 복원 직후 상태 일치는 판정한다.
  B: 같은 run-dir 두 번째 학습 거부(첫 학습 생존 중), 학습 ID 하나 교체 후 재개 거부.
pilot weight는 본학습에 이월하지 않는다. 결정적 검사 run은 select.load_epochs가 선택에 쓰지 못하게 거부한다.
"""
import json
import os
import subprocess
import sys
import threading
import time

PROT = "results/iter_012/protocols/pilot_protocol.json"
B = "results/iter_012/pilot"
T = "results/iter_012/tests"
M_ = "results/iter_010/manifests/"
VAL8 = "results/iter_011/pilot/val8_ids.json"  # iter_011에서 고정한 validation 8명 (정렬 앞쪽 opacity4/normal2/not_normal2), 읽기 전용 재사용
GATES = {"loss_rtol": 1e-3, "adapter_atol": 1e-4, "util_atol": 0.05,
         "exact_required": ["batch_ids", "batch_token_sha", "lr", "rng_before", "opt_step_before", "restored_equals_saved", "validation_state_unchanged",
                            "checkpoint_digests_at_same_steps"],
         "note": "iter_011 기준값(loss 1e-3, adapter 1e-4, utility 0.05)을 그대로 유지한다. D·M은 수치 기준과 정확 일치 항목을 모두 판정한다. "
                 "N은 기본 kernel의 부동소수 차이를 참고로만 기록하고 정확 일치 항목만 판정한다. 관측값에 맞춰 기준을 바꾸지 않는다."}
LRS = {"1e-4": 0, "2e-4": 1}
R = {}


def check(name, cond, detail=None):
    R[name] = {"pass": bool(cond), "detail": detail}
    print(("PASS " if cond else "FAIL ") + name, "" if cond else json.dumps(detail, default=str)[:600], flush=True)


def train(gpu, run_dir, args, log):
    with open(log, "a") as f:
        f.write(f"\n=== {time.strftime('%F %T')} {' '.join(args)}\n")
        f.flush()
        p = subprocess.run([sys.executable, "-m", "rsna_diag.train", "--run-dir", run_dir, "--protocol", PROT, *args],
                           env=dict(os.environ, CUDA_VISIBLE_DEVICES=str(gpu)), stdout=f, stderr=subprocess.STDOUT)
    return p.returncode


def pilot_args(lr, det):
    a = ["--pilot", "--eff-batch", "4", "--train-ids", M_ + "pilot16_ids.json", "--val-ids", VAL8, "--ckpt-every", "2", "--microbatch", "2",
         "--workers", "2", "--seed", "17", "--lr", lr, "--epochs", "3"]
    return a + (["--deterministic"] if det else [])


def main_args(lr):
    return ["--pilot", "--no-val", "--deterministic", "--microbatch", "2", "--workers", "3", "--seed", "17", "--lr", lr, "--epochs", "5",
            "--ckpt-every", "2"]


R_SEQ = [(["--stop-after-step", "2"], 5), (["--stop-after-epoch-ckpt", "1"], 3), (["--stop-in-validation", "3"], 4),
         (["--stop-after-step", "10"], 5), (["--stop-after-epoch-ckpt", "3"], 3), ([], 0)]


def run_gpu(lr, gpu, rc):
    for mode in ("D", "N"):
        det = mode == "D"
        for u in ("U1", "U2"):
            d = f"{B}/{mode}_{u}_lr{lr}"
            rc[(mode, u, lr)] = train(gpu, d, pilot_args(lr, det), f"{d}.log")
        d = f"{B}/{mode}_R_lr{lr}"
        rc[(mode, "R", lr)] = [train(gpu, d, pilot_args(lr, det) + extra, f"{d}.log") for extra, _ in R_SEQ]
    for u in ("U1", "U2"):
        d = f"{B}/M_{u}_lr{lr}"
        rc[("M", u, lr)] = train(gpu, d, main_args(lr) + ["--max-steps", "4"], f"{d}.log")
    d = f"{B}/M_R_lr{lr}"
    rc[("M", "R", lr)] = [train(gpu, d, main_args(lr) + ["--stop-after-step", "2"], f"{d}.log"),
                          train(gpu, d, main_args(lr) + ["--max-steps", "4"], f"{d}.log")]


def logs(d):
    return [json.loads(l) for l in open(os.path.join(d, "train_log.jsonl")) if l.strip()]


def steps(d):
    return {r["step"]: r for r in logs(d) if "loss" in r}


def ckpts(d):
    """(step, epoch, pos) -> digests (마지막 기록). 재개 R에서는 같은 위치를 한 번만 저장한다."""
    return {(r["step"], r["epoch"], r["pos"]): r["digests"] for r in logs(d) if r.get("event") == "checkpoint"}


def compare(a, b, n_steps, with_val=True, numeric_gate=True):
    import torch
    sa, sb = steps(a), steps(b)
    out = {"n_steps": [len(sa), len(sb)]}
    ok_steps = sorted(sa) == sorted(sb) == list(range(1, n_steps + 1))
    out["same_steps"] = ok_steps
    if not ok_steps:
        return out, False, False
    rel = [abs(sa[k]["loss"] - sb[k]["loss"]) / abs(sa[k]["loss"]) for k in sa]
    out["loss_max_rel_diff"] = max(rel)
    out["loss_bitwise_equal_all"] = all(sa[k]["loss"] == sb[k]["loss"] for k in sa)
    exact = {f: all(sa[k][f] == sb[k][f] for k in sa) for f in ("batch_ids", "batch_token_sha", "lr", "rng_before", "opt_step_before", "train_mode")}
    ca, cb = ckpts(a), ckpts(b)
    common = sorted(set(ca) & set(cb))
    exact["checkpoint_digests_at_same_steps"] = bool(common) and all(ca[k] == cb[k] for k in common)
    out["checkpoint_positions_compared"] = common
    out["checkpoint_digest_mismatch"] = [k for k in common if ca[k] != cb[k]]
    out["exact"] = exact
    num_ok = out["loss_max_rel_diff"] <= GATES["loss_rtol"]
    if with_val:
        mx = 0.0
        eq = {}
        for e in (1, 2, 3):
            x = torch.load(f"{a}/epoch_{e:02d}/adapter.pt", map_location="cpu", weights_only=True)
            y = torch.load(f"{b}/epoch_{e:02d}/adapter.pt", map_location="cpu", weights_only=True)
            mx = max(mx, max(float((x["state"][k] - y["state"][k]).abs().max()) for k in x["state"]))
            eq[e] = x["digest"] == y["digest"]
        ma = {e: json.load(open(f"{a}/epoch_{e:02d}/val_metrics.json")) for e in (1, 2, 3)}
        mb = {e: json.load(open(f"{b}/epoch_{e:02d}/val_metrics.json")) for e in (1, 2, 3)}
        du = max(abs(ma[e]["utility"] - mb[e]["utility"]) for e in ma)
        dl = max(abs(ma[e]["val_loss"] - mb[e]["val_loss"]) / ma[e]["val_loss"] for e in ma)

        def outs(d, e):
            return {json.loads(l)["id"]: json.loads(l)["suffix_ids"] for l in open(f"{d}/epoch_{e:02d}/val_gen/gen_worker0.jsonl")}
        same_out = {e: sum(outs(a, e)[i] == outs(b, e).get(i) for i in outs(a, e)) for e in (1, 2, 3)}
        out.update({"adapter_max_abs_diff": mx, "adapter_digest_equal_by_epoch": eq, "utility_max_diff": du, "val_loss_max_rel_diff": dl,
                    "utility_by_epoch": [[ma[e]["utility"] for e in ma], [mb[e]["utility"] for e in mb]],
                    "val_outputs_identical_of_8_by_epoch": same_out})
        num_ok = num_ok and mx <= GATES["adapter_atol"] and du <= GATES["util_atol"] and dl <= GATES["loss_rtol"]
    else:
        import torch as _t
        x = _t.load(f"{a}/ckpt_latest.pt", map_location="cpu", weights_only=False)
        y = _t.load(f"{b}/ckpt_latest.pt", map_location="cpu", weights_only=False)
        mx = max(float((x["lora"][k] - y["lora"][k]).abs().max()) for k in x["lora"])
        out.update({"final_adapter_max_abs_diff": mx, "final_digests_equal": x["digests"] == y["digests"], "final_step": [x["step"], y["step"]]})
        num_ok = num_ok and mx <= GATES["adapter_atol"]
    return out, all(exact.values()), num_ok


def resume_checks(d, n_resume):
    ev = logs(d)
    res = [r for r in ev if r.get("event") == "resume"]
    ck = ckpts(d)
    restored_match_saved = all(r.get("restored_equals_saved") and ck.get((r["step"], r["epoch"], r["pos"])) == r["restored_digests"] for r in res)
    val = [r for r in ev if r.get("event") == "validation_done"]
    return {"n_resume": len(res), "restored_match_saved": restored_match_saved, "n_validation_done": len(val),
            "validation_state_unchanged": all(r.get("state_unchanged") for r in val), "recovered_from_file": [r["recovered_from_file"] for r in val]}, \
        len(res) == n_resume and restored_match_saved and all(r.get("state_unchanged") for r in val)


def main():
    os.makedirs(B, exist_ok=True)
    os.makedirs(T, exist_ok=True)
    gp = f"{T}/gpu_gate_config.json"
    if not os.path.exists(gp):
        json.dump(GATES, open(gp, "w"), indent=1)
    elif json.load(open(gp)) != GATES:
        sys.exit("gate config changed after being fixed")
    t0 = time.time()
    rc = {}
    th = [threading.Thread(target=run_gpu, args=(lr, g, rc)) for lr, g in LRS.items()]
    [t.start() for t in th]
    [t.join() for t in th]
    R["_wall_s_main_phases"] = {"pass": True, "detail": time.time() - t0}
    exp_r = [c for _, c in R_SEQ]
    for lr in LRS:
        for mode in ("D", "N"):
            check(f"{mode}_lr{lr}_return_codes_as_designed",
                  rc[(mode, "U1", lr)] == 0 and rc[(mode, "U2", lr)] == 0 and rc[(mode, "R", lr)] == exp_r,
                  {k: rc[(mode, k, lr)] for k in ("U1", "U2", "R")})
        check(f"M_lr{lr}_return_codes_as_designed", rc[("M", "U1", lr)] == 0 and rc[("M", "U2", lr)] == 0 and rc[("M", "R", lr)] == [5, 0],
              {k: rc[("M", k, lr)] for k in ("U1", "U2", "R")})
        for mode in ("D", "N"):
            u1, u2, rr = (f"{B}/{mode}_{k}_lr{lr}" for k in ("U1", "U2", "R"))
            try:
                o12, ex12, num12 = compare(u1, u2, 12)
                o1r, ex1r, num1r = compare(u1, rr, 12)
                rs, rs_ok = resume_checks(rr, 5)
            except Exception as e:  # 실행 실패로 산출물이 없으면 FAIL로 기록
                check(f"{mode}_lr{lr}_comparison_available", False, repr(e)[:300])
                continue
            comp = {}
            for e in (1, 2, 3):
                comp[e] = json.load(open(f"{rr}/epoch_{e:02d}/val_gen/completion.json"))["n_new_this_run"]
            if mode == "D":
                check(f"D_lr{lr}_U1_vs_U2_same_gpu_numeric_gate", num12, o12)
                check(f"D_lr{lr}_U1_vs_U2_exact_state_sequence", ex12, o12.get("exact"))
                check(f"D_lr{lr}_U1_vs_R_numeric_gate", num1r, o1r)
                check(f"D_lr{lr}_U1_vs_R_exact_state_sequence", ex1r, o1r.get("exact"))
            else:
                R[f"N_lr{lr}_U1_vs_U2_default_kernels_reference"] = {"pass": True, "detail": o12}
                R[f"N_lr{lr}_U1_vs_R_default_kernels_reference"] = {"pass": True, "detail": o1r}
                check(f"N_lr{lr}_U1_vs_U2_exact_nonfloat_state", all(v for k, v in o12["exact"].items() if k != "checkpoint_digests_at_same_steps"), o12.get("exact"))
                check(f"N_lr{lr}_U1_vs_R_exact_nonfloat_state", all(v for k, v in o1r["exact"].items() if k != "checkpoint_digests_at_same_steps"), o1r.get("exact"))
            check(f"{mode}_lr{lr}_R_restored_equals_saved_and_validation_invariant", rs_ok, rs)
            check(f"{mode}_lr{lr}_R_validation_recovery_counts_8_5_8", comp == {1: 8, 2: 5, 3: 8}, comp)
            for e in (1, 2, 3):
                n = sum(1 for _ in open(f"{rr}/epoch_{e:02d}/val_gen/gen_worker0.jsonl"))
                check(f"{mode}_lr{lr}_R_epoch{e}_raw_requests_8_no_duplicates", n == 8, n)
        u1, u2, rr = (f"{B}/M_{k}_lr{lr}" for k in ("U1", "U2", "R"))
        try:
            m12, mex12, mnum12 = compare(u1, u2, 4, with_val=False)
            m1r, mex1r, mnum1r = compare(u1, rr, 4, with_val=False)
            mrs, mrs_ok = resume_checks(rr, 1)
            check(f"M_lr{lr}_U1_vs_U2_numeric_gate", mnum12, m12)
            check(f"M_lr{lr}_U1_vs_U2_exact_state_sequence", mex12, m12.get("exact"))
            check(f"M_lr{lr}_U1_vs_R_numeric_gate", mnum1r, m1r)
            check(f"M_lr{lr}_U1_vs_R_exact_state_sequence", mex1r, m1r.get("exact"))
            check(f"M_lr{lr}_R_restored_equals_saved", mrs_ok, mrs)
            cfg = json.load(open(f"{u1}/train_config.json"))["config"]
            check(f"M_lr{lr}_main_config_path", cfg["n_train"] == 2400 and cfg["eff_batch"] == 16 and cfg["microbatch"] == 2 and cfg["deterministic"],
                  {k: cfg[k] for k in ("n_train", "eff_batch", "microbatch", "deterministic")})
        except Exception as e:
            check(f"M_lr{lr}_comparison_available", False, repr(e)[:300])

    # ---- B. 같은 run-dir 동시 학습 거부, 입력 ID 교체 재개 거부 ----
    TL = f"{B}/B_lock"
    out = {}

    def long_run():
        out["T"] = train(0, TL, ["--pilot", "--eff-batch", "4", "--no-val", "--train-ids", M_ + "pilot16_ids.json", "--epochs", "6", "--ckpt-every", "2",
                                 "--seed", "17", "--lr", "2e-4", "--microbatch", "2", "--workers", "2"], f"{TL}.log")

    tl = threading.Thread(target=long_run)
    tl.start()
    lockfile = os.path.join(TL, "train.lock")
    for _ in range(120):
        if os.path.exists(lockfile) and '"role": "train"' in open(lockfile).read():
            break
        time.sleep(1)
    held = os.path.exists(lockfile) and '"role": "train"' in open(lockfile).read()
    rc2 = train(1, TL, ["--pilot", "--eff-batch", "4", "--no-val", "--train-ids", M_ + "pilot16_ids.json", "--epochs", "6", "--seed", "17",
                        "--lr", "2e-4", "--microbatch", "2", "--workers", "2"], f"{TL}_second.log")
    txt = open(f"{TL}_second.log").read()
    tl.join()
    check("B_second_train_same_run_dir_refused_while_first_alive", held and rc2 != 0 and "owned by another live train process" in txt, [held, rc2, txt[-300:]])
    check("B_first_train_finished_rc0", out.get("T") == 0, out)
    gt = json.load(open(M_ + "gt_manifest.json"))
    tr16 = json.load(open(M_ + "pilot16_ids.json"))
    other = [i for i in sorted(gt) if gt[i]["split"] == "train" and i not in tr16 and gt[i]["category"] == "opacity"][0]
    sw = f"{B}/pilot16_swapped_ids.json"
    json.dump(sorted(tr16)[1:] + [other], open(sw, "w"))
    a = pilot_args("1e-4", True)
    a[a.index("--train-ids") + 1] = sw
    rc3 = train(0, f"{B}/D_U1_lr1e-4", a, f"{B}/B_swap.log")
    check("B_one_train_id_swapped_resume_refused", rc3 != 0 and "train config differs" in open(f"{B}/B_swap.log").read(), rc3)

    R["_wall_s_total"] = {"pass": True, "detail": time.time() - t0}
    json.dump(R, open(f"{T}/fixtures_iter012_gpu.json", "w"), indent=1, default=str)
    n_ok = sum(v["pass"] for v in R.values())
    print(f"{n_ok}/{len(R)} pass")
    sys.exit(0 if n_ok == len(R) else 1)


if __name__ == "__main__":
    main()
