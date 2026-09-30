"""validation 규칙에 따른 학습 확장·learning rate·checkpoint 선택 (iter_010 사전 고정 규칙, iter_011 gate 추가).

- 확장 규칙: epoch 5에서, 어느 한 learning rate라도 (utility(5) - utility(4) >= 0.01) and (val_loss(5) <= 0.99 * val_loss(4))이면
  두 learning rate 모두 epoch 8까지 연장한다 ('마지막 두 epoch' = epoch 4 -> 5 변화로 고정 해석).
- checkpoint: run별 epoch 중 utility 최대, 동률은 양성 F1@0.5, 그 다음 이른 epoch. learning rate: seed 17 run의 선택 utility 최대
  (동률 F1@0.5, 그 다음 작은 lr).
- iter_011: 예정된 epoch 1..E 전체의 val_metrics가 있고, 각 epoch의 원시 validation 요청 집합(400 ID x concise)·adapter digest·
  protocol·입력 digest·train_digest가 실제 파일과 일치할 때만 선택/확장 판정을 한다 (하나라도 어긋나면 예외, 출력 파일 없음).
사용: python -m rsna_diag.select extend|pick --runs DIR [DIR ...] --epochs E --protocol P --out FILE
"""
import argparse
import glob
import hashlib
import json
import os

from . import eval_gate, inputs, lock_protocol, sft_eval

MANIFEST = "results/iter_010/manifests/infer_manifest.jsonl"
GT = "results/iter_010/manifests/gt_manifest.json"
VAL_IDS = "results/iter_010/manifests/validation_ids.json"


def verify_epoch(run_dir, e, tc, v_in, protocol, val_items, gt):
    """한 epoch의 val_metrics가 이 run·입력·adapter·원시 validation 요청 집합·protocol과 연결되는지 검증하고,
    생성 기반 점수(utility·F1 등 summarize 결과 전체)를 원시 응답에서 다시 계산해 기록값과 같은지 확인한다. returns metrics."""
    ed = os.path.join(run_dir, f"epoch_{e:02d}")
    vm = os.path.join(ed, "val_metrics.json")
    if not os.path.exists(vm):
        raise eval_gate.GateError(f"{run_dir}: epoch {e} val_metrics missing")
    m = json.load(open(vm))
    if m.get("epoch") != e or m.get("train_digest") != tc["train_digest"] or m.get("val_inputs_digest") != v_in:
        raise eval_gate.GateError(f"{run_dir}: epoch {e} metrics not linked to this run/inputs")
    if m.get("seed") != tc["config"]["seed"] or m.get("lr") != tc["config"]["lr"]:
        raise eval_gate.GateError(f"{run_dir}: epoch {e} seed/lr mismatch")
    if m.get("protocol_digest") != lock_protocol.verify(protocol):
        raise eval_gate.GateError(f"{run_dir}: epoch {e} metrics protocol digest differs from current protocol")
    adg = eval_gate.adapter_digest(ed)
    if m["adapter_digest"] != adg:
        raise eval_gate.GateError(f"{run_dir}: epoch {e} adapter digest differs from metrics")
    done = eval_gate.verify_gen(os.path.join(ed, "val_gen"), val_items, ["concise"], ed, protocol)
    c = json.load(open(os.path.join(ed, "val_gen", "completion.json")))
    if c.get("val_inputs_digest") != v_in:
        raise eval_gate.GateError(f"{run_dir}: epoch {e} completion input digest differs")
    ids = [i["id"] for i in val_items]
    edges = sft_eval.area_edges(gt, [i for i in gt if gt[i]["split"] == "train"])
    rec = json.loads(json.dumps(sft_eval.summarize(sft_eval.parse_records(done, ids, "concise", strict=True), gt, ids, edges)))
    bad = [k for k in rec if m.get(k) != rec[k]]
    if bad:
        raise eval_gate.GateError(f"{run_dir}: epoch {e} recorded scores differ from recomputation from raw responses: {bad[:5]}")
    return m


def load_epochs(run_dir, expected_epochs, protocol, val_items=None, gt=None):
    """epoch 1..expected_epochs 전체를 검증해 {epoch: metrics}를 반환한다. 누락·불일치는 GateError."""
    if not expected_epochs or expected_epochs < 1:
        raise eval_gate.GateError("expected_epochs required")
    tc = json.load(open(os.path.join(run_dir, "train_config.json")))
    if val_items is None:
        val_items, gt = inputs.load_items(MANIFEST, GT, VAL_IDS, "validation")
    v_in = inputs.inputs_digest(val_items, gt)
    if tc["config"].get("val_inputs_digest") != v_in:
        raise eval_gate.GateError(f"{run_dir}: run was not trained/validated on the current validation inputs")
    if tc["config"].get("deterministic"):
        raise eval_gate.GateError(f"{run_dir}: deterministic check run cannot be used for selection")
    out = {}
    for e in range(1, expected_epochs + 1):
        if not os.path.exists(os.path.join(run_dir, f"epoch_{e:02d}", "val_metrics.json")):
            raise eval_gate.GateError(f"{run_dir}: epoch {e} val_metrics missing (planned epochs 1..{expected_epochs})")
        out[e] = verify_epoch(run_dir, e, tc, v_in, protocol, val_items, gt)
    return out


def file_sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def evidence(run_dir, expected_epochs):
    """선택 근거 파일의 내용 hash (val_metrics·completion·원시 요청 파일·adapter). load_epochs 통과 뒤에만 부른다."""
    ev = {"train_config_sha256": file_sha(os.path.join(run_dir, "train_config.json")), "epochs": {}}
    for e in range(1, expected_epochs + 1):
        ed = os.path.join(run_dir, f"epoch_{e:02d}")
        ev["epochs"][str(e)] = {"val_metrics_sha256": file_sha(os.path.join(ed, "val_metrics.json")),
                                "completion_sha256": file_sha(os.path.join(ed, "val_gen", "completion.json")),
                                "gen_files_sha256": {os.path.basename(f): file_sha(f) for f in sorted(glob.glob(os.path.join(ed, "val_gen", "gen_worker*.jsonl")))},
                                "adapter_file_sha256": file_sha(os.path.join(ed, "adapter.pt"))}
    return ev


def should_extend(run_dirs, protocol, expected=5):
    rep, ext = {}, False
    vi, gt = inputs.load_items(MANIFEST, GT, VAL_IDS, "validation")
    for d in run_dirs:
        e = load_epochs(d, expected, protocol, vi, gt)
        du = e[5]["utility"] - e[4]["utility"]
        rl = e[5]["val_loss"] / e[4]["val_loss"]
        hit = du >= 0.01 and rl <= 0.99
        rep[d] = {"utility_4": e[4]["utility"], "utility_5": e[5]["utility"], "delta_utility": du, "val_loss_ratio_5_over_4": rl, "meets_rule": hit}
        ext = ext or hit
    return ext, rep


def best_epoch(epochs):
    best = max(epochs.values(), key=lambda m: (round(m["utility"], 12), round(m["f1@0.5"], 12), -m["epoch"]))
    return best["epoch"], {k: {"utility": m["utility"], "f1@0.3": m["f1@0.3"], "f1@0.5": m["f1@0.5"], "val_loss": m["val_loss"]}
                           for k, m in sorted(epochs.items())}


def pick(run_dirs, protocol, expected):
    res = {}
    vi, gt = inputs.load_items(MANIFEST, GT, VAL_IDS, "validation")
    for d in run_dirs:
        ep_metrics = load_epochs(d, expected, protocol, vi, gt)
        ep, table = best_epoch(ep_metrics)
        cfg = json.load(open(os.path.join(d, "train_config.json")))["config"]
        res[d] = {"best_epoch": ep, "lr": cfg["lr"], "seed": cfg["seed"], "n_epochs_validated": expected, "table": table,
                  "utility": table[ep]["utility"], "f1@0.5": table[ep]["f1@0.5"],
                  "adapter_dir": os.path.join(d, f"epoch_{ep:02d}"), "adapter_digest": ep_metrics[ep]["adapter_digest"]}
    best = max(res, key=lambda d: (round(res[d]["utility"], 12), round(res[d]["f1@0.5"], 12), -res[d]["lr"]))
    return res, best


RULES = {"extend": "iter010 fixed: any LR with utility(5)-utility(4)>=0.01 and val_loss(5)<=0.99*val_loss(4) -> both LRs to 8 epochs",
         "pick": "iter010 fixed: epoch max utility, tie F1@0.5, then earlier epoch; run max utility, tie F1@0.5, then smaller lr"}


def payload(mode, runs, protocol, epochs):
    """선택 결정 + provenance (protocol 내용 digest, 규칙, 예정 epoch, seed/lr, 입력 digest, 근거 파일 hash). 항상 원시 근거에서 재계산한다."""
    if len(set(runs)) != len(runs):
        raise eval_gate.GateError("duplicate --runs")
    if mode == "extend" and epochs != 5:
        raise eval_gate.GateError("extend decision is defined at epoch 5 only")
    pdig = lock_protocol.verify(protocol)
    vi, gt = inputs.load_items(MANIFEST, GT, VAL_IDS, "validation")
    base = {"mode": mode, "rule": RULES[mode], "protocol_path": protocol, "protocol_digest": pdig, "planned_epochs": epochs,
            "runs_in": list(runs), "val_inputs_digest": inputs.inputs_digest(vi, gt)}
    if mode == "extend":
        ext, rep = should_extend(runs, protocol, 5)
        base.update({"extend": ext, "detail": rep})
    else:
        res, best = pick(runs, protocol, epochs)
        base.update({"runs": res, "selected_run": best})
    base["evidence"] = {d: evidence(d, epochs) for d in runs}
    return base


def write_or_verify(path, pl):
    """없으면 원자적으로 쓰고, 있으면 재계산 결과와 완전히 같아야 한다 (오래되거나 바뀐 선택 파일은 조용히 믿지 않는다)."""
    if os.path.exists(path):
        old = json.load(open(path))
        if old != json.loads(json.dumps(pl)):
            raise eval_gate.GateError(f"{path}: existing selection differs from recomputation from current evidence")
        return "verified_existing"
    tmp = path + ".tmp"
    json.dump(pl, open(tmp, "w"), indent=1)
    os.replace(tmp, path)
    return "written"


def verify_file(path, mode, protocol):
    """선택 파일을 그 파일에 적힌 runs·예정 epoch로 다시 계산해 동일한지 검증한다 (final_eval이 사용). returns 파일 내용."""
    old = json.load(open(path))
    if old.get("mode") != mode:
        raise eval_gate.GateError(f"{path}: not a {mode} selection")
    pl = payload(mode, old["runs_in"], protocol, old["planned_epochs"])
    if old != json.loads(json.dumps(pl)):
        raise eval_gate.GateError(f"{path}: selection no longer matches recomputation from current evidence")
    return old


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["extend", "pick"])
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--epochs", type=int, required=True, help="예정 epoch 수 (extend는 5 고정)")
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    pl = payload(a.mode, a.runs, a.protocol, a.epochs)
    st = write_or_verify(a.out, pl)
    print(a.mode, st, pl.get("extend", pl.get("selected_run")))


if __name__ == "__main__":
    main()
