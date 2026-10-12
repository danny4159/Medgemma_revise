"""iter_112 평가. 모델 출력(scores)과 GT를 이 단계에서만 결합한다. 규칙은 plan의 Evaluation 그대로이며 결과를 보고 바꾸지 않는다.
검토 단위=예측 box, 오류=환자 GT box와의 최대 IoU<0.3 (GT 없는 환자는 최대 IoU=0 -> 오류), 검토량 K=ceil(0.25N), 낮은 값부터 검토."""
import json
import math
import sys

import numpy as np

import mr112_spec as S
from rsna_diag import metrics as M

import os
D = os.environ.get("MR112_DIR", "results/iter_112")  # 합성 dry-run 검증용 override


def build_table(man, gt, sc):
    """sc: request_id -> record (mean_logprob). 환자 full score는 그 환자의 모든 box에 복제."""
    full = {}
    for q in man["requests"]:
        if q["group"] == "main" and q["kind"] == "full":
            full[q["id"]] = sc[q["request_id"]]["mean_logprob"]
    rows = {r["id"]: r for r in man["rows"]}
    T = []
    for q in man["requests"]:
        if q["group"] != "main" or q["kind"] != "region":
            continue
        r = rows[q["id"]]
        b = next(x for x in r["boxes"] if x["det_index"] == q["det_index"])
        g = gt[q["id"]]["boxes_xyxy_px"]
        mi = M.max_iou_all([b["xyxy_px"]], g)
        T.append(dict(id=q["id"], det_index=q["det_index"], conf=b["score"], region=sc[q["request_id"]]["mean_logprob"],
                      full=full[q["id"]], max_iou=mi, err3=mi < S.IOU_MAIN, err5=mi < S.IOU_AUX, gt_pos=bool(g)))
    T.sort(key=lambda t: (t["id"], t["det_index"]))
    return T


def order(T, which):
    """검토 순서 index (낮은 값부터). 동률: 낮은 confidence, patient id, box index (GT 미사용)."""
    key = {"conf": lambda t: (t["conf"], t["id"], t["det_index"]),
           "region": lambda t: (t["region"], t["conf"], t["id"], t["det_index"]),
           "full": lambda t: (t["full"], t["conf"], t["id"], t["det_index"])}[which]
    return sorted(range(len(T)), key=lambda i: key(T[i]))


def captured(T, which, err="err3"):
    K = S.n_review(len(T))
    top = order(T, which)[:K]
    return sum(T[i][err] for i in top), top


def summary(T, err="err3"):
    N = len(T)
    out = dict(N=N, K=S.n_review(N), n_err=sum(t[err] for t in T), n_patients=len({t["id"] for t in T}))
    tops = {}
    for w in ("conf", "region", "full"):
        c, top = captured(T, w, err)
        out["captured_" + w] = c
        tops[w] = set(top)
    out["diff_region_conf"] = (out["captured_region"] - out["captured_conf"]) / N
    out["diff_region_full"] = (out["captured_region"] - out["captured_full"]) / N
    out["diff_full_conf"] = (out["captured_full"] - out["captured_conf"]) / N
    for a, b in (("region", "conf"), ("region", "full")):
        ea = {i for i in tops[a] if T[i][err]}
        eb = {i for i in tops[b] if T[i][err]}
        out[f"{a}_vs_{b}"] = dict(common=len(ea & eb), added=len(ea - eb), lost=len(eb - ea),
                                  added_patients=len({T[i]["id"] for i in ea - eb}), lost_patients=len({T[i]["id"] for i in eb - ea}))
    # confidence 대비 환자별 순이득
    gain = {}
    for i in range(len(T)):
        e = T[i][err]
        if e:
            gain[T[i]["id"]] = gain.get(T[i]["id"], 0) + (i in tops["region"]) - (i in tops["conf"])
    out["patients_net_gain_vs_conf"] = sum(v > 0 for v in gain.values())
    out["patients_net_loss_vs_conf"] = sum(v < 0 for v in gain.values())
    return out


def bootstrap(T, B=10000, seed=112017, err="err3"):
    ids = sorted({t["id"] for t in T})
    by = {p: [t for t in T if t["id"] == p] for p in ids}
    rng = np.random.default_rng(seed)
    d1, d2 = [], []
    for _ in range(B):
        pick = rng.integers(0, len(ids), len(ids))
        Tb = []
        for c, k in enumerate(pick):
            for t in by[ids[k]]:
                Tb.append(dict(t, copy=c))
        # 동률 처리에 복제 index를 마지막 키로 추가
        N = len(Tb)
        K = S.n_review(N)

        def cap(which):
            if which == "conf":
                key = lambda t: (t["conf"], t["id"], t["det_index"], t["copy"])
            else:
                key = lambda t: (t[which], t["conf"], t["id"], t["det_index"], t["copy"])
            return sum(t[err] for t in sorted(Tb, key=key)[:K])
        c0, c1, c2 = cap("conf"), cap("region"), cap("full")
        d1.append((c1 - c0) / N)
        d2.append((c1 - c2) / N)
    q = lambda a: [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))]
    return dict(B=B, seed=seed, diff_region_conf_ci=q(d1), diff_region_full_ci=q(d2))


def leave_one_patient_out(T, err="err3"):
    ids = sorted({t["id"] for t in T})
    res = []
    for p in ids:
        s = summary([t for t in T if t["id"] != p], err)
        res.append((p, s["diff_region_conf"], s["diff_region_full"]))
    return dict(min_diff_region_conf=min(r[1] for r in res), max_diff_region_conf=max(r[1] for r in res),
                min_diff_region_full=min(r[2] for r in res), max_diff_region_full=max(r[2] for r in res))


def decide(s):
    pos = s["diff_region_conf"] >= 0.05 and s["diff_region_full"] >= 0.05 and s["patients_net_gain_vs_conf"] >= 3
    if s["diff_region_conf"] <= 0:
        return "negative: confidence 대비 추가 포착 없음 (현재 고정 scoring 경로 종료)"
    if pos:
        return "positive_exploratory: 양성 탐색 (독립 확인만 후속 제안)"
    if s["diff_region_full"] <= 0:
        return "unsupported_vs_full: 영역 조건화의 추가 가치 미지지 (전체 영역 대조로 설명 가능)"
    return "inconclusive: 양의 차이가 5pp 미만이거나 기여 환자 3명 미만"


def main(out, d=None):
    global D
    D = d or D
    man =json.load(open(f"{D}/data/manifest.json"))
    gt = json.load(open(f"{D}/data/gt.json"))
    sc = {}
    for l in open(f"{D}/scores/main_scores.jsonl"):
        r = json.loads(l)
        sc[r["request_id"]] = r
    need = [q["request_id"] for q in man["requests"] if q["group"] == "main"]
    miss = [x for x in need if x not in sc]
    if miss:
        sys.exit(f"누락 score {len(miss)}: 주 판정 보류")
    for x in need:
        if not math.isfinite(sc[x]["mean_logprob"]):
            sys.exit(f"비유한 score {x}: 주 판정 보류")
    T = build_table(man, gt, sc)
    rep = dict(primary=summary(T), aux_iou05=summary(T, "err5"), boot=bootstrap(T), loo=leave_one_patient_out(T))
    rep["decision"] = decide(rep["primary"])
    pos = [t for t in T if t["gt_pos"]]
    if pos:
        rep["secondary_gt_positive_patients_only"] = summary(pos)
    rep["score_stats"] = {k: dict(min=float(min(t[k] for t in T)), max=float(max(t[k] for t in T)), n_unique=len({t[k] for t in T}))
                          for k in ("conf", "region", "full")}
    ra = lambda k: np.argsort(np.argsort([t[k] for t in T], kind="stable"), kind="stable").astype(float)
    rep["spearman_region_vs_conf"] = float(np.corrcoef(ra("region"), ra("conf"))[0, 1])  # 순위 상관(동률은 안정 정렬 순위, 기술 통계)
    rep["spearman_region_vs_full"] = float(np.corrcoef(ra("region"), ra("full"))[0, 1])
    json.dump(rep, open(out, "w"), indent=1)
    json.dump(T, open(out.replace("report", "table"), "w"), indent=1)
    print(json.dumps(rep["primary"], indent=1), rep["decision"])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
