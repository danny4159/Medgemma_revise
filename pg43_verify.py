"""iter_043 독립 재계산: pg39_spec/rsna_diag.parse·metrics/pg43_eval/pg43_retrieval을 쓰지 않는 별도 구현 (좌표·matching·parser는 pg41_verify의 순수 함수 재사용).
- 원시 record의 suffix_text_raw를 strict whole-string JSON으로 해석한다 (pipeline parser보다 엄격). pipeline이 valid로 본 record와 strict 판정이 다르면 그 수를 그대로 보고하며 조용히 보정하지 않는다.
- retrieval k=1은 별도 TF-IDF 구현으로 재계산한다.
- 쌍 분석은 pixel 좌표 변환(직접 구현)으로 original normalized 좌표를 만들고 max_matching F1을 계산한다. cluster bootstrap은 다른 seed로 CI를 재계산한다.
python pg43_verify.py --report results/iter_043/eval/report.json --out results/iter_043/eval/verify.json
"""
import argparse
import glob
import hashlib
import json
import math
import os
import re
import sys
from collections import Counter

import numpy as np

import pg41_verify as V

OUT = "results/iter_043"


def read_dir(d):
    recs = {}
    for f in sorted(glob.glob(os.path.join(d, "gen_worker*.jsonl"))):
        for ln in open(f):
            if ln.strip():
                r = json.loads(ln)
                key = (r["patient"], r["targets"][0], r["cond"])
                assert key not in recs, key
                recs[key] = r
    return recs


def strict_boxes(r):
    ok, g = V.parse(r["suffix_text_raw"], r["ended_eos"], set(r["targets"]))
    return ok, g.get(r["targets"][0], []) if ok else []


def _balanced_lists(text):
    out, i, n = [], 0, len(text)
    while i < n:
        if text[i] != "[":
            i += 1
            continue
        depth, j, ins, esc = 0, i, False, False
        while j < n:
            c = text[j]
            if ins:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    ins = False
            elif c == '"':
                ins = True
            elif c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if depth == 0 and j < n:
            out.append(text[i:j + 1])
            i = j + 1
        else:
            break
    return out


def lenient_boxes(r):
    """M0처럼 thinking/'Final Answer' 표지가 붙는 응답용 별도 추출: EOS 필수, thinking 종료 표지 뒤에서 완결 JSON list 후보를 찾고,
    서로 다른 후보가 정확히 하나일 때만 사용(없거나 여럿이면 invalid). label은 요청 target과 같아야 한다."""
    if not r["ended_eos"]:
        return False, []
    t = r["suffix_text_raw"]
    t = t[:-len(V.EOT)] if t.endswith(V.EOT) else t
    if "<unused95>" in t:
        t = t.split("<unused95>", 1)[1]
    elif "<unused94>" in t:
        return False, []
    cands = []
    for raw in _balanced_lists(t):
        try:
            v = json.loads(raw)
        except Exception:
            continue
        if isinstance(v, list) and all(isinstance(x, dict) for x in v):
            cands.append(raw if False else json.dumps(v, sort_keys=True))
    if len(set(cands)) != 1:
        return False, []
    arr = json.loads(cands[0])
    tgt = r["targets"][0]
    out = []
    for e in arr:
        b, lab = e.get("box_2d"), e.get("label")
        if not (isinstance(b, list) and len(b) == 4 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in b) and isinstance(lab, str)):
            return False, []
        if not (0 <= b[0] < b[2] <= 1000 and 0 <= b[1] < b[3] <= 1000):
            return False, []
        m = re.fullmatch(r"\s*q([abAB])\s*", lab)
        if not m:
            return False, []
        if "q" + m.group(1).upper() == tgt:
            out.append([float(v) for v in b])
    return True, out


def boxes_for(model, r):
    return lenient_boxes(r) if model == "M0" else strict_boxes(r)


def norm_of_canvas(b, aff, h, w):
    top, left, side = aff
    y0, x0, y1, x1 = b
    return [(x0 * side / 1000 - left) / w, (y0 * side / 1000 - top) / h, (x1 * side / 1000 - left) / w, (y1 * side / 1000 - top) / h]


def f1n(pred, gt, thr):  # generic-layout IoU (V.iou uses indices 0,1 min / 2,3 max)
    return V.f1(pred, gt, thr)


# ---- independent retrieval (word 1-2 gram, k=1) ----
def toks(s):
    w = re.findall(r"\w+", " ".join(s.lower().split()))
    return w + [a + " " + b for a, b in zip(w, w[1:])]


def retrieval_k1(train, queries):
    docs = [Counter(toks(s)) for s, _ in train]
    df = Counter()
    for d in docs:
        df.update(d.keys())
    n = len(docs)
    idf = {t: math.log((1 + n) / (1 + c)) + 1.0 for t, c in df.items()}

    def vec(c):
        v = {t: k * idf[t] for t, k in c.items() if t in idf}
        nr = math.sqrt(sum(x * x for x in v.values()))
        return {t: x / nr for t, x in v.items()} if nr > 0 else {}
    dv = [vec(d) for d in docs]
    out = {}
    for q in queries:
        qn = " ".join(q.lower().split())
        qv = vec(Counter(toks(q)))
        best = None
        for j, d in enumerate(dv):
            s = round(sum(x * d.get(t, 0.0) for t, x in qv.items()), 12)
            tie = hashlib.sha256(f"4304|{qn}|{j}|{' '.join(train[j][0].lower().split())}".encode()).hexdigest()
            key = (-s, tie)
            if best is None or key < best[0]:
                best = (key, j)
        out[q] = train[best[1]][1]
    return out


def boot_ci(v, level, seed):
    v = np.asarray(v, float)
    idx = np.random.default_rng(seed).integers(0, len(v), size=(10000, len(v)), dtype=np.int32)
    m = v[idx].mean(axis=1)
    a = (1 - level) / 2 * 100
    return [float(v.mean()), float(np.percentile(m, a)), float(np.percentile(m, 100 - a))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("output exists")
    rep = json.load(open(a.report))
    item = json.load(open(a.report.replace(".json", "_per_item.json")))
    man = json.load(open(f"{OUT}/data/manifest_private.json"))
    v96 = {e["PatientID"]: e for e in man["V96"]}
    pids = [e["PatientID"] for e in man["V96"]]
    src = {"M0_real": "results/iter_039/gen/E96", "C_real": "results/iter_040/gen/C", "M0_text": f"{OUT}/gen/MAIN_M0", "C_text": f"{OUT}/gen/MAIN_C"}
    conds = {"M0_real": "I-short", "C_real": "I-short", "M0_text": "I-short-text", "C_text": "I-short-text"}
    res = {"systems": {}, "pairs": {}}
    per = {}
    for s, d in src.items():
        recs = read_dir(d)
        vals3, vals5, strict_invalid = {}, {}, 0
        for p in pids:
            e = v96[p]
            f3, f5 = [], []
            for t in ("qA", "qB"):
                r = recs[(p, t, conds[s])]
                ok, bx = boxes_for(s.split("_")[0], r)
                strict_invalid += (not ok)
                gt = [V.canvas(b, e["h"], e["w"]) for b in e["gt_boxes_xyxy_norm"][t]]
                f3.append(V.f1(bx, gt, 0.3))
                f5.append(V.f1(bx, gt, 0.5))
            vals3[p], vals5[p] = float(np.mean(f3)), float(np.mean(f5))
        per[s] = vals3
        rp = item["sentences"][s]
        pipe = {p: float(np.mean([rp[f"{p}|{t}"]["f1_03"] for t in ("qA", "qB")])) for p in pids}
        pipe_invalid = sum(1 for k, v in rp.items() if v["status"] not in ("valid_nonempty", "valid_empty"))
        res["systems"][s] = {"strict_f1_03_mean": float(np.mean(list(vals3.values()))), "strict_f1_05_mean": float(np.mean(list(vals5.values()))),
                             "pipeline_f1_03_mean": float(np.mean(list(pipe.values()))),
                             "report_f1_03_mean": rep["primary_V96"][s]["f1_03"]["mean"], "report_f1_05_mean": rep["primary_V96"][s]["f1_05"]["mean"],
                             "max_abs_patient_f1_03_diff_strict_vs_pipeline": max(abs(vals3[p] - pipe[p]) for p in pids),
                             "strict_invalid_records": strict_invalid, "pipeline_invalid_records": pipe_invalid,
                             "n_patients_strict_pipeline_differ": sum(abs(vals3[p] - pipe[p]) > 1e-9 for p in pids)}
    # retrieval
    train = [(x["sentences"][t], x["gt_boxes_xyxy_norm"][t]) for x in man["T305"] for t in ("qA", "qB")]
    qs = sorted({v96[p]["sentences"][t] for p in pids for t in ("qA", "qB")})
    pred = retrieval_k1(train, qs)
    vp3, vp5 = {}, {}
    for p in pids:
        e = v96[p]
        f3, f5 = [], []
        for t in ("qA", "qB"):
            bx = [V.canvas(b, e["h"], e["w"]) for b in pred[e["sentences"][t]]]
            gt = [V.canvas(b, e["h"], e["w"]) for b in e["gt_boxes_xyxy_norm"][t]]
            f3.append(V.f1(bx, gt, 0.3))
            f5.append(V.f1(bx, gt, 0.5))
        vp3[p], vp5[p] = float(np.mean(f3)), float(np.mean(f5))
    per["P"] = vp3
    rp = item["sentences"]["P"]
    res["systems"]["P"] = {"indep_f1_03_mean": float(np.mean(list(vp3.values()))), "indep_f1_05_mean": float(np.mean(list(vp5.values()))),
                           "report_f1_03_mean": rep["primary_V96"]["P"]["f1_03"]["mean"],
                           "max_abs_patient_f1_03_diff": max(abs(vp3[p] - np.mean([rp[f"{p}|{t}"]["f1_03"] for t in ("qA", "qB")])) for p in pids)}
    # 차이 CI (다른 seed) : P-C, C-M0
    def d(x, y):
        return np.array([per[x][p] - per[y][p] for p in pids])
    res["diff_ci975_other_seed"] = {"P_minus_C_real": boot_ci(d("P", "C_real"), 0.975, 99), "C_real_minus_P": boot_ci(-d("P", "C_real"), 0.975, 99),
                                    "C_real_minus_M0_real": boot_ci(d("C_real", "M0_real"), 0.975, 99)}
    res["diff_ci975_report"] = {k: [rep["compare_f1_03"][k]["f1_03_ci975"][x] for x in ("mean", "lo", "hi")]
                                for k in ("P_minus_C_real", "C_real_minus_P", "C_real_minus_M0_real")}
    # ---- pairs ----
    recs = {"M0": (read_dir(src["M0_real"]), read_dir(f"{OUT}/gen/MAIN_M0")), "C": (read_dir(src["C_real"]), read_dir(f"{OUT}/gen/MAIN_C"))}
    rows = {}
    for m, (real, main) in recs.items():
        out = []
        for p in man["pairs"]:
            dv = {k: [] for k in ("B_05", "corr_05", "gt_sep_05", "o_r_05", "B_03", "gt_sep_03")}
            for rec, don in ((p["a"], p["b"]), (p["b"], p["a"])):
                er, ed = v96[rec["PatientID"]], v96[don["PatientID"]]
                t = rec["qID"]
                O = real[(er["PatientID"], t, "I-short")]
                S_ = main[(er["PatientID"], t, "I-short-swap")]
                assert S_["donor_patient"] == ed["PatientID"] and S_["input_pixel_sha256"] == ed["input_pixel_sha256"]
                okO, bO = boxes_for(m, O)
                okS, bS = boxes_for(m, S_)
                nO = [norm_of_canvas(b, O["pad_affine_top_left_side"], er["h"], er["w"]) for b in bO]
                nS = [norm_of_canvas(b, S_["pad_affine_top_left_side"], ed["h"], ed["w"]) for b in bS]
                gr, gd = er["gt_boxes_xyxy_norm"][t], ed["gt_boxes_xyxy_norm"][don["qID"]]
                for thr, k in ((0.5, "05"), (0.3, "03")):
                    fo, fs, fsd = V.f1(nO, gr, thr), V.f1(nS, gr, thr), V.f1(nS, gd, thr)
                    dv[f"B_{k}"].append(fo - fs)
                    dv[f"gt_sep_{k}"].append(1 - V.f1(gd, gr, thr))
                    if k == "05":
                        dv["corr_05"].append(fsd - fs)
                        dv["o_r_05"].append(fo)
            out.append({"cluster": p["cluster"], **{k: float(np.mean(v)) for k, v in dv.items()}})
        rows[m] = out
    ncl = 17
    def cl_ci(m, key, level, seed):
        cl = {}
        for r in rows[m]:
            cl.setdefault(r["cluster"], []).append(r[key])
        ids = sorted(cl)
        s = np.array([sum(cl[c]) for c in ids])
        n = np.array([len(cl[c]) for c in ids])
        idx = np.random.default_rng(seed).integers(0, len(ids), size=(10000, len(ids)), dtype=np.int32)
        rep_ = s[idx].sum(axis=1) / n[idx].sum(axis=1)
        al = (1 - level) / 2 * 100
        return [float(np.mean([r[key] for r in rows[m]])), float(np.percentile(rep_, al)), float(np.percentile(rep_, 100 - al))]
    key_map = {"B_05": "B_05", "corr_05": "corr_05", "gt_sep_05": "gt_sep_05", "o_r_05": "f1_05_orig_vs_recipient"}
    for m in ("M0", "C"):
        res["pairs"][m] = {}
        for k, rk in key_map.items():
            ind = cl_ci(m, k, 0.975, 98)
            if k == "gt_sep_05":
                repv = rep["pairs"]["models"][m]["gt_cross_reference"]["gt_sep_05"]["ci975"]
            else:
                repv = rep["pairs"]["models"][m][rk]["ci975"]
            res["pairs"][m][k] = {"indep_mean_ci975(other seed)": ind, "report": [repv["mean"], repv["lo"], repv["hi"]],
                                  "mean_abs_diff": abs(ind[0] - repv["mean"])}
    res["posthoc_descriptive_separable_pairs"] = {"note": "사후 기술 분석(결정 규칙에 미사용): IoU0.5에서 두 환자 GT가 다른 쌍(gt_sep_05>0)만의 B_05",
                                                  "models": {}}
    for m in ("M0", "C"):
        sep = [r for r in rows[m] if r["gt_sep_05"] > 0]
        non = [r for r in rows[m] if r["gt_sep_05"] <= 0]
        ent = {"n_separable_pairs": len(sep), "n_nonseparable_pairs": len(non),
               "B_05_mean_separable": float(np.mean([r["B_05"] for r in sep])), "B_05_mean_nonseparable": float(np.mean([r["B_05"] for r in non])),
               "orig_f1_05_mean_separable": float(np.mean([r["o_r_05"] for r in sep])), "orig_f1_05_mean_nonseparable": float(np.mean([r["o_r_05"] for r in non])),
               "gt_sep_05_mean_separable": float(np.mean([r["gt_sep_05"] for r in sep]))}
        cl = {}
        for r in sep:
            cl.setdefault(r["cluster"], []).append(r["B_05"])
        ids = sorted(cl)
        sm = np.array([sum(cl[c]) for c in ids])
        nn = np.array([len(cl[c]) for c in ids])
        idx = np.random.default_rng(97).integers(0, len(ids), size=(10000, len(ids)), dtype=np.int32)
        rp_ = sm[idx].sum(axis=1) / nn[idx].sum(axis=1)
        ent["B_05_separable_cluster_ci95"] = [ent["B_05_mean_separable"], float(np.percentile(rp_, 2.5)), float(np.percentile(rp_, 97.5))]
        ent["n_clusters_with_separable_pairs"] = len(ids)
        res["posthoc_descriptive_separable_pairs"]["models"][m] = ent
    res["mean_match_1e-9"] = bool(all(v["mean_abs_diff"] < 1e-9 for m in res["pairs"].values() for v in m.values())
                                  and all(abs(s.get("strict_f1_03_mean", s.get("indep_f1_03_mean")) - s["report_f1_03_mean"]) < 1e-9
                                          for s in res["systems"].values() if s.get("n_patients_strict_pipeline_differ", 0) == 0))
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(res, open(a.out, "x"), indent=1)
    print(json.dumps(res, indent=1)[:5000])


if __name__ == "__main__":
    main()
