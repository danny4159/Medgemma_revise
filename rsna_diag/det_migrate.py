"""iter_034 부분 학습 checkpoint(format 1)의 이관 가능성 감사 (natten_py310 env).

원본 checkpoint·로그는 읽기만 한다. 결과로 migration manifest를 쓰며, det_train.py --init_from --migration이
이 manifest를 요구한다. 판정 근거:
  1. 원본 checkpoint sha256, update_idx/epoch/cursor 규약, scheduler(last_epoch·base_lrs), optimizer group lr,
     저장 args, 필수 RNG·dataset RNG 존재.
  2. 원본 로그: update 연속·중복 없음(=강제 종료 뒤 재개 이력 없음), 모든 finite, 저장 update 이후 orphan 수.
  3. 결정적 재현: 원래 epoch permutation 함수와 epoch 시작 시딩 규약으로 로그 전체의 sample id·flip을 재생하고,
     저장된 dataset RNG 상태가 저장 update까지 소비한 상태와 정확히 같은지 확인한다(실제 permutation 미저장 보완).
  4. 실행 소스: 원본 run의 det_train/det_lib sha256(인자 값)과 commit 기록을 manifest에 남긴다.
"""
import argparse
import json
import os
import random
import sys

import numpy as np
import torch

BASE = "/SSD1_1TB/home/milab/daniel/08_medgemma/research"
sys.path.insert(0, BASE)
from rsna_diag import det_lib as D, det_train as T  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src_run", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--old_det_train_sha256", required=True)
    ap.add_argument("--old_det_lib_sha256", required=True)
    ap.add_argument("--old_commit", required=True)
    a = ap.parse_args()

    ck_path = os.path.join(a.src_run, "ckpt_latest.pt")
    log_path = os.path.join(a.src_run, "train_log.jsonl")
    # 구버전 extra.args=vars(args)에는 argparse의 func(__main__.cmd_train)가 pickle돼 있다. 로드용 이름만 제공한다.
    sys.modules["__main__"].cmd_train = T.cmd_train
    ck = torch.load(ck_path, map_location="cpu", weights_only=False)
    old_args = {k: v for k, v in ck["extra"]["args"].items() if k != "func"}
    checks = {}
    ids = json.load(open(T.find_manifest(old_args["manifest"])))["ids"]
    gt, infer = D.load_gt_infer()
    upe = len(ids) // old_args["effective_batch"]
    u = ck["update_idx"]
    checks["format1_keys"] = all(k in ck for k in ("model", "optimizer", "scheduler", "rng", "epoch", "update_idx",
                                                     "sample_cursor", "ids_order", "extra"))
    checks["rng_keys"] = sorted(ck["rng"].keys()) == ["numpy", "python", "torch_cpu", "torch_cuda"] and ck["rng"]["torch_cuda"] is not None
    checks["ds_rng_state_present"] = ck["extra"].get("ds_rng_state") is not None
    checks["ids_order_is_manifest_order"] = ck["ids_order"] == ids
    checks["epoch_cursor_convention"] = ck["epoch"] == (u - 1) // upe and ck["sample_cursor"] == (u - 1) % upe + 1
    sch = ck["scheduler"]
    checks["scheduler_last_epoch_eq_update"] = sch["last_epoch"] == u
    checks["scheduler_base_lrs"] = all(x == old_args["lr"] for x in sch["base_lrs"])
    warm = upe  # 원 코드: 1 epoch warmup
    miles = [upe * m for m in old_args["lr_drop_epochs"]]

    def lam(step):
        if step < warm:
            return (step + 1) / warm
        f = 1.0
        for m in miles:
            if step >= m:
                f *= 0.1
        return f
    grp_lrs = [g["lr"] for g in ck["optimizer"]["param_groups"]]
    checks["optimizer_lr_eq_scheduled_next"] = all(abs(x - lam(u) * old_args["lr"]) < 1e-15 for x in grp_lrs)
    checks["optimizer_initial_lr"] = all(g.get("initial_lr") == old_args["lr"] for g in ck["optimizer"]["param_groups"])

    # 로그
    L = [json.loads(l) for l in open(log_path) if l.strip()]
    ups = [r["update"] for r in L]
    checks["log_contiguous_from0_no_dup"] = ups == list(range(len(ups)))
    checks["log_all_finite"] = all(r["finite"] and not r.get("skipped_nonfinite") for r in L)
    checks["log_covers_saved_update"] = len(L) >= u
    n_orphan = len([x for x in ups if x >= u])
    # 원 코드의 lr_applied는 sched.step() 뒤의 다음 LR이다: lam(update+1)*lr
    checks["log_lr_matches_fresh_schedule"] = all(abs(r["lr_applied"] - lam(r["update"] + 1) * old_args["lr"]) < 1e-15 for r in L)

    # 결정적 재생: sample id·flip·dataset RNG
    seed = old_args["seed"]
    eb = old_args["effective_batch"]
    mism = []
    ds_state_at_u = None
    rng = None
    for upd in range(len(L)):
        e, pos = upd // upe, upd % upe
        if pos == 0:
            rng = random.Random(seed * 1000 + e)
        perm = T.epoch_perm(seed, e, len(ids))
        bidx = perm[pos * eb:(pos + 1) * eb]
        exp_ids = [ids[i] for i in bidx]
        exp_flips = [rng.random() < 0.5 for _ in bidx]
        if exp_ids != L[upd]["sample_ids"] or exp_flips != L[upd]["flips"]:
            mism.append(upd)
        if upd + 1 == u:
            ds_state_at_u = rng.getstate()
    checks["replay_sample_ids_flips_all_log"] = not mism
    checks["replay_ds_rng_state_eq_saved"] = ds_state_at_u == ck["extra"]["ds_rng_state"]

    new_cfg = {"manifest": old_args["manifest"], "effective_batch": eb, "microbatch": old_args["microbatch"],
               "lr": old_args["lr"], "momentum": 0.9, "weight_decay": 1e-4, "lr_drop_epochs": old_args["lr_drop_epochs"],
               "seed": seed, "warmup_epochs": 1, "trainable_backbone_layers": 5, "flip_p": 0.5, "min_size": 800,
               "max_size": 1333}
    ok = all(checks.values())
    out = {
        "kind": "det_train format1 -> format2 migration",
        "ok": ok, "checks": checks, "replay_mismatch_updates": mism[:20],
        "source_checkpoint": os.path.abspath(ck_path), "source_checkpoint_sha256": D.sha256_file(ck_path),
        "source_log": os.path.abspath(log_path), "source_log_sha256": D.sha256_file(log_path),
        "source_code_sha256": {"rsna_diag/det_train.py": a.old_det_train_sha256,
                               "rsna_diag/det_lib.py": a.old_det_lib_sha256, "commit": a.old_commit},
        "old_args": old_args, "config": new_cfg, "input_digest": T.input_digest(ids, gt, infer),
        "update_idx": u, "n_log_records": len(L), "n_orphan_log_records": n_orphan,
        "scheduler_state": {k: v for k, v in sch.items() if k != "lr_lambdas"}, "optimizer_group_lrs": grp_lrs,
        "compat_note": ("format 1 저장값에는 config/input/source digest·실제 permutation이 없다. 동일 recipe의 기본값"
                        "(momentum 0.9, wd 1e-4, warmup 1 epoch, backbone 5층, flip 0.5, 800/1333)은 원 코드 상수와 같고,"
                        " permutation·flip·dataset RNG는 결정적 재생으로 유일하게 복원됨을 위 checks로 확인한다."),
    }
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps({"ok": ok, "checks": checks, "update_idx": u, "n_orphan": n_orphan,
                      "old_microbatch": old_args["microbatch"], "old_args": old_args}, indent=1))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
