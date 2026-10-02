"""iter_053 평가: 상태 JSON -> 최종 상태 -> r / h / h_fail / acc / clean·robust exact / sens, 네 truth 조합 동일 가중 macro,
층화 paired 환자 bootstrap(seed 5302, 10,000회), 동시 보정 구간, 퇴화 경우의 exact binomial 경계, 공통 valid 보조 분석. CPU only.

호출자는 rr53_run.verify(manifest 재구성 요청 대조 + completion 검증)를 먼저 통과해야 한다 (main이 강제한다).
bootstrap 규약(검증기와 공유): 층(truth_code)을 정렬 순서로, 층 안의 환자를 PatientID 정렬 순서로 두고 rng=np.random.default_rng(5302)에서
층마다 integers(0, n_층, size=(B, n_층))를 순서대로 뽑는다. macro 통계 = 층별 resample 평균의 동일 가중 평균. 모든 조건·지표가 같은 resample을 쓴다.
"""
import argparse
import hashlib
import json
import math
import os
import sys

import numpy as np

import rr47_eval as E47
import rr53_spec as S
from rr53_data import OUT, file_sha

CONDS = ["K", "R1", "R2", "T", "BJ", "BT", "BI"]
SIMPLE = ["R1", "R2", "BJ", "BI"]
METRICS = ["r", "h", "h_fail", "acc", "clean_exact", "robust_exact", "sens"]
DRAFTS = S.DRAFT_CODES
N_SIMULT = len(SIMPLE) * 2  # 네 조건 × 두 endpoint(r, h_fail)
SIMULT_LEVEL = 1 - 0.05 / N_SIMULT


def finals_for(cond, draft, byc, ds):
    if cond == "K":
        return dict(zip(S.IDS, ds)), True
    if cond in ("R1", "R2", "T"):
        p = byc[f"{cond}_d{draft}"]
    elif cond in ("BJ", "BT"):
        p = byc[cond]
    elif cond == "BI":
        return {i: S.final_state(byc[f"BI_{i}"], i) for i in S.IDS}, all(byc[f"BI_{i}"]["status"] == "ok" for i in S.IDS)
    else:
        raise KeyError(cond)
    return {i: S.final_state(p, i) for i in S.IDS}, p["status"] == "ok"


def patient_metrics(truth, cond, byc):
    """truth=[A,B]. 분모는 환자마다 고정(틀린 상태 4, 맞은 상태 4, 전체 8). returns (metrics, states list)."""
    n_wrong = n_right = fixed = harmed = hfail = correct = 0
    seq = {i: [] for i in S.IDS}
    clean = None
    allok = True
    states = []
    for d in DRAFTS:
        ds = S.code_states(d)
        fin, valid = finals_for(cond, d, byc, ds)
        both = True
        for k, i in enumerate(S.IDS):
            f = fin[i]
            seq[i].append(f)
            correct += f == truth[k]
            both = both and f == truth[k]
            wrong = ds[k] != truth[k]
            if wrong:
                n_wrong += 1
                fixed += f == truth[k]
            else:
                n_right += 1
                harmed += f == S.flip(truth[k])
                hfail += f != truth[k]
            states.append((d, i, wrong, f == truth[k], f == S.flip(truth[k]), valid))
        if d == S.draft_code(*truth):
            clean = both
        allok = allok and both
    assert n_wrong == 4 and n_right == 4
    sens = sum(len(set(v)) > 1 for v in seq.values()) / 2
    return dict(r=fixed / 4, h=harmed / 4, h_fail=hfail / 4, acc=correct / 8, clean_exact=float(bool(clean)), robust_exact=float(allok), sens=sens), states


def build_table(manifest, rows, recs):
    parsed = E47.parse_all(manifest, rows, recs)
    table = {}
    for m in manifest["rows"]:
        pid = m["PatientID"]
        truth = [m["q"][i]["state"] for i in S.IDS]
        met, st = {}, {}
        for c in CONDS:
            met[c], st[c] = patient_metrics(truth, c, parsed[pid])
        table[pid] = dict(stratum=m["truth_code"], truth=truth, metrics=met, states=st)
    return table, parsed


def strata(table):
    return E47.strata(table)


def boot_idx(st):
    return E47.boot_indices(st, S.BOOT_B, S.BOOT_SEED)


def macro_mean(table, st, cond, metric):
    return float(np.mean([np.mean([table[p]["metrics"][cond][metric] for p in pids]) for pids in st.values()]))


def macro_samples(table, st, idxs, cond, metric):
    tot = 0
    for pids, idx in zip(st.values(), idxs):
        v = np.array([table[p]["metrics"][cond][metric] for p in pids], float)
        tot = tot + v[idx].mean(axis=1)
    return tot / len(st)


def cp_upper_zero(n, alpha):
    """0/n 사건에 대한 Clopper-Pearson 단측 상한: 1 - alpha^(1/n)."""
    return 1 - alpha ** (1 / n)


def degenerate_bounds(table, st, cond, metric):
    """모든 환자에서 사건 0(나쁜 방향)이면 층별 exact binomial 상한을 Bonferroni(층 수·검정 수)로 결합한 보수적 경계. 아니면 None.
    h_fail: any-failure 환자 비율 상한(>= h_fail 상한). r: any-miss 환자 비율 상한 -> r 하한 = 1 - 상한."""
    if metric == "h_fail":
        bad = lambda p: table[p]["metrics"][cond]["h_fail"] > 0
    elif metric == "r":
        bad = lambda p: table[p]["metrics"][cond]["r"] < 1
    else:
        return None
    if any(bad(p) for pids in st.values() for p in pids):
        return None
    a = 0.05 / (len(st) * N_SIMULT)
    ub = float(np.mean([cp_upper_zero(len(pids), a) for pids in st.values()]))
    return dict(any_event_patient_fraction_upper=ub, alpha_per_stratum_test=a)


def common_valid(table, st, a, b):
    """두 조건 모두 해당 요청이 valid인 상태만 모아 macro 수정률·보존 실패율(h_fail) 차이 (점추정, 보조)."""
    va = {(p, d, i): v for p in table for (d, i, _w, _o, _h, v) in table[p]["states"][a]}
    vb = {(p, d, i): v for p in table for (d, i, _w, _o, _h, v) in table[p]["states"][b]}
    keep = {k: va[k] and vb[k] for k in va}

    def rates(c):
        rr, hh = [], []
        for pids in st.values():
            fw = nw = hf = nr = 0
            for p in pids:
                for (d, i, wrong, ok, _h, _v) in table[p]["states"][c]:
                    if not keep[(p, d, i)]:
                        continue
                    if wrong:
                        nw += 1
                        fw += ok
                    else:
                        nr += 1
                        hf += (not ok)
            rr.append(fw / nw if nw else float("nan"))
            hh.append(hf / nr if nr else float("nan"))
        return float(np.nanmean(rr)), float(np.nanmean(hh))

    ra, ha = rates(a)
    rb, hb = rates(b)
    return dict(n_common_valid_states=int(sum(keep.values())), n_states=len(keep), r_a=ra, r_b=rb, r_diff=ra - rb, hfail_a=ha, hfail_b=hb, hfail_diff=ha - hb)


PAIRS = [("BJ", "R2", 0.975, ["r", "h_fail"]), ("BJ", "BT", 0.95, ["acc"]),
         ("BJ", "R2", 0.95, ["h", "acc"]), ("R2", "R1", 0.95, ["r", "h_fail", "acc"]), ("BI", "BJ", 0.95, ["r", "h_fail", "acc"]),
         ("R2", "T", 0.95, ["acc"]), ("R1", "T", 0.95, ["acc"]), ("BT", "T", 0.95, ["acc"]), ("R2", "K", 0.95, ["r", "h_fail"]),
         ("BJ", "R1", 0.95, ["r", "h_fail"]), ("BI", "R2", 0.95, ["r", "h_fail"])]
PRIMARY = {("BJ", "R2", 0.975, "r"), ("BJ", "R2", 0.975, "h_fail"), ("BJ", "BT", 0.95, "acc")}


def summarize(table):
    st = strata(table)
    idxs = boot_idx(st)
    N = len(table)
    out = dict(n_patients=N, strata_sizes={k: len(v) for k, v in st.items()}, weighting="macro: 네 truth 조합 동일 가중(층별 환자 평균의 평균)", conds={}, diffs={})
    cache = {}

    def samp(c, m):
        if (c, m) not in cache:
            cache[(c, m)] = macro_samples(table, st, idxs, c, m)
        return cache[(c, m)]

    for c in CONDS:
        out["conds"][c] = {}
        for m in METRICS:
            lo, hi = E47.ci(samp(c, m), 0.95)
            d = dict(mean=macro_mean(table, st, c, m), natural_mean=float(np.mean([table[p]["metrics"][c][m] for p in table])), lo95=lo, hi95=hi)
            if c in SIMPLE and m in ("r", "h_fail"):
                slo, shi = E47.ci(samp(c, m), SIMULT_LEVEL)
                d.update(simult_level=SIMULT_LEVEL, simult_lo=slo, simult_hi=shi, degenerate_exact=degenerate_bounds(table, st, c, m))
            out["conds"][c][m] = d
    for a, b, lev, ms in PAIRS:
        for m in ms:
            key = f"{a}-{b}:{m}"
            assert key not in out["diffs"], key
            dd = samp(a, m) - samp(b, m)
            lo, hi = E47.ci(dd, lev)
            out["diffs"][key] = dict(mean=macro_mean(table, st, a, m) - macro_mean(table, st, b, m), lo=lo, hi=hi, level=lev,
                                     degenerate=bool(np.ptp(dd) == 0), primary=(a, b, lev, m) in PRIMARY)
    out["common_valid"] = {f"{a}-{b}": common_valid(table, st, a, b) for a, b in (("BJ", "R2"), ("BJ", "R1"), ("BI", "R2"), ("BJ", "BI"))}
    return out


def format_counts(parsed):
    out = {}
    for pid, byc in parsed.items():
        for cond, p in byc.items():
            base = cond.split("_")[0] if cond.startswith(("R1", "R2", "T_", "BI", "O_", "OT_")) else cond
            out.setdefault(base, {}).setdefault(p["status"], 0)
            out[base][p["status"]] += 1
    return out


def answer_counts(parsed):
    out = {}
    for pid, byc in parsed.items():
        for cond, p in byc.items():
            base = cond.split("_")[0] if cond.startswith(("R1", "R2", "T_", "BI", "O_", "OT_")) else cond
            if p["status"] == "ok":
                for v in p["answers"].values():
                    out.setdefault(base, {}).setdefault(v, 0)
                    out[base][v] += 1
    return out


def oracle_check(groups, parsed):
    """groups: {name: manifest_rows}. O_dXX는 image, OT_dXX는 text oracle. 정답 상태 + 결정론적 문장 렌더링 일치만 통과."""
    out = {}
    for name, rows in groups.items():
        for pref, mod in (("O_d", "image"), ("OT_d", "text")):
            n = ok = 0
            bad = []
            for m in rows:
                pid = m["PatientID"]
                fp = {i: m["q"][i]["finding"] for i in S.IDS}
                truth = {i: m["q"][i]["state"] for i in S.IDS}
                for d in DRAFTS:
                    p = parsed[pid][pref + d]
                    n += 1
                    fin = {i: S.final_state(p, i) for i in S.IDS}
                    want = [S.FINDINGS[fp[i]][truth[i]] for i in S.IDS]
                    if fin == truth and S.render_final(fp, fin) == want:
                        ok += 1
                    else:
                        bad.append(dict(patient=pid, draft=d, final=fin, status=p["status"]))
            out[f"{name}:{mod}"] = dict(n=n, ok=ok, bad=bad)
    return out


def make_report(stage, manifest, rows, recs):
    """manifest·요청 행·verify를 통과한 record -> report(수치 부분)."""
    main_rows = [r for r in rows if not r["cond"].startswith(("O_", "OT_"))]
    table, parsed_main = build_table(manifest, [r for r in main_rows if r["set"] == stage], recs)
    rep = summarize(table)
    rep["stage"] = stage
    parsed_all = E47.parse_all(manifest, rows, recs)
    nonO = [(c, p) for byc in parsed_all.values() for c, p in byc.items() if not c.startswith(("O_", "OT_"))]
    rep["format_status_counts"] = format_counts({p: {c: v for c, v in byc.items() if not c.startswith(("O_", "OT_"))} for p, byc in parsed_all.items()})
    rep["answer_counts_ok_only"] = answer_counts({p: {c: v for c, v in byc.items() if not c.startswith(("O_", "OT_"))} for p, byc in parsed_all.items()})
    rep["n_valid_requests_nonoracle"] = sum(p["status"] == "ok" for c, p in nonO)
    rep["n_requests_nonoracle"] = len(nonO)
    rep["n_non_eos_final"] = sum(1 for byc in parsed_all.values() for p in byc.values() if not p["ended_eos"])
    rep["valid_rate_by_cond"] = {c: v.get("ok", 0) / sum(v.values()) for c, v in rep["format_status_counts"].items()}
    if stage == "D":
        rep["oracle"] = oracle_check({"chexpert_D16": manifest["rows"], "padchest_D8": manifest["pc_oracle_rows"]}, parsed_all)
    rep["per_patient_metrics"] = {pid: dict(stratum=t["stratum"], truth=t["truth"], metrics=t["metrics"]) for pid, t in table.items()}
    st = strata(table)
    rep["by_truth_stratum"] = {k: {c: {m: float(np.mean([table[p]["metrics"][c][m] for p in v])) for m in METRICS} for c in CONDS} for k, v in st.items()}
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=["D", "E", "F"])
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit(f"refuse to overwrite {a.out}")
    import rr53_run
    recs = rr53_run.verify(a.out_dir, a.stage, a.protocol)
    req_path = f"{OUT}/requests/requests_{a.stage}.jsonl"
    rows = [json.loads(l) for l in open(req_path)]
    man_path = f"{OUT}/data/manifest_{a.stage}.json"
    manifest = json.load(open(man_path))
    rep = make_report(a.stage, manifest, rows, recs)
    h = hashlib.sha256()
    wf = {}
    for f in sorted(os.listdir(a.out_dir)):
        if f.startswith("gen_worker") and f.endswith(".jsonl"):
            wf[f] = file_sha(os.path.join(a.out_dir, f))
            h.update(open(os.path.join(a.out_dir, f), "rb").read())
    rep["source"] = dict(protocol=a.protocol, protocol_sha256=file_sha(a.protocol), out_dir=a.out_dir, worker_files_sha256=wf, worker_files_digest=h.hexdigest(),
                         requests_sha256=file_sha(req_path), manifest_sha256=file_sha(man_path), spec=S.VERSION, boot_seed=S.BOOT_SEED, boot_b=S.BOOT_B,
                         eval_sha256=file_sha("rr53_eval.py"), data_check_sha256=file_sha(f"{OUT}/data/data_check.json"))
    tmp = a.out + ".tmp"
    json.dump(rep, open(tmp, "w"), indent=1, default=str)
    os.replace(tmp, a.out)
    print("report written", a.out)


if __name__ == "__main__":
    main()
