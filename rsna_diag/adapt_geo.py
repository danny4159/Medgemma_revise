"""iter_014 학습기: C(직접 추가 SFT) / U(GT 질량을 맞춘 균등 pseudo-box) / G(GIoU 가중 pseudo-box). 손실 정의는 geo_loss.py 참조. 사용:
CUDA_VISIBLE_DEVICES=<gpu> python -m rsna_diag.adapt_geo --run-dir D --stage-config S.json --loss C|U|G --lr 2e-5 --protocol P --microbatch 2 --branch-microbatch 4

- adapt.py(iter_013)의 재개·validation·lock 동작을 그대로 따른다 (train.py helper 재사용). 달라지는 것은 (1) GT sequence의 token별 가중치, (2) 후보 branch의
  순차 forward/backward 누적(같은 optimizer update 안, 모든 branch 뒤에만 optimizer.step), (3) 추가 provenance(후보 manifest digest, branch digest).
- C는 가중치가 전부 1이고 branch가 없어 iter_013 C와 같은 손실이다 (수치 환원 검사: tests).
- 후보 branch의 prefix hidden state/KV cache는 재사용하지 않는다 (LoRA를 통과하는 값을 detach하지 않으며 branch마다 전체 forward).
"""
import argparse
import hashlib
import json
import math
import os
import sys
import time

import numpy as np

from . import adapt as A, coord_loss as CL, generate, geo_loss as GL, inputs, lock_protocol, lora, migrate, prompts as P, queue_lock, select, sft_data, sft_eval
from . import train as T

STAGE_KEYS = A.STAGE_KEYS + ("cand_manifest", "cand_manifest_sha256")


class GeoDataset:
    def __init__(self, tok, proc, items, gt, prompt, order, dig_ids, mode, cands):
        self.tok, self.proc, self.items, self.gt, self.prompt, self.order, self.dig, self.mode, self.cands = tok, proc, items, gt, prompt, order, dig_ids, mode, cands

    def __len__(self):
        return len(self.order)

    def __getitem__(self, k):
        import torch
        it = self.items[self.order[k]]
        image, _, _ = inputs.load_verified(it)
        boxes = sft_data.target_boxes([b["yxyx_norm"] for b in self.gt[it["id"]]["boxes"]])
        tgt = sft_data.target_text([b["yxyx_norm"] for b in self.gt[it["id"]]["boxes"]])
        ex = sft_data.build_example(self.proc, image, self.prompt, tgt)
        fid, npf = ex["input_ids"].tolist(), ex["n_prefix"]
        tokw = torch.ones(len(fid), dtype=torch.float32)
        branches = []
        if boxes:
            ent = self.cands.get(it["id"]) if self.mode != "C" else None
            if self.mode != "C":
                if ent is None or [e["gt"] for e in ent] != boxes:
                    raise GL.GeoError(f"{it['id']}: candidate manifest GT boxes != training target boxes")
                cl = [e["cands"] for e in ent]
            else:
                cl = [[{"giou": 0.5, "box": [0, 0, 1, 1]}] * GL.K_CAND for _ in boxes]  # C: q만 필요 (1,0,..), 후보 미사용
            bd = GL.build_branches(self.tok, tgt, self.dig, cl, self.mode)
            if list(fid[npf:npf + len(bd["gt_ids"])]) != bd["gt_ids"]:
                raise GL.GeoError("assistant tokens in chat sequence != standalone tokenization")
            tokw[npf:npf + len(bd["gt_ids"])] = torch.tensor(GL.gt_token_weights(len(bd["gt_ids"]), bd["gt_spans"], bd["q0"]), dtype=torch.float32)
            pre = fid[:npf]
            tt = ex["token_type_ids"][:npf] if "token_type_ids" in ex else None
            for br in bd["branches"]:
                ids = torch.tensor(pre + br["ids"], dtype=torch.long)
                lab = torch.full_like(ids, -100)
                w = torch.zeros(len(ids), dtype=torch.float32)
                lab[npf + br["span"][0]:npf + br["span"][1] + 1] = ids[npf + br["span"][0]:npf + br["span"][1] + 1]
                w[npf + br["span"][0]:npf + br["span"][1] + 1] = br["w_per_token"]
                d = {"input_ids": ids, "labels": lab, "tokw": w, "box": br["box"], "m": br["m"], "cand": br["cand"], "span": br["span"], "w_per_token": br["w_per_token"],
                     "giou": br["giou"], "n_b": br["n_b"], "n_bm": br["n_bm"]}
                if tt is not None:
                    d["token_type_ids"] = torch.cat([tt, torch.zeros(len(ids) - npf, dtype=torch.long)])
                branches.append(d)
        ex["tokw"] = tokw
        ex["branches"] = branches
        ex["sample_pos"] = int(k)
        return ex


def collate(ex, pad_id):
    import torch
    br = [e["branches"] for e in ex]
    tw = [e["tokw"] for e in ex]
    out = sft_data.collate([{k: v for k, v in e.items() if k not in ("tokw", "branches")} for e in ex], pad_id)
    t = torch.zeros((len(ex), out["input_ids"].shape[1]), dtype=torch.float32)
    for i, w in enumerate(tw):
        t[i, :len(w)] = w
    out["tokw"] = t
    out["branches"] = br
    return out


def branch_batch(torch, per_ex_branches, pixel_values, pad_id, sel):
    """sel: [(example index, branch)] -> 모델 입력 dict (같은 영상의 pixel_values를 branch마다 복제)."""
    L = max(len(b["input_ids"]) for _, b in sel)
    B = len(sel)
    ids = torch.full((B, L), pad_id, dtype=torch.long)
    att = torch.zeros((B, L), dtype=torch.long)
    lab = torch.full((B, L), -100, dtype=torch.long)
    tw = torch.zeros((B, L), dtype=torch.float32)
    has_tt = "token_type_ids" in sel[0][1]
    tt = torch.zeros((B, L), dtype=torch.long) if has_tt else None
    for r, (ei, b) in enumerate(sel):
        n = len(b["input_ids"])
        ids[r, :n], att[r, :n], lab[r, :n], tw[r, :n] = b["input_ids"], 1, b["labels"], b["tokw"]
        if has_tt:
            tt[r, :n] = b["token_type_ids"]
    out = {"input_ids": ids, "attention_mask": att, "labels": lab, "tokw": tw, "pixel_values": torch.cat([pixel_values[ei:ei + 1] for ei, _ in sel], 0)}
    if has_tt:
        out["token_type_ids"] = tt
    return out


def geo_forward(torch, model, batch, softcap_unused=None):
    """batch(cuda): labels/tokw 포함. returns (weighted_ce_sum(grad), unweighted_ce_sum(detached), n_tok). 전체 vocabulary softmax + 모델 softcap."""
    b = dict(batch)
    tw, labels = b.pop("tokw"), b.pop("labels")
    b["pixel_values"] = b["pixel_values"].to(torch.bfloat16)
    out = model.model(**b, use_cache=False)
    h = out.last_hidden_state[:, :-1]
    lab = labels[:, 1:]
    sel = lab != -100
    logits = model.lm_head(h[sel]).float()
    sc = getattr(model.config.get_text_config(), "final_logit_softcapping", None)
    if sc:
        logits = torch.tanh(logits / sc) * sc
    y, w = lab[sel], tw[:, 1:][sel]
    if bool((w <= 0).any()):
        raise RuntimeError("label position with non-positive weight")
    ce = torch.logsumexp(logits, dim=-1) - logits.gather(1, y[:, None]).squeeze(1)
    return (ce * w).sum(), ce.detach().sum(), int(sel.sum())


def load_stage(path, protocol):
    st = json.load(open(path))
    miss = [k for k in STAGE_KEYS if k not in st]
    if miss:
        sys.exit(f"stage config missing keys {miss}")
    locked = json.load(open(protocol))["locked"]["files"]
    for k in (path, st["parent_adapter"], st["train_ids"], st["val_ids"], st["cand_manifest"]):
        if os.path.relpath(k) not in locked:
            sys.exit(f"{k} is not a locked protocol file")
    if hashlib.sha256(open(st["parent_adapter"], "rb").read()).hexdigest() != st["parent_adapter_sha256"]:
        sys.exit("parent adapter file sha256 != stage config")
    if hashlib.sha256(open(st["cand_manifest"], "rb").read()).hexdigest() != st["cand_manifest_sha256"]:
        sys.exit("candidate manifest sha256 != stage config")
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--stage-config", required=True)
    ap.add_argument("--loss", required=True, choices=["C", "U", "G"])
    ap.add_argument("--lr", type=float, required=True)
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--microbatch", type=int, default=2)
    ap.add_argument("--branch-microbatch", type=int, default=4)
    ap.add_argument("--ckpt-every", type=int, default=50)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--max-steps", type=int, default=None, help="test: 이 optimizer step까지만 (checkpoint 저장 후 종료)")
    ap.add_argument("--stop-after-step", type=int, default=None, help="test: 정기 checkpoint step 직후 비정상 종료 (재개 검사)")
    ap.add_argument("--deterministic", action="store_true", help="검사 전용: 결정적 kernel (선택·본실험 금지)")
    ap.add_argument("--stop-in-validation", type=int, default=None)
    a = ap.parse_args()
    if a.deterministic:
        os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    pdig = lock_protocol.verify(a.protocol)
    st = load_stage(a.stage_config, a.protocol)
    if a.lr not in st["allowed_lrs"]:
        sys.exit(f"lr {a.lr} not in stage allowed_lrs {st['allowed_lrs']}")
    os.makedirs(a.run_dir, exist_ok=True)
    lk, own, reclaimed = queue_lock.try_lock(os.path.join(os.path.realpath(a.run_dir), "train.lock"), queue_lock.my_info(role="adapt_geo"))
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
    cands = json.load(open(st["cand_manifest"]))
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
    cfg = dict(T.CFG, lr=a.lr, seed=seed, microbatch=a.microbatch, branch_microbatch=a.branch_microbatch, eff_batch=eb, n_train=n_tr, n_val=len(val_items), stage=st,
               stage_config_sha256=migrate.file_sha(a.stage_config), loss_mode=a.loss, total_updates=total, steps_per_epoch=spe,
               geo={"gamma": GL.GAMMA, "giou_min": GL.GIOU_MIN, "k": GL.K_CAND, "seed_tag": GL.SEED_TAG, "cand_manifest_sha256": st["cand_manifest_sha256"],
                    "norm": "L=[CE_outside_spans + sum_b n_b sum_m q_bm ell_bm]/N", "q": {"C": "q0=1", "U": "q0=1/Z,q_m=(1-q0)/4", "G": "q=r/Z"}},
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

    mil = set(st.get("milestone_epochs") or range(1, st["epochs"] + 1))
    if val_items:
        for e in sorted(mil):
            if e > epoch0:
                continue
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
        ds = GeoDataset(tok, proc, train_items, gt, P.CONCISE, order, dig_ids, a.loss, cands)
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
            lr = A.lr_at(step, total, a.lr, st["warmup_frac"])
            for g in opt.param_groups:
                g["lr"] = lr
            rng_before, opt_step_before = T.rng_digest(torch), T.opt_step_count(opt)
            if not model.training:
                raise RuntimeError("model not in train mode at optimizer step")
            acc = {"gt_w": 0.0, "gt_ce": 0.0, "br_w": 0.0, "br_ce": 0.0}
            ntok_seen = n_branch = n_branch_tok = 0
            seen_pos, tok_h, br_h = [], hashlib.sha256(), hashlib.sha256()
            for _ in range(math.ceil(len(grp) / a.microbatch)):
                b = next(it)
                seen_pos += b.pop("sample_pos").tolist()
                per_ex = b.pop("branches")
                tok_h.update(T.batch_token_digest({k: v for k, v in b.items() if k != "tokw"}).digest())
                tok_h.update(b["tokw"].contiguous().numpy().tobytes())
                flat = [(ei, br) for ei, lst in enumerate(per_ex) for br in lst]
                for _, br in flat:
                    br_h.update(json.dumps([br["box"], br["m"], br["cand"], br["span"], round(br["w_per_token"], 12)]).encode())
                    br_h.update(br["input_ids"].numpy().tobytes())
                pv_cpu = b["pixel_values"]
                bg = {k: v.cuda() for k, v in b.items()}
                w_sum, ce_sum, nt = geo_forward(torch, model, bg, softcap)
                (w_sum / tot_tok).backward()
                acc["gt_w"] += float(w_sum.detach()) / tot_tok
                acc["gt_ce"] += float(ce_sum) / tot_tok
                ntok_seen += nt
                del bg, w_sum, ce_sum
                for c0 in range(0, len(flat), a.branch_microbatch):
                    chunk = flat[c0:c0 + a.branch_microbatch]
                    bb = {k: v.cuda() for k, v in branch_batch(torch, per_ex, pv_cpu, tok.pad_token_id, chunk).items()}
                    w_sum, ce_sum, nt = geo_forward(torch, model, bb, softcap)
                    (w_sum / tot_tok).backward()
                    acc["br_w"] += float(w_sum.detach()) / tot_tok
                    acc["br_ce"] += float(ce_sum) / tot_tok
                    n_branch += len(chunk)
                    n_branch_tok += nt
                    del bb, w_sum, ce_sum
            if ntok_seen != tot_tok:
                raise RuntimeError(f"label token count mismatch {ntok_seen} != {tot_tok}")
            planned = [train_items[j]["id"] for j in grp]
            actual = [train_items[order[p]]["id"] for p in seen_pos]
            if actual != planned or seen_pos != list(range(s * eb, s * eb + len(grp))):
                raise RuntimeError(f"step {step + 1}: DataLoader batch != planned batch")
            gn = float(torch.nn.utils.clip_grad_norm_(params, T.CFG["grad_clip"]))
            loss_total = acc["gt_w"] + acc["br_w"]
            if not math.isfinite(gn) or not math.isfinite(loss_total):
                raise RuntimeError(f"non-finite loss/grad at step {step}: {loss_total} {gn}")
            opt.step()
            opt.zero_grad(set_to_none=True)
            step += 1
            logf.write(json.dumps({"step": step, "epoch": epoch + 1, "pos": s + 1, "loss": loss_total, "gt_weighted_ce": acc["gt_w"], "gt_unweighted_ce": acc["gt_ce"],
                                   "branch_weighted_ce": acc["br_w"], "branch_unweighted_ce": acc["br_ce"], "n_branches": n_branch, "n_branch_label_tokens": n_branch_tok,
                                   "n_label_tokens": tot_tok, "grad_norm": gn, "lr": lr, "n_examples": len(grp), "elapsed_s": time.time() - t0,
                                   "peak_mem_gb": torch.cuda.max_memory_allocated() / 2 ** 30, "batch_ids": actual, "batch_token_sha": tok_h.hexdigest()[:24],
                                   "branch_sha": br_h.hexdigest()[:24], "rng_before": rng_before, "opt_step_before": opt_step_before, "train_mode": True}) + "\n")
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
        do_val = bool(val_items) and (epoch + 1) in mil
        save_ckpt(epoch + 1, 0, val_pending=epoch + 1 if do_val else None)
        if do_val:
            validate_epoch(epoch + 1, from_file=False, stop_after=a.stop_in_validation)
        pos0 = 0
    print("training complete", flush=True)
    T.atomic_json({"status": "complete", "steps": step, "loss_mode": a.loss, "train_digest": tdig, "wall_s": time.time() - t0}, os.path.join(a.run_dir, "done.json"))


if __name__ == "__main__":
    main()
