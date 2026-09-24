"""iter_010 CPU/소형 fixture 검증 (실행기·gate·LoRA 수식·baseline). 실행: python test_rsna_iter010.py
-> results/iter_010/tests/fixtures_iter010.json (모든 항목 pass여야 exit 0). 실제 모델 GPU 검증은 test_rsna_iter010_gpu.py.
"""
import json
import multiprocessing as mp
import os
import sys
import tempfile
import zipfile

import numpy as np

from rsna_diag import baselines, dicom_min, generate, lock_protocol, prompts as P, queue_lock, rsna_data as rd, run_shards, sft_data, sft_eval, train

R = {}


def check(name, cond, detail=None):
    R[name] = {"pass": bool(cond), "detail": detail}
    print(("PASS " if cond else "FAIL ") + name, detail if not cond else "")


# ---- A. DICOM 표시 gate ----
std = {"Rows": 1024, "Columns": 1024, "BitsAllocated": 8, "BitsStored": 8, "HighBit": 7, "PixelRepresentation": 0,
       "PhotometricInterpretation": "MONOCHROME2", "SamplesPerPixel": 1, "TransferSyntaxUID": dicom_min.JPEG_BASELINE}
check("dicom_standard_ok", dicom_min.display_problems(std) == [])
check("dicom_identity_rescale_ok", dicom_min.display_problems(dict(std, RescaleSlope="1", RescaleIntercept="0", NumberOfFrames="1")) == [])
for nm, upd in [("window_center", {"WindowCenter": "40"}), ("window_width", {"WindowWidth": "400"}), ("slope", {"RescaleSlope": "2"}),
                ("intercept", {"RescaleIntercept": "-1024"}), ("frames", {"NumberOfFrames": "2"}), ("voi_lut_seq", {"VOILUTSequence": "x"}),
                ("voi_func", {"VOILUTFunction": "SIGMOID"}), ("mono1", {"PhotometricInterpretation": "MONOCHROME1"}),
                ("bits12", {"BitsStored": 12}), ("signed", {"PixelRepresentation": 1}), ("pres_lut", {"PresentationLUTShape": "INVERSE"}),
                ("size", {"Rows": 512}), ("ts", {"TransferSyntaxUID": "1.2.840.10008.1.2.1"})]:
    check(f"dicom_gate_rejects_{nm}", len(dicom_min.display_problems(dict(std, **upd))) >= 1)
ZIP = "results/iter_009/source/raw/pneumonia-challenge-dataset-adjudicated-kaggle_2018.zip"
rz = rd.RsnaZip(ZIP)
sample = sorted(rz.members)[:5]
probs = [dicom_min.display_problems(dicom_min.parse(rz.read(s))[0]) for s in sample]
check("dicom_real_samples_pass_gate", all(p == [] for p in probs), probs)
meta, arr = dicom_min.read_pixels(rz.read(sample[0]))
check("dicom_real_decoded_uint8_1024", arr.shape == (1024, 1024) and arr.dtype == np.uint8, [arr.shape, str(arr.dtype)])

# ---- B. lock / claim (flock) ----
import subprocess
import time


def _hold(args):
    path, tag = args
    lk, prev, rec = queue_lock.try_lock(path, queue_lock.my_info(tag=tag))
    if lk is None:
        return (0, 0)
    time.sleep(1.5)
    lk.release()
    return (1, int(rec))


DEAD = {"pid": 4194000, "start": 12345, "host": __import__("socket").gethostname(), "ts": 0}
with tempfile.TemporaryDirectory() as td:
    p = os.path.join(td, "a.claim")
    me = queue_lock.my_info()
    l1, prev1, rec1 = queue_lock.try_lock(p, me)
    l2, own, _ = queue_lock.try_lock(p, queue_lock.my_info(other=1))
    check("claim_second_acquire_denied_while_owner_alive", l1 is not None and l2 is None and own["pid"] == os.getpid() and not rec1)
    l1.release()
    l3, prev3, rec3 = queue_lock.try_lock(p, me)
    check("released_lock_reacquirable_not_counted_as_reclaim", l3 is not None and not rec3)
    l3.release()
    # 소유 프로세스가 (release 없이) 죽으면 커널이 lock을 놓고, 다음 소유자가 이전 소유자 정보와 함께 회수한다
    holder = subprocess.Popen([sys.executable, "-c",
                               "import sys,time;from rsna_diag import queue_lock as q;l,_,_=q.try_lock(sys.argv[1],q.my_info(tag='holder'));"
                               "print('held' if l else 'fail',flush=True);time.sleep(60)", p], stdout=subprocess.PIPE, text=True)
    held = holder.stdout.readline().strip()
    l4, own4, _ = queue_lock.try_lock(p, me)
    check("live_other_process_lock_not_stolen", held == "held" and l4 is None and own4["tag"] == "holder" and own4["pid"] == holder.pid, [held, own4])
    holder.kill()
    holder.wait()
    l5, prev5, rec5 = queue_lock.try_lock(p, me)
    check("killed_owner_claim_reclaimed_with_prev_info", l5 is not None and rec5 and prev5["pid"] == holder.pid and prev5["tag"] == "holder", [rec5, prev5])
    l5.release()
    # 경쟁: 8 프로세스가 같은 새 claim / 죽은 소유자 정보가 남은 claim (lock은 아무도 안 잡음)
    with mp.Pool(8) as pool:
        r1 = pool.map(_hold, [(os.path.join(td, "n.claim"), i) for i in range(8)], chunksize=1)
        json.dump(DEAD, open(os.path.join(td, "d.claim"), "w"))
        r2 = pool.map(_hold, [(os.path.join(td, "d.claim"), i) for i in range(8)], chunksize=1)
    check("claim_race_exactly_one_winner_new", sum(r[0] for r in r1) == 1, r1)
    check("claim_race_exactly_one_winner_reclaim_dead_info", sum(r[0] for r in r2) == 1 and sum(r[1] for r in r2) == 1, r2)

# ---- C. 재개 검증 (완료 요청 포함) ----
prompts_used = {"concise": P.CONCISE}
env = {"model_id": "m", "model_revision": generate.MODEL_REVISION, "dtype": "bf16", "transformers": "t", "torch": "x",
       "preprocess": generate.PREPROC_VERSION, "chat_template_sha256": "c", "eos_token_id": [1, 106], "do_pan_and_scan": False, "image_size": "s"}
cdig, _ = generate.config_digest(env, prompts_used)
items = [{"id": f"a{k}", "split": "validation", "image": f"img{k}", "file_sha256": f"f{k}"} for k in range(3)]
pd = P.digest(P.CONCISE)


def mk(k, adapter=None, split="validation", **over):
    it = items[k]
    r = {"id": it["id"], "prompt_name": "concise", "prompt_sha256": pd, "input_pixel_sha256": f"px{k}", "image_file_sha256": f"f{k}",
         "request_id": generate.request_id(generate.MODEL_REVISION, adapter, split, it["id"], pd), "config_digest": cdig,
         "adapter_digest": adapter, "protocol_digest": "PD"}
    r.update(over)
    return r


pxf = lambda path: "px" + path[3:]
V = lambda files, adapter=None, **kw: generate.validate_existing(files, items, ["concise"], prompts_used, cdig, adapter, kw.get("pdig", "PD"), kw.get("px", pxf))


def raises(fn):
    try:
        fn()
    except generate.RunError as e:
        return str(e)
    return None


check("resume_valid_records_accepted", len(V({"w0": [mk(0), mk(1)], "w1": [mk(2)]})) == 3)
check("resume_duplicate_across_files_rejected_even_if_identical", raises(lambda: V({"w0": [mk(0)], "w1": [mk(0)]})) is not None)
check("resume_duplicate_within_file_rejected", raises(lambda: V({"w0": [mk(0), mk(0)]})) is not None)
check("resume_config_digest_mismatch_rejected", raises(lambda: V({"w0": [mk(0, config_digest="zzz")]})) is not None)
check("resume_protocol_mismatch_rejected", raises(lambda: V({"w0": [mk(0)]}, pdig="OTHER")) is not None)
check("resume_adapter_mismatch_rejected", raises(lambda: V({"w0": [mk(0, adapter="AD")]}, adapter=None)) is not None)
check("resume_base_record_under_adapter_run_rejected", raises(lambda: V({"w0": [mk(0)]}, adapter="AD")) is not None)
check("resume_split_mismatch_rejected", raises(lambda: V({"w0": [mk(0, split="confirm")]})) is not None)
check("resume_changed_input_rejected_for_completed_request", raises(lambda: V({"w0": [mk(0)]}, px=lambda p: "CHANGED")) is not None)
check("resume_unexpected_id_rejected", raises(lambda: V({"w0": [dict(mk(0), id="zz")]})) is not None)
check("resume_unexpected_prompt_rejected", raises(lambda: V({"w0": [dict(mk(0), prompt_name="official_long")]})) is not None)
check("resume_prompt_text_change_rejected", raises(lambda: V({"w0": [mk(0, prompt_sha256="x")]})) is not None)
check("request_id_includes_adapter_split_prompt",
      len({generate.request_id("r", a, s, "i", p) for a in (None, "A") for s in ("s", "t") for p in ("p", "q")}) == 8)

# ---- D. completion 대조 ----
with tempfile.TemporaryDirectory() as td:
    for fn, ks in (("gen_worker0.jsonl", [0, 1]), ("gen_worker1.jsonl", [2])):
        open(os.path.join(td, fn), "w").write("".join(json.dumps(mk(k)) + "\n" for k in ks))
    comp, rep = run_shards.finalize(td, items, ["concise"], prompts_used, None, "PD")
    check("finalize_complete_when_expected_equals_actual", comp and rep["n_missing"] == 0)
    open(os.path.join(td, "gen_worker1.jsonl"), "w").write("")
    comp, rep = run_shards.finalize(td, items, ["concise"], prompts_used, None, "PD")
    check("finalize_incomplete_on_missing", not comp and rep["n_missing"] == 1)
    open(os.path.join(td, "gen_worker1.jsonl"), "w").write(json.dumps(mk(2)) + "\n" + json.dumps(mk(0)) + "\n")
    comp, rep = run_shards.finalize(td, items, ["concise"], prompts_used, None, "PD")
    check("finalize_incomplete_on_duplicate", not comp and rep["n_duplicate"] == 1)
    open(os.path.join(td, "gen_worker1.jsonl"), "w").write(json.dumps(dict(mk(2), id="zz")) + "\n")
    comp, rep = run_shards.finalize(td, items, ["concise"], prompts_used, None, "PD")
    check("finalize_incomplete_on_extra", not comp and rep["n_extra"] == 1)

# ---- E. protocol lock ----
with tempfile.TemporaryDirectory() as td:
    f = os.path.join(td, "x.txt")
    open(f, "w").write("a")
    out = os.path.join(td, "proto.json")
    cur = lock_protocol.current(extra=[f])
    json.dump({"locked": cur}, open(out, "w"), default=str)
    d1 = lock_protocol.verify(out)
    check("protocol_verify_ok_returns_digest", isinstance(d1, str) and len(d1) == 64)
    open(f, "w").write("b")
    try:
        lock_protocol.verify(out)
        check("protocol_detects_changed_file", False)
    except RuntimeError:
        check("protocol_detects_changed_file", True)
    try:
        lock_protocol.verify(os.path.join(td, "missing.json"))
        check("protocol_missing_path_fails", False)
    except RuntimeError:
        check("protocol_missing_path_fails", True)
    open(f, "w").write("a")
    js = json.load(open(out))
    js["locked"]["generation_config_digest"] = "0" * 64
    json.dump(js, open(out, "w"))
    try:
        lock_protocol.verify(out)
        check("protocol_detects_config_digest_change", False)
    except RuntimeError:
        check("protocol_detects_config_digest_change", True)

# ---- F. target / collate (processor 불필요) ----
bx = [[100.4, 500.5, 300.0, 700.0], [100.0, 100.0, 200.0, 200.0]]
tt = json.loads(sft_data.target_text(bx))
check("target_sorted_by_center_x_then_y_integer", [t["box_2d"] for t in tt] == [[100, 100, 200, 200], [100, 501, 300, 700]] and tt[0]["label"] == "pulmonary opacity", tt)
check("target_empty_is_empty_list", sft_data.target_text([]) == "[]")
try:
    sft_data.target_text([[10.2, 10.0, 10.3, 20.0]])
    check("target_rounding_invalid_raises", False)
except ValueError:
    check("target_rounding_invalid_raises", True)
import torch
e1 = {"input_ids": torch.tensor([5, 6, 7]), "attention_mask": torch.ones(3, dtype=torch.long), "labels": torch.tensor([-100, 6, 7]),
      "pixel_values": torch.zeros(1, 3, 2, 2), "token_type_ids": torch.tensor([0, 1, 0])}
e2 = {"input_ids": torch.tensor([5, 8]), "attention_mask": torch.ones(2, dtype=torch.long), "labels": torch.tensor([-100, 8]),
      "pixel_values": torch.zeros(1, 3, 2, 2), "token_type_ids": torch.tensor([0, 0])}
cb = sft_data.collate([e1, e2], pad_id=0)
check("collate_right_pad_mask_and_labels", cb["input_ids"].tolist() == [[5, 6, 7], [5, 8, 0]] and cb["attention_mask"].tolist() == [[1, 1, 1], [1, 1, 0]]
      and cb["labels"].tolist() == [[-100, 6, 7], [-100, 8, -100]] and cb["token_type_ids"].tolist() == [[0, 1, 0], [0, 0, 0]] and cb["pixel_values"].shape[0] == 2)

# ---- G. LoRA 수식 / gradient / 재개 (소형 선형층) ----
from rsna_diag import lora as L
torch.manual_seed(0)
base = torch.nn.Linear(24, 16, bias=False).to(torch.bfloat16)
base.weight.requires_grad_(False)
lin = L.LoRALinear(base, r=4, alpha=8, dropout=0.0)
x = torch.randn(5, 24, dtype=torch.bfloat16)
check("lora_initial_identity_exact", torch.equal(lin(x), base(x)))
check("lora_only_lora_trainable", not base.weight.requires_grad and lin.lora_A.requires_grad and lin.lora_B.requires_grad)
with torch.no_grad():
    lin.lora_B.copy_(torch.randn_like(lin.lora_B))
xf = x.double()
A64, B64, W64 = lin.lora_A.detach().double().requires_grad_(), lin.lora_B.detach().double().requires_grad_(), base.weight.detach().double()
ref = xf @ W64.t() + (8 / 4) * (xf @ A64.t()) @ B64.t()
tgt = torch.randn(5, 16, dtype=torch.float64)
(ref * tgt).sum().backward()
y = lin(x)
(y.float() * tgt.float()).sum().backward()
check("lora_forward_matches_fp64_reference", torch.allclose(y.double(), ref, atol=0.05, rtol=0.02), float((y.double() - ref).abs().max().item()))
relA = float((lin.lora_A.grad.double() - A64.grad).norm() / A64.grad.norm())
relB = float((lin.lora_B.grad.double() - B64.grad).norm() / B64.grad.norm())
check("lora_bf16_path_grad_close_to_fp64_reference_relative_norm", relA < 0.02 and relB < 0.02 and base.weight.grad is None, [relA, relB])
torch.manual_seed(3)
b32 = torch.nn.Linear(24, 16, bias=False)
l32 = L.LoRALinear(b32, r=4, alpha=8, dropout=0.0)
with torch.no_grad():
    l32.lora_B.copy_(torch.randn_like(l32.lora_B))
x32 = torch.randn(5, 24)
A2, B2 = l32.lora_A.detach().double().requires_grad_(), l32.lora_B.detach().double().requires_grad_()
ref2 = x32.double() @ b32.weight.detach().double().t() + 2.0 * (x32.double() @ A2.t()) @ B2.t()
t2 = torch.randn(5, 16, dtype=torch.float64)
(ref2 * t2).sum().backward()
(l32(x32) * t2.float()).sum().backward()
check("lora_fp32_grad_matches_fp64_reference_tight", torch.allclose(l32.lora_A.grad.double(), A2.grad, rtol=1e-4, atol=1e-4)
      and torch.allclose(l32.lora_B.grad.double(), B2.grad, rtol=1e-4, atol=1e-4),
      [float((l32.lora_A.grad.double() - A2.grad).abs().max()), float((l32.lora_B.grad.double() - B2.grad).abs().max())])
m = torch.nn.Sequential(L.LoRALinear(torch.nn.Linear(6, 6).to(torch.bfloat16), 2, 4, 0.1))
st = {"0.lora_A": m[0].lora_A.detach().clone(), "0.lora_B": torch.randn(6, 2)}
dg = L.state_digest(st)
L.load_lora_state(m, st)
check("adapter_reload_state_and_digest_roundtrip", L.state_digest(L.lora_state_dict(m)) == dg)
try:
    L.load_lora_state(m, {"0.lora_A": st["0.lora_A"]})
    check("adapter_reload_rejects_key_mismatch", False)
except ValueError:
    check("adapter_reload_rejects_key_mismatch", True)


def tiny_run(steps, save_at=None, resume=None):
    """소형 모델 + AdamW. resume={'state','opt','rng'}이면 그 지점에서 이어간다. dropout이 RNG를 쓴다."""
    torch.manual_seed(1)
    mod = L.LoRALinear(torch.nn.Linear(8, 8, bias=False).to(torch.bfloat16), 2, 4, 0.3)
    opt = torch.optim.AdamW([mod.lora_A, mod.lora_B], lr=1e-2, weight_decay=0.01)
    data = torch.randn(steps + 1, 4, 8, generator=torch.Generator().manual_seed(2)).to(torch.bfloat16)
    s0 = 0
    if resume:
        L.load_lora_state(mod, resume["state"])
        opt.load_state_dict(resume["opt"])
        torch.set_rng_state(resume["rng"])
        s0 = resume["step"]
    snap = None
    for s in range(s0, steps):
        loss = mod(data[s]).float().pow(2).mean() + 0.0 * mod.lora_B.sum()
        loss.backward()
        opt.step()
        opt.zero_grad()
        if save_at == s + 1:
            snap = {"state": L.lora_state_dict(mod), "opt": __import__("copy").deepcopy(opt.state_dict()), "rng": torch.get_rng_state(), "step": s + 1}
    return L.lora_state_dict(mod), snap


torch.manual_seed(1)
full, _ = tiny_run(10)
_, snap = tiny_run(10, save_at=5)
part, _ = tiny_run(10, resume=snap)
check("optimizer_rng_resume_matches_uninterrupted_tensors",
      all(torch.equal(full[k], part[k]) for k in full), {k: float((full[k] - part[k]).abs().max()) for k in full})

# ---- H. lr schedule ----
spe = 150
check("lr_warmup_start_peak_end", abs(train.lr_at(0, spe, 2e-4) - 2e-4 / 38) < 1e-12 and abs(train.lr_at(37, spe, 2e-4) - 2e-4) < 1e-12
      and train.lr_at(749, spe, 2e-4) < 1e-8, [train.lr_at(0, spe, 2e-4), train.lr_at(37, spe, 2e-4), train.lr_at(749, spe, 2e-4)])
check("lr_extension_phase_starts_at_0p1_peak_ends_zero", abs(train.lr_at(750, spe, 2e-4) - 2e-5) < 1e-9 and train.lr_at(1199, spe, 2e-4) < 1e-8)

# ---- I. baselines ----
b = [200.0, 300.0, 400.0, 600.0]
check("apply_box_identity", baselines.apply_box(b, (0, 0, 0, 1.0, 1.0)) == b)
check("apply_box_swap", baselines.apply_box(b, (1, 0, 0, 1.0, 1.0)) == [300.0, 200.0, 600.0, 400.0])
check("apply_box_scale_shift", baselines.apply_box([0.0, 0.0, 100.0, 100.0], (0, 75, 0, 0.5, 1.0)) == [100.0, 0.0, 150.0, 100.0])
check("apply_box_clip_to_canvas", baselines.apply_box([0.0, 0.0, 100.0, 100.0], (0, 0, -75, 1.0, 1.0)) == [0.0, 0.0, 100.0, 25.0])
check("apply_box_vanishes_outside_canvas", baselines.apply_box([0.0, 0.0, 100.0, 100.0], (0, -150, 0, 0.4, 0.4)) is None)
check("baseline_candidate_count_800", len(baselines.CANDIDATES) == 800)
preds = [{"status": "valid_nonempty", "boxes": [[400.0, 100.0, 500.0, 900.0]]} for _ in range(3)]
gts = [[[100.0, 400.0, 900.0, 500.0]] for _ in range(3)]
with mp.Pool(2) as pool:
    sel, _ = baselines.select_correction(preds, gts, pool)
check("correction_selects_known_swap_transform", sel["spec"] == [1, 0, 0, 1.0, 1.0] and sel["score"] == 1.0, sel["spec"])
preds0 = [{"status": "valid_nonempty", "boxes": g[0:1]} for g in gts]
with mp.Pool(2) as pool:
    sel0, _ = baselines.select_correction(preds0, gts, pool)
check("correction_tie_prefers_identity", sel0["spec"] == [0, 0, 0, 1.0, 1.0], sel0["spec"])
pr, nv = baselines.apply_pred({"status": "truncated", "boxes": [[1, 2, 3, 4]]}, (1, 0, 0, 1.0, 1.0))
check("correction_does_not_rescue_invalid_output", pr["status"] == "truncated" and nv == 0)
with mp.Pool(2) as pool:
    ps, pb = baselines.select_prior([[[0, 0, 500, 500]], [[0, 0, 500, 500], [600, 600, 900, 900]], [[600, 600, 900, 900]]], pool)
check("prior_picks_real_gt_set_with_max_mean_f1", ps["set"] == [[0, 0, 500, 500], [600, 600, 900, 900]] or ps["set"] == [[0, 0, 500, 500]] or ps["set"] == [[600, 600, 900, 900]], ps)

# ---- J. utility ----
gt_ = {"p": {"category": "opacity", "boxes": [{"yxyx_norm": [0, 0, 100, 100]}]}, "n": {"category": "normal", "boxes": []},
       "x": {"category": "not_normal_no_opacity", "boxes": []}}
pred_ = {"p": {"status": "valid_nonempty", "boxes": [[0, 0, 100, 100]]}, "n": {"status": "valid_empty", "boxes": []},
         "x": {"status": "valid_nonempty", "boxes": [[0, 0, 5, 5]]}}
sm = sft_eval.summarize(pred_, gt_, ["p", "n", "x"])
check("utility_hand_calc", abs(sm["utility"] - (0.5 * 1 + 0.25 * 1 + 0.25 * 0)) < 1e-12 and sm["neg_NoOpacity/NotNormal"]["extra_box"]["k"] == 1, sm["utility"])
pred_["n"] = {"status": "truncated", "boxes": []}
sm = sft_eval.summarize(pred_, gt_, ["p", "n", "x"])
check("format_failure_not_counted_as_empty_success", sm["neg_Normal"]["valid_empty"]["k"] == 0 and sm["neg_Normal"]["format_fail"]["k"] == 1)

OUT = sys.argv[1] if len(sys.argv) > 1 else "results/iter_010/tests"
os.makedirs(OUT, exist_ok=True)
json.dump(R, open(os.path.join(OUT, "fixtures_iter010.json"), "w"), indent=1)
n_fail = sum(1 for v in R.values() if not v["pass"])
print(f"{len(R) - n_fail}/{len(R)} pass")
sys.exit(1 if n_fail else 0)
