"""직접 병변 LoRA SFT 학습 (iter_010, iter_011 복구 수정). 표준 torch LoRA, assistant-only CE, 재개 가능 checkpoint, epoch별 validation 생성 평가.

- base bf16 동결, LoRA(fp32) rank16/alpha32/dropout0.05, AdamW(wd 0.01), grad clip 1, 5% warmup 후 cosine.
  확장(epoch 6-8) 구간은 사전 고정 규칙: 0.1*peak에서 0까지 cosine (warmup 없음, optimizer state 유지).
- loss: assistant 토큰(JSON+<end_of_turn>)의 effective-batch 토큰 평균. lm_head는 label 위치의 hidden에만 적용(수치적으로 동일한 loss).
- 재개: 50 optimizer step 및 epoch 경계에 ckpt_latest.pt를 원자적으로 저장. adapter는 epoch별 epoch_XX/adapter.pt로 보존.
- iter_011 수정: (1) run-dir 단일 writer lock (train.lock), (2) 시작 시 epoch adapter는 있으나 val_metrics가 없는 epoch의 validation을 복구
  (마지막 epoch 포함, 학습 상태·RNG 불변), (3) split ID 파일 내용·현재 file/pixel hash·GT를 입력 digest로 train_digest에 연결,
  (4) 검증된 부모 checkpoint를 migration manifest로만 가져온다.
사용: CUDA_VISIBLE_DEVICES=<gpu> python -m rsna_diag.train --run-dir D --lr 2e-4 --seed 17 --epochs 5 --protocol P [--migration M]
"""
import argparse
import json
import math
import os
import random
import sys
import time

import numpy as np

from . import generate, inputs, lock_protocol, lora, migrate, prompts as P, queue_lock, sft_data, sft_eval

MANIFEST = "results/iter_010/manifests/infer_manifest.jsonl"
GT = "results/iter_010/manifests/gt_manifest.json"
SPLIT_IDS = "results/iter_010/manifests/{}_ids.json"
PHASE1_EPOCHS = 5
EXT_FLOOR_FRAC = 0.1
CFG = {"r": 16, "alpha": 32, "dropout": 0.05, "weight_decay": 0.01, "betas": [0.9, 0.999], "eps": 1e-8, "grad_clip": 1.0,
       "warmup_frac": 0.05, "eff_batch": 16, "phase1_epochs": PHASE1_EPOCHS, "ext_floor_frac": EXT_FLOOR_FRAC,
       "prompt": "concise", "targets": sft_data.TARGET_LABEL}
train_digest = migrate.cfg_digest
LOCK_FD = [None]


def lr_at(step, steps_per_epoch, peak, phase1_epochs=PHASE1_EPOCHS, warmup_frac=0.05, ext_floor=EXT_FLOOR_FRAC, total_epochs=8):
    t1 = steps_per_epoch * phase1_epochs
    warm = math.ceil(warmup_frac * t1)
    if step < warm:
        return peak * (step + 1) / warm
    if step < t1:
        return 0.5 * peak * (1 + math.cos(math.pi * (step - warm) / (t1 - warm)))
    t2 = steps_per_epoch * (total_epochs - phase1_epochs)
    return 0.5 * ext_floor * peak * (1 + math.cos(math.pi * (step - t1) / t2))


def atomic_save(torch, obj, path):
    tmp = path + ".tmp"
    torch.save(obj, tmp)
    os.replace(tmp, path)


def atomic_json(obj, path):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def label_count(tok, target):
    return len(tok(target + "<end_of_turn>", add_special_tokens=False)["input_ids"])


def assistant_loss_sum(torch, model, batch, softcap):
    """batch(cuda) -> (CE 합, 학습 토큰 수). lm_head는 label 예측 위치에만 적용한다."""
    inp = {k: v for k, v in batch.items() if k != "labels"}
    inp["pixel_values"] = inp["pixel_values"].to(torch.bfloat16)
    out = model.model(**inp, use_cache=False)
    h = out.last_hidden_state[:, :-1]
    lab = batch["labels"][:, 1:]
    sel = lab != -100
    logits = model.lm_head(h[sel]).float()
    if softcap:
        logits = torch.tanh(logits / softcap) * softcap
    return torch.nn.functional.cross_entropy(logits, lab[sel], reduction="sum"), int(sel.sum())


class SFTDataset:
    def __init__(self, proc, items, gt, prompt, order):
        self.proc, self.items, self.gt, self.prompt, self.order = proc, items, gt, prompt, order

    def __len__(self):
        return len(self.order)

    def __getitem__(self, k):
        it = self.items[self.order[k]]
        image, _, _ = inputs.load_verified(it)  # 현재 pixel hash가 manifest와 다르면 예외
        tgt = sft_data.target_text([b["yxyx_norm"] for b in self.gt[it["id"]]["boxes"]])
        return sft_data.build_example(self.proc, image, self.prompt, tgt)


def setup_model(seed):
    torch, proc, model = generate.load_model()
    names = lora.apply_lora(model, CFG["r"], CFG["alpha"], CFG["dropout"], seed=seed)
    return torch, proc, model, names


def seed_all(torch, seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def rng_state(torch):
    return {"torch": torch.get_rng_state(), "cuda": torch.cuda.get_rng_state(), "np": np.random.get_state(), "py": random.getstate()}


def set_rng_state(torch, st):
    torch.set_rng_state(st["torch"])
    torch.cuda.set_rng_state(st["cuda"])
    np.random.set_state(st["np"])
    random.setstate(st["py"])


def save_adapter(torch, model, path, extra):
    st = lora.lora_state_dict(model)
    dg = lora.state_digest(st)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_save(torch, {"state": st, "config": {"r": CFG["r"], "alpha": CFG["alpha"]}, "digest": dg, **extra}, path)
    return dg


def val_loss(torch, model, proc, val_items, gt, softcap, prompt):
    model.eval()
    tot, n = 0.0, 0
    with torch.no_grad():
        for it in val_items:
            image, _, _ = inputs.load_verified(it)
            tgt = sft_data.target_text([b["yxyx_norm"] for b in gt[it["id"]]["boxes"]])
            ex = sft_data.build_example(proc, image, prompt, tgt)
            b = {k: (v.unsqueeze(0).cuda() if k in ("input_ids", "attention_mask", "labels", "token_type_ids") else v.cuda())
                 for k, v in ex.items() if k != "n_prefix"}
            s, c = assistant_loss_sum(torch, model, b, softcap)
            tot += float(s)
            n += c
    return tot / n, n


def record_request(torch, proc, model, eos_ids, it, cdig, pdig, adapter_digest, tag, epoch, out):
    pdg = P.digest(P.CONCISE)
    rec = generate.run_request(torch, proc, model, eos_ids, it, "concise", P.CONCISE)
    rec.update({"request_id": generate.request_id(generate.MODEL_REVISION, adapter_digest, it.get("split"), it["id"], pdg),
                "split": it.get("split"), "adapter_digest": adapter_digest, "protocol_digest": pdig, "config_digest": cdig,
                "worker": 0, "ts": time.time(), "run_tag": tag, "epoch": epoch})
    with open(out, "a") as f:
        f.write(json.dumps(rec) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return rec


def run_validation(torch, proc, model, env, cdig, pdig, val_items, gt, edges, out_dir, epoch, adapter_digest, tag, inputs_dig, stop_after=None):
    """epoch 끝 validation: 전체 val 생성(cap 래더) + parse + 지표. record는 generate와 같은 provenance를 갖는다.

    모든 (id, concise) 요청이 기존+신규 record로 채워지고 중복·잉여가 없을 때만 completion.json을 원자적으로 쓴다 (점수는 그 뒤 계산).
    stop_after: test 전용 (요청을 이 개수만 새로 기록하고 비정상 종료).
    """
    import glob
    prompts_used = {"concise": P.CONCISE}
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "gen_worker0.jsonl")
    files = {f: generate.read_records(f) for f in glob.glob(os.path.join(out_dir, "gen_worker*.jsonl"))}
    cache = {}
    px = lambda p: cache.setdefault(p, generate.load_image(p)[2])
    done = generate.validate_existing(files, val_items, ["concise"], prompts_used, cdig, adapter_digest, pdig, px)
    eos = env["eos_token_id"]
    eos_ids = set(eos if isinstance(eos, list) else [eos])
    model.eval()
    model.config.use_cache = True
    n_new = 0
    for it in val_items:
        if (it["id"], "concise") in done:
            continue
        done[(it["id"], "concise")] = record_request(torch, proc, model, eos_ids, it, cdig, pdig, adapter_digest, tag, epoch, out)
        n_new += 1
        if stop_after is not None and n_new >= stop_after:
            print("test stop in validation", flush=True)
            os._exit(4)
    model.config.use_cache = False
    ids = [i["id"] for i in val_items]
    expected = {(i, "concise") for i in ids}
    if set(done) != expected:
        raise RuntimeError(f"validation request set incomplete/extra: {len(expected - set(done))} missing, {len(set(done) - expected)} extra")
    atomic_json({"n_expected": len(expected), "n_actual_unique": len(done), "n_missing": 0, "n_duplicate": 0, "adapter_digest": adapter_digest,
                 "protocol_digest": pdig, "config_digest": cdig, "val_inputs_digest": inputs_dig, "epoch": epoch, "prompts": ["concise"],
                 "n_new_this_run": n_new}, os.path.join(out_dir, "completion.json"))
    preds = sft_eval.parse_records(done, ids, "concise", strict=True)
    summ = sft_eval.summarize(preds, gt, ids, edges)
    gen = [done[(i, "concise")] for i in ids]
    summ["generation"] = {"mean_out_tokens": float(np.mean([r["n_output_tokens"] for r in gen])),
                          "max_out_tokens": max(r["n_output_tokens"] for r in gen),
                          "n_cap_extended": sum(len(r["attempts"]) > 1 for r in gen),
                          "mean_runtime_s": float(np.mean([r["runtime_s_total"] for r in gen])),
                          "peak_mem_gb_max": max(r["peak_mem_alloc_gb_max"] for r in gen), "n_new_requests_this_run": n_new}
    return summ


def close_lock_fd(_worker_id):
    """DataLoader worker가 run lock의 fd 사본을 붙들지 않게 한다 (부모가 죽으면 lock이 커널에서 풀리도록)."""
    if LOCK_FD[0] is not None:
        try:
            os.close(LOCK_FD[0])
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--lr", type=float, required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--epochs", type=int, required=True)
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--microbatch", type=int, default=1)
    ap.add_argument("--ckpt-every", type=int, default=50)
    ap.add_argument("--train-ids", default=SPLIT_IDS.format("train"))
    ap.add_argument("--val-ids", default=SPLIT_IDS.format("validation"))
    ap.add_argument("--no-val", action="store_true", help="pilot: validation 생성/loss 생략")
    ap.add_argument("--max-steps", type=int, default=None, help="pilot/test: 이 optimizer step 수까지만")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--eff-batch", type=int, default=16, help="pilot 전용 변경 (본실험은 16 고정)")
    ap.add_argument("--pilot", action="store_true", help="복구 검사: split 전체 일치 검사·기본 ID 파일 강제를 완화 (본실험 금지)")
    ap.add_argument("--migration", default=None, help="검증된 부모 checkpoint를 새 run으로 가져오는 migration manifest")
    ap.add_argument("--stop-after-epoch-ckpt", type=int, default=None, help="test: 이 epoch의 adapter/ckpt 저장 직후(validation 전) 종료")
    ap.add_argument("--stop-in-validation", type=int, default=None, help="test: validation 요청을 이 개수 새로 기록한 뒤 종료")
    a = ap.parse_args()
    CFG["eff_batch"] = a.eff_batch
    if not a.no_val and a.eff_batch != 16 and not a.pilot:
        sys.exit("eff-batch override is pilot-only")
    if not a.pilot and (a.no_val or a.train_ids != SPLIT_IDS.format("train") or a.val_ids != SPLIT_IDS.format("validation")
                        or a.stop_after_epoch_ckpt or a.stop_in_validation):
        sys.exit("non-default ids / --no-val / stop hooks require --pilot")
    if not a.no_val and not a.pilot and a.epochs > PHASE1_EPOCHS and a.epochs != 8:
        sys.exit("extension is defined only up to 8 epochs")
    pdig = lock_protocol.verify(a.protocol)
    os.makedirs(a.run_dir, exist_ok=True)
    # 단일 writer lock: run-dir 안의 파일은 이 프로세스만 쓴다. lock 파일은 지우지 않으며 소유자가 종료되어야 커널이 푼다.
    lk, own, reclaimed = queue_lock.try_lock(os.path.join(os.path.realpath(a.run_dir), "train.lock"), queue_lock.my_info(role="train"))
    if lk is None:
        sys.exit(f"run-dir {a.run_dir} is owned by another live train process: {own}")
    LOCK_FD[0] = lk.fd
    try:
        run(a, pdig, reclaimed)
    finally:
        lk.release()


def run(a, pdig, reclaimed_lock):
    import torch
    split_tr, split_va = (None, None) if a.pilot else ("train", "validation")
    train_items, gt = inputs.load_items(MANIFEST, GT, a.train_ids, split_tr, exact=not a.pilot)
    val_items = []
    if not a.no_val:
        val_items, _ = inputs.load_items(MANIFEST, GT, a.val_ids, split_va, exact=not a.pilot)
    t_in = inputs.inputs_digest(train_items, gt)
    v_in = inputs.inputs_digest(val_items, gt) if val_items else None
    edges = sft_eval.area_edges(gt, [i for i in gt if gt[i]["split"] == "train"])
    seed_all(torch, a.seed)
    _, proc, model, names = setup_model(a.seed)
    tok = proc.tokenizer
    softcap = getattr(model.config.get_text_config(), "final_logit_softcapping", None)
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.config.use_cache = False
    params = list(lora.lora_params(model).values())
    n_train_params = sum(p.numel() for p in params)
    env = generate.env_info(torch, proc, model)
    cdig, _ = generate.config_digest(env, {"concise": P.CONCISE})
    full_cd, _ = generate.config_digest(env, P.all_prompts())
    if full_cd != json.load(open(a.protocol))["locked"]["generation_config_digest"]:
        sys.exit("runtime generation config digest != protocol")
    cfg = dict(CFG, lr=a.lr, seed=a.seed, microbatch=a.microbatch, n_train=len(train_items), n_val=len(val_items),
               model_revision=generate.MODEL_REVISION, protocol_digest=pdig, n_lora_targets=len(names), n_trainable=n_train_params,
               train_inputs_digest=t_in, val_inputs_digest=v_in)
    tdig = train_digest(cfg)
    cfg_path = os.path.join(a.run_dir, "train_config.json")
    if os.path.exists(cfg_path):
        old = json.load(open(cfg_path))
        if old["train_digest"] != tdig:
            sys.exit("train config differs from existing run_dir (refusing to resume/overwrite)")
    else:
        json.dump({"train_digest": tdig, "config": cfg, "lora_targets_head": names[:9], "env": env, "migration": a.migration,
                   "migration_sha256": migrate.file_sha(a.migration) if a.migration else None}, open(cfg_path, "w"), indent=1, default=str)
    opt = torch.optim.AdamW(params, lr=a.lr, betas=tuple(CFG["betas"]), eps=CFG["eps"], weight_decay=CFG["weight_decay"])
    n_tr = len(train_items)
    spe = math.ceil(n_tr / CFG["eff_batch"])
    step, epoch0, pos0 = 0, 0, 0
    ck = os.path.join(a.run_dir, "ckpt_latest.pt")
    logf = open(os.path.join(a.run_dir, "train_log.jsonl"), "a")

    def save_ckpt(epoch, pos, val_pending=None, parent=None):
        atomic_save(torch, {"lora": lora.lora_state_dict(model), "optimizer": opt.state_dict(), "step": step, "epoch": epoch,
                            "pos_in_epoch": pos, "rng": rng_state(torch), "train_digest": tdig, "val_pending_epoch": val_pending,
                            "base_revision": generate.MODEL_REVISION, "protocol_digest": pdig, "parent": parent}, ck)

    def log_event(**kw):
        logf.write(json.dumps({"ts": time.time(), **kw}) + "\n")
        logf.flush()

    if os.path.exists(ck):
        blob = torch.load(ck, map_location="cpu", weights_only=False)
        if blob["train_digest"] != tdig or blob["base_revision"] != generate.MODEL_REVISION or blob["protocol_digest"] != pdig:
            sys.exit("checkpoint provenance mismatch")
        lora.load_lora_state(model, blob["lora"])
        opt.load_state_dict(blob["optimizer"])
        step, epoch0, pos0 = blob["step"], blob["epoch"], blob["pos_in_epoch"]
        set_rng_state(torch, blob["rng"])
        print(f"resumed step={step} epoch={epoch0} pos={pos0}", flush=True)
        log_event(event="resume", step=step, epoch=epoch0, pos=pos0, stale_lock_reclaimed=bool(reclaimed_lock))
    elif a.migration:
        blob, mig = migrate.verify_parent(a.migration, cfg, pdig)
        lora.load_lora_state(model, blob["lora"])
        opt.load_state_dict(blob["optimizer"])
        step, epoch0, pos0 = blob["step"], blob["epoch"], blob["pos_in_epoch"]
        set_rng_state(torch, blob["rng"])
        # 부모 log는 checkpoint step까지만 유효한 trajectory다. 그 이후 step은 원본 이력으로만 남고 유효 step에서 분리한다.
        with open(os.path.join(a.run_dir, "parent_train_log_valid_prefix.jsonl"), "w") as pf:
            for ln in open(mig["parent_train_log"]):
                if ln.strip() and json.loads(ln)["step"] <= mig["parent_step"]:
                    pf.write(ln)
        log_event(event="imported_parent", parent_ckpt_sha256=mig["parent_ckpt_sha256"], step=step, epoch=epoch0, pos=pos0)
        save_ckpt(epoch0, pos0, parent={"ckpt_sha256": mig["parent_ckpt_sha256"], "step": step})
        print(f"imported parent checkpoint step={step} epoch={epoch0} pos={pos0}", flush=True)
    t0 = time.time()

    def validate_epoch(e, from_file, stop_after=None):
        """epoch e adapter로 validation. from_file이면 현재 학습 상태를 보관했다가 epoch adapter를 넣고 끝난 뒤 복원한다 (optimizer 불변, RNG 복원)."""
        epoch_dir = os.path.join(a.run_dir, f"epoch_{e:02d}")
        vm = os.path.join(epoch_dir, "val_metrics.json")
        if os.path.exists(vm):
            return
        rng_before = rng_state(torch)
        snap = lora.lora_state_dict(model) if from_file else None
        if from_file:
            blob_a = torch.load(os.path.join(epoch_dir, "adapter.pt"), map_location="cpu", weights_only=True)
            if lora.state_digest(blob_a["state"]) != blob_a["digest"]:
                raise RuntimeError(f"epoch {e} adapter file digest mismatch")
            lora.load_lora_state(model, blob_a["state"])
        adig = lora.state_digest(lora.lora_state_dict(model))
        torch.cuda.reset_peak_memory_stats()
        vl, vn = val_loss(torch, model, proc, val_items, gt, softcap, P.CONCISE)
        summ = run_validation(torch, proc, model, env, cdig, pdig, val_items, gt, edges, os.path.join(epoch_dir, "val_gen"), e, adig,
                              os.path.basename(a.run_dir), v_in, stop_after)
        summ.update({"val_loss": vl, "val_loss_tokens": vn, "epoch": e, "step": e * spe, "adapter_digest": adig, "lr": a.lr,
                     "seed": a.seed, "train_digest": tdig, "val_inputs_digest": v_in, "protocol_digest": pdig})
        atomic_json(summ, vm)
        if from_file:
            lora.load_lora_state(model, snap)
        set_rng_state(torch, rng_before)
        log_event(event="validation_done", epoch=e, val_loss=vl, utility=summ["utility"], recovered_from_file=from_file)
        print(f"epoch {e}: val_loss {vl:.4f} utility {summ['utility']:.4f} f1@.3 {summ['f1@0.3']:.4f}", flush=True)

    if not a.no_val:  # adapter 저장 뒤 validation을 못 끝낸 epoch는 다음 epoch 학습 전에 복구한다 (마지막 epoch 포함)
        for e in range(1, epoch0 + 1):
            epoch_dir = os.path.join(a.run_dir, f"epoch_{e:02d}")
            if not os.path.exists(os.path.join(epoch_dir, "adapter.pt")):
                raise RuntimeError(f"epoch {e} adapter missing although checkpoint is at epoch {epoch0}")
            if not os.path.exists(os.path.join(epoch_dir, "val_metrics.json")):
                print(f"recovering pending validation for epoch {e}", flush=True)
                validate_epoch(e, from_file=True)
    for epoch in range(epoch0, a.epochs):
        rng = np.random.default_rng(a.seed * 1000 + epoch)
        order = rng.permutation(n_tr)
        start_pos = pos0 if epoch == epoch0 else 0
        ds = SFTDataset(proc, train_items, gt, P.CONCISE, order)
        idx = list(range(start_pos * CFG["eff_batch"], n_tr))
        dl = torch.utils.data.DataLoader(torch.utils.data.Subset(ds, idx), batch_size=a.microbatch, shuffle=False, num_workers=a.workers,
                                         collate_fn=lambda ex: sft_data.collate(ex, tok.pad_token_id), prefetch_factor=2 if a.workers else None,
                                         worker_init_fn=close_lock_fd)
        model.train()
        it = iter(dl)
        for s in range(start_pos, spe):
            grp = order[s * CFG["eff_batch"]:(s + 1) * CFG["eff_batch"]]
            tot_tok = sum(label_count(tok, sft_data.target_text([b["yxyx_norm"] for b in gt[train_items[j]["id"]]["boxes"]])) for j in grp)
            lr = lr_at(step, spe, a.lr, total_epochs=8)
            for g in opt.param_groups:
                g["lr"] = lr
            loss_acc, ntok_seen = 0.0, 0
            n_micro = math.ceil(len(grp) / a.microbatch)
            for _ in range(n_micro):
                b = next(it)
                b = {k: v.cuda() for k, v in b.items()}
                if int((b["labels"] != -100).sum()) == 0:
                    raise RuntimeError("batch without assistant tokens")
                ls, nt = assistant_loss_sum(torch, model, b, softcap)
                (ls / tot_tok).backward()
                loss_acc += float(ls) / tot_tok
                ntok_seen += nt
            if ntok_seen != tot_tok:
                raise RuntimeError(f"label token count mismatch {ntok_seen} != {tot_tok}")
            gn = float(torch.nn.utils.clip_grad_norm_(params, CFG["grad_clip"]))
            if not math.isfinite(gn) or not math.isfinite(loss_acc):
                raise RuntimeError(f"non-finite loss/grad at step {step}: {loss_acc} {gn}")
            opt.step()
            opt.zero_grad(set_to_none=True)
            step += 1
            logf.write(json.dumps({"step": step, "epoch": epoch + 1, "pos": s + 1, "loss": loss_acc, "grad_norm": gn, "lr": lr,
                                   "n_examples": len(grp), "elapsed_s": time.time() - t0,
                                   "peak_mem_gb": torch.cuda.max_memory_allocated() / 2 ** 30}) + "\n")
            logf.flush()
            if step % a.ckpt_every == 0 and (s + 1) < spe:
                save_ckpt(epoch, s + 1)
            if a.max_steps is not None and step >= a.max_steps:
                save_ckpt(epoch, s + 1)
                print("max-steps reached", flush=True)
                return
        del dl, it
        epoch_dir = os.path.join(a.run_dir, f"epoch_{epoch + 1:02d}")
        save_adapter(torch, model, os.path.join(epoch_dir, "adapter.pt"), {"epoch": epoch + 1, "step": step, "train_digest": tdig})
        save_ckpt(epoch + 1, 0, val_pending=None if a.no_val else epoch + 1)
        if a.stop_after_epoch_ckpt == epoch + 1:
            print("test stop after epoch ckpt", flush=True)
            os._exit(3)
        if not a.no_val:
            validate_epoch(epoch + 1, from_file=False, stop_after=a.stop_in_validation)
        pos0 = 0
    print("training complete", flush=True)


if __name__ == "__main__":
    main()
