"""SFT target gate (iter_010): 모든 split의 GT를 학습 target으로 바꿔 정수 반올림 유효성, box 수, token 길이, 표본 pixel hash를 점검한다.

실패(반올림으로 유효성이 깨지는 표본)는 조용히 고치지 않고 목록으로 기록한 뒤 종료 코드 1로 끝낸다.
사용: python -m rsna_diag.data_gate
"""
import collections
import json
import sys

import numpy as np

from . import generate, prompts as P, sft_data

OUT = "results/iter_010/data_audit/target_gate.json"


def main():
    gt = json.load(open("results/iter_010/manifests/gt_manifest.json"))
    man = {json.loads(l)["id"]: json.loads(l) for l in open("results/iter_010/manifests/infer_manifest.jsonl") if l.strip()}
    import os
    os.environ.setdefault("HF_HOME", generate.HF_HOME)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    import transformers
    tok = transformers.AutoProcessor.from_pretrained(generate.MODEL_ID, revision=generate.MODEL_REVISION).tokenizer
    bad, res = [], {}
    for split in ("train", "validation", "confirm"):
        ids = sorted(i for i in gt if gt[i]["split"] == split)
        nb, ntok = collections.Counter(), []
        for i in ids:
            boxes = [b["yxyx_norm"] for b in gt[i]["boxes"]]
            try:
                t = sft_data.target_text(boxes)
            except ValueError as e:
                bad.append({"id": i, "err": str(e)})
                continue
            nb[len(boxes)] += 1
            ntok.append(len(tok(t + "<end_of_turn>", add_special_tokens=False)["input_ids"]))
        res[split] = {"n": len(ids), "n_boxes_dist": dict(sorted(nb.items())), "target_tokens_max": int(max(ntok)),
                      "target_tokens_mean": float(np.mean(ntok)), "target_tokens_p99": float(np.percentile(ntok, 99))}
    # 파일 hash 재검증 (manifest vs 디스크)
    import hashlib
    mism = [i for i in man if hashlib.sha256(open(man[i]["image"], "rb").read()).hexdigest() != man[i]["file_sha256"]]
    res["file_sha_mismatch"] = mism
    res["rounding_failures"] = bad
    json.dump(res, open(OUT, "w"), indent=1)
    print(json.dumps(res, indent=1))
    sys.exit(1 if bad or mism else 0)


if __name__ == "__main__":
    main()
