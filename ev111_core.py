"""iter_111 판단·위치 공동 평가와 검토량 대조의 순수 함수. 입력은 ev111_link.py가 만든 ledger rows.
원 규칙(plan.md Evaluation): IoU 0.3 주 / 0.5 보조, 최대 일대일 matching(rsna_diag.metrics), 답 추출 ev109_extract_v1 무변경."""
import numpy as np

import ev108_spec as S8
import ev109_extract as X
from rsna_diag import geometry as G
from rsna_diag import metrics as M

THR_DET = 0.70
IOU_MAIN, IOU_AUX = 0.3, 0.5
SEED, NBOOT = 11117, 10000
CATS = ("opacity", "normal", "not_normal_no_opacity")


def prep(rows):
    """ledger rows -> 환자별 dict. 답/박스는 GT와 독립으로 만든다."""
    out = []
    for r in rows:
        top, left, side = r["pad"]
        d = r["det"]
        db, ds = [], []
        for b, s, l in zip(d["boxes_xyxy_px"], d["scores"], d["labels"]):
            if l != 1 or s < THR_DET:
                continue
            db.append(G.canvas_to_norm(b, top, left, side))
            ds.append(float(s))
        st, sb = S8.parse_saved_bbox(r["SFT"]["raw"], r["SFT"]["ended_eos"])
        ans = X.resolve("O", r["O"]["raw"], r["O"]["ended_eos"])
        out.append(dict(id=r["id"], cat=r["category"], gt=r["gt_yxyx_norm"], det=db, det_scores=ds,
                        sft=sb, sft_status=st, ans=ans["answer"], ans_source=ans["source"]))
    return out


def box_outcome(pred, gt, thr):
    """returns dict(tp, fp, fn, exact: GT 양성이면 TP==n_gt==n_pred, 음성이면 pred 비어 있음)."""
    tp = len(M.match(pred, gt, thr)) if pred and gt else 0
    fp, fn = len(pred) - tp, len(gt) - tp
    exact = (len(pred) == 0) if not gt else (tp == len(gt) == len(pred))
    return dict(tp=tp, fp=fp, fn=fn, exact=bool(exact))


def system_boxes(p, loc):
    """loc: det|sft -> (boxes, valid)."""
    if loc == "det":
        return p["det"], True
    return p["sft"], p["sft_status"] in ("ok", "empty")


def joint(p, loc, mode, thr):
    """mode: loc(박스 유무=존재 출력) | indep(reader 답 + localizer) | gate(reader No면 빈 박스).
    returns True/False/None(미해결). 박스를 쓰는데 localizer 출력이 invalid면 False."""
    boxes, valid = system_boxes(p, loc)
    pos = bool(p["gt"])
    if mode == "loc":
        if not valid:
            return False
        return box_outcome(boxes, p["gt"], thr)["exact"]
    a = p["ans"]
    if a is None:
        return None
    if mode == "gate" and a == "no":
        boxes, valid = [], True
    if not valid:
        return False
    if pos != (a == "yes"):
        return False
    return box_outcome(boxes, p["gt"], thr)["exact"]


def error_type(p):
    """detector 양성 출력(S)의 주 오류 Y와 유형. returns (Y, type)."""
    ok = box_outcome(p["det"], p["gt"], IOU_MAIN)["exact"]
    if ok:
        return False, "correct"
    return True, "neg_claim" if not p["gt"] else "pos_location"


def expected_found(score, Y, k):
    """score 낮은 순 k개 선택(경계 동률은 균등 기대값)으로 찾는 Y 합."""
    score, Y = np.asarray(score, float), np.asarray(Y, float)
    n = len(score)
    if k <= 0 or n == 0:
        return 0.0
    if k >= n:
        return float(Y.sum())
    srt = np.sort(score)
    v = srt[k - 1]
    lo = score < v
    tie = score == v
    j = k - int(lo.sum())
    return float(Y[lo].sum() + j / tie.sum() * Y[tie].sum())


def vec(P):
    """환자별 사전 계산(비싼 matching은 한 번만). 부트스트랩은 이 배열의 index 재표집으로 수행한다."""
    inS = np.array([bool(p["det"]) for p in P])
    et = [error_type(p) if p["det"] else (False, "none") for p in P]
    return dict(inS=inS, Y=np.array([e[0] for e in et]), typ=np.array([e[1] for e in et]),
                res=np.array([p["ans"] is not None for p in P]), no=np.array([p["ans"] == "no" for p in P]),
                smax=np.array([max(p["det_scores"]) if p["det"] else np.nan for p in P]),
                smin=np.array([min(p["det_scores"]) if p["det"] else np.nan for p in P]))


def endpoint(v, idx=None):
    """주 endpoint 구성요소. S=detector nonempty. idx가 있으면 해당 index(복원 추출)로 재계산(k·confidence 경계 모두 재계산)."""
    g = (lambda a: a) if idx is None else (lambda a: a[idx])
    m = g(v["inS"])
    if not m.any():
        return None
    Y, typ, res, no = g(v["Y"])[m], g(v["typ"])[m], g(v["res"])[m], g(v["no"])[m]
    smax, smin = g(v["smax"])[m], g(v["smin"])[m]
    n = len(Y)
    k, nr = int(no.sum()), int(res.sum())
    out = dict(n_S=n, n_Y=int(Y.sum()), n_unres=int((~res).sum()), n_resolved=nr, k=k)
    vlm = float(Y[no].sum())
    conf = expected_found(smax[res], Y[res], k)
    confmin = expected_found(smin[res], Y[res], k)
    out.update(found_vlm=vlm, found_conf=conf, found_confmin=confmin, ep=(vlm - conf) / n, ep_aux=(vlm - confmin) / n,
               Y_res=int(Y[res].sum()))
    for t in ("neg_claim", "pos_location"):
        mt = typ == t
        out[f"vlm_{t}"] = float((Y & no & mt).sum())
        out[f"conf_{t}"] = expected_found(smax[res], (Y & mt)[res], k)
        out[f"confmin_{t}"] = expected_found(smin[res], (Y & mt)[res], k)
        out[f"Y_{t}"] = int((Y & mt).sum())
    out["review_correct_removed_vlm"] = int((no & ~Y).sum())
    out["recall_vlm"] = vlm / out["Y_res"] if out["Y_res"] else float("nan")
    out["precision_vlm"] = vlm / k if k else float("nan")
    out["degenerate"] = bool(k == 0 or k == nr)
    return out


def endpoint_arrays(P):
    return endpoint(vec(P))


def boot(P, B=NBOOT, seed=SEED, keys=("ep", "ep_aux")):
    v = vec(P)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(P), size=(B, len(P)), dtype=np.int32)
    res = {k: [] for k in keys}
    res["pos_diff"], res["pos_diff_aux"], res["degenerate"] = [], [], 0
    for b in range(B):
        e = endpoint(v, idx[b])
        if e is None:
            continue
        for k in keys:
            res[k].append(e[k])
        res["pos_diff"].append((e["vlm_pos_location"] - e["conf_pos_location"]) / e["n_S"])
        res["pos_diff_aux"].append((e["vlm_pos_location"] - e["confmin_pos_location"]) / e["n_S"])
        res["degenerate"] += e["degenerate"]
    return res


def ci(v, lo=2.5, hi=97.5):
    v = np.asarray(v, float)
    return [float(np.percentile(v, lo)), float(np.percentile(v, hi))]


def assign_unresolved(P, mode):
    """미해결 답 배정으로 만든 복사본. mode: yes|no|adverse|favorable (adverse/favorable은 GT를 이용한 경계 계산용)."""
    Q = []
    for p in P:
        q = dict(p)
        if p["ans"] is None:
            if mode in ("yes", "no"):
                q["ans"] = mode
            else:
                Y, _ = error_type(p) if p["det"] else (False, None)
                flagged_adverse = bool(p["det"]) and not Y  # 올바른 출력을 검토 대상으로 소모
                flagged_fav = bool(p["det"]) and Y
                q["ans"] = "no" if (flagged_adverse if mode == "adverse" else flagged_fav) else "yes"
        Q.append(q)
    return Q


def system_table(P, loc, mode, thr):
    """전체/범주별 공동 성공과 보조 지표."""
    def one(sub):
        n = len(sub)
        js = [joint(p, loc, mode, thr) for p in sub]
        unres = sum(j is None for j in js)
        succ = sum(j is True for j in js)
        pos = [p for p in sub if p["gt"]]
        f1 = [M.patient_metrics(system_boxes(p, loc)[0], p["gt"], thr)["f1"] for p in pos] if pos else []
        hit = [M.patient_metrics(system_boxes(p, loc)[0], p["gt"], thr)["tp"] > 0 for p in pos] if pos else []
        fp = fn = 0
        for p in sub:
            b, _ = system_boxes(p, loc)
            if mode == "gate" and p["ans"] == "no":
                b = []
            o = box_outcome(b, p["gt"], thr)
            fp += o["fp"]
            fn += o["fn"]
        ex = None
        if mode != "loc":
            ex = float(np.mean([(p["ans"] == "yes") == bool(p["gt"]) for p in sub if p["ans"] is not None])) if any(p["ans"] is not None for p in sub) else None
        else:
            ex = float(np.mean([bool(system_boxes(p, loc)[0]) == bool(p["gt"]) for p in sub]))
        inv = sum(not system_boxes(p, loc)[1] for p in sub)
        return dict(n=n, joint=succ / n, joint_n=succ, unresolved=unres, joint_if_unres_fail=succ / n,
                    joint_best_case=(succ + unres) / n, existence_acc=ex, pos_f1=float(np.mean(f1)) if f1 else None,
                    pos_any_hit=float(np.mean(hit)) if hit else None, fp_per_patient=fp / n, fn_per_patient=fn / n, invalid_loc=inv)
    out = {"all": one(P)}
    for c in CATS:
        out[c] = one([p for p in P if p["cat"] == c])
    out["equal_weight_joint"] = float(np.mean([out[c]["joint"] for c in CATS]))
    return out
