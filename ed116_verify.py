"""iter_116 독립 재계산 (ed116_eval/ed116_analyze를 import하지 않는다). 승인된 답 추출(ev109_extract.resolve)만 재사용하고,
선택·정답·정책·matching(열거)·공동 지표·bootstrap(index 생성 규약 동일)을 원시 record에서 다시 계산해 report.json과 대조한다.
사용: python ed116_verify.py --gen DIR --eval DIR --out FILE ('x' 모드)"""
import argparse
import glob
import hashlib
import itertools
import json
import sys

import numpy as np

import ev108_spec as S
import ev109_extract as X

PROV = "results/iter_116/provenance"
POL = ("K", "B", "G", "M", "N", "E", "R", "T", "S")
THR = 0.70


def iou(a, b):
    i = max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u > 0 else 0.0


def max_match(pred, gt, thr):
    for k in range(min(len(pred), len(gt)), 0, -1):
        for gi in itertools.combinations(range(len(gt)), k):
            for pi in itertools.permutations(range(len(pred)), k):
                if all(iou(pred[p], gt[g]) >= thr for g, p in zip(gi, pi)):
                    return k
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", required=True)
    ap.add_argument("--eval", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = dict((r["id"], r) for r in json.load(open(f"{PROV}/ledger_nogt.json"))["rows"])
    gt = json.load(open(f"{PROV}/gt.json"))
    rep = json.load(open(f"{a.eval}/report.json"))
    perp = json.load(open(f"{a.eval}/per_patient.json"))
    C = []

    def chk(name, ok, detail=None):
        C.append(dict(name=name, passed=bool(ok), detail=detail))

    # --- 선택 재계산 (독립)
    resolved, agree, mism = {}, [], []
    for i, r in rows.items():
        k = X.resolve("O", r["O"]["raw"], r["O"]["ended_eos"])["answer"]
        b = "yes" if any(s >= THR for s in r["det"]["scores"]) else "no"
        if k is None:
            continue
        resolved[i] = (k, b)
        (agree if k == b else mism).append(i)
    key = lambda i: hashlib.sha256(("iter116|" + rows[i]["patient"]).encode()).hexdigest()
    agree.sort(key=key)
    ctrl = agree[12:99]
    sel = json.load(open("results/iter_116/lock/selection.json"))
    chk("selection_mismatch_set", sorted(mism) == sorted(sel["mismatch"]) and len(mism) == 87)
    chk("selection_control_set", ctrl == sel["control"] and agree[:12] == sel["tech"])
    # --- record 읽기
    recs = {}
    for fn in sorted(glob.glob(f"{a.gen}/gen_worker*.jsonl")):
        for ln in open(fn):
            if ln.strip():
                r = json.loads(ln)
                recs[(r["patient"], r["cond"])] = r
    chk("record_count", len(recs) == 4 * (87 + 87), len(recs))
    ans = {}
    for (p, c), r in recs.items():
        ans.setdefault(p, {})[c] = X.resolve("O", r["suffix_text_raw"], r["ended_eos"])["answer"]
    # --- 정책
    def pol(i):
        k, b = resolved[i]
        st, _ = S.parse_saved_bbox(rows[i]["SFT"]["raw"], rows[i]["SFT"]["ended_eos"])
        g = {"ok": "yes", "empty": "no"}.get(st)
        e = ans[i]["E"]
        maj = k if g is None else ("yes" if [k, b, g].count("yes") >= 2 else "no")
        return dict(K=k, B=b, G=g, M=maj, N=ans[i]["N"], E=e, R=ans[i]["R"], T=ans[i]["T"], S=(e if (e is not None and e == b) else k))
    out = {}
    for gname, ids in (("mismatch", mism), ("control", ctrl)):
        ids = sorted(ids, key=key) if gname == "mismatch" else ids
        yv = {i: ("yes" if gt[i]["category"] == "opacity" else "no") for i in ids}
        P = {i: pol(i) for i in ids}
        n = len(ids)
        corr = {q: np.array([int(P[i][q] == yv[i]) for i in ids]) for q in POL}
        kc = corr["K"].astype(bool)
        g = {"n": n, "correct": {q: int(corr[q].sum()) for q in POL},
             "correction": {q: int(corr[q][~kc].sum()) for q in POL}, "harm": {q: int((1 - corr[q])[kc].sum()) for q in POL},
             "diff_R": {q: int(corr["R"].sum() - corr[q].sum()) for q in POL if q != "R"}}
        # 공동 지표 (R, K, S, N, E, T): 독립 matching
        def joint(q, thr):
            tot = 0
            for i in ids:
                top, left, side = rows[i]["pad"]
                dets = [b for s, b in sorted(((s, b) for s, b in zip(rows[i]["det"]["scores"], rows[i]["det"]["boxes_xyxy_px"]) if s >= THR),
                                             key=lambda t: (-t[0], t[1]))]
                pred = [[(b[1] + top) * 1000 / side, (b[0] + left) * 1000 / side, (b[3] + top) * 1000 / side, (b[2] + left) * 1000 / side] for b in dets]
                gb = gt[i]["gt_yxyx_norm"]
                a_ = P[i][q]
                if yv[i] == "yes":
                    tp = max_match(pred, gb, thr) if a_ == "yes" else 0
                    tot += int(a_ == "yes" and tp == len(gb) == len(pred))
                else:
                    tot += int(a_ == "no")
            return tot
        g["joint03"] = {q: joint(q, 0.3) for q in ("K", "N", "E", "R", "T", "S")}
        g["joint05"] = {q: joint(q, 0.5) for q in ("K", "R")}
        # bootstrap (동일 index 규약)
        idx = np.random.default_rng(11617).integers(0, n, size=(10000, n), dtype=np.int32)
        def ci(v):
            m = np.asarray(v, float)[idx].mean(axis=1)
            return [float(np.mean(v)), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]
        g["ci_diff_R"] = {q: ci(corr["R"] - corr[q]) for q in ("K", "S", "N", "E", "T", "M", "B", "G")}
        out[gname] = g
    # --- report와 대조
    for gname, key_ in (("mismatch", "mismatch"), ("control", "control")):
        g, r = out[gname], rep[key_]
        chk(f"{gname}_n", g["n"] == r["n"])
        chk(f"{gname}_correct_counts", all(g["correct"][q] == r["point"][f"correct_{q}"] for q in POL), g["correct"])
        chk(f"{gname}_correction_harm", all(g["correction"][q] == r["point"][f"correction_{q}"] and g["harm"][q] == r["point"][f"harm_{q}"] for q in POL))
        chk(f"{gname}_diff_R", all(g["diff_R"][q] == r["point"][f"diff_R_{q}"] for q in g["diff_R"]))
        chk(f"{gname}_joint03", all(g["joint03"][q] == r["point"][f"joint03_{q}"] for q in g["joint03"]), g["joint03"])
        chk(f"{gname}_joint05", all(g["joint05"][q] == r["point"][f"joint05_{q}"] for q in g["joint05"]))
        chk(f"{gname}_ci_diff_R", all(max(abs(x - y) for x, y in zip(g["ci_diff_R"][q], r["ci95"][f"diff_R_{q}"])) < 1e-12 for q in g["ci_diff_R"]))
    # per_patient 표 대조
    pp = dict((r["id"], r) for r in perp)
    chk("per_patient_answers", all(pp[i]["answers"] == pol(i) for i in pp))
    chk("per_patient_raw_matches_records", all(pp[i]["raw"][c] == recs[(i, c)]["suffix_text_raw"] for i in pp for c in "NERT"))
    chk("n_unresolved_cells", True, {q: sum(1 for i in pp if pp[i]["answers"][q] is None) for q in "GNERT"})
    json.dump(dict(n=len(C), n_pass=sum(c["passed"] for c in C), checks=C, independent=out), open(a.out, "x"), indent=1)
    print(sum(c["passed"] for c in C), "/", len(C))
    sys.exit(0 if all(c["passed"] for c in C) else 1)


if __name__ == "__main__":
    main()
