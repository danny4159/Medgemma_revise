"""iter_048 E/J 학습기 (pg40_train 기반; pg40_train.py는 iter_040 산출물 검증용으로 수정하지 않고 보존).

E: C(epoch03)에서 추가 독립 CE. 환자당 I-short 두 sequence (qA, qB).    mode=ce
J: 같은 C에서 직접 공동 CE.  환자당 J-short 한 sequence (두 소견, AB/BA는 환자 hash + epoch parity로 균형).    mode=joint

pg40 대비 변경: (1) mode = ce | joint (contrast/cross 경로 제거, 문장 대조 loss 없음), (2) 학습기 내부 validation 제거 -- D24 선택 평가는 외부 stage가 담당하므로
validation 이후 RNG 복원 문제가 없다, (3) 초기 adapter는 필수이며 digest가 C epoch03(419ae81f...)인지 강제한다, (4) train_config에 입력 manifest·source·precision·env를 묶고
재개 시 같은 config만 허용한다, (5) 결정적 AB/BA 배정 및 joint target 직렬화 함수를 export한다 (gate가 같은 함수를 검사한다).
재사용: rsna_diag.lora, sft_data(build_example/collate/target_boxes), generate, queue_lock, rsna_diag.train의 lr/atomic 저장/RNG/optimizer digest.
사용하지 않음: rsna_diag.train.main/run, 매 epoch 전체 validation.

학습 단위 = 환자 1명. effective batch = 8환자. CE는 logical batch 전체 assistant token 합(마지막 불완전 batch는 실제 token 수)으로 정규화한다.
RNG: 환자마다 (seed, step, patient) 결정적 seed로 dropout RNG를 설정 -> 재개 시 정확히 재현.

사용:
  python pg48_train.py make-protocol --out P
  CUDA_VISIBLE_DEVICES=<gpu> python pg48_train.py train --run-dir D --protocol P --mode ce|joint --init-adapter results/iter_040/train2/C_s17/epoch_03 --epochs 5 --mb 2
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
C_ADAPTER_DIGEST = "419ae81f5ef455d39742b158537373da6e26061b362d13205ab28b4a50905ba8"
CODE_FILES = ["pg48_train.py", "pg39_spec.py", "rsna_diag/lora.py", "rsna_diag/sft_data.py", "rsna_diag/generate.py", "rsna_diag/geometry.py",
              "rsna_diag/queue_lock.py", "rsna_diag/train.py", "rsna_diag/prompts.py"]
CFG = {"r": 16, "alpha": 32, "dropout": 0.05, "weight_decay": 0.01, "betas": [0.9, 0.999], "eps": 1e-8, "grad_clip": 1.0, "eff_batch_patients": 8,
       "lr": 1e-5, "schedule": "const", "precision": "bf16 model/LoRA params fp32-as-built, logits fp32 for CE",
       "prompt_E": "I-short (pg39_spec.prompt_I_short)", "prompt_J": "J-short (pg39_spec.prompt_J_short), AB/BA by hash+epoch parity"}
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


def joint_target_text(gtc, order):
    """order: ('qA','qB') 또는 ('qB','qA'). 요청 순서대로 두 ID의 전체 GT box를 연결하고 각 ID 내부 정렬은 target_boxes 규칙."""
    if sorted(order) != ["qA", "qB"]:
        raise ValueError(f"joint order must be a permutation of qA,qB: {order}")
    ent = []
    for pid in order:
        ent += [{"box_2d": b, "label": pid} for b in sft_data.target_boxes(gtc[pid])]
    return json.dumps(ent)


def joint_order(patient_id, epoch):
    """환자 hash + epoch parity로 AB/BA를 균형화한다 (epoch은 0부터)."""
    h = int(hashlib.sha256(patient_id.encode()).hexdigest()[:8], 16)
    return ("qA", "qB") if (h + epoch) % 2 == 0 else ("qB", "qA")


def load_rows(path, sets):
    return [r for r in (json.loads(l) for l in open(path)) if r.get("subset") in sets]


def check_image(row):
    a = np.asarray(Image.open(row["image_meta"]["path"]))
    if hashlib.sha256(a.tobytes()).hexdigest() != row["image_meta"]["u8_pixel_sha256"]:
        raise TrainError(f"image pixel hash mismatch {row['ImageID']}")


def patient_texts(row, mode, epoch):
    """mode=ce: list of (prompt, target) 2개(qA,qB). mode=joint: 1개 (J-short prompt, joint target)."""
    gtc = row["gt_canvas_yxyx"]
    if mode == "ce":
        return [(S.prompt_I_short(row["sentences"][p], p), target_text(gtc[p], p)) for p in ("qA", "qB")]
    order = joint_order(row["PatientID"], epoch)
    return [(S.prompt_J_short([(i, row["sentences"][i]) for i in order]), joint_target_text(gtc, order))]


class PatientDataset:
    def __init__(self, proc, rows, order, mode, epoch):
        self.proc, self.rows, self.order, self.mode, self.epoch = proc, rows, order, mode, epoch

    def __len__(self):
        return len(self.order)

    def __getitem__(self, k):
        row = self.rows[self.order[k]]
        check_image(row)
        image, _, _ = generate.load_image(row["image_meta"]["path"])
        exs = [sft_data.build_example(self.proc, image, *pt) for pt in patient_texts(row, self.mode, self.epoch)]
        return {"pos_in_epoch": int(k), "row_idx": int(self.order[k]), "exs": exs}


# ---------------- loss ----------------
def seq_losses(torch, model, batch, softcap):
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
    ces, ns, toks = [], [], 0
    for i in range(0, len(exs), mb):
        b = sft_data.collate(exs[i:i + mb], pad_id)
        b = {k: v.cuda() for k, v in b.items()}
        toks += int(b["attention_mask"].sum())
        c, n = seq_losses(torch, model, b, softcap)
        ces.append(c)
        ns.append(n)
    return torch.cat(ces), torch.cat(ns), toks


def derive_seed(seed, step, k):
    return int(hashlib.sha256(f"{seed}|{step}|{k}".encode()).hexdigest()[:8], 16)


def patient_step(torch, model, item, pad_id, softcap, tot_tok, mb, seed_int, backward=True):
    torch.manual_seed(seed_int)
    torch.cuda.manual_seed(seed_int)
    ce, n, toks = group_losses(torch, model, item["exs"], pad_id, softcap, mb)
    loss = ce.sum() / tot_tok
    if backward:
        loss.backward()
    return {"ce_sum": float(ce.detach().sum()), "ntok": int(n.sum()), "fwd_tokens": toks, "loss": float(loss.detach())}


def label_count(tok, target):
    return len(tok(target + "<end_of_turn>", add_special_tokens=False)["input_ids"])


def batch_tot_tok(tok, rows, grp, mode, epoch):
    return sum(label_count(tok, t) for j in grp for _, t in patient_texts(rows[j], mode, epoch))


# ---------------- protocol ----------------
def make_protocol(out, extra=None):
    if os.path.exists(out):
        raise TrainError(f"protocol exists: {out}")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    d = {"runner": "pg48_train_v1", "code": {f: sha_file(f) for f in CODE_FILES}, "manifest_train_sha256": sha_file(TRAIN_MANIFEST),
         "c_adapter_digest": C_ADAPTER_DIGEST, "cfg": CFG, "extra": extra or {}}
    tmp = out + f".{os.getpid()}.tmp"
    json.dump(d, open(tmp, "w"), indent=1)
    os.replace(tmp, out)
    return d


def verify_protocol(path):
    p = json.load(open(path))
    bad = [f for f, h in p["code"].items() if sha_file(f) != h]
    if bad:
        raise TrainError(f"code changed since protocol lock: {bad}")
    if sha_file(TRAIN_MANIFEST) != p["manifest_train_sha256"]:
        raise TrainError("train manifest changed since protocol lock")
    return hashlib.sha256(canon(p).encode()).hexdigest(), p


def run_dir_lock(run_dir):
    lk, own, rec = queue_lock.try_lock(os.path.join(os.path.realpath(run_dir), "train.lock"), queue_lock.my_info(role="pg48_train"))
    if lk is None:
        raise TrainError(f"run-dir owned by another live process: {own}")
    LOCK_FD[0] = lk.fd
    return lk, rec


def close_lock_fd(_wid):
    if LOCK_FD[0] is not None:
        try:
            os.close(LOCK_FD[0])
        except OSError:
            pass


def train(a):
    import torch
    pdig, proto = verify_protocol(a.protocol)
    os.makedirs(a.run_dir, exist_ok=True)
    lk, reclaimed = run_dir_lock(a.run_dir)
    try:
        run(a, torch, pdig, proto, reclaimed)
    finally:
        lk.release()


def run(a, torch, pdig, proto, reclaimed):
    rows = sorted(load_rows(TRAIN_MANIFEST, {"T305"}), key=lambda r: r["PatientID"])
    if a.max_patients:
        rows = rows[:a.max_patients]
    n_tr = len(rows)
    P_EB = CFG["eff_batch_patients"]
    spe = math.ceil(n_tr / P_EB)
    target_steps = a.total_updates if a.total_updates else a.epochs * spe
    if a.deterministic:
        os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
        T0.set_deterministic(torch)
    T0.seed_all(torch, a.seed)
    torch_, proc, model = generate.load_model()
    names = lora.apply_lora(model, CFG["r"], CFG["alpha"], CFG["dropout"], seed=a.seed)
    tok = proc.tokenizer
    softcap = getattr(model.config.get_text_config(), "final_logit_softcapping", None)
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.config.use_cache = False
    model.train()
    params = list(lora.lora_params(model).values())
    blob = torch.load(os.path.join(a.init_adapter, "adapter.pt"), map_location="cpu", weights_only=True)
    if lora.state_digest(blob["state"]) != blob["digest"] or blob["digest"] != C_ADAPTER_DIGEST:
        raise TrainError("init adapter digest != C epoch03 digest")
    lora.load_lora_state(model, blob["state"])
    init_dig = blob["digest"]
    if lora.state_digest(lora.lora_state_dict(model)) != init_dig:
        raise TrainError("loaded init adapter state digest mismatch")
    env = generate.env_info(torch, proc, model)
    cfg = dict(CFG, mode=a.mode, seed=a.seed, microbatch_sequences=a.mb, n_train=n_tr, init_adapter_digest=init_dig,
               init_adapter_file_sha256=sha_file(os.path.join(a.init_adapter, "adapter.pt")), protocol_digest=pdig,
               model_revision=generate.MODEL_REVISION, n_lora_targets=len(names), n_trainable=sum(p.numel() for p in params),
               deterministic=bool(a.deterministic), source_sha256={f: sha_file(f) for f in CODE_FILES},
               train_manifest_sha256=sha_file(TRAIN_MANIFEST), torch=torch.__version__, chat_template_sha256=env.get("chat_template_sha256"),
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
        b = {"lora": lora.lora_state_dict(model), "optimizer": opt.state_dict(), "step": step, "epoch": epoch, "pos_in_epoch": pos,
             "rng": T0.rng_state(torch), "train_digest": tdig, "protocol_digest": pdig, "digests": dg}
        T0.atomic_save(torch, b, ck)
        if also and not os.path.exists(also):
            os.makedirs(os.path.dirname(also), exist_ok=True)
            T0.atomic_save(torch, b, also)
        log_event(event="checkpoint", step=step, epoch=epoch, pos=pos, digests=dg)
        return dg

    if os.path.exists(ck):
        b = torch.load(ck, map_location="cpu", weights_only=False)
        if b["train_digest"] != tdig or b["protocol_digest"] != pdig:
            raise TrainError("checkpoint provenance mismatch")
        lora.load_lora_state(model, b["lora"])
        opt.load_state_dict(b["optimizer"])
        step, epoch0, pos0 = b["step"], b["epoch"], b["pos_in_epoch"]
        T0.set_rng_state(torch, b["rng"])
        restored = T0.live_digests(torch, model, opt)
        if restored != b["digests"]:
            raise TrainError(f"restored state != saved checkpoint state {b['digests']} {restored}")
        log_event(event="resume", step=step, epoch=epoch0, pos=pos0, stale_lock_reclaimed=bool(reclaimed), restored_equals_saved=True)
        print(f"resumed step={step} epoch={epoch0} pos={pos0}", flush=True)
    else:
        log_event(event="start", init_adapter_digest=init_dig, train_digest=tdig, n_train=n_tr, steps_per_epoch=spe, target_steps=target_steps)
    base_h = lora.base_digest(model) if a.check_base else None
    epochs_total = math.ceil(target_steps / spe)
    t_wall0 = time.time()
    done = step >= target_steps
    for epoch in range(epoch0, epochs_total):
        if done:
            break
        order = np.random.default_rng(a.seed * 1000 + epoch).permutation(n_tr)
        start_pos = pos0 if epoch == epoch0 else 0
        ds = PatientDataset(proc, rows, order, a.mode, epoch)
        idx = list(range(start_pos * P_EB, n_tr))
        dl_gen = torch.Generator()
        dl_gen.manual_seed(a.seed * 1000 + epoch)
        dl = torch.utils.data.DataLoader(torch.utils.data.Subset(ds, idx), batch_size=None, shuffle=False, num_workers=a.workers,
                                         prefetch_factor=2 if a.workers else None, worker_init_fn=close_lock_fd, generator=dl_gen)
        it = iter(dl)
        model.train()
        for s in range(start_pos, spe):
            grp = order[s * P_EB:(s + 1) * P_EB]
            tot_tok = batch_tot_tok(tok, rows, grp, a.mode, epoch)
            for g in opt.param_groups:
                g["lr"] = a.lr
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
                infos.append(patient_step(torch, model, item, tok.pad_token_id, softcap, tot_tok, a.mb, derive_seed(a.seed, step, k)))
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
            log_event(event="step", step=step, epoch=epoch + 1, pos=s + 1, loss=loss, ce=sum(i["ce_sum"] for i in infos) / tot_tok, grad_norm=gn, lr=a.lr,
                      n_patients=len(grp), tot_label_tokens=tot_tok, step_time_s=t_step, data_wait_s=t_wait, fwd_tokens=sum(i["fwd_tokens"] for i in infos),
                      peak_mem_gb=torch.cuda.max_memory_allocated() / 2 ** 30, peak_reserved_gb=torch.cuda.max_memory_reserved() / 2 ** 30,
                      batch_rows=[int(j) for j in grp], rng_before=rng_before, opt_step_before=opt_step_before, elapsed_s=time.time() - t_wall0,
                      joint_orders=[("AB" if joint_order(rows[j]["PatientID"], epoch)[0] == "qA" else "BA") for j in grp] if a.mode == "joint" else None)
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
        if step >= target_steps and (step % spe) != 0:
            ed = os.path.join(a.run_dir, f"step_{step:04d}")
            T0.save_adapter(torch, model, os.path.join(ed, "adapter.pt"), {"step": step, "train_digest": tdig})
            save_ckpt(epoch, (step - epoch * spe) % spe or spe, also=os.path.join(ed, "ckpt.pt"))
        else:
            e = step // spe if step % spe == 0 else epoch + 1
            ed = os.path.join(a.run_dir, f"epoch_{e:02d}")
            T0.save_adapter(torch, model, os.path.join(ed, "adapter.pt"), {"epoch": e, "step": step, "train_digest": tdig})
            save_ckpt(e, 0, also=os.path.join(ed, "ckpt.pt"))
            print(f"epoch {e} saved step={step}", flush=True)
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
    t.add_argument("--mode", choices=["ce", "joint"], required=True)
    t.add_argument("--lr", type=float, default=CFG["lr"])
    t.add_argument("--seed", type=int, default=17)
    t.add_argument("--epochs", type=int, default=None)
    t.add_argument("--total-updates", type=int, default=None)
    t.add_argument("--mb", type=int, default=2, help="한 forward에 묶는 sequence 수 (E: 1 또는 2, J는 환자당 1 sequence)")
    t.add_argument("--init-adapter", required=True)
    t.add_argument("--ckpt-every", type=int, default=20)
    t.add_argument("--workers", type=int, default=3)
    t.add_argument("--max-patients", type=int, default=None, help="동작 확인 전용: 앞 N명만 (본실험 금지)")
    t.add_argument("--deterministic", action="store_true", help="검사 전용")
    t.add_argument("--check-base", action="store_true")
    t.add_argument("--stop-after-step", type=int, default=None, help="검사 전용")
    a = ap.parse_args()
    if a.cmd == "make-protocol":
        make_protocol(a.out)
        return
    if (a.epochs is None) == (a.total_updates is None):
        sys.exit("exactly one of --epochs / --total-updates")
    if a.lr != CFG["lr"]:
        sys.exit("lr is fixed by the plan (1e-5 const)")
    if a.max_patients or a.deterministic or a.stop_after_step:
        print("WARNING: test-only flags in use", flush=True)
    train(a)


if __name__ == "__main__":
    main()
