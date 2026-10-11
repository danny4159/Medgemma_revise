"""iter_111 전체 비교 실행: lock 검증 → 저장 출력 비교 → report/per_patient. 새 추론·학습 없음. 기존 결과 덮어쓰기 금지."""
import hashlib
import json
import os
import sys
import time

import numpy as np

import ev111_core as C
from rsna_diag import metrics as M

PROV = "results/iter_111/provenance"
OUT = "results/iter_111/eval"
LOCK = f"{PROV}/eval_lock.json"


def fsha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def check_lock():
    lk = json.load(open(LOCK))
    bad = [f for f, h in lk["code_sha256"].items() if fsha(f) != h]
    for k, p in (("ledger_sha256", f"{PROV}/ledger.json"), ("provenance_sha256", f"{PROV}/provenance.json")):
        if fsha(p) != lk[k]:
            bad.append(p)
    if bad:
        sys.exit(f"lock 불일치: {bad}")
    return lk


def weights(score, k):
    """conf 전략의 환자별 선택 확률(경계 동률 균등). expected_found와 동일 규칙."""
    score = np.asarray(score, float)
    n = len(score)
    if k <= 0 or n == 0:
        return np.zeros(n)
    if k >= n:
        return np.ones(n)
    v = np.sort(score)[k - 1]
    w = (score < v).astype(float)
    tie = score == v
    w[tie] = (k - int((score < v).sum())) / tie.sum()
    return w


def decide(ep, ci_lo, pos_diff, ep_aux, degenerate, unres_bounds):
    """원 계획 Evaluation의 분기. 임의 수정 금지."""
    if degenerate:
        return "negative", "k=0 또는 k=resolved S 전체: 내용 선택의 추가 정보 없음(ep=0)"
    if ep <= 0:
        return "negative", "주 endpoint<=0"
    if pos_diff <= 0:
        return "negative", "추가 이득이 GT 음성 오류에 한정(양성 위치 오류 추가 포착<=0)"
    if ep >= 0.05 and ci_lo > 0 and ep_aux > 0 and min(unres_bounds) > 0:
        return "positive", "ep>=0.05, CI하한>0, 양성 위치 오류 추가 포착>0, 최소 score 대조 순이득>0, unresolved 범위에서 방향 유지"
    return "inconclusive", "ep>0이나 기준(5pp/CI/최소 score 대조/unresolved 범위) 미충족"


def main():
    if os.path.exists(f"{OUT}/report.json"):
        sys.exit("exists")
    os.makedirs(OUT, exist_ok=True)
    lk = check_lock()
    t0 = time.time()
    rows = json.load(open(f"{PROV}/ledger.json"))["rows"]
    P = C.prep(rows)
    n = len(P)
    v = C.vec(P)
    t_prep = time.time() - t0
    rep = dict(lock_locked_at=lk["locked_at"], n=n, t_prep_s=t_prep)
    # reader 분포
    rd = {}
    for c in list(C.CATS) + ["all"]:
        sub = [p for p in P if c == "all" or p["cat"] == c]
        rd[c] = dict(n=len(sub), yes=sum(p["ans"] == "yes" for p in sub), no=sum(p["ans"] == "no" for p in sub),
                     unresolved=sum(p["ans"] is None for p in sub), explicit=sum(p["ans_source"] == "explicit" for p in sub))
    rep["reader_answers"] = rd
    # S와 오류 분해
    e = C.endpoint(v)
    rep["endpoint_point"] = e
    S = [p for p in P if p["det"]]
    rep["S_breakdown"] = {c: dict(n=sum(p["cat"] == c for p in S), Y=sum(C.error_type(p)[0] for p in S if p["cat"] == c)) for c in C.CATS}
    rep["S_error_types"] = {t: sum(C.error_type(p)[1] == t for p in S) for t in ("correct", "neg_claim", "pos_location")}
    # 부트스트랩 (최초 200회 시간 측정)
    t1 = time.time()
    C.boot(P, B=200)
    t200 = time.time() - t1
    b = C.boot(P)
    rep["bootstrap"] = dict(B=C.NBOOT, seed=C.SEED, t200_s=t200, ep=dict(mean=float(np.mean(b["ep"])), ci95=C.ci(b["ep"])),
                            ep_aux=dict(ci95=C.ci(b["ep_aux"])), pos_diff=dict(ci95=C.ci(b["pos_diff"])),
                            pos_diff_aux=dict(ci95=C.ci(b["pos_diff_aux"])), degenerate_fraction=b["degenerate"] / len(b["ep"]))
    rep["pos_diff_point"] = (e["vlm_pos_location"] - e["conf_pos_location"]) / e["n_S"]
    rep["pos_diff_aux_point"] = (e["vlm_pos_location"] - e["confmin_pos_location"]) / e["n_S"]
    # unresolved 범위
    ub = {}
    for mode in ("yes", "no", "adverse", "favorable"):
        ee = C.endpoint(C.vec(C.assign_unresolved(P, mode)))
        ub[mode] = dict(ep=ee["ep"], ep_aux=ee["ep_aux"], k=ee["k"], found_vlm=ee["found_vlm"], found_conf=ee["found_conf"],
                        pos_diff=(ee["vlm_pos_location"] - ee["conf_pos_location"]) / ee["n_S"])
    rep["unresolved_bounds"] = ub
    rep["decision"] = dict(zip(("outcome", "reason"), decide(e["ep"], rep["bootstrap"]["ep"]["ci95"][0], rep["pos_diff_point"], e["ep_aux"],
                                                          e["degenerate"], [x["ep"] for x in ub.values()])))
    # 시스템 표
    sysrep = {}
    for loc in ("det", "sft"):
        for mode in ("loc", "indep", "gate"):
            for thr in (C.IOU_MAIN, C.IOU_AUX):
                sysrep[f"{loc}_{mode}_iou{thr}"] = C.system_table(P, loc, mode, thr)
    rep["systems"] = sysrep
    idx = M.bootstrap_indices(n, 10000, C.SEED)
    pc = {}
    for loc in ("det", "sft"):
        base = np.array([C.joint(p, loc, "loc", .3) is True for p in P], float)
        for mode in ("indep", "gate"):
            a = np.array([C.joint(p, loc, mode, .3) is True for p in P], float)
            pc[f"{loc}_{mode}_minus_loc_joint0.3_unresolved_as_fail"] = dict(zip(("diff", "lo", "hi"), M.paired_boot_ci(a, base, idx)))
    rep["paired_joint"] = pc
    rep["t_total_s"] = time.time() - t0
    # per patient
    sel_conf = np.zeros(n)
    sel_confmin = np.zeros(n)
    inS = v["inS"]
    ids_res = np.where(inS & v["res"])[0]
    k = e["k"]
    sel_conf[ids_res] = weights(v["smax"][ids_res], k)
    sel_confmin[ids_res] = weights(v["smin"][ids_res], k)
    chk = float((sel_conf[ids_res] * v["Y"][ids_res]).sum())
    rep["weights_check"] = dict(conf_found_from_weights=chk, conf_found=e["found_conf"], ok=abs(chk - e["found_conf"]) < 1e-9)
    pp = [dict(id=p["id"], cat=p["cat"], ans=p["ans"], ans_source=p["ans_source"], det_nonempty=bool(p["det"]), Y=bool(v["Y"][i]),
               type=str(v["typ"][i]), smax=None if np.isnan(v["smax"][i]) else float(v["smax"][i]),
               smin=None if np.isnan(v["smin"][i]) else float(v["smin"][i]), vlm_selected=bool(v["no"][i] and inS[i]),
               conf_select_prob=float(sel_conf[i]), confmin_select_prob=float(sel_confmin[i]), sft_status=p["sft_status"]) for i, p in enumerate(P)]
    json.dump(pp, open(f"{OUT}/per_patient.json", "w"))
    json.dump(rep, open(f"{OUT}/report.json", "w"), indent=1, default=float)
    print(json.dumps(dict(decision=rep["decision"], ep=e["ep"], ci=rep["bootstrap"]["ep"]["ci95"], k=e["k"], n_S=e["n_S"], t=rep["t_total_s"]), default=float))


if __name__ == "__main__":
    main()
