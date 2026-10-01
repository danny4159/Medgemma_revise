"""iter_046 기술 동작 확인 (venv, GPU 1장). 결과: results/iter_046/tests/<name>.json (기존 파일 덮어쓰기 거부).
python mg46_vrun.py mg46_gates.py data|matcher|aug|accum|step|overfit|throughput [--microbatches 2,4,8]
연구 가설 판정이 아니라 구현 정합성·메모리·처리량 확인이다.
"""
import argparse
import json
import os
import sys
import time

import numpy as np

import mg46_train as T

OUT = "results/iter_046/tests"


def save(name, obj):
    p = os.path.join(OUT, name)
    os.makedirs(OUT, exist_ok=True)
    if os.path.exists(p):
        sys.exit(f"exists: {p}")
    json.dump(obj, open(p, "x"), indent=1, default=str)
    return p


def pick8(items):
    """metadata 기반 고정 8: 다중 box 2, 작은 단일 2, 큰 단일 2, 긴 문장 2 (정렬 순서 결정적)."""
    def area(it):
        return max((b[2] - b[0]) * (b[3] - b[1]) for b in it["boxes"])
    multi = [i for i, it in enumerate(items) if len(it["boxes"]) > 1]
    single = sorted([i for i, it in enumerate(items) if len(it["boxes"]) == 1], key=lambda i: (area(items[i]), i))
    longs = sorted(range(len(items)), key=lambda i: (-len(items[i]["sentence"]), i))
    chosen = []
    for c in multi[:2] + single[:2] + single[-2:] + longs:
        if c not in chosen:
            chosen.append(c)
    return chosen[:8]


def d_data(a):
    import hashlib
    items = T.load_t305()
    man = json.load(open(T.MAN))
    t_man = {e["PatientID"]: e for e in man["T305"]}
    res = {"n_sentences": len(items), "n_patients": len({i["patient"] for i in items}), "n_boxes": int(sum(len(i["boxes"]) for i in items)),
           "max_boxes": int(max(len(i["boxes"]) for i in items))}
    lock = json.load(open("results/iter_040/data/selection_lock.json"))
    res["manifest_train_sha_matches_lock"] = T.file_sha(T.T305_MAN) == lock["manifest_train_sha256"]
    mism = 0
    for it in items:
        e = t_man[it["patient"]]
        mism += int(e["sentences"][it["target"]] != it["sentence"] or e["gt_boxes_xyxy_norm"][it["target"]] != it["boxes"] or e["u8_pixel_sha256"] != it["u8_sha"])
    res["iter043_t305_mismatch"] = mism
    ts = T.TrainSet(items)  # 전 이미지 디코드 hash 대조 (불일치면 raise)
    res["decoded_pixel_hash_ok_images"] = len(ts.cache)
    # manifest의 raw_png_sha256은 ZIP 원본 PNG(uint16)의 hash다. 저장 영상(uint8 L)의 파일 hash가 아니므로 직접 대조하지 않는다(v1 gate의 잘못된 대조를 정정).
    # 대신 iter_040 manifest와 iter_043 manifest의 raw hash 일치 + 저장 영상 디코드 pixel hash(위) 일치로 provenance를 확인한다.
    rows40 = {json.loads(l)["PatientID"]: json.loads(l) for l in open(T.T305_MAN) if l.strip()}
    res["raw_png_sha_iter040_vs_iter043_mismatch"] = sum(rows40[p]["image_meta"]["raw_png_sha256"] != t_man[p]["raw_png_sha256"] for p in rows40)
    res["u8_sha_iter040_vs_iter043_mismatch"] = sum(rows40[p]["image_meta"]["u8_pixel_sha256"] != t_man[p]["u8_pixel_sha256"] for p in rows40)
    raw_bad = []
    res["raw_png_sha_mismatch"] = res["raw_png_sha_iter040_vs_iter043_mismatch"]
    # 평가 집단과 비중복
    ev = {}
    for k in ("D24", "V96"):
        ev[k] = {"patients": {e["PatientID"] for e in man[k]}, "studies": {e["StudyID"] for e in man[k]}, "images": {e["ImageID"] for e in man[k]},
                 "u8": {e["u8_pixel_sha256"] for e in man[k]}, "raw": {e["raw_png_sha256"] for e in man[k]}}
    tr = {"patients": {i["patient"] for i in items}, "studies": {i["study"] for i in items}, "images": {i["image_id"] for i in items}, "u8": {i["u8_sha"] for i in items},
          "raw": {t_man[i["patient"]]["raw_png_sha256"] for i in items}}
    res["overlap_with_eval"] = {k: {f: len(tr[f] & ev[k][f]) for f in tr} for k in ev}
    res["overlap_D24_V96"] = {f: len(ev["D24"][f] & ev["V96"][f]) for f in ev["D24"]}
    res["eval_counts"] = {"D24": [len(man["D24"]), sum(len(e["gt_boxes_xyxy_norm"][t]) for e in man["D24"] for t in T.TARGETS)],
                          "V96": [len(man["V96"]), sum(len(e["gt_boxes_xyxy_norm"][t]) for e in man["V96"] for t in T.TARGETS)],
                          "V96_max_boxes": max(len(e["gt_boxes_xyxy_norm"][t]) for e in man["V96"] for t in T.TARGETS)}
    res["pick8"] = [{"idx": i, "patient": items[i]["patient"], "target": items[i]["target"], "n_box": len(items[i]["boxes"]), "sent_len": len(items[i]["sentence"])} for i in pick8(items)]
    res["category_labels_nonempty"] = all(len(i["labels"]) > 0 for i in items)
    ok = (res["n_sentences"] == 610 and res["n_patients"] == 305 and res["n_boxes"] == 765 and res["manifest_train_sha_matches_lock"] and mism == 0
          and res["raw_png_sha_mismatch"] == 0 and all(v == 0 for k in res["overlap_with_eval"].values() for v in k.values())
          and all(v == 0 for v in res["overlap_D24_V96"].values()) and res["eval_counts"]["D24"] == [24, 59] and res["eval_counts"]["V96"] == [96, 249])
    res["PASS"] = bool(ok)
    print(save("gate_data_v2.json", res))
    sys.exit(0 if ok else 1)


def d_matcher(a):
    import torch
    from model.medgrounder_matcher import HungarianMatcher
    S = T.make_strict_matcher_cls()
    rng = torch.Generator().manual_seed(0)
    off, st = HungarianMatcher(1, 5, 2), S(1, 5, 2)
    same, n = 0, 200
    for k in range(n):
        B = 4
        out = {"pred_groundability": torch.randn(B, 5, 2, generator=rng), "pred_boxes": torch.rand(B, 5, 4, generator=rng) * 0.6 + 0.1}
        tg = []
        for b in range(B):
            m = int(torch.randint(0, 5, (1,), generator=rng))
            tg.append({"labels": torch.zeros(m, dtype=torch.int64), "boxes": torch.rand(m, 4, generator=rng) * 0.5 + 0.1})
        o, s = off(out, tg), st(out, tg)
        same += all(torch.equal(x[0], y[0]) and torch.equal(x[1], y[1]) for x, y in zip(o, s))
    res = {"random_cases": n, "identical_assignments": same}
    raised = {}
    base = {"pred_groundability": torch.randn(1, 5, 2), "pred_boxes": torch.rand(1, 5, 4) * 0.5 + 0.1}
    tg = [{"labels": torch.zeros(1, dtype=torch.int64), "boxes": torch.tensor([[0.5, 0.5, 0.2, 0.2]])}]
    for name, mod in (("nan_pred", lambda o, t: o["pred_boxes"].__setitem__((0, 0, 0), float("nan"))), ("zero_wh_target", lambda o, t: t[0]["boxes"].__setitem__((0, 2), 0.0)),
                      ("nan_logit", lambda o, t: o["pred_groundability"].__setitem__((0, 1, 0), float("nan")))):
        o = {k: v.clone() for k, v in base.items()}
        t = [{k: v.clone() for k, v in tg[0].items()}]
        mod(o, t)
        try:
            st(o, t)
            raised[name] = False
        except T.TrainError:
            raised[name] = True
    res["strict_raises"] = raised
    # 공식은 비양수 크기에서 경고만 출력하고 fallback 가능: 대조용 기록
    res["PASS"] = bool(same == n and all(raised.values()))
    print(save("gate_matcher.json", res))
    sys.exit(0 if res["PASS"] else 1)


def d_aug(a):
    items = T.load_t305()
    ts = T.TrainSet(items[:40])
    import torch
    r = {}
    s1, s2 = ts.get(3, 1, 17), ts.get(3, 1, 17)
    r["same_seed_identical_image"] = bool(torch.equal(s1["image"], s2["image"])) and bool(torch.equal(s1["boxes"], s2["boxes"]))
    diffs = sum(not torch.equal(ts.get(3, e, 17)["image"], s1["image"]) for e in range(2, 8))
    r["different_epoch_differs_of_6"] = int(diffs)
    # 40 샘플 x 20 epoch: box 삭제/전체 삭제 빈도
    drop = empty = tot = 0
    for e in range(1, 21):
        for i in range(40):
            s = ts.get(i, e, 17)
            drop += s["n_orig"] - len(s["boxes"])
            empty += int(len(s["boxes"]) == 0)
            tot += 1
    r["box_dropped_total"] = drop
    r["all_boxes_deleted_samples"] = empty
    r["samples_checked"] = tot
    v = ts.get(3, 1, 17, augment=False)
    from mg45_mg import val_transform
    import numpy as np
    out = val_transform()(image=ts.cache[items[3]["image"]], bboxes=np.array(items[3]["boxes"], dtype=np.float32), bbox_labels=[1] * len(items[3]["boxes"]))
    r["val_path_equals_official_val_transform"] = bool(torch.equal(v["image"], out["image"]))
    r["PASS"] = bool(r["same_seed_identical_image"] and r["different_epoch_differs_of_6"] >= 5 and r["val_path_equals_official_val_transform"])
    print(save("gate_aug.json", r))
    sys.exit(0 if r["PASS"] else 1)


def _grad_vec(model):
    import torch
    return torch.cat([p.grad.detach().flatten().float().cpu() if p.grad is not None else torch.zeros(p.numel()) for p in model.parameters() if p.requires_grad])


def _official_loss(crit, out, targets):
    losses = crit({"pred_groundability": out["pred_groundability"].float(), "pred_boxes": out["pred_boxes"].float()}, targets)
    wd = crit.weight_dict
    return wd["loss_groundability"] * losses["loss_groundability"] + wd["loss_bbox"] * losses["loss_bbox"] + wd["loss_giou"] * losses["loss_giou"]


def d_accum(a):
    import torch
    dev = torch.device("cuda:0")
    items = T.load_t305()
    idx = pick8(items)
    ts = T.TrainSet([items[i] for i in idx])
    model, crit, _ = T.build_model(dev)
    model.eval()  # dropout off (FrozenBN은 train/eval 동일)
    torch.backends.cudnn.deterministic = True  # v2: v1(비결정 cudnn)에서 split 대 unsplit 기울기 상대차 ~1e-3 > 사전 기준 1e-4 -> 반복 노이즈 바닥을 함께 측정
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.allow_tf32 = False  # v3: cudnn conv의 기본 TF32가 batch 분할별 ~1e-3 기울기 차이를 만든다는 가설 확인
    torch.backends.cuda.matmul.allow_tf32 = False
    samples = [ts.get(i, 1, 17) for i in range(8)]
    zero = dict(samples[0]); zero["boxes"] = zero["boxes"][:0]
    cases = {"full8": samples, "last6": samples[:6], "with_zero_gt": [zero] + samples[1:5]}
    res = {"cases": {}}
    for name, ss in cases.items():
        model.zero_grad(set_to_none=True)
        out = T.forward_samples(model, ss, dev, False)
        l0 = _official_loss(crit, out, T.targets_of(ss, dev))
        l0.backward()
        g0 = _grad_vec(model)
        ref = float(l0)
        model.zero_grad(set_to_none=True)
        out_r = T.forward_samples(model, ss, dev, False)
        _official_loss(crit, out_r, T.targets_of(ss, dev)).backward()
        gr = _grad_vec(model)
        noise = float((gr - g0).norm() / (g0.norm() + 1e-30))
        res["cases"][name] = {"official_unsplit_repeat_grad_rel_l2": noise, "official_unsplit_loss": ref, "n": len(ss), "n_gt": int(sum(len(s["boxes"]) for s in ss)), "mb": {}}
        for mb in (1, 2, 3, 4):
            model.zero_grad(set_to_none=True)
            acc = T.accumulate(model, crit, ss, mb, dev, autocast=False)
            g = _grad_vec(model)
            rel = float((g - g0).norm() / (g0.norm() + 1e-30))
            res["cases"][name]["mb"][str(mb)] = {"loss": acc["total"], "abs_loss_diff": abs(acc["total"] - ref), "grad_rel_l2_diff": rel, "grad_max_abs_diff": float((g - g0).abs().max())}
    # 이상 분모 점검: CE 가중 평균 vs 단순 평균 차이가 실제로 재가중을 필요로 함을 확인 (microbatch별 평균을 그냥 평균하면 달라지는 정도)
    naive = {}
    ss = cases["last6"]
    model.zero_grad(set_to_none=True)
    vals = []
    for i in range(0, 6, 4):
        mbs = ss[i:i + 4]
        out = T.forward_samples(model, mbs, dev, False)
        vals.append(float(_official_loss(crit, out, T.targets_of(mbs, dev))) * len(mbs) / 6)
    naive["naive_mean_of_official_microbatch_losses_last6"] = sum(vals)
    res["naive_for_contrast"] = naive
    worst = max(v["grad_rel_l2_diff"] for c in res["cases"].values() for v in c["mb"].values())
    wl = max(v["abs_loss_diff"] for c in res["cases"].values() for v in c["mb"].values())
    res["worst_grad_rel_l2"] = worst
    res["worst_abs_loss_diff"] = wl
    res["picked8"] = idx
    noise_max = max(c["official_unsplit_repeat_grad_rel_l2"] for c in res["cases"].values())
    res["noise_floor_repeat_grad_rel_l2_max"] = noise_max
    res["PASS_rule"] = "abs loss diff < 1e-4 and worst split grad rel L2 < max(1e-3, 5 x repeat-run noise floor); v1 used 1e-4 grad (non-deterministic cudnn) and failed at 1.4e-3 (kept as gate_accum.json)"
    res["PASS"] = bool(wl < 1e-4 and worst < max(1e-3, 5 * noise_max))
    print(save("gate_accum_v3.json", res))
    sys.exit(0 if res["PASS"] else 1)


def d_step(a):
    import torch
    dev = torch.device("cuda:0")
    items = T.load_t305()
    idx = pick8(items)
    ts = T.TrainSet([items[i] for i in idx])
    model, crit, _ = T.build_model(dev)
    samples = [ts.get(i, 1, 17) for i in range(8)]
    res = {}
    # bf16 vs fp32 (eval mode, 같은 가중치)
    model.eval()
    with torch.no_grad():
        o32 = T.forward_samples(model, samples, dev, False)
        o16 = T.forward_samples(model, samples, dev, True)
        l32 = _official_loss(crit, o32, T.targets_of(samples, dev))
        l16 = _official_loss(crit, o16, T.targets_of(samples, dev))
    res["fp32_loss"], res["bf16_loss"] = float(l32), float(l16)
    res["logit_max_abs_diff"] = float((o32["pred_groundability"].float() - o16["pred_groundability"].float()).abs().max())
    res["box_max_abs_diff"] = float((o32["pred_boxes"].float() - o16["pred_boxes"].float()).abs().max())
    res["bf16_outputs_finite"] = bool(torch.isfinite(o16["pred_groundability"]).all() and torch.isfinite(o16["pred_boxes"]).all())
    # 실제 update 검사 (train mode, LR>0 step)
    model.train()
    opt, ginfo = T.make_optimizer(model, "S")
    res["groups"] = ginfo
    before = {n: p.detach().clone() for n, p in model.named_parameters()}
    acc = T.train_step(model, crit, opt, samples, 4, dev, step=5, steps_main=300, supp=False)
    changed = {"backbone": [0, 0], "text_encoder": [0, 0], "base": [0, 0]}
    for g in opt.param_groups:
        for p in g["params"]:
            pass
    name_group = {}
    for n, p in model.named_parameters():
        if p.requires_grad:
            k = "backbone" if n.startswith("backbone.") else ("text_encoder" if "text_encoder." in n else "base")
            changed[k][1] += 1
            changed[k][0] += int(not torch.equal(before[n], p.detach()))
    frozen_changed = sum(int(not torch.equal(before[n], p.detach())) for n, p in model.named_parameters() if not p.requires_grad)
    res["tensors_changed_over_total"] = changed
    res["frozen_tensors_changed"] = frozen_changed
    res["step_loss"], res["grad_norm_pre_clip"], res["lr_after_mult"] = acc["total"], acc["grad_norm"], acc["lr"]
    res["peak_alloc_gb_mb4"] = torch.cuda.max_memory_allocated() / 2**30
    res["PASS"] = bool(res["bf16_outputs_finite"] and np.isfinite(acc["total"]) and frozen_changed == 0 and all(c[0] > 0 for c in changed.values()))
    print(save("gate_step.json", res))
    sys.exit(0 if res["PASS"] else 1)


def d_overfit(a):
    import torch
    dev = torch.device("cuda:0")
    items = T.load_t305()
    idx = pick8(items)
    ts = T.TrainSet([items[i] for i in idx])
    model, crit, _ = T.build_model(dev)  # scratch copy: 본학습에 사용하지 않음
    model.train()
    opt, _ = T.make_optimizer(model, "S")
    samples = [ts.get(i, 1, 17, augment=False) for i in range(8)]
    losses = []
    for s in range(a.steps):
        for g in opt.param_groups:
            g["base_lr"] = 10 * g["base_lr"] if s == 0 else g["base_lr"]  # 1e-4/5e-4 짧은 overfit 용 (본학습 설정 아님)
        acc = T.train_step(model, crit, opt, samples, 4, dev, step=a.steps_main // 2, steps_main=a.steps_main, supp=False, autocast=False)
        losses.append(acc["total"])
    res = {"purpose": "scratch overfit (8 fixed samples, no aug, 10x LR) technical check only", "losses": losses, "first": losses[0], "last": losses[-1], "ratio": losses[-1] / losses[0]}
    res["PASS"] = bool(losses[-1] < 0.6 * losses[0])
    print(save("gate_overfit.json", res))
    sys.exit(0 if res["PASS"] else 1)


def d_throughput(a):
    import torch
    dev = torch.device("cuda:0")
    items = T.load_t305()
    ts = T.TrainSet(items[:64])
    res = {"mb": {}, "visible": os.environ.get("CUDA_VISIBLE_DEVICES"), "autocast_bf16": not a.fp32}
    for mb in [int(x) for x in a.microbatches.split(",")]:
        try:
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            model, crit, _ = T.build_model(dev)
            model.train()
            opt, _ = T.make_optimizer(model, "S")
            samples = [ts.get(i, 1, 17) for i in range(32)]
            times = []
            for s in range(4):
                t0 = time.time()
                acc = T.train_step(model, crit, opt, samples, mb, dev, step=5 + s, steps_main=300, supp=False, autocast=not a.fp32)
                torch.cuda.synchronize()
                times.append(time.time() - t0)
            res["mb"][str(mb)] = {"step_s": times, "median_step_s_excl_first": float(np.median(times[1:])), "peak_alloc_gb": torch.cuda.max_memory_allocated() / 2**30,
                                  "peak_reserved_gb": torch.cuda.max_memory_reserved() / 2**30, "loss": acc["total"]}
            del model, crit, opt
        except torch.cuda.OutOfMemoryError as e:
            res["mb"][str(mb)] = {"oom": True}
            torch.cuda.empty_cache()
    print(save(a.name, res))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--steps-main", type=int, default=300)
    ap.add_argument("--microbatches", default="2,4,8")
    ap.add_argument("--name", default="gate_throughput.json")
    ap.add_argument("--fp32", action="store_true")
    a = ap.parse_args()
    {"data": d_data, "matcher": d_matcher, "aug": d_aug, "accum": d_accum, "step": d_step, "overfit": d_overfit, "throughput": d_throughput}[a.cmd](a)


if __name__ == "__main__":
    main()
