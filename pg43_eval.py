"""iter_043 평가 (CPU only). 기존 M0/C 실제 영상 출력은 import 검증 후 재사용하고, 신규 text-only/영상 교환 출력은 verify_completion으로 재검증한다.

python pg43_eval.py --out results/iter_043/eval/report.json   (기존 파일 덮어쓰기 거부; 결과는 고유 임시 파일에 쓰고 마지막에 replace)

결정 규칙은 plan.md Evaluation을 결과를 보기 전에 그대로 구현한 것이며 결과를 보고 바꾸지 않는다:
  - 전체 V96: 환자 평균(두 문장) F1@0.3. 차이는 환자 paired bootstrap 10,000회 (seed 4302), gate 판정은 97.5% CI.
  - 동일 문장 21쌍: F1@0.5 주지표. B = mean_dir[F1(원래 영상 출력, recipient GT) - F1(교환 영상 출력, recipient GT)]. 17 문장 cluster bootstrap 10,000회 (seed 4302).
    좌표는 입력 영상 affine을 역변환한 original normalized 좌표(클리핑 없음)에서 recipient/donor GT와 비교한다.
  - 양성: P-C 하한>=-0.03 & C 실제 F1@0.5(21쌍)>=0.20 & B_C 상한<=0.10 & GT교차(1-crossF1@0.5) 하한>0.20 & 결론을 막는 provenance 문제 없음.
  - 음성: C-P 하한>0.03 & B_C 하한>0.10 & 교환 출력이 donor GT에 대응 (corr = F1@0.5(S,donor)-F1@0.5(S,recipient)의 평균>0이고 97.5% CI 하한>0; 결과 전에 고정한 해석).
  - 그 외 불확정. text-only valid율이 실제 영상보다 5pp 이상 낮으면 내용상 영상 기여로 해석하지 않는다는 flag를 남긴다.
"""
import argparse
import glob
import hashlib
import json
import os
import sys
import time

import numpy as np

import pg39_spec as S39
import pg43_retrieval as RT
import pg43_run as R
from rsna_diag import geometry, parse

OUT = "results/iter_043"
NBOOT = 10000
SEED = 4302
IMPORTS = {
    "M0": {"gen": "results/iter_039/gen/E96", "requests": "results/iter_039/requests_v2/requests_E96.jsonl",
           "protocol": "results/iter_039/protocol/protocol_E96.json", "adapter_digest": None},
    "C": {"gen": "results/iter_040/gen/C", "requests": "results/iter_040/requests/requests_V96.jsonl",
          "protocol": "results/iter_040/protocol/protocol_C.json",
          "adapter_digest": "419ae81f5ef455d39742b158537373da6e26061b362d13205ab28b4a50905ba8"},
}
C_REPRO = {"gen": "results/iter_041/gen/V96_C_Icost", "requests": "results/iter_041/requests/requests_V96_Icost.jsonl",
           "protocol": "results/iter_041/protocol/protocol_V96_C_Icost.json"}


def boot_idx(n, seed=SEED, B=NBOOT):
    return np.random.default_rng(seed).integers(0, n, size=(B, n), dtype=np.int32)


def ci(vals, level, idx):
    v = np.asarray(vals, float)
    m = v[idx].mean(axis=1)
    a = (1 - level) / 2 * 100
    return {"mean": float(v.mean()), "lo": float(np.percentile(m, a)), "hi": float(np.percentile(m, 100 - a)), "level": level}


def wilson(k, n, z=1.959964):
    if n == 0:
        return [0.0, 0.0, 0.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [p, float(c - h), float(c + h)]


# ---------------- 기존 출력 import 검증 ----------------
def verify_import(model, man_v96):
    """기존 completion/record/요청/adapter/현재 영상 hash를 검증한다. returns {(patient, target): record} (I-short만)."""
    spec = IMPORTS[model]
    d = spec["gen"]
    comp = json.load(open(f"{d}/completion.json"))
    if any(c != 0 for c in comp["exit_codes"]):
        raise R.RunError(f"import {model}: nonzero exit codes")
    proto = json.load(open(spec["protocol"]))
    if R.file_sha(spec["requests"]) != proto["requests_sha256"]:
        raise R.RunError(f"import {model}: requests file != protocol lock")
    ad = proto.get("adapter")
    if (ad["digest"] if ad else None) != spec["adapter_digest"]:
        raise R.RunError(f"import {model}: adapter digest mismatch")
    if ad and R.file_sha(os.path.join(ad["path"], "adapter.pt")) != ad["file_sha256"]:
        raise R.RunError(f"import {model}: adapter file changed")
    rows = {}
    for l in open(spec["requests"]):
        if l.strip():
            r = json.loads(l)
            rows[r["request_id"]] = r
    recs = []
    files = sorted(glob.glob(f"{d}/gen_worker*.jsonl"))
    if sorted(os.path.basename(f) for f in files) != sorted(comp["worker_file_sha256"]):
        raise R.RunError(f"import {model}: worker file set differs from completion")
    for f in files:
        if R.file_sha(f) != comp["worker_file_sha256"][os.path.basename(f)]:
            raise R.RunError(f"import {model}: worker file changed after completion {f}")
        recs += R.read_records(f)
    ids = [r["request_id"] for r in recs]
    if len(ids) != len(set(ids)) or set(ids) != set(rows) or len(ids) != comp["n_requests"]:
        raise R.RunError(f"import {model}: request set mismatch")
    if {r["protocol_digest"] for r in recs} != {comp["protocol_digest"]}:
        raise R.RunError(f"import {model}: record protocol digest != completion")
    out = {}
    for r in recs:
        if r["record_digest"] != R.record_digest(r) or r["row_digest"] != R.row_digest(rows[r["request_id"]]):
            raise R.RunError(f"import {model}: record/row digest mismatch")
        if r.get("adapter_digest") != spec["adapter_digest"]:
            raise R.RunError(f"import {model}: record adapter digest mismatch")
        if r["cond"] != "I-short":
            continue
        e = man_v96[r["patient"]]
        t = r["targets"][0]
        row = rows[r["request_id"]]
        if row["prompt_sha256"] != R.sha_bytes(S39.prompt_I_short(e["sentences"][t], t).encode()) or r["prompt_sha256"] != row["prompt_sha256"]:
            raise R.RunError(f"import {model}: prompt != manifest sentence")
        if r["input_pixel_sha256"] != e["input_pixel_sha256"] or row["image"] != e["image"]:
            raise R.RunError(f"import {model}: input image != manifest")
        out[(r["patient"], t)] = r
    if len(out) != 192:
        raise R.RunError(f"import {model}: expected 192 I-short, got {len(out)}")
    return out


def current_image_hashes(man):
    for e in man["V96"]:
        if R.file_sha(e["image"]) != e["image_file_sha256"] or R.G.load_image(e["image"])[2] != e["input_pixel_sha256"]:
            raise R.RunError(f"current image hash mismatch {e['PatientID']}")


# ---------------- 채점 ----------------
def parsed(rec):
    t = rec["targets"][0]
    r = S39.parse_ids(rec["suffix_text_raw"], rec["ended_eos"], {t})
    return r["status"], r["groups"][t]


def canvas_to_norm_xyxy(b, aff, h, w):
    x0, y0, x1, y1 = geometry.norm_to_canvas(b, *aff)
    return [x0 / w, y0 / h, x1 / w, y1 / h]


def score_canvas(status, boxes, gt_canvas):
    return S39.score_request(status, {"q": boxes}, ["q"], {"q": gt_canvas})["q"]


def score_norm(status, boxes_norm, gt_norm):
    valid = status in parse.VALID
    pred = boxes_norm if valid else []
    m3 = S39.sent_metrics(pred, gt_norm, 0.3)
    m5 = S39.sent_metrics(pred, gt_norm, 0.5)
    return {"f1_03": m3["f1"], "f1_05": m5["f1"]}


def rate(recs, key):
    return sum(1 for r in recs if r[key])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("output exists")
    t_start = time.time()
    man = json.load(open(f"{OUT}/data/manifest_private.json"))
    sel = json.load(open(f"{OUT}/retrieval/selection.json"))
    lock = json.load(open(f"{OUT}/data/selection_lock.json"))
    if R.file_sha(f"{OUT}/data/manifest_private.json") != lock["manifest_sha256"] or sel["manifest_sha256"] != lock["manifest_sha256"]:
        raise R.RunError("manifest hash != selection lock / retrieval selection")
    if sel["retrieval_source_sha256"] != R.file_sha("pg43_retrieval.py"):
        raise R.RunError("retrieval source changed since selection")
    v96 = {e["PatientID"]: e for e in man["V96"]}
    pids = [e["PatientID"] for e in man["V96"]]
    current_image_hashes(man)
    # ---- 기존 실제 영상 출력 + 신규 출력 ----
    real = {m: verify_import(m, v96) for m in ("M0", "C")}
    # C 재실행(iter_041 Icost)과 iter_040 C의 token 일치 (출처 확인)
    rep_all = {}
    for f in sorted(glob.glob(f"{C_REPRO['gen']}/gen_worker*.jsonl")):
        for r in R.read_records(f):
            rep_all[r["patient"] + "|" + r["targets"][0]] = r["suffix_ids"]
    c_repro = {"n": len(rep_all), "token_mismatch": sum(real["C"][(k.split("|")[0], k.split("|")[1])]["suffix_ids"] != v for k, v in rep_all.items())}
    new = {}
    for m in ("M0", "C"):
        recs = R.verify_completion(f"{OUT}/gen/MAIN_{m}", f"{OUT}/requests/requests_MAIN_{m}.jsonl", f"{OUT}/protocol/protocol_MAIN_{m}.json")
        text = {(r["patient"], r["targets"][0]): r for r in recs if r["kind"] == "V96text"}
        swap = {(r["patient"], r["targets"][0]): r for r in recs if r["kind"] == "swap"}
        if len(text) != 192 or len(swap) != 42:
            raise R.RunError("unexpected main record counts")
        new[m] = {"text": text, "swap": swap, "protocol_digest": R.verify_protocol(f"{OUT}/protocol/protocol_MAIN_{m}.json",
                                                                                    f"{OUT}/requests/requests_MAIN_{m}.jsonl")[0]}
    # ---- retrieval P ----
    idx_ret = RT.build(man)
    setting = (sel["chosen"]["kind"], sel["chosen"]["k"])
    t0 = time.perf_counter()
    P_pred = RT.predictions(idx_ret, man["V96"], setting)
    retr_s = time.perf_counter() - t0
    # ---- 문장별 채점 (canvas) ----
    sysnames = ["M0_real", "C_real", "P", "M0_text", "C_text"]
    rows = {s: {} for s in sysnames}  # (patient,target) -> score dict
    stat = {s: {} for s in sysnames}
    for e in man["V96"]:
        for t in ("qA", "qB"):
            k = (e["PatientID"], t)
            gt = e["gt_canvas_yxyx"][t]
            for m in ("M0", "C"):
                for kind, src in (("real", real[m]), ("text", new[m]["text"])):
                    st, bx = parsed(src[k])
                    sc = score_canvas(st, bx, gt)
                    sc["status"] = st
                    sc["eos"] = bool(src[k]["ended_eos"])
                    sc["runtime_s"] = src[k]["runtime_s_total"]
                    sc["n_out_tokens"] = src[k]["n_output_tokens"]
                    rows[f"{m}_{kind}"][k] = sc
            pb = P_pred[k][0]
            sc = score_canvas("valid_nonempty" if pb else "valid_empty", pb, gt)
            sc["status"] = "valid_nonempty"
            rows["P"][k] = sc
    def parr(s, key):
        return np.array([np.mean([rows[s][(p, t)][key] for t in ("qA", "qB")]) for p in pids])
    idxP = boot_idx(len(pids))
    prim = {}
    for s in sysnames:
        sr = list(rows[s].values())
        valid = sum(r["status"] in parse.VALID for r in sr)
        prim[s] = {"f1_03": ci(parr(s, "f1_03"), 0.95, idxP), "f1_05": ci(parr(s, "f1_05"), 0.95, idxP),
                   "recall_03": float(np.mean([r["recall_03"] for r in sr])), "fp_per_sentence_03": float(np.mean([r["fp_03"] for r in sr])),
                   "empty_rate": float(np.mean([bool(r["empty"]) for r in sr])), "invalid": int(len(sr) - valid),
                   "valid_rate": valid / len(sr), "eos_rate": float(np.mean([r.get("eos", True) for r in sr])) if s != "P" else None,
                   "n_sentences": len(sr), "mean_runtime_s": float(np.mean([r["runtime_s"] for r in sr])) if s != "P" else None,
                   "p95_runtime_s": float(np.percentile([r["runtime_s"] for r in sr], 95)) if s != "P" else None,
                   "mean_out_tokens": float(np.mean([r["n_out_tokens"] for r in sr])) if s != "P" else None}
    prim["P"]["retrieval_cpu_s_total_192_sentences"] = retr_s
    def diff(x, y, level):
        return ci(parr(x, "f1_03") - parr(y, "f1_03"), level, idxP)
    pairs_cmp = {}
    for x, y in (("P", "C_real"), ("C_real", "P"), ("C_real", "M0_real"), ("P", "M0_real"), ("C_text", "C_real"), ("M0_text", "M0_real"),
                 ("C_real", "C_text"), ("C_text", "P"), ("M0_text", "M0_real")):
        k = f"{x}_minus_{y}"
        if k not in pairs_cmp:
            pairs_cmp[k] = {"f1_03_ci975": diff(x, y, 0.975), "f1_03_ci95": diff(x, y, 0.95),
                            "f1_05_ci95": ci(parr(x, "f1_05") - parr(y, "f1_05"), 0.95, idxP)}
    # ---- 층별 (결과와 무관하게 정의; small = 가장 큰 GT box 면적이 V96 192문장 중앙값 미만) ----
    def area_frac(b):
        return max(0, (b[2] - b[0])) * max(0, (b[3] - b[1])) / 1e6
    max_area = {(e["PatientID"], t): max(area_frac(b) for b in e["gt_canvas_yxyx"][t]) for e in man["V96"] for t in ("qA", "qB")}
    med = float(np.median(list(max_area.values())))
    tr_norm = {RT.normalize(s) for x in man["T305"] for s in x["sentences"].values()}
    strat = {"multi_box": lambda e, t: len(e["gt_canvas_yxyx"][t]) > 1, "single_box": lambda e, t: len(e["gt_canvas_yxyx"][t]) == 1,
             "small_box(max GT area<median)": lambda e, t: max_area[(e["PatientID"], t)] < med,
             "large_box": lambda e, t: max_area[(e["PatientID"], t)] >= med,
             "sentence_in_T305": lambda e, t: RT.normalize(e["sentences"][t]) in tr_norm,
             "sentence_not_in_T305": lambda e, t: RT.normalize(e["sentences"][t]) not in tr_norm}
    strata = {}
    for name, fn in strat.items():
        ks = [(e["PatientID"], t) for e in man["V96"] for t in ("qA", "qB") if fn(e, t)]
        strata[name] = {"n_sentences": len(ks), "systems": {}}
        for s in ("M0_real", "C_real", "P"):
            strata[name]["systems"][s] = {"f1_03": float(np.mean([rows[s][k]["f1_03"] for k in ks])),
                                          "missed_gt_per_sentence": float(np.mean([rows[s][k]["n_gt"] - rows[s][k]["tp_03"] for k in ks])),
                                          "fp_per_sentence": float(np.mean([rows[s][k]["fp_03"] for k in ks])),
                                          "empty_rate": float(np.mean([bool(rows[s][k]["empty"]) for k in ks]))}
        # 환자 cluster bootstrap 대신 문장 수준이 아닌 환자 paired: 층 안 P-C 차이는 환자별 문장 평균으로
        pp = sorted({k[0] for k in ks})
        if len(pp) >= 5:
            dd = np.array([np.mean([rows["P"][(p, t)]["f1_03"] - rows["C_real"][(p, t)]["f1_03"] for t in ("qA", "qB") if (p, t) in set(ks)]) for p in pp])
            strata[name]["P_minus_C_f1_03_ci95_patient"] = ci(dd, 0.95, boot_idx(len(pp)))
    # ---- 동일 문장 쌍 ----
    pair_rows = []
    per_model = {}
    inv = {"f1_invariance_checked": 0, "f1_invariance_mismatch": 0}
    for m in ("M0", "C"):
        for p in man["pairs"]:
            dirs = []
            for rec, don in ((p["a"], p["b"]), (p["b"], p["a"])):
                er, ed = v96[rec["PatientID"]], v96[don["PatientID"]]
                t = rec["qID"]
                O, S_ = real[m][(er["PatientID"], t)], new[m]["swap"][(er["PatientID"], t)]
                if S_["image"] != ed["image"] or S_["input_pixel_sha256"] != ed["input_pixel_sha256"] or S_["donor_patient"] != ed["PatientID"]:
                    raise R.RunError("swap record image != donor manifest image")
                if tuple(S_["pad_affine_top_left_side"]) != tuple(geometry.pad_offsets(ed["h"], ed["w"])) or \
                        tuple(O["pad_affine_top_left_side"]) != tuple(geometry.pad_offsets(er["h"], er["w"])):
                    raise R.RunError("pad affine mismatch")
                sO, bO = parsed(O)
                sS, bS = parsed(S_)
                nO = [canvas_to_norm_xyxy(b, O["pad_affine_top_left_side"], er["h"], er["w"]) for b in bO]
                nS = [canvas_to_norm_xyxy(b, S_["pad_affine_top_left_side"], ed["h"], ed["w"]) for b in bS]
                gtr, gtd = er["gt_boxes_xyxy_norm"][t], ed["gt_boxes_xyxy_norm"][don["qID"]]
                # 좌표 변환 불변성: 실제 영상 출력의 canvas F1 == original-normalized F1
                c_ = score_canvas(sO, bO, er["gt_canvas_yxyx"][t])
                n_ = score_norm(sO, nO, gtr)
                inv["f1_invariance_checked"] += 1
                inv["f1_invariance_mismatch"] += int(abs(c_["f1_03"] - n_["f1_03"]) > 1e-9 or abs(c_["f1_05"] - n_["f1_05"]) > 1e-9)
                d = {"recipient": er["PatientID"], "donor": ed["PatientID"], "t": t, "status_orig": sO, "status_swap": sS,
                     "n_pred_orig": len(bO), "n_pred_swap": len(bS), "identical_output_text": O["suffix_text_raw"] == S_["suffix_text_raw"],
                     "n_gt_recipient": len(gtr), "n_gt_donor": len(gtd)}
                for thr, key in ((0.3, "03"), (0.5, "05")):
                    fo = S39.sent_metrics(nO if sO in parse.VALID else [], gtr, thr)["f1"]
                    fs_r = S39.sent_metrics(nS if sS in parse.VALID else [], gtr, thr)["f1"]
                    fs_d = S39.sent_metrics(nS if sS in parse.VALID else [], gtd, thr)["f1"]
                    fo_d = S39.sent_metrics(nO if sO in parse.VALID else [], gtd, thr)["f1"]
                    cross = S39.sent_metrics(gtd, gtr, thr)["f1"]
                    d.update({f"f1_{key}_orig_vs_recipient": fo, f"f1_{key}_swap_vs_recipient": fs_r, f"f1_{key}_swap_vs_donor": fs_d,
                              f"f1_{key}_orig_vs_donor": fo_d, f"f1_{key}_gt_cross": cross,
                              f"B_{key}": fo - fs_r, f"corr_{key}": fs_d - fs_r, f"gt_sep_{key}": 1 - cross})
                dirs.append(d)
            pr = {"model": m, "pair_id": p["pair_id"], "cluster": p["cluster"], "dirs": dirs}
            for key in ("B_03", "B_05", "corr_03", "corr_05", "gt_sep_03", "gt_sep_05", "f1_03_orig_vs_recipient", "f1_05_orig_vs_recipient",
                        "f1_05_swap_vs_recipient", "f1_05_swap_vs_donor", "f1_03_swap_vs_recipient", "f1_03_swap_vs_donor"):
                pr[key] = float(np.mean([d[key] for d in dirs]))
            pair_rows.append(pr)
    ncl = len({p["cluster"] for p in man["pairs"]})
    cl_ids = sorted({p["cluster"] for p in man["pairs"]})
    cidx = np.random.default_rng(SEED).integers(0, ncl, size=(NBOOT, ncl), dtype=np.int32)

    def cluster_ci(model, key, level):
        vals = {c: [pr[key] for pr in pair_rows if pr["model"] == model and pr["cluster"] == c] for c in cl_ids}
        s = np.array([sum(vals[c]) for c in cl_ids])
        n = np.array([len(vals[c]) for c in cl_ids])
        allv = [pr[key] for pr in pair_rows if pr["model"] == model]
        rep_ = s[cidx].sum(axis=1) / n[cidx].sum(axis=1)
        al = (1 - level) / 2 * 100
        return {"mean": float(np.mean(allv)), "lo": float(np.percentile(rep_, al)), "hi": float(np.percentile(rep_, 100 - al)),
                "level": level, "n_pairs": len(allv), "n_clusters": ncl}
    for m in ("M0", "C"):
        pm = [pr for pr in pair_rows if pr["model"] == m]
        dd = [d for pr in pm for d in pr["dirs"]]
        per_model[m] = {k: {"ci95": cluster_ci(m, k, 0.95), "ci975": cluster_ci(m, k, 0.975)}
                        for k in ("B_05", "B_03", "corr_05", "corr_03", "f1_05_orig_vs_recipient", "f1_03_orig_vs_recipient",
                                  "f1_05_swap_vs_recipient", "f1_05_swap_vs_donor", "f1_03_swap_vs_recipient", "f1_03_swap_vs_donor")}
        per_model[m]["gt_cross_reference"] = {k: {"ci95": cluster_ci(m, k, 0.95), "ci975": cluster_ci(m, k, 0.975)} for k in ("gt_sep_05", "gt_sep_03")}
        per_model[m]["counts"] = {"n_queries": len(dd), "swap_output_text_identical_to_original": sum(d["identical_output_text"] for d in dd),
                                  "orig_invalid": sum(d["status_orig"] not in parse.VALID for d in dd),
                                  "swap_invalid": sum(d["status_swap"] not in parse.VALID for d in dd),
                                  "orig_empty": sum(d["status_orig"] == "valid_empty" for d in dd),
                                  "swap_empty": sum(d["status_swap"] == "valid_empty" for d in dd),
                                  "swap_nonempty_vs_orig_nonempty": [sum(d["status_swap"] == "valid_nonempty" for d in dd),
                                                                     sum(d["status_orig"] == "valid_nonempty" for d in dd)],
                                  "n_pairs_B_05_positive": sum(pr["B_05"] > 0 for pr in pm), "n_pairs_B_05_zero": sum(pr["B_05"] == 0 for pr in pm),
                                  "n_pairs_B_05_negative": sum(pr["B_05"] < 0 for pr in pm),
                                  "pairs_gt_sep_05_positive": sum(pr["gt_sep_05"] > 0 for pr in pm),
                                  "pairs_gt_sep_03_positive": sum(pr["gt_sep_03"] > 0 for pr in pm)}
        # 두 출력이 모두 valid nonempty인 방향만 (invalid/empty에 의한 B 상승 배제 민감도)
        okd = [d for d in dd if d["status_orig"] == "valid_nonempty" and d["status_swap"] == "valid_nonempty"]
        per_model[m]["both_valid_nonempty_directions"] = {"n": len(okd), "B_05_mean": float(np.mean([d["B_05"] for d in okd])) if okd else None,
                                                          "corr_05_mean": float(np.mean([d["corr_05"] for d in okd])) if okd else None}
    # P (retrieval)의 같은 쌍 진단: 같은 문장은 같은 box 집합이므로 교환에 반응하지 않는다 (정의상 B_P=0)
    pair_P = []
    for p in man["pairs"]:
        vals = []
        for rec in (p["a"], p["b"]):
            e = v96[rec["PatientID"]]
            vals.append(rows["P"][(e["PatientID"], rec["qID"])]["f1_05"])
        pair_P.append(float(np.mean(vals)))
    per_model["P"] = {"f1_05_recipient_pair_mean": float(np.mean(pair_P)),
                      "note": "동일 문장 -> 동일 normalized box 집합: 영상 교환에 대한 출력 변화 0 (영상 미사용)"}
    # ---- 결정 규칙 (사전 고정) ----
    valid_ok = {m: prim[f"{m}_text"]["valid_rate"] >= prim[f"{m}_real"]["valid_rate"] - 0.05 for m in ("M0", "C")}
    PmC = pairs_cmp["P_minus_C_real"]["f1_03_ci975"]
    CmP = pairs_cmp["C_real_minus_P"]["f1_03_ci975"]
    Cm = per_model["C"]
    prov_ok = c_repro["token_mismatch"] == 0 and inv["f1_invariance_mismatch"] == 0
    pos = {"P_minus_C_lo_ge_-0.03": PmC["lo"] >= -0.03, "C_real_f1_05_pairs_ge_0.20": Cm["f1_05_orig_vs_recipient"]["ci975"]["mean"] >= 0.20,
           "B_C_hi_le_0.10": Cm["B_05"]["ci975"]["hi"] <= 0.10, "gt_sep_lo_gt_0.20": Cm["gt_cross_reference"]["gt_sep_05"]["ci975"]["lo"] > 0.20,
           "provenance_ok": prov_ok}
    neg = {"C_minus_P_lo_gt_0.03": CmP["lo"] > 0.03, "B_C_lo_gt_0.10": Cm["B_05"]["ci975"]["lo"] > 0.10,
           "swap_corresponds_to_donor": bool(Cm["corr_05"]["ci975"]["mean"] > 0 and Cm["corr_05"]["ci975"]["lo"] > 0), "provenance_ok": prov_ok}
    outcome = "positive_pilot_candidate" if all(pos.values()) else ("negative_prior_explanation_weakened" if all(neg.values()) else "inconclusive_hold")
    dec = {"positive_conditions": pos, "negative_conditions": neg, "outcome": outcome, "text_only_valid_within_5pp": valid_ok,
           "note": "규칙은 plan.md Evaluation을 결과 전에 코드로 고정. 개발 자료(V96·21쌍)이며 validated 승격이나 외부 일반화 근거가 아니다."}
    rep = {"n_patients": len(pids), "primary_V96": prim, "compare_f1_03": pairs_cmp, "strata": strata, "strata_small_threshold_max_gt_area_median": med,
           "pairs": {"n_pairs": len(man["pairs"]), "n_clusters": ncl, "models": per_model, "coordinate_invariance": inv},
           "retrieval": {"setting": sel["chosen"], "d24_scores": sel["scores"]}, "c_repro_iter041_vs_iter040": c_repro, "decision": dec,
           "provenance": {"eval_source_sha256": R.file_sha("pg43_eval.py"), "retrieval_source_sha256": R.file_sha("pg43_retrieval.py"),
                          "spec_sha256": R.file_sha("pg39_spec.py"), "parse_sha256": R.file_sha("rsna_diag/parse.py"),
                          "metrics_sha256": R.file_sha("rsna_diag/metrics.py"), "manifest_sha256": R.file_sha(f"{OUT}/data/manifest_private.json"),
                          "selection_lock_sha256": R.file_sha(f"{OUT}/data/selection_lock.json"),
                          "retrieval_selection_sha256": R.file_sha(f"{OUT}/retrieval/selection.json"),
                          "protocol_digest_new": {m: new[m]["protocol_digest"] for m in new},
                          "completion_sha256_new": {m: R.file_sha(f"{OUT}/gen/MAIN_{m}/completion.json") for m in new},
                          "imported": {m: {"gen": IMPORTS[m]["gen"], "completion_sha256": R.file_sha(IMPORTS[m]["gen"] + "/completion.json"),
                                           "protocol_sha256": R.file_sha(IMPORTS[m]["protocol"]), "requests_sha256": R.file_sha(IMPORTS[m]["requests"])}
                                       for m in IMPORTS},
                          "bootstrap": {"B": NBOOT, "seed": SEED}, "eval_wall_s": time.time() - t_start}}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    tmp = a.out + f".{os.getpid()}.tmp"
    json.dump(rep, open(tmp, "w"), indent=1)
    tmp2 = a.out.replace(".json", "_per_item.json") + f".{os.getpid()}.tmp"
    json.dump({"sentences": {s: {f"{k[0]}|{k[1]}": v for k, v in rows[s].items()} for s in sysnames}, "pairs": pair_rows}, open(tmp2, "w"))
    os.replace(tmp2, a.out.replace(".json", "_per_item.json"))
    os.replace(tmp, a.out)
    print(json.dumps({"outcome": outcome, "P": prim["P"]["f1_03"]["mean"], "C": prim["C_real"]["f1_03"]["mean"], "M0": prim["M0_real"]["f1_03"]["mean"],
                      "pos": pos, "neg": neg}, indent=1))


if __name__ == "__main__":
    main()
