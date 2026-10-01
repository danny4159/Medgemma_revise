"""iter_047 독립 검증기. production(rr47_eval/rr47_spec의 parser·점수 함수)을 호출하지 않고 원시 record와 manifest·요청에서 다시 계산해
저장 report와 대조한다. 모든 조건·지표·diff를 검사하며 불일치 조건을 제외한 PASS를 만들지 않는다.

python rr47_verify.py --stage D8 --out-dir D --protocol P --report REPORT --out verify.json
(completion 검증은 rr47_run.verify를 호출한다 — 이는 요청 집합·hash 연결 검사이며 점수 계산이 아니다.)
"""
import argparse
import hashlib
import json
import os
import re
import sys

import numpy as np

import rr47_run
import pg43_run as PR

ANS = {"present", "absent", "uncertain"}
FINDING_SENT = None  # manifest에서 finding 이름이 아니라 상태만 쓰므로 필요 없음
DRAFTS = ["00", "01", "10", "11"]


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def parse_raw(raw, eos, keys):
    """독립 parser: (state dict or None). None이면 invalid."""
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
    # 최상위 객체의 key 중복 여부는 pairs 전체(내부 객체 포함)로 보수적으로 검사한다. 값이 모두 문자열이어야 하므로 내부 객체는 있을 수 없다.
    if len([k for k, _ in pairs]) != len({k for k, _ in pairs}):
        return None
    if not isinstance(obj, dict) or set(obj) != set(keys) or len(obj) != len(keys):
        return None
    for v in obj.values():
        if not isinstance(v, str) or v not in ANS:
            return None
    return obj


def bits(code):
    return ["present" if ch == "1" else "absent" for ch in code]


def per_patient(manifest, reqs, recs):
    rec = {r["request_id"]: r for r in recs}
    parsed = {}
    for q in reqs:
        r = rec[q["request_id"]]
        parsed[(q["patient"], q["cond"])] = parse_raw(r["suffix_text_raw"], r["ended_eos"], q["targets"])
    out = {}
    for m in manifest["rows"]:
        pid = m["PatientID"]
        truth = [m["q"][i]["state"] for i in ("qA", "qB")]
        res = {}
        for cond in ["K", "R1", "R2", "T", "BJ", "BI"]:
            fixed = harmed = hfail = corr = 0
            clean = False
            allok = True
            seq = [[], []]
            for d in DRAFTS:
                ds = bits(d)
                fin = []
                for k, i in enumerate(("qA", "qB")):
                    if cond == "K":
                        v = ds[k]
                    elif cond in ("R1", "R2", "T"):
                        p = parsed[(pid, f"{cond}_d{d}")]
                        v = p[i] if p else "invalid"
                    elif cond == "BJ":
                        p = parsed[(pid, "BJ")]
                        v = p[i] if p else "invalid"
                    else:
                        p = parsed[(pid, f"BI_{i}")]
                        v = p[i] if p else "invalid"
                    fin.append(v)
                    seq[k].append(v)
                    corr += v == truth[k]
                    if ds[k] != truth[k]:
                        fixed += v == truth[k]
                    else:
                        harmed += v == ("absent" if truth[k] == "present" else "present")
                        hfail += v != truth[k]
                both = all(fin[k] == truth[k] for k in range(2))
                allok = allok and both
                if ds == truth:
                    clean = both
            sens = sum(len(set(s)) > 1 for s in seq) / 2
            res[cond] = dict(r=fixed / 4, h=harmed / 4, h_fail=hfail / 4, acc=corr / 8, clean_exact=float(clean), robust_exact=float(allok), sens=sens)
        out[pid] = dict(stratum=m["truth_code"], metrics=res)
    return out, parsed


def boot(vals_by_stratum, B=10000, seed=4702):
    """vals_by_stratum: list(층 정렬순) of list(PatientID 정렬순) of dict(cond->metric->value). returns draws list per stratum."""
    rng = np.random.default_rng(seed)
    return [rng.integers(0, len(v), size=(B, len(v))) for v in vals_by_stratum]


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
    recs = rr47_run.verify(a.out_dir, a.stage, a.protocol)
    req_path = f"results/iter_047/requests/requests_{a.stage}.jsonl"
    reqs = [json.loads(l) for l in open(req_path)]
    manifest = json.load(open(f"results/iter_047/data/manifest_{a.stage}.json"))
    report = json.load(open(a.report))
    pp, parsed = per_patient(manifest, reqs, recs)
    byst = {}
    for pid in sorted(pp):
        byst.setdefault(pp[pid]["stratum"], []).append(pid)
    strata = [byst[k] for k in sorted(byst)]
    draws = boot(strata)
    N = len(pp)
    metrics = ["r", "h", "h_fail", "acc", "clean_exact", "robust_exact", "sens"]
    bad = []
    n_checked = 0

    def samp(cond, m):
        tot = 0
        for pids, idx in zip(strata, draws):
            v = np.array([pp[p]["metrics"][cond][m] for p in pids], float)
            tot = tot + v[idx].sum(axis=1)
        return tot / N

    def close(x, y):
        return abs(x - y) <= 1e-9

    for cond, md in report["conds"].items():
        for m in metrics:
            mean = sum(pp[p]["metrics"][cond][m] for p in pp) / N
            s = samp(cond, m)
            lo, hi = np.percentile(s, 2.5), np.percentile(s, 97.5)
            n_checked += 1
            if not (close(mean, md[m]["mean"]) and close(lo, md[m]["lo95"]) and close(hi, md[m]["hi95"])):
                bad.append(("cond", cond, m, mean, md[m]))
    for key, dd in report["diffs"].items():
        ab, m = key.split(":")
        x, y = ab.split("-")
        s = samp(x, m) - samp(y, m)
        mean = sum(pp[p]["metrics"][x][m] - pp[p]["metrics"][y][m] for p in pp) / N
        al = (1 - dd["level"]) / 2 * 100
        n_checked += 1
        if not (close(mean, dd["mean"]) and close(np.percentile(s, al), dd["lo"]) and close(np.percentile(s, 100 - al), dd["hi"])):
            bad.append(("diff", key, mean, dd))
    # format 상태별 환자·조건 개수 (valid/invalid)와 report의 valid 집계도 재계산
    n_valid = sum(v is not None for v in parsed.values())
    if report.get("n_valid_requests_nonoracle") is not None:
        n_nonO_valid = sum(v is not None for (pid, c), v in parsed.items() if not c.startswith("O_"))
        n_checked += 1
        if n_nonO_valid != report["n_valid_requests_nonoracle"]:
            bad.append(("n_valid", n_nonO_valid, report["n_valid_requests_nonoracle"]))
    res = dict(stage=a.stage, n_checked=n_checked, mismatches=bad, passed=(not bad), n_records=len(recs), n_valid_parse=n_valid,
               source_digests=dict(report=sha_file(a.report), requests=sha_file(req_path), manifest=sha_file(f"results/iter_047/data/manifest_{a.stage}.json"),
                                   protocol=sha_file(a.protocol),
                                   worker_files={f: sha_file(os.path.join(a.out_dir, f)) for f in sorted(os.listdir(a.out_dir)) if f.startswith("gen_worker") and f.endswith(".jsonl")}))
    tmp = a.out + ".tmp"
    json.dump(res, open(tmp, "w"), indent=1, default=str)
    os.replace(tmp, a.out)
    print("PASS" if res["passed"] else "FAIL", n_checked, "checks;", len(bad), "mismatches")
    sys.exit(0 if res["passed"] else 1)


if __name__ == "__main__":
    main()
