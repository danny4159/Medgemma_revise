"""iter_046 D24 checkpoint 평가·선택 규칙 (CPU, 기본 python). 모든 규칙은 학습 전에 protocol_lock에 잠근다.

사전 고정 규칙 (plan.md Section 3~4):
  - checkpoint별 threshold: 후보 0.2/0.4/0.6/0.8 중 D24 환자평균 F1@0.3 최대 -> F1@0.5 최대 -> FP/문장 최소 -> 높은 threshold (mg45_eval.pick_threshold와 동일).
  - 후보 checkpoint 순위(각자 자기 선택 threshold의 요약): F1@0.3 최대 -> F1@0.5 최대 -> FP 최소 -> 이른 epoch -> 설정 S 우선.
  - 한정 보완(supp) 조건: D24에서 (epoch15 F1@0.3 - epoch10 F1@0.3 >= 0.01) 또는 (epoch15가 선택 trajectory 후보 중 순위 1위 이고
    epoch15 평균 train loss가 epoch10 평균 train loss보다 5% 이상 낮음).
D24는 24환자·48문장이며 V96 결과를 보기 전에 끝난다. V96 결과로 선택을 바꾸지 않는다.
"""
import hashlib
import json
import os
import sys

import mg45_eval as E

ROOT = "results/iter_046"
MAN = E.MAN
THRS = E.THRS
LOCKED_CODE = ["mg45_mg.py", "mg45_worker.py"]


def d24_dir(label):
    return f"{ROOT}/eval_d24/{label}"


def verify_dir(d, setname, label, ckpt_path, man):
    """mg45_eval.verify_mg_dir의 임의 checkpoint 판: completion·protocol·요청집합·현재 입력 hash·ckpt sha 대조. {(patient,target): record}, comp, proto."""
    comp = json.load(open(os.path.join(d, "completion.json")))
    if comp["complete"] is not True or any(c != 0 for c in comp["exit_codes"]):
        raise E.EvalError(f"incomplete/nonzero exit: {d}")
    pp = os.path.join(d, "launch_protocol.json")
    if E.file_sha(pp) != comp["launch_protocol_sha256"]:
        raise E.EvalError("launch protocol changed after completion")
    proto = json.load(open(pp))
    bad = [f for f in LOCKED_CODE if E.file_sha(f) != proto["code"][f]]
    if bad:
        raise E.EvalError(f"code changed since run: {bad}")
    if E.file_sha(MAN) != proto["manifest_sha256"]:
        raise E.EvalError("manifest changed since run")
    ck = E.file_sha(ckpt_path)
    if ck != proto["ckpt_sha256"] or proto["args"].get("ckpt") != label:
        raise E.EvalError("checkpoint file/label != protocol")
    ents = {e["PatientID"]: e for e in E.entries(man, setname)}
    import glob
    files = sorted(glob.glob(os.path.join(d, "raw_worker*.jsonl")))
    if sorted(os.path.basename(f) for f in files) != sorted(comp["raw_file_sha256"]):
        raise E.EvalError("raw file set != completion")
    recs = []
    for f in files:
        if E.file_sha(f) != comp["raw_file_sha256"][os.path.basename(f)]:
            raise E.EvalError(f"raw file changed {f}")
        recs += [json.loads(l) for l in open(f, "rb").read().split(b"\n")[:-1] if l.strip()]
    want = {E.rid(setname, label, p, t): (p, t) for p in ents for t in ("qA", "qB")}
    ids = [r["request_id"] for r in recs]
    if len(ids) != len(set(ids)) or set(ids) != set(want):
        raise E.EvalError("request set mismatch")
    out = {}
    img_ok = {}
    for r in recs:
        p, t = want[r["request_id"]]
        e = ents[p]
        if (r["patient"], r["target"]) != (p, t) or r["ckpt"] != label or r["set"] != setname or r["ckpt_sha256"] != ck:
            raise E.EvalError("record identity mismatch")
        if r["sentence_sha256"] != hashlib.sha256(e["sentences"][t].encode()).hexdigest():
            raise E.EvalError("sentence != manifest")
        if r["u8_pixel_sha256"] != e["u8_pixel_sha256"] or r["image"] != e["image"]:
            raise E.EvalError("input pixel/image != manifest")
        if e["image"] not in img_ok:
            img_ok[e["image"]] = E.file_sha(e["image"]) == e["image_file_sha256"]
        if not img_ok[e["image"]]:
            raise E.EvalError(f"current image file hash mismatch {e['image']}")
        out[(p, t)] = r
    return out, comp, proto


def checkpoint_table(label, ckpt_path, man=None):
    man = man or json.load(open(MAN))
    ents = {e["PatientID"]: e for e in man["D24"]}
    pids = sorted(ents)
    recs, comp, proto = verify_dir(d24_dir(label), "D24", label, ckpt_path, man)
    table = {t: E.summarize(E.mg_scores(recs, ents, t), pids) for t in THRS}
    sel = E.pick_threshold(table)
    return {"label": label, "ckpt_path": ckpt_path, "ckpt_sha256": proto["ckpt_sha256"], "table": {str(t): table[t] for t in THRS}, "selected_threshold": sel,
            "selected": table[sel], "fixed_0.4": table[0.4], "completion_sha256": E.file_sha(os.path.join(d24_dir(label), "completion.json")),
            "workload": {"launcher_wall_s_incl_loading": comp["launcher_wall_s_incl_loading"], "peak_alloc_gb_max": comp["peak_alloc_gb_max"]}}


def rank_key(c):
    s = c["selected"]
    return (-round(s["f1_03"], 12), -round(s["f1_05"], 12), round(s["fp_per_sentence"], 12), c["epoch"], 0 if c["traj"] == "S" else 1)


def write_once(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        sys.exit(f"exists: {path}")
    tmp = path + f".{os.getpid()}.tmp"
    json.dump(obj, open(tmp, "w"), indent=1)
    os.replace(tmp, path)


def cmd_ckpt(label, traj, epoch):
    path = f"{ROOT}/train/{traj}/weights_e{epoch}.pth"
    res = checkpoint_table(label, path)
    res.update({"traj": traj, "epoch": epoch})
    write_once(f"{ROOT}/decisions/D24_{label}.json", res)
    s = res["selected"]
    print(label, "thr", res["selected_threshold"], {k: round(v, 4) for k, v in s.items()}, "fixed0.4 f1_03", round(res["fixed_0.4"]["f1_03"], 4))
    return res


def load_ckpt_decisions(trajs, epochs):
    out = []
    for tj in trajs:
        for ep in epochs:
            p = f"{ROOT}/decisions/D24_A_{tj}_e{ep}.json"
            if os.path.exists(p):
                out.append(json.load(open(p)))
    return out


def select_best(cands):
    return sorted(cands, key=rank_key)


def cmd_select_traj(a):
    """phase1: (S,U)x(e2,e5) 네 후보 순위 -> 선택 trajectory."""
    cands = load_ckpt_decisions(["S", "U"], [2, 5])
    if len(cands) != 4:
        sys.exit(f"need 4 candidates, got {len(cands)}")
    ranked = select_best(cands)
    res = {"rule": __doc__, "ranked": [{"label": c["label"], "traj": c["traj"], "epoch": c["epoch"], "thr": c["selected_threshold"], "f1_03": c["selected"]["f1_03"],
                                        "f1_05": c["selected"]["f1_05"], "fp": c["selected"]["fp_per_sentence"]} for c in ranked],
           "selected_traj": ranked[0]["traj"], "best_candidate": ranked[0]["label"],
           "candidate_files": {c["label"]: c["completion_sha256"] for c in cands}}
    write_once(f"{ROOT}/decisions/select_trajectory.json", res)
    print(json.dumps(res["ranked"], indent=1), "->", res["selected_traj"])


def cmd_supp(a):
    """phase2 후: 한정 보완(supp) 실행 여부."""
    tj = json.load(open(f"{ROOT}/decisions/select_trajectory.json"))["selected_traj"]
    cands = load_ckpt_decisions([tj], [2, 5, 10, 15])
    ep = {c["epoch"]: c for c in cands}
    if 10 not in ep or 15 not in ep:
        sys.exit("need e10,e15")
    reach = {15: json.load(open(f"{ROOT}/train/{tj}/reached_epoch15.json"))}  # amendment: reached_epoch10.json 없음(epoch_losses는 epoch15 파일에 전부 포함)
    l10 = reach[15]["epoch_mean_train_loss"]["10"]
    l15 = reach[15]["epoch_mean_train_loss"]["15"]
    d = ep[15]["selected"]["f1_03"] - ep[10]["selected"]["f1_03"]
    best = select_best([c for c in cands if c["epoch"] in (2, 5, 10, 15)])[0]["epoch"]
    cond_a = d >= 0.01 - 1e-12
    cond_b = best == 15 and (l15 <= 0.95 * l10)
    res = {"traj": tj, "f1_03_e10": ep[10]["selected"]["f1_03"], "f1_03_e15": ep[15]["selected"]["f1_03"], "delta": d, "best_epoch_among_2_5_10_15": best,
           "train_loss_e10": l10, "train_loss_e15": l15, "loss_drop_frac": 1 - l15 / l10, "cond_a_delta_ge_0.01": bool(cond_a), "cond_b_best15_and_loss_drop_ge_5pct": bool(cond_b),
           "run_supp": bool(cond_a or cond_b), "rule": "run_supp iff (f1_03_e15-f1_03_e10>=0.01) or (e15 rank-1 and e15 mean train loss <= 0.95*e10)"}
    write_once(f"{ROOT}/decisions/supp_decision.json", res)
    print(json.dumps(res, indent=1))


def cmd_final_select(a):
    """모든 실행 완료 후 최종 checkpoint(선택 trajectory의 e2~e30 중) + threshold 잠금. V96 생성 전 단계."""
    tj = json.load(open(f"{ROOT}/decisions/select_trajectory.json"))["selected_traj"]
    sd = json.load(open(f"{ROOT}/decisions/supp_decision.json"))
    eps = [2, 5, 10, 15] + ([20, 25, 30] if sd["run_supp"] else [])
    cands = load_ckpt_decisions([tj], eps)
    if sorted(c["epoch"] for c in cands) != sorted(eps):
        sys.exit("missing candidate decisions")
    ranked = select_best(cands)
    best = ranked[0]
    res = {"traj": tj, "ranked": [{"label": c["label"], "epoch": c["epoch"], "thr": c["selected_threshold"], "f1_03": c["selected"]["f1_03"], "f1_05": c["selected"]["f1_05"],
                                   "fp": c["selected"]["fp_per_sentence"]} for c in ranked],
           "label": best["label"], "epoch": best["epoch"], "ckpt_path": best["ckpt_path"], "ckpt_sha256": best["ckpt_sha256"], "selected_threshold": best["selected_threshold"],
           "fixed_threshold": 0.4, "supp_run": sd["run_supp"],
           "convergence_note": ("supp 실행 후에도 상승 여부는 ranked 곡선으로 판단; 추가 연장 없음" if sd["run_supp"] else "supp 조건 미충족"),
           "note": "D24 선택. V96를 본 뒤 변경 금지."}
    write_once(f"{ROOT}/decisions/final_selection.json", res)
    print(json.dumps({k: res[k] for k in ("traj", "label", "epoch", "selected_threshold", "ckpt_sha256")}, indent=1))


def main():
    import argparse
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("ckpt")
    c.add_argument("--traj", required=True)
    c.add_argument("--epoch", type=int, required=True)
    sub.add_parser("select-traj")
    sub.add_parser("supp")
    sub.add_parser("final-select")
    a = ap.parse_args()
    if a.cmd == "ckpt":
        cmd_ckpt(f"A_{a.traj}_e{a.epoch}", a.traj, a.epoch)
    elif a.cmd == "select-traj":
        cmd_select_traj(a)
    elif a.cmd == "supp":
        cmd_supp(a)
    else:
        cmd_final_select(a)


if __name__ == "__main__":
    main()
