"""iter_011 CPU 회귀 검증: 입력 provenance, 평가 gate, seed 집합, 선택 gate, migration 이관. 실행: python test_rsna_iter011.py [OUT_DIR]
-> results/iter_011/tests/fixtures_iter011.json (모든 항목 pass여야 exit 0). 실제 모델 GPU 검증은 test_rsna_iter011_gpu.py.
실제 protocol 파일은 건드리지 않고 (lock_protocol.verify를 임시 대체), 임시 디렉터리에 만든 소형 PNG/manifest/records로 검사한다.
"""
import argparse
import json
import os
import sys
import tempfile

import numpy as np
import torch
from PIL import Image

from rsna_diag import eval_gate, final_eval, generate, inputs, lock_protocol, lora, migrate, prompts as P, select as SEL

R = {}


def check(name, cond, detail=None):
    R[name] = {"pass": bool(cond), "detail": detail}
    print(("PASS " if cond else "FAIL ") + name, detail if not cond else "")


def raises(fn, exc):
    try:
        fn()
    except exc as e:
        return str(e)
    except Exception as e:  # noqa
        return None if not isinstance(e, exc) else str(e)
    return None


def sha(b):
    return inputs.sha(b)


# ---------- 소형 데이터 ----------
TD = tempfile.mkdtemp(prefix="iter011_")
rng = np.random.default_rng(0)
man, gt = [], {}
for k, split in enumerate(["train"] * 4 + ["validation"] * 3):
    arr = rng.integers(0, 255, (64, 64), dtype=np.uint8)
    path = os.path.join(TD, f"img{k}.png")
    Image.fromarray(arr).save(path)
    iid = f"{split[:3]}_{k:03d}"
    man.append({"id": iid, "split": split, "image": path, "pixel_sha256": sha(arr.tobytes()), "file_sha256": sha(open(path, "rb").read())})
    gt[iid] = {"id": iid, "split": split, "category": "opacity" if k % 2 == 0 else "normal", "pixel_sha256": sha(arr.tobytes()),
               "boxes": ([{"yxyx_norm": [100, 100, 400, 400]}] if k % 2 == 0 else [])}
MP, GP = os.path.join(TD, "man.jsonl"), os.path.join(TD, "gt.json")
open(MP, "w").write("\n".join(json.dumps(m) for m in man) + "\n")
json.dump(gt, open(GP, "w"))
tr_ids = [m["id"] for m in man if m["split"] == "train"]
va_ids = [m["id"] for m in man if m["split"] == "validation"]


def ids_file(name, ids):
    p = os.path.join(TD, name)
    json.dump(ids, open(p, "w"))
    return p


TRP, VAP = ids_file("tr.json", tr_ids), ids_file("va.json", va_ids)

# ---- A. inputs ----
items, g = inputs.load_items(MP, GP, TRP, "train")
check("inputs_exact_ok", [i["id"] for i in items] == sorted(tr_ids))
d0 = inputs.inputs_digest(items, g)
check("inputs_one_id_removed_rejected", raises(lambda: inputs.load_items(MP, GP, ids_file("a.json", tr_ids[:-1]), "train"), inputs.InputError) is not None)
check("inputs_one_id_swapped_for_other_split_rejected",
      raises(lambda: inputs.load_items(MP, GP, ids_file("b.json", tr_ids[:-1] + [va_ids[0]]), "train"), inputs.InputError) is not None)
check("inputs_duplicate_id_rejected", raises(lambda: inputs.load_items(MP, GP, ids_file("c.json", tr_ids + [tr_ids[0]]), "train"), inputs.InputError) is not None)
check("inputs_unknown_id_rejected", raises(lambda: inputs.load_items(MP, GP, ids_file("d.json", tr_ids[:-1] + ["tra_999"]), "train"), inputs.InputError) is not None)
gt_bad = json.loads(json.dumps(gt))
gt_bad[tr_ids[0]]["split"] = "validation"
GBP = os.path.join(TD, "gt_bad_split.json")
json.dump(gt_bad, open(GBP, "w"))
check("inputs_wrong_gt_split_rejected", raises(lambda: inputs.load_items(MP, GBP, TRP, "train"), inputs.InputError) is not None)
gt_px = json.loads(json.dumps(gt))
gt_px[tr_ids[0]]["pixel_sha256"] = "0" * 64
GPX = os.path.join(TD, "gt_bad_px.json")
json.dump(gt_px, open(GPX, "w"))
check("inputs_gt_pixel_hash_mismatch_rejected", raises(lambda: inputs.load_items(MP, GPX, TRP, "train"), inputs.InputError) is not None)
g2 = json.loads(json.dumps(g))
g2[tr_ids[0]]["boxes"] = [{"yxyx_norm": [101, 100, 400, 400]}]
check("inputs_digest_changes_with_gt_box", inputs.inputs_digest(items, g2) != d0)
check("inputs_digest_changes_with_id_subset", inputs.inputs_digest(items[:-1], g) != d0)
check("inputs_digest_stable", inputs.inputs_digest(items, g) == d0)
# 영상 pixel 변경 (원본 복사본에서)
img0 = items[0]["image"]
orig = open(img0, "rb").read()
arr2 = np.asarray(Image.open(img0)).copy()
arr2[0, 0] ^= 1
Image.fromarray(arr2).save(img0)
check("inputs_changed_pixel_rejected_by_digest", raises(lambda: inputs.inputs_digest(items, g), inputs.InputError) is not None)
check("inputs_changed_pixel_rejected_by_loader", raises(lambda: inputs.load_verified(items[0]), inputs.InputError) is not None)
open(img0, "wb").write(orig)
check("inputs_restored_ok", inputs.inputs_digest(items, g) == d0)
im, aff, ps = inputs.load_verified(items[0])
check("load_verified_matches_generate_load_image", ps == generate.load_image(items[0]["image"])[2])

# ---- B. seed 집합 ----
check("seeds_exact_ok", eval_gate.check_seeds(["17=a", "29=b", "43=c"]) == (17, 29, 43))
check("seeds_duplicate_rejected", raises(lambda: eval_gate.check_seeds(["17:a", "17:b", "43:c"]), eval_gate.GateError) is not None)
check("seeds_missing_rejected", raises(lambda: eval_gate.check_seeds(["17:a", "29:b"]), eval_gate.GateError) is not None)
check("seeds_extra_rejected", raises(lambda: eval_gate.check_seeds(["17:a", "29:b", "43:c", "5:d"]), eval_gate.GateError) is not None)
check("seeds_wrong_set_rejected", raises(lambda: eval_gate.check_seeds(["17:a", "29:b", "44:c"]), eval_gate.GateError) is not None)


class NS:
    def __init__(self, **kw):
        self.__dict__.update(kw)


check("final_eval_confirm_duplicate_seed_rejected_before_any_io",
      raises(lambda: final_eval.cmd_confirm(NS(sft=["17:x:y", "17:x:z", "43:x:w"], comparator="/nonexistent")), eval_gate.GateError) is not None)

# ---- C. verify_gen ----
FAKE_ENV = {"model_id": generate.MODEL_ID, "model_revision": generate.MODEL_REVISION, "dtype": "torch.bfloat16", "transformers": "x", "torch": "y",
            "preprocess": generate.PREPROC_VERSION, "chat_template_sha256": "c", "eos_token_id": [1, 106], "do_pan_and_scan": None, "image_size": "s"}
generate.static_env = lambda: FAKE_ENV
PDIG_NEW, PDIG_OLD = "p_new", "p_old"
lock_protocol.verify = lambda path: {"NEWP": PDIG_NEW, "OLDP": PDIG_OLD}.get(os.path.basename(path).split(".")[0], PDIG_NEW)
lock_protocol.digest_of = lambda path: PDIG_OLD
pn = ["official_long", "concise"]
prompts_used = {p: P.all_prompts()[p] for p in pn}
CD, _ = generate.config_digest(FAKE_ENV, prompts_used)
CD1, _ = generate.config_digest(FAKE_ENV, {"concise": P.CONCISE})
lock_protocol.locked_config_digest = lambda path: "same_cfg"


def mk_adapter(dirp, seedv):
    os.makedirs(dirp, exist_ok=True)
    st = {"w.lora_A": torch.full((2, 2), float(seedv)), "w.lora_B": torch.zeros(2, 2)}
    dg = lora.state_digest(st)
    torch.save({"state": st, "config": {"r": 16, "alpha": 32}, "digest": dg}, os.path.join(dirp, "adapter.pt"))
    return dg


def rec(it, pname, adg, pdig=PDIG_NEW, cdig=None):
    ps = {"official_long": P.OFFICIAL_LONG if hasattr(P, "OFFICIAL_LONG") else P.all_prompts()["official_long"], "concise": P.CONCISE}[pname]
    return {"id": it["id"], "prompt_name": pname, "request_id": generate.request_id(generate.MODEL_REVISION, adg, it["split"], it["id"], P.digest(ps)),
            "config_digest": cdig or (CD if len(pnames_cur[0]) == 2 else CD1), "adapter_digest": adg, "protocol_digest": pdig, "prompt_sha256": P.digest(ps),
            "input_pixel_sha256": generate.load_image(it["image"])[2], "image_file_sha256": it["file_sha256"], "split": it["split"]}


pnames_cur = [pn]


def write_gen(dirp, recs_by_file, completion=None):
    os.makedirs(dirp, exist_ok=True)
    for fn, rs in recs_by_file.items():
        with open(os.path.join(dirp, fn), "w") as f:
            f.write("".join(json.dumps(r) + "\n" for r in rs))
    if completion is not None:
        json.dump(completion, open(os.path.join(dirp, "completion.json"), "w"))


def full(items_, names, adg):
    pnames_cur[0] = names
    return [rec(i, p, adg) for i in items_ for p in names]


vitems, vg = inputs.load_items(MP, GP, VAP, "validation")
n_exp = len(vitems) * 2
comp_ok = {"n_expected": n_exp, "n_actual_unique": n_exp, "n_missing": 0, "n_duplicate": 0, "adapter_digest": None, "protocol_digest": PDIG_NEW}
rs = full(vitems, pn, None)
base_dir = os.path.join(TD, "base_ok")
write_gen(base_dir, {"gen_worker0.jsonl": rs[:3], "gen_worker1.jsonl": rs[3:]}, comp_ok)
PROT = os.path.join(TD, "NEWP.json")
got = eval_gate.verify_gen(base_dir, vitems, pn, None, PROT)
check("gate_complete_base_ok", len(got) == n_exp)
d = os.path.join(TD, "miss")
write_gen(d, {"gen_worker0.jsonl": rs[:-1]}, comp_ok)
check("gate_missing_request_rejected", raises(lambda: eval_gate.verify_gen(d, vitems, pn, None, PROT), eval_gate.GateError) is not None)
d = os.path.join(TD, "dup")
write_gen(d, {"gen_worker0.jsonl": rs, "gen_worker1.jsonl": rs[:1]}, comp_ok)
check("gate_duplicate_request_rejected", raises(lambda: eval_gate.verify_gen(d, vitems, pn, None, PROT), eval_gate.GateError) is not None)
d = os.path.join(TD, "extra")
write_gen(d, {"gen_worker0.jsonl": rs + [rec(items[0], "concise", None)]}, comp_ok)
check("gate_extra_request_rejected", raises(lambda: eval_gate.verify_gen(d, vitems, pn, None, PROT), eval_gate.GateError) is not None)
d = os.path.join(TD, "nocomp")
write_gen(d, {"gen_worker0.jsonl": rs})
check("gate_missing_completion_rejected", raises(lambda: eval_gate.verify_gen(d, vitems, pn, None, PROT), eval_gate.GateError) is not None)
check("gate_completion_optional_flag_allows_incomplete_marker", len(eval_gate.verify_gen(d, vitems, pn, None, PROT, require_completion=False)) == n_exp)
d = os.path.join(TD, "badcomp")
write_gen(d, {"gen_worker0.jsonl": rs}, dict(comp_ok, n_actual_unique=n_exp - 1))
check("gate_inconsistent_completion_rejected", raises(lambda: eval_gate.verify_gen(d, vitems, pn, None, PROT), eval_gate.GateError) is not None)
d = os.path.join(TD, "wrongprot")
write_gen(d, {"gen_worker0.jsonl": [dict(r, protocol_digest="other") for r in rs]}, comp_ok)
check("gate_record_protocol_mismatch_rejected", raises(lambda: eval_gate.verify_gen(d, vitems, pn, None, PROT), eval_gate.GateError) is not None)
d = os.path.join(TD, "wrongcfg")
write_gen(d, {"gen_worker0.jsonl": [dict(r, config_digest="zzz") for r in rs]}, comp_ok)
check("gate_record_config_mismatch_rejected", raises(lambda: eval_gate.verify_gen(d, vitems, pn, None, PROT), eval_gate.GateError) is not None)
d = os.path.join(TD, "badpx")
write_gen(d, {"gen_worker0.jsonl": [dict(r, input_pixel_sha256="0" * 64) for r in rs]}, comp_ok)
check("gate_record_pixel_hash_mismatch_rejected", raises(lambda: eval_gate.verify_gen(d, vitems, pn, None, PROT), eval_gate.GateError) is not None)
# 부모 record (이전 protocol digest) 연결
d = os.path.join(TD, "parentlink")
par = os.path.join(TD, "parent")
write_gen(par, {"gen_worker0.jsonl": [dict(r, protocol_digest=PDIG_OLD) for r in rs[:4]]})
write_gen(d, {"gen_worker0.jsonl": rs[4:]}, comp_ok)
OLDP = os.path.join(TD, "OLDP.json")
check("gate_parent_records_accepted_with_parent_protocol", len(eval_gate.verify_gen(d, vitems, pn, None, PROT, par, OLDP)) == n_exp)
check("gate_parent_records_rejected_without_parent_link", raises(lambda: eval_gate.verify_gen(d, vitems, pn, None, PROT), eval_gate.GateError) is not None)
write_gen(par, {"gen_worker0.jsonl": [dict(r, protocol_digest="unknown") for r in rs[:4]]})
check("gate_parent_records_with_unknown_protocol_rejected", raises(lambda: eval_gate.verify_gen(d, vitems, pn, None, PROT, par, OLDP), eval_gate.GateError) is not None)
# adapter
ad_a, ad_b = os.path.join(TD, "adA"), os.path.join(TD, "adB")
dga, dgb = mk_adapter(ad_a, 1), mk_adapter(ad_b, 2)
rsA = full(vitems, ["concise"], dga)
d = os.path.join(TD, "adgen")
write_gen(d, {"gen_worker0.jsonl": rsA}, dict(comp_ok, n_expected=len(vitems), n_actual_unique=len(vitems), adapter_digest=dga))
pnames_cur[0] = ["concise"]
check("gate_adapter_ok", len(eval_gate.verify_gen(d, vitems, ["concise"], ad_a, PROT)) == len(vitems))
check("gate_wrong_adapter_dir_rejected", raises(lambda: eval_gate.verify_gen(d, vitems, ["concise"], ad_b, PROT), eval_gate.GateError) is not None)
check("gate_base_records_under_adapter_rejected", raises(lambda: eval_gate.verify_gen(d, vitems, ["concise"], None, PROT), eval_gate.GateError) is not None)
tam = torch.load(os.path.join(ad_a, "adapter.pt"), weights_only=True)
tam["state"]["w.lora_A"] = tam["state"]["w.lora_A"] + 1
tad = os.path.join(TD, "adTamper")
os.makedirs(tad)
torch.save(tam, os.path.join(tad, "adapter.pt"))
check("gate_adapter_file_tamper_rejected", raises(lambda: eval_gate.adapter_digest(tad), eval_gate.GateError) is not None)
from rsna_diag import sft_eval  # noqa: E402
check("parse_records_strict_missing_raises", raises(lambda: sft_eval.parse_records({}, ["a"], "concise"), ValueError) is not None)
check("parse_records_nonstrict_marks_missing", sft_eval.parse_records({}, ["a"], "concise", strict=False)["a"]["status"] == "missing")

# ---- D. select gate ----
SEL.MANIFEST, SEL.GT, SEL.VAL_IDS = MP, GP, VAP
run_dir = os.path.join(TD, "run_lr")
os.makedirs(run_dir)
vin = inputs.inputs_digest(vitems, vg)
TDIG = "tdig"
json.dump({"train_digest": TDIG, "config": {"seed": 17, "lr": 2e-4, "val_inputs_digest": vin}}, open(os.path.join(run_dir, "train_config.json"), "w"))
pnames_cur[0] = ["concise"]


def mk_epoch(e, util, loss, skip_gen=False, digest_lie=False):
    ed = os.path.join(run_dir, f"epoch_{e:02d}")
    dg = mk_adapter(ed, e)
    if skip_gen:
        import shutil
        shutil.rmtree(os.path.join(ed, "val_gen"), ignore_errors=True)
    else:
        write_gen(os.path.join(ed, "val_gen"), {"gen_worker0.jsonl": full(vitems, ["concise"], dg)},
                  dict(comp_ok, n_expected=len(vitems), n_actual_unique=len(vitems), adapter_digest=dg, val_inputs_digest=vin))
    json.dump({"epoch": e, "utility": util, "val_loss": loss, "f1@0.3": util / 2, "f1@0.5": util / 3, "train_digest": TDIG, "val_inputs_digest": vin,
               "seed": 17, "lr": 2e-4, "adapter_digest": "lie" if digest_lie else dg}, open(os.path.join(ed, "val_metrics.json"), "w"))


for e, (u, l) in enumerate([(0.3, 1.0), (0.4, 0.9), (0.45, 0.8), (0.5, 0.7), (0.52, 0.65)], 1):
    if e != 3:
        mk_epoch(e, u, l)
check("select_missing_epoch_rejected", raises(lambda: SEL.load_epochs(run_dir, 5, PROT), eval_gate.GateError) is not None)
mk_epoch(3, 0.45, 0.8, digest_lie=True)
check("select_metrics_adapter_digest_lie_rejected", raises(lambda: SEL.load_epochs(run_dir, 5, PROT), eval_gate.GateError) is not None)
mk_epoch(3, 0.45, 0.8, skip_gen=True)
check("select_missing_raw_validation_records_rejected", raises(lambda: SEL.load_epochs(run_dir, 5, PROT), eval_gate.GateError) is not None)
mk_epoch(3, 0.45, 0.8)
ep = SEL.load_epochs(run_dir, 5, PROT)
check("select_all_planned_epochs_ok", sorted(ep) == [1, 2, 3, 4, 5])
check("select_extra_planned_epoch_missing_rejected", raises(lambda: SEL.load_epochs(run_dir, 8, PROT), eval_gate.GateError) is not None)
be, tb = SEL.best_epoch(ep)
check("select_best_epoch_is_max_utility", be == 5)
ext, rep = SEL.should_extend([run_dir], PROT, 5)
check("select_extend_rule_hand_calc", (ext is True) and abs(rep[run_dir]["delta_utility"] - 0.02) < 1e-9)
tcbad = json.load(open(os.path.join(run_dir, "train_config.json")))
tcbad["config"]["val_inputs_digest"] = "changed"
run_bad = os.path.join(TD, "run_bad")
os.makedirs(run_bad)
json.dump(tcbad, open(os.path.join(run_bad, "train_config.json"), "w"))
check("select_run_trained_on_other_validation_inputs_rejected", raises(lambda: SEL.load_epochs(run_bad, 5, PROT), eval_gate.GateError) is not None)

# ---- E. migration ----
os.makedirs(os.path.join(TD, "parent_run"))
pcfg = {"r": 16, "lr": 1e-4, "seed": 17, "microbatch": 2, "n_train": 2400, "protocol_digest": "old"}
pblob = {"lora": {"a": torch.zeros(1)}, "optimizer": {}, "step": 100, "epoch": 0, "pos_in_epoch": 100, "rng": {}, "train_digest": "td_old",
         "base_revision": "rev", "protocol_digest": "old"}
pck = os.path.join(TD, "parent_run", "ckpt_latest.pt")
torch.save(pblob, pck)
open(os.path.join(TD, "parent_run", "train_log.jsonl"), "w").write('{"step": 1}\n')
mig = {"new_protocol_digest": "new", "parent_ckpt": pck, "parent_ckpt_sha256": migrate.file_sha(pck), "parent_train_digest": "td_old",
       "parent_protocol_digest": "old", "parent_step": 100, "parent_epoch": 0, "parent_pos_in_epoch": 100, "parent_config": pcfg}
MG = os.path.join(TD, "mig.json")
json.dump(mig, open(MG, "w"))
newcfg = dict(pcfg, protocol_digest="new", train_inputs_digest="t", val_inputs_digest="v")
b_, m_ = migrate.verify_parent(MG, newcfg, "new")
check("migrate_verify_parent_ok", b_["step"] == 100)
check("migrate_lr_semantic_change_rejected", raises(lambda: migrate.verify_parent(MG, dict(newcfg, lr=2e-4), "new"), migrate.MigrationError) is not None)
check("migrate_microbatch_change_rejected", raises(lambda: migrate.verify_parent(MG, dict(newcfg, microbatch=1), "new"), migrate.MigrationError) is not None)
check("migrate_extra_new_key_rejected", raises(lambda: migrate.verify_parent(MG, dict(newcfg, new_hparam=1), "new"), migrate.MigrationError) is not None)
check("migrate_wrong_new_protocol_rejected", raises(lambda: migrate.verify_parent(MG, newcfg, "other"), migrate.MigrationError) is not None)
pblob2 = dict(pblob, step=101)
torch.save(pblob2, pck)
check("migrate_changed_parent_checkpoint_rejected", raises(lambda: migrate.verify_parent(MG, newcfg, "new"), migrate.MigrationError) is not None)
torch.save(pblob, pck)
mig2 = dict(mig, parent_step=99)
json.dump(mig2, open(MG, "w"))
mig2["parent_ckpt_sha256"] = migrate.file_sha(pck)
json.dump(mig2, open(MG, "w"))
check("migrate_manifest_step_disagrees_with_checkpoint_rejected", raises(lambda: migrate.verify_parent(MG, newcfg, "new"), migrate.MigrationError) is not None)

ap = argparse.ArgumentParser()
ap.add_argument("out", nargs="?", default="results/iter_011/tests")
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
json.dump(R, open(os.path.join(a.out, "fixtures_iter011.json"), "w"), indent=1)
n_ok = sum(v["pass"] for v in R.values())
print(f"{n_ok}/{len(R)} pass")
sys.exit(0 if n_ok == len(R) else 1)
