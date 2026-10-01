"""iter_045 평가 라이브러리/CLI (기본 python, CPU only). MG 출력은 원본 정규화 xyxy에서, C 출력은 canvas->원본 정규화 역변환으로 채점한다.

사전 고정 규칙 (plan.md Evaluation; 결과를 본 뒤 바꾸지 않는다):
  - 주지표 문장 F1@IoU0.3 (최대 cardinality 일대일 matching, 동률은 총 IoU 최대: pg39_spec.match_fast)를 환자 안 평균 -> 환자 평균.
  - D24 운영점 선택: checkpoint별 환자평균 F1@0.3 최대 threshold. 동률은 F1@0.5, 낮은 FP/문장, 높은 threshold 순.
    두 checkpoint 대표 선택도 같은 순서. 완전 동률이면 MS. 공식 threshold 0.8은 보조 보고.
  - 낮은 성능을 이유로 정상 동작한 모델을 제외하지 않는다.
CLI:
  python mg45_eval.py select --out results/iter_045/decisions/D24_select.json
"""
import argparse
import glob
import hashlib
import json
import os
import sys

import numpy as np

import pg39_spec as S39
from rsna_diag import parse

MAN = "results/iter_043/data/manifest_private.json"
THRS = [0.2, 0.4, 0.6, 0.8]
OFFICIAL_THR = 0.8
LOCKED_CODE = ["mg45_mg.py", "mg45_worker.py"]


class EvalError(RuntimeError):
    pass


def file_sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def rid(setname, ckpt, patient, t):
    return hashlib.sha256(f"{setname}|{ckpt}|{patient}|{t}".encode()).hexdigest()[:32]


def entries(man, setname):
    if setname in ("D24", "D8"):
        ents = man["D24"]
        if setname == "D8":
            keep = set(man["D8"])
            ents = [e for e in ents if e["PatientID"] in keep]
        return ents
    return man[setname]


def verify_mg_dir(d, setname, ckpt, man, allow_code_diff=False):
    """completion·protocol·요청 집합·현재 입력 hash·code/ckpt/manifest 잠금을 검증하고 {(patient,target): record}를 반환한다."""
    comp_p = os.path.join(d, "completion.json")
    if not os.path.exists(comp_p):
        raise EvalError(f"no completion: {d}")
    comp = json.load(open(comp_p))
    if comp["complete"] is not True or any(c != 0 for c in comp["exit_codes"]):
        raise EvalError(f"completion not complete/exit codes nonzero: {d}")
    pp = os.path.join(d, "launch_protocol.json")
    if file_sha(pp) != comp["launch_protocol_sha256"]:
        raise EvalError("launch protocol changed after completion")
    proto = json.load(open(pp))
    bad = [f for f in LOCKED_CODE if file_sha(f) != proto["code"][f]]
    if bad and not allow_code_diff:
        raise EvalError(f"code changed since run: {bad}")
    if file_sha(MAN) != proto["manifest_sha256"]:
        raise EvalError("manifest changed since run")
    wf = {"P": "medgrounder_pretrain_imagenome.pth", "MS": "medgrounder_finetune_ms.pth"}[ckpt]
    ck = file_sha(os.path.join("results/iter_045/external/weights", wf))
    if ck != proto["ckpt_sha256"]:
        raise EvalError("checkpoint file changed")
    ents = {e["PatientID"]: e for e in entries(man, setname)}
    files = sorted(glob.glob(os.path.join(d, "raw_worker*.jsonl")))
    if sorted(os.path.basename(f) for f in files) != sorted(comp["raw_file_sha256"]):
        raise EvalError("raw file set != completion")
    recs = []
    for f in files:
        if file_sha(f) != comp["raw_file_sha256"][os.path.basename(f)]:
            raise EvalError(f"raw file changed after completion {f}")
        recs += [json.loads(l) for l in open(f, "rb").read().split(b"\n")[:-1] if l.strip()]
    want = {rid(setname, ckpt, p, t): (p, t) for p in ents for t in ("qA", "qB")}
    ids = [r["request_id"] for r in recs]
    if len(ids) != len(set(ids)) or set(ids) != set(want):
        raise EvalError("request set mismatch (missing/duplicate/extra)")
    out = {}
    img_ok = {}
    for r in recs:
        p, t = want[r["request_id"]]
        e = ents[p]
        if (r["patient"], r["target"]) != (p, t) or r["ckpt"] != ckpt or r["set"] != setname or r["ckpt_sha256"] != ck:
            raise EvalError("record identity mismatch")
        if r["sentence_sha256"] != hashlib.sha256(e["sentences"][t].encode()).hexdigest():
            raise EvalError("sentence != manifest")
        if r["u8_pixel_sha256"] != e["u8_pixel_sha256"] or r["image"] != e["image"]:
            raise EvalError("input pixel/image != manifest")
        if e["image"] not in img_ok:
            img_ok[e["image"]] = file_sha(e["image"]) == e["image_file_sha256"]
        if not img_ok[e["image"]]:
            raise EvalError(f"current image file hash mismatch {e['image']}")
        out[(p, t)] = r
    return out, comp, proto


def score(pred_boxes, gt_boxes):
    m3 = S39.sent_metrics(pred_boxes, gt_boxes, 0.3)
    m5 = S39.sent_metrics(pred_boxes, gt_boxes, 0.5)
    return {"f1_03": m3["f1"], "f1_05": m5["f1"], "recall_03": m3["recall"], "fp_03": m3["fp"], "n_pred": len(pred_boxes),
            "n_gt": len(gt_boxes), "empty": len(pred_boxes) == 0}


def mg_scores(recs, ents, thr):
    """{(patient,target): score dict} at threshold thr. 예측 box는 원본 정규화 xyxy(추가 clipping 없음)."""
    out = {}
    for (p, t), r in recs.items():
        d = r["detections"][str(thr)]
        out[(p, t)] = score(d["boxes_orig_xyxy"], ents[p]["gt_boxes_xyxy_norm"][t])
    return out


def summarize(sc, pids):
    f3 = [np.mean([sc[(p, t)]["f1_03"] for t in ("qA", "qB")]) for p in pids]
    f5 = [np.mean([sc[(p, t)]["f1_05"] for t in ("qA", "qB")]) for p in pids]
    rec = [np.mean([sc[(p, t)]["recall_03"] for t in ("qA", "qB")]) for p in pids]
    fp = [np.mean([sc[(p, t)]["fp_03"] for t in ("qA", "qB")]) for p in pids]
    emp = [np.mean([sc[(p, t)]["empty"] for t in ("qA", "qB")]) for p in pids]
    return {"n_patients": len(pids), "f1_03": float(np.mean(f3)), "f1_05": float(np.mean(f5)), "recall_03": float(np.mean(rec)),
            "fp_per_sentence": float(np.mean(fp)), "empty_rate": float(np.mean(emp))}


def pick_threshold(table):
    """table: {thr: summary}. 규칙: F1@0.3 최대 -> F1@0.5 최대 -> FP 최소 -> threshold 최대."""
    return sorted(table, key=lambda t: (-round(table[t]["f1_03"], 12), -round(table[t]["f1_05"], 12),
                                        round(table[t]["fp_per_sentence"], 12), -t))[0]


def cmd_select(a):
    if os.path.exists(a.out):
        sys.exit("output exists")
    man = json.load(open(MAN))
    ents = {e["PatientID"]: e for e in man["D24"]}
    pids = sorted(ents)
    res = {"manifest_sha256": file_sha(MAN), "n_patients": len(pids), "rule": pick_threshold.__doc__, "ckpts": {}, "dirs": {}}
    for ck, d in (("P", a.p_dir), ("MS", a.ms_dir)):
        recs, comp, proto = verify_mg_dir(d, "D24", ck, man)
        res["dirs"][ck] = {"dir": d, "completion_sha256": file_sha(os.path.join(d, "completion.json")),
                           "launch_protocol_sha256": comp["launch_protocol_sha256"]}
        table = {t: summarize(mg_scores(recs, ents, t), pids) for t in THRS}
        sel = pick_threshold(table)
        res["ckpts"][ck] = {"table": {str(t): table[t] for t in THRS}, "selected_threshold": sel, "official_0.8": table[OFFICIAL_THR]}
    cand = {ck: res["ckpts"][ck]["table"][str(res["ckpts"][ck]["selected_threshold"])] for ck in ("P", "MS")}
    key = lambda ck: (-round(cand[ck]["f1_03"], 12), -round(cand[ck]["f1_05"], 12), round(cand[ck]["fp_per_sentence"], 12))
    best = sorted(["MS", "P"], key=key)  # 완전 동률이면 MS 우선(정렬 안정성: 리스트 순서)
    res["selected"] = {"ckpt": best[0], "threshold": res["ckpts"][best[0]]["selected_threshold"], "summary": cand[best[0]],
                       "tie_rule_ms_preferred": key("P") == key("MS")}
    res["note"] = "D24는 양성 문장 집단이다. 이 선택으로 부재 거부 성능을 주장할 수 없다. V96를 보고 checkpoint/threshold를 바꾸지 않는다."
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    tmp = a.out + f".{os.getpid()}.tmp"
    json.dump(res, open(tmp, "w"), indent=1)
    os.replace(tmp, a.out)
    print(json.dumps({"selected": res["selected"], "P": res["ckpts"]["P"]["selected_threshold"], "MS": res["ckpts"]["MS"]["selected_threshold"]}, indent=1))
    for ck in ("P", "MS"):
        for t in THRS:
            print(ck, t, {k: round(v, 4) for k, v in res["ckpts"][ck]["table"][str(t)].items()})


def cmd_cfg(a):
    """실행 구성(worker/batch) 비교: 기준 dir 대비 logit/box 차이, threshold 통과 집합, 최종 box 집합·matching F1 일치. 처리량은 completion 기록."""
    if os.path.exists(a.out):
        sys.exit("output exists")
    man = json.load(open(MAN))
    ents = {e["PatientID"]: e for e in man["D24"]}
    pids = sorted(ents)
    base, bcomp, _ = verify_mg_dir(a.base, "D24", a.ckpt, man)
    res = {"base": a.base, "ckpt": a.ckpt, "configs": {}}
    for d in a.dirs:
        recs, comp, proto = verify_mg_dir(d, "D24", a.ckpt, man)
        ml = mb = 0.0
        pass_same = True
        boxes_same = True
        f1_same = True
        for k, r in recs.items():
            b = base[k]
            ml = max(ml, float(np.abs(np.array(r["logits"]) - np.array(b["logits"])).max()))
            mb = max(mb, float(np.abs(np.array(r["pred_boxes_cxcywh"]) - np.array(b["pred_boxes_cxcywh"])).max()))
            for t in THRS:
                x, y = r["detections"][str(t)], b["detections"][str(t)]
                pass_same &= x["pre_wbf_n"] == y["pre_wbf_n"]
                boxes_same &= len(x["boxes_orig_xyxy"]) == len(y["boxes_orig_xyxy"])
        for t in THRS:
            sa, sb = mg_scores(recs, ents, t), mg_scores(base, ents, t)
            f1_same &= all(sa[k]["f1_03"] == sb[k]["f1_03"] and sa[k]["f1_05"] == sb[k]["f1_05"] for k in sa)
        res["configs"][d] = {"workers": comp["workers"], "batch": comp["batch"], "workload_wall_s": comp.get("workload_wall_s"),
                             "launcher_wall_incl_loading_s": comp["launcher_wall_s_incl_loading"], "items_per_min_workload": (48 / comp["workload_wall_s"] * 60) if comp.get("workload_wall_s") else None,
                             "peak_alloc_gb_max": comp["peak_alloc_gb_max"], "max_abs_logit_diff": ml, "max_abs_box_diff": mb,
                             "threshold_pass_counts_equal": bool(pass_same), "n_final_boxes_equal": bool(boxes_same), "per_sentence_f1_equal_all_thr": bool(f1_same)}
    json.dump(res, open(a.out, "x"), indent=1)
    print(json.dumps(res, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cfg")
    c.add_argument("--out", required=True)
    c.add_argument("--ckpt", required=True)
    c.add_argument("--base", required=True)
    c.add_argument("--dirs", nargs="+", required=True)
    s = sub.add_parser("select")
    s.add_argument("--out", required=True)
    s.add_argument("--p-dir", default="results/iter_045/mg/D24_P_w1b1")
    s.add_argument("--ms-dir", default="results/iter_045/mg/D24_MS_w1b1")
    a = ap.parse_args()
    {"select": cmd_select, "cfg": cmd_cfg}[a.cmd](a)


if __name__ == "__main__":
    main()
