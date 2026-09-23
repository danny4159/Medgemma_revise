"""(image_id, class)별 target과 후속 pooling probe의 metric·대조군·집계 규약 (iter_006, CPU, float64).

Target 계약
- 주분석 클래스는 MAIN_CLASSES 4개로 고정한다 (순서 = 출력 channel 순서).
- target[i, k] = 영상 i에서 클래스 k의 bbox들만의 union occupancy (다른 클래스 box는 섞지 않는다).
- 해당 클래스 bbox가 없으면 observed[i, k] = False(unknown)이고 target은 0으로 채우되 loss·metric에서 제외한다.
  bbox 없음은 음성 GT가 아니다 (NIH bbox는 일부 finding에만 그려짐).
- fine 64×64 occupancy, coarse 16×16 = fine의 4×4 평균.

Probe 규약 (모델 추출·학습은 이번에 실행하지 않음)
- soft-IoU(p, t) = sum(p*t) / (sum(p) + sum(t) - sum(p*t)), 관측된 양성 target(sum(t) > 0)만 평가.
- coarse prediction = sigmoid(P(logits)), P = 4×4 평균 pooling (fine logits → coarse logits → sigmoid).
- 집계: 영상 안의 관측 클래스 점수를 먼저 평균 → patient macro(patient별 평균의 평균). 클래스별 결과는 따로.
- 위치 prior: train split의 클래스별 관측 target 평균 (fine/coarse 각각).
- image-swap: 같은 split·같은 클래스의 관측 영상 중 다른 patient로 가는 고정 derangement.
- bootstrap: patient 단위, 고정 seed로 만든 같은 재표집 index를 모든 방법에 적용 (paired).
"""
import random

import numpy as np

from . import targets as T

MAIN_CLASSES = ["Atelectasis", "Effusion", "Cardiomegaly", "Pneumonia"]
SWAP_SEED = 20260924
BOOT_SEED = 20260925


def image_class_targets(annotation, W, H, classes=MAIN_CLASSES):
    """annotation: [{"label", "xyxy"}, ...] → (fine[K,64,64], coarse[K,16,16], observed[K])."""
    K = len(classes)
    fine = np.zeros((K, T.FINE, T.FINE))
    observed = np.zeros(K, dtype=bool)
    for k, c in enumerate(classes):
        bl = [a["xyxy"] for a in annotation if a["label"] == c]
        if bl:
            fine[k] = T.bbox_union_occupancy(bl, W, H)
            observed[k] = True
    coarse = np.stack([T.coarse_from_fine(f) for f in fine])
    return fine, coarse, observed


def build_split_targets(manifest, classes=MAIN_CLASSES):
    rows = sorted(manifest, key=lambda r: (r["split"], int(r["patient_id"])))
    fine, coarse, obs = [], [], []
    for r in rows:
        f, c, o = image_class_targets(r["annotation"], r["width"], r["height"], classes)
        fine.append(f)
        coarse.append(c)
        obs.append(o)
    return {"image_id": np.array([r["image"] for r in rows]), "patient_id": np.array([r["patient_id"] for r in rows]),
            "split": np.array([r["split"] for r in rows]), "classes": np.array(classes),
            "fine": np.array(fine), "coarse": np.array(coarse), "observed": np.array(obs)}


# ---------------------------------------------------------------- metric·집계


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def coarse_prediction(fine_logits):
    """fine logits (..., 64, 64) → sigmoid(P(logits)) (..., 16, 16)."""
    s = fine_logits.shape
    x = fine_logits.reshape(s[:-2] + (s[-2] // T.POOL, T.POOL, s[-1] // T.POOL, T.POOL))
    return sigmoid(x.mean(axis=(-3, -1)))


def soft_iou(p, t):
    """관측 양성 target만 받는다. sum(t) == 0이면 ValueError (음성·unknown은 평가 대상이 아님)."""
    p = np.asarray(p, dtype=np.float64)
    t = np.asarray(t, dtype=np.float64)
    st = t.sum()
    if not st > 0:
        raise ValueError("soft-IoU is defined only for observed positive targets")
    inter = (p * t).sum()
    return float(inter / (p.sum() + st - inter))


def masked_bce(logits, target, observed):
    """관측 클래스 channel만 평균 (unknown channel은 loss에 기여하지 않음). logits/target: (N,K,H,W)."""
    lg = np.asarray(logits, dtype=np.float64)
    t = np.asarray(target, dtype=np.float64)
    m = np.asarray(observed, dtype=bool)
    per = np.maximum(lg, 0) - lg * t + np.log1p(np.exp(-np.abs(lg)))  # 안정한 BCE-with-logits
    per = per.mean(axis=(-2, -1))  # (N,K)
    if not m.any():
        raise ValueError("no observed class")
    return float(per[m].mean())


def score_matrix(pred, target, observed):
    """pred/target (N,K,h,w) → scores (N,K), unknown은 NaN."""
    N, K = observed.shape
    out = np.full((N, K), np.nan)
    for i in range(N):
        for k in range(K):
            if observed[i, k]:
                out[i, k] = soft_iou(pred[i, k], target[i, k])
    return out


def aggregate(scores, observed, patient_id):
    """영상 안 관측 클래스 평균 → patient macro. 클래스별 평균(관측 영상만)도 반환."""
    per_image = np.array([scores[i, observed[i]].mean() if observed[i].any() else np.nan
                          for i in range(len(scores))])
    pats = sorted(set(patient_id.tolist()))
    per_patient = np.array([np.nanmean(per_image[patient_id == p]) for p in pats])
    per_class = [float(scores[observed[:, k], k].mean()) if observed[:, k].any() else None
                 for k in range(scores.shape[1])]
    return {"patient_macro": float(np.nanmean(per_patient)), "per_patient": per_patient, "patients": pats,
            "per_class": per_class, "n_patients": len(pats)}


def location_prior(targets, observed, split, train="train"):
    """train의 클래스별 관측 target 평균. targets (N,K,h,w) → (K,h,w)."""
    K = observed.shape[1]
    sel = split == train
    return np.stack([targets[sel & observed[:, k], k].mean(axis=0) for k in range(K)])


def image_swap_derangement(patient_id, split, observed, seed=SWAP_SEED):
    """클래스 k, split s마다 관측 영상 index의 고정 derangement (다른 patient로만 이동).

    반환: donor[N,K] (int, 관측 아님은 -1). 방법 m의 swap 점수는 pred[donor[i,k], k] 대 target[i,k].
    한 split·클래스의 관측 영상이 1개면 derangement가 없어 -1 (평가 제외, 보고).
    """
    N, K = observed.shape
    donor = np.full((N, K), -1, dtype=int)
    for k in range(K):
        for s in sorted(set(split.tolist())):
            idx = [i for i in range(N) if split[i] == s and observed[i, k]]
            idx.sort(key=lambda i: (int(patient_id[i]), i))
            if len(idx) < 2:
                continue
            rng = random.Random(f"{seed}|{k}|{s}")
            order = idx[:]
            rng.shuffle(order)
            # 섞은 순서에서 한 칸 이동(cyclic shift): 고정점이 없는 derangement
            for a, b in zip(order, order[1:] + order[:1]):
                donor[a, k] = b
    return donor


def bootstrap_indices(n_patients, B=2000, seed=BOOT_SEED):
    """patient 단위 재표집 index (B, n). 모든 방법에 같은 배열을 쓴다."""
    rng = np.random.default_rng(seed)
    return rng.integers(0, n_patients, size=(B, n_patients))


def paired_bootstrap_ci(per_patient_a, per_patient_b, idx, alpha=0.05):
    d = np.asarray(per_patient_a) - np.asarray(per_patient_b)
    bs = d[idx].mean(axis=1)
    return {"mean_diff": float(d.mean()), "ci_low": float(np.quantile(bs, alpha / 2)),
            "ci_high": float(np.quantile(bs, 1 - alpha / 2)), "B": int(idx.shape[0])}
