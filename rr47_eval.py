"""iter_047 평가: 상태 JSON -> 최종 상태 -> 수정률 r / 훼손률 h / 보존 실패율 h_fail / 최종 상태 정확도 / clean·robust exact / 초안 민감도,
환자 단위 층화 paired bootstrap (seed 4702, 10,000회). CPU only. 호출자는 verify(pg43_run.verify_completion + rr47_run.verify)를 먼저 통과해야 한다.

bootstrap 규약(검증기와 공유하는 명세): 층(truth_code)을 정렬 순서로, 층 안의 환자를 PatientID 정렬 순서로 두고
rng=np.random.default_rng(4702)에서 층마다 integers(0, n_층, size=(B, n_층))를 순서대로 뽑아 모든 조건·지표가 같은 resample을 쓴다.
"""
import json
import math

import numpy as np

import rr47_spec as S

CONDS_EDIT = ["R1", "R2", "T"]
CONDS = ["K", "R1", "R2", "T", "BJ", "BI"]
METRICS = ["r", "h", "h_fail", "acc", "clean_exact", "robust_exact", "sens"]
DRAFTS = S.DRAFT_CODES


def parse_all(manifest, rows, recs):
    """records -> {patient: {cond: parsed}}. 모든 요청을 한 번씩 소비하고 누락/잉여는 예외."""
    by_rid = {r["request_id"]: r for r in recs}
    out = {}
    for row in rows:
        rec = by_rid[row["request_id"]]
        p = S.parse_state(rec["suffix_text_raw"], rec["ended_eos"], row["targets"])
        p["final_cap"] = rec["final_cap"]
        p["ended_eos"] = rec["ended_eos"]
        out.setdefault(row["patient"], {})[row["cond"]] = p
    return out


def finals_for(cond, draft, parsed_by_cond, drafts_states):
    """조건·초안 -> {qA: state, qB: state} (state in present/absent/uncertain/invalid)."""
    if cond == "K":
        return dict(zip(S.IDS, drafts_states))
    if cond in CONDS_EDIT:
        p = parsed_by_cond[f"{cond}_d{draft}"]
        return {i: S.final_state(p, i) for i in S.IDS}
    if cond == "BJ":
        p = parsed_by_cond["BJ"]
        return {i: S.final_state(p, i) for i in S.IDS}
    if cond == "BI":
        return {i: S.final_state(parsed_by_cond[f"BI_{i}"], i) for i in S.IDS}
    raise KeyError(cond)


def patient_metrics(truth, cond, parsed_by_cond):
    """truth: [stateA, stateB]. 환자 단위 지표 dict (분모는 환자마다 고정: 틀린 상태 4, 맞은 상태 4, 전체 8)."""
    n_wrong = n_right = 0
    fixed = harmed = hfail = correct = 0
    per_finding_final = {i: [] for i in S.IDS}
    exact_clean = None
    all_ok = True
    for d in DRAFTS:
        ds = S.code_states(d)
        fin = finals_for(cond, d, parsed_by_cond, ds)
        ok_both = True
        for k, i in enumerate(S.IDS):
            f = fin[i]
            per_finding_final[i].append(f)
            if f == truth[k]:
                correct += 1
            else:
                ok_both = False
            if ds[k] != truth[k]:
                n_wrong += 1
                fixed += f == truth[k]
            else:
                n_right += 1
                harmed += f == S.flip(truth[k])
                hfail += f != truth[k]
        if d == S.draft_code(*truth):
            exact_clean = ok_both
        all_ok = all_ok and ok_both
    assert n_wrong == 4 and n_right == 4
    sens = sum(len(set(v)) > 1 for v in per_finding_final.values()) / 2
    return dict(r=fixed / 4, h=harmed / 4, h_fail=hfail / 4, acc=correct / 8, clean_exact=float(bool(exact_clean)), robust_exact=float(all_ok), sens=sens)


def build_table(manifest, rows, recs):
    parsed = parse_all(manifest, rows, recs)
    table = {}
    for m in manifest["rows"]:
        pid = m["PatientID"]
        truth = [m["q"][i]["state"] for i in S.IDS]
        table[pid] = dict(stratum=m["truth_code"], truth=truth,
                          metrics={c: patient_metrics(truth, c, parsed[pid]) for c in CONDS if c != "K" or True})
    return table, parsed


def strata(table):
    st = {}
    for pid in sorted(table):
        st.setdefault(table[pid]["stratum"], []).append(pid)
    return dict(sorted(st.items()))


def boot_indices(st, B=S.BOOT_B, seed=S.BOOT_SEED):
    rng = np.random.default_rng(seed)
    return [rng.integers(0, len(p), size=(B, len(p))) for p in st.values()]


def boot_stat(table, st, idxs, fn):
    """fn(pid)->float. returns array (B,) of resampled patient means (층별 resample을 합쳐 전체 환자 수로 나눈 값)."""
    N = sum(len(p) for p in st.values())
    tot = 0
    for p, idx in zip(st.values(), idxs):
        v = np.array([fn(pid) for pid in p], float)
        tot = tot + v[idx].sum(axis=1)
    return tot / N


def ci(arr, level):
    a = (1 - level) / 2 * 100
    return float(np.percentile(arr, a)), float(np.percentile(arr, 100 - a))


def summarize(table, conds=CONDS, extra_pairs=()):
    st = strata(table)
    idxs = boot_indices(st)
    N = len(table)
    out = dict(n_patients=N, strata_sizes={k: len(v) for k, v in st.items()}, conds={}, diffs={})
    cache = {}

    def samples(c, m):
        if (c, m) not in cache:
            cache[(c, m)] = boot_stat(table, st, idxs, lambda pid: table[pid]["metrics"][c][m])
        return cache[(c, m)]

    for c in conds:
        out["conds"][c] = {}
        for m in METRICS:
            mean = float(np.mean([table[p]["metrics"][c][m] for p in table]))
            lo, hi = ci(samples(c, m), 0.95)
            out["conds"][c][m] = dict(mean=mean, lo95=lo, hi95=hi)
    pairs = [("BJ", "R2", 0.975, ["r", "h_fail", "h", "acc"]), ("BJ", "T", 0.95, ["acc"]), ("R2", "R1", 0.95, ["r", "h_fail", "acc"]),
             ("BI", "BJ", 0.95, ["r", "h_fail", "acc"]), ("R2", "T", 0.95, ["acc"]), ("R1", "T", 0.95, ["acc"]), ("R2", "K", 0.95, ["r", "h_fail"]),
             ("BJ", "R1", 0.95, ["r", "h_fail"]), ("BI", "R2", 0.95, ["r", "h_fail"])] + list(extra_pairs)
    for a, b, lev, ms in pairs:
        if a not in conds or b not in conds:
            continue
        for m in ms:
            d = samples(a, m) - samples(b, m)
            mean = float(np.mean([table[p]["metrics"][a][m] - table[p]["metrics"][b][m] for p in table]))
            lo, hi = ci(d, lev)
            out["diffs"][f"{a}-{b}:{m}"] = dict(mean=mean, lo=lo, hi=hi, level=lev, degenerate=bool(np.ptp(d) == 0),
                                              exploratory=(lev != 0.975))
    return out


def format_counts(parsed):
    out = {}
    for pid, byc in parsed.items():
        for cond, p in byc.items():
            base = cond.split("_d")[0] if cond.startswith(("R1", "R2", "T_", "O_")) else cond.split("_")[0] if cond.startswith("BI") else cond
            out.setdefault(base, {}).setdefault(p["status"], 0)
            out[base][p["status"]] += 1
    return out


def uncertain_counts(parsed):
    out = {}
    for pid, byc in parsed.items():
        for cond, p in byc.items():
            base = cond.split("_d")[0] if cond.startswith(("R1", "R2", "T_", "O_")) else cond.split("_")[0] if cond.startswith("BI") else cond
            if p["status"] == "ok":
                for i, v in p["answers"].items():
                    out.setdefault(base, {}).setdefault(v, 0)
                    out[base][v] += 1
    return out


def oracle_check(manifest, parsed):
    """O 조건: 최종 상태가 정답이고 결정론적 문장 렌더링이 canonical 문장과 일치하는가 (D8 형식·편집 연결 검사)."""
    n = ok = 0
    bad = []
    for m in manifest["rows"]:
        pid = m["PatientID"]
        fp = {i: m["q"][i]["finding"] for i in S.IDS}
        truth = {i: m["q"][i]["state"] for i in S.IDS}
        for d in DRAFTS:
            p = parsed[pid].get(f"O_d{d}")
            if p is None:
                continue
            n += 1
            fin = {i: S.final_state(p, i) for i in S.IDS}
            rend = S.render_final(fp, fin)
            want = [S.FINDINGS[fp[i]][truth[i]] for i in S.IDS]
            if fin == truth and rend == want:
                ok += 1
            else:
                bad.append((pid, d, fin))
    return dict(n=n, ok=ok, bad=bad)


def main():
    import argparse
    import hashlib
    import os
    import sys
    import rr47_run
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit(f"refuse to overwrite {a.out}")
    recs = rr47_run.verify(a.out_dir, a.stage, a.protocol)  # completion·요청 집합·hash 재검증 후에만 점수 계산
    req_path = f"results/iter_047/requests/requests_{a.stage}.jsonl"
    rows = [json.loads(l) for l in open(req_path)]
    manifest = json.load(open(f"results/iter_047/data/manifest_{a.stage}.json"))
    table, parsed = build_table(manifest, rows, recs)
    rep = summarize(table)
    rep["stage"] = a.stage
    rep["format_status_counts"] = format_counts(parsed)
    rep["answer_counts_ok_only"] = uncertain_counts(parsed)
    nonO = [(c, p) for byc in parsed.values() for c, p in byc.items() if not c.startswith("O_")]
    rep["n_valid_requests_nonoracle"] = sum(p["status"] == "ok" for c, p in nonO)
    rep["n_requests_nonoracle"] = len(nonO)
    rep["n_non_eos_final"] = sum(1 for byc in parsed.values() for p in byc.values() if not p["ended_eos"])
    rep["oracle"] = oracle_check(manifest, parsed)
    rep["per_patient_metrics"] = dict((pid, dict(stratum=t["stratum"], truth=t["truth"], metrics=t["metrics"])) for pid, t in table.items())
    rep["by_truth_stratum"] = dict((k, dict((c, dict((m, float(np.mean([table[p]["metrics"][c][m] for p in v]))) for m in METRICS)) for c in CONDS))
                                   for k, v in strata(table).items())
    h = hashlib.sha256()
    for f in sorted(os.listdir(a.out_dir)):
        if f.startswith("gen_worker") and f.endswith(".jsonl"):
            h.update(open(os.path.join(a.out_dir, f), "rb").read())
    rep["source"] = dict(protocol=a.protocol, out_dir=a.out_dir, worker_files_digest=h.hexdigest(), spec=S.VERSION, boot_seed=S.BOOT_SEED, boot_b=S.BOOT_B)
    tmp = a.out + ".tmp"
    json.dump(rep, open(tmp, "w"), indent=1, default=str)
    os.replace(tmp, a.out)
    print("report written", a.out)


if __name__ == "__main__":
    main()
