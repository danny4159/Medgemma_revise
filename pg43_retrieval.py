"""iter_043 문장 retrieval baseline P (CPU only, 학습 없음). T305의 610문장/공식 box 집합만 사용한다. 평가 GT·labels·locations는 특징으로 쓰지 않는다.

설정 4개: {word 1-2gram, char 3-5gram} x k in {1, 5}. TF-IDF: tf=원시 count, idf=ln((1+n)/(1+df))+1 (T305 610문장에서만 계산), L2 정규화, cosine.
질의 문장은 lower-case + 공백 정리만 적용한다. 유사도 동률/전부 0은 고정 hash 순서(seed 4304)로 처리한다.
k=1: 최상위 문장의 전체 box 집합. k=5: 상위 5개 이웃의 box 집합 중 나머지 4개와의 평균 pairwise set-F1@0.3이 가장 높은 것(medoid); 동률은 순위가 앞선 이웃.
반환은 원본 normalized xyxy (영상 크기와 무관) — 대상 영상의 canvas 좌표로의 변환은 호출자가 한다.
"""
import hashlib
import math
import re
from collections import Counter

import numpy as np

import pg39_spec as S39

SEED = 4304
SETTINGS = [("word", 1), ("word", 5), ("char", 1), ("char", 5)]  # 동률 시 앞선 것 (k=1 우선, word 우선)의 순서와 함께 고정
TIE_ORDER = [("word", 1), ("char", 1), ("word", 5), ("char", 5)]  # 동률: k=1 먼저, word 먼저


def normalize(s):
    return " ".join(s.lower().split())


def features(text, kind):
    t = normalize(text)
    if kind == "word":
        w = re.findall(r"\w+", t)
        return Counter(w + [f"{a} {b}" for a, b in zip(w, w[1:])])
    if kind == "char":
        c = Counter()
        for n in (3, 4, 5):
            for i in range(len(t) - n + 1):
                c[t[i:i + n]] += 1
        return c
    raise ValueError(kind)


class Index:
    def __init__(self, train_sentences, train_boxes, kind):
        """train_sentences: list[str]; train_boxes: list[list[xyxy norm]]."""
        self.kind = kind
        self.sent = train_sentences
        self.boxes = train_boxes
        docs = [features(s, kind) for s in train_sentences]
        df = Counter()
        for d in docs:
            df.update(d.keys())
        self.vocab = {t: i for i, t in enumerate(sorted(df))}
        n = len(docs)
        self.idf = np.array([math.log((1 + n) / (1 + df[t])) + 1.0 for t in sorted(df)])
        self.M = np.stack([self._vec(d) for d in docs])

    def _vec(self, feat):
        v = np.zeros(len(self.vocab))
        for t, c in feat.items():
            i = self.vocab.get(t)
            if i is not None:
                v[i] = c * self.idf[i]
        nrm = np.linalg.norm(v)
        return v / nrm if nrm > 0 else v

    def ranking(self, query):
        q = self._vec(features(query, self.kind))
        sims = self.M @ q
        tie = [hashlib.sha256(f"{SEED}|{normalize(query)}|{j}|{normalize(self.sent[j])}".encode()).hexdigest() for j in range(len(sims))]
        order = sorted(range(len(sims)), key=lambda j: (-round(float(sims[j]), 12), tie[j]))
        return order, sims


def _yx(b):
    return [b[1], b[0], b[3], b[2]]


def set_f1(a, b, thr=0.3):
    return S39.sent_metrics([_yx(x) for x in a], [_yx(x) for x in b], thr)["f1"]


def predict(index, query, k):
    """returns (boxes_xyxy_norm, info)."""
    order, sims = index.ranking(query)
    if k == 1:
        j = order[0]
        return index.boxes[j], {"neighbors": [j], "sim": [float(sims[j])], "chosen": j}
    top = order[:k]
    best, best_s = None, -1.0
    for r, j in enumerate(top):
        s = float(np.mean([set_f1(index.boxes[j], index.boxes[o]) for o in top if o != j]))
        if s > best_s + 1e-12:
            best, best_s = j, s
    return index.boxes[best], {"neighbors": top, "sim": [float(sims[j]) for j in top], "chosen": best, "medoid_score": best_s}


def build(man):
    """man: manifest_private.json dict. returns {kind: Index}."""
    sents, boxes = [], []
    for x in man["T305"]:
        for t in ("qA", "qB"):
            sents.append(x["sentences"][t])
            boxes.append(x["gt_boxes_xyxy_norm"][t])
    assert len(sents) == 610
    return {kind: Index(sents, boxes, kind) for kind in ("word", "char")}


def predictions(indices, entries, setting):
    """entries: manifest 환자 목록. returns {(PatientID, qID): (canvas_yxyx boxes, info)} (대상 영상의 canvas 좌표)."""
    kind, k = setting
    out = {}
    for e in entries:
        for t in ("qA", "qB"):
            nb, info = predict(indices[kind], e["sentences"][t], k)
            out[(e["PatientID"], t)] = (S39.gt_to_canvas(nb, e["h"], e["w"]), nb, info)
    return out


def patient_mean_f1(pred, entries, thr=0.3):
    """pred: predictions() 결과. 환자 평균(두 문장) F1@thr의 평균과 환자 배열."""
    vals = []
    for e in entries:
        f = [S39.sent_metrics(pred[(e["PatientID"], t)][0], e["gt_canvas_yxyx"][t], thr)["f1"] for t in ("qA", "qB")]
        vals.append(sum(f) / 2)
    return float(np.mean(vals)), vals
