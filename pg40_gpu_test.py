"""iter_040 GPU 동작 확인 (실제 MedGemma, T305 학습 자료 일부). overfit 결과는 일반화 근거가 아니다.

python pg40_gpu_test.py inproc --out results/iter_040/tests/gpu_inproc.json
python pg40_gpu_test.py resume --out results/iter_040/tests/gpu_resume.json
GPU는 상속된 CUDA_VISIBLE_DEVICES의 첫 장치를 쓴다 (프로세스 안에서 장치 지정 변경 없음).
"""
import os
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")  # 결정적 cuBLAS workspace (CUDA context 생성 전)
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

import numpy as np

import pg39_spec as S
import pg40_train as T
from rsna_diag import generate, lora, sft_data
from rsna_diag import train as T0

RES = []


def check(name, ok, detail=None):
    RES.append({"name": name, "pass": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name, json.dumps(detail, default=str)[:400], flush=True)


def pick_rows(n_per=2):
    rows = sorted(T.load_rows(T.TRAIN_MANIFEST, {"T305"}), key=lambda r: r["PatientID"])
    out = []
    for st in sorted({r["stratum"] for r in rows}):
        for el in (True, False):
            c = [r for r in rows if r["stratum"] == st and r["contrast_eligible"] == el]
            out += c[:n_per if st.startswith("share0") else 1]
    return out


def maxdiff(a, b):
    return max(float((x - y).abs().max()) for x, y in zip(a, b))


def inproc(a):
    import torch
    torch.manual_seed(0)
    torch_, proc, model = generate.load_model()
    T0.set_deterministic(torch_)  # 이 검사는 결정적 kernel 하에서 수행 (비결정 잡음과 구현 차이를 분리)
    tok = proc.tokenizer
    softcap = getattr(model.config.get_text_config(), "final_logit_softcapping", None)
    rows = pick_rows()
    check("pick_rows_cover_strata_and_eligibility", len({r["stratum"] for r in rows}) == 4 and {r["contrast_eligible"] for r in rows} == {True, False},
          {"n": len(rows), "strata": sorted({r["stratum"] for r in rows})})
    ds = T.PatientDataset(proc, rows, list(range(len(rows))), True)
    items = [ds[i] for i in range(len(rows))]
    # --- T1: prefix/tensor/labels ---
    ok_lab, ok_img, ok_pad, ok_txt = True, True, True, True
    for r, it in zip(rows, items):
        tx = T.patient_texts(r, r["contrast_eligible"])
        for pid in ("qA", "qB"):
            ex = it["pos"][pid]
            lab = ex["labels"]
            keep = lab[lab != -100].tolist()
            txt = tok.decode(keep, skip_special_tokens=False)
            ok_txt &= txt == tx["pos"][pid][1] + "<end_of_turn>"
            ok_lab &= bool((lab[:ex["n_prefix"]] == -100).all()) and int(lab[-1]) == -100
            image, _, _ = generate.load_image(r["image_meta"]["path"])
            gen = generate.build_inputs(proc, image, tx["pos"][pid][0])
            ok_img &= bool((gen["pixel_values"] == ex["pixel_values"]).all()) and bool((gen["input_ids"][0] == ex["input_ids"][:ex["n_prefix"]]).all())
    check("train_prefix_equals_generation_prefix_and_pixels", ok_img)
    check("labels_are_assistant_json_plus_eot_only", ok_lab and ok_txt)
    b = sft_data.collate([items[0]["pos"]["qA"], items[1]["pos"]["qB"]], tok.pad_token_id)
    pad_mask = b["attention_mask"] == 0
    check("padding_positions_excluded_from_loss", bool((b["labels"][pad_mask] == -100).all()) and bool(pad_mask.any()), {"n_pad": int(pad_mask.sum())})
    # --- T7: 문장/ID 교체 fixture ---
    ok_sw = True
    det = []
    for r, it in zip(rows, items):
        if not r["contrast_eligible"]:
            ok_sw &= it["cross"] is None
            continue
        for pid, oth in (("qA", "qB"), ("qB", "qA")):
            p, c = it["pos"][pid], it["cross"][pid]
            lp, lc = p["labels"][p["labels"] != -100], c["labels"][c["labels"] != -100]
            same_target = bool(torch_.equal(lp, lc))
            pr_c = tok.decode(c["input_ids"][:c["n_prefix"]].tolist(), skip_special_tokens=False)
            has_sent = r["sentences"][oth] in pr_c and f'"{pid}"' in pr_c and r["sentences"][pid] not in pr_c
            ok_sw &= same_target and has_sent
            det.append([same_target, has_sent])
    check("cross_target_identical_id_and_length_only_sentence_swapped", ok_sw, det[:4])
    # --- T2: LoRA identity + frozen base ---
    base_h0 = None
    ex0 = items[0]["pos"]["qA"]
    bt = {k: v.unsqueeze(0).cuda() if k in ("input_ids", "attention_mask", "token_type_ids") else v.cuda() for k, v in ex0.items()
          if k in ("input_ids", "attention_mask", "token_type_ids", "pixel_values")}
    bt["pixel_values"] = bt["pixel_values"].to(torch_.bfloat16)
    model.eval()
    with torch_.no_grad():
        base_logits = model(**bt).logits.float().cpu()
    base_h0 = lora.base_digest(model)
    names = lora.apply_lora(model, T.CFG["r"], T.CFG["alpha"], T.CFG["dropout"], seed=17)
    with torch_.no_grad():
        l_logits = model(**bt).logits.float().cpu()
    check("lora_init_identity_logits", float((base_logits - l_logits).abs().max()) == 0.0, {"max_abs": float((base_logits - l_logits).abs().max())})
    lay = {n.split(".")[3] for n in names}
    check("lora_targets_language_layers_only", all(n.startswith(lora.LM_LAYER_PREFIX) for n in names) and len(names) == 238, {"n": len(names), "n_layers": len(lay)})
    params = list(lora.lora_params(model).values())
    check("only_lora_params_trainable", all("lora_" in n for n in lora.lora_params(model)) and sum(p.numel() for p in params) == 29802496,
          {"n_trainable": sum(p.numel() for p in params)})
    # LoRA B를 작은 무작위 값으로 (deterministic) -> gradient/등가성 검사가 자명하지 않게
    g = torch_.Generator().manual_seed(123)
    with torch_.no_grad():
        for n, p in model.named_parameters():
            if "lora_B" in n:
                p.copy_(torch_.randn(p.shape, generator=g) * 0.01)
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.config.use_cache = False
    pad = tok.pad_token_id
    # --- T3: CE 독립 대조 (전체 logits) ---
    model.eval()
    ex = items[0]["pos"]["qA"]
    bb = sft_data.collate([ex], pad)
    bbc = {k: v.cuda() for k, v in bb.items()}
    with torch_.no_grad():
        ce, n = T.seq_losses(torch_, model, bbc, softcap)
    inp = {k: v for k, v in bbc.items() if k != "labels"}
    inp["pixel_values"] = inp["pixel_values"].to(torch_.bfloat16)
    with torch_.no_grad():
        full = model(**inp).logits.float()
    lab = bbc["labels"][:, 1:]
    sel = lab != -100
    ref = torch_.nn.functional.cross_entropy(full[:, :-1][sel], lab[sel], reduction="sum")
    check("ce_matches_independent_full_logits_ce", abs(float(ce.sum()) - float(ref)) / max(1.0, float(ref)) < 5e-3 and int(n.sum()) == int(sel.sum()),
          {"trainer": float(ce.sum()), "independent": float(ref), "ntok": int(n.sum()), "softcap": softcap})
    # --- T6: pair/ell 독립 계산 (eval mode) ---
    el_idx = [i for i, r in enumerate(rows) if r["contrast_eligible"]][0]
    it = items[el_idx]

    def ell_ref(exx):
        bb = {k: v.cuda() for k, v in sft_data.collate([exx], pad).items()}
        inp = {k: v for k, v in bb.items() if k != "labels"}
        inp["pixel_values"] = inp["pixel_values"].to(torch_.bfloat16)
        with torch_.no_grad():
            lg = model(**inp).logits.float()
        lb = bb["labels"][:, 1:]
        s = lb != -100
        lp = torch_.log_softmax(lg[:, :-1], -1)[s].gather(1, lb[s].unsqueeze(1)).squeeze(1)
        return float(lp.mean())
    info = T.patient_step(torch_, model, it, pad, softcap, 100, 1, 0.1, 0.1, 1, True, 7, backward=False)
    e = {("pos", p): ell_ref(it["pos"][p]) for p in ("qA", "qB")}
    e.update({("cross", p): ell_ref(it["cross"][p]) for p in ("qA", "qB")})
    pair_ref = 0.5 * (max(0, 0.1 - e[("pos", "qA")] + e[("cross", "qA")]) + max(0, 0.1 - e[("pos", "qB")] + e[("cross", "qB")]))
    check("pair_loss_matches_independent_log_likelihood", abs(info["pair"] - pair_ref) < 5e-3 and
          max(abs(info["ell_pos"][0] - e[("pos", "qA")]), abs(info["ell_cross"][1] - e[("cross", "qB")])) < 5e-3,
          {"pair": info["pair"], "ref": pair_ref, "ell": info["ell_pos"] + info["ell_cross"]})
    # 동일 문장이면 ell 차이 0 (문장 조건이 유일한 차이)
    same = {"pos": it["pos"], "cross": {"qA": it["pos"]["qA"], "qB": it["pos"]["qB"]}}
    i2 = T.patient_step(torch_, model, same, pad, softcap, 100, 1, 0.1, 0.1, 1, True, 7, backward=False)
    check("identical_prompt_gives_zero_ell_difference", max(abs(m) for m in i2["margin"]) < 1e-6, {"margin": i2["margin"]})
    # --- T4/T5: lam=0 환원, 누적 순서, 단일 그래프 대조 ---
    model.train()
    sub = [items[i] for i in [el_idx, [i for i, r in enumerate(rows) if r["contrast_eligible"]][1], [i for i, r in enumerate(rows) if not r["contrast_eligible"]][0]]]
    tt = sum(T.label_count(tok, t) for i in sub for t in T.patient_texts(rows[items.index(i)], False)["targets"].values())

    def grads(order, lam, cross, mb=1):
        for p in params:
            p.grad = None
        for k in order:
            T.patient_step(torch_, model, sub[k], pad, softcap, tt, 3, lam, 0.1, mb, cross and sub[k]["cross"] is not None, T.derive_seed(17, 0, k))
        return [p.grad.detach().clone() for p in params]
    gC = grads([0, 1, 2], 0.0, False)
    gC2 = grads([0, 1, 2], 0.0, False)
    check("repeat_same_function_gradient_noise_floor_is_zero_in_deterministic_mode", maxdiff(gC, gC2) == 0.0, {"max_abs_diff": maxdiff(gC, gC2)})
    gM0 = grads([0, 1, 2], 0.0, True)
    check("lambda0_with_cross_forward_reduces_to_CE_gradients_exactly", maxdiff(gC, gM0) == 0.0, {"max_abs_diff": maxdiff(gC, gM0)})
    gM = grads([0, 1, 2], 0.1, True)
    check("contrast_term_changes_gradients", maxdiff(gC, gM) > 0, {"max_abs_diff": maxdiff(gC, gM)})
    gr = grads([2, 1, 0], 0.1, True)
    nrm = float(torch_.sqrt(sum((x.float() ** 2).sum() for x in gM)))
    check("accumulation_order_invariance_grad", maxdiff(gM, gr) / nrm < 1e-3, {"max_abs": maxdiff(gM, gr), "grad_norm": nrm})
    gmb2 = grads([0, 1, 2], 0.1, True, mb=2)
    check("microbatch2_vs_1_grad_close", maxdiff(gM, gmb2) / nrm < 2e-2, {"max_abs": maxdiff(gM, gmb2), "grad_norm": nrm})
    # 단일 그래프(누적 없음) 대조: 각 환자의 loss를 하나의 스칼라로 합쳐 한 번 backward
    for p in params:
        p.grad = None
    tot = 0
    for k in range(3):
        torch_.manual_seed(T.derive_seed(17, 0, k))
        torch_.cuda.manual_seed(T.derive_seed(17, 0, k))
        c, nn_, _ = T.group_losses(torch_, model, [sub[k]["pos"]["qA"], sub[k]["pos"]["qB"]], pad, softcap, 1)
        ell = -c / nn_
        tot = tot + c.sum() / tt
        if sub[k]["cross"] is not None:
            cc, cn, _ = T.group_losses(torch_, model, [sub[k]["cross"]["qA"], sub[k]["cross"]["qB"]], pad, softcap, 1)
            ec = -cc / cn
            tot = tot + 0.1 * 0.5 * (torch_.relu(0.1 - ell[0] + ec[0]) + torch_.relu(0.1 - ell[1] + ec[1])) / 3
    tot.backward()
    g1 = [p.grad.detach().clone() for p in params]
    check("single_graph_equals_accumulated_gradients", maxdiff(gM, g1) / nrm < 1e-3, {"max_abs": maxdiff(gM, g1), "grad_norm": nrm})
    check("gradients_finite", all(bool(torch_.isfinite(x).all()) for x in gM))
    # AdamW update 동일성 (lam0 cross vs C)
    def one_update(gs):
        st = lora.lora_state_dict(model)
        opt = torch_.optim.AdamW(params, lr=1e-4, betas=(0.9, 0.999), eps=1e-8, weight_decay=0.01)
        for p, g_ in zip(params, gs):
            p.grad = g_.clone()
        torch_.nn.utils.clip_grad_norm_(params, 1.0)
        opt.step()
        d = lora.state_digest(lora.lora_state_dict(model))
        lora.load_lora_state(model, st)
        return d
    check("lambda0_update_identical_to_CE_update", one_update(gC) == one_update(gM0))
    # --- T9: 저장·복원 ---
    st = lora.lora_state_dict(model)
    d0 = lora.state_digest(st)
    os.makedirs("results/iter_040/tests/adapter_rt", exist_ok=True)
    T0.save_adapter(torch_, model, "results/iter_040/tests/adapter_rt/adapter.pt", {"x": 1})
    with torch_.no_grad():
        for p in params:
            p.add_(1.0)
    blob = torch_.load("results/iter_040/tests/adapter_rt/adapter.pt", map_location="cpu", weights_only=True)
    lora.load_lora_state(model, blob["state"])
    model.eval()
    with torch_.no_grad():
        l2 = model(**bt).logits.float().cpu()
    d1 = lora.state_digest(lora.lora_state_dict(model))
    check("adapter_save_restore_identical", d0 == d1 and blob["digest"] == d0)
    # 동결 base
    check("base_weights_unchanged_after_lora_ops", lora.base_digest(model) == base_h0)
    # 메모리
    check("peak_mem_recorded", True, {"peak_alloc_gb": torch_.cuda.max_memory_allocated() / 2 ** 30})
    json.dump({"results": RES, "n_pass": sum(r["pass"] for r in RES), "n": len(RES)}, open(a.out, "w"), indent=1, default=str)
    print(f"{sum(r['pass'] for r in RES)}/{len(RES)} PASS")


def run_train(args, tag):
    cmd = [sys.executable, "pg40_train.py", "train"] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r


def steps(run_dir):
    out = {}
    for l in open(os.path.join(run_dir, "train_log.jsonl")):
        d = json.loads(l)
        if d["event"] == "step":
            out[d["step"]] = d
    return out


def resume(a):
    base = "results/iter_040/tests/resume"
    os.makedirs(base, exist_ok=True)
    proto = os.path.join(base, "protocol.json")
    if not os.path.exists(proto):
        T.make_protocol(proto)
    common = ["--protocol", proto, "--lr", "2e-4", "--schedule", "cosine8", "--seed", "17", "--total-updates", "4", "--max-patients", "32", "--mb", "1",
              "--workers", "2", "--deterministic", "--ckpt-every", "2", "--check-base"]
    for mode in ("ce_contrast", "ce"):
        A, Bd = os.path.join(base, f"{mode}_cont"), os.path.join(base, f"{mode}_kill")
        for d in (A, Bd):
            if os.path.exists(d):
                sys.exit(f"{d} exists (new attempt path required)")
        r1 = run_train(["--run-dir", A, "--mode", mode] + common, "A")
        r2 = run_train(["--run-dir", Bd, "--mode", mode, "--stop-after-step", "2"] + common, "B1")
        stopped = r2.returncode == 5
        r3 = run_train(["--run-dir", Bd, "--mode", mode] + common, "B2")
        sa, sb = steps(A), steps(Bd)
        loss_diff = max(abs(sa[k]["loss"] - sb[k]["loss"]) for k in sa) if set(sa) == set(sb) else None
        da = json.load(open(os.path.join(A, "train_config.json")))["train_digest"]
        import torch
        fa = sorted(x for x in os.listdir(A) if x.startswith(("epoch_", "step_")))
        fb = sorted(x for x in os.listdir(Bd) if x.startswith(("epoch_", "step_")))
        da_ = torch.load(os.path.join(A, fa[-1], "adapter.pt"), map_location="cpu", weights_only=True)["digest"]
        db_ = torch.load(os.path.join(Bd, fb[-1], "adapter.pt"), map_location="cpu", weights_only=True)["digest"]
        ev = [json.loads(l) for l in open(os.path.join(Bd, "train_log.jsonl"))]
        resumed = [e for e in ev if e["event"] == "resume"]
        base_ok = any(e["event"] == "base_frozen_verified" for e in [json.loads(l) for l in open(os.path.join(A, "train_log.jsonl"))])
        check(f"{mode}_stop_at_mid_optimizer_step_then_resume_ok", r1.returncode == 0 and stopped and r3.returncode == 0 and len(resumed) == 1 and resumed[0]["restored_equals_saved"],
              {"rc": [r1.returncode, r2.returncode, r3.returncode], "stderr_tail": (r3.stderr or "")[-300:] if r3.returncode else ""})
        check(f"{mode}_resumed_losses_equal_continuous", loss_diff is not None and loss_diff == 0.0, {"max_loss_diff": loss_diff, "n_steps": [len(sa), len(sb)]})
        check(f"{mode}_final_adapter_digest_equal", da_ == db_, {"cont": da_[:16], "resumed": db_[:16]})
        check(f"{mode}_base_frozen_verified_in_run", base_ok)
        check(f"{mode}_batch_ids_and_rng_match_after_resume", all(sa[k]["batch_rows"] == sb[k]["batch_rows"] and sa[k]["rng_before"] == sb[k]["rng_before"] for k in sa) if set(sa) == set(sb) else False)
    # 동시 실행 lock 거부
    lockdir = os.path.join(base, "lock_test")
    os.makedirs(lockdir, exist_ok=True)
    from rsna_diag import queue_lock
    lk, _, _ = queue_lock.try_lock(os.path.join(os.path.realpath(lockdir), "train.lock"), queue_lock.my_info(role="test"))
    r = run_train(["--run-dir", lockdir, "--mode", "ce", "--protocol", proto, "--lr", "2e-4", "--schedule", "const", "--total-updates", "1", "--max-patients", "8"], "lock")
    lk.release()
    check("second_writer_on_same_run_dir_rejected", r.returncode != 0 and "owned by another live process" in (r.stderr + r.stdout))
    # protocol 변조 거부: 잠긴 코드 파일 대신 복제한 protocol의 hash를 바꿔 넣는다
    p = json.load(open(proto))
    p["code"]["pg40_train.py"] = "0" * 64
    bad = os.path.join(base, "protocol_tampered.json")
    json.dump(p, open(bad, "w"))
    r = run_train(["--run-dir", os.path.join(base, "tamper"), "--mode", "ce", "--protocol", bad, "--lr", "2e-4", "--schedule", "const", "--total-updates", "1"], "tamper")
    check("tampered_protocol_rejected", r.returncode != 0 and "code changed since protocol lock" in (r.stderr + r.stdout))
    json.dump({"results": RES, "n_pass": sum(r["pass"] for r in RES), "n": len(RES)}, open(a.out, "w"), indent=1, default=str)
    print(f"{sum(r['pass'] for r in RES)}/{len(RES)} PASS")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=["inproc", "resume"])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("output exists")
    (inproc if a.which == "inproc" else resume)(a)
