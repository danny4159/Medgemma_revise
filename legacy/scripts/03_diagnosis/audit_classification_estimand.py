"""Audit: how much of the reported log-prob classification AUC is image signal?

Re-analyses eval_results/remedy_logprob.jsonl only (no inference, no new data).

The remedy report (docs, [해법 6]) states CheXpert AUC 0.700, p=0.0043 and reads
it as "discriminative signal is real". Two properties of that estimand are
checked here:
  1. ground truth policy: CheXpert rows were scored with gt = label in present,
     i.e. uncertain dropped and UNLABELED counted as negative ("U-zero").
  2. pooled AUC across 14 different label questions: a model that simply says
     "yes" more readily to some questions than others gains AUC without looking
     at the image, and a global label shuffle does not control for that.

Analyses (per dataset)
  A  pooled AUC as reported + the original global-shuffle permutation test
  B  label-controlled: per-label AUC, macro AUC over evaluable labels,
     leave-one-image-out label-only baseline, within-label centred pooled AUC,
     within-label permutation test, image-cluster bootstrap CI
  C  CheXpert explicit-only (present vs absent); labels lacking either class
     are recorded as "not estimable", never imputed as 0.5
NIH (complete binary labels) gets A and B as the control.

Output: eval_results/diagnostics_classification_estimand.json
"""
import json
from collections import Counter

import numpy as np

BASE = "/SSD1_1TB/home/milab/daniel/08_medgemma"
LOGPROB = f"{BASE}/eval_results/remedy_logprob.jsonl"
CHEX_META = f"{BASE}/eval_samples/not_in_training/chexpert/meta.json"
NIH_META = f"{BASE}/eval_samples/not_in_training/nih_chestxray14/meta.json"
OUT = f"{BASE}/eval_results/diagnostics_classification_estimand.json"

N_PERM = 10_000
N_BOOT = 10_000
SEED = 0


def auc(score, gt):
    """Pairwise (Mann-Whitney) AUC, ties count 1/2. None if a class is empty."""
    score, gt = np.asarray(score, float), np.asarray(gt, bool)
    pos, neg = score[gt], score[~gt]
    if len(pos) == 0 or len(neg) == 0:
        return None
    d = pos[:, None] - neg[None, :]
    return float(((d > 0).sum() + 0.5 * (d == 0).sum()) / d.size)


def per_label(rows):
    out = {}
    for lab in sorted({r["label"] for r in rows}):
        rs = [r for r in rows if r["label"] == lab]
        g = [r["y"] for r in rs]
        a = auc([r["score"] for r in rs], g)
        out[lab] = {"n_pos": int(sum(g)), "n_neg": int(len(g) - sum(g)),
                    "auc": a if a is not None else "not estimable"}
    return out


def macro(pl):
    v = [d["auc"] for d in pl.values() if d["auc"] != "not estimable"]
    return (float(np.mean(v)) if v else None), len(v)


def loio_label_baseline(rows):
    """Score each row by the mean score of the SAME label on the OTHER images."""
    base = []
    for r in rows:
        other = [q["score"] for q in rows
                 if q["label"] == r["label"] and q["file"] != r["file"]]
        base.append(np.mean(other))
    return np.array(base)


def centred(rows):
    """Subtract each label's mean score: removes per-question offsets entirely."""
    m = {lab: np.mean([r["score"] for r in rows if r["label"] == lab])
         for lab in {r["label"] for r in rows}}
    return np.array([r["score"] - m[r["label"]] for r in rows])


def analyse(rows, rng):
    s = np.array([r["score"] for r in rows])
    y = np.array([r["y"] for r in rows], bool)
    labs = np.array([r["label"] for r in rows])
    files = np.array([r["file"] for r in rows])
    ulabs = sorted(set(labs))
    idx_by_lab = {l: np.where(labs == l)[0] for l in ulabs}
    evaluable = [l for l in ulabs if 0 < y[idx_by_lab[l]].sum() < len(idx_by_lab[l])]

    def macro_auc(yy, ss=s):
        return float(np.mean([auc(ss[idx_by_lab[l]], yy[idx_by_lab[l]]) for l in evaluable]))

    pooled = auc(s, y)
    pl = per_label(rows)
    mac, n_eval = macro(pl)
    base = loio_label_baseline(rows)
    base_auc = auc(base, y)
    cent_auc = auc(centred(rows), y)

    # A: original test — shuffle gt across all 133/140 rows (breaks label structure)
    glob = np.empty(N_PERM)
    for i in range(N_PERM):
        glob[i] = auc(s, rng.permutation(y))
    # B: shuffle gt only among images of the same label (keeps per-label base rates)
    strat_pooled, strat_macro = np.empty(N_PERM), np.empty(N_PERM)
    for i in range(N_PERM):
        yy = y.copy()
        for l in ulabs:
            ix = idx_by_lab[l]
            yy[ix] = rng.permutation(y[ix])
        strat_pooled[i] = auc(s, yy)
        strat_macro[i] = macro_auc(yy)

    def p_ge(null, obs):
        return float((1 + (null >= obs - 1e-12).sum()) / (1 + len(null)))

    # image-cluster bootstrap: resample images, keep all their (label) rows
    ufiles = sorted(set(files))
    idx_by_file = {f: np.where(files == f)[0] for f in ufiles}
    bp, bm, bc = [], [], []
    n_macro_degenerate = 0
    for _ in range(N_BOOT):
        pick = rng.choice(ufiles, size=len(ufiles), replace=True)
        ix = np.concatenate([idx_by_file[f] for f in pick])
        a = auc(s[ix], y[ix])
        if a is not None:
            bp.append(a)
        # centred score recomputed inside the resample
        lb = labs[ix]
        means = {l: s[ix][lb == l].mean() for l in set(lb)}
        c = s[ix] - np.array([means[l] for l in lb])
        a = auc(c, y[ix])
        if a is not None:
            bc.append(a)
        ms = []
        for l in ulabs:
            jx = ix[labs[ix] == l]
            a = auc(s[jx], y[jx])
            if a is not None:
                ms.append(a)
        if ms:
            bm.append(np.mean(ms))
        else:
            n_macro_degenerate += 1

    def ci(v):
        return [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] if v else None

    return {
        "n_rows": int(len(rows)), "n_images": len(ufiles),
        "n_pos": int(y.sum()), "n_neg": int((~y).sum()),
        "A_pooled": {
            "auc": pooled,
            "global_shuffle_perm_p": p_ge(glob, pooled),
            "global_shuffle_null_95": [float(np.percentile(glob, 2.5)),
                                       float(np.percentile(glob, 97.5))],
        },
        "B_label_controlled": {
            "per_label": pl,
            "evaluable_labels": evaluable,
            "macro_auc": mac, "n_evaluable_labels": n_eval,
            "loio_label_only_baseline_auc": base_auc,
            "within_label_centred_pooled_auc": cent_auc,
            "within_label_perm": {
                "pooled_auc_p": p_ge(strat_pooled, pooled),
                "pooled_auc_null_mean": float(strat_pooled.mean()),
                "pooled_auc_null_95": [float(np.percentile(strat_pooled, 2.5)),
                                       float(np.percentile(strat_pooled, 97.5))],
                "macro_auc_p": p_ge(strat_macro, mac),
                "macro_auc_null_mean": float(strat_macro.mean()),
            },
            "image_cluster_bootstrap_95": {
                "pooled_auc": ci(bp),
                "within_label_centred_auc": ci(bc),
                "macro_auc": ci(bm),
                "n_boot": N_BOOT,
                "macro_note": "macro over labels evaluable in each resample",
                "n_macro_degenerate": n_macro_degenerate,
            },
        },
    }


def main():
    rng = np.random.default_rng(SEED)
    rows = [json.loads(l) for l in open(LOGPROB)]

    # ---- CheXpert: attach explicit status per (file, label) ----
    meta = {m["file"]: m for m in json.load(open(CHEX_META))}
    all_status = Counter(s for m in meta.values() for s in m["raw_codes"].values())
    assert all_status == {"present": 16, "absent": 14, "uncertain": 7, "unlabeled": 103}, all_status
    chex = [r for r in rows if r["dataset"] == "chexpert"]
    for r in chex:
        r["status"] = meta[r["file"]]["raw_codes"][r["label"]]
        assert r["gt"] == int(r["status"] == "present"), r   # stored gt == U-zero policy
    st = Counter(r["status"] for r in chex)
    assert st == {"present": 16, "absent": 14, "unlabeled": 103}, st
    assert len(chex) == 133

    uzero = [dict(r, y=int(r["status"] == "present")) for r in chex]
    explicit = [dict(r, y=int(r["status"] == "present"))
                for r in chex if r["status"] in ("present", "absent")]
    assert len(explicit) == 30
    ex_pl = per_label(explicit)

    # ---- NIH: complete binary labels ----
    nmeta = {m["file"]: m for m in json.load(open(NIH_META))}
    nih = [r for r in rows if r["dataset"] == "nih_chestxray14"]
    for r in nih:
        present = [f for f in nmeta[r["file"]]["findings"].split("|") if f and f != "No Finding"]
        r["status"] = "present" if r["label"] in present else "absent"
        assert r["gt"] == int(r["status"] == "present")
    nih = [dict(r, y=r["gt"]) for r in nih]
    assert len(nih) == 140

    res = {
        "source": LOGPROB, "seed": SEED, "n_perm": N_PERM, "n_boot": N_BOOT,
        "chexpert_status_counts_all_140_pairs": dict(all_status),
        "chexpert_status_counts_scored_133_rows": dict(st),
        "chexpert_U_zero": analyse(uzero, rng),
        "chexpert_explicit_only": {
            "n_rows": len(explicit),
            "n_pos": int(sum(r["y"] for r in explicit)),
            "n_neg": int(len(explicit) - sum(r["y"] for r in explicit)),
            "per_label": ex_pl,
            "estimable_labels": [l for l, d in ex_pl.items() if d["auc"] != "not estimable"],
            "pooled_auc_NOT_INTERPRETABLE": auc([r["score"] for r in explicit],
                                                [r["y"] for r in explicit]),
            "verdict": None,
        },
        "nih_control": analyse(nih, rng),
    }
    ce = res["chexpert_explicit_only"]
    ce["verdict"] = ("not estimable" if len(ce["estimable_labels"]) < 2 else "estimable")

    json.dump(res, open(OUT, "w"), indent=2, ensure_ascii=False)

    # ---- console summary ----
    for name in ("chexpert_U_zero", "nih_control"):
        d = res[name]
        A, B = d["A_pooled"], d["B_label_controlled"]
        print("=" * 78)
        print(f"{name}: rows={d['n_rows']} images={d['n_images']} pos={d['n_pos']} neg={d['n_neg']}")
        print(f"  A pooled AUC {A['auc']:.3f}   global-shuffle p={A['global_shuffle_perm_p']:.4f}"
              f"  null95={[round(x, 3) for x in A['global_shuffle_null_95']]}")
        print("  B per-label:")
        for lab, v in B["per_label"].items():
            a = v["auc"] if isinstance(v["auc"], str) else f"{v['auc']:.3f}"
            print(f"     {lab:28s} pos={v['n_pos']:2d} neg={v['n_neg']:2d} auc={a}")
        wp, bs = B["within_label_perm"], B["image_cluster_bootstrap_95"]
        print(f"  macro AUC {B['macro_auc']:.3f} over {B['n_evaluable_labels']} labels"
              f"   within-label perm p={wp['macro_auc_p']:.4f}")
        print(f"  LOIO label-only baseline AUC {B['loio_label_only_baseline_auc']:.3f}")
        print(f"  within-label centred pooled AUC {B['within_label_centred_pooled_auc']:.3f}")
        print(f"  pooled AUC under within-label perm: p={wp['pooled_auc_p']:.4f}"
              f"  null mean={wp['pooled_auc_null_mean']:.3f}"
              f"  null95={[round(x, 3) for x in wp['pooled_auc_null_95']]}")
        print(f"  image-cluster bootstrap 95%: pooled={[round(x, 3) for x in bs['pooled_auc']]}"
              f"  centred={[round(x, 3) for x in bs['within_label_centred_auc']]}"
              f"  macro={[round(x, 3) for x in bs['macro_auc']]}")
    print("=" * 78)
    print(f"chexpert explicit-only: rows={ce['n_rows']} pos={ce['n_pos']} neg={ce['n_neg']}")
    for lab, v in ce["per_label"].items():
        a = v["auc"] if isinstance(v["auc"], str) else f"{v['auc']:.3f}"
        print(f"     {lab:28s} pos={v['n_pos']:2d} neg={v['n_neg']:2d} auc={a}")
    print(f"  estimable labels: {ce['estimable_labels']}  -> verdict: {ce['verdict']}")
    print(f"\nsaved -> {OUT}")


if __name__ == "__main__":
    main()
