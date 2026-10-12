"""iter_113 독립 재계산(nr113_core / nr107_* 를 import 하지 않는다). 원시 CURE·MG 출력과 원 manifest 에서 다시 계산해
report.json 과 대조한다. union 면적은 포함-배제(inclusion-exclusion)로 계산한다."""
import hashlib
import itertools
import json
import math
import random
import re
import sys
from pathlib import Path

R = Path("results")
OUT = Path("results/iter_113")


def ie_union(boxes):
    n = len(boxes)
    tot = 0.0
    for r in range(1, n + 1):
        for sub in itertools.combinations(boxes, r):
            x0 = max(b[0] for b in sub); y0 = max(b[1] for b in sub)
            x1 = min(b[2] for b in sub); y1 = min(b[3] for b in sub)
            if x1 > x0 and y1 > y0:
                tot += (-1) ** (r + 1) * (x1 - x0) * (y1 - y0)
    return tot


def uiou(A, B):
    if not A or not B:
        return 0.0
    ua, ub = ie_union(A), ie_union(B)
    inter = ua + ub - ie_union(A + B)
    return inter / (ua + ub - inter)


def parse_cure(text, eos):
    if not eos:
        return None, "truncated"
    groups = re.findall(r"\[([^\[\]]*)\]", text)
    rest = re.sub(r"\[[^\[\]]*\]", "", text)
    if "[" in rest or "]" in rest:
        return None, "malformed"
    out = []
    for g in groups:
        parts = [p.strip() for p in g.split(",")]
        if len(parts) != 4:
            return None, "malformed"
        try:
            c = [float(p) for p in parts]
        except ValueError:
            return None, "malformed"
        if not all(math.isfinite(v) for v in c):
            return None, "coord_invalid"
        if c[2] <= 0 or c[3] <= 0 or any(v < 0 or v > 1 for v in c):
            return None, "coord_invalid"
        xy = [c[0] - c[2] / 2, c[1] - c[3] / 2, c[0] + c[2] / 2, c[1] + c[3] / 2]
        if xy[0] < 0 or xy[1] < 0 or xy[2] > 1 or xy[3] > 1:
            return None, "coord_invalid"
        out.append(xy)
    return out, ("valid_nonempty" if out else "no_box")


def kk(n):
    return (n + 3) // 4


def tkey(k, rep=0):
    return (hashlib.sha256(("iter113|" + k).encode()).hexdigest(), rep)


def topk(ents, f):
    K = kk(len(ents))
    idx = sorted(range(len(ents)), key=lambda i: (-ents[i][f], ents[i]["tk"]))
    return set(idx[:K])


def diff_of(ents):
    sd, sb = topk(ents, "D"), topk(ents, "B")
    return sum(ents[i]["e"] for i in sd) - sum(ents[i]["e"] for i in sb), sd, sb


def tie_sets(ents, f):
    """경계 동률이 있는 순위에서 가능한 모든 선택 집합(전수)."""
    K = kk(len(ents))
    vals = sorted((e[f] for e in ents), reverse=True)
    rk = vals[K - 1]
    forced = [i for i, e in enumerate(ents) if e[f] > rk]
    tied = [i for i, e in enumerate(ents) if e[f] == rk]
    need = K - len(forced)
    return [set(forced) | set(c) for c in itertools.combinations(tied, need)]


def main():
    items = json.load(open(R / "iter_107/data/items.json"))
    cure = {}
    for sh in (0, 1):
        for ln in open(R / f"iter_107/gen/M47/cure/shard{sh}/outputs.jsonl"):
            r = json.loads(ln)
            cure[r["id"]] = r
    mg = {}
    for w in (0, 1):
        for ln in open(R / f"iter_046/mg/V96_A_w2b4/raw_worker{w}.jsonl"):
            r = json.loads(ln)
            mg[r["request_id"]] = r
    man = {}
    for ln in open(R / "iter_039/data/manifest_private.jsonl"):
        r = json.loads(ln)
        for t in r["sentences"]:
            man[(r["ImageID"], r["PatientID"], t)] = (r, t)
    ents, ex = [], []
    for it in items:
        c = cure[f"{it['ImageID']}|CURE|pg-f{it['finding_index']}"]
        att = c["attempts"][-1]
        C, st = parse_cure(c["text"], bool(att["ended_eos"]) and att["finish_reason"] == "eos")
        if C is None:
            ex.append((it["item_key"], st)); continue
        det = mg[it["mg_request_id"]]["detections"]["0.8"]
        M, sc = det["boxes_orig_xyxy"], det["scores"]
        row, t = man[(it["ImageID"], it["PatientID"], it["target"])]
        G = row["gt_boxes_xyxy_norm"][t]; H = row["extra_boxes_xyxy_norm"][t]
        assert len(M) == len(sc)
        if not M and not C: D = 0.0
        elif not M or not C: D = 1.0
        else: D = 1.0 - uiou(M, C)
        B = 1.0 if not sc else 1.0 - min(sc)
        eg = 1 if (not M or uiou(M, G) < 0.3) else 0
        eh = None if not H else (1 if (not M or uiou(M, H) < 0.3) else 0)
        ents.append({"key": it["item_key"], "patient": it["PatientID"], "tk": tkey(it["item_key"]), "D": round(D, 12), "B": round(B, 12), "e": eg, "eh": eh})
    rep = json.load(open(OUT / "report.json"))
    chk = {}
    N = len(ents); K = kk(N)
    d, sd, sb = diff_of(ents)
    chk["N"] = N == rep["N"]; chk["K"] = K == rep["K"]
    chk["n_errors"] = sum(e["e"] for e in ents) == rep["n_errors_official"]
    chk["capture_D"] = sum(ents[i]["e"] for i in sd) == rep["capture_D"]
    chk["capture_B"] = sum(ents[i]["e"] for i in sb) == rep["capture_B"]
    chk["diff"] = d == rep["diff"]
    chk["selected_D_ids"] = sorted(ents[i]["key"] for i in sd) == sorted(rep["selected_D"])
    chk["selected_B_ids"] = sorted(ents[i]["key"] for i in sb) == sorted(rep["selected_B"])
    chk["excluded"] = sorted(k for k, _ in ex) == sorted(x["item_key"] for x in rep["excluded_from_ranking"])
    # annotation status
    def st(e):
        if e["eh"] is None: return "undetermined_no_alt"
        return "confirmed_error" if e["e"] == 1 and e["eh"] == 1 else "confirmed_ok" if e["e"] == 0 and e["eh"] == 0 else "undetermined_disagree"
    cnt = {}
    for e in ents: cnt[st(e)] = cnt.get(st(e), 0) + 1
    chk["annot_counts"] = all(cnt.get(k, 0) == v for k, v in rep["annotation_status_counts"].items())
    # 상보성
    dn = [i for i in sd if i not in sb and ents[i]["e"]]; bn = [i for i in sb if i not in sd and ents[i]["e"]]
    bt = [i for i in sd if i in sb and ents[i]["e"]]; nn = [i for i in range(N) if i not in sd and i not in sb and ents[i]["e"]]
    cp = rep["complementarity"]
    chk["comp_counts"] = (len(dn), len(bn), len(bt), len(nn)) == (len(cp["D_only_errors"]), len(cp["B_only_errors"]), len(cp["both_errors"]), len(cp["neither_errors"]))
    chk["comp_patients"] = (len({ents[i]["patient"] for i in dn}), len({ents[i]["patient"] for i in bn})) == (cp["D_only_error_patients"], cp["B_only_error_patients"])
    # 동률·주석 범위 전수
    Ds, Bs = tie_sets(ents, "D"), tie_sets(ents, "B")
    cd = [sum(ents[i]["e"] for i in s) for s in Ds]; cb = [sum(ents[i]["e"] for i in s) for s in Bs]
    chk["tie_capture_ranges"] = [min(cd), max(cd)] == list(rep["bounds"]["D_capture_tie_range"]) and [min(cb), max(cb)] == list(rep["bounds"]["B_capture_tie_range"])
    chk["tie_only_diff_range"] = [min(cd) - max(cb), max(cd) - min(cb)] == list(rep["bounds"]["tie_only"])
    unds = [i for i, e in enumerate(ents) if st(e).startswith("undetermined")]
    def brute(selD_list, selB_list):
        lo, hi = 10 ** 9, -10 ** 9
        if len(unds) > 22:
            return None
        for sD in selD_list:
            for sB in selB_list:
                base = sum(ents[i]["e"] * ((i in sD) - (i in sB)) for i in range(N) if i not in unds)
                gain_min = sum(min(0, (i in sD) - (i in sB)) for i in unds)
                gain_max = sum(max(0, (i in sD) - (i in sB)) for i in unds)
                lo = min(lo, base + gain_min); hi = max(hi, base + gain_max)
        return [lo, hi]
    a = brute([sd], [sb]); b = brute(Ds, Bs)
    chk["annot_only_range"] = a is not None and a == list(rep["bounds"]["annot_only"])
    chk["tie_and_annot_range"] = b is not None and b == list(rep["bounds"]["tie_and_annot"])
    # bootstrap (동일 절차 독립 구현)
    pats = sorted({e["patient"] for e in ents})
    by = {p: [e for e in ents if e["patient"] == p] for p in pats}
    rng = random.Random(113)
    diffs = []
    for _ in range(10000):
        rr = []
        for j in range(len(pats)):
            for e in by[pats[rng.randrange(len(pats))]]:
                rr.append({**e, "tk": (e["tk"][0], j)})
        diffs.append(diff_of(rr)[0])
    saved = json.load(open(OUT / "bootstrap_diffs.json"))
    chk["bootstrap_diffs_identical"] = diffs == saved
    s = sorted(diffs)
    def pct(q):
        pos = q * (len(s) - 1); lo = int(math.floor(pos)); fr = pos - lo
        return s[lo] + (s[min(lo + 1, len(s) - 1)] - s[lo]) * fr
    chk["bootstrap_ci"] = abs(pct(.025) - rep["bootstrap"]["ci95"][0]) < 1e-9 and abs(pct(.975) - rep["bootstrap"]["ci95"][1]) < 1e-9
    # LOO
    loo = []
    for p in pats:
        sub = [e for e in ents if e["patient"] != p]
        loo.append(diff_of(sub)[0])
    chk["loo"] = (min(loo), max(loo), sum(1 for x in loo if x < 0)) == (rep["leave_one_patient_out"]["min"], rep["leave_one_patient_out"]["max"], rep["leave_one_patient_out"]["n_negative"])
    res = {"checks": chk, "all_pass": all(chk.values()), "n_items": len(items), "n_ranked": N, "brute_force_undetermined": len(unds),
           "tie_set_sizes": [len(Ds), len(Bs)], "independent_of": ["nr113_core", "nr107_geom", "nr107_spec"]}
    p = OUT / "verify.json"
    if p.exists():
        raise SystemExit("verify.json exists")
    p.write_text(json.dumps(res, indent=1))
    print(json.dumps(res))
    sys.exit(0 if res["all_pass"] else 1)


if __name__ == "__main__":
    main()
