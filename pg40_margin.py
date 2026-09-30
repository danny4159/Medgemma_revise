"""iter_040 보조 진단: teacher-forced 문장 조건부 margin (ell(q,Y) - ell(other q,Y))을 학습 adapter별로 V96의 대조 적격 환자에서 계산한다.
보조 근거일 뿐이며 실제 생성 F1을 대신하지 않는다. python pg40_margin.py --adapters B=dir C=dir M=dir --out results/iter_040/eval/margin_v96.json
"""
import argparse
import json
import os
import sys

import numpy as np

import pg39_spec as S
import pg40_train as T
from rsna_diag import generate, lora, sft_data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapters", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--subset", default="V96")
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("output exists")
    rows = [r for r in T.load_rows(T.EVAL_MANIFEST, {"V96"})]
    el = [r for r in rows if S.cross_iou_max(*(T.canvas_gt(r)[k] for k in ("qA", "qB"))) < 0.1]
    import torch
    torch_, proc, model = generate.load_model()
    lora.apply_lora(model, T.CFG["r"], T.CFG["alpha"], 0.0)
    model.eval()
    softcap = getattr(model.config.get_text_config(), "final_logit_softcapping", None)
    pad = proc.tokenizer.pad_token_id
    items = []
    for r in el:
        image, _, _ = generate.load_image(r["image_meta"]["path"])
        tx = T.patient_texts(r, True)
        items.append({"pos": {p: sft_data.build_example(proc, image, *tx["pos"][p]) for p in ("qA", "qB")},
                      "cross": {p: sft_data.build_example(proc, image, *tx["cross"][p]) for p in ("qA", "qB")}})
    out = {"n_eligible_patients": len(el), "subset": a.subset, "models": {}}
    for spec in a.adapters:
        name, d = spec.split("=", 1)
        blob = torch_.load(os.path.join(d, "adapter.pt"), map_location="cpu", weights_only=True)
        lora.load_lora_state(model, blob["state"])
        m, pr, ce = [], [], []
        for it in items:
            info = T.patient_step(torch_, model, it, pad, softcap, 1, 1, 0.1, T.CFG["margin"], 1, True, 1, backward=False)
            m += info["margin"]
            pr.append(info["pair"])
            ce.append(info["ce_sum"] / info["ntok"])
        out["models"][name] = {"adapter_digest": blob["digest"], "mean_teacher_forced_margin": float(np.mean(m)), "frac_sentences_margin_lt_0.1": float(np.mean([x < 0.1 for x in m])),
                               "mean_pair_hinge": float(np.mean(pr)), "mean_ce_token": float(np.mean(ce))}
        print(name, out["models"][name], flush=True)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(out, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
