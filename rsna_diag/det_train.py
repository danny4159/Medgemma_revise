"""RSNA detector 학습/평가 실행기 (natten_py310 env 전용).

iter_033의 results/iter_033/run_detector.py(sha256 994b061dee66d48436f08606dc551d4f47329f9719dc5d270e38800ec6ddf18c)를
원본으로 하고, iter_034에서 다음 결함을 수정했다:

1. augmentation RNG: 원본은 매 update마다 ds.set_epoch_rng(seed*1000+epoch)를 호출해 epoch 내 각 batch
   위치의 flip 패턴이 반복됐다. 수정본은 epoch 시작에만 재시딩하고 이후 rng 상태를 자연스럽게 이어간다.
   재개 시에는 checkpoint에 저장한 ds_rng_state를 그대로 복원해 이어간다(에폭 경계에서 재개하면 새로 시딩).
2. checkpoint: 실제 dataset RNG 상태(ds_rng_state)를 extra에 추가로 저장한다. 기존 model/optimizer/
   scheduler/full_rng_state/epoch/update_idx/sample_cursor/args는 원본과 동일하게 유지한다.
3. 로그: 매 update의 실제 sample id·flip 여부·적용 LR을 train_log.jsonl에 기록한다.
4. lock: 원본은 PID 존재 여부만 확인하는 파일 기반 lock이라 PID 재사용에 취약했다. 수정본은 fcntl.flock을
   프로세스 lifetime 동안 보유하는 방식으로 바꿔, 소유권이 OS 커널에 의해 강제되고(자기 lock만 해제),
   프로세스가 예기치 않게 죽어도 OS가 자동 해제한다.
5. 비유한 loss/gradient: 원본은 finite 여부를 기록만 하고 항상 opt.step()을 호출했다. 수정본은 optimizer
   update 전에 finite를 검사하고, 비유한 경우 opt.step()/sched.step()을 건너뛰고 기록한다.
6. SIGTERM: 안전한 경계에서 checkpoint를 저장하고 종료하는 handler를 추가했다.
7. --stop_after: 재개 검사(resume_check)에서 실제 cmd_train 프로세스를 지정한 update 수에서 중단시키기
   위한 테스트 전용 옵션이다.

이 파일과 결정은 rsna_diag/det_lib.py의 재사용 승인 범위(전처리·모델·optimizer/scheduler 유틸리티)를
넘어서는 실행기 자체이므로 별도 검증(fixtures/resume_check)을 거친다.
"""
import argparse
import fcntl
import json
import os
import signal
import sys
import time

import numpy as np
import torch

sys.path.insert(0, "/SSD1_1TB/home/milab/daniel/08_medgemma/research")
from rsna_diag import det_lib as D

BASE = "/SSD1_1TB/home/milab/daniel/08_medgemma/research"
DATA_DIRS = {
    "iter_033": f"{BASE}/results/iter_033/data",
    "iter_034": f"{BASE}/results/iter_034/data",
}


def load_manifest(name, data_dir=None):
    if data_dir is None:
        # iter_033 manifests take precedence (existing fixed D32/V100/train600/L64/train2400_full ids);
        # iter_034-only manifests (e.g. V400) live in iter_034/data.
        p33 = f"{DATA_DIRS['iter_033']}/{name}.json"
        p34 = f"{DATA_DIRS['iter_034']}/{name}.json"
        data_dir = DATA_DIRS['iter_033'] if os.path.exists(p33) else DATA_DIRS['iter_034']
    return json.load(open(f"{data_dir}/{name}.json"))


def get_device(dev_arg):
    return torch.device(f"cuda:{dev_arg}" if torch.cuda.is_available() else "cpu")


class FlockLock:
    """fcntl.flock 기반 exclusive lock. 파일 열림 동안만 유효하며 프로세스 종료 시 OS가 자동 해제한다."""

    def __init__(self, run_dir):
        os.makedirs(run_dir, exist_ok=True)
        self.path = os.path.join(run_dir, "train.lock")
        self.fh = open(self.path, "a+")
        try:
            fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.fh.close()
            raise RuntimeError(f"run_dir {run_dir} is locked by another live process (flock held)")
        self.fh.seek(0)
        self.fh.truncate()
        self.fh.write(json.dumps({"pid": os.getpid(), "t": time.time()}))
        self.fh.flush()

    def release(self):
        try:
            fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
        finally:
            self.fh.close()


_STOP_REQUESTED = {"flag": False}


def _sigterm_handler(signum, frame):
    _STOP_REQUESTED["flag"] = True


def make_checkpoint(model, opt, sched, epoch, update_idx, sample_cursor, ids_order, extra):
    return {
        "model": model.state_dict(),
        "optimizer": opt.state_dict(),
        "scheduler": sched.state_dict() if sched is not None else None,
        "rng": D.full_rng_state(),
        "epoch": epoch,
        "update_idx": update_idx,
        "sample_cursor": sample_cursor,
        "ids_order": ids_order,
        "extra": extra,
    }


def cmd_train(args):
    manifest = load_manifest(args.manifest)
    ids = manifest["ids"]
    gt, infer = D.load_gt_infer()
    device = get_device(args.device)
    run_dir = args.run_dir
    lock = FlockLock(run_dir)
    signal.signal(signal.SIGTERM, _sigterm_handler)
    try:
        images_per_epoch = len(ids)
        updates_per_epoch = images_per_epoch // args.effective_batch
        total_updates = updates_per_epoch * args.epochs
        if args.stop_after is not None:
            total_updates = min(total_updates, args.stop_after)
        warmup_updates = updates_per_epoch  # 1 epoch warmup
        milestone_updates = [updates_per_epoch * m for m in args.lr_drop_epochs]

        latest_path = os.path.join(run_dir, "ckpt_latest.pt")
        log_path = os.path.join(run_dir, "train_log.jsonl")
        resuming = os.path.exists(latest_path) and not args.fresh
        resume_ds_state = None
        resume_epoch = None
        resume_pos = None
        if resuming:
            ck = torch.load(latest_path, map_location="cpu", weights_only=False)
            model = D.build_model().to(device)
            model.load_state_dict(ck["model"])
            opt = D.build_optimizer(model, lr=args.lr)
            opt.load_state_dict(ck["optimizer"])
            D.optimizer_state_to_device(opt, device)
            sched = D.linear_warmup_then_multistep(opt, warmup_updates, milestone_updates)
            sched.load_state_dict(ck["scheduler"])
            D.restore_rng_state(ck["rng"])
            start_update = ck["update_idx"]
            resume_ds_state = ck.get("extra", {}).get("ds_rng_state")
            resume_epoch = ck.get("epoch")
            resume_pos = ck.get("sample_cursor")
            print(f"resumed from update {start_update}")
        else:
            torch.manual_seed(args.seed); np.random.seed(args.seed)
            model = D.build_model().to(device)
            opt = D.build_optimizer(model, lr=args.lr)
            sched = D.linear_warmup_then_multistep(opt, warmup_updates, milestone_updates)
            start_update = 0

        D.set_train_mode(model)
        ds = D.RSNADetDataset(ids, gt, infer, train_aug=True, seed=args.seed)

        def epoch_order(epoch_idx):
            rng = np.random.default_rng(args.seed * 100000 + epoch_idx)
            perm = rng.permutation(len(ids)).tolist()
            return perm

        t0 = time.time()
        n_images_processed = 0
        last_epoch_started = -1
        first_iter = True
        n_skipped_nonfinite = 0
        update_idx = start_update
        for update_idx in range(start_update, total_updates):
            epoch_idx = update_idx // updates_per_epoch
            pos_in_epoch = update_idx % updates_per_epoch
            if epoch_idx != last_epoch_started:
                if (first_iter and resuming and resume_ds_state is not None
                        and epoch_idx == resume_epoch and pos_in_epoch == resume_pos):
                    ds.rng.setstate(resume_ds_state)
                else:
                    ds.set_epoch_rng(args.seed * 1000 + epoch_idx)
                last_epoch_started = epoch_idx
            first_iter = False
            perm = epoch_order(epoch_idx)
            batch_indices = perm[pos_in_epoch * args.effective_batch:(pos_in_epoch + 1) * args.effective_batch]
            imgs, targets, batch_pids, batch_flips = [], [], [], []
            for bi in batch_indices:
                img, target, hw = ds[bi]
                imgs.append(img.to(device))
                targets.append({"boxes": target["boxes"].to(device), "labels": target["labels"].to(device)})
                batch_pids.append(ds.ids[bi])
                batch_flips.append(bool(target["flip"]))
            micro = args.microbatch
            opt.zero_grad()
            total_loss = 0.0
            loss_parts = {}
            for s in range(0, len(imgs), micro):
                sub_imgs = imgs[s:s + micro]
                sub_targets = targets[s:s + micro]
                loss_dict = model(sub_imgs, sub_targets)
                loss = sum(loss_dict.values()) * (len(sub_imgs) / len(imgs))
                loss.backward()
                total_loss += float(loss.item())
                for k, v in loss_dict.items():
                    loss_parts[k] = loss_parts.get(k, 0.0) + float(v.item()) * (len(sub_imgs) / len(imgs))
            gn_t = torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1e6)
            gn = float(gn_t)
            finite = bool(np.isfinite(total_loss)) and bool(np.isfinite(gn))
            if finite:
                opt.step()
                sched.step()
            else:
                opt.zero_grad()
                n_skipped_nonfinite += 1
            n_images_processed += len(batch_indices)
            rec = {"update": update_idx, "epoch": epoch_idx, "loss": total_loss, "finite": finite,
                   "skipped_nonfinite": (not finite), "grad_norm": gn, "lr_applied": sched.get_last_lr()[0],
                   "sample_ids": batch_pids, "flips": batch_flips, **loss_parts}
            with open(log_path, "a") as f:
                f.write(json.dumps(rec) + "\n")
            if update_idx % 50 == 0:
                elapsed = time.time() - t0
                imgs_per_sec = n_images_processed / elapsed if elapsed > 0 else 0.0
                print(json.dumps({**{k: v for k, v in rec.items() if k in ("update", "epoch", "loss", "finite", "lr_applied")},
                                   "images_per_sec": imgs_per_sec}))
            do_epoch_ckpt = (update_idx + 1) % updates_per_epoch == 0
            do_periodic_ckpt = (update_idx + 1) % 100 == 0
            if do_epoch_ckpt or do_periodic_ckpt or _STOP_REQUESTED["flag"]:
                ck = make_checkpoint(model, opt, sched, epoch_idx, update_idx + 1, pos_in_epoch + 1, ids,
                                     {"args": vars(args), "ds_rng_state": ds.rng.getstate()})
                D.atomic_save(ck, latest_path)
                if do_epoch_ckpt:
                    ep_dir = os.path.join(run_dir, f"epoch_{epoch_idx + 1:02d}")
                    os.makedirs(ep_dir, exist_ok=True)
                    D.atomic_save({"model": model.state_dict()}, os.path.join(ep_dir, "model.pt"))
            if _STOP_REQUESTED["flag"]:
                print(json.dumps({"sigterm_stop": True, "last_update_saved": update_idx}))
                return
        if args.stop_after is not None and update_idx == total_updates - 1:
            # 테스트 전용 강제 중단: 마지막 처리된 update가 주기적 checkpoint 경계와 맞지 않을 수 있으므로
            # 재개 정합성 검사를 위해 항상 checkpoint를 남긴다.
            pos_in_epoch_final = update_idx % updates_per_epoch
            epoch_idx_final = update_idx // updates_per_epoch
            ck = make_checkpoint(model, opt, sched, epoch_idx_final, update_idx + 1, pos_in_epoch_final + 1, ids,
                                 {"args": vars(args), "ds_rng_state": ds.rng.getstate()})
            D.atomic_save(ck, latest_path)
            print(json.dumps({"stop_after_reached": True, "last_update_saved": update_idx}))
            return
        elapsed = time.time() - t0
        peak_mib = torch.cuda.max_memory_allocated(device) / (1024 * 1024) if torch.cuda.is_available() else None
        peak_reserved_mib = torch.cuda.max_memory_reserved(device) / (1024 * 1024) if torch.cuda.is_available() else None
        print(json.dumps({"done": True, "total_updates": total_updates,
                           "elapsed_s": elapsed, "images_per_sec": n_images_processed / elapsed if elapsed > 0 else None,
                           "peak_allocated_mib": peak_mib, "peak_reserved_mib": peak_reserved_mib,
                           "n_skipped_nonfinite": n_skipped_nonfinite}))
    finally:
        lock.release()


def cmd_eval(args):
    manifest = load_manifest(args.manifest)
    ids = manifest["ids"]
    gt, infer = D.load_gt_infer()
    device = get_device(args.device)
    model = D.build_model().to(device)
    ck = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    model.load_state_dict(ck["model"])
    model.to(device)
    t0 = time.time()
    raw = D.run_inference(model, device, ids, gt, infer, batch_size=args.batch_size)
    elapsed = time.time() - t0
    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "raw_preds.json"), "w") as f:
        json.dump(raw, f)
    with open(os.path.join(out_dir, "eval_meta.json"), "w") as f:
        json.dump({"checkpoint": args.checkpoint, "manifest": args.manifest, "n_ids": len(ids),
                   "elapsed_s": elapsed, "images_per_sec": len(ids) / elapsed}, f, indent=2)
    print(json.dumps({"n_ids": len(ids), "elapsed_s": elapsed, "images_per_sec": len(ids) / elapsed}))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("train")
    p.add_argument("--manifest", required=True)
    p.add_argument("--run_dir", required=True)
    p.add_argument("--device", default="0")
    p.add_argument("--epochs", type=int, required=True)
    p.add_argument("--effective_batch", type=int, default=8)
    p.add_argument("--microbatch", type=int, default=2)
    p.add_argument("--lr", type=float, default=0.005)
    p.add_argument("--lr_drop_epochs", type=int, nargs="*", default=[])
    p.add_argument("--seed", type=int, default=17)
    p.add_argument("--fresh", action="store_true")
    p.add_argument("--stop_after", type=int, default=None, help="테스트용: 지정 update 수에서 강제 중단")
    p.set_defaults(func=cmd_train)

    p = sub.add_parser("eval")
    p.add_argument("--manifest", required=True)
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--out_dir", required=True)
    p.add_argument("--device", default="0")
    p.add_argument("--batch_size", type=int, default=4)
    p.set_defaults(func=cmd_eval)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
