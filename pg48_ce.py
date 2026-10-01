"""iter_048 D24 teacher-forced CE (선택 자료, eval mode, no grad). adapter별로 두 형식의 token 평균 CE를 계산한다.
  I 형식: D24 48문장 (I-short prompt + 문장별 target)        J 형식: D24 24명 x {AB, BA} = 48 sequence (J-short prompt + 공동 target)
python pg48_ce.py --adapter results/iter_048/train/E_s17/epoch_02 --label E_e2 --out results/iter_048/decisions/ce_E_e2.json
GT는 target 구성에만 쓰이며 생성 요청에는 쓰이지 않는다 (D24는 선택 자료).
"""
import argparse
import hashlib
import json
import os
import sys
import time

import pg39_spec as S
import pg48_train as T
from rsna_diag import generate, lora, sft_data

MAN = "results/iter_043/data/manifest_private.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("exists")
    import torch
    t0 = time.time()
    man = json.load(open(MAN))
    d24 = man["D24"]
    _, proc, model = generate.load_model()
    adig = generate.load_adapter(torch, model, a.adapter)
    model.eval()
    softcap = getattr(model.config.get_text_config(), "final_logit_softcapping", None)
    pad = proc.tokenizer.pad_token_id
    tot = {"I": [0.0, 0, 0], "J_AB": [0.0, 0, 0], "J_BA": [0.0, 0, 0]}
    with torch.no_grad():
        for e in d24:
            image, _, pxs = generate.load_image(e["image"])
            if pxs != e["input_pixel_sha256"]:
                raise RuntimeError("D24 image hash mismatch")
            gtc = e["gt_canvas_yxyx"]
            seqs = {"I": [(S.prompt_I_short(e["sentences"][p], p), T.target_text(gtc[p], p)) for p in ("qA", "qB")],
                    "J_AB": [(S.prompt_J_short([("qA", e["sentences"]["qA"]), ("qB", e["sentences"]["qB"])]), T.joint_target_text(gtc, ("qA", "qB")))],
                    "J_BA": [(S.prompt_J_short([("qB", e["sentences"]["qB"]), ("qA", e["sentences"]["qA"])]), T.joint_target_text(gtc, ("qB", "qA")))]}
            for k, lst in seqs.items():
                exs = [sft_data.build_example(proc, image, *pt) for pt in lst]
                ce, n, _ = T.group_losses(torch, model, exs, pad, softcap, 1)
                tot[k][0] += float(ce.sum())
                tot[k][1] += int(n.sum())
                tot[k][2] += len(lst)
    out = {"label": a.label, "adapter": a.adapter, "adapter_digest": adig, "adapter_file_sha256": hashlib.sha256(open(os.path.join(a.adapter, "adapter.pt"), "rb").read()).hexdigest(),
           "ce_token_mean": {k: v[0] / v[1] for k, v in tot.items()}, "n_tokens": {k: v[1] for k, v in tot.items()}, "n_sequences": {k: v[2] for k, v in tot.items()},
           "ce_J_both_orders_token_mean": (tot["J_AB"][0] + tot["J_BA"][0]) / (tot["J_AB"][1] + tot["J_BA"][1]), "manifest_sha256": hashlib.sha256(open(MAN, "rb").read()).hexdigest(),
           "source_sha256": {f: hashlib.sha256(open(f, "rb").read()).hexdigest() for f in ("pg48_ce.py", "pg48_train.py")}, "wall_s": time.time() - t0,
           "cuda_visible": os.environ.get("CUDA_VISIBLE_DEVICES")}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    tmp = a.out + f".{os.getpid()}.tmp"
    json.dump(out, open(tmp, "w"), indent=1)
    os.replace(tmp, a.out)
    print(json.dumps(out["ce_token_mean"]))


if __name__ == "__main__":
    main()
