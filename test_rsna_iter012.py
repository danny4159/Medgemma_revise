"""iter_012 CPU 회귀·주입 검사. 실행: python test_rsna_iter012.py [OUT_DIR] -> OUT_DIR/fixtures_iter012.json (기본 results/iter_012/tests)

A. DataLoader 전용 generator: iterator 생성이 전역 torch CPU RNG를 소비하는지 (없을 때) / 소비하지 않는지 (있을 때) 통제 비교
B. collate의 sample_pos 전달, optimizer/batch digest의 안정성·민감도
C. select.verify_epoch: 기록 점수를 원시 응답에서 재계산 (utility 변조·요청 삭제·protocol 불일치·결정적 검사 run 거부)
D. select.payload/write_or_verify/verify_file: 같은 근거는 통과, 근거 파일이 바뀌면 오래된 선택 파일 거부
E. final_eval confirm: 오래된 comparator(재계산과 다름) 거부, 중복 seed는 I/O 전에 거부
F. run_shards: 새 시도 시작 시 기존 completion 보존·무효화, worker 실패 시 completion 미생성·attempt 실패 기록 (실제 CLI, 실제 protocol)
G. launch: 성공/실패/중단(child 생존) 상태 구분 (실제 CLI)
H. pipeline 단일 소유 lock, train.py의 검사 전용 옵션 --pilot 강제, protocol 잠금 목록에 pipeline.py 포함
실제 protocol 파일(results/iter_012/protocols/main_protocol.json)은 F에서 읽기만 한다. C-E는 임시 디렉터리와 lock_protocol.verify 임시 대체로 검사한다.
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time

import numpy as np
import torch
from PIL import Image

from rsna_diag import eval_gate, final_eval, generate, inputs, lock_protocol, lora, pipeline, prompts as P, queue_lock, select as SEL, sft_data, sft_eval
from rsna_diag import train as T

R = {}
REAL_PROT = os.environ.get("ITER012_PROTOCOL", "results/iter_012/protocols/pilot_protocol.json")
REAL_VERIFY = lock_protocol.verify


def check(name, cond, detail=None):
    R[name] = {"pass": bool(cond), "detail": detail}
    print(("PASS " if cond else "FAIL ") + name, "" if cond else detail, flush=True)


def raises(fn, exc):
    try:
        fn()
    except exc as e:
        return str(e) or type(e).__name__
    except Exception:  # noqa
        return None
    return None


TD = tempfile.mkdtemp(prefix="iter012_")

# ---------- A. DataLoader RNG ----------
class DS(torch.utils.data.Dataset):
    def __len__(self):
        return 8

    def __getitem__(self, i):
        return i


def iter_consumes_global(gen):
    torch.manual_seed(123)
    before = torch.get_rng_state().clone()
    dl = torch.utils.data.DataLoader(DS(), batch_size=2, num_workers=2, generator=gen)
    it = iter(dl)
    first = next(it)
    del it
    return not torch.equal(before, torch.get_rng_state()), first.tolist()


c_none, f_none = iter_consumes_global(None)
g = torch.Generator()
g.manual_seed(17000)
c_gen, f_gen = iter_consumes_global(g)
check("A_control_without_generator_iterator_consumes_global_cpu_rng", c_none is True)
check("A_with_dedicated_generator_global_cpu_rng_untouched", c_gen is False)
check("A_batch_order_unchanged_by_generator", f_none == f_gen == [0, 1])

# ---------- B. collate / digests ----------
exs = [{"input_ids": torch.tensor([1, 2, 3]), "attention_mask": torch.ones(3, dtype=torch.long), "labels": torch.tensor([-100, 2, 3]),
        "pixel_values": torch.zeros(1, 3, 4, 4), "sample_pos": 5},
       {"input_ids": torch.tensor([4, 5]), "attention_mask": torch.ones(2, dtype=torch.long), "labels": torch.tensor([-100, 5]),
        "pixel_values": torch.zeros(1, 3, 4, 4), "sample_pos": 6}]
b = sft_data.collate(exs, 0)
check("B_collate_carries_sample_pos", b["sample_pos"].tolist() == [5, 6])
b2 = sft_data.collate([{k: v for k, v in e.items() if k != "sample_pos"} for e in exs], 0)
check("B_collate_without_sample_pos_unchanged_keys", "sample_pos" not in b2 and set(b2) == set(b) - {"sample_pos"})
h1 = T.batch_token_digest({k: v for k, v in b.items() if k != "sample_pos"}).hexdigest()
b3 = {k: v.clone() for k, v in b.items() if k != "sample_pos"}
b3["labels"][0, 1] = -100
check("B_batch_token_digest_sensitive_to_label_mask", h1 != T.batch_token_digest(b3).hexdigest())
p = torch.nn.Parameter(torch.ones(3))
opt = torch.optim.AdamW([p], lr=1e-3)
d0 = T.opt_digest(torch, opt)
p.grad = torch.ones(3)
opt.step()
d1 = T.opt_digest(torch, opt)
opt2 = torch.optim.AdamW([torch.nn.Parameter(p.detach().clone())], lr=1e-3)
opt2.load_state_dict(opt.state_dict())
check("B_opt_digest_changes_after_step_and_roundtrips", d0 != d1 and T.opt_digest(torch, opt2) == d1 and T.opt_step_count(opt2) == 1)

# ---------- C. verify_epoch ----------
rng = np.random.default_rng(0)
man, gt = [], {}
cats = ["opacity", "opacity", "normal", "not_normal_no_opacity"]
for k, (split, cat) in enumerate([("train", c) for c in cats] + [("validation", c) for c in cats]):
    arr = rng.integers(0, 255, (48, 48), dtype=np.uint8)
    path = os.path.join(TD, f"img{k}.png")
    Image.fromarray(arr).save(path)
    iid = f"{split[:3]}_{k:03d}"
    man.append({"id": iid, "split": split, "image": path, "pixel_sha256": inputs.sha(arr.tobytes()), "file_sha256": inputs.sha(open(path, "rb").read())})
    gt[iid] = {"id": iid, "split": split, "category": cat, "pixel_sha256": inputs.sha(arr.tobytes()),
               "boxes": ([{"yxyx_norm": [100 + 10 * k, 100, 400, 400 + 10 * k]}] if cat == "opacity" else [])}
MP, GP = os.path.join(TD, "man.jsonl"), os.path.join(TD, "gt.json")
open(MP, "w").write("".join(json.dumps(m) + "\n" for m in man))
json.dump(gt, open(GP, "w"))
VAP = os.path.join(TD, "va.json")
json.dump([m["id"] for m in man if m["split"] == "validation"], open(VAP, "w"))
FAKE_ENV = {"model_id": generate.MODEL_ID, "model_revision": generate.MODEL_REVISION, "dtype": "torch.bfloat16", "transformers": "x", "torch": "y",
            "preprocess": generate.PREPROC_VERSION, "chat_template_sha256": "c", "eos_token_id": [1, 106], "do_pan_and_scan": None, "image_size": "s"}
generate.static_env = lambda: FAKE_ENV
PD = "pdig_iter012"
lock_protocol.verify = lambda path: PD if os.path.basename(path) != "OTHER.json" else "other_pdig"
PROT = os.path.join(TD, "PROT.json")
CD1, _ = generate.config_digest(FAKE_ENV, {"concise": P.CONCISE})
SEL.MANIFEST, SEL.GT, SEL.VAL_IDS = MP, GP, VAP
vitems, vgt = inputs.load_items(MP, GP, VAP, "validation")
vin = inputs.inputs_digest(vitems, vgt)
ids = [i["id"] for i in vitems]
edges = sft_eval.area_edges(vgt, [i for i in vgt if vgt[i]["split"] == "train"])


def mk_adapter(dirp, v):
    os.makedirs(dirp, exist_ok=True)
    st = {"w.lora_A": torch.full((2, 2), float(v)), "w.lora_B": torch.zeros(2, 2)}
    dg = lora.state_digest(st)
    torch.save({"state": st, "config": {"r": 16, "alpha": 32}, "digest": dg}, os.path.join(dirp, "adapter.pt"))
    return dg


def response(it):
    if gt[it["id"]]["boxes"]:
        return json.dumps([{"box_2d": [110, 100, 400, 400], "label": "pulmonary opacity"}]) + "<end_of_turn>"
    return "[]<end_of_turn>"


def mk_run(rd, seed=17, lr=2e-4, n_ep=2, deterministic=False):
    os.makedirs(rd, exist_ok=True)
    tc = {"train_digest": f"td_{seed}_{lr}", "config": {"seed": seed, "lr": lr, "val_inputs_digest": vin, "deterministic": deterministic}}
    json.dump(tc, open(os.path.join(rd, "train_config.json"), "w"))
    for e in range(1, n_ep + 1):
        ed = os.path.join(rd, f"epoch_{e:02d}")
        dg = mk_adapter(ed, e + seed)
        recs = []
        for it in vitems:
            recs.append({"id": it["id"], "prompt_name": "concise", "split": it["split"],
                         "request_id": generate.request_id(generate.MODEL_REVISION, dg, it["split"], it["id"], P.digest(P.CONCISE)),
                         "config_digest": CD1, "adapter_digest": dg, "protocol_digest": PD, "prompt_sha256": P.digest(P.CONCISE),
                         "input_pixel_sha256": generate.load_image(it["image"])[2], "image_file_sha256": it["file_sha256"],
                         "suffix_text_raw": response(it) if e == 1 or it["id"] != ids[0] else "[]<end_of_turn>", "ended_eos": True})
        gd = os.path.join(ed, "val_gen")
        os.makedirs(gd, exist_ok=True)
        open(os.path.join(gd, "gen_worker0.jsonl"), "w").write("".join(json.dumps(r) + "\n" for r in recs))
        json.dump({"n_expected": len(ids), "n_actual_unique": len(ids), "n_missing": 0, "n_duplicate": 0, "adapter_digest": dg, "protocol_digest": PD,
                   "val_inputs_digest": vin}, open(os.path.join(gd, "completion.json"), "w"))
        done = {(r["id"], "concise"): r for r in recs}
        summ = sft_eval.summarize(sft_eval.parse_records(done, ids, "concise"), gt, ids, edges)
        summ.update({"val_loss": 1.0 / e, "epoch": e, "adapter_digest": dg, "lr": lr, "seed": seed, "train_digest": tc["train_digest"],
                     "val_inputs_digest": vin, "protocol_digest": PD, "generation": {"n": len(ids)}})
        json.dump(summ, open(os.path.join(ed, "val_metrics.json"), "w"))
    return tc


rd = os.path.join(TD, "run_a")
tc = mk_run(rd)
check("C_verify_epoch_ok", SEL.verify_epoch(rd, 1, tc, vin, PROT, vitems, gt)["epoch"] == 1)
vm = os.path.join(rd, "epoch_02", "val_metrics.json")
orig = open(vm).read()
m = json.loads(orig)
m["utility"] = m["utility"] + 0.1
json.dump(m, open(vm, "w"))
check("C_tampered_utility_rejected_by_recomputation", raises(lambda: SEL.verify_epoch(rd, 2, tc, vin, PROT, vitems, gt), eval_gate.GateError) is not None)
open(vm, "w").write(orig)
gf = os.path.join(rd, "epoch_02", "val_gen", "gen_worker0.jsonl")
gorig = open(gf).read()
open(gf, "w").write("".join(gorig.splitlines(True)[1:]))
check("C_missing_raw_request_rejected", raises(lambda: SEL.verify_epoch(rd, 2, tc, vin, PROT, vitems, gt), eval_gate.GateError) is not None)
open(gf, "w").write(gorig)
check("C_protocol_mismatch_rejected", raises(lambda: SEL.verify_epoch(rd, 2, tc, vin, os.path.join(TD, "OTHER.json"), vitems, gt), eval_gate.GateError) is not None)
check("C_load_epochs_all_planned_ok", sorted(SEL.load_epochs(rd, 2, PROT)) == [1, 2])
check("C_load_epochs_missing_planned_epoch_rejected", raises(lambda: SEL.load_epochs(rd, 3, PROT), eval_gate.GateError) is not None)
rdd = os.path.join(TD, "run_det")
mk_run(rdd, deterministic=True)
check("C_deterministic_check_run_rejected_for_selection", raises(lambda: SEL.load_epochs(rdd, 2, PROT), eval_gate.GateError) is not None)

# ---------- D. selection provenance ----------
rb = os.path.join(TD, "run_b")
mk_run(rb, lr=1e-4)
pl = SEL.payload("pick", [rd, rb], PROT, 2)
out = os.path.join(TD, "pick.json")
check("D_write_new_selection", SEL.write_or_verify(out, pl) == "written")
check("D_existing_identical_selection_verified", SEL.write_or_verify(out, SEL.payload("pick", [rd, rb], PROT, 2)) == "verified_existing")
check("D_verify_file_recomputes_equal", SEL.verify_file(out, "pick", PROT)["selected_run"] == pl["selected_run"])
check("D_selection_has_protocol_rule_epochs_inputs_evidence",
      all(k in pl for k in ("protocol_digest", "rule", "planned_epochs", "val_inputs_digest", "evidence")) and
      set(pl["evidence"][rd]["epochs"]) == {"1", "2"})
open(gf, "w").write(gorig.replace('"ended_eos": true', '"ended_eos":  true', 1))  # 같은 의미, 다른 파일 내용
check("D_changed_evidence_file_makes_stored_selection_stale", raises(lambda: SEL.verify_file(out, "pick", PROT), eval_gate.GateError) is not None)
check("D_write_or_verify_refuses_stale_existing", raises(lambda: SEL.write_or_verify(out, SEL.payload("pick", [rd, rb], PROT, 2)), eval_gate.GateError) is not None)
open(gf, "w").write(gorig)
check("D_duplicate_runs_rejected", raises(lambda: SEL.payload("pick", [rd, rd], PROT, 2), eval_gate.GateError) is not None)
check("D_extend_only_at_epoch5", raises(lambda: SEL.payload("extend", [rd, rb], PROT, 2), eval_gate.GateError) is not None)
r5 = os.path.join(TD, "run_5ep")
mk_run(r5, seed=29, n_ep=5)
ep5 = SEL.load_epochs(r5, 5, PROT)
ext5, rep5 = SEL.should_extend([r5], PROT, 5)
exp_du = ep5[5]["utility"] - ep5[4]["utility"]
check("D_extend_rule_hand_calc", ext5 == (exp_du >= 0.01 and (0.2 / 0.25) <= 0.99) and abs(rep5[r5]["val_loss_ratio_5_over_4"] - 0.8) < 1e-12
      and abs(rep5[r5]["delta_utility"] - exp_du) < 1e-12, rep5)
hand_best = sorted(ep5.values(), key=lambda m_: (-round(m_["utility"], 12), -round(m_["f1@0.5"], 12), m_["epoch"]))[0]["epoch"]
check("D_best_epoch_rule_hand_calc", SEL.best_epoch(ep5)[0] == hand_best, [SEL.best_epoch(ep5)[0], hand_best])


# ---------- E. final_eval confirm: stale comparator ----------
class NS:
    def __init__(self, **kw):
        self.__dict__.update(kw)


cfile = os.path.join(TD, "comparator.json")
comp = {"comparator": "concise", "protocol_digest": PD, "baselines_json_sha256": final_eval.fsha(final_eval.BASE_JSON), "val_base_dir": "x",
        "parent_dir": None, "parent_protocol": None}
json.dump(comp, open(cfile, "w"))
final_eval.comparator_payload = lambda *a_, **k_: dict(comp, comparator="prior_set")
check("E_stale_comparator_rejected", "stale" in (raises(lambda: final_eval.cmd_confirm(NS(sft=["17:a:b", "29:a:b", "43:a:b"], comparator=cfile, protocol=PROT,
                                                                                         extend="x", conf_base="x", out="x")), eval_gate.GateError) or ""))
check("E_duplicate_seed_rejected_before_io", raises(lambda: final_eval.cmd_confirm(NS(sft=["17:a:b", "17:a:b", "43:a:b"], comparator="/nonexistent")), eval_gate.GateError) is not None)
lock_protocol.verify = REAL_VERIFY

# ---------- F. run_shards (실제 CLI) ----------
env = dict(os.environ, CUDA_VISIBLE_DEVICES="0,1")
rs = os.path.join(TD, "rs")
os.makedirs(rs)
json.dump({"n_expected": 1, "old": True}, open(os.path.join(rs, "completion.json"), "w"))
bad_ids = os.path.join(TD, "bad_ids.json")
json.dump(["not_in_manifest_id"], open(bad_ids, "w"))
if os.path.exists(REAL_PROT):
    p = subprocess.run([sys.executable, "-m", "rsna_diag.run_shards", "--manifest", "results/iter_010/manifests/infer_manifest.jsonl", "--ids", bad_ids,
                        "--out-dir", rs, "--protocol", REAL_PROT, "--prompts", "concise", "--workers", "2"], env=env, capture_output=True, text=True)
    att = [f for f in os.listdir(os.path.join(rs, "attempts")) if f.startswith("attempt_")]
    sup = [f for f in os.listdir(os.path.join(rs, "attempts")) if f.startswith("completion_superseded")]
    a0 = json.load(open(os.path.join(rs, "attempts", att[0]))) if att else {}
    check("F_worker_failure_nonzero_exit_and_no_completion", p.returncode == 2 and not os.path.exists(os.path.join(rs, "completion.json")), [p.returncode, p.stdout[-300:], p.stderr[-300:]])
    check("F_old_completion_preserved_but_superseded", len(sup) == 1 and json.load(open(os.path.join(rs, "attempts", sup[0]))).get("old") is True)
    check("F_attempt_recorded_failed_with_worker_returncodes", a0.get("status") == "failed_or_incomplete" and all(c != 0 for c in a0.get("returncodes", [0])), a0)
else:
    check("F_real_protocol_exists", False, REAL_PROT)

# ---------- G. launch (실제 CLI) ----------
okj = os.path.join(TD, "ok.json")
json.dump({"a": 1}, open(okj, "w"))
jobs_ok = [{"gpu": "0", "module": "json.tool", "args": [okj], "log": os.path.join(TD, "g_ok.log")},
           {"gpu": "1", "module": "json.tool", "args": [os.path.join(TD, "missing.json")], "log": os.path.join(TD, "g_bad.log")}]
jp = os.path.join(TD, "jobs1.json")
json.dump(jobs_ok, open(jp, "w"))
p = subprocess.run([sys.executable, "-m", "rsna_diag.launch", "--jobs", jp, "--log-dir", os.path.join(TD, "L1")], env=env, capture_output=True, text=True)
lr1 = json.load(open(os.path.join(TD, "L1", "launch_result.json")))
check("G_failed_child_gives_failed_status_nonzero_exit", p.returncode == 1 and lr1["status"] == "failed" and lr1["jobs"][0]["returncode"] == 0 and lr1["jobs"][1]["returncode"] not in (0, None), lr1)
jobs_long = [{"gpu": "0", "module": "timeit", "args": ["-n", "1", "-r", "1", "import time; time.sleep(60)"], "log": os.path.join(TD, "g_long.log")}]
jp2 = os.path.join(TD, "jobs2.json")
json.dump(jobs_long, open(jp2, "w"))
pl2 = subprocess.Popen([sys.executable, "-m", "rsna_diag.launch", "--jobs", jp2, "--log-dir", os.path.join(TD, "L2")], env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
time.sleep(6)
pl2.send_signal(signal.SIGINT)
pl2.wait(timeout=60)
lr2 = json.load(open(os.path.join(TD, "L2", "launch_result.json")))
check("G_interrupted_launch_marks_live_child_running_not_success",
      pl2.returncode != 0 and lr2["status"] == "interrupted_children_running" and lr2["jobs"][0]["state"] == "running" and lr2["jobs"][0]["returncode"] is None, lr2)
try:
    os.kill(lr2["jobs"][0]["pid"], signal.SIGTERM)  # 이 검사가 만든 child만 정리한다
except ProcessLookupError:
    pass

# ---------- H. pipeline lock / train guard / protocol list ----------
pipeline.R = os.path.join(TD, "pipe")
os.makedirs(pipeline.R)
hold, _, _ = queue_lock.try_lock(os.path.join(os.path.realpath(pipeline.R), "pipeline.lock"), queue_lock.my_info(role="test_holder"))
msg = raises(pipeline.main, SystemExit)
check("H_second_pipeline_refused_while_lock_held", hold is not None and msg is not None and "another pipeline owns" in msg, msg)
hold.release()
p = subprocess.run([sys.executable, "-m", "rsna_diag.train", "--run-dir", os.path.join(TD, "t"), "--lr", "1e-4", "--seed", "1", "--epochs", "1",
                    "--protocol", REAL_PROT, "--deterministic"], env=env, capture_output=True, text=True)
check("H_train_deterministic_requires_pilot", p.returncode != 0 and "require --pilot" in p.stderr, p.stderr[-300:])
p = subprocess.run([sys.executable, "-m", "rsna_diag.train", "--run-dir", os.path.join(TD, "t"), "--lr", "1e-4", "--seed", "1", "--epochs", "1",
                    "--protocol", REAL_PROT, "--stop-after-step", "2"], env=env, capture_output=True, text=True)
check("H_train_stop_after_step_requires_pilot", p.returncode != 0 and "require --pilot" in p.stderr, p.stderr[-300:])
check("H_protocol_locks_pipeline_py", "rsna_diag/pipeline.py" in lock_protocol.CODE)
if os.path.exists(REAL_PROT):
    check("H_real_protocol_includes_pipeline_and_thr_manifest",
          all(f in json.load(open(REAL_PROT))["locked"]["files"] for f in ("rsna_diag/pipeline.py", "results/iter_009/manifests/infer_manifest.jsonl")))

ap = argparse.ArgumentParser()
ap.add_argument("out", nargs="?", default="results/iter_012/tests")
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
json.dump(R, open(os.path.join(a.out, "fixtures_iter012.json"), "w"), indent=1, default=str)
n_ok = sum(v["pass"] for v in R.values())
print(f"{n_ok}/{len(R)} pass")
sys.exit(0 if n_ok == len(R) else 1)
