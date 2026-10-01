"""iter_046 MedGrounder-P 직접 적응 trainer (격리 venv 실행: python mg46_vrun.py mg46_train.py ...).

공식 코드(a0aad98d, results/iter_045/external/MedGrounder)의 build_medgrounder / SetCriterion.loss_groundability·loss_boxes /
build_transforms('train')를 그대로 호출한다. 공식 snapshot에는 학습 실행기가 없으므로 이 파일이 orchestration만 새로 만든다.
의도된 차이(plan.md): matcher의 GIoU 예외 zero-cost fallback 금지(StrictMatcher), microbatch 누적 시 batch 전체 분모로 재가중,
augmentation은 (seed, epoch, sample)에 연결해 재현, 원자적 checkpoint·단일 소유 lock·중간 step 재개.
GT 좌표: manifest 원본 정규화 xyxy -> 공식 augmentation(albumentations format) -> 공식 box_xyxy_to_cxcywh target.

CLI:
  train --traj NAME --out DIR --lr-cfg S|U --target-epoch N [--save-epochs 2,5] [--microbatch 4] [--supp] [--gpu-check]
"""
import argparse
import fcntl
import hashlib
import json
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

import mg45_mg as M  # 환경변수 설정 + 공식 repo sys.path 등록

HERE = os.path.dirname(os.path.abspath(__file__))
T305_MAN = "results/iter_040/data/manifest_train_private.jsonl"
MAN = "results/iter_043/data/manifest_private.json"
LR_CFG = {"S": {"base": 1e-5, "backbone": 1e-5, "text": 5e-5}, "U": {"base": 1e-5, "backbone": 1e-5, "text": 1e-5}}
HP = {"batch": 32, "horizon_epochs": 15, "weight_decay": 1e-4, "betas": [0.9, 0.999], "eps": 1e-8, "clip": 0.1, "warmup_frac": 0.01,
      "supp_start_mult": 0.5, "supp_epochs": 15, "imsize": 640, "seed": 17, "num_queries": 5,
      "coef": {"groundability": 1.0, "bbox": 5.0, "giou": 2.0}, "eos_coef": 0.1}
TARGETS = ("qA", "qB")


class TrainError(RuntimeError):
    pass


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def file_sha(p):
    return M.file_sha(p)


# ---------------- 데이터 ----------------
def load_t305():
    """610 (환자,문장) 항목. 정렬: PatientID, target. 이미지는 iter_040 PNG(uint8 L)."""
    rows = [json.loads(l) for l in open(T305_MAN) if l.strip()]
    items = []
    for r in sorted(rows, key=lambda r: r["PatientID"]):
        for t in TARGETS:
            items.append({"patient": r["PatientID"], "target": t, "sentence": r["sentences"][t], "image": r["image_meta"]["path"],
                          "u8_sha": r["image_meta"]["u8_pixel_sha256"], "boxes": r["gt_boxes_xyxy_norm"][t], "study": r["StudyID"],
                          "image_id": r["ImageID"], "labels": r["labels"][t], "stratum": r["stratum"]})
    return items


class TrainSet:
    """디코드 캐시를 갖는 학습 자료. 항목 접근은 (seed, epoch, idx)로 augmentation seed가 결정된다. 로딩·변환 오류는 raise (조용한 skip 금지)."""

    def __init__(self, items):
        from PIL import Image
        self.items = items
        self.cache = {}
        for it in items:
            if it["image"] in self.cache:
                continue
            im = Image.open(it["image"])
            if im.mode != "L":
                raise TrainError(f"unexpected image mode {im.mode}: {it['image']}")
            a = np.array(im)
            if sha_bytes(a.tobytes()) != it["u8_sha"]:
                raise TrainError(f"decoded pixel hash != manifest: {it['image']}")
            self.cache[it["image"]] = np.stack([a, a, a], axis=-1)  # PIL L->RGB와 동일(채널 복제)

    def __len__(self):
        return len(self.items)

    def get(self, idx, epoch, seed, augment=True):
        import torch
        from dataloaders.dataset import build_transforms
        from utils.box_ops import box_xyxy_to_cxcywh
        it = self.items[idx]
        tf = build_transforms("train" if augment else "val", HP["imsize"])
        if augment:
            tf.set_random_seed(int(np.random.SeedSequence([seed, epoch, idx]).generate_state(1)[0]))
        boxes = np.array(it["boxes"], dtype=np.float32).reshape(-1, 4)
        out = tf(image=self.cache[it["image"]], bboxes=boxes, bbox_labels=[1] * len(boxes))
        bt = torch.tensor(np.array(out["bboxes"], dtype=np.float32).reshape(-1, 4))
        cx = box_xyxy_to_cxcywh(bt) if len(bt) else torch.empty((0, 4), dtype=torch.float32)
        return {"image": out["image"], "boxes": cx, "n_orig": len(boxes), "phrase": it["sentence"], "idx": idx}


def epoch_order(n, seed, epoch):
    return np.random.default_rng([seed, epoch]).permutation(n).tolist()


def batches(order, bs):
    return [order[i:i + bs] for i in range(0, len(order), bs)]


# ---------------- strict matcher ----------------
def make_strict_matcher_cls():
    import torch
    from scipy.optimize import linear_sum_assignment
    from model.medgrounder_matcher import HungarianMatcher
    from utils.box_ops import box_cxcywh_to_xyxy, generalized_box_iou

    class StrictMatcher(HungarianMatcher):
        """공식 HungarianMatcher와 같은 cost(1/5/2)·linear_sum_assignment. 공식의 GIoU 예외 zero-cost fallback만 제거하고,
        비유한 값·비양수 크기·비유한 cost는 예외로 중단한다."""

        @torch.no_grad()
        def forward(self, outputs, targets):
            bs, nq = outputs["pred_groundability"].shape[:2]
            out_prob = outputs["pred_groundability"].flatten(0, 1).softmax(-1)
            out_bbox = outputs["pred_boxes"].flatten(0, 1)
            tgt_ids = torch.cat([v["labels"] for v in targets])
            tgt_bbox = torch.cat([v["boxes"] for v in targets])
            if not (torch.isfinite(out_prob).all() and torch.isfinite(out_bbox).all() and torch.isfinite(tgt_bbox).all()):
                raise TrainError("matcher: non-finite output/target")
            if (out_bbox[:, 2:] <= 0).any() or (tgt_bbox[:, 2:] <= 0).any():
                raise TrainError("matcher: non-positive width/height")
            cost_class = -out_prob[:, tgt_ids]
            cost_bbox = torch.cdist(out_bbox, tgt_bbox, p=1)
            cost_giou = -generalized_box_iou(box_cxcywh_to_xyxy(out_bbox), box_cxcywh_to_xyxy(tgt_bbox))
            C = self.cost_bbox * cost_bbox + self.cost_class * cost_class + self.cost_giou * cost_giou
            if not torch.isfinite(C).all():
                raise TrainError("matcher: non-finite cost")
            C = C.view(bs, nq, -1).cpu()
            sizes = [len(v["boxes"]) for v in targets]
            idx = [linear_sum_assignment(c[i]) for i, c in enumerate(C.split(sizes, -1))]
            return [(torch.as_tensor(i, dtype=torch.int64), torch.as_tensor(j, dtype=torch.int64)) for i, j in idx]
    return StrictMatcher


# ---------------- 모델/optimizer ----------------
def build_model(device, seed=HP["seed"], init_path=None):
    """공식 build_medgrounder + MG-P(pretrain_imagenome) strict load + StrictMatcher. returns (model, criterion, cfg)."""
    import torch
    from model.medgrounder import build_medgrounder
    cfg = M.build_cfg("P")
    torch.manual_seed(seed)
    model, crit, _ = build_medgrounder(cfg)
    path = init_path or M.WEIGHTS["P"]
    ck = torch.load(path, map_location="cpu", weights_only=True)
    sd = ck["model"] if "model" in ck else ck
    model.load_state_dict(sd, strict=True)
    m = crit.matcher
    crit.matcher = make_strict_matcher_cls()(cost_class=m.cost_class, cost_bbox=m.cost_bbox, cost_giou=m.cost_giou)
    return model.to(device), crit.to(device), cfg


def param_groups(model, lr_cfg):
    """backbone(requires_grad) / text_encoder / 나머지(transformer·heads·proj·query). 누락·중복 없음을 검사한다."""
    c = LR_CFG[lr_cfg]
    groups = {"backbone": [], "text_encoder": [], "base": []}
    for n, p in model.named_parameters():
        if not p.requires_grad:
            continue
        if n.startswith("backbone."):
            groups["backbone"].append((n, p))
        elif "text_encoder." in n:
            groups["text_encoder"].append((n, p))
        else:
            groups["base"].append((n, p))
    lrs = {"backbone": c["backbone"], "text_encoder": c["text"], "base": c["base"]}
    allp = [id(p) for g in groups.values() for _, p in g]
    trainable = [id(p) for p in model.parameters() if p.requires_grad]
    if len(allp) != len(set(allp)) or set(allp) != set(trainable):
        raise TrainError("param group duplicate/missing")
    pg = [{"params": [p for _, p in groups[k]], "lr": lrs[k], "base_lr": lrs[k], "name": k, "weight_decay": HP["weight_decay"]} for k in ("backbone", "text_encoder", "base")]
    info = {k: {"n_tensors": len(v), "n_params": int(sum(p.numel() for _, p in v)), "lr": lrs[k]} for k, v in groups.items()}
    info["frozen_n_params"] = int(sum(p.numel() for p in model.parameters() if not p.requires_grad))
    return pg, info


def make_optimizer(model, lr_cfg):
    import torch
    pg, info = param_groups(model, lr_cfg)
    opt = torch.optim.AdamW(pg, betas=tuple(HP["betas"]), eps=HP["eps"], weight_decay=HP["weight_decay"])
    return opt, info


def steps_per_epoch(n, bs=HP["batch"]):
    return math.ceil(n / bs)


def lr_mult(step, steps_main, supp):
    """step: 지금까지 완료한 optimizer step 수(0부터). main: HF linear_with_warmup(총 steps_main, warmup 1%). supp: step>=steps_main에서 0.5 -> 0 선형(warmup 없음)."""
    warm = max(1, int(round(HP["warmup_frac"] * steps_main)))
    if step < steps_main:
        return step / warm if step < warm else max(0.0, (steps_main - step) / (steps_main - warm))
    if not supp:
        raise TrainError("step beyond main horizon without --supp")
    n_s = steps_main  # 15 epoch 보완 = main horizon과 같은 step 수
    return HP["supp_start_mult"] * max(0.0, (steps_main + n_s - step) / n_s)


# ---------------- loss (microbatch 누적, 공식 loss 함수 + batch 전체 분모) ----------------
def targets_of(samples, device):
    import torch
    return [{"labels": torch.zeros((len(s["boxes"]),), dtype=torch.int64, device=device), "boxes": s["boxes"].to(device)} for s in samples]


def batch_denoms(counts, nq, eos):
    """전체 logical batch의 분모: num_boxes = max(sum n_gt,1) (공식 clamp), CE class-weight 합 W = n_matched*1 + (B*Q-n_matched)*eos, n_matched=sum min(Q,n_gt)."""
    n_gt = int(sum(counts))
    n_matched = int(sum(min(nq, c) for c in counts))
    return {"num_boxes": float(max(n_gt, 1)), "W": n_matched * 1.0 + (len(counts) * nq - n_matched) * eos, "n_matched": n_matched, "n_gt": n_gt}


def micro_loss(crit, out, targets, denom, w_total_den):
    """한 microbatch의 (가중) 손실 항. 반환: dict(total, ce_part, bbox_part, giou_part, n_matched). total은 batch 전체 평균 손실에 대한 기여분."""
    import torch
    logits, boxes = out["pred_groundability"].float(), out["pred_boxes"].float()
    outs = {"pred_groundability": logits, "pred_boxes": boxes}
    indices = crit.matcher(outs, targets)
    n_matched = int(sum(len(i) for i, _ in indices))
    nq = logits.shape[1]
    W_mb = n_matched * 1.0 + (logits.shape[0] * nq - n_matched) * crit.eos_coef
    ce = crit.loss_groundability(outs, targets, indices, None, log=False)["loss_groundability"] * (W_mb / w_total_den)
    bx = crit.loss_boxes(outs, targets, indices, denom["num_boxes"])  # sum / (batch 전체 num_boxes)
    wd = crit.weight_dict
    total = wd["loss_groundability"] * ce + wd["loss_bbox"] * bx["loss_bbox"] + wd["loss_giou"] * bx["loss_giou"]
    return {"total": total, "ce": ce.detach(), "bbox": bx["loss_bbox"].detach(), "giou": bx["loss_giou"].detach(), "n_matched": n_matched}


def forward_samples(model, samples, device, autocast):
    import torch
    from utils.misc import NestedTensor
    x = torch.stack([s["image"] for s in samples]).to(device)
    masks = torch.stack([torch.zeros_like(s["image"][0], dtype=torch.bool) for s in samples]).to(device)
    with torch.autocast("cuda", dtype=torch.bfloat16, enabled=autocast):
        out = model(NestedTensor(x, masks), [s["phrase"] for s in samples])
    return out


def accumulate(model, crit, samples, microbatch, device, autocast=True, backward=True):
    """logical batch 전체의 손실/기울기를 microbatch 누적으로 계산(기울기는 .grad에 누적). returns 합계 dict."""
    counts = [len(s["boxes"]) for s in samples]
    den = batch_denoms(counts, HP["num_queries"], crit.eos_coef)
    acc = {"total": 0.0, "ce": 0.0, "bbox": 0.0, "giou": 0.0, "n_matched": 0}
    for i in range(0, len(samples), microbatch):
        mb = samples[i:i + microbatch]
        out = forward_samples(model, mb, device, autocast)
        part = micro_loss(crit, out, targets_of(mb, device), den, den["W"])
        if backward:
            part["total"].backward()
        for k in ("total", "ce", "bbox", "giou"):
            acc[k] += float(part[k].detach())
        acc["n_matched"] += part["n_matched"]
    if acc["n_matched"] != den["n_matched"]:
        raise TrainError(f"matched count {acc['n_matched']} != expected {den['n_matched']}")
    acc.update({"n_gt": den["n_gt"], "denom": den})
    return acc


def train_step(model, crit, opt, samples, microbatch, device, step, steps_main, supp, autocast=True):
    """1 optimizer step: LR 설정 -> 누적 backward -> clip 0.1 -> step. 비유한 값이면 TrainError."""
    import torch
    mult = lr_mult(step, steps_main, supp)
    for g in opt.param_groups:
        g["lr"] = g["base_lr"] * mult
    opt.zero_grad(set_to_none=True)
    acc = accumulate(model, crit, samples, microbatch, device, autocast)
    params = [p for g in opt.param_groups for p in g["params"]]
    gn = torch.nn.utils.clip_grad_norm_(params, HP["clip"])
    if not (math.isfinite(acc["total"]) and torch.isfinite(gn)):
        raise TrainError(f"non-finite loss/grad at step {step}: loss={acc['total']} gn={float(gn)}")
    opt.step()
    acc["grad_norm"] = float(gn)
    acc["lr_mult"] = mult
    acc["lr"] = {g["name"]: g["lr"] for g in opt.param_groups}
    return acc


# ---------------- checkpoint ----------------
def rng_state():
    import random
    import torch
    return {"torch": torch.get_rng_state(), "cuda": torch.cuda.get_rng_state_all(), "numpy": np.random.get_state(), "python": random.getstate()}


def set_rng_state(s):
    import random
    import torch
    torch.set_rng_state(s["torch"])
    torch.cuda.set_rng_state_all(s["cuda"])
    np.random.set_state(s["numpy"])
    random.setstate(s["python"])


def atomic_torch_save(obj, path):
    import torch
    tmp = f"{path}.{os.getpid()}.tmp"
    torch.save(obj, tmp)
    with open(tmp, "rb") as f:
        os.fsync(f.fileno())
    os.replace(tmp, path)
    d = file_sha(path)
    tj = f"{path}.sha256.{os.getpid()}.tmp"
    json.dump({"sha256": d, "bytes": os.path.getsize(path)}, open(tj, "w"))
    os.replace(tj, path + ".sha256.json")
    return d


def load_verified(path):
    import torch
    sj = path + ".sha256.json"
    if not os.path.exists(sj):
        raise TrainError(f"missing digest for {path}")
    if file_sha(path) != json.load(open(sj))["sha256"]:
        raise TrainError(f"checkpoint digest mismatch {path}")
    return torch.load(path, map_location="cpu", weights_only=False)


def acquire_lock(out):
    f = open(os.path.join(out, "train.lock"), "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise TrainError(f"another training process owns {out}")
    f.write(json.dumps({"pid": os.getpid(), "t": time.time()}))
    f.flush()
    return f


# ---------------- train CLI ----------------
def cmd_train(a):
    import torch
    out = a.out
    os.makedirs(out, exist_ok=True)
    lock = acquire_lock(out)
    if a.deterministic:
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    dev = torch.device("cuda:0")
    items = load_t305()
    if a.limit_train:
        items = items[:a.limit_train]  # 재개/동작 검사 전용
    n = len(items)
    spe = steps_per_epoch(n)
    steps_main = HP["horizon_epochs"] * spe if not a.limit_train else a.horizon_steps
    ts = TrainSet(items)
    model, crit, cfg = build_model(dev, HP["seed"])
    opt, ginfo = make_optimizer(model, a.lr_cfg)
    model.train()
    state = {"step": 0, "epoch_done": 0, "epoch_losses": {}, "hist_digest": None}
    rp = os.path.join(out, "resume.pt")
    log_p = os.path.join(out, "train_log.jsonl")
    if os.path.exists(rp):
        ck = load_verified(rp)
        if ck["config"]["lr_cfg"] != a.lr_cfg or ck["config"]["n_items"] != n or ck["config"]["steps_main"] != steps_main or ck["config"]["seed"] != HP["seed"]:
            raise TrainError("resume checkpoint config != requested config")
        model.load_state_dict(ck["model"], strict=True)
        opt.load_state_dict(ck["optimizer"])
        for g, gs in zip(opt.param_groups, ck["optimizer"]["param_groups"]):
            g["base_lr"] = gs["base_lr"]
        state = ck["state"]
        set_rng_state(ck["rng"])
        # 로그: 체크포인트 이후 step 행은 보존 파일로 이동
        if os.path.exists(log_p):
            rows = [json.loads(l) for l in open(log_p) if l.strip()]
            keep = [r for r in rows if r["step"] < state["step"]]
            drop = [r for r in rows if r["step"] >= state["step"]]
            if drop:
                open(os.path.join(out, f"train_log.discarded_{int(time.time())}.jsonl"), "x").write("\n".join(json.dumps(r) for r in drop) + "\n")
            open(log_p, "w").write("".join(json.dumps(r) + "\n" for r in keep))
        print(f"resumed at step {state['step']} epoch_done {state['epoch_done']}", flush=True)
    cfgrec = {"lr_cfg": a.lr_cfg, "n_items": n, "steps_main": steps_main, "seed": HP["seed"], "hp": HP, "lr": LR_CFG[a.lr_cfg], "microbatch": a.microbatch,
              "autocast_bf16": a.bf16, "deterministic": a.deterministic, "groups": ginfo, "init_ckpt_sha256": file_sha(M.WEIGHTS["P"]), "supp": a.supp}
    json.dump(cfgrec, open(os.path.join(out, f"config_{int(time.time())}.json"), "w"), indent=1, default=str)
    pool = ThreadPoolExecutor(max_workers=8)
    save_epochs = [int(x) for x in a.save_epochs.split(",")] if a.save_epochs else []
    log = open(log_p, "a")
    start_epoch = state["epoch_done"]
    while state["epoch_done"] < a.target_epoch:
        ep = state["epoch_done"] + 1  # 1-based epoch (augmentation/order seed용)
        bl = batches(epoch_order(n, HP["seed"], ep), HP["batch"])
        first_b = state["step"] - (ep - 1) * spe
        if not (0 <= first_b <= len(bl)):
            raise TrainError(f"inconsistent step/epoch: step {state['step']} epoch {ep}")
        for bi in range(first_b, len(bl)):
            t0 = time.time()
            samples = list(pool.map(lambda i: ts.get(i, ep, HP["seed"]), bl[bi]))
            t1 = time.time()
            acc = train_step(model, crit, opt, samples, a.microbatch, dev, state["step"], steps_main, a.supp, autocast=a.bf16)
            torch.cuda.synchronize()
            t2 = time.time()
            row = {"step": state["step"], "epoch": ep, "batch_in_epoch": bi, "n_samples": len(samples), "loss": acc["total"], "ce": acc["ce"], "bbox": acc["bbox"],
                   "giou": acc["giou"], "grad_norm": acc["grad_norm"], "lr": acc["lr"], "n_gt_after_aug": acc["n_gt"],
                   "n_gt_dropped": int(sum(s["n_orig"] for s in samples) - acc["n_gt"]), "n_empty_after_aug": int(sum(len(s["boxes"]) == 0 for s in samples)),
                   "data_s": t1 - t0, "step_s": t2 - t1, "peak_alloc_gb": torch.cuda.max_memory_allocated() / 2**30, "finite": True}
            log.write(json.dumps(row) + "\n")
            log.flush()
            os.fsync(log.fileno())
            state["epoch_losses"].setdefault(str(ep), []).append(acc["total"])
            state["step"] += 1
            end_of_epoch = bi == len(bl) - 1
            if end_of_epoch:
                state["epoch_done"] = ep
            if end_of_epoch or (a.ckpt_every and state["step"] % a.ckpt_every == 0):
                if end_of_epoch and ep in save_epochs:
                    wp = os.path.join(out, f"weights_e{ep}.pth")
                    d = atomic_torch_save({"model": model.state_dict()}, wp)
                    json.dump({"epoch": ep, "step": state["step"], "sha256": d, "epoch_mean_train_loss": float(np.mean(state["epoch_losses"][str(ep)]))},
                              open(os.path.join(out, f"weights_e{ep}.json"), "w"))
                atomic_torch_save({"model": model.state_dict(), "optimizer": opt.state_dict(), "state": state, "rng": rng_state(),
                                   "config": {k: cfgrec[k] for k in ("lr_cfg", "n_items", "steps_main", "seed")}}, rp)
            if a.stop_after_steps is not None and state["step"] >= a.stop_after_steps and not end_of_epoch and a.ckpt_every and state["step"] % a.ckpt_every == 0:
                print(f"test stop after step {state['step']}", flush=True)
                os._exit(137)
        mean_loss = float(np.mean(state["epoch_losses"][str(ep)]))
        print(f"epoch {ep} done step {state['step']} mean_loss {mean_loss:.4f}", flush=True)
    done = {"traj": a.traj, "lr_cfg": a.lr_cfg, "epoch_done": state["epoch_done"], "step": state["step"], "resume_sha256": json.load(open(rp + ".sha256.json"))["sha256"],
            "epoch_mean_train_loss": {k: float(np.mean(v)) for k, v in state["epoch_losses"].items()}, "t": time.time()}
    json.dump(done, open(os.path.join(out, f"reached_epoch{state['epoch_done']}.json"), "w"), indent=1)
    lock.close()


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train")
    t.add_argument("--traj", required=True)
    t.add_argument("--out", required=True)
    t.add_argument("--lr-cfg", required=True, choices=["S", "U"])
    t.add_argument("--target-epoch", type=int, required=True)
    t.add_argument("--save-epochs", default="")
    t.add_argument("--microbatch", type=int, default=4)
    t.add_argument("--supp", action="store_true")
    t.add_argument("--bf16", action="store_true", help="기본은 fp32 (gate_throughput: bf16 이득 없음, bf16 loss 차이 7%)")
    t.add_argument("--deterministic", action="store_true")
    t.add_argument("--ckpt-every", type=int, default=10)
    t.add_argument("--limit-train", type=int, default=None, help="재개/동작 검사 전용")
    t.add_argument("--horizon-steps", type=int, default=None)
    t.add_argument("--stop-after-steps", type=int, default=None, help="재개 검사 전용: step N checkpoint 직후 os._exit")
    a = ap.parse_args()
    try:
        cmd_train(a)
    except TrainError as e:
        print(f"TRAIN_ERROR: {e}", flush=True)
        sys.exit(3)


if __name__ == "__main__":
    main()
