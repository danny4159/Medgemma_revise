"""validation 규칙에 따른 학습 확장·learning rate·checkpoint 선택 (iter_010, 사전 고정 규칙). validation 지표만 읽는다.

- 확장 규칙: epoch 5에서, 어느 한 learning rate라도 (utility(5) - utility(4) >= 0.01) and (val_loss(5) <= 0.99 * val_loss(4))이면
  두 learning rate 모두 epoch 8까지 연장한다 ('마지막 두 epoch' = epoch 4 -> 5 변화로 고정 해석).
- checkpoint: run별 epoch 중 utility 최대, 동률은 양성 F1@0.5, 그 다음 이른 epoch. learning rate: seed 17 run의 선택 utility 최대
  (동률 F1@0.5, 그 다음 작은 lr).
사용: python -m rsna_diag.select extend|pick --runs DIR [DIR ...] --out FILE
"""
import argparse
import glob
import json
import os


def load_epochs(run_dir):
    out = {}
    for f in sorted(glob.glob(os.path.join(run_dir, "epoch_*", "val_metrics.json"))):
        m = json.load(open(f))
        out[m["epoch"]] = m
    return out


def should_extend(run_dirs):
    rep = {}
    ext = False
    for d in run_dirs:
        e = load_epochs(d)
        if 4 not in e or 5 not in e:
            raise RuntimeError(f"{d}: epoch 4/5 validation missing")
        du = e[5]["utility"] - e[4]["utility"]
        rl = e[5]["val_loss"] / e[4]["val_loss"]
        hit = du >= 0.01 and rl <= 0.99
        rep[d] = {"utility_4": e[4]["utility"], "utility_5": e[5]["utility"], "delta_utility": du, "val_loss_ratio_5_over_4": rl, "meets_rule": hit}
        ext = ext or hit
    return ext, rep


def best_epoch(run_dir, max_epoch=None):
    e = load_epochs(run_dir)
    cand = [m for k, m in e.items() if max_epoch is None or k <= max_epoch]
    best = max(cand, key=lambda m: (round(m["utility"], 12), round(m["f1@0.5"], 12), -m["epoch"]))
    return best["epoch"], {k: {"utility": m["utility"], "f1@0.3": m["f1@0.3"], "f1@0.5": m["f1@0.5"], "val_loss": m["val_loss"]} for k, m in sorted(e.items())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["extend", "pick"])
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.mode == "extend":
        ext, rep = should_extend(a.runs)
        json.dump({"extend": ext, "detail": rep}, open(a.out, "w"), indent=1)
        print("extend", ext)
    else:
        res = {}
        for d in a.runs:
            ep, table = best_epoch(d)
            cfg = json.load(open(os.path.join(d, "train_config.json")))["config"]
            res[d] = {"best_epoch": ep, "lr": cfg["lr"], "seed": cfg["seed"], "table": table,
                      "utility": table[ep]["utility"], "f1@0.5": table[ep]["f1@0.5"]}
        best = max(res, key=lambda d: (round(res[d]["utility"], 12), round(res[d]["f1@0.5"], 12), -res[d]["lr"]))
        json.dump({"runs": res, "selected_run": best}, open(a.out, "w"), indent=1)
        print("selected", best, res[best]["best_epoch"])


if __name__ == "__main__":
    main()
