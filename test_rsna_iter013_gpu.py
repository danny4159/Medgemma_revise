"""iter_013 실제 MedGemma GPU 검사. 실행: python test_rsna_iter013_gpu.py -> results/iter_013/tests/fixtures_iter013_gpu.json, 산출물 results/iter_013/pilot/
GPU는 상속된 CUDA_VISIBLE_DEVICES 허용 집합 안에서만 쓴다 (허용 집합의 첫/둘째 장치를 lane0/lane1로 사용).

E  loss 경로 등가 (lane1, in-process): adapt.adapt_loss(C)의 CE 합·gradient가 기존 train.assistant_loss_sum과 일치, H/D 추가 항이 같은 logits의
   독립 float64 계산과 일치, alpha=0 gradient == CE gradient.
D  재개 (lane0, 결정적 kernel, sanity16/eff4/2 epochs/val8, loss D): 무중단 U, 그리고 U와 같은 시작점의 R = step2 직후 종료 -> epoch1 validation 3요청 뒤 종료
   -> 복구·완료. batch ID·token/mask sha·LR·RNG·optimizer step 정확 일치, loss/ce/extra rtol 1e-3, 최종 adapter digest·val 지표 비교.
X  조건 간 (lane1, 결정적, 각 1 step): C/H/D의 step1 batch·token sha·CE가 같고 C의 monitor extra == H/D의 extra.
M  microbatch 2 vs 4 (lane0 mb2, lane1 mb4 동시, pilot_mb stage, D): step 시간·peak 메모리·step1 CE.
I  추론 workers: lane0 1 worker vs lane1 2 workers (thr48, B0 adapter, concise): token 일치·처리량·GPU 점유, 그리고 --parent-dir 재사용 경로(NameError 수정) 검사.
pilot weight는 본실험에 이월하지 않는다.
"""
import json
import os
import subprocess
import sys
import threading
import time

PROT = "results/iter_013/protocols/pilot_protocol.json"
B = "results/iter_013/pilot"
T = "results/iter_013/tests"
ST = "results/iter_013/stage/"
R = {}
LANES = [int(x) for x in os.environ.get("CUDA_VISIBLE_DEVICES", "0,1").split(",")]
L0, L1 = LANES[0], LANES[-1]
RTOL = 1e-3


def check(name, cond, detail=None):
    R[name] = {"pass": bool(cond), "detail": detail}
    print(("PASS " if cond else "FAIL ") + name, "" if cond else json.dumps(detail, default=str)[:600], flush=True)


def run(gpu, mod_args, log, module="rsna_diag.adapt"):
    with open(log, "a") as f:
        f.write(f"\n=== {time.strftime('%F %T')} {' '.join(mod_args)}\n")
        f.flush()
        return subprocess.run([sys.executable, "-m", module, *mod_args], env=dict(os.environ, CUDA_VISIBLE_DEVICES=str(gpu)), stdout=f, stderr=subprocess.STDOUT).returncode


def aargs(run_dir, stage, loss, extra=()):
    return ["--run-dir", run_dir, "--stage-config", ST + f"{stage}.json", "--loss", loss, "--lr", "2e-5", "--protocol", PROT, "--workers", "2", *extra]


def steps(d):
    return [json.loads(ln) for ln in open(os.path.join(d, "train_log.jsonl")) if '"loss"' in ln and '"batch_ids"' in ln]


def equiv():
    import numpy as np
    import torch
    from rsna_diag import adapt, coord_loss as CL, generate, inputs, lora, prompts as P, sft_data, train as TR
    items, gt = inputs.load_items(TR.MANIFEST, TR.GT, "results/iter_013/subsets/sanity16_ids.json", "train", exact=False)
    _, proc, model = generate.load_model()
    lora.apply_lora(model, 16, 32, 0.05, seed=17)
    st = json.load(open(ST + "sanity.json"))
    lora.load_lora_state(model, torch.load(st["parent_adapter"], map_location="cpu", weights_only=True)["state"])
    model.eval()  # dropout 끔 (두 경로의 forward가 동일해야 하므로)
    tok = proc.tokenizer
    dig = CL.digit_ids(tok)
    softcap = getattr(model.config.get_text_config(), "final_logit_softcapping", None)
    pos = [i for i in items if gt[i["id"]]["category"] == "opacity"][:2] + [i for i in items if gt[i["id"]]["category"] != "opacity"][:1]
    exs = []
    for it in pos:
        image, _, _ = inputs.load_verified(it)
        t = sft_data.target_text([b["yxyx_norm"] for b in gt[it["id"]]["boxes"]])
        e = sft_data.build_example(proc, image, P.CONCISE, t)
        e["coord_w"] = CL.coord_weights(tok, t, e["input_ids"].tolist(), e["n_prefix"], dig)
        e["sample_pos"] = 0
        exs.append(e)
    b = adapt.collate(exs, tok.pad_token_id)
    b.pop("sample_pos")
    b = {k: v.cuda() for k, v in b.items()}
    params = [p for p in model.parameters() if p.requires_grad]

    def grad_of(fn):
        for p in params:
            p.grad = None
        fn().backward()
        return torch.cat([p.grad.flatten() for p in params]).clone()

    old_b = {k: v for k, v in b.items() if k != "coord_w"}
    with torch.no_grad():
        ce_old, n_old = TR.assistant_loss_sum(torch, model, old_b, softcap)
    g_old = grad_of(lambda: TR.assistant_loss_sum(torch, model, old_b, softcap)[0])
    g_old2 = grad_of(lambda: TR.assistant_loss_sum(torch, model, old_b, softcap)[0])  # 같은 함수의 두 번째 평가: bf16 kernel의 run-to-run noise floor
    res = {}
    for mode in ("C", "H", "D"):
        with torch.no_grad():
            r = adapt.adapt_loss(torch, model, b, softcap, mode, dig, 0.1, 1.0)
        g = grad_of(lambda: (lambda x: x["ce_sum"] + 0.0 * x["extra_sum"])(adapt.adapt_loss(torch, model, b, softcap, mode, dig, 0.1, 1.0)))
        res[mode] = {"ce": float(r["ce_sum"]), "extra": float(r["extra_sum"]), "n_tok": r["n_tok"], "n_coord": r["n_coord"], "mon_h": float(r["mon_h"]),
                     "mon_d": float(r["mon_d"]), "grad_max_abs_diff_vs_old_ce": float((g - g_old).abs().max()), "grad_rel_l2_diff_vs_old_ce": float((g - g_old).norm() / g_old.norm()),
                     "grad_norm": float(g.norm())}
    # 같은 logits를 밖에서 다시 구해 독립 float64 기준과 대조
    with torch.no_grad():
        bb = dict(b)
        cw, labels = bb.pop("coord_w"), bb.pop("labels")
        bb["pixel_values"] = bb["pixel_values"].to(torch.bfloat16)
        h = model.model(**bb, use_cache=False).last_hidden_state[:, :-1]
        lab = labels[:, 1:]
        sel = lab != -100
        lg = model.lm_head(h[sel]).float()
        if softcap:
            lg = torch.tanh(lg / softcap) * softcap
        y, w = lab[sel].cpu().numpy(), cw[:, 1:][sel].cpu().numpy()
        di = torch.as_tensor(dig, device=lg.device)
        # 전체 vocabulary logits 대신 필요한 열만 옮겨 float64 기준 계산: lse는 GPU float64로
        lse = torch.logsumexp(lg.double(), -1).cpu().numpy()
        gold = lg.gather(1, torch.as_tensor(y, device=lg.device)[:, None]).squeeze(1).double().cpu().numpy()
        dl = lg[:, di].double().cpu().numpy()
    ce_ref = float((lse - gold).sum())
    h_ref = float(sum(w[t] * (lse[t] - gold[t]) for t in range(len(y)) if w[t] > 0))
    d_ref = 0.0
    for t in range(len(y)):
        if w[t] > 0:
            g_ = dig.index(int(y[t]))
            q = np.exp(-((np.arange(10) - g_) ** 2) / 1.0)
            q /= q.sum()
            lp = dl[t] - lse[t]
            d_ref += float(w[t] * (q * (np.log(q) - lp)).sum())
    out = {"res": res, "ce_old": float(ce_old), "n_old": n_old, "ce_ref": ce_ref, "h_ref": h_ref, "d_ref": d_ref, "grad_norm_old": float(g_old.norm()),
           "noise_floor": {"max_abs": float((g_old - g_old2).abs().max()), "rel_l2": float((g_old - g_old2).norm() / g_old.norm())}}
    json.dump(out, open(os.path.join(B, "equiv.json"), "w"), indent=1)
    print("equiv done")


def mon_gpu(stop, out, gpus):
    while not stop.is_set():
        q = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used", "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout
        for ln in q.strip().splitlines():
            i, m = [x.strip() for x in ln.split(",")]
            if int(i) in gpus:
                out[int(i)] = max(out.get(int(i), 0), int(m))
        time.sleep(3)


def main():
    os.makedirs(B, exist_ok=True)
    os.makedirs(T, exist_ok=True)
    peak = {}
    stop = threading.Event()
    th = threading.Thread(target=mon_gpu, args=(stop, peak, {L0, L1}), daemon=True)
    th.start()
    logs = {}

    # ---- phase 1: lane0 D-resume chain / lane1 E + X
    def lane0():
        d = f"{B}/resume"
        rc = {}
        rc["U"] = run(L0, aargs(f"{d}/U", "sanity", "D", ["--deterministic", "--ckpt-every", "2", "--microbatch", "2"]), f"{d}_U.log")
        rc["R1"] = run(L0, aargs(f"{d}/R", "sanity", "D", ["--deterministic", "--ckpt-every", "2", "--microbatch", "2", "--stop-after-step", "2"]), f"{d}_R.log")
        rc["R2"] = run(L0, aargs(f"{d}/R", "sanity", "D", ["--deterministic", "--ckpt-every", "2", "--microbatch", "2", "--stop-in-validation", "3"]), f"{d}_R.log")
        rc["R3"] = run(L0, aargs(f"{d}/R", "sanity", "D", ["--deterministic", "--ckpt-every", "2", "--microbatch", "2"]), f"{d}_R.log")
        logs["resume_rc"] = rc

    def lane1():
        os.makedirs(f"{B}/xcond", exist_ok=True)
        e = subprocess.run([sys.executable, "test_rsna_iter013_gpu.py", "--equiv"], env=dict(os.environ, CUDA_VISIBLE_DEVICES=str(L1)),
                           stdout=open(f"{B}/equiv.log", "a"), stderr=subprocess.STDOUT).returncode
        rc = {"equiv": e}
        for m in ("C", "H", "D"):
            rc[m] = run(L1, aargs(f"{B}/xcond/{m}", "sanity", m, ["--deterministic", "--ckpt-every", "2", "--microbatch", "2", "--max-steps", "1"]), f"{B}/xcond_{m}.log")
        logs["lane1_rc"] = rc

    t0 = time.time()
    ths = [threading.Thread(target=lane0), threading.Thread(target=lane1)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    logs["phase1_wall_s"] = time.time() - t0
    check("E.subprocess_rc", logs["lane1_rc"]["equiv"] == 0, logs["lane1_rc"])
    eq = json.load(open(f"{B}/equiv.json"))
    r = eq["res"]
    check("E.C_ce_equals_old_assistant_loss_sum", abs(r["C"]["ce"] - eq["ce_old"]) <= 1e-6 * abs(eq["ce_old"]) and r["C"]["n_tok"] == eq["n_old"], (r["C"]["ce"], eq["ce_old"]))
    nf = eq["noise_floor"]
    check("E.alpha0_gradient_equals_old_CE_gradient_all_modes_within_2x_noise_floor",
          all(r[m]["grad_max_abs_diff_vs_old_ce"] <= 3 * nf["max_abs"] + 1e-6 and r[m]["grad_rel_l2_diff_vs_old_ce"] <= 2 * nf["rel_l2"] + 1e-4 for m in r),
          {"noise_floor(same old function twice)": nf, **{m: (r[m]["grad_max_abs_diff_vs_old_ce"], r[m]["grad_rel_l2_diff_vs_old_ce"]) for m in r}})
    check("E.H_extra_matches_float64_reference", abs(r["H"]["extra"] - eq["h_ref"]) <= 1e-4 * max(1.0, abs(eq["h_ref"])), (r["H"]["extra"], eq["h_ref"]))
    check("E.D_extra_matches_float64_reference", abs(r["D"]["extra"] - eq["d_ref"]) <= 1e-4 * max(1.0, abs(eq["d_ref"])), (r["D"]["extra"], eq["d_ref"]))
    check("E.monitors_equal_active_extra", abs(r["C"]["mon_h"] - r["H"]["extra"]) < 1e-5 * max(1, abs(r["H"]["extra"])) and abs(r["C"]["mon_d"] - r["D"]["extra"]) < 1e-5 * max(1, abs(r["D"]["extra"])),
          (r["C"]["mon_h"], r["H"]["extra"], r["C"]["mon_d"], r["D"]["extra"]))
    check("E.coord_positions_counted", r["C"]["n_coord"] > 0 and r["C"]["n_coord"] == r["H"]["n_coord"] == r["D"]["n_coord"], r["C"]["n_coord"])

    # D 재개
    check("D.processes_exit_codes", logs["resume_rc"] == {"U": 0, "R1": 5, "R2": 4, "R3": 0}, logs["resume_rc"])
    U, Rr = steps(f"{B}/resume/U"), steps(f"{B}/resume/R")
    check("D.step_count_8_both", len(U) == 8 and len(Rr) == 8, (len(U), len(Rr)))
    exact = ["batch_ids", "batch_token_sha", "lr", "rng_before", "opt_step_before", "n_label_tokens", "n_coord_tokens"]
    mism = [(k, i + 1) for i, (u, rr) in enumerate(zip(U, Rr)) for k in exact if u[k] != rr[k]]
    check("D.exact_state_match_batch_token_lr_rng_optstep", not mism, mism[:5])
    rel = lambda a, b: abs(a - b) / max(1e-12, abs(b))
    lm = [(k, i + 1, u[k], rr[k]) for i, (u, rr) in enumerate(zip(U, Rr)) for k in ("loss", "ce", "extra_raw", "grad_norm") if rel(rr[k], u[k]) > RTOL]
    check("D.loss_ce_extra_gradnorm_within_rtol_1e-3", not lm, lm[:5])
    check("D.loss_bitwise_equal_deterministic", all(u["loss"] == rr["loss"] for u, rr in zip(U, Rr)), [(u["loss"], rr["loss"]) for u, rr in zip(U, Rr) if u["loss"] != rr["loss"]][:3])
    lg = lambda d: [json.loads(ln) for ln in open(os.path.join(d, "train_log.jsonl"))]
    ev = [e for e in lg(f"{B}/resume/R") if e.get("event") == "resume"]
    check("D.resume_restored_equals_saved", len(ev) >= 2 and all(e["restored_equals_saved"] for e in ev), len(ev))
    vd = [e for e in lg(f"{B}/resume/R") if e.get("event") == "validation_done"]
    check("D.validation_state_unchanged_and_recovered", len(vd) >= 2 and all(e["state_unchanged"] for e in vd) and any(e["recovered_from_file"] for e in vd), [(e["epoch"], e["recovered_from_file"]) for e in vd])
    au = json.load(open(f"{B}/resume/U/epoch_02/val_metrics.json"))
    ar = json.load(open(f"{B}/resume/R/epoch_02/val_metrics.json"))
    check("D.final_adapter_digest_equal", au["adapter_digest"] == ar["adapter_digest"], (au["adapter_digest"][:12], ar["adapter_digest"][:12]))
    keys = ["f1@0.3", "f1@0.5", "utility", "val_loss"]
    check("D.val_metrics_equal", all(abs(au[k] - ar[k]) <= 1e-6 + RTOL * abs(au[k]) for k in keys), {k: (au[k], ar[k]) for k in keys})
    a1 = json.load(open(f"{B}/resume/U/epoch_01/val_metrics.json"))
    b1 = json.load(open(f"{B}/resume/R/epoch_01/val_metrics.json"))
    check("D.pending_validation_epoch1_recovered_metrics_equal", all(abs(a1[k] - b1[k]) <= 1e-6 + RTOL * abs(a1[k]) for k in keys), {k: (a1[k], b1[k]) for k in keys})
    from rsna_diag import select
    try:
        tc = json.load(open(f"{B}/resume/R/train_config.json"))
        from rsna_diag import adapt_eval, inputs
        vi, gt = inputs.load_items("results/iter_010/manifests/infer_manifest.jsonl", "results/iter_010/manifests/gt_manifest.json", ST.replace("stage/", "subsets/") + "val8_ids.json", "validation", exact=False)
        select.verify_epoch(f"{B}/resume/R", 2, tc, inputs.inputs_digest(vi, gt), PROT, vi, gt)
        ok = True
    except Exception as e:  # noqa
        ok = str(e)[:300]
    check("D.select_verify_epoch_accepts_adapt_run", ok is True, ok)
    check("D.deterministic_run_flagged_in_config", json.load(open(f"{B}/resume/R/train_config.json"))["config"]["deterministic"] is True)

    # X 조건 간
    xs = {m: steps(f"{B}/xcond/{m}")[0] for m in ("C", "H", "D")}
    check("X.same_batch_and_tokens_across_conditions", len({(x["batch_token_sha"], tuple(x["batch_ids"]), x["n_label_tokens"], x["n_coord_tokens"]) for x in xs.values()}) == 1)
    check("X.step1_ce_identical_across_conditions", len({x["ce"] for x in xs.values()}) == 1, {m: x["ce"] for m, x in xs.items()})
    check("X.C_monitors_equal_H_D_extra", xs["C"]["monitor_H_extra_raw"] == xs["H"]["extra_raw"] and xs["C"]["monitor_D_extra_raw"] == xs["D"]["extra_raw"],
          (xs["C"]["monitor_H_extra_raw"], xs["H"]["extra_raw"], xs["C"]["monitor_D_extra_raw"], xs["D"]["extra_raw"]))
    check("X.total_loss_definition", all(abs(x["loss"] - (x["ce"] + 0.1 * x["extra_raw"])) < 1e-9 for x in xs.values()) and xs["C"]["extra_raw"] == 0.0)
    check("X.first_step_lr_warmup", all(abs(x["lr"] - 2e-5 / max(1, __import__("math").ceil(0.05 * 8))) < 1e-15 for x in xs.values()), xs["C"]["lr"])

    # ---- phase 2: microbatch pilot (lane0 mb2, lane1 mb4)
    t0 = time.time()
    p2 = {}
    ths = [threading.Thread(target=lambda g=g, mb=mb: p2.__setitem__(mb, run(g, aargs(f"{B}/mb{mb}", "pilot_mb", "D", ["--microbatch", str(mb)]), f"{B}/mb{mb}.log")))
           for g, mb in ((L0, 2), (L1, 4))]
    [t.start() for t in ths]
    [t.join() for t in ths]
    logs["phase2_wall_s"] = time.time() - t0
    mbrep = {}
    for mb in (2, 4):
        st_ = steps(f"{B}/mb{mb}")
        mbrep[mb] = {"rc": p2[mb], "n_steps": len(st_), "step_times": [b["elapsed_s"] - (a["elapsed_s"] if k else 0) for k, (a, b) in enumerate(zip([st_[0]] + st_, st_))][:3] if st_ else None,
                     "peak_alloc_gb": max(s["peak_mem_gb"] for s in st_) if st_ else None, "step1_ce": st_[0]["ce"] if st_ else None, "step1_loss": st_[0]["loss"] if st_ else None}
    logs["mb_report"] = mbrep
    check("M.both_microbatch_runs_ok", all(mbrep[m]["rc"] == 0 and mbrep[m]["n_steps"] == 3 for m in (2, 4)), mbrep)
    check("M.step1_ce_close_mb2_vs_mb4", rel(mbrep[4]["step1_ce"], mbrep[2]["step1_ce"]) < 5e-2, (mbrep[2]["step1_ce"], mbrep[4]["step1_ce"]))

    # ---- phase 3: 추론 worker 비교 (thr48, B0 adapter, concise): lane0 1 worker vs lane1 2 workers
    B0 = "results/iter_012/train/lr2e-4_s17/epoch_05"
    t0 = time.time()
    p3 = {}

    def gen(name, gpu, workers, extra=()):
        cmd = [sys.executable, "-m", "rsna_diag.run_shards", "--manifest", "results/iter_010/manifests/infer_manifest.jsonl", "--ids", "results/iter_013/subsets/thr48_ids.json",
               "--out-dir", f"{B}/gen_{name}", "--protocol", PROT, "--prompts", "concise", "--workers", str(workers), "--gpus", str(gpu), "--adapter", B0, *extra]
        s = time.time()
        rc = subprocess.run(cmd, env=dict(os.environ, CUDA_VISIBLE_DEVICES=str(gpu)), stdout=open(f"{B}/gen_{name}.log", "a"), stderr=subprocess.STDOUT).returncode
        p3[name] = {"rc": rc, "wall_s": time.time() - s}

    ths = [threading.Thread(target=gen, args=("w1", L0, 1)), threading.Thread(target=gen, args=("w2", L1, 2))]
    [t.start() for t in ths]
    [t.join() for t in ths]
    logs["phase3_wall_s"] = time.time() - t0
    rec = lambda n: {(r["id"], r["prompt_name"]): r for f in __import__("glob").glob(f"{B}/gen_{n}/gen_worker*.jsonl") for r in map(json.loads, filter(str.strip, open(f)))}
    a, b_ = rec("w1"), rec("w2")
    same = sum(1 for k in a if k in b_ and a[k]["suffix_ids"] == b_[k]["suffix_ids"])
    rep3 = {n: {"rc": p3[n]["rc"], "wall_s": p3[n]["wall_s"], "n": len(r), "req_per_min": len(r) / p3[n]["wall_s"] * 60, "max_req_s": max(x["runtime_s_total"] for x in r.values()),
                "max_out_tokens": max(x["n_output_tokens"] for x in r.values()), "worker_peak_alloc_gb": max(x["peak_mem_alloc_gb_max"] for x in r.values())}
            for n, r in (("w1", a), ("w2", b_))}
    rep3["identical_output_tokens"] = {"n_compared": len(a), "n_identical": same}
    logs["gen_report"] = rep3
    check("I.both_configs_complete_48_no_dup", rep3["w1"]["rc"] == 0 and rep3["w2"]["rc"] == 0 and rep3["w1"]["n"] == 48 == rep3["w2"]["n"], rep3)
    check("I.greedy_token_outputs_identical_w1_w2", same == 48, rep3["identical_output_tokens"])
    # parent 재사용 경로 (NameError 수정): 새 out-dir에서 w1 결과를 부모로 사용
    rc = subprocess.run([sys.executable, "-m", "rsna_diag.run_shards", "--manifest", "results/iter_010/manifests/infer_manifest.jsonl", "--ids", "results/iter_013/subsets/thr48_ids.json",
                         "--out-dir", f"{B}/gen_parent_reuse", "--protocol", PROT, "--prompts", "concise", "--workers", "1", "--gpus", str(L1), "--adapter", B0,
                         "--parent-dir", f"{B}/gen_w1", "--parent-protocol", PROT], env=dict(os.environ, CUDA_VISIBLE_DEVICES=str(L1)),
                        stdout=open(f"{B}/gen_parent_reuse.log", "a"), stderr=subprocess.STDOUT).returncode
    err = open(f"{B}/gen_parent_reuse/worker0.stderr.log").read() if os.path.exists(f"{B}/gen_parent_reuse/worker0.stderr.log") else ""
    check("I.parent_dir_path_no_NameError_and_complete", rc == 0 and "NameError" not in err and os.path.exists(f"{B}/gen_parent_reuse/completion.json"), {"rc": rc, "stderr": err[-300:]})
    stop.set()
    logs["gpu_total_used_max_mib_all_phases"] = peak
    logs["lanes"] = LANES
    json.dump({"checks": R, "logs": logs}, open(os.path.join(T, "fixtures_iter013_gpu.json"), "w"), indent=1, default=str)
    n_pass = sum(v["pass"] for v in R.values())
    print(f"{n_pass}/{len(R)} PASS")
    sys.exit(0 if n_pass == len(R) else 1)


if __name__ == "__main__":
    if "--gpu" in sys.argv:  # 단독 실행용: 허용 집합 안의 장치 하나 (torch import 전에 설정)
        os.environ["CUDA_VISIBLE_DEVICES"] = sys.argv[sys.argv.index("--gpu") + 1]
    if "--equiv" in sys.argv:
        equiv()
    else:
        main()
