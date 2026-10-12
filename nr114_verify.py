"""iter_114 독립 재계산 (nr114_core / nr113_core / nr107_* 를 import 하지 않는다).
원시 MG(A, MSPC)·CURE 출력 JSONL 과 items.json 에서 다시 계산해 result_<stage>/ 와 대조한다. union 면적은 포함-배제(inclusion-exclusion),
위험 값은 반올림 없이 원 float 로 비교(순위·동률 규칙 동일), 부트스트랩은 같은 절차를 독립 구현.
사용: python nr114_verify.py <init|final>   → analysis/verify_<stage>.json
"""
import hashlib
import itertools
import json
import math
import random
import re
import sys
from pathlib import Path

R = Path("results/iter_114")
AN = R / "analysis_r1"


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def ie_union(boxes):
    tot = 0.0
    for r in range(1, len(boxes) + 1):
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


def good_box(b):
    return len(b) == 4 and all(isinstance(v, (int, float)) and math.isfinite(v) for v in b) and 0 <= b[0] < b[2] <= 1 and 0 <= b[1] < b[3] <= 1


def kk(n):
    return (n + 3) // 4


def tkey(k, rep=0):
    return (hashlib.sha256(("iter113|" + k).encode()).hexdigest(), rep)


def topk(ents, f):
    K = kk(len(ents))
    idx = sorted(range(len(ents)), key=lambda i: (-ents[i][f], ents[i]["tk"]))
    return set(idx[:K])


def caps(ents):
    s = {f: topk(ents, f) for f in ("B", "D", "P")}
    return {f: sum(ents[i]["e"] for i in s[f]) for f in s}, s


def tie_sets(ents, f):
    K = kk(len(ents))
    vals = sorted((e[f] for e in ents), reverse=True)
    rk = vals[K - 1]
    forced = [i for i, e in enumerate(ents) if e[f] > rk]
    tied = [i for i, e in enumerate(ents) if e[f] == rk]
    need = K - len(forced)
    return [set(forced) | set(c) for c in itertools.combinations(tied, need)]


def read_jsonl_dir(d, pat):
    rows = []
    for p in sorted(Path(d).glob(pat)):
        for ln in open(p):
            if ln.strip():
                rows.append(json.loads(ln))
    return rows


def pctl(v, q):
    s = sorted(v)
    pos = q / 100 * (len(s) - 1)
    lo = int(math.floor(pos)); fr = pos - lo
    return s[lo] + (s[min(lo + 1, len(s) - 1)] - s[lo]) * fr


def main(stage):
    names = ["INIT"] if stage == "init" else ["INIT", "EXPAND"]
    items_all = json.load(open(R / "data/items.json"))
    ents, ex = [], []
    for nm in names:
        runs = json.load(open(AN / f"runs_{'init' if nm == 'INIT' else 'expand'}.json"))
        want = "init" if nm == "INIT" else "expand"
        items = [it for it in items_all if it["stage"] == want]
        A = {r["item_key"]: r for r in read_jsonl_dir(runs["A"], "raw_worker*.jsonl")}
        P = {r["item_key"]: r for r in read_jsonl_dir(runs["MSPC"], "raw_worker*.jsonl")}
        CR = {r["id"]: r for r in read_jsonl_dir(Path(runs["CURE"]) / "cure", "shard*/outputs.jsonl")}
        assert len(A) == len(P) == len(items) == len(CR), (len(A), len(P), len(items), len(CR))
        for it in items:
            a, p = A[it["item_key"]]["detection"], P[it["item_key"]]["detection"]
            c = CR[f"{it['ImageID']}|CURE|pg-f{it['finding_index']}"]
            att = c["attempts"][-1]
            C, st = parse_cure(c["text"], bool(att["ended_eos"]) and att["finish_reason"] == "eos")
            tech = (len(a["boxes_orig_xyxy"]) != len(a["scores"]) or len(p["boxes_orig_xyxy"]) != len(p["scores"])
                    or not all(good_box(b) for b in a["boxes_orig_xyxy"] + p["boxes_orig_xyxy"]) or any(s < 0.8 or not math.isfinite(s) for s in a["scores"] + p["scores"]))
            if C is None or tech:
                ex.append((it["item_key"], st if C is None else "technical"))
                continue
            M, sc, Pb = a["boxes_orig_xyxy"], a["scores"], p["boxes_orig_xyxy"]
            G, H = it["gt"], it["extra"]
            def drisk(X, Y):
                if not X and not Y: return 0.0
                if not X or not Y: return 1.0
                return 1.0 - uiou(X, Y)
            Bk = 1.0 if not sc else 1.0 - min(sc)
            eg = 1 if (not M or uiou(M, G) < 0.3) else 0
            eh = None if not H else (1 if (not M or uiou(M, H) < 0.3) else 0)
            ents.append({"key": it["item_key"], "patient": it["PatientID"], "tk": tkey(it["item_key"]), "D": drisk(M, C), "P": drisk(M, Pb), "B": Bk, "e": eg, "eh": eh})
    rep = json.load(open(AN / f"result_{stage}/report.json"))
    pi = {r["item_key"]: r for r in json.load(open(AN / f"result_{stage}/per_item.json"))}
    saved_boot = json.load(open(AN / f"result_{stage}/bootstrap.json"))
    chk = {}
    N = len(ents); K = kk(N)
    c, sel = caps(ents)
    chk["N_K"] = (N, K) == (rep["N"], rep["K"])
    chk["n_errors"] = sum(e["e"] for e in ents) == rep["n_errors_official"]
    chk["captures"] = (c["D"], c["P"], c["B"]) == (rep["capture"]["cure"], rep["capture"]["mspc"], rep["capture"]["confidence"])
    chk["dA_dB_counts"] = (c["D"] - c["B"], c["D"] - c["P"]) == (rep["dA_count"], rep["dB_count"])
    chk["selected_ids"] = all(sorted(ents[i]["key"] for i in sel[f]) == sorted(rep["selected"][nm]) for f, nm in (("D", "cure"), ("P", "mspc"), ("B", "confidence")))
    chk["excluded"] = sorted(k for k, _ in ex) == sorted(x["item_key"] for x in rep["excluded_from_ranking"])
    # production 의 원 float 위험 값과 독립 값이 같은 순위를 내는지 (반올림 없이)
    tol = max((abs(pi[e["key"]][f] - e[f]) for e in ents for f in ("D", "P", "B")), default=0.0)
    chk["risk_values_match_1e-12"] = tol < 1e-12
    prod_ent = [{"key": k, "D": pi[k]["D"], "P": pi[k]["P"], "B": pi[k]["B"], "e": pi[k]["e"], "tk": tkey(k)} for k in (e["key"] for e in ents)]
    c2, sel2 = caps(prod_ent)
    chk["rank_same_with_production_raw_floats"] = all({prod_ent[i]["key"] for i in sel2[f]} == {ents[i]["key"] for i in sel[f]} for f in sel)
    # 보수적 범위 (전수)
    def st(e):
        if e["eh"] is None: return "undetermined_no_alt"
        return "confirmed_error" if e["e"] == 1 and e["eh"] == 1 else "confirmed_ok" if e["e"] == 0 and e["eh"] == 0 else "undetermined_disagree"
    unds = [i for i, e in enumerate(ents) if st(e).startswith("undetermined")]
    cnt = {}
    for e in ents: cnt[st(e)] = cnt.get(st(e), 0) + 1
    chk["annot_counts"] = all(cnt.get(k, 0) == v for k, v in rep["annotation_status_counts"].items())
    skipped = []
    def brute(fx, fy, tie):
        sxl = tie_sets(ents, fx) if tie else [topk(ents, fx)]
        syl = tie_sets(ents, fy) if tie else [topk(ents, fy)]
        if len(sxl) * len(syl) > 3_000_000:
            skipped.append((fx, fy, tie)); return None
        lo, hi = 10 ** 9, -10 ** 9
        det = [i for i in range(N) if i not in unds]
        for sx in sxl:
            for sy in syl:
                base = sum(ents[i]["e"] * ((i in sx) - (i in sy)) for i in det)
                lo = min(lo, base + sum(min(0, (i in sx) - (i in sy)) for i in unds))
                hi = max(hi, base + sum(max(0, (i in sx) - (i in sy)) for i in unds))
        return [lo, hi]
    for which, fy in (("A", "B"), ("B", "P")):
        b = rep["bounds_" + which]
        r1, r2, r3 = brute("D", fy, True), brute("D", fy, False), None
        # tie_only: e 고정(미확정도 원 e), annot 자유 없음
        sxl, syl = tie_sets(ents, "D"), tie_sets(ents, fy)
        if len(sxl) * len(syl) <= 3_000_000:
            vals = [sum(ents[i]["e"] * ((i in sx) - (i in sy)) for i in range(N)) for sx in sxl for sy in syl]
            chk[f"bounds_{which}_tie_only"] = [min(vals), max(vals)] == list(b["tie_only"])
        chk[f"bounds_{which}_tie_and_annot"] = r1 is not None and r1 == list(b["tie_and_annot"])
        chk[f"bounds_{which}_annot_only"] = r2 is not None and r2 == list(b["annot_only"])
    # bootstrap (동일 절차)
    pats = sorted({e["patient"] for e in ents})
    by = {p: [e for e in ents if e["patient"] == p] for p in pats}
    rng = random.Random(113)
    boot = []
    for _ in range(20000):
        rr = []
        for j in range(len(pats)):
            for e in by[pats[rng.randrange(len(pats))]]:
                rr.append({**e, "tk": (e["tk"][0], j)})
        cc, _s = caps(rr)
        boot.append([cc["D"] - cc["B"], cc["D"] - cc["P"], len(rr)])
    chk["bootstrap_identical"] = boot == saved_boot
    for name, idx in (("A", 0), ("B", 1)):
        v = [x[idx] / x[2] for x in boot]
        lo, hi = pctl(v, 0.625), pctl(v, 99.375)
        sv = rep["bootstrap"][name]["ci_9875"]
        chk[f"ci_9875_{name}"] = abs(lo - sv[0]) < 1e-12 and abs(hi - sv[1]) < 1e-12
    # LOO
    loo = {"A": [], "B": []}
    for p in pats:
        sub = [e for e in ents if e["patient"] != p]
        cc, _s = caps(sub)
        loo["A"].append(cc["D"] - cc["B"]); loo["B"].append(cc["D"] - cc["P"])
    chk["loo"] = all((min(loo[w]), max(loo[w]), sum(x < 0 for x in loo[w])) == (rep["leave_one_patient_out"][w]["min"], rep["leave_one_patient_out"][w]["max"], rep["leave_one_patient_out"][w]["n_negative"]) for w in "AB")
    # complementarity
    for w, (a, b) in (("A", ("D", "B")), ("B", ("D", "P"))):
        cmp_ = rep["complementarity_" + w]
        ao = [i for i in sel[a] if i not in sel[b] and ents[i]["e"]]; bo = [i for i in sel[b] if i not in sel[a] and ents[i]["e"]]
        bt = [i for i in sel[a] if i in sel[b] and ents[i]["e"]]
        chk[f"comp_{w}"] = (len(ao), len(bo), len(bt)) == (len(cmp_["a_only_errors"]), len(cmp_["b_only_errors"]), len(cmp_["both_errors"])) and \
            (len({ents[i]["patient"] for i in ao}), len({ents[i]["patient"] for i in bo})) == (cmp_["a_only_error_patients"], cmp_["b_only_error_patients"])
    files = {f"result_{stage}/{f}": sha_file(AN / f"result_{stage}" / f) for f in ("report.json", "per_item.json", "bootstrap.json", "state.json")}
    files[f"ledger_{stage}.json"] = sha_file(AN / f"ledger_{stage}.json")
    files[f"stage_lock_{stage}.json"] = sha_file(AN / f"stage_lock_{stage}.json")
    res = {"checks": chk, "all_pass": all(chk.values()), "stage": stage, "n_ranked": N, "n_excluded": len(ex), "brute_force_skipped": skipped,
           "n_undetermined": len(unds), "max_risk_abs_diff_vs_production": tol, "verified_files": files,
           "independent_of": ["nr114_core", "nr113_core", "nr107_geom", "nr107_spec"]}
    out = AN / f"verify_{stage}.json"
    if out.exists():
        raise SystemExit(f"{out} exists")
    out.write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "verified_files"}, indent=1))
    sys.exit(0 if res["all_pass"] else 1)


if __name__ == "__main__":
    main(sys.argv[1])
