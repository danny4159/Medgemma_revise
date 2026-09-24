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
import json
import os

from . import eval_gate, inputs

MANIFEST = "results/iter_010/manifests/infer_manifest.jsonl"
GT = "results/iter_010/manifests/gt_manifest.json"
VAL_IDS = "results/iter_010/manifests/validation_ids.json"


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
    out = {}
    for e in range(1, expected_epochs + 1):
        ed = os.path.join(run_dir, f"epoch_{e:02d}")
        vm = os.path.join(ed, "val_metrics.json")
        if not os.path.exists(vm):
            raise eval_gate.GateError(f"{run_dir}: epoch {e} val_metrics missing (planned epochs 1..{expected_epochs})")
        m = json.load(open(vm))
        if m.get("epoch") != e or m.get("train_digest") != tc["train_digest"] or m.get("val_inputs_digest") != v_in:
            raise eval_gate.GateError(f"{run_dir}: epoch {e} metrics not linked to this run/inputs")
        if m.get("seed") != tc["config"]["seed"] or m.get("lr") != tc["config"]["lr"]:
            raise eval_gate.GateError(f"{run_dir}: epoch {e} seed/lr mismatch")
        adg = eval_gate.adapter_digest(ed)
        if m["adapter_digest"] != adg:
            raise eval_gate.GateError(f"{run_dir}: epoch {e} adapter digest differs from metrics")
        eval_gate.verify_gen(os.path.join(ed, "val_gen"), val_items, ["concise"], ed, protocol)
        c = json.load(open(os.path.join(ed, "val_gen", "completion.json")))
        if c.get("val_inputs_digest") != v_in:
            raise eval_gate.GateError(f"{run_dir}: epoch {e} completion input digest differs")
        out[e] = m
    return out


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["extend", "pick"])
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--epochs", type=int, required=True, help="예정 epoch 수 (extend는 5 고정)")
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if len(set(a.runs)) != len(a.runs):
        raise SystemExit("duplicate --runs")
    if os.path.exists(a.out):
        raise SystemExit(f"{a.out} exists (not overwritten)")
    if a.mode == "extend":
        ext, rep = should_extend(a.runs, a.protocol, 5)
        json.dump({"extend": ext, "detail": rep, "protocol": a.protocol}, open(a.out, "w"), indent=1)
        print("extend", ext)
    else:
        res, best = pick(a.runs, a.protocol, a.epochs)
        json.dump({"runs": res, "selected_run": best, "protocol": a.protocol}, open(a.out, "w"), indent=1)
        print("selected", best, res[best]["best_epoch"])


if __name__ == "__main__":
    main()
