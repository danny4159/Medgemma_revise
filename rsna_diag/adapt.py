"""iter_013 추가 적응 단계 학습기 (C: 추가 SFT, H: 좌표 가중 CE, D: DIST²Loss 자리별 이식). 사용:
CUDA_VISIBLE_DEVICES=<gpu> python -m rsna_diag.adapt --run-dir D --stage-config S.json --loss C|H|D --lr 2e-5 --protocol P --microbatch 2

- 공통 시작점 = stage config의 parent adapter (파일 sha256·digest 검증). base + 언어층 LoRA 범위는 그대로, optimizer는 새로 초기화한다
  (부모 학습 trajectory를 이어서 재개한 것이 아니다). 학습 일정은 이 단계의 총 update에 대해 5% warmup 뒤 cosine(0까지). 기존 5->8 epoch 규칙 미사용.
- loss: (CE합 + alpha * 추가항합) / N, N = effective batch의 assistant 학습 token 수 (모든 조건 동일). 추가 항은 coord_loss.loss_sums.
  C도 H/D의 추가 항 값을 gradient 없이 기록한다 (조건 간 loss 성분 비교용).
- 검증: 각 epoch 끝(=milestone)에 stage config의 val_ids(V200)를 생성 평가한다. 시작점(B0)의 V200은 기존 검증된 출력의 부분집합을 쓴다 (adapt_eval).
- train.py의 helper(원자 저장·digest·RNG·validation 생성)를 재사용하고 그 코드는 수정하지 않는다. 재개/복구/lock 동작은 train.py와 같다.
- stage/ids/parent 파일은 protocol의 잠긴 파일이어야 한다 (lock_protocol --extra).
"""
import argparse
import hashlib
import json
import math
import os
import sys
import time

import numpy as np

from . import coord_loss as CL, generate, inputs, lock_protocol, lora, migrate, prompts as P, queue_lock, select, sft_data, sft_eval
from . import train as T

STAGE_KEYS = ("stage_id", "parent_adapter", "parent_adapter_sha256", "parent_adapter_digest", "train_ids", "val_ids", "seed", "epochs",
              "eff_batch", "allowed_lrs", "warmup_frac", "validate", "alpha", "tau")


def lr_at(step, total, peak, warmup_frac):
    warm = max(1, math.ceil(warmup_frac * total))
    if step < warm:
        return peak * (step + 1) / warm
    return 0.5 * peak * (1 + math.cos(math.pi * (step - warm) / max(1, total - warm)))


class AdaptDataset:
    def __init__(self, tok, proc, items, gt, prompt, order, dig_ids):
        self.tok, self.proc, self.items, self.gt, self.prompt, self.order, self.dig = tok, proc, items, gt, prompt, order, dig_ids

    def __len__(self):
        return len(self.order)

    def __getitem__(self, k):
        it = self.items[self.order[k]]
        image, _, _ = inputs.load_verified(it)
        tgt = sft_data.target_text([b["yxyx_norm"] for b in self.gt[it["id"]]["boxes"]])
        ex = sft_data.build_example(self.proc, image, self.prompt, tgt)
        ex["coord_w"] = CL.coord_weights(self.tok, tgt, ex["input_ids"].tolist(), ex["n_prefix"], self.dig)
        ex["sample_pos"] = int(k)
        return ex


def collate(ex, pad_id):
    import torch
    cw = [e["coord_w"] for e in ex]
    out = sft_data.collate([{k: v for k, v in e.items() if k != "coord_w"} for e in ex], pad_id)
    t = torch.zeros((len(ex), out["input_ids"].shape[1]), dtype=torch.float32)
    for i, w in enumerate(cw):
        t[i, :len(w)] = torch.tensor(w, dtype=torch.float32)
    out["coord_w"] = t  # 모델 forward에는 넣지 않는다 (adapt_loss가 pop)
    return out


def adapt_loss(torch, model, batch, softcap, mode, dig_ids, alpha, tau):
    """batch(cuda) -> dict(ce_sum, extra_sum(loss에 쓰는 것), mon_h, mon_d (detached), n_tok, n_coord)."""
    b = dict(batch)
    cw, labels = b.pop("coord_w"), b.pop("labels")
    b["pixel_values"] = b["pixel_values"].to(torch.bfloat16)
    out = model.model(**b, use_cache=False)
    h = out.last_hidden_state[:, :-1]
    lab = labels[:, 1:]
    sel = lab != -100
    logits = model.lm_head(h[sel]).float()
    softcap_v = getattr(model.config.get_text_config(), "final_logit_softcapping", None)
    if softcap_v:
        logits = torch.tanh(logits / softcap_v) * softcap_v
    y, w = lab[sel], cw[:, 1:][sel]
    if int((cw > 0).sum()) != int((w > 0).sum()):
        raise RuntimeError("coordinate token outside assistant label positions")
    ce_sum, extra = CL.loss_sums(torch, logits, y, w, mode, dig_ids, alpha, tau)
    with torch.no_grad():
        ld = logits.detach()
        mon_h = CL.loss_sums(torch, ld, y, w, "H", dig_ids)[1]
        mon_d = CL.loss_sums(torch, ld, y, w, "D", dig_ids, alpha, tau)[1]
    return {"ce_sum": ce_sum, "extra_sum": extra, "mon_h": mon_h, "mon_d": mon_d, "n_tok": int(sel.sum()), "n_coord": int((w > 0).sum())}


def load_stage(path, protocol):
    st = json.load(open(path))
    miss = [k for k in STAGE_KEYS if k not in st]
    if miss:
        sys.exit(f"stage config missing keys {miss}")
    locked = json.load(open(protocol))["locked"]["files"]
    for k in (path, st["parent_adapter"], st["train_ids"], st["val_ids"]):
        if os.path.relpath(k) not in locked:
            sys.exit(f"{k} is not a locked protocol file")
    if hashlib.sha256(open(st["parent_adapter"], "rb").read()).hexdigest() != st["parent_adapter_sha256"]:
        sys.exit("parent adapter file sha256 != stage config")
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--stage-config", required=True)
    ap.add_argument("--loss", required=True, choices=["C", "H", "D"])
    ap.add_argument("--lr", type=float, required=True)
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--microbatch", type=int, default=2)
    ap.add_argument("--ckpt-every", type=int, default=50)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--max-steps", type=int, default=None, help="test: 이 optimizer step까지만 (checkpoint 저장 후 종료)")
    ap.add_argument("--stop-after-step", type=int, default=None, help="test: 정기 checkpoint step 직후 비정상 종료 (재개 검사)")
    ap.add_argument("--deterministic", action="store_true", help="검사 전용: 결정적 kernel (선택·본실험 금지)")
    ap.add_argument("--stop-in-validation", type=int, default=None, help="test: validation 요청을 이 개수 새로 쓴 뒤 종료")
    a = ap.parse_args()
    if a.deterministic:
        os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    pdig = lock_protocol.verify(a.protocol)
    st = load_stage(a.stage_config, a.protocol)
    if a.lr not in st["allowed_lrs"]:
        sys.exit(f"lr {a.lr} not in stage allowed_lrs {st['allowed_lrs']}")
    os.makedirs(a.run_dir, exist_ok=True)
    lk, own, reclaimed = queue_lock.try_lock(os.path.join(os.path.realpath(a.run_dir), "train.lock"), queue_lock.my_info(role="adapt"))
    if lk is None:
        sys.exit(f"run-dir {a.run_dir} is owned by another live process: {own}")
    T.LOCK_FD[0] = lk.fd
    try:
        run(a, st, pdig, reclaimed)
    finally:
        lk.release()


def run(a, st, pdig, reclaimed_lock):
    import torch
    train_items, gt = inputs.load_items(T.MANIFEST, T.GT, st["train_ids"], "train", exact=False)
    val_items = inputs.load_items(T.MANIFEST, T.GT, st["val_ids"], "validation", exact=False)[0] if st["validate"] else []
    t_in = inputs.inputs_digest(train_items, gt)
    v_in = inputs.inputs_digest(val_items, gt) if val_items else None
    edges = sft_eval.area_edges(gt, [i for i in gt if gt[i]["split"] == "train"])
    if a.deterministic:
        T.set_deterministic(torch)
    seed = st["seed"]
    T.seed_all(torch, seed)
    _, proc, model, names = T.setup_model(seed)
    tok = proc.tokenizer
    dig_ids = CL.digit_ids(tok)
    softcap = getattr(model.config.get_text_config(), "final_logit_softcapping", None)
    pblob = torch.load(st["parent_adapter"], map_location="cpu", weights_only=True)
    if lora.state_digest(pblob["state"]) != st["parent_adapter_digest"] or pblob.get("digest") != st["parent_adapter_digest"]:
        sys.exit("parent adapter digest != stage config")
    if pblob["config"] != {"r": T.CFG["r"], "alpha": T.CFG["alpha"]}:
        sys.exit("parent adapter rank/alpha != trainer config")
    lora.load_lora_state(model, pblob["state"])
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.config.use_cache = False
    params = list(lora.lora_params(model).values())
    env = generate.env_info(torch, proc, model)
    cdig, _ = generate.config_digest(env, {"concise": P.CONCISE})
    full_cd, _ = generate.config_digest(env, P.all_prompts())
    if full_cd != json.load(open(a.protocol))["locked"]["generation_config_digest"]:
        sys.exit("runtime generation config digest != protocol")
    eb = st["eff_batch"]
    n_tr = len(train_items)
    spe = math.ceil(n_tr / eb)
    total = spe * st["epochs"]
    cfg = dict(T.CFG, lr=a.lr, seed=seed, microbatch=a.microbatch, eff_batch=eb, n_train=n_tr, n_val=len(val_items), stage=st, stage_config_sha256=migrate.file_sha(a.stage_config),
               loss_mode=a.loss, alpha=st["alpha"], tau=st["tau"], place_weights="right-to-left 1,2,3,4", total_updates=total, steps_per_epoch=spe,
               model_revision=generate.MODEL_REVISION, protocol_digest=pdig, n_lora_targets=len(names), n_trainable=sum(p.numel() for p in params),
               train_inputs_digest=t_in, val_inputs_digest=v_in, deterministic=bool(a.deterministic), optimizer_init="fresh AdamW (parent optimizer not resumed)",
               dataloader_rng="torch.Generator seeded seed*1000+epoch")
    tdig = migrate.cfg_digest(cfg)
    cfg_path = os.path.join(a.run_dir, "train_config.json")
    if os.path.exists(cfg_path):
        if json.load(open(cfg_path))["train_digest"] != tdig:
            sys.exit("train config differs from existing run_dir (refusing to resume/overwrite)")
    else:
        json.dump({"train_digest": tdig, "config": cfg, "env": env}, open(cfg_path, "w"), indent=1, default=str)
    opt = torch.optim.AdamW(params, lr=a.lr, betas=tuple(T.CFG["betas"]), eps=T.CFG["eps"], weight_decay=T.CFG["weight_decay"])
    step, epoch0, pos0 = 0, 0, 0
    ck = os.path.join(a.run_dir, "ckpt_latest.pt")
    logf = open(os.path.join(a.run_dir, "train_log.jsonl"), "a")

    def log_event(**kw):
        logf.write(json.dumps({"ts": time.time(), **kw}) + "\n")
        logf.flush()

    def save_ckpt(epoch, pos, val_pending=None):
        dg = T.live_digests(torch, model, opt)
        T.atomic_save(torch, {"lora": lora.lora_state_dict(model), "optimizer": opt.state_dict(), "step": step, "epoch": epoch, "pos_in_epoch": pos,
                              "rng": T.rng_state(torch), "train_digest": tdig, "val_pending_epoch": val_pending, "loss_mode": a.loss,
                              "base_revision": generate.MODEL_REVISION, "protocol_digest": pdig, "digests": dg}, ck)
        log_event(event="checkpoint", step=step, epoch=epoch, pos=pos, digests=dg)

    if os.path.exists(ck):
        blob = torch.load(ck, map_location="cpu", weights_only=False)
        if blob["train_digest"] != tdig or blob["base_revision"] != generate.MODEL_REVISION or blob["protocol_digest"] != pdig or blob["loss_mode"] != a.loss:
            sys.exit("checkpoint provenance mismatch")
        lora.load_lora_state(model, blob["lora"])
        opt.load_state_dict(blob["optimizer"])
        step, epoch0, pos0 = blob["step"], blob["epoch"], blob["pos_in_epoch"]
        T.set_rng_state(torch, blob["rng"])
        restored = T.live_digests(torch, model, opt)
        if restored != blob["digests"]:
            sys.exit(f"restored state != saved checkpoint state: saved {blob['digests']} restored {restored}")
        print(f"resumed step={step} epoch={epoch0} pos={pos0}", flush=True)
        log_event(event="resume", step=step, epoch=epoch0, pos=pos0, stale_lock_reclaimed=bool(reclaimed_lock), restored_digests=restored, restored_equals_saved=True)
    t0 = time.time()

    def verify_existing_val(e):
        select.verify_epoch(a.run_dir, e, json.load(open(cfg_path)), v_in, a.protocol, val_items, gt)

    def validate_epoch(e, from_file, stop_after=None):
        epoch_dir = os.path.join(a.run_dir, f"epoch_{e:02d}")
        vm = os.path.join(epoch_dir, "val_metrics.json")
        if os.path.exists(vm):
            verify_existing_val(e)
            return
        rng_before = T.rng_state(torch)
        pre = T.live_digests(torch, model, opt)
        snap = lora.lora_state_dict(model) if from_file else None
        if from_file:
            ba = torch.load(os.path.join(epoch_dir, "adapter.pt"), map_location="cpu", weights_only=True)
            if lora.state_digest(ba["state"]) != ba["digest"]:
                raise RuntimeError(f"epoch {e} adapter file digest mismatch")
            lora.load_lora_state(model, ba["state"])
        adig = lora.state_digest(lora.lora_state_dict(model))
        torch.cuda.reset_peak_memory_stats()
        vl, vn = T.val_loss(torch, model, proc, val_items, gt, softcap, P.CONCISE)
        summ = T.run_validation(torch, proc, model, env, cdig, pdig, val_items, gt, edges, os.path.join(epoch_dir, "val_gen"), e, adig,
                                os.path.basename(a.run_dir), v_in, stop_after)
        summ.update({"val_loss": vl, "val_loss_tokens": vn, "epoch": e, "step": e * spe, "adapter_digest": adig, "lr": a.lr, "seed": seed,
                     "train_digest": tdig, "val_inputs_digest": v_in, "protocol_digest": pdig})
        T.atomic_json(summ, vm)
        if from_file:
            lora.load_lora_state(model, snap)
        T.set_rng_state(torch, rng_before)
        post = T.live_digests(torch, model, opt)
        if post != pre:
            raise RuntimeError(f"validation changed training state: before {pre} after {post}")
        log_event(event="validation_done", epoch=e, val_loss=vl, utility=summ["utility"], recovered_from_file=from_file, state_unchanged=True, digests=post)
        print(f"epoch {e}: val_loss {vl:.4f} f1@.3 {summ['f1@0.3']:.4f} f1@.5 {summ['f1@0.5']:.4f}", flush=True)

    if val_items:
        for e in range(1, epoch0 + 1):
            ed = os.path.join(a.run_dir, f"epoch_{e:02d}")
            if not os.path.exists(os.path.join(ed, "adapter.pt")):
                raise RuntimeError(f"epoch {e} adapter missing although checkpoint is at epoch {epoch0}")
            if not os.path.exists(os.path.join(ed, "val_metrics.json")):
                print(f"recovering pending validation for epoch {e}", flush=True)
                validate_epoch(e, from_file=True)
            else:
                verify_existing_val(e)
    for epoch in range(epoch0, st["epochs"]):
        order = np.random.default_rng(seed * 1000 + epoch).permutation(n_tr)
        start_pos = pos0 if epoch == epoch0 else 0
        ds = AdaptDataset(tok, proc, train_items, gt, P.CONCISE, order, dig_ids)
        dl_gen = torch.Generator()
        dl_gen.manual_seed(seed * 1000 + epoch)
        dl = torch.utils.data.DataLoader(torch.utils.data.Subset(ds, list(range(start_pos * eb, n_tr))), batch_size=a.microbatch, shuffle=False,
                                         num_workers=a.workers, collate_fn=lambda ex: collate(ex, tok.pad_token_id), prefetch_factor=2 if a.workers else None,
                                         worker_init_fn=T.close_lock_fd, generator=dl_gen)
        model.train()
        it = iter(dl)
        for s in range(start_pos, spe):
            grp = order[s * eb:(s + 1) * eb]
            tot_tok = sum(T.label_count(tok, sft_data.target_text([b["yxyx_norm"] for b in gt[train_items[j]["id"]]["boxes"]])) for j in grp)
            lr = lr_at(step, total, a.lr, st["warmup_frac"])
            for g in opt.param_groups:
                g["lr"] = lr
            rng_before, opt_step_before = T.rng_digest(torch), T.opt_step_count(opt)
            if not model.training:
                raise RuntimeError("model not in train mode at optimizer step")
            acc = {"ce": 0.0, "extra": 0.0, "mon_h": 0.0, "mon_d": 0.0}
            ntok_seen = ncoord = 0
            seen_pos, tok_h = [], hashlib.sha256()
            for _ in range(math.ceil(len(grp) / a.microbatch)):
                b = next(it)
                seen_pos += b.pop("sample_pos").tolist()
                tok_h.update(T.batch_token_digest(b).digest())
                tok_h.update(b["coord_w"].contiguous().numpy().tobytes())
                b = {k: v.cuda() for k, v in b.items()}
                r = adapt_loss(torch, model, b, softcap, a.loss, dig_ids, st["alpha"], st["tau"])
                ((r["ce_sum"] + st["alpha"] * r["extra_sum"]) / tot_tok).backward()
                acc["ce"] += float(r["ce_sum"]) / tot_tok
                acc["extra"] += float(r["extra_sum"]) / tot_tok
                acc["mon_h"] += float(r["mon_h"]) / tot_tok
                acc["mon_d"] += float(r["mon_d"]) / tot_tok
                ntok_seen += r["n_tok"]
                ncoord += r["n_coord"]
            if ntok_seen != tot_tok:
                raise RuntimeError(f"label token count mismatch {ntok_seen} != {tot_tok}")
            planned = [train_items[j]["id"] for j in grp]
            actual = [train_items[order[p]]["id"] for p in seen_pos]
            if actual != planned or seen_pos != list(range(s * eb, s * eb + len(grp))):
                raise RuntimeError(f"step {step + 1}: DataLoader batch != planned batch")
            gn = float(torch.nn.utils.clip_grad_norm_(params, T.CFG["grad_clip"]))
            loss_total = acc["ce"] + st["alpha"] * acc["extra"]
            if not math.isfinite(gn) or not math.isfinite(loss_total):
                raise RuntimeError(f"non-finite loss/grad at step {step}: {loss_total} {gn}")
            opt.step()
            opt.zero_grad(set_to_none=True)
            step += 1
            logf.write(json.dumps({"step": step, "epoch": epoch + 1, "pos": s + 1, "loss": loss_total, "ce": acc["ce"], "extra_raw": acc["extra"],
                                   "extra_weighted": st["alpha"] * acc["extra"], "monitor_H_extra_raw": acc["mon_h"], "monitor_D_extra_raw": acc["mon_d"],
                                   "n_label_tokens": tot_tok, "n_coord_tokens": ncoord, "grad_norm": gn, "lr": lr, "n_examples": len(grp),
                                   "elapsed_s": time.time() - t0, "peak_mem_gb": torch.cuda.max_memory_allocated() / 2 ** 30, "batch_ids": actual,
                                   "batch_token_sha": tok_h.hexdigest()[:24], "rng_before": rng_before, "opt_step_before": opt_step_before,
                                   "train_mode": True}) + "\n")
            logf.flush()
            saved = False
            if step % a.ckpt_every == 0 and (s + 1) < spe:
                save_ckpt(epoch, s + 1)
                saved = True
            if a.stop_after_step is not None and step == a.stop_after_step:
                if not saved:
                    raise RuntimeError("--stop-after-step must coincide with a regular mid-epoch checkpoint step")
                print("test stop after mid-epoch step checkpoint", flush=True)
                os._exit(5)
            if a.max_steps is not None and step >= a.max_steps:
                save_ckpt(epoch, s + 1)
                print("max-steps reached", flush=True)
                return
        del dl, it
        ed = os.path.join(a.run_dir, f"epoch_{epoch + 1:02d}")
        T.save_adapter(torch, model, os.path.join(ed, "adapter.pt"), {"epoch": epoch + 1, "step": step, "train_digest": tdig})
        save_ckpt(epoch + 1, 0, val_pending=epoch + 1 if val_items else None)
        if val_items:
            validate_epoch(epoch + 1, from_file=False, stop_after=a.stop_in_validation)
        pos0 = 0
    print("training complete", flush=True)
    T.atomic_json({"status": "complete", "steps": step, "loss_mode": a.loss, "train_digest": tdig, "wall_s": time.time() - t0}, os.path.join(a.run_dir, "done.json"))


if __name__ == "__main__":
    main()
