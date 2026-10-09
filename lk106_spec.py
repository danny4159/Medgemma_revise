"""iter_106 고정 명세: CURE PG 복합·반복 요청 구성, 좌표 추출, 최대 일대일 matching 평가(순수 함수, GPU 미사용).

 - I  : 기존 독립 PG 두 출력(S1, S2)의 box multiset 단순 결합(NMS/중복 제거 없음). iter_105 E32 출력 재사용 + D4는 재측정.
 - J12: "Ground the phrase: S1 S2", J21: "Ground the phrase: S2 S1" (공백 하나), R11/R22: 같은 소견 반복.
 - 평가는 문장별 binding 없이 main GT box 두 개와 예측 multiset 사이 IoU>=0.3 최대 일대일 matching이다.
"""
import itertools
import json
import math
import re

SYSTEM = "CURE"
IOU_THR = 0.3
NEW_CONDS = ["J12", "J21", "R11", "R22"]
IND_CONDS = ["I1", "I2"]
BR4 = re.compile(r"\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]")


def pg_prompt(sentence):
    return f"Ground the phrase: {sentence}"


def cond_prompt(cond, row):
    s1, s2 = row["S1"], row["S2"]
    sent = {"I1": s1, "I2": s2, "J12": f"{s1} {s2}", "J21": f"{s2} {s1}", "R11": f"{s1} {s1}", "R22": f"{s2} {s2}"}[cond]
    return pg_prompt(sent)


def requests_for(rows, conds):
    """id = ImageID|CURE|<cond>. I1/I2 요청은 iter_105의 pg-S1/pg-S2와 prompt가 같다."""
    out = []
    for r in rows:
        for c in conds:
            out.append({"id": f"{r['ImageID']}|{SYSTEM}|{c}", "ImageID": r["ImageID"], "system": SYSTEM, "kind": "pg", "modality": "image",
                        "cond": c, "order": None, "prompt": cond_prompt(c, r)})
    assert len({q["id"] for q in out}) == len(out)
    return out


def cxcywh_to_xyxy(c):
    return [c[0] - c[2] / 2, c[1] - c[3] / 2, c[0] + c[2] / 2, c[1] + c[3] / 2]


def parse_pg(text, ended_eos):
    """status: truncated | coord_invalid | no_box | valid_nonempty. boxes는 원본 정규화 xyxy(clipping 없음).
    box가 하나라도 유한·양의 크기·[0,1] 범위가 아니면 해당 응답 전체가 coord_invalid(위치 회복 0)."""
    if not ended_eos:
        return {"status": "truncated", "boxes": []}
    boxes = []
    for m in BR4.finditer(text):
        c = [float(v) for v in m.groups()]
        if not all(math.isfinite(v) for v in c) or c[2] <= 0 or c[3] <= 0 or not all(0 <= v <= 1 for v in c):
            return {"status": "coord_invalid", "boxes": []}
        boxes.append(cxcywh_to_xyxy(c))
    return {"status": "valid_nonempty" if boxes else "no_box", "boxes": boxes}


def iou(a, b):
    iw = min(a[2], b[2]) - max(a[0], b[0])
    ih = min(a[3], b[3]) - max(a[1], b[1])
    inter = max(0.0, iw) * max(0.0, ih)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def match(gts, preds, thr=IOU_THR):
    """최대 일대일 matching(Kuhn). returns (matched_gt_indices:set, n_matched)."""
    adj = [[j for j, p in enumerate(preds) if iou(g, p) >= thr] for g in gts]
    owner = {}

    def aug(i, seen):
        for j in adj[i]:
            if j in seen:
                continue
            seen.add(j)
            if j not in owner or aug(owner[j], seen):
                owner[j] = i
                return True
        return False
    for i in range(len(gts)):
        aug(i, set())
    return set(owner.values()), len(owner)


def score_boxes(gts, preds):
    """returns dict(recall, matched_idx(정렬된 list; 보장 matching 중 하나), n_pred, n_unmatched).
    matched_idx는 matching이 여러 개일 때 GT 집합이 달라질 수 있으나, 2 GT 환경의 'GT 단위 회복'은
    각 GT가 어떤 최대 matching에서 회복 가능한지(rec_possible)로도 별도 기록한다."""
    idx, n = match(gts, preds)
    possible = [bool(match([g], preds)[1]) for g in gts]
    return {"recall": n / len(gts), "n_matched": n, "matched_idx": sorted(idx), "possible": possible, "n_pred": len(preds),
            "n_unmatched": len(preds) - n}


def f1_ann(n_matched, n_pred, n_gt):
    p = n_matched / n_pred if n_pred else 0.0
    r = n_matched / n_gt
    return 2 * p * r / (p + r) if p + r else 0.0


def sha_json(o):
    import hashlib
    return hashlib.sha256(json.dumps(o, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
