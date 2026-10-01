"""iter_048 독립 검증기 (CPU). pg39_spec/pg48_eval/rsna_diag.parse·metrics를 호출하지 않는 별도 구현.

원시 record(gen_worker*.jsonl, raw_worker*.jsonl)에서 strict JSON 목록을 직접 해석하고(순수 JSON만 유효; label은 qA/qB, 좌표 유한·양의 크기·0~1000),
GT canvas는 원본 normalized xyxy와 영상 크기에서 다시 계산, matching은 augmenting path, bootstrap은 같은 seed/index 생성 규칙(10,000회, seed 4801)을 독립 구현한다.
검증 대상: C·E·J의 I/AB/BA, A 모두 (불일치 시스템을 제외하지 않는다 -- 실패는 all_ok=false로 그대로 남긴다).
비교: 환자별 점수 벡터(per_patient.json) 정확도 1e-12, 시스템 점수 CI·주비교 CI 1e-9.

python pg48_verify.py --report R --select S --out OUT
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys

import numpy as np

MAN = "results/iter_043/data/manifest_private.json"
EOT = "<end_of_turn>"
LABEL = re.compile(r"\s*q([abAB])\s*")


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def canvas(box, h, w):
    side = max(h, w)
    top = (side - h) // 2 if h < w else 0
    left = (side - w) // 2 if w < h else 0
    x0, y0, x1, y1 = box[0] * w, box[1] * h, box[2] * w, box[3] * h
    return [(y0 + top) * 1000 / side, (x0 + left) * 1000 / side, (y1 + top) * 1000 / side, (x1 + left) * 1000 / side]


def iou(a, b):
    ih = min(a[2], b[2]) - max(a[0], b[0])
    iw = min(a[3], b[3]) - max(a[1], b[1])
    if ih <= 0 or iw <= 0:
        return 0.0
    i = ih * iw
    return i / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i)


def tp_count(pred, gt, thr):
    adj = [[j for j, p in enumerate(pred) if iou(g, p) >= thr] for g in gt]
    owner = {}

    def aug(u, seen):
        for v in adj[u]:
            if v in seen:
                continue
            seen.add(v)
            if v not in owner or aug(owner[v], seen):
                owner[v] = u
                return True
        return False
    return sum(aug(u, set()) for u in range(len(gt)))


def metrics(pred, gt, thr):
    tp = tp_count(pred, gt, thr) if pred and gt else 0
    prec = tp / len(pred) if pred else 0.0
    rec = tp / len(gt) if gt else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return f1, rec, len(pred) - tp


def strict_parse(raw, ended):
    """returns (ok, {qA:[boxes], qB:[boxes]}, reason)."""
    if not ended:
        return False, {}, "not_eos"
    t = raw[:-len(EOT)] if raw.endswith(EOT) else raw
    try:
        arr = json.loads(t.strip())
    except Exception:
        return False, {}, "json"
    if not isinstance(arr, list):
        return False, {}, "not_list"
    out = {"qA": [], "qB": []}
    for e in arr:
        if not isinstance(e, dict) or set(e) != {"box_2d", "label"}:
            return False, {}, "entry"
        b, lab = e["box_2d"], e["label"]
        if not (isinstance(b, list) and len(b) == 4 and all(isinstance(v, (int, float)) and not isinstance(v, bool) and np.isfinite(v) for v in b) and isinstance(lab, str)):
            return False, {}, "box_type"
        if not (0 <= b[0] < b[2] <= 1000 and 0 <= b[1] < b[3] <= 1000):
            return False, {}, "box_range"
        m = LABEL.fullmatch(lab)
        if not m:
            return False, {}, "label"
        out["q" + m.group(1).upper()].append([float(v) for v in b])
    return True, out, "ok"


def read_jsonl_dir(d, pat="gen_worker*.jsonl"):
    recs = []
    for fn in sorted(glob.glob(os.path.join(d, pat))):
        for ln in open(fn, "rb").read().split(b"\n")[:-1]:
            if ln.strip():
                recs.append(json.loads(ln))
    return recs


def boot_idx(n, seed=4801, B=10000):
    return np.random.default_rng(seed).integers(0, n, size=(B, n), dtype=np.int32)


def ci(vals, level, idx):
    v = np.asarray(vals, float)
    m = v[idx].mean(axis=1)
    a = (1 - level) / 2 * 100
    return [float(v.mean()), float(np.percentile(m, a)), float(np.percentile(m, 100 - a))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--select", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit("exists")
    man = json.load(open(MAN))
    ents = {e["PatientID"]: e for e in man["V96"]}
    pids = [e["PatientID"] for e in man["V96"]]
    rep = json.load(open(a.report))
    per = json.load(open(a.report.replace(".json", "_per_patient.json")))
    dry = "tests/dryrun" in a.report
    if not dry and not os.path.exists(a.select):
        sys.exit("selection gate file required")
    assert per["patients"] == pids
    gt_canvas = {p: {t: [canvas(b, ents[p]["h"], ents[p]["w"]) for b in ents[p]["gt_boxes_xyxy_norm"][t]] for t in ("qA", "qB")} for p in pids}
    # ---- 원시 record 위치 (보고서 provenance의 gen_dir)
    prov = rep["provenance"]
    dirs = {"C": {"I": prov["C"]["I"]["gen_dir"], "AB": prov["C"]["AB"]["gen_dir"], "BA": prov["C"]["BA"]["gen_dir"]}}
    for n in ("E", "J"):
        if prov[n].get("dry_run_stand_in") == "C":
            dirs[n] = dict(dirs["C"])
            continue
        d = prov[n]["gen_dir"]
        dirs[n] = {"I": d, "AB": d, "BA": d}
    res = {"systems": {}, "vector_check": {}, "ci_check": {}, "label_coord_checks": {}}
    V = {}
    cond_of = {"I": "I-short", "AB": "J-short", "BA": "J-short-rev"}
    for n, dd in dirs.items():
        invalid_reasons = {}
        nbox, nbad_box = 0, 0
        patient = {"I": {}, "AB": {}, "BA": {}}
        for kind, d in dd.items():
            seen = set()
            for r in read_jsonl_dir(d):
                if r["cond"] != cond_of[kind] or r["patient"] not in ents:
                    continue
                key = (r["patient"], tuple(r["targets"]))
                assert key not in seen, f"duplicate record {n} {kind} {key}"
                seen.add(key)
                ok, groups, why = strict_parse(r["suffix_text_raw"], r["ended_eos"])
                invalid_reasons[why] = invalid_reasons.get(why, 0) + 1
                if ok:
                    for g in groups.values():
                        for b in g:
                            nbox += 1
                            nbad_box += not (all(np.isfinite(b)) and b[0] < b[2] and b[1] < b[3])
                for t in r["targets"]:
                    pred = groups.get(t, []) if ok else []
                    if kind == "I" and t not in r["targets"]:
                        continue
                    patient[kind].setdefault(r["patient"], {})[t] = {"m3": metrics(pred, gt_canvas[r["patient"]][t], 0.3), "m5": metrics(pred, gt_canvas[r["patient"]][t], 0.5), "ok": ok}
            n_expect = 192 if kind == "I" else 96
            assert sum(len(v) for v in patient[kind].values()) == (192 if kind == "I" else 192), f"coverage {n} {kind}: {sum(len(v) for v in patient[kind].values())}"
        res["label_coord_checks"][n] = {"n_boxes": nbox, "nonfinite_or_nonpositive": nbad_box, "invalid_reasons": invalid_reasons}

        def vec(kind, which, idx_):
            return np.array([np.mean([patient[kind][p][t][which][idx_] for t in ("qA", "qB")]) for p in pids])
        for kind in ("I", "AB", "BA"):
            V[(n, kind, "f1_03")] = vec(kind, "m3", 0)
            V[(n, kind, "f1_05")] = vec(kind, "m5", 0)
            V[(n, kind, "recall_03")] = vec(kind, "m3", 1)
            V[(n, kind, "fp_03")] = vec(kind, "m3", 2)
        for m in ("f1_03", "f1_05", "recall_03", "fp_03"):
            V[(n, "J", m)] = (V[(n, "AB", m)] + V[(n, "BA", m)]) / 2
    # ---- A
    A = {}
    arec = read_jsonl_dir(prov["A"]["gen_dir"], "raw_worker*.jsonl")
    assert len(arec) == 192 and len({(r["patient"], r["target"]) for r in arec}) == 192
    abad = 0
    for r in arec:
        gtn = ents[r["patient"]]["gt_boxes_xyxy_norm"][r["target"]]
        bx = r["detections"]["0.8"]["boxes_orig_xyxy"]
        abad += sum(not (all(np.isfinite(b)) and b[0] < b[2] and b[1] < b[3]) for b in bx)
        # norm xyxy -> canvas yxyx (같은 변환) 후 matching
        pc = [canvas(b, ents[r["patient"]]["h"], ents[r["patient"]]["w"]) for b in bx]
        A[(r["patient"], r["target"])] = (metrics(pc, gt_canvas[r["patient"]][r["target"]], 0.3), metrics(pc, gt_canvas[r["patient"]][r["target"]], 0.5))
    res["label_coord_checks"]["A"] = {"n_boxes": sum(len(r["detections"]["0.8"]["boxes_orig_xyxy"]) for r in arec), "nonfinite_or_nonpositive": abad}
    V[("A", "A", "f1_03")] = np.array([np.mean([A[(p, t)][0][0] for t in ("qA", "qB")]) for p in pids])
    V[("A", "A", "f1_05")] = np.array([np.mean([A[(p, t)][1][0] for t in ("qA", "qB")]) for p in pids])
    V[("A", "A", "recall_03")] = np.array([np.mean([A[(p, t)][0][1] for t in ("qA", "qB")]) for p in pids])
    V[("A", "A", "fp_03")] = np.array([np.mean([A[(p, t)][0][2] for t in ("qA", "qB")]) for p in pids])
    # ---- 벡터 대조 (모든 시스템; 불일치 시스템을 제외하지 않는다)
    allv_ok = True
    for k, v in V.items():
        key = f"{k[0]}|{k[1]}|{k[2]}"
        rv = np.array(per["vectors"][key])
        diff = float(np.max(np.abs(rv - v)))
        res["vector_check"][key] = diff
        allv_ok &= diff <= 1e-12
    # ---- CI 대조
    idx = boot_idx(len(pids))
    ok_ci = True
    checks = {}

    def cmp_ci(name, mine, theirs):
        nonlocal ok_ci
        d = max(abs(x - y) for x, y in zip(mine, [theirs["mean"], theirs["lo"], theirs["hi"]]))
        checks[name] = d
        ok_ci &= d <= 1e-9
    for n in ("C", "E", "J"):
        for kind in ("I", "AB", "BA", "J"):
            for m in ("f1_03", "f1_05", "recall_03", "fp_03"):
                if n == "C" and kind == "J" or True:
                    cmp_ci(f"sys:{n}:{kind}:{m}", ci(V[(n, kind, m)], 0.95, idx), rep["systems"][n][kind][m])
    for m in ("f1_03", "f1_05", "recall_03", "fp_03"):
        cmp_ci(f"sys:A:{m}", ci(V[("A", "A", m)], 0.95, idx), rep["A"][m])
    c = rep["compare"]
    d = lambda x, y, m: V[x + (m,)] - V[y + (m,)]  # noqa
    e_loss = V[("E", "I", "f1_03")] - V[("E", "J", "f1_03")]
    j_loss = V[("J", "I", "f1_03")] - V[("J", "J", "f1_03")]
    cmp_ci("M1_975", ci(d(("J", "J"), ("E", "J"), "f1_03"), 0.975, idx), c["M1_J_J_minus_E_J"]["f1_03_ci975"])
    cmp_ci("M2_975", ci(e_loss - j_loss, 0.975, idx), c["M2_loss_reduction_(E_I-E_J)-(J_I-J_J)"]["f1_03_ci975"])
    cmp_ci("J_loss_95", ci(j_loss, 0.95, idx), c["J_loss_J_I_minus_J_J"]["f1_03_ci95"])
    cmp_ci("E_loss_95", ci(e_loss, 0.95, idx), c["E_loss_E_I_minus_E_J"]["f1_03_ci95"])
    for m in ("f1_03", "f1_05", "recall_03", "fp_03"):
        cmp_ci(f"J_I-E_I:{m}", ci(d(("J", "I"), ("E", "I"), m), 0.95, idx), c["J_I_minus_E_I"][m]["ci95"])
    for o in ("AB", "BA"):
        cc = c[f"J_{o}_minus_E_I"]
        cmp_ci(f"J_{o}-E_I:f1_03_975", ci(d(("J", o), ("E", "I"), "f1_03"), 0.975, idx), cc["f1_03_ci975"])
        cmp_ci(f"J_{o}-E_I:f1_05_95", ci(d(("J", o), ("E", "I"), "f1_05"), 0.95, idx), cc["f1_05_ci95"])
        cmp_ci(f"J_{o}-E_I:fp_95", ci(d(("J", o), ("E", "I"), "fp_03"), 0.95, idx), cc["fp_03_ci95"])
    for name, x in (("E_I", ("E", "I")), ("J_J", ("J", "J")), ("J_I", ("J", "I")), ("E_J", ("E", "J")), ("C_I", ("C", "I")), ("C_J", ("C", "J"))):
        cc = c[f"{name}_minus_A"]
        cmp_ci(f"{name}-A:f1_03_975", ci(d(x, ("A", "A"), "f1_03"), 0.975, idx), cc["f1_03_ci975"])
        cmp_ci(f"{name}-A:f1_05_95", ci(d(x, ("A", "A"), "f1_05"), 0.95, idx), cc["f1_05_ci95"])
        cmp_ci(f"{name}-A:fp_95", ci(d(x, ("A", "A"), "fp_03"), 0.95, idx), cc["fp_03_ci95"])
    res["ci_check"] = {"max_abs_diff": max(checks.values()), "n_checked": len(checks), "ok": ok_ci}
    # invalid 수/상태 대조
    inval_ok = True
    for n in ("C", "E", "J"):
        mine_inv = {k: sum(v for r_, v in [(0, 0)]) for k in ()}
    res["vector_check_all_ok"] = allv_ok
    res["strict_vs_production_invalid"] = {}
    for n in ("C", "E", "J"):
        prod_inv = {k: rep["systems"][n][k]["n_invalid"] for k in ("I", "AB", "BA")}
        mine_valid_reasons = res["label_coord_checks"][n]["invalid_reasons"]
        res["strict_vs_production_invalid"][n] = {"production_invalid": prod_inv, "strict_reasons_all_conditions": mine_valid_reasons}
        inval_ok &= (sum(v for k, v in mine_valid_reasons.items() if k != "ok") == sum(prod_inv.values()))
    res["invalid_counts_match"] = bool(inval_ok)
    coord_ok = all(v["nonfinite_or_nonpositive"] == 0 for v in res["label_coord_checks"].values())
    res["coord_checks_ok"] = bool(coord_ok)
    res["all_ok"] = bool(allv_ok and ok_ci and inval_ok and coord_ok)
    res["input_digests"] = {"report_sha256": sha_file(a.report), "per_patient_sha256": sha_file(a.report.replace(".json", "_per_patient.json")), "select_sha256": (sha_file(a.select) if os.path.exists(a.select) else None),
                            "manifest_sha256": sha_file(MAN), "verify_source_sha256": sha_file("pg48_verify.py"),
                            "raw_file_sha256": {f"{n}:{k}": {os.path.basename(fn): sha_file(fn) for fn in sorted(glob.glob(os.path.join(dd[k], "gen_worker*.jsonl")))} for n, dd in dirs.items() for k in ("I",)}}
    json.dump(res, open(a.out, "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("all_ok", "vector_check_all_ok", "ci_check", "invalid_counts_match", "coord_checks_ok")}, indent=1))
    sys.exit(0 if res["all_ok"] else 1)


if __name__ == "__main__":
    main()
