"""iter_010 비교 평가. 두 단계:

  comparator: validation(400)의 base 생성·보정·prior 중 양성 F1@0.3 최대인 단순 비교군 1개를 주 비교군으로 고정 (확인 결과를 보기 전에).
  confirm:    고정된 주 비교군과 SFT 3개 seed를 확인 800명에서 같은 metric으로 비교 (paired bootstrap 10,000회, seed 20260925).
iter_011: 모든 입력 생성 결과는 eval_gate.verify_gen(예상 ID x prompt x adapter 집합, protocol/config/입력/completion)을 통과해야 하며,
  seed 집합은 정확히 {17, 29, 43} (중복은 dict 생성 전에 거부), 각 seed의 adapter는 select 기록의 adapter digest와 일치해야 한다.
사용: python -m rsna_diag.final_eval comparator --val-base DIR [--parent-dir D --parent-protocol P0] --protocol P --out FILE
      python -m rsna_diag.final_eval confirm --comparator FILE --conf-base DIR --protocol P --sft SEED:SELECTION.json:GEN_DIR ... --out FILE
"""
import argparse
import glob
import hashlib
import json
import os

import numpy as np

from . import baselines as B, eval_gate, inputs, lock_protocol, metrics as M, parse as PA, sft_eval

MANIFEST = "results/iter_010/manifests/infer_manifest.jsonl"
SPLIT_IDS = "results/iter_010/manifests/{}_ids.json"
GT = "results/iter_010/manifests/gt_manifest.json"
BASE_JSON = "results/iter_010/baselines/baselines.json"
BOOT_SEED, BOOT_B = 20260925, 10000


def split_ids(gt, split):
    return sorted(i for i in gt if gt[i]["split"] == split)


def base_predictions(recs, ids, bl):
    """base 생성 record -> {이름: preds}. 보정은 prompt별 고정 변환 (실패 출력은 그대로)."""
    out = {}
    for p in ("official_long", "concise"):
        raw = sft_eval.parse_records(recs, ids, p)
        out[p] = raw
        spec = tuple(bl[p]["spec"])
        out[p + "+corr"] = {i: B.apply_pred(raw[i], spec)[0] for i in ids}
    return out


def prior_predictions(ids, bl):
    return {"prior_set": {i: {"status": "valid_nonempty", "boxes": bl["prior_set"]["set"]} for i in ids},
            "prior_single": {i: {"status": "valid_nonempty", "boxes": [bl["prior_single_box"]["box"]]} for i in ids}}


def all_simple(recs, ids, bl):
    d = base_predictions(recs, ids, bl)
    d.update(prior_predictions(ids, bl))
    return d


def fsha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def comparator_payload(val_base, protocol, parent_dir=None, parent_protocol=None):
    """validation base 생성의 원시 요청에서 주 비교군을 재계산한다 (근거 파일 hash 포함)."""
    items, gt = inputs.load_items(MANIFEST, GT, SPLIT_IDS.format("validation"), "validation")
    bl = json.load(open(BASE_JSON))
    ids = [i["id"] for i in items]
    recs = eval_gate.verify_gen(val_base, items, ["official_long", "concise"], None, protocol, parent_dir, parent_protocol)
    tr = [i for i in gt if gt[i]["split"] == "train"]
    edges = sft_eval.area_edges(gt, tr)
    preds = all_simple(recs, ids, bl)
    summ = {k: sft_eval.summarize(v, gt, ids, edges) for k, v in preds.items()}
    best = max(summ, key=lambda k: (round(summ[k]["f1@0.3"], 12), k))
    gen_files = sorted(glob.glob(os.path.join(val_base, "gen_worker*.jsonl")))
    par_files = sorted(glob.glob(os.path.join(parent_dir, "gen_worker*.jsonl"))) if parent_dir else []
    return {"comparator": best, "selection": "validation positive mean F1@0.3 (end-to-end)", "n_val": len(ids),
            "protocol_digest": lock_protocol.verify(protocol), "baselines_json_sha256": fsha(BASE_JSON),
            "val_inputs_digest": inputs.inputs_digest(items, gt), "val_base_dir": val_base, "parent_dir": parent_dir,
            "parent_protocol": parent_protocol, "parent_protocol_digest": lock_protocol.digest_of(parent_protocol) if parent_protocol else None,
            "evidence": {"gen_files_sha256": {f: fsha(f) for f in gen_files + par_files},
                         "completion_sha256": fsha(os.path.join(val_base, "completion.json"))},
            "val_f1@0.3": {k: v["f1@0.3"] for k, v in summ.items()}, "val_summaries": summ}


def cmd_comparator(a):
    from . import select as SEL
    pl = comparator_payload(a.val_base, a.protocol, a.parent_dir, a.parent_protocol)
    st = SEL.write_or_verify(a.out, pl)
    print("comparator", st, pl["comparator"], {k: round(v, 4) for k, v in pl["val_f1@0.3"].items()})


def cmd_confirm(a):
    seeds_in = eval_gate.check_seeds([kv.split(":")[0] for kv in a.sft])  # 가장 먼저: 중복/누락/잉여 seed 거부 (dict 생성 이전)
    from . import select as SEL
    comp = json.load(open(a.comparator))
    items, gt = inputs.load_items(MANIFEST, GT, SPLIT_IDS.format("confirm"), "confirm")
    bl = json.load(open(BASE_JSON))
    pdig = lock_protocol.verify(a.protocol)
    if comp.get("protocol_digest") != pdig or comp["baselines_json_sha256"] != hashlib.sha256(open(BASE_JSON, "rb").read()).hexdigest():
        raise eval_gate.GateError("comparator file was not locked under the current protocol/baselines")
    # iter_012: 주 비교군·연장·선택을 원시 validation 근거에서 다시 계산해 파일과 완전히 같을 때만 확인 평가를 한다
    if comp != json.loads(json.dumps(comparator_payload(comp["val_base_dir"], a.protocol, comp["parent_dir"], comp["parent_protocol"]))):
        raise eval_gate.GateError("comparator file is stale: differs from recomputation from validation base generations")
    ext = SEL.verify_file(a.extend, "extend", a.protocol)
    E = 8 if ext["extend"] else 5
    sel_files = {int(kv.split(":")[0]): SEL.verify_file(kv.split(":")[1], "pick", a.protocol) for kv in a.sft}
    for s, sf in sel_files.items():
        if sf["planned_epochs"] != E:
            raise eval_gate.GateError(f"seed {s}: selection planned epochs {sf['planned_epochs']} != E={E} from extend decision")
    if sorted(sel_files[17]["runs_in"]) != sorted(ext["runs_in"]) or len(ext["runs_in"]) != 2:
        raise eval_gate.GateError("seed 17 LR pick must be over exactly the two seed-17 LR runs of the extend decision")
    lr17 = sel_files[17]["runs"][sel_files[17]["selected_run"]]["lr"]
    for s in (29, 43):
        if len(sel_files[s]["runs_in"]) != 1 or sel_files[s]["runs"][sel_files[s]["selected_run"]]["lr"] != lr17:
            raise eval_gate.GateError(f"seed {s}: selection must be a single run at the seed-17 selected lr {lr17}")
    ids = [i["id"] for i in items]
    pos = [i for i in ids if gt[i]["category"] == "opacity"]
    tr = [i for i in gt if gt[i]["split"] == "train"]
    edges = sft_eval.area_edges(gt, tr)
    recs = eval_gate.verify_gen(a.conf_base, items, ["official_long", "concise"], None, a.protocol)
    preds = all_simple(recs, ids, bl)
    sft, sel_meta = {}, {}
    for kv in a.sft:
        seed, selp, d = kv.split(":")
        sel = json.load(open(selp))
        run = sel["runs"][sel["selected_run"]]
        if run["seed"] != int(seed):
            raise eval_gate.GateError(f"selection {selp} is for seed {run['seed']}, not {seed}")
        r = eval_gate.verify_gen(d, items, ["concise"], run["adapter_dir"], a.protocol)
        if {x["adapter_digest"] for x in r.values()} != {run["adapter_digest"]}:
            raise eval_gate.GateError(f"seed {seed}: generation adapter digest != selected adapter digest")
        sft[f"sft_seed{seed}"] = sft_eval.parse_records(r, ids, "concise")
        sel_meta[int(seed)] = {"selection": selp, "lr": run["lr"], "best_epoch": run["best_epoch"], "n_epochs_validated": run["n_epochs_validated"],
                               "adapter_digest": run["adapter_digest"]}
    if len({(m["lr"], m["n_epochs_validated"]) for m in sel_meta.values()}) != 1:
        raise eval_gate.GateError(f"seeds used different lr/epoch plans: {sel_meta}")
    assert tuple(sorted(sel_meta)) == seeds_in
    preds.update(sft)
    summ = {k: sft_eval.summarize(v, gt, ids, edges) for k, v in preds.items()}
    per = {k: sft_eval.per_patient(v, gt, ids)[1]["f1@0.3"] for k, v in preds.items()}
    idx = M.bootstrap_indices(len(pos), BOOT_B, BOOT_SEED)
    cname = comp["comparator"]
    seeds = sorted(sft)
    mean_sft = np.mean([per[s] for s in seeds], axis=0)
    m, lo, hi = M.paired_boot_ci(mean_sft, per[cname], idx)
    diffs = {s: float(per[s].mean() - per[cname].mean()) for s in seeds}
    boot_all = {}
    for k in preds:
        if k in sft or k == cname:
            continue
        mm, l_, h_ = M.paired_boot_ci(mean_sft, per[k], idx)
        boot_all[k] = {"mean_diff": mm, "ci95": [l_, h_]}
    base_c = summ["concise"]
    neg_ok = {}
    for s in seeds:
        neg_ok[s] = {nm: (base_c[f"neg_{nm}"]["valid_empty"]["rate"] - summ[s][f"neg_{nm}"]["valid_empty"]["rate"]) <= 0.05
                     for nm in ("Normal", "NoOpacity/NotNormal")}
    crit = {"mean_diff_ge_0.05": m >= 0.05, "ci_lower_gt_0": lo > 0, "all_seed_diffs_positive": all(v > 0 for v in diffs.values()),
            "valid_output_rate_all_ge_95pct_each_seed": all(summ[s]["valid_rate_all"]["rate"] >= 0.95 for s in seeds),
            "negative_valid_empty_not_worse_than_5pp_vs_base_concise": all(all(v.values()) for v in neg_ok.values())}
    verdict = "success" if all(crit.values()) else ("partial_improvement" if m > 0 else "no_improvement")
    res = {"comparator": cname, "seed_selection": sel_meta, "protocol_digest": pdig, "n_confirm_positive": len(pos), "primary": {"mean_sft_minus_comparator_f1@0.3": m, "ci95": [lo, hi],
           "bootstrap": {"B": BOOT_B, "seed": BOOT_SEED, "unit": "positive patient", "note": "학습 seed 불확실성을 충분히 추정하지 않는다"},
           "per_seed_diff": diffs, "per_seed_f1@0.3": {s: float(per[s].mean()) for s in seeds},
           "seed_range_f1@0.3": [min(per[s].mean() for s in seeds), max(per[s].mean() for s in seeds)]},
           "criteria": crit, "negative_layer_detail": neg_ok, "verdict_preregistered_criteria": verdict,
           "diff_vs_other_baselines": boot_all, "summaries": summ,
           "provenance": {"comparator_file": a.comparator, "comparator_sha256": fsha(a.comparator), "extend_file": a.extend,
                          "extend_sha256": fsha(a.extend), "total_epochs_E": E,
                          "selection_files_sha256": {kv.split(":")[0]: fsha(kv.split(":")[1]) for kv in a.sft},
                          "recomputed_and_equal": True}}
    tmp = a.out + ".tmp"
    json.dump(res, open(tmp, "w"), indent=1)
    os.replace(tmp, a.out)
    print(json.dumps({k: res["primary"][k] for k in ("mean_sft_minus_comparator_f1@0.3", "ci95", "per_seed_diff")}), crit, verdict)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("comparator")
    c.add_argument("--val-base", required=True)
    c.add_argument("--protocol", required=True)
    c.add_argument("--parent-dir", default=None)
    c.add_argument("--parent-protocol", default=None)
    c.add_argument("--out", required=True)
    f = sp.add_parser("confirm")
    f.add_argument("--comparator", required=True)
    f.add_argument("--extend", required=True, help="seed17 연장 판정 파일 (재계산 검증)")
    f.add_argument("--conf-base", required=True)
    f.add_argument("--protocol", required=True)
    f.add_argument("--sft", nargs="+", required=True, help="SEED:SELECTION.json:GEN_DIR (정확히 17, 29, 43)")
    f.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "confirm" and os.path.exists(a.out):
        raise SystemExit(f"{a.out} exists (not overwritten)")
    {"comparator": cmd_comparator, "confirm": cmd_confirm}[a.cmd](a)


if __name__ == "__main__":
    main()
