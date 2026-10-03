"""iter_054 독립 검증기: raw gen_worker*.jsonl과 eval_manifest만으로 지표를 별도 구현(mc54_eval/mc54_spec 의 parser·집계 미사용)으로 재계산해
report.json과 대조한다. bootstrap은 같은 seed(RandomState 54)의 (R,K) 한 번 draw + 명시적 pair 재구성 방식으로 계산한다.
결과: verify.json (report sha 연결). 사용: python mc54_verify.py <report.json> <verify.json>"""
import glob
import hashlib
import json
import re
import sys

import numpy as np

MAIN = "results/iter_054/raw/main"
PARENT = "results/iter_054/raw/tech_ref_w2"
EVM = "results/iter_054/data/eval_manifest.json"
BASE = ["MC_orig", "MC_swap", "GD_orig", "GD_swap", "GD_avg", "GD_cal", "PS", "PS_cal"]


def sha_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def letter_strict(raw, eos):
    if not eos:
        return "-"
    t = raw
    for tok in ("<end_of_turn>", "<eos>", "<pad>"):
        t = t.replace(tok, "")
    t = t.strip()
    m = re.fullmatch(r"(?:\*\*)?\(?\s*([AB])\s*\)?(?:\*\*)?\s*[.:)]?", t)
    return m.group(1) if m else "-"


def canon_letter(x, order):
    if x not in "AB" or x == "-":
        return x
    return x if order == "orig" else ("B" if x == "A" else "A")


def sgn(x):
    return "A" if x > 0 else ("B" if x < 0 else "-")


def load_raw():
    recs = {}
    for d in (MAIN, PARENT):
        for fn in sorted(glob.glob(d + "/gen_worker*.jsonl")):
            for line in open(fn).read().split("\n")[:-1]:
                if line.strip():
                    r = json.loads(line)
                    assert r["request_id"] not in recs
                    recs[r["request_id"]] = r
    return recs


def main(rep_path, out_path):
    rep = json.load(open(rep_path))
    ev = json.load(open(EVM))
    recs = load_raw()
    got = {}
    for rid, m in ev["requests"].items():
        if rid in recs:
            got.setdefault(m["pair"], []).append((m, recs[rid]))
    avail = sorted(p for p, m in ev["pairs"].items() if m["available"])
    checks = []

    def chk(name, ok, **kw):
        checks.append({"name": name, "pass": bool(ok), **kw})
        print("PASS" if ok else "FAIL", name, kw, flush=True)
    chk("all_available_pairs_have_18_records", all(len(got.get(p, [])) == 18 for p in avail) and set(got) == set(avail), n_pairs=len(got))
    chk("raw_record_count_equals_requests_of_available_pairs", len(recs) == 18 * len(avail), n=len(recs))
    # 시스템별 pair 결과
    S_ = {n: [] for n in BASE}
    IND = {"GD_avg": [], "T_GD_avg": []}
    O = []
    comp = []
    orient_cal_equal = True
    near = {}
    for p in avail:
        rows = got[p]
        t = (ev["pairs"][p]["im1_correct"], ev["pairs"][p]["im2_correct"])
        mc, gd, ps = {}, {}, {}
        for m, r in rows:
            if m["kind"] == "mc":
                mc[(m["slot"], m["order"])] = canon_letter(letter_strict(r["payload"]["suffix_text_raw"], r["payload"]["ended_eos"]), m["order"])
            elif m["kind"] == "gd":
                v = r["payload"]["logit_A"] - r["payload"]["logit_B"]
                gd[(m["slot"], m["order"])] = v if m["order"] == "orig" else -v
            else:
                ps[(m["slot"], m["option"])] = float(np.mean(r["payload"]["token_logps"]))
        sl = ("im1", "im2")

        def setok(ans):
            return int(ans[0] == t[0] and ans[1] == t[1])
        S_["MC_orig"].append(setok([mc[(s, "orig")] for s in sl]))
        S_["MC_swap"].append(setok([mc[(s, "swap")] for s in sl]))
        S_["GD_orig"].append(setok([sgn(gd[(s, "orig")]) for s in sl]))
        S_["GD_swap"].append(setok([sgn(gd[(s, "swap")]) for s in sl]))
        avg = [(gd[(s, "orig")] + gd[(s, "swap")]) / 2 for s in sl]
        tavg = (gd[("text", "orig")] + gd[("text", "swap")]) / 2
        S_["GD_avg"].append(setok([sgn(x) for x in avg]))
        S_["GD_cal"].append(setok([sgn(x - tavg) for x in avg]))
        d = [ps[(s, "A")] - ps[(s, "B")] for s in sl]
        dt = ps[("text", "A")] - ps[("text", "B")]
        S_["PS"].append(setok([sgn(x) for x in d]))
        S_["PS_cal"].append(setok([sgn(x - dt) for x in d]))
        IND["GD_avg"].append(sum(sgn(avg[i]) == t[i] for i in range(2)) / 2)
        IND["T_GD_avg"].append(sum(sgn(tavg) == t[i] for i in range(2)) / 2)
        ia = 0 if t[0] == "A" else 1
        O.append(1.0 if avg[ia] > avg[1 - ia] else (0.0 if avg[ia] < avg[1 - ia] else 0.5))
        comp.append(ev["pairs"][p]["component"])
    N = len(avail)
    pt_S = {n: float(np.mean(S_[n])) for n in BASE}
    pt_O = float(np.mean(O))
    pt_G = pt_O - max(pt_S.values())
    pt_acc = float(np.mean(IND["GD_avg"]) - np.mean(IND["T_GD_avg"]))
    r_pt = rep["point"]
    tol = 1e-9
    chk("point_estimates_match_report", all(abs(pt_S[n] - r_pt[f"S:{n}"]) < tol for n in BASE) and abs(pt_O - r_pt["O"]) < tol
        and abs(pt_G - r_pt["G"]) < tol and abs(pt_acc - r_pt["ACC_gd_minus_text"]) < tol,
        O=pt_O, G=pt_G, S=pt_S, ACC=pt_acc)
    # 지표 대조 (individual/set/invalid)
    summ = rep["systems"]
    chk("system_set_acc_match_report", all(abs(summ[n]["set_acc"] - pt_S[n]) < tol for n in BASE))
    # bootstrap (독립 구현)
    comp = np.array(comp)
    cids = sorted(set(comp.tolist()))
    K = len(cids)
    members = [np.where(comp == c)[0] for c in cids]
    arr = {f"S:{n}": np.array(S_[n], float) for n in BASE}
    arr["O"] = np.array(O)
    arr["ACC"] = np.array(IND["GD_avg"]) - np.array(IND["T_GD_avg"])
    rs = np.random.RandomState(54)
    draws = rs.randint(0, K, size=(10000, K))
    Gs, Os, Ds, Accs = [], [], {n: [] for n in BASE}, []
    for row in draws:
        idx = np.concatenate([members[k] for k in row])
        s = {n: arr[f"S:{n}"][idx].mean() for n in BASE}
        o = arr["O"][idx].mean()
        Os.append(o)
        Gs.append(o - max(s.values()))
        Accs.append(arr["ACC"][idx].mean())
        for n in BASE:
            Ds[n].append(s[n] - s["MC_orig"])
    pc = lambda a: [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))]
    b = rep["bootstrap_cluster"]
    cmp_ = {"O": (pc(Os), b["O"]["ci95"]), "G": (pc(Gs), b["G"]["ci95"]), "ACC": (pc(Accs), b["ACC_gd_minus_text"]["ci95"])}
    for n in BASE:
        cmp_[f"dS:{n}"] = (pc(Ds[n]), b[f"dS:{n}"]["ci95"])
    worst = max(max(abs(x - y) for x, y in zip(a, c)) for a, c in cmp_.values())
    chk("bootstrap_ci_match_report", worst < 1e-9, max_abs_diff=worst, n_rep=10000, n_units=K)
    # 완료 검증 외 raw 연결: record digest 재계산
    bad = 0
    for r in recs.values():
        rr = {k: v for k, v in r.items() if k != "record_digest"}
        h = hashlib.sha256(json.dumps(rr, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
        bad += h != r["record_digest"]
    chk("record_digests_recomputed", bad == 0, n_bad=bad)
    # raw provenance digest가 report와 연결
    prov = rep["provenance"]
    chk("report_provenance_matches_files", prov["completion_sha256"] == sha_file(MAIN + "/completion.json") and
        prov["eval_manifest_sha256"] == sha_file(EVM), completion=prov["completion_sha256"][:12])
    chk("report_eval_code_hashes_current", all(sha_file(f) == h for f, h in prov["eval_code"].items()), files=list(prov["eval_code"]))
    out = {"checks": checks, "all_pass": all(c["pass"] for c in checks), "report_path": rep_path, "report_sha256": sha_file(rep_path),
           "verifier_sha256": sha_file(__file__)}
    json.dump(out, open(out_path, "x"), indent=1)
    print("all_pass", out["all_pass"])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
