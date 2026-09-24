"""iter_011 실제 모델 GPU 복구 검증 (MedGemma 1.5, 실제 LoRA 학습 경로). 실행: python test_rsna_iter011_gpu.py
-> results/iter_011/tests/fixtures_iter011_gpu.json, 실행 산출물은 results/iter_011/pilot/ 아래.

이 검사는 복구 경로의 정확성 검사다. 여기서 쓰는 소표본(pilot16 train, 고정 validation 8명)은 성능 선택 자료나 독립 확인이 아니며
pilot weight는 본학습에 이월하지 않는다. 허용 오차는 실행 전에 아래 상수로 고정한다.

  A. 중단 위치별 재개: uninterrupted(U, GPU0) vs 4회 중단·재개(R, GPU1)
     중단 지점: epoch1 adapter/ckpt 저장 직후(validation 전) -> 재개 시 epoch1 validation 복구 -> epoch2 validation 중 3요청 뒤 kill ->
                재개 시 남은 5요청만 수행 -> epoch3(마지막) adapter/ckpt 저장 직후 kill -> 재개 시 마지막 validation 복구.
     비교: step별 loss(상대 LOSS_RTOL), epoch adapter 최대 절대 차(ADAPTER_ATOL), val_metrics utility/val_loss, epoch별 요청 수·중복.
  B. 같은 run-dir 두 번째 학습 프로세스 거부(lock), 입력 ID 하나 교체 시 재개 거부, 본실험 경로에서 --pilot 없는 완화 옵션 거부.
  C. 실제 iter_010 부모 checkpoint(seed17, lr 1e-4/2e-4, step 100)를 migration manifest로 가져와 원본 로그의 이후 step(101..)과 같은 batch·loss가
     재현되는지 대조 (LOSS_RTOL). 실제 2,400/400 입력 digest 검증 포함.
"""
import json
import os
import subprocess
import sys
import threading
import time

R = {}
PROT = "results/iter_011/protocols/main_protocol.json"
B = "results/iter_011/pilot"
M = "results/iter_010/manifests/"
LOSS_RTOL = 1e-3
ADAPTER_ATOL = 1e-4
UTIL_ATOL = 0.05


def check(name, cond, detail=None):
    R[name] = {"pass": bool(cond), "detail": detail}
    print(("PASS " if cond else "FAIL ") + name, detail if not cond else "", flush=True)


def train(gpu, run_dir, extra, log, ids=True):
    args = ["--run-dir", run_dir, "--protocol", PROT, "--seed", "17", "--lr", "2e-4", "--microbatch", "2", "--workers", "2"] + extra
    with open(log, "a") as f:
        p = subprocess.run([sys.executable, "-m", "rsna_diag.train", *args], env=dict(os.environ, CUDA_VISIBLE_DEVICES=str(gpu)),
                           stdout=f, stderr=subprocess.STDOUT)
    return p.returncode


PILOT = ["--pilot", "--eff-batch", "4", "--train-ids", M + "pilot16_ids.json", "--val-ids", f"{B}/val8_ids.json", "--ckpt-every", "2"]


def logs(run_dir):
    return [json.loads(l) for l in open(os.path.join(run_dir, "train_log.jsonl")) if l.strip()]


def steps(run_dir):
    return {r["step"]: r for r in logs(run_dir) if "step" in r and "loss" in r}


def main():
    import torch
    os.makedirs(B, exist_ok=True)
    gt = json.load(open(M + "gt_manifest.json"))
    val = sorted(i for i in gt if gt[i]["split"] == "validation")
    pick = [i for i in val if gt[i]["category"] == "opacity"][:4] + [i for i in val if gt[i]["category"] == "normal"][:2] \
        + [i for i in val if gt[i]["category"] == "not_normal_no_opacity"][:2]
    json.dump(sorted(pick), open(f"{B}/val8_ids.json", "w"))  # 고정 규칙: validation split의 정렬된 앞쪽 opacity 4 / normal 2 / not_normal 2
    tr16 = json.load(open(M + "pilot16_ids.json"))
    check("pilot_ids_cover_single_multi_and_two_negative_strata",
          {len(gt[i]["boxes"]) for i in tr16 if gt[i]["category"] == "opacity"} >= {1, 2, 3}
          and {gt[i]["category"] for i in tr16} == {"opacity", "normal", "not_normal_no_opacity"})

    # ---- A. uninterrupted vs interrupted ----
    U, Rr = f"{B}/A_uninterrupted", f"{B}/A_interrupted"
    rc = {}

    def pipeline_u():
        rc["U"] = train(0, U, PILOT + ["--epochs", "3"], f"{B}/A_uninterrupted.log")

    def pipeline_r():
        rc["r1"] = train(1, Rr, PILOT + ["--epochs", "3", "--stop-after-epoch-ckpt", "1"], f"{B}/A_interrupted.log")
        rc["r2"] = train(1, Rr, PILOT + ["--epochs", "3", "--stop-in-validation", "3"], f"{B}/A_interrupted.log")
        rc["r3"] = train(1, Rr, PILOT + ["--epochs", "3", "--stop-after-epoch-ckpt", "3"], f"{B}/A_interrupted.log")
        rc["r4"] = train(1, Rr, PILOT + ["--epochs", "3"], f"{B}/A_interrupted.log")

    th = [threading.Thread(target=pipeline_u), threading.Thread(target=pipeline_r)]
    [t.start() for t in th]
    [t.join() for t in th]
    check("A_return_codes_as_designed", rc == {"U": 0, "r1": 3, "r2": 4, "r3": 3, "r4": 0}, rc)
    ok_files = all(os.path.exists(f"{d}/epoch_{e:02d}/val_metrics.json") for d in (U, Rr) for e in (1, 2, 3))
    check("A_all_epoch_validations_completed_in_both", ok_files)
    if ok_files:
        mu = {e: json.load(open(f"{U}/epoch_{e:02d}/val_metrics.json")) for e in (1, 2, 3)}
        mr = {e: json.load(open(f"{Rr}/epoch_{e:02d}/val_metrics.json")) for e in (1, 2, 3)}
        su, sr = steps(U), steps(Rr)
        check("A_same_number_of_optimizer_steps", sorted(su) == sorted(sr) and len(su) == 12, [len(su), len(sr)])
        rel = max(abs(su[k]["loss"] - sr[k]["loss"]) / abs(su[k]["loss"]) for k in su)
        check("A_step_losses_match_uninterrupted", rel <= LOSS_RTOL, {"max_rel_diff": rel, "tol": LOSS_RTOL})
        lrs_equal = all(abs(su[k]["lr"] - sr[k]["lr"]) < 1e-15 for k in su)
        check("A_lr_sequence_identical", lrs_equal)
        # 다음 입력 순서: epoch/pos 라벨과 batch 크기 동일
        check("A_epoch_pos_sequence_identical", all((su[k]["epoch"], su[k]["pos"], su[k]["n_examples"]) == (sr[k]["epoch"], sr[k]["pos"], sr[k]["n_examples"]) for k in su))
        mx = 0.0
        exact = {}
        for e in (1, 2, 3):
            a = torch.load(f"{U}/epoch_{e:02d}/adapter.pt", map_location="cpu", weights_only=True)
            b = torch.load(f"{Rr}/epoch_{e:02d}/adapter.pt", map_location="cpu", weights_only=True)
            d = max(float((a["state"][k] - b["state"][k]).abs().max()) for k in a["state"])
            mx = max(mx, d)
            exact[e] = a["digest"] == b["digest"]
        check("A_adapter_tensors_match_uninterrupted", mx <= ADAPTER_ATOL, {"max_abs_diff": mx, "tol": ADAPTER_ATOL, "digest_equal_by_epoch": exact})
        du = max(abs(mu[e]["utility"] - mr[e]["utility"]) for e in mu)
        dl = max(abs(mu[e]["val_loss"] - mr[e]["val_loss"]) / mu[e]["val_loss"] for e in mu)
        check("A_validation_metrics_match_uninterrupted", du <= UTIL_ATOL and dl <= LOSS_RTOL,
              {"max_utility_diff": du, "max_val_loss_rel_diff": dl, "utility_by_epoch_U": {e: mu[e]["utility"] for e in mu},
               "utility_by_epoch_R": {e: mr[e]["utility"] for e in mr}})
        comp = {e: json.load(open(f"{Rr}/epoch_{e:02d}/val_gen/completion.json")) for e in (1, 2, 3)}
        check("A_epoch2_only_remaining_5_of_8_requests_generated_after_kill", comp[2]["n_new_this_run"] == 5, comp[2])
        check("A_epoch1_and_epoch3_recovered_all_8_from_pending", comp[1]["n_new_this_run"] == 8 and comp[3]["n_new_this_run"] == 8, [comp[1]["n_new_this_run"], comp[3]["n_new_this_run"]])
        for e in (1, 2, 3):
            n = sum(1 for _ in open(f"{Rr}/epoch_{e:02d}/val_gen/gen_worker0.jsonl"))
            check(f"A_epoch{e}_raw_request_count_8_no_duplicates", n == 8, n)
        ev = [r for r in logs(Rr) if r.get("event") == "resume"]
        check("A_resume_events_logged", len(ev) == 3, ev)

    # ---- B. lock / 입력 변경 거부 ----
    T = f"{B}/B_lock"
    out = {}

    def long_run():
        out["T"] = train(0, T, PILOT[:0] + ["--pilot", "--eff-batch", "4", "--no-val", "--train-ids", M + "pilot16_ids.json", "--epochs", "6", "--ckpt-every", "2"], f"{B}/B_lock.log")

    tl = threading.Thread(target=long_run)
    tl.start()
    time.sleep(25)  # 첫 프로세스가 lock을 잡은 뒤
    lockfile = os.path.join(T, "train.lock")
    held = os.path.exists(lockfile)
    rc2 = train(1, T, ["--pilot", "--eff-batch", "4", "--no-val", "--train-ids", M + "pilot16_ids.json", "--epochs", "6"], f"{B}/B_lock_second.log")
    txt = open(f"{B}/B_lock_second.log").read()
    tl.join()
    check("B_second_train_on_same_run_dir_refused_while_first_alive", held and rc2 != 0 and "owned by another live train process" in txt, [held, rc2, txt[-300:]])
    check("B_first_train_unaffected_finished_rc0", out.get("T") == 0, out)
    check("B_lock_file_not_deleted_and_released_after_exit", os.path.exists(lockfile) and "released" in open(lockfile).read())
    # 입력 ID 하나 교체: U가 학습한 run-dir에 다른 train id 집합으로 재개 시도
    other = [i for i in sorted(gt) if gt[i]["split"] == "train" and i not in tr16 and gt[i]["category"] == "opacity"][0]
    swapped = sorted(tr16)[1:] + [other]
    json.dump(swapped, open(f"{B}/pilot16_swapped_ids.json", "w"))
    rc3 = train(0, U, ["--pilot", "--eff-batch", "4", "--epochs", "3", "--train-ids", f"{B}/pilot16_swapped_ids.json", "--val-ids", f"{B}/val8_ids.json"], f"{B}/B_swap.log")
    t3 = open(f"{B}/B_swap.log").read()
    check("B_one_train_id_swapped_resume_refused", rc3 != 0 and "train config differs" in t3, [rc3, t3[-200:]])
    dup = f"{B}/pilot16_dup_ids.json"
    json.dump(tr16 + [tr16[0]], open(dup, "w"))
    rc4 = train(0, f"{B}/B_dup", ["--pilot", "--eff-batch", "4", "--no-val", "--epochs", "1", "--train-ids", dup], f"{B}/B_dup.log")
    check("B_duplicate_id_refused", rc4 != 0 and "duplicate ids" in open(f"{B}/B_dup.log").read())
    rc5 = train(0, f"{B}/B_nopilot", ["--no-val", "--epochs", "1"], f"{B}/B_nopilot.log")
    check("B_relaxed_options_require_pilot_flag", rc5 != 0 and "require --pilot" in open(f"{B}/B_nopilot.log").read())

    # ---- C. 부모 checkpoint 이관 + 원본 이후 step 재현 ----
    res = {}

    def mig2(gpu, lr, until):
        d = f"{B}/C_mig_lr{lr}"
        args = ["--run-dir", d, "--protocol", PROT, "--seed", "17", "--lr", lr, "--microbatch", "2", "--workers", "3", "--epochs", "5",
                "--migration", f"results/iter_011/recovery/migration_lr{lr}_s17.json", "--max-steps", str(until)]
        # 본실험 경로(non-pilot)와 같은 옵션으로 실행하되 max-steps는 검증용이다 (cfg에 포함되지 않는다)
        with open(f"{B}/C_mig_lr{lr}.log", "a") as f:
            res[lr] = subprocess.run([sys.executable, "-m", "rsna_diag.train", *args], env=dict(os.environ, CUDA_VISIBLE_DEVICES=str(gpu)), stdout=f,
                                     stderr=subprocess.STDOUT).returncode

    ths = [threading.Thread(target=mig2, args=(1, "1e-4", 121)), threading.Thread(target=mig2, args=(0, "2e-4", 107))]
    [t.start() for t in ths]
    [t.join() for t in ths]
    check("C_migration_runs_rc0", res == {"1e-4": 0, "2e-4": 0}, res)
    for lr, until in (("1e-4", 121), ("2e-4", 107)):
        d = f"{B}/C_mig_lr{lr}"
        par = {}
        for l in open(f"results/iter_010/train/lr{lr}_s17/train_log.jsonl"):
            r = json.loads(l)
            par[r["step"]] = r
        new = steps(d)
        common = [k for k in range(101, until + 1) if k in new and k in par]
        rel = max(abs(new[k]["loss"] - par[k]["loss"]) / par[k]["loss"] for k in common) if common else None
        check(f"C_lr{lr}_reproduces_original_steps_101_to_{until}", common == list(range(101, until + 1)) and rel is not None and rel <= LOSS_RTOL,
              {"n_compared": len(common), "max_rel_loss_diff": rel, "tol": LOSS_RTOL,
               "lr_equal": all(abs(new[k]["lr"] - par[k]["lr"]) < 1e-15 for k in common),
               "same_position": all((new[k]["epoch"], new[k]["pos"]) == (par[k]["epoch"], par[k]["pos"]) for k in common)})
        ev = [r for r in logs(d) if r.get("event") == "imported_parent"]
        check(f"C_lr{lr}_import_event_logged_with_parent_sha", len(ev) == 1 and ev[0]["step"] == 100, ev)
        check(f"C_lr{lr}_parent_prefix_log_has_only_steps_le_100",
              max(json.loads(l)["step"] for l in open(f"{d}/parent_train_log_valid_prefix.jsonl")) == 100)
        cfg = json.load(open(f"{d}/train_config.json"))["config"]
        check(f"C_lr{lr}_real_input_digests_recorded", bool(cfg["train_inputs_digest"]) and bool(cfg["val_inputs_digest"]) and cfg["n_train"] == 2400 and cfg["n_val"] == 400)

    n_ok = sum(v["pass"] for v in R.values())
    os.makedirs("results/iter_011/tests", exist_ok=True)
    json.dump(R, open("results/iter_011/tests/fixtures_iter011_gpu.json", "w"), indent=1, default=str)
    print(f"{n_ok}/{len(R)} pass")
    sys.exit(0 if n_ok == len(R) else 1)


if __name__ == "__main__":
    main()
