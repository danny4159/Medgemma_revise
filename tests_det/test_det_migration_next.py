"""이관한 iter_034 checkpoint(update 706)에서 다음 update 검증 (natten_py310 env, GPU 1장).

원본 로그는 저장 update 706 직전(705)까지만 있으므로 원 프로세스의 다음 update와 직접 비교할 수 없다.
대신 (1) 새 프로세스 두 개(a, b)를 같은 이관 state에서 3 update씩 실행해 control·입력·첫 update loss 일치,
(2) 원래 결정적 함수(epoch permutation, epoch 시작 시딩 후 연속 소비한 dataset RNG)로 재생한 update 706–708의
sample id·flip과 일치, (3) 적용 LR=0.005(warmup 이후, 감소 전 schedule)와 finite, (4) 첫 update loss가 원본 로그
마지막 100 update의 loss 범위 안에 있는지를 확인한다. 원본 checkpoint·로그는 읽기만 한다.
"""
import argparse
import json
import os
import random
import subprocess
import sys

BASE = "/SSD1_1TB/home/milab/daniel/08_medgemma/research"
sys.path.insert(0, BASE)
from rsna_diag import det_train as T  # noqa: E402

TRAIN = f"{BASE}/rsna_diag/det_train.py"
PY = sys.executable


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--migration", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    m = json.load(open(a.migration))
    cfg = m["config"]
    u0 = m["update_idx"]
    n = 3
    C = ["--manifest", cfg["manifest"], "--epochs", "26", "--effective_batch", str(cfg["effective_batch"]),
         "--microbatch", str(cfg["microbatch"]), "--lr", str(cfg["lr"]), "--lr_drop_epochs",
         *[str(x) for x in cfg["lr_drop_epochs"]], "--seed", str(cfg["seed"]), "--device", "0", "--trace"]
    res = {"update_idx": u0}
    runs = {}
    for tag in ("a", "b"):
        d = os.path.join(a.out, f"next_{tag}")
        with open(os.path.join(a.out, f"next_{tag}.log"), "w") as f:
            rc = subprocess.run([PY, TRAIN, "train", "--run_dir", d, "--init_from", m["source_checkpoint"],
                                 "--migration", a.migration, "--prefix_log", m["source_log"],
                                 "--stop_after", str(u0 + n)] + C, stdout=f, stderr=subprocess.STDOUT).returncode
        res[f"rc_{tag}"] = rc
        recs, orph = T.canonical_log(d)
        runs[tag] = {r["update"]: r for r in recs}
        res[f"canonical_n_{tag}"] = len(recs)
        res[f"canonical_first_{tag}"] = recs[0]["update"] if recs else None
    ids = json.load(open(T.find_manifest(cfg["manifest"])))["ids"]
    upe = len(ids) // cfg["effective_batch"]
    seed, eb = cfg["seed"], cfg["effective_batch"]
    exp = {}
    rng = None
    for upd in range(0, u0 + n):
        e, pos = upd // upe, upd % upe
        if pos == 0:
            rng = random.Random(seed * 1000 + e)
        perm = T.epoch_perm(seed, e, len(ids))
        bidx = perm[pos * eb:(pos + 1) * eb]
        exp[upd] = ([ids[i] for i in bidx], [rng.random() < cfg["flip_p"] for _ in bidx])
    rows = []
    for upd in range(u0, u0 + n):
        ra, rb = runs["a"][upd], runs["b"][upd]
        rows.append({"update": upd, "ids_flips_match_replay": (ra["sample_ids"], ra["flips"]) == exp[upd]
                     and (rb["sample_ids"], rb["flips"]) == exp[upd],
                     "input_digest_equal": ra["input_digest"] == rb["input_digest"],
                     "lr_applied": [ra["lr_applied"], rb["lr_applied"]], "loss": [ra["loss"], rb["loss"]],
                     "grad_norm": [ra["grad_norm"], rb["grad_norm"]], "params_equal": ra["params_digest"] == rb["params_digest"]})
    old = [json.loads(l) for l in open(m["source_log"]) if l.strip()]
    last = [r["loss"] for r in old[-100:]]
    res["rows"] = rows
    res["old_last100_loss_range"] = [min(last), max(last)]
    first = rows[0]
    res["prefix_records_linked"] = res["canonical_first_a"] == 0 and res["canonical_n_a"] == u0 + n
    res["pass"] = bool(res["rc_a"] == 3 and res["rc_b"] == 3 and all(r["ids_flips_match_replay"] and r["input_digest_equal"]
                                                                       and r["lr_applied"] == [0.005, 0.005] for r in rows)
                       and abs(first["loss"][0] - first["loss"][1]) <= 1e-6
                       and min(last) <= first["loss"][0] <= max(last) and res["prefix_records_linked"])
    json.dump(res, open(os.path.join(a.out, "next_update_check.json"), "w"), indent=2)
    print(json.dumps(res, indent=1))
    sys.exit(0 if res["pass"] else 1)


if __name__ == "__main__":
    main()
