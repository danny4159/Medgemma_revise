"""직접 병변 LoRA SFT 학습 (iter_010). 표준 torch LoRA, assistant-only CE, 재개 가능 checkpoint, epoch별 validation 생성 평가.

- base bf16 동결, LoRA(fp32) rank16/alpha32/dropout0.05, AdamW(wd 0.01), grad clip 1, 5% warmup 후 cosine.
  확장(epoch 6-8) 구간은 사전 고정 규칙: 0.1*peak에서 0까지 cosine (warmup 없음, optimizer state 유지).
- loss: assistant 토큰(JSON+<end_of_turn>)의 effective-batch 토큰 평균. lm_head는 label 위치의 hidden에만 적용(수치적으로 동일한 loss).
- 재개: 50 optimizer step 및 epoch 경계에 ckpt_latest.pt를 원자적으로 저장. adapter는 epoch별 epoch_XX/adapter.pt로 보존.
사용: CUDA_VISIBLE_DEVICES=<gpu> python -m rsna_diag.train --run-dir D --lr 2e-4 --seed 17 --epochs 5 --protocol P
"""
import argparse
import hashlib
import json
import math
import os
import random
import sys
import time

import numpy as np

from . import generate, lock_protocol, lora, prompts as P, sft_data, sft_eval

MANIFEST = "results/iter_010/manifests/infer_manifest.jsonl"
GT = "results/iter_010/manifests/gt_manifest.json"
SPLIT_IDS = "results/iter_010/manifests/{}_ids.json"
PHASE1_EPOCHS = 5
EXT_FLOOR_FRAC = 0.1
CFG = {"r": 16, "alpha": 32, "dropout": 0.05, "weight_decay": 0.01, "betas": [0.9, 0.999], "eps": 1e-8, "grad_clip": 1.0,
       "warmup_frac": 0.05, "eff_batch": 16, "phase1_epochs": PHASE1_EPOCHS, "ext_floor_frac": EXT_FLOOR_FRAC,
       "prompt": "concise", "targets": sft_data.TARGET_LABEL}


def lr_at(step, steps_per_epoch, peak, phase1_epochs=PHASE1_EPOCHS, warmup_frac=0.05, ext_floor=EXT_FLOOR_FRAC, total_epochs=8):
    t1 = steps_per_epoch * phase1_epochs
    warm = math.ceil(warmup_frac * t1)
    if step < warm:
        return peak * (step + 1) / warm
    if step < t1:
        return 0.5 * peak * (1 + math.cos(math.pi * (step - warm) / (t1 - warm)))
    t2 = steps_per_epoch * (total_epochs - phase1_epochs)
    return 0.5 * ext_floor * peak * (1 + math.cos(math.pi * (step - t1) / t2))


def train_digest(cfg):
    return hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()


def atomic_save(torch, obj, path):
    tmp = path + ".tmp"
    torch.save(obj, tmp)
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
        image, _, _ = generate.load_image(it["image"])
        tgt = sft_data.target_text([b["yxyx_norm"] for b in self.gt[it["id"]]["boxes"]])
        return sft_data.build_example(self.proc, image, self.prompt, tgt)


def setup_model(seed, adapter_state=None):
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
            image, _, _ = generate.load_image(it["image"])
            tgt = sft_data.target_text([b["yxyx_norm"] for b in gt[it["id"]]["boxes"]])
            ex = sft_data.build_example(proc, image, prompt, tgt)
            b = {k: (v.unsqueeze(0).cuda() if k in ("input_ids", "attention_mask", "labels", "token_type_ids") else v.cuda())
                 for k, v in ex.items() if k != "n_prefix"}
            s, c = assistant_loss_sum(torch, model, b, softcap)
            tot += float(s)
            n += c
    return tot / n, n


def run_validation(torch, proc, model, env, cdig, pdig, val_items, gt, edges, out_dir, epoch, adapter_digest, tag):
    """epoch 끝 validation: 전체 val 생성(cap 래더) + parse + 지표. record는 generate와 같은 provenance를 갖는다."""
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
    pdg = P.digest(P.CONCISE)
    model.eval()
    model.config.use_cache = True
    for it in val_items:
        if (it["id"], "concise") in done:
            continue
        rec = generate.run_request(torch, proc, model, eos_ids, it, "concise", P.CONCISE)
        rec.update({"request_id": generate.request_id(generate.MODEL_REVISION, adapter_digest, it.get("split"), it["id"], pdg),
                    "split": it.get("split"), "adapter_digest": adapter_digest, "protocol_digest": pdig, "config_digest": cdig,
                    "worker": 0, "ts": time.time(), "run_tag": tag, "epoch": epoch})
        with open(out, "a") as f:
            f.write(json.dumps(rec) + "\n")
            f.flush()
            os.fsync(f.fileno())
        done[(it["id"], "concise")] = rec
    model.config.use_cache = False
    ids = [i["id"] for i in val_items]
    recs = {k: v for k, v in done.items()}
    preds = sft_eval.parse_records(recs, ids, "concise")
    summ = sft_eval.summarize(preds, gt, ids, edges)
    gen = [recs[(i, "concise")] for i in ids]
    summ["generation"] = {"mean_out_tokens": float(np.mean([r["n_output_tokens"] for r in gen])),
                          "max_out_tokens": max(r["n_output_tokens"] for r in gen),
                          "n_cap_extended": sum(len(r["attempts"]) > 1 for r in gen),
                          "mean_runtime_s": float(np.mean([r["runtime_s_total"] for r in gen])),
                          "peak_mem_gb_max": max(r["peak_mem_alloc_gb_max"] for r in gen)}
    return summ


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
    a = ap.parse_args()
    CFG["eff_batch"] = a.eff_batch
    if not a.no_val and a.eff_batch != 16:
        sys.exit("eff-batch override is pilot-only (--no-val)")
    if not a.no_val and a.epochs > PHASE1_EPOCHS and a.epochs != 8:
        sys.exit("extension is defined only up to 8 epochs")
    pdig = lock_protocol.verify(a.protocol)
    import torch
    items_all = {json.loads(l)["id"]: json.loads(l) for l in open(MANIFEST) if l.strip()}
    gt = json.load(open(GT))
    tr_ids, va_ids = json.load(open(a.train_ids)), json.load(open(a.val_ids))
    train_items = [items_all[i] for i in sorted(tr_ids)]
    val_items = [items_all[i] for i in sorted(va_ids)]
    assert all(it["split"] == "train" for it in train_items) or a.no_val, "train ids must be from train split"
    if a.no_val is False:
        assert all(it["split"] == "validation" for it in val_items)
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
               model_revision=generate.MODEL_REVISION, protocol_digest=pdig, n_lora_targets=len(names), n_trainable=n_train_params)
    tdig = train_digest(cfg)
    os.makedirs(a.run_dir, exist_ok=True)
    cfg_path = os.path.join(a.run_dir, "train_config.json")
    if os.path.exists(cfg_path):
        old = json.load(open(cfg_path))
        if old["train_digest"] != tdig:
            sys.exit("train config differs from existing run_dir (refusing to resume/overwrite)")
    else:
        json.dump({"train_digest": tdig, "config": cfg, "lora_targets_head": names[:9], "env": env}, open(cfg_path, "w"), indent=1, default=str)
    opt = torch.optim.AdamW(params, lr=a.lr, betas=tuple(CFG["betas"]), eps=CFG["eps"], weight_decay=CFG["weight_decay"])
    n_tr = len(train_items)
    spe = math.ceil(n_tr / CFG["eff_batch"])
    step, epoch0, pos0 = 0, 0, 0
    ck = os.path.join(a.run_dir, "ckpt_latest.pt")
    if os.path.exists(ck):
        blob = torch.load(ck, map_location="cpu", weights_only=False)
        if blob["train_digest"] != tdig or blob["base_revision"] != generate.MODEL_REVISION or blob["protocol_digest"] != pdig:
            sys.exit("checkpoint provenance mismatch")
        lora.load_lora_state(model, blob["lora"])
        opt.load_state_dict(blob["optimizer"])
        step, epoch0, pos0 = blob["step"], blob["epoch"], blob["pos_in_epoch"]
        set_rng_state(torch, blob["rng"])
        print(f"resumed step={step} epoch={epoch0} pos={pos0}", flush=True)
    logf = open(os.path.join(a.run_dir, "train_log.jsonl"), "a")
    t0 = time.time()
    acc = max(1, CFG["eff_batch"] // a.microbatch)

    def save_ckpt(epoch, pos):
        atomic_save(torch, {"lora": lora.lora_state_dict(model), "optimizer": opt.state_dict(), "step": step, "epoch": epoch,
                            "pos_in_epoch": pos, "rng": rng_state(torch), "train_digest": tdig,
                            "base_revision": generate.MODEL_REVISION, "protocol_digest": pdig}, ck)

    for epoch in range(epoch0, a.epochs):
        rng = np.random.default_rng(a.seed * 1000 + epoch)
        order = rng.permutation(n_tr)
        start_pos = pos0 if epoch == epoch0 else 0
        ds = SFTDataset(proc, train_items, gt, P.CONCISE, order)
        idx = list(range(start_pos * CFG["eff_batch"], n_tr))
        dl = torch.utils.data.DataLoader(torch.utils.data.Subset(ds, idx), batch_size=a.microbatch, shuffle=False, num_workers=a.workers,
                                         collate_fn=lambda ex: sft_data.collate(ex, tok.pad_token_id), prefetch_factor=2 if a.workers else None)
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
        adig = save_adapter(torch, model, os.path.join(epoch_dir, "adapter.pt"), {"epoch": epoch + 1, "step": step, "train_digest": tdig})
        save_ckpt(epoch + 1, 0)
        if not a.no_val:
            vm = os.path.join(epoch_dir, "val_metrics.json")
            if not os.path.exists(vm):
                torch.cuda.reset_peak_memory_stats()
                vl, vn = val_loss(torch, model, proc, val_items, gt, softcap, P.CONCISE)
                summ = run_validation(torch, proc, model, env, cdig, pdig, val_items, gt, edges, os.path.join(epoch_dir, "val_gen"),
                                      epoch + 1, adig, os.path.basename(a.run_dir))
                summ.update({"val_loss": vl, "val_loss_tokens": vn, "epoch": epoch + 1, "step": step, "adapter_digest": adig,
                             "lr": a.lr, "seed": a.seed})
                json.dump(summ, open(vm, "w"), indent=1)
                print(f"epoch {epoch + 1}: val_loss {vl:.4f} utility {summ['utility']:.4f} f1@.3 {summ['f1@0.3']:.4f}", flush=True)
        pos0 = 0
    print("training complete", flush=True)


if __name__ == "__main__":
    main()
