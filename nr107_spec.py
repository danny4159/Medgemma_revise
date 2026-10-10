"""iter_107 고정 명세: 요청 구성(공식 CURE 단일 phrase grounding), 엄격 parser, 핵심 집단 규칙, 사건 정의.

순수 함수만 둔다(모델·GPU 미사용). 정답(GT/extra)은 모델 요청에 들어가지 않는다.
parser는 malformed bracket / 세 숫자 / nan·inf / 비양수 폭·높이 / 범위 밖 / 좌표 없는 prose를 구분한다. clipping으로 오류를 숨기지 않는다.
"""
import math
import re

import nr107_geom as G

SYSTEM = "CURE"
CORE_IOU_MATCH = 0.5
COV_HIGH, COV_LOW = 0.5, 0.1
GROUP_RE = re.compile(r"\[([^\[\]]*)\]")
NUM_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$|^[+-]?(?:nan|inf|infinity)$", re.I)


def pg_prompt(sentence):
    return f"Ground the phrase: {sentence}"


def request_id(image_id, finding_index):
    return f"{image_id}|{SYSTEM}|pg-f{finding_index}"


def requests_for(items):
    out = []
    for it in items:
        out.append({"id": request_id(it["ImageID"], it["finding_index"]), "ImageID": it["ImageID"], "system": SYSTEM, "kind": "pg",
                    "modality": "image", "cond": "PG", "order": None, "item_key": it["item_key"], "prompt": pg_prompt(it["sentence"])})
    assert len({q["id"] for q in out}) == len(out)
    return out


def parse_pg(text, ended_eos):
    """returns dict(status, boxes(xyxy norm, 원본 좌표계), n_groups, n_bad). status:
    truncated | no_box | malformed | coord_invalid | valid_nonempty.
    부분 유효(일부 group만 유효)는 invalid로 처리하고 boxes=[] 로 둔다(valid_boxes는 별도 보존)."""
    if not ended_eos:
        return {"status": "truncated", "boxes": [], "valid_boxes": [], "n_groups": 0, "n_bad": 0}
    groups = GROUP_RE.findall(text)
    stripped = GROUP_RE.sub("", text)
    unbalanced = "[" in stripped or "]" in stripped
    boxes, bad_malformed, bad_coord = [], 0, 0
    for g in groups:
        parts = [p.strip() for p in g.split(",")]
        if len(parts) != 4 or not all(NUM_RE.match(p) for p in parts):
            bad_malformed += 1
            continue
        c = [float(p) for p in parts]
        if not all(math.isfinite(v) for v in c):
            bad_coord += 1
            continue
        if c[2] <= 0 or c[3] <= 0 or not all(0 <= v <= 1 for v in c):
            bad_coord += 1
            continue
        xy = [c[0] - c[2] / 2, c[1] - c[3] / 2, c[0] + c[2] / 2, c[1] + c[3] / 2]
        if xy[0] < 0 or xy[1] < 0 or xy[2] > 1 or xy[3] > 1:
            bad_coord += 1
            continue
        boxes.append(xy)
    n_bad = bad_malformed + bad_coord + (1 if unbalanced else 0)
    if bad_malformed or unbalanced:
        status = "malformed"
    elif bad_coord:
        status = "coord_invalid"
    elif boxes:
        status = "valid_nonempty"
    else:
        status = "no_box"
    return {"status": status, "boxes": boxes if status == "valid_nonempty" else [], "valid_boxes": boxes, "n_groups": len(groups), "n_bad": n_bad}


def core_status(gt, extra):
    """핵심 집단 규칙: 공식·대체 주석이 각각 정확히 2 box, 집합 내부 서로 겹치지 않음, 두 집합 사이 일대일 대응 각 IoU>=0.5.
    returns (is_core, pairing) — pairing[i] = extra box index matched to gt box i."""
    if len(gt) != 2 or len(extra) != 2:
        return False, None
    if not (G.pairwise_disjoint(gt) and G.pairwise_disjoint(extra)):
        return False, None
    ok_id = G.iou(gt[0], extra[0]) >= CORE_IOU_MATCH and G.iou(gt[1], extra[1]) >= CORE_IOU_MATCH
    ok_sw = G.iou(gt[0], extra[1]) >= CORE_IOU_MATCH and G.iou(gt[1], extra[0]) >= CORE_IOU_MATCH
    if ok_id and ok_sw:  # 양쪽 대응이 모두 가능하면 IoU 합이 큰 쪽을 택한다(동률이면 핵심 제외 = 모호)
        s_id = G.iou(gt[0], extra[0]) + G.iou(gt[1], extra[1])
        s_sw = G.iou(gt[0], extra[1]) + G.iou(gt[1], extra[0])
        if s_id == s_sw:
            return False, None
        return True, [0, 1] if s_id > s_sw else [1, 0]
    if ok_id:
        return True, [0, 1]
    if ok_sw:
        return True, [1, 0]
    return False, None


def cov_pair(pred, a, b):
    return G.coverage(pred, a), G.coverage(pred, b)


def classify_event(pred_boxes, gt, extra, pairing):
    """핵심 소견의 '주석 일치 부분 누락' 판정. 근거 k = (gt[k], extra[pairing[k]]).
    recovered(k): 두 주석 모두 coverage>=0.5 / missing(k): 두 주석 모두 coverage<=0.1.
    한 근거 recovered & 다른 근거 missing -> 'partial_omission'. 둘 다 recovered -> 'both_retained', 둘 다 missing -> 'both_missing'.
    그 외(0.1~0.5 사이 또는 주석별 방향 불일치) -> 'ambiguous'. 예측이 없거나 invalid면 coverage 0 이므로 both_missing."""
    cov = []
    for k in range(2):
        cg = G.coverage(pred_boxes, gt[k])
        ce = G.coverage(pred_boxes, extra[pairing[k]])
        if cg >= COV_HIGH and ce >= COV_HIGH:
            d = "recovered"
        elif cg <= COV_LOW and ce <= COV_LOW:
            d = "missing"
        else:
            d = "ambiguous"
        cov.append({"cov_official": cg, "cov_alt": ce, "dir": d})
    dirs = [c["dir"] for c in cov]
    if "ambiguous" in dirs:
        ev = "ambiguous"
    elif dirs == ["recovered", "recovered"]:
        ev = "both_retained"
    elif dirs == ["missing", "missing"]:
        ev = "both_missing"
    else:
        ev = "partial_omission"
    return ev, cov


def item_metrics(pred_boxes, gts):
    """한 주석 집합(gts)에 대한 기술통계."""
    covs = [G.coverage(pred_boxes, g) for g in gts]
    mt, ng, npred = G.match_recall(pred_boxes, gts, 0.3)
    return {"union_iou": G.union_iou(pred_boxes, gts), "cov": covs, "cov_min": min(covs), "cov_mean": sum(covs) / len(covs),
            "all_cov_ge_0.5": all(c >= 0.5 for c in covs), "outside_frac": G.outside_fraction(pred_boxes, gts),
            "match03": mt, "n_gt": ng, "n_pred": npred}
