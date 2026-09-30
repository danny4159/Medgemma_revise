"""iter_040 문장별 grounding LoRA 학습기 (직접 SFT B / CE 대조 C / CE+문장 대조 M).

재사용: rsna_diag.lora (LoRA·state digest), rsna_diag.sft_data (build_example의 prefix 대조·assistant-only labels·target_boxes),
        rsna_diag.generate (모델·영상 로드), rsna_diag.queue_lock (단일 writer lock), rsna_diag.train의 lr_at·atomic 저장·RNG/optimizer digest.
사용하지 않음: rsna_diag.train.main/run (RSNA manifest·매 epoch 전체 validation·select·migration), GIoU/truncated 경로.

학습 단위 = 환자 1명(두 문장 = positive 2개). effective batch = 8환자(=16 positive 문장). 마지막 불완전 batch는 실제 환자 수/토큰 수로 정규화.
loss_M = CE(token 평균 over effective batch) + lam * mean_patient(L_pair), L_pair는 대조 적격 환자만 (모든 GT cross-IoU < 0.1).
ell(q, Y) = 영상+문장 q prompt에서 Y(JSON+<end_of_turn>) assistant 토큰 평균 log-likelihood. Y를 평가하는 두 prompt 모두 Y의 ID를 지시한다.
RNG: 환자마다 (seed, step, patient) 결정적 seed로 dropout RNG를 설정 -> M/C의 positive forward가 동일하고 재개 시 정확히 재현.

사용:
  python pg40_train.py make-protocol --out P
  CUDA_VISIBLE_DEVICES=<gpu> python pg40_train.py train --run-dir D --protocol P --mode ce|ce_contrast --lr 2e-4 --schedule cosine8|const --epochs 5 ...
"""
import argparse
import hashlib
import json
import math
import os
import sys
import time

import numpy as np
from PIL import Image

import pg39_spec as S
from rsna_diag import generate, lora, queue_lock, sft_data
from rsna_diag import train as T0

TRAIN_MANIFEST = "results/iter_040/data/manifest_train_private.jsonl"
EVAL_MANIFEST = "results/iter_040/data/manifest_eval_private.jsonl"
CODE_FILES = ["pg40_train.py", "pg39_spec.py", "rsna_diag/lora.py", "rsna_diag/sft_data.py", "rsna_diag/generate.py", "rsna_diag/geometry.py",
              "rsna_diag/queue_lock.py", "rsna_diag/train.py", "rsna_diag/prompts.py"]
CFG = {"r": 16, "alpha": 32, "dropout": 0.05, "weight_decay": 0.01, "betas": [0.9, 0.999], "eps": 1e-8, "grad_clip": 1.0,
       "warmup_frac": 0.05, "eff_batch_patients": 8, "phase1_epochs": 5, "ext_floor_frac": 0.1, "prompt": "I-short (pg39_spec.prompt_I_short)",
       "margin": 0.1, "cross_iou_max": 0.1}
LOCK_FD = [None]


class TrainError(RuntimeError):
    pass


def sha_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def canon(o):
    return json.dumps(o, sort_keys=True, ensure_ascii=False, default=str)


# ---------------- data ----------------
def target_text(boxes_yxyx, label):
    return json.dumps([{"box_2d": b, "label": label} for b in sft_data.target_boxes(boxes_yxyx)])


def load_rows(path, sets):
    return [r for r in (json.loads(l) for l in open(path)) if r.get("eval_set", r.get("set")) in sets or r.get("subset") in sets]


def check_image(row):
    """PNG를 읽어 저장된 8-bit pixel hash와 대조한다 (불일치는 예외)."""
    a = np.asarray(Image.open(row["image_meta"]["path"]))
    if hashlib.sha256(a.tobytes()).hexdigest() != row["image_meta"]["u8_pixel_sha256"]:
        raise TrainError(f"image pixel hash mismatch {row['ImageID']}")


def canvas_gt(row):
    """train manifest는 저장된 canvas GT, eval manifest(iter_039 행)는 원본 normalized xyxy에서 같은 함수로 변환한다."""
    if "gt_canvas_yxyx" in row:
        return row["gt_canvas_yxyx"]
    m = row["image_meta"]
    return {k: S.gt_to_canvas(row["gt_boxes_xyxy_norm"][k], m["h"], m["w"]) for k in ("qA", "qB")}


def patient_texts(row, cross):
    """returns dict: pos[pid]=(prompt,target), cross[pid]=(prompt,target)  (cross[pid]: 다른 문장 prompt + pid의 target/ID)."""
    other = {"qA": "qB", "qB": "qA"}
    gtc = canvas_gt(row)
    tg = {p: target_text(gtc[p], p) for p in ("qA", "qB")}
    pos = {p: (S.prompt_I_short(row["sentences"][p], p), tg[p]) for p in ("qA", "qB")}
    cr = {p: (S.prompt_I_short(row["sentences"][other[p]], p), tg[p]) for p in ("qA", "qB")} if cross else None
    return {"pos": pos, "cross": cr, "targets": tg}


class PatientDataset:
    def __init__(self, proc, rows, order, need_cross):
        self.proc, self.rows, self.order, self.need_cross = proc, rows, order, need_cross

    def __len__(self):
        return len(self.order)

    def __getitem__(self, k):
        row = self.rows[self.order[k]]
        check_image(row)
        image, _, _ = generate.load_image(row["image_meta"]["path"])
        cross = self.need_cross and row["contrast_eligible"]
        tx = patient_texts(row, cross)
        out = {"pos_in_epoch": int(k), "row_idx": int(self.order[k]),
               "pos": {p: sft_data.build_example(self.proc, image, *tx["pos"][p]) for p in ("qA", "qB")}, "cross": None}
        if cross:
            out["cross"] = {p: sft_data.build_example(self.proc, image, *tx["cross"][p]) for p in ("qA", "qB")}
        return out


# ---------------- loss ----------------
def seq_losses(torch, model, batch, softcap):
    """batch(cuda) -> (CE 합 (B,), 학습 토큰 수 (B,)). lm_head는 label 예측 위치에만 적용 (rsna_diag.train.assistant_loss_sum과 같은 수식)."""
    inp = {k: v for k, v in batch.items() if k != "labels"}
    inp["pixel_values"] = inp["pixel_values"].to(torch.bfloat16)
    out = model.model(**inp, use_cache=False)
    h = out.last_hidden_state[:, :-1]
    lab = batch["labels"][:, 1:]
    sel = lab != -100
    logits = model.lm_head(h[sel]).float()
    if softcap:
        logits = torch.tanh(logits / softcap) * softcap
    tok = torch.nn.functional.cross_entropy(logits, lab[sel], reduction="none")
    rows = sel.nonzero()[:, 0]
    ce = torch.zeros(lab.shape[0], device=tok.device, dtype=tok.dtype).index_add(0, rows, tok)
    return ce, sel.sum(1)


def group_losses(torch, model, exs, pad_id, softcap, mb):
    """exs: build_example 결과 list. mb=1이면 각 sequence를 따로, mb>=2이면 함께 forward. returns (ce (n,), ntok (n,), fwd_tokens)."""
    ces, ns, toks = [], [], 0
    for i in range(0, len(exs), mb):
        chunk = exs[i:i + mb]
        b = sft_data.collate(chunk, pad_id)
        b = {k: v.cuda() for k, v in b.items()}
        toks += int(b["attention_mask"].sum())
        c, n = seq_losses(torch, model, b, softcap)
        ces.append(c)
        ns.append(n)
    return torch.cat(ces), torch.cat(ns), toks


def derive_seed(seed, step, k):
    return int(hashlib.sha256(f"{seed}|{step}|{k}".encode()).hexdigest()[:8], 16)


def patient_step(torch, model, item, pad_id, softcap, tot_tok, n_pat, lam, margin, mb, do_cross, seed_int, backward=True):
    """환자 1명의 positive CE (+ 대조 항)를 계산하고 backward한다. returns dict(로그용 스칼라)."""
    if backward is False:
        with torch.no_grad():
            return patient_step(torch, model, item, pad_id, softcap, tot_tok, n_pat, lam, margin, mb, do_cross, seed_int, backward=None)
    torch.manual_seed(seed_int)
    torch.cuda.manual_seed(seed_int)
    ce, n, t1 = group_losses(torch, model, [item["pos"]["qA"], item["pos"]["qB"]], pad_id, softcap, mb)
    ell_pos = -ce / n
    loss = ce.sum() / tot_tok
    out = {"ce_sum": float(ce.detach().sum()), "ntok": int(n.sum()), "fwd_tokens": t1, "pair": None, "margin": None}
    if do_cross:
        cce, cn, t2 = group_losses(torch, model, [item["cross"]["qA"], item["cross"]["qB"]], pad_id, softcap, mb)
        ell_cr = -cce / cn
        pair = 0.5 * (torch.relu(margin - ell_pos[0] + ell_cr[0]) + torch.relu(margin - ell_pos[1] + ell_cr[1]))
        loss = loss + lam * pair / n_pat
        out.update({"pair": float(pair.detach()), "margin": [float(ell_pos[0].detach() - ell_cr[0].detach()), float(ell_pos[1].detach() - ell_cr[1].detach())],
                    "ell_pos": [float(x.detach()) for x in ell_pos], "ell_cross": [float(x.detach()) for x in ell_cr]})
        out["fwd_tokens"] += t2
    if backward:
        loss.backward()
    out["loss"] = float(loss.detach())
    return out


def label_count(tok, target):
    return len(tok(target + "<end_of_turn>", add_special_tokens=False)["input_ids"])


def batch_tot_tok(tok, rows, grp):
    return sum(label_count(tok, t) for j in grp for t in patient_texts(rows[j], False)["targets"].values())


def val_ce(torch, model, proc, rows, softcap):
    """V48 등 검증 문장의 teacher-forced CE (positive prompt만, eval mode, no grad). returns (token 평균 CE, 토큰 수, 문장 수)."""
    model.eval()
    tot, n, ns = 0.0, 0, 0
    with torch.no_grad():
        for row in rows:
            check_image(row)
            image, _, _ = generate.load_image(row["image_meta"]["path"])
            tx = patient_texts(row, False)
            exs = [sft_data.build_example(proc, image, *tx["pos"][p]) for p in ("qA", "qB")]
            c, k, _ = group_losses(torch, model, exs, proc.tokenizer.pad_token_id, softcap, 1)
            tot += float(c.sum())
            n += int(k.sum())
            ns += 2
    model.train()
    return tot / n, n, ns


def lr_for(a, step, spe):
    if a.schedule == "cosine8":
        return T0.lr_at(step, spe, a.lr, total_epochs=8)
    if a.schedule == "const":
        return a.lr
    raise TrainError(a.schedule)


# ---------------- protocol ----------------
def make_protocol(out, extra=None):
    if os.path.exists(out):
        raise TrainError(f"protocol exists: {out}")
    d = {"runner": "pg40_train_v1", "code": {f: sha_file(f) for f in CODE_FILES}, "manifest_train_sha256": sha_file(TRAIN_MANIFEST),
         "manifest_eval_sha256": sha_file(EVAL_MANIFEST), "cfg": CFG, "extra": extra or {}}
    tmp = out + f".{os.getpid()}.tmp"
    json.dump(d, open(tmp, "w"), indent=1)
    os.replace(tmp, out)
    return d


def verify_protocol(path):
    p = json.load(open(path))
    bad = [f for f, h in p["code"].items() if sha_file(f) != h]
    if bad:
        raise TrainError(f"code changed since protocol lock: {bad}")
    if sha_file(TRAIN_MANIFEST) != p["manifest_train_sha256"] or sha_file(EVAL_MANIFEST) != p["manifest_eval_sha256"]:
        raise TrainError("manifest changed since protocol lock")
    return hashlib.sha256(canon(p).encode()).hexdigest(), p


def run_dir_lock(run_dir):
    lk, own, rec = queue_lock.try_lock(os.path.join(os.path.realpath(run_dir), "train.lock"), queue_lock.my_info(role="pg40_train"))
    if lk is None:
        raise TrainError(f"run-dir owned by another live process: {own}")
    LOCK_FD[0] = lk.fd
    return lk, rec


# ---------------- main train ----------------
def close_lock_fd(_wid):
    """DataLoader worker가 run lock fd 사본을 붙들지 않게 한다."""
    if LOCK_FD[0] is not None:
        try:
            os.close(LOCK_FD[0])
        except OSError:
            pass


def build_model(seed):
    torch, proc, model = generate.load_model()
    names = lora.apply_lora(model, CFG["r"], CFG["alpha"], CFG["dropout"], seed=seed)
    return torch, proc, model, names


def train(a):
    import torch
    pdig, proto = verify_protocol(a.protocol)
    os.makedirs(a.run_dir, exist_ok=True)
    lk, reclaimed = run_dir_lock(a.run_dir)
    try:
        run(a, torch, pdig, reclaimed)
    finally:
        lk.release()


def run(a, torch, pdig, reclaimed):
    rows = sorted(load_rows(TRAIN_MANIFEST, {"T305"}), key=lambda r: r["PatientID"])
    if a.max_patients:
        rows = rows[:a.max_patients]
    val_rows = [r for r in load_rows(EVAL_MANIFEST, {"V96"}) if r["is_V48"]]
    n_tr = len(rows)
    P_EB = CFG["eff_batch_patients"]
    spe = math.ceil(n_tr / P_EB)
    target_steps = a.total_updates if a.total_updates else a.epochs * spe
    if a.deterministic:
        os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
        T0.set_deterministic(torch)
    T0.seed_all(torch, a.seed)
    _, proc, model, names = build_model(a.seed)
    tok = proc.tokenizer
    softcap = getattr(model.config.get_text_config(), "final_logit_softcapping", None)
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.config.use_cache = False
    model.train()
    params = list(lora.lora_params(model).values())
    init_dig = None
    if a.init_adapter:
        blob = torch.load(os.path.join(a.init_adapter, "adapter.pt"), map_location="cpu", weights_only=True)
        if lora.state_digest(blob["state"]) != blob["digest"]:
            raise TrainError("init adapter digest mismatch")
        lora.load_lora_state(model, blob["state"])
        init_dig = blob["digest"]
    env = generate.env_info(torch, proc, model)
    do_contrast = a.mode == "ce_contrast"
    lam = a.lam if do_contrast else 0.0
    cfg = dict(CFG, mode=a.mode, lam=lam, lr=a.lr, schedule=a.schedule, seed=a.seed, microbatch_sequences=a.mb, n_train=n_tr,
               init_adapter_digest=init_dig, protocol_digest=pdig, model_revision=generate.MODEL_REVISION, n_lora_targets=len(names),
               n_trainable=sum(p.numel() for p in params), deterministic=bool(a.deterministic), force_cross=bool(a.force_cross),
               train_ids_digest=hashlib.sha256(canon([r["PatientID"] for r in rows]).encode()).hexdigest(),
               order="np.random.default_rng(seed*1000+epoch).permutation over PatientID-sorted rows")
    tdig = hashlib.sha256(canon(cfg).encode()).hexdigest()
    cfg_path = os.path.join(a.run_dir, "train_config.json")
    if os.path.exists(cfg_path):
        if json.load(open(cfg_path))["train_digest"] != tdig:
            raise TrainError("train config differs from existing run_dir (refusing to resume/overwrite)")
    else:
        json.dump({"train_digest": tdig, "config": cfg, "env": env, "init_adapter": a.init_adapter}, open(cfg_path, "w"), indent=1, default=str)
    opt = torch.optim.AdamW(params, lr=a.lr, betas=tuple(CFG["betas"]), eps=CFG["eps"], weight_decay=CFG["weight_decay"])
    logf = open(os.path.join(a.run_dir, "train_log.jsonl"), "a")
    step, epoch0, pos0 = 0, 0, 0
    ck = os.path.join(a.run_dir, "ckpt_latest.pt")

    def log_event(**kw):
        logf.write(json.dumps({"ts": time.time(), **kw}) + "\n")
        logf.flush()

    def save_ckpt(epoch, pos, also=None):
        dg = T0.live_digests(torch, model, opt)
        blob = {"lora": lora.lora_state_dict(model), "optimizer": opt.state_dict(), "step": step, "epoch": epoch, "pos_in_epoch": pos,
                "rng": T0.rng_state(torch), "train_digest": tdig, "protocol_digest": pdig, "digests": dg}
        T0.atomic_save(torch, blob, ck)
        if also and not os.path.exists(also):
            os.makedirs(os.path.dirname(also), exist_ok=True)
            T0.atomic_save(torch, blob, also)
        log_event(event="checkpoint", step=step, epoch=epoch, pos=pos, digests=dg)
        return dg

    if os.path.exists(ck):
        blob = torch.load(ck, map_location="cpu", weights_only=False)
        if blob["train_digest"] != tdig or blob["protocol_digest"] != pdig:
            raise TrainError("checkpoint provenance mismatch")
        lora.load_lora_state(model, blob["lora"])
        opt.load_state_dict(blob["optimizer"])
        step, epoch0, pos0 = blob["step"], blob["epoch"], blob["pos_in_epoch"]
        T0.set_rng_state(torch, blob["rng"])
        restored = T0.live_digests(torch, model, opt)
        if restored != blob["digests"]:
            raise TrainError(f"restored state != saved checkpoint state {blob['digests']} {restored}")
        log_event(event="resume", step=step, epoch=epoch0, pos=pos0, stale_lock_reclaimed=bool(reclaimed), restored_equals_saved=True)
        print(f"resumed step={step} epoch={epoch0} pos={pos0}", flush=True)
    base_h = lora.base_digest(model) if a.check_base else None
    epochs_total = math.ceil(target_steps / spe)
    valce_epochs = set(int(x) for x in a.valce_epochs.split(",") if x)
    t_wall0 = time.time()
    done = step >= target_steps
    for epoch in range(epoch0, epochs_total):
        if done:
            break
        order = np.random.default_rng(a.seed * 1000 + epoch).permutation(n_tr)
        start_pos = pos0 if epoch == epoch0 else 0
        ds = PatientDataset(proc, rows, order, do_contrast or a.force_cross)
        idx = list(range(start_pos * P_EB, n_tr))
        dl_gen = torch.Generator()
        dl_gen.manual_seed(a.seed * 1000 + epoch)
        dl = torch.utils.data.DataLoader(torch.utils.data.Subset(ds, idx), batch_size=None, shuffle=False, num_workers=a.workers,
                                         prefetch_factor=2 if a.workers else None, worker_init_fn=close_lock_fd, generator=dl_gen)
        it = iter(dl)
        model.train()
        for s in range(start_pos, spe):
            grp = order[s * P_EB:(s + 1) * P_EB]
            tot_tok = batch_tot_tok(tok, rows, grp)
            lr = lr_for(a, step, spe)
            for g in opt.param_groups:
                g["lr"] = lr
            rng_before, opt_step_before = T0.rng_digest(torch), T0.opt_step_count(opt)
            infos, seen = [], []
            t_wait = 0.0
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats()
            t0 = time.time()
            for k in range(len(grp)):
                tw = time.time()
                item = next(it)
                t_wait += time.time() - tw
                seen.append(item["row_idx"])
                do_cross = item["cross"] is not None
                infos.append(patient_step(torch, model, item, tok.pad_token_id, softcap, tot_tok, len(grp), lam, CFG["margin"], a.mb,
                                          do_cross, derive_seed(a.seed, step, k)))
            if seen != [int(j) for j in grp]:
                raise TrainError(f"step {step + 1}: DataLoader batch != planned batch")
            if sum(i["ntok"] for i in infos) != tot_tok:
                raise TrainError("label token count mismatch")
            gn = float(torch.nn.utils.clip_grad_norm_(params, CFG["grad_clip"]))
            loss = sum(i["loss"] for i in infos)
            if not math.isfinite(gn) or not math.isfinite(loss):
                raise TrainError(f"non-finite loss/grad at step {step}: {loss} {gn}")
            opt.step()
            opt.zero_grad(set_to_none=True)
            torch.cuda.synchronize()
            t_step = time.time() - t0
            step += 1
            pairs = [i["pair"] for i in infos if i["pair"] is not None]
            log_event(event="step", step=step, epoch=epoch + 1, pos=s + 1, loss=loss, ce=sum(i["ce_sum"] for i in infos) / tot_tok, grad_norm=gn, lr=lr,
                      n_patients=len(grp), n_eligible_cross=len(pairs), pair_mean_over_eligible=float(np.mean(pairs)) if pairs else None,
                      margin_mean=float(np.mean([m for i in infos if i["margin"] for m in i["margin"]])) if pairs else None,
                      step_time_s=t_step, data_wait_s=t_wait, fwd_tokens=sum(i["fwd_tokens"] for i in infos),
                      peak_mem_gb=torch.cuda.max_memory_allocated() / 2 ** 30, batch_rows=[int(j) for j in grp], rng_before=rng_before,
                      opt_step_before=opt_step_before, elapsed_s=time.time() - t_wall0)
            saved = False
            if a.ckpt_every and step % a.ckpt_every == 0 and (s + 1) < spe and step < target_steps:
                save_ckpt(epoch, s + 1)
                saved = True
            if a.stop_after_step is not None and step == a.stop_after_step:
                if not saved:
                    save_ckpt(epoch, s + 1)
                print("test stop after step checkpoint", flush=True)
                os._exit(5)
            if step >= target_steps:
                done = True
                break
        del dl, it
        if step >= target_steps and (step % spe) != 0:  # 중간 종료 지점의 endpoint
            ed = os.path.join(a.run_dir, f"step_{step:04d}")
            T0.save_adapter(torch, model, os.path.join(ed, "adapter.pt"), {"step": step, "train_digest": tdig})
            save_ckpt(epoch, (step - epoch * spe) % spe or spe, also=os.path.join(ed, "ckpt.pt"))
        else:
            e = step // spe if step % spe == 0 else epoch + 1
            ed = os.path.join(a.run_dir, f"epoch_{e:02d}")
            adig = T0.save_adapter(torch, model, os.path.join(ed, "adapter.pt"), {"epoch": e, "step": step, "train_digest": tdig})
            save_ckpt(e, 0, also=os.path.join(ed, "ckpt.pt"))
            if e in valce_epochs:
                vc, vn, vs = val_ce(torch, model, proc, val_rows, softcap)
                T0.atomic_json({"epoch": e, "step": step, "val_ce_V48": vc, "n_tokens": vn, "n_sentences": vs, "adapter_digest": adig},
                               os.path.join(ed, "valce.json"))
                log_event(event="valce", epoch=e, val_ce_V48=vc)
                print(f"epoch {e}: V48 CE {vc:.4f}", flush=True)
        pos0 = 0
    if a.check_base:
        if lora.base_digest(model) != base_h:
            raise TrainError("base weights changed during training")
        log_event(event="base_frozen_verified")
    print("training complete", flush=True)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make-protocol")
    m.add_argument("--out", required=True)
    t = sub.add_parser("train")
    t.add_argument("--run-dir", required=True)
    t.add_argument("--protocol", required=True)
    t.add_argument("--mode", choices=["ce", "ce_contrast"], required=True)
    t.add_argument("--lr", type=float, required=True)
    t.add_argument("--schedule", choices=["cosine8", "const"], required=True)
    t.add_argument("--seed", type=int, default=17)
    t.add_argument("--epochs", type=int, default=None)
    t.add_argument("--total-updates", type=int, default=None)
    t.add_argument("--lam", type=float, default=0.1)
    t.add_argument("--mb", type=int, default=1, help="한 forward에 묶는 sequence 수 (1 또는 2)")
    t.add_argument("--init-adapter", default=None)
    t.add_argument("--ckpt-every", type=int, default=20)
    t.add_argument("--workers", type=int, default=3)
    t.add_argument("--valce-epochs", default="")
    t.add_argument("--max-patients", type=int, default=None, help="동작 확인 전용: 앞 N명만 (본실험 금지)")
    t.add_argument("--force-cross", action="store_true", help="검사 전용: lam=0이어도 cross forward를 계산")
    t.add_argument("--deterministic", action="store_true", help="검사 전용")
    t.add_argument("--check-base", action="store_true")
    t.add_argument("--stop-after-step", type=int, default=None, help="검사 전용")
    a = ap.parse_args()
    if a.cmd == "make-protocol":
        make_protocol(a.out)
        return
    if (a.epochs is None) == (a.total_updates is None):
        sys.exit("exactly one of --epochs / --total-updates")
    if a.max_patients or a.force_cross or a.deterministic or a.stop_after_step:
        print("WARNING: test-only flags in use", flush=True)
    train(a)


if __name__ == "__main__":
    main()
