"""iter_014 stage config (결과를 보기 전에 고정). 사용: python -m rsna_diag.geo_stages --out-dir results/iter_014/stage [--compute-updates K]

sanity   : 동작·재개 검사 (sanity16, val8, 2 epochs x 4 examples/update). 본실험 미사용.
pilot_mb : 처리량·메모리 pilot (sanity16, eff16, 3 epochs, validation 없음). 본실험 weight 이월 없음.
explore  : 가능성 탐색. train1200 (iter_013 explore와 동일 ID·seed·일정), V200, seed17, 3 epochs x 75 updates, peak LR 2e-5. milestone = update 75/150/225.
full     : 확대. train 2,400 전체, seed17, 3 epochs x 150 updates = 450 updates, LR 2e-5. milestone = update 150/300/450.
compute  : C_compute (계산량 대조 SFT). K = 450 * ceil(max(1, r)) updates (r = pilot의 G/C 학습 시간 비율; epoch 경계·3등분 milestone에 맞춰 450 단위로 올림).
공통: 부모 = iter_012 seed17 epoch_05 adapter, 5% warmup + cosine(0), effective batch 16 (sanity는 4), optimizer 새로 초기화.
"""
import argparse
import hashlib
import json
import math
import os

from . import adapt_stages as AS

CAND = "results/iter_014/candidates/train_candidates.json"


def stage(sid, seed, train_ids, val_ids, epochs, eff, validate, note):
    d = AS.stage(sid, seed, train_ids, val_ids, epochs, eff, [2e-5], validate, note)
    d["cand_manifest"] = CAND
    d["cand_manifest_sha256"] = hashlib.sha256(open(CAND, "rb").read()).hexdigest()
    d["loss_spec"] = "geo_loss.py: L=[CE_outside_spans + sum_b n_b sum_m q_bm ell_bm]/N; alpha/tau(iter_013)는 사용하지 않는다"
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--compute-updates", type=int, default=None)
    a = ap.parse_args()
    S = AS.S
    MI = AS.MI
    cfgs = {
        "sanity": stage("sanity", 17, S + "sanity16_ids.json", S + "val8_ids.json", 2, 4, True, "동작·재개 검사 (결정적 kernel), 본실험 미사용"),
        "pilot_mb": stage("pilot_mb", 17, S + "sanity16_ids.json", S + "val8_ids.json", 3, 16, False, "branch microbatch·처리량·메모리 pilot"),
        "pilot_thr": stage("pilot_thr", 17, S + "thr48_ids.json", S + "val8_ids.json", 2, 16, False, "G/C 학습 시간 비율 r 측정 (thr48: train 분포 층화 24 양성+24 음성, train1200 밖)"),
        "explore": stage("explore", 17, S + "train1200_ids.json", S + "v200_ids.json", 3, 16, True, "가능성 탐색 (1,200 train, V200)"),
        "full": stage("full", 17, MI + "train_ids.json", S + "v200_ids.json", 3, 16, True, "확대 (train 2,400, V200)"),
    }
    if a.compute_updates:
        k = a.compute_updates
        assert k % 450 == 0 and k >= 450
        cfgs["compute"] = stage("compute", 17, MI + "train_ids.json", S + "v200_ids.json", k // 150, 16, True,
                                f"C_compute: K={k} updates, milestone {k // 3}/{2 * k // 3}/{k} (epoch 경계)")
        e = k // 150
        cfgs["compute"]["milestone_epochs"] = [e // 3, 2 * e // 3, e]
    os.makedirs(a.out_dir, exist_ok=True)
    for k, v in cfgs.items():
        p = os.path.join(a.out_dir, f"{k}.json")
        if os.path.exists(p):
            assert json.load(open(p)) == v, f"{p} exists and differs (not overwritten)"
            print(k, "ok")
        else:
            json.dump(v, open(p, "w"), indent=1)
            print(k, "written")


if __name__ == "__main__":
    main()
