"""iter_028 CPU fixture: AUROC/Capture/Platt/bootstrap 계산과 request_id/completion 검사 (GPU 불필요)."""
import json
import math
import os
import shutil

import numpy as np

from rsna_diag import risk28, risk28_eval as E

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


# --- AUROC ---
check("auroc_perfect", E.auroc([0.1, 0.2, 0.9, 0.8], [0, 0, 1, 1]) == 1.0)
check("auroc_reversed", E.auroc([0.9, 0.8, 0.1, 0.2], [0, 0, 1, 1]) == 0.0)
check("auroc_all_tie", E.auroc([0.5, 0.5, 0.5, 0.5], [0, 0, 1, 1]) == 0.5)
check("auroc_nan_no_pos", math.isnan(E.auroc([0.1, 0.2], [0, 0])))

# --- capture_at_k ---
scores = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.0]
y = [1, 0, 1, 0, 0, 0, 0, 0, 0, 1]
cap = E.capture_at_k(scores, y, frac=0.2)
check("capture_top2_of3pos", abs(cap - (1.0 / 3.0)) < 1e-9, cap)

scores_tie = [1, 1, 1, 1, 0, 0]
y_tie = [1, 0, 1, 0, 0, 0]
cap_tie = E.capture_at_k(scores_tie, y_tie, frac=1.0 / 3.0)
check("capture_tie_expected", abs(cap_tie - 0.5) < 1e-9, cap_tie)

# --- Platt ---
rng = np.random.default_rng(0)
z_true = rng.normal(size=400)
p_true = 1 / (1 + np.exp(-2.0 * z_true))
yb = (rng.uniform(size=400) < p_true).astype(int)
cal = E.fit_platt(z_true, yb)
check("platt_slope_nonneg", cal["a"] >= 0.0, cal["a"])
probs = E.apply_platt(cal, np.sort(z_true))
check("platt_monotonic", bool(np.all(np.diff(probs) >= -1e-12)))

const_cal = E.fit_platt(np.zeros(20), [1] * 5 + [0] * 15)
check("platt_constant_flag", const_cal["constant"] is True)
check("platt_constant_prob_between_0_1", 0.0 < E.apply_platt(const_cal, [0.0])[0] < 1.0)

# --- bootstrap CI sanity: known separated data -> AUROC CI should be tight near 1 ---
sc = np.array([0.1] * 50 + [0.9] * 50)
yy = np.array([0] * 50 + [1] * 50)


def f(idx):
    return E.auroc(sc[idx], yy[idx])


ci = E.metric_ci(f, len(sc), B=500, seed=1)
check("bootstrap_auroc_point_is_1", abs(ci["point"] - 1.0) < 1e-9, ci)

# --- risk28: independent CPU vs FP32 torch log-softmax agreement ---
try:
    import torch
    logits = torch.randn(2000, dtype=torch.float32) * 5
    nll_t, ent_t, logp_t = risk28.fp32_logsoftmax_stats(logits, 17)
    nll_c, ent_c = risk28.cpu_independent_logsoftmax_stats(logits.numpy(), 17)
    check("logsoftmax_nll_agree", abs(nll_t - nll_c) < 1e-4, (nll_t, nll_c))
    check("logsoftmax_entropy_agree", abs(ent_t - ent_c) < 1e-4, (ent_t, ent_c))
except ImportError:
    check("logsoftmax_skip_no_torch", True, "torch not available in this check")

# --- request_id determinism / distinctness ---
r1 = risk28.request_id("sft", "C", "val_00000021", "token_score")
r2 = risk28.request_id("sft", "C", "val_00000021", "token_score")
r3 = risk28.request_id("base", "C", "val_00000021", "token_score")
check("request_id_deterministic", r1 == r2)
check("request_id_variant_sensitive", r1 != r3)

# --- check_completion: missing/extra detection ---
tmp = "results/iter_028/tests/_tmp_completion"
shutil.rmtree(tmp, ignore_errors=True)
os.makedirs(tmp, exist_ok=True)
items = [{"id": f"p{i}", "image": "x.png"} for i in range(3)]


def rec(pid, task, variant):
    return {"id": pid, "task": task, "variant": variant, "image": "x.png"}


with open(os.path.join(tmp, "gen_sft_worker0.jsonl"), "w") as f:
    for pid in ("p0", "p1"):
        for t in risk28.TASKS_SFT:
            f.write(json.dumps(rec(pid, t, "sft")) + "\n")
with open(os.path.join(tmp, "gen_base_worker0.jsonl"), "w") as f:
    for pid in ("p0", "p1", "p2"):
        for t in risk28.TASKS_BASE:
            f.write(json.dumps(rec(pid, t, "base")) + "\n")
comp = risk28.check_completion(tmp, items, variants=("base", "sft"))
check("completion_detects_missing_sft_p2", not comp["ok"] and comp["counts"]["sft"]["missing"] == 3, comp)
check("completion_base_ok", comp["counts"]["base"]["missing"] == 0 and comp["counts"]["base"]["extra"] == 0)

with open(os.path.join(tmp, "gen_sft_worker1.jsonl"), "w") as f:
    for t in risk28.TASKS_SFT:
        f.write(json.dumps(rec("p0", t, "sft")) + "\n")
comp2 = risk28.check_completion(tmp, items, variants=("sft",))
check("completion_detects_duplicate", any("duplicate" in p for p in comp2["problems"]), comp2["problems"])
shutil.rmtree(tmp, ignore_errors=True)

n_pass = sum(1 for _, ok, _ in results if ok)
print(f"{n_pass}/{len(results)} PASS")
for name, ok, detail in results:
    if not ok:
        print("FAIL", name, detail)
os.makedirs("results/iter_028/tests", exist_ok=True)
json.dump({"n_pass": n_pass, "n_total": len(results),
           "results": [{"name": n, "ok": ok, "detail": str(d)} for n, ok, d in results]},
          open("results/iter_028/tests/fixtures_iter028.json", "w"), indent=1)
assert n_pass == len(results), "some fixtures failed"
