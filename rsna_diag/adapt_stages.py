"""iter_013 stage config 생성 (결과를 보기 전에 고정). 사용: python -m rsna_diag.adapt_stages --out-dir results/iter_013/stage

sanity / pilot_mb : 동작 확인·처리량 pilot (train sanity16). 본실험 weight로 이월하지 않는다.
explore           : 가능성 탐색. train1200, V200(val_ids), seed17, 3 epochs x 75 updates, peak LR 2e-5.
full_s17          : 확대. train 2,400 전체, seed17, 3 epochs x 150 updates, LR 2e-5/5e-5 (C·D, 그리고 D의 선택 LR에서 H).
full_s29 / s43    : 조건부 재현. 각 seed의 부모 epoch_05 adapter에서 시작 (부모 학습 seed까지 바뀐다).
공통: alpha=0.1, tau=1.0, 자리 가중 1,2,3,4, 5% warmup + cosine(0), effective batch 16 (sanity는 4). 부모 optimizer는 이어받지 않는다.
"""
import argparse
import hashlib
import json
import os

from . import lora

MI = "results/iter_010/manifests/"
S = "results/iter_013/subsets/"
PARENT = "results/iter_012/train/lr2e-4_s{}/epoch_05/adapter.pt"


def parent(seed):
    import torch
    p = PARENT.format(seed)
    b = torch.load(p, map_location="cpu", weights_only=True)
    dg = lora.state_digest(b["state"])
    assert b["digest"] == dg
    return {"parent_adapter": p, "parent_adapter_sha256": hashlib.sha256(open(p, "rb").read()).hexdigest(), "parent_adapter_digest": dg}


def stage(sid, seed, train_ids, val_ids, epochs, eff, lrs, validate, note):
    return {"stage_id": sid, "seed": seed, "train_ids": train_ids, "val_ids": val_ids, "epochs": epochs, "eff_batch": eff, "allowed_lrs": lrs,
            "warmup_frac": 0.05, "validate": validate, "alpha": 0.1, "tau": 1.0, "schedule": "5% warmup then cosine to 0 over this stage's total updates",
            "note": note, **parent(seed)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    cfgs = {
        "sanity": stage("sanity", 17, S + "sanity16_ids.json", S + "val8_ids.json", 2, 4, [2e-5], True, "동작·재개 검사 (결정적 kernel), 본실험 미사용"),
        "pilot_mb": stage("pilot_mb", 17, S + "sanity16_ids.json", S + "val8_ids.json", 3, 16, [2e-5], False, "microbatch 2 vs 4 처리량·메모리 pilot"),
        "explore": stage("explore", 17, S + "train1200_ids.json", S + "v200_ids.json", 3, 16, [2e-5], True, "가능성 탐색 (1,200 train, V200)"),
        "full_s17": stage("full_s17", 17, MI + "train_ids.json", S + "v200_ids.json", 3, 16, [2e-5, 5e-5], True, "확대 (train 2,400, V200)"),
        "full_s29": stage("full_s29", 29, MI + "train_ids.json", S + "v200_ids.json", 3, 16, [2e-5, 5e-5], True, "조건부 재현 (부모 seed29)"),
        "full_s43": stage("full_s43", 43, MI + "train_ids.json", S + "v200_ids.json", 3, 16, [2e-5, 5e-5], True, "조건부 재현 (부모 seed43)"),
    }
    for k, v in cfgs.items():
        p = os.path.join(a.out_dir, f"{k}.json")
        if os.path.exists(p):
            assert json.load(open(p)) == v, f"{p} exists and differs (not overwritten)"
        else:
            json.dump(v, open(p, "w"), indent=1)
        print(k, "written" if not os.path.exists(p) else "ok")


if __name__ == "__main__":
    main()
