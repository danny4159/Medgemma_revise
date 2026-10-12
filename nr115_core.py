"""iter_115: iter_114 저장 ledger(87개)에서 CURE/MSPC 차별 포착 MG 오류의 기하 유형을 기술하는 사후 CPU 분석 코어.

규약(결과를 본 뒤 정한 사후 분류. 사전등록·눈가림·독립 확인이 아니다. t·범주 우선순위는 결과에 맞춰 바꾸지 않는다):
- 오류 정의는 iter_114 원 정의(union IoU(M, 공식 GT) < 0.3, 빈 M 은 오류)를 그대로 쓴다.
- u_j = area(M ∩ g_j) / area(g_j), t = 0.3 은 설명용 대응 기준이다(원 오류 정의를 대체하지 않음).
- 유형은 'MG 예측 M 대 해당 주석 집합'으로만 정하고 검토 목록 이름으로 바꾸지 않는다. 공식 GT 와 대체 주석(ALT)에 동일 적용한다.
"""
import hashlib

import nr107_geom as G
import nr113_core as B
import nr114_core as C

T_COVER = 0.3
TYPES = ("empty_pred", "no_overlap", "partial_low_coverage", "all_covered_area_mismatch", "other_overlap")
NON_ERR = "iou_ok"  # 해당 주석에 대해 원 오류 기준을 통과(오류 아님)
NA = "NA"  # 주석 없음 / 계산 불가


def u_values(m, gts):
    return [(G.inter_union_with_box(m, g) / G.area(g)) if (m and G.area(g) > 0) else 0.0 for g in gts]


def gt_boxes_overlap(gts):
    """주석 box 쌍 중 양의 면적으로 겹치는 쌍이 있는가."""
    for i in range(len(gts)):
        for j in range(i + 1, len(gts)):
            a, b = gts[i], gts[j]
            if min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1]):
                return True
    return False


def classify(m, gts, t=T_COVER):
    """MG 예측 m 대 주석 집합 gts 의 유형. gts 가 비면 NA."""
    if not gts:
        return NA
    if not m:
        return "empty_pred"
    if G.union_iou(m, gts) >= B.ERR_IOU:
        return NON_ERR
    inter = G.union_area_inter(m, gts)
    if inter <= 1e-15:
        return "no_overlap"
    u = u_values(m, gts)
    if len(gts) >= 2 and any(x >= t for x in u) and any(x < t for x in u):
        return "partial_low_coverage"
    if all(x >= t for x in u):
        return "all_covered_area_mismatch"
    return "other_overlap"


def row_metrics(l, e, sel):
    """ledger 한 행(l) + entry(e) + 선택 flag(sel: cure/mspc/conf) -> 전체 87행 표의 한 행."""
    M, Cc, P, GT, ALT = l["M"], l["C"], l["P"], l["GT"], l["ALT"]
    r = {"item_key": l["item_key"], "patient": l["PatientID"], "image_id": l["ImageID"], "finding_index": l["finding_index"],
         "sentence": l["cure_text"], "stage": l["stage"],
         "sel_cure": sel["cure"], "sel_mspc": sel["mspc"], "sel_conf": sel["confidence"],
         "error_official": e["e"], "error_alt": e["eh"], "annot_status": e["annot"],
         "n_M": len(M), "n_C": len(Cc), "n_P": len(P), "n_GT": len(GT), "n_ALT": len(ALT),
         "area_M": G.union_area(M), "area_C": G.union_area(Cc), "area_P": G.union_area(P),
         "area_GT": G.union_area(GT), "area_ALT": G.union_area(ALT) if ALT else None,
         "risk_conf": e["B"], "risk_cure": e["D"], "risk_mspc": e["P"],
         "iou_M_GT": G.union_iou(M, GT) if M else 0.0, "iou_C_GT": G.union_iou(Cc, GT) if Cc else 0.0,
         "iou_P_GT": G.union_iou(P, GT) if P else 0.0,
         "iou_M_ALT": (G.union_iou(M, ALT) if M else 0.0) if ALT else None,
         "iou_C_ALT": (G.union_iou(Cc, ALT) if Cc else 0.0) if ALT else None,
         "iou_P_ALT": (G.union_iou(P, ALT) if P else 0.0) if ALT else None,
         "iou_M_C": G.union_iou(M, Cc) if (M and Cc) else 0.0, "iou_M_P": G.union_iou(M, P) if (M and P) else 0.0,
         "cure_err_vs_GT": B.is_error(Cc, GT), "mspc_err_vs_GT": B.is_error(P, GT),
         "cure_status": l["cure_status"],
         "u_GT": u_values(M, GT), "u_ALT": u_values(M, ALT) if ALT else None,
         "outside_GT": G.outside_fraction(M, GT) if M else None,
         "GT_boxes_overlap": gt_boxes_overlap(GT), "ALT_boxes_overlap": gt_boxes_overlap(ALT) if ALT else None,
         "type_GT": classify(M, GT), "type_ALT": classify(M, ALT)}
    return r


def group_of(r):
    err = r["error_official"]
    c, p = r["sel_cure"], r["sel_mspc"]
    if err:
        return "err_cure_only" if (c and not p) else "err_mspc_only" if (p and not c) else "err_both" if (c and p) else "err_neither"
    return "ok_selected_by_cure_or_mspc" if (c or p) else "ok_not_selected"


GROUPS = ("err_cure_only", "err_mspc_only", "err_both", "err_neither", "ok_selected_by_cure_or_mspc", "ok_not_selected")


def rank_info(entries, field):
    """선택 순서 기반 1-기준 순위와 K 경계 동률 여부."""
    K = B.k_of(len(entries))
    order = sorted(range(len(entries)), key=lambda i: (-entries[i][field], entries[i]["tk"]))
    rank = {}
    for pos, i in enumerate(order):
        rank[i] = pos + 1
    kth, k1 = entries[order[K - 1]][field], entries[order[K]][field]
    return rank, {"K": K, "risk_at_K": kth, "risk_at_K+1": k1, "boundary_tie": kth == k1}


def aggregate(rows):
    out = {}
    for g in GROUPS:
        rs = [r for r in rows if group_of(r) == g]

        def cnt(key):
            d = {}
            for r in rs:
                d[r[key]] = d.get(r[key], 0) + 1
            return d

        def med(key):
            v = sorted(r[key] for r in rs if r[key] is not None)
            return None if not v else v[len(v) // 2] if len(v) % 2 else (v[len(v) // 2 - 1] + v[len(v) // 2]) / 2
        out[g] = {"n_items": len(rs), "n_patients": len({r["patient"] for r in rs}), "sel_conf": sum(r["sel_conf"] for r in rs),
                  "annot_status": cnt("annot_status"), "type_GT": cnt("type_GT"), "type_ALT": cnt("type_ALT"),
                  "cure_err_vs_GT": sum(r["cure_err_vs_GT"] for r in rs), "mspc_err_vs_GT": sum(r["mspc_err_vs_GT"] for r in rs),
                  "median_n_M": med("n_M"), "median_n_GT": med("n_GT"), "median_area_M": med("area_M"), "median_area_GT": med("area_GT"),
                  "median_iou_M_GT": med("iou_M_GT"), "median_iou_C_GT": med("iou_C_GT"), "median_iou_P_GT": med("iou_P_GT"),
                  "median_risk_cure": med("risk_cure"), "median_risk_mspc": med("risk_mspc"), "median_risk_conf": med("risk_conf"),
                  "n_GT_multi": sum(1 for r in rs if r["n_GT"] >= 2), "n_M_multi": sum(1 for r in rs if r["n_M"] >= 2)}
    return out


def sha_json(o):
    import json
    return hashlib.sha256(json.dumps(o, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
