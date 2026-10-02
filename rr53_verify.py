"""iter_053 독립 검증기. production(rr53_eval/rr47_eval/rr53_spec의 parser·점수·bootstrap)을 호출하지 않고 원시 record·요청·manifest·labels에서
다시 계산해 저장 report와 대조한다. 모든 조건·지표·diff·동시 보정 구간·공통 valid·oracle·valid율을 검사하고, 불일치 항목을 제외한 PASS를 만들지 않는다.

python rr53_verify.py --stage D|E|F --out-dir D --protocol P --report REPORT --out verify.json
(completion·요청 집합·hash 연결은 rr53_run.verify가 담당한다 — 점수 계산이 아니다.)
"""
import argparse
import hashlib
import json
import os
import re
import sys

import numpy as np

import rr53_run
from rr53_data import OUT

ANS = {"present", "absent", "uncertain"}
DRAFTS = ["00", "01", "10", "11"]
IDS = ("qA", "qB")
SIMULT_LEVEL = 1 - 0.05 / 8


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def parse_raw(raw, eos, keys):
    """독립 parser: 상태 dict 또는 None(invalid)."""
    if not eos:
        return None
    t = raw
    if t.endswith("<end_of_turn>"):
        t = t[: -len("<end_of_turn>")]
    if "<unused94>" in t or "<unused95>" in t:
        i, j = t.find("<unused94>"), t.find("<unused95>")
        if not (t.lstrip().startswith("<unused94>") and t.count("<unused94>") == 1 and t.count("<unused95>") == 1 and i < j):
            return None
        t = t[j + len("<unused95>"):]
    t = t.strip()
    m = re.fullmatch(r"```(?:json|JSON)?[ \t]*\n(.*?)\n?```", t, flags=re.S)
    if m:
        t = m.group(1).strip()
    if "`" in t or not t.startswith("{") or not t.endswith("}"):
        return None
    pairs = []
    try:
        obj = json.loads(t, object_pairs_hook=lambda p: (pairs.extend(p), dict(p))[1])
    except ValueError:
        return None
    if len([k for k, _ in pairs]) != len({k for k, _ in pairs}):
        return None
    if not isinstance(obj, dict) or set(obj) != set(keys) or len(obj) != len(keys):
        return None
    if any((not isinstance(v, str)) or v not in ANS for v in obj.values()):
        return None
    return obj


def bits(code):
    return ["present" if ch == "1" else "absent" for ch in code]


def final_of(parsed, pid, cond, d, i, ds_k):
    """(상태, valid). K는 초안 그대로."""
    if cond == "K":
        return ds_k, True
    key = {"R1": f"R1_d{d}", "R2": f"R2_d{d}", "T": f"T_d{d}", "BJ": "BJ", "BT": "BT", "BI": f"BI_{i}"}[cond]
    p = parsed[(pid, key)]
    return (p[i] if p else "invalid"), p is not None


def per_patient(manifest, parsed):
    out = {}
    for m in manifest["rows"]:
        pid = m["PatientID"]
        truth = [m["q"][i]["state"] for i in IDS]
        res, sts = {}, {}
        for cond in ["K", "R1", "R2", "T", "BJ", "BT", "BI"]:
            fixed = harmed = hfail = corr = 0
            clean = False
            allok = True
            seq = [[], []]
            ss = []
            for d in DRAFTS:
                ds = bits(d)
                fin = []
                for k, i in enumerate(IDS):
                    v, ok = final_of(parsed, pid, cond, d, i, ds[k])
                    fin.append(v)
                    seq[k].append(v)
                    corr += v == truth[k]
                    wrong = ds[k] != truth[k]
                    if wrong:
                        fixed += v == truth[k]
                    else:
                        harmed += v == ("absent" if truth[k] == "present" else "present")
                        hfail += v != truth[k]
                    ss.append((d, i, wrong, v == truth[k], ok))
                both = all(fin[k] == truth[k] for k in range(2))
                allok = allok and both
                if ds == truth:
                    clean = both
            res[cond] = dict(r=fixed / 4, h=harmed / 4, h_fail=hfail / 4, acc=corr / 8, clean_exact=float(clean), robust_exact=float(allok),
                             sens=sum(len(set(s)) > 1 for s in seq) / 2)
            sts[cond] = ss
        out[pid] = dict(stratum=m["truth_code"], metrics=res, states=sts, truth=truth)
    return out


def draws(strata, B=10000, seed=5302):
    rng = np.random.default_rng(seed)
    return [rng.integers(0, len(v), size=(B, len(v))) for v in strata]


def compare(stage, reqs, recs, manifest, report, labels):
    """원시 record에서 모든 수치를 다시 계산해 report와 대조한다. returns (mismatches, n_checked, parsed)."""
    bad = []
    # GT 독립 대조: manifest 상태 == labels.json (원천 HF label 대응은 data_check가 검증)
    for m in manifest["rows"]:
        L = labels[m["PatientID"]]
        if (m["q"]["qA"]["state"], m["q"]["qB"]["state"]) != (L["cardiomegaly"], L["pleural_effusion"]):
            bad.append(("manifest_truth_vs_labels", m["PatientID"]))
    rec = {r["request_id"]: r for r in recs}
    parsed = {}
    for q in reqs:
        r = rec[q["request_id"]]
        parsed[(q["patient"], q["cond"])] = parse_raw(r["suffix_text_raw"], r["ended_eos"], q["targets"])
    pp = per_patient(manifest, parsed)
    byst = {}
    for pid in sorted(pp):
        byst.setdefault(pp[pid]["stratum"], []).append(pid)
    skeys = sorted(byst)
    strata = [byst[k] for k in skeys]
    dr = draws(strata)
    N = len(pp)
    metrics = ["r", "h", "h_fail", "acc", "clean_exact", "robust_exact", "sens"]
    n_checked = 0

    def close(x, y, tol=1e-9):
        return abs(x - y) <= tol

    def samp(cond, m):
        tot = 0
        for pids, idx in zip(strata, dr):
            v = np.array([pp[p]["metrics"][cond][m] for p in pids], float)
            tot = tot + v[idx].mean(axis=1)
        return tot / len(strata)

    def macro(cond, m):
        return sum(sum(pp[p]["metrics"][cond][m] for p in pids) / len(pids) for pids in strata) / len(strata)

    for cond, md in report["conds"].items():
        for m in metrics:
            s = samp(cond, m)
            lo, hi = np.percentile(s, 2.5), np.percentile(s, 97.5)
            nat = sum(pp[p]["metrics"][cond][m] for p in pp) / N
            n_checked += 1
            if not (close(macro(cond, m), md[m]["mean"]) and close(nat, md[m]["natural_mean"]) and close(lo, md[m]["lo95"]) and close(hi, md[m]["hi95"])):
                bad.append(("cond", cond, m, macro(cond, m), md[m]))
            if "simult_lo" in md[m]:
                slo, shi = np.percentile(s, (1 - SIMULT_LEVEL) / 2 * 100), np.percentile(s, 100 - (1 - SIMULT_LEVEL) / 2 * 100)
                n_checked += 1
                if not (close(slo, md[m]["simult_lo"]) and close(shi, md[m]["simult_hi"]) and close(md[m]["simult_level"], SIMULT_LEVEL)):
                    bad.append(("simult", cond, m, slo, shi, md[m]))
                # 퇴화 exact 경계
                allzero = all((pp[p]["metrics"][cond]["h_fail"] == 0) if m == "h_fail" else (pp[p]["metrics"][cond]["r"] == 1) for p in pp)
                n_checked += 1
                dg = md[m].get("degenerate_exact")
                if allzero != (dg is not None):
                    bad.append(("degenerate_flag", cond, m, allzero, dg))
                elif allzero:
                    a_ = 0.05 / (len(strata) * 8)
                    ub = sum(1 - a_ ** (1 / len(pids)) for pids in strata) / len(strata)
                    if not close(ub, dg["any_event_patient_fraction_upper"]):
                        bad.append(("degenerate_bound", cond, m, ub, dg))
    for key, dd in report["diffs"].items():
        ab, m = key.split(":")
        x, y = ab.split("-")
        s = samp(x, m) - samp(y, m)
        al = (1 - dd["level"]) / 2 * 100
        n_checked += 1
        if not (close(macro(x, m) - macro(y, m), dd["mean"]) and close(np.percentile(s, al), dd["lo"]) and close(np.percentile(s, 100 - al), dd["hi"])
                and bool(np.ptp(s) == 0) == dd["degenerate"]):
            bad.append(("diff", key, macro(x, m) - macro(y, m), dd))
    # 공통 valid 보조 분석
    for key, cv in report["common_valid"].items():
        x, y = key.split("-")
        keep = {}
        for p in pp:
            for (d, i, _w, _ok, vx), (_d, _i, _w2, _ok2, vy) in zip(pp[p]["states"][x], pp[p]["states"][y]):
                keep[(p, d, i)] = vx and vy

        def rates(c):
            rr, hh = [], []
            for pids in strata:
                fw = nw = hf = nr = 0
                for p in pids:
                    for (d, i, wrong, ok, _v) in pp[p]["states"][c]:
                        if not keep[(p, d, i)]:
                            continue
                        if wrong:
                            nw += 1
                            fw += ok
                        else:
                            nr += 1
                            hf += not ok
                rr.append(fw / nw if nw else float("nan"))
                hh.append(hf / nr if nr else float("nan"))
            return float(np.nanmean(rr)), float(np.nanmean(hh))
        ra, ha = rates(x)
        rb, hb = rates(y)
        n_checked += 1
        if not (cv["n_common_valid_states"] == sum(keep.values()) and close(cv["r_diff"], ra - rb) and close(cv["hfail_diff"], ha - hb)):
            bad.append(("common_valid", key, ra - rb, ha - hb, cv))
    # valid율·형식·비EOS
    nonO = [(c, v) for (p, c), v in parsed.items() if not c.startswith(("O_", "OT_"))]
    n_checked += 1
    if sum(v is not None for _, v in nonO) != report["n_valid_requests_nonoracle"] or len(nonO) != report["n_requests_nonoracle"]:
        bad.append(("n_valid", sum(v is not None for _, v in nonO), report["n_valid_requests_nonoracle"]))
    n_checked += 1
    if sum(1 for q in reqs if not rec[q["request_id"]]["ended_eos"]) != report["n_non_eos_final"]:
        bad.append(("non_eos", report["n_non_eos_final"]))
    per_cond = {}
    for (p, c), v in parsed.items():
        if c.startswith(("O_", "OT_")):
            continue
        b = c.split("_")[0] if c.startswith(("R1", "R2", "T_", "BI")) else c
        per_cond.setdefault(b, [0, 0])
        per_cond[b][1] += 1
        per_cond[b][0] += v is not None
    for b, (k, n) in per_cond.items():
        n_checked += 1
        if not close(k / n, report["valid_rate_by_cond"][b]):
            bad.append(("valid_rate", b, k / n, report["valid_rate_by_cond"][b]))
    # oracle (D): 정답 상태와 결정론적 문장 렌더링
    if stage == "D":
        groups = {"chexpert_D16": manifest["rows"], "padchest_D8": manifest["pc_oracle_rows"]}
        for name, rows in groups.items():
            for pref, mod in (("O_d", "image"), ("OT_d", "text")):
                n = ok = 0
                for m in rows:
                    truth = {i: m["q"][i]["state"] for i in IDS}
                    for d in DRAFTS:
                        n += 1
                        ok += parsed[(m["PatientID"], pref + d)] == truth
                n_checked += 1
                ro = report["oracle"][f"{name}:{mod}"]
                if not (ro["n"] == n and ro["ok"] == ok):
                    bad.append(("oracle", name, mod, n, ok, ro["n"], ro["ok"]))
    return bad, n_checked, parsed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit(f"refuse to overwrite {a.out}")
    recs = rr53_run.verify(a.out_dir, a.stage, a.protocol)
    req_path = f"{OUT}/requests/requests_{a.stage}.jsonl"
    reqs = [json.loads(l) for l in open(req_path)]
    man_path = f"{OUT}/data/manifest_{a.stage}.json"
    manifest = json.load(open(man_path))
    report = json.load(open(a.report))
    labels = json.load(open("results/iter_018/manifests/labels.json"))
    bad, n_checked, parsed = compare(a.stage, reqs, recs, manifest, report, labels)
    src_now = dict(protocol_sha256=sha_file(a.protocol), requests_sha256=sha_file(req_path), manifest_sha256=sha_file(man_path),
                   eval_sha256=sha_file("rr53_eval.py"), data_check_sha256=sha_file(f"{OUT}/data/data_check.json"),
                   worker_files_sha256={f: sha_file(os.path.join(a.out_dir, f)) for f in sorted(os.listdir(a.out_dir))
                                        if f.startswith("gen_worker") and f.endswith(".jsonl")})
    for k, v in src_now.items():
        n_checked += 1
        if report["source"][k] != v:
            bad.append(("report_source_digest", k))
    res = dict(stage=a.stage, n_checked=n_checked, mismatches=bad, passed=(not bad), n_records=len(recs), n_valid_parse=sum(v is not None for v in parsed.values()),
               source_digests=dict(report=sha_file(a.report), verify_py=sha_file("rr53_verify.py"), **src_now))
    tmp = a.out + ".tmp"
    json.dump(res, open(tmp, "w"), indent=1, default=str)
    os.replace(tmp, a.out)
    print("PASS" if res["passed"] else "FAIL", n_checked, "checks;", len(bad), "mismatches")
    sys.exit(0 if res["passed"] else 1)


if __name__ == "__main__":
    main()
