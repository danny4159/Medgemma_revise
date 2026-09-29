"""iter_031 continuation(F) 저장 출력 보완 분석 (기본 medgemma env, GPU 재생성 없음).

원본: results/iter_034/analysis_iter031/supplement.py (sha256 a5990de1...). 원본은 report.json의 cost_rows만 쓰고
(1) IoU0.5 회복을 환자 F1의 0→양수로 대신했고, (2) dedup을 FP 수에서 중복 수를 빼는 근사로 계산했다.
이번 수정:
- 원시 F token을 고정 tokenizer로 decode하고 기존 strict parser(parse.parse_response)로 다시 해석한다.
  저장 report.json의 cost_rows(F1@0.3/0.5, TP/FP)와 H2 회복 수를 먼저 재현한다(불일치 시 중단).
- 회복: 기존 엄격 누락 사건(y_partial)과 원래 누락 GT identity(zero_overlap_gt_idx)에 대해 새 box가
  (a) IoU≥0.3 [원 정의 재현], (b) IoU≥0.5, (c) 중심이 누락 GT 내부 인 경우를 각각 계산한다.
- dedup: 기존 정의(parse.duplicates = 동일 좌표 box)로 실제 중복 box를 제거(첫 등장 유지)한 뒤 재매칭한다.
- 원래 O box 수 1/2 이상·category별 회복, 추가 TP/FP, F1, invalid와 분모를 보고한다. FP는 전체 N 하한(invalid→0)과
  valid-only를 구분한다.
- 비용: F 호출 자체(runtime, 생성 token)와 같은 환자 O 대비 F−O 차이를 분리한다. O·F는 같은 실행 구성에서
  측정됐으므로 차이를 보고하되, 원래 SFT 생성 시간과의 비교는 구성 차이로 결측 처리한다.
H1/H2 판정과 continuation 투자 종료 판단은 바꾸지 않는다.
"""
import glob
import hashlib
import json
import os
import sys

import numpy as np

BASE = "/SSD1_1TB/home/milab/daniel/08_medgemma/research"
sys.path.insert(0, BASE)
from rsna_diag import metrics as M, parse as PA  # noqa: E402

SPLITS = {"C201": "C", "E402": "E"}


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def load_raw(run_dir):
    out = {}
    for p in sorted(glob.glob(f"{run_dir}/attempt1/gen_worker*.jsonl")):
        for l in open(p):
            if l.strip():
                r = json.loads(l)
                k = (r["id"], r["task"])
                if k in out:
                    raise ValueError(f"duplicate {k}")
                out[k] = r
    return out


def dedup(boxes):
    seen, out = set(), []
    for b in boxes:
        t = tuple(b)
        if t not in seen:
            seen.add(t)
            out.append(b)
    return out


def center_in(b, g):
    cy, cx = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    return g[0] <= cy <= g[2] and g[1] <= cx <= g[3]


def analyze(name, split, tok):
    run = f"{BASE}/results/iter_031/{name}"
    rep = json.load(open(f"{run}/report.json"))
    man = json.load(open(f"{BASE}/{rep['source_manifest_path']}"))
    aud = json.load(open(f"{BASE}/{rep['source_audit_path']}"))
    if sha(f"{BASE}/{rep['source_audit_path']}") != rep["source_audit_sha256"]:
        raise ValueError("source_audit changed")
    raw = load_raw(run)
    ids = list(man["patients"][split].keys())
    if set(raw) != {(i, t) for i in ids for t in ("O", "F")}:
        raise ValueError("raw O/F set incomplete")
    stored = {r["id"]: r for r in rep["h2"]["cost_rows"]}
    stored_ev = {e["id"]: e for e in rep["h2"]["events_detail"]}
    rows, mism = [], []
    for pid in ids:
        a = aud["patients"][split][pid]
        gt = a["gt_boxes_norm"]
        o_boxes = a["pred_boxes_seed17"]
        f = raw[(pid, "F")]
        o = raw[(pid, "O")]
        txt = tok.decode(f["suffix_ids"], skip_special_tokens=False)
        fp_ = PA.parse_response(txt, f["ended_eos"])
        valid = fp_["status"] in PA.VALID
        fb = fp_["boxes"] if valid else []
        new = fb[len(o_boxes):] if valid and fb[:len(o_boxes)] == o_boxes else None
        m3, m5 = (M.patient_metrics(fb, gt, 0.3), M.patient_metrics(fb, gt, 0.5)) if valid else (None, None)
        s = stored[pid]
        if (s["f_valid"] != valid or (valid and (abs(s["f_f1_03"] - m3["f1"]) > 1e-12 or abs(s["f_f1_05"] - m5["f1"]) > 1e-12
                                                 or s["f_fp_03"] != m3["unmatched_pred"] or s["f_dup"] != PA.duplicates(fb)))):
            mism.append(pid)
        fd = dedup(fb) if valid else []
        d3, d5 = (M.patient_metrics(fd, gt, 0.3), M.patient_metrics(fd, gt, 0.5)) if valid else (None, None)
        om3, om5 = M.patient_metrics(o_boxes, gt, 0.3), M.patient_metrics(o_boxes, gt, 0.5)
        ev = a["event"]
        rec = {}
        if ev["y_partial"]:
            missed = [gt[i] for i in ev["zero_overlap_gt_idx"]]
            nb = new or []
            rec = {"iou0.3": bool(nb) and len(M.match(nb, missed, 0.3)) >= 1,
                   "iou0.5": bool(nb) and len(M.match(nb, missed, 0.5)) >= 1,
                   "center_in_gt": any(center_in(b, g) for b in nb for g in missed),
                   "iou0.3_after_dedup": bool(nb) and len(M.match(dedup(nb), missed, 0.3)) >= 1}
            if rec["iou0.3"] != stored_ev[pid]["recovered"]:
                mism.append(pid + ":event")
        rows.append({"id": pid, "category": a["category"], "n_pred_O": len(o_boxes), "event": bool(ev["y_partial"]), "rec": rec,
                     "f_valid": valid, "o": {"f1@0.3": om3["f1"], "f1@0.5": om5["f1"], "tp@0.3": om3["tp"], "fp@0.3": om3["unmatched_pred"]},
                     "f": None if not valid else {"f1@0.3": m3["f1"], "f1@0.5": m5["f1"], "tp@0.3": m3["tp"], "fp@0.3": m3["unmatched_pred"],
                                                  "tp@0.5": m5["tp"], "n_pred": len(fb), "dup": PA.duplicates(fb)},
                     "f_dedup": None if not valid else {"f1@0.3": d3["f1"], "f1@0.5": d5["f1"], "tp@0.3": d3["tp"],
                                                        "fp@0.3": d3["unmatched_pred"], "n_pred": len(fd)},
                     "tok_O": len(o["suffix_ids"]), "tok_F": len(f["suffix_ids"]), "rt_O": o["runtime_s"], "rt_F": f["runtime_s"]})
    if mism:
        raise ValueError(f"{name}: stored report not reproduced for {mism[:5]}")

    def group(rs):
        n = len(rs)
        if not n:
            return {"n": 0}
        ev = [r for r in rs if r["event"]]
        g = {"n": n, "n_invalid_F": sum(not r["f_valid"] for r in rs), "n_events": len(ev)}
        for k in ("iou0.3", "iou0.5", "center_in_gt", "iou0.3_after_dedup"):
            g[f"recovered_{k}"] = sum(r["rec"][k] for r in ev)
            g[f"recovery_rate_{k}"] = g[f"recovered_{k}"] / len(ev) if ev else None
        for thr in ("0.3", "0.5"):
            g[f"mean_f1@{thr}_O"] = float(np.mean([r["o"][f"f1@{thr}"] for r in rs]))
            g[f"mean_f1@{thr}_F_invalid0"] = float(np.mean([r["f"][f"f1@{thr}"] if r["f_valid"] else 0.0 for r in rs]))
            g[f"mean_f1@{thr}_F_dedup_invalid0"] = float(np.mean([r["f_dedup"][f"f1@{thr}"] if r["f_valid"] else 0.0 for r in rs]))
        g["extra_tp@0.3_total"] = sum(r["f"]["tp@0.3"] - r["o"]["tp@0.3"] for r in rs if r["f_valid"])
        fp_all = [r["f"]["fp@0.3"] if r["f_valid"] else 0 for r in rs]
        fpd_all = [r["f_dedup"]["fp@0.3"] if r["f_valid"] else 0 for r in rs]
        g["fp@0.3_per_patient_O"] = float(np.mean([r["o"]["fp@0.3"] for r in rs]))
        g["fp@0.3_per_patient_F_all_n_lower_bound"] = float(np.mean(fp_all))
        g["fp@0.3_per_patient_F_valid_only"] = float(np.mean([r["f"]["fp@0.3"] for r in rs if r["f_valid"]])) if any(r["f_valid"] for r in rs) else None
        g["fp@0.3_per_patient_F_dedup_all_n_lower_bound"] = float(np.mean(fpd_all))
        g["extra_fp@0.3_per_patient_all_n"] = g["fp@0.3_per_patient_F_all_n_lower_bound"] - g["fp@0.3_per_patient_O"]
        g["n_with_dup"] = sum(1 for r in rs if r["f_valid"] and r["f"]["dup"] > 0)
        return g

    cats = sorted({r["category"] for r in rows})
    out = {"split": name, "n": len(rows), "stored_report_reproduced": True,
           "all": group(rows),
           "by_category": {c: group([r for r in rows if r["category"] == c]) for c in cats},
           "by_n_pred_O": {"1": group([r for r in rows if r["n_pred_O"] == 1]), ">=2": group([r for r in rows if r["n_pred_O"] >= 2])},
           "cost": {"F_call_runtime_s_mean": float(np.mean([r["rt_F"] for r in rows])),
                    "F_minus_O_runtime_s_mean": float(np.mean([r["rt_F"] - r["rt_O"] for r in rows])),
                    "F_minus_O_runtime_s_median": float(np.median([r["rt_F"] - r["rt_O"] for r in rows])),
                    "F_tokens_mean": float(np.mean([r["tok_F"] for r in rows])),
                    "F_minus_O_tokens_mean": float(np.mean([r["tok_F"] - r["tok_O"] for r in rows])),
                    "extra_new_boxes_mean": float(np.mean([r["f"]["n_pred"] - r["n_pred_O"] for r in rows if r["f_valid"]])),
                    "vs_original_iter012_generation": None,
                    "note": "O·F는 같은 iter_031 실행 구성의 측정값이다. 원래 SFT 생성과의 시간 비교는 구성 차이로 결측."},
           "inputs": {"report_sha256": sha(f"{run}/report.json"), "source_audit_sha256": rep["source_audit_sha256"],
                      "raw_files": {os.path.basename(p): sha(p) for p in sorted(glob.glob(f"{run}/attempt1/gen_worker*.jsonl"))}}}
    return out


def main():
    out_dir = f"{BASE}/results/iter_035/analysis_iter031"
    os.makedirs(out_dir, exist_ok=True)
    outp = f"{out_dir}/supplement.json"
    if os.path.exists(outp):
        raise FileExistsError(outp)
    os.environ.setdefault("HF_HOME", "/SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    import transformers
    from rsna_diag.generate import MODEL_ID, MODEL_REVISION
    tok = transformers.AutoProcessor.from_pretrained(MODEL_ID, revision=MODEL_REVISION).tokenizer
    res = {k: analyze(k, s, tok) for k, s in SPLITS.items()}
    json.dump(res, open(outp, "w"), indent=2)
    for k, r in res.items():
        a = r["all"]
        print(k, json.dumps({x: a[x] for x in a if x.startswith(("recover", "n_", "mean_f1", "fp@", "extra"))}), json.dumps(r["cost"]))


if __name__ == "__main__":
    main()
