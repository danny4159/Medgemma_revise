"""iter_100 회귀 검사: clear 속성 포함, unknown/partial/temporal 제외 유지, atom 고유 ID·출처 연결, 원문 없는 quote 거부, 잠금 보호.

iter_099의 test_report99.py는 finding-only 조건을 복제해 원 계획 준수를 검증하지 못했다. 여기서는 규칙을 ledger에서 직접 독립 계산한다.
중복 readings 거부는 수정 없는 report98_data.py의 iter_099 증거를 hash 확인 후 재사용하되, 이 호출에서 한 번 더 실제 실행한다.
"""
import copy
import json
import sys
from pathlib import Path

import report98_data as D
import report100_lock as L

T = D.ROOT / "results" / "iter_100" / "tests"
checks = []


def check(name, ok, detail=""):
    checks.append(dict(name=name, passed=bool(ok), detail=detail))


def files(d):
    return sorted(p.name for p in Path(d).iterdir() if not p.name.startswith("lock_errors"))


def main():
    T.mkdir(parents=True, exist_ok=True)
    # 0) report98_data.py가 iter_099 검증 당시와 동일한지(hash)
    old = json.load(open(L.DECISION99))["provenance_sha256"]["report98_data.py"]
    check("report98_data_unchanged_since_iter099", old == L.sha_file(D.ROOT / "report98_data.py"), old)

    # 1) 독립 계산: ledger에서 직접 N을 구해 대조(finding-only는 []이고 attr 포함 시 [53])
    led = L.build_ledger()
    p_ok = set(pi for pi, e in led.items() if any(a["status"] == "clear" for a in e["P"]))
    q_f = set(pi for pi, e in led.items() if any(a["status"] == "clear" and a["kind"] == "finding" for a in e["Q"]))
    q_fa = set(pi for pi, e in led.items() if any(a["status"] == "clear" and a["kind"] in ("finding", "attr") for a in e["Q"]))
    check("finding_only_cohort_empty_and_attr_cohort_is_P053", sorted(p_ok & q_f) == [] and sorted(p_ok & q_fa) == [53] and L.cohort(led) == [53],
          json.dumps(dict(finding_only=sorted(p_ok & q_f), with_attr=sorted(p_ok & q_fa))))

    # 2) unknown/partial/covered_by_draft/temporal은 clear 속성이 있어도 자동 포함되지 않는다
    for status in ("unknown", "partial", "covered_by_draft"):
        bad = copy.deepcopy(led)
        bad[53]["Q"][0]["status"] = status
        check("attr_status_%s_excluded" % status, L.cohort(bad) == [])
    bad = copy.deepcopy(led)
    bad[53]["Q"][0]["kind"] = "temporal"
    check("attr_kind_temporal_excluded", L.cohort(bad) == [])

    # 3) 존재와 크기 atom은 별도 고유 ID
    ids = D.abnormal_ids()
    am = json.load(open(D.REF_AMEND))["patients"]
    R = D.load_readings()
    by = dict((am[i]["patient_index"], i) for i in ids)
    dec53 = L.decorate(53, led[53], D.package(by[53], R), am[by[53]])
    pid, qid = dec53["P"][0]["id"], dec53["Q"][0]["id"]
    check("existence_and_size_have_distinct_ids", pid != qid and dec53["P"][0]["fact"] == dec53["Q"][0]["fact"] == "F3", "%s %s" % (pid, qid))
    g = dec53["Q"][0]["groups"]
    check("size_atom_source_linked_to_D08_D11", sorted(x["gid"] for x in g) == ["D08", "D11"]
          and sorted(r for x in g for r in x["regions"]) == ["left costophrenic angle", "left lower lung zone"], json.dumps(g))
    check("all_ledger_ids_unique", True if len(set(a["id"] for pi in led for k in ("P", "Q")
                                                    for a in L.decorate(pi, led[pi], D.package(by[pi], R), am[by[pi]])[k])) ==
          sum(len(led[pi]["P"]) + len(led[pi]["Q"]) for pi in led) else False)

    # 4) 원문 없는 quote와 중복 readings 거부, 실패 시 잠금 파일 없음
    bad = copy.deepcopy(led)
    bad[53]["Q"][0]["desc_quote"] = "this sentence does not exist in any region description"
    out = T / "work_badquote"
    rc, pr = L.build(out, ledger=bad)
    check("bad_desc_quote_no_lock", rc == 1 and files(out) == [] and any(p["problem"] == "desc_quote" for p in pr))
    lines = open(D.READINGS).read().splitlines()
    dup = T / "readings_dup.jsonl"
    if not dup.exists():
        with open(dup, "x") as f:
            f.write("\n".join(lines + [lines[3]]) + "\n")
    out = T / "work_dup"
    rc, pr = L.build(out, readings_path=dup)
    check("dup_readings_no_lock", rc == 1 and files(out) == [] and pr[0]["problem"] == "readings_duplicate")
    try:
        D.load_readings(dup)
        check("load_readings_rejects_duplicate", False)
    except ValueError:
        check("load_readings_rejects_duplicate", True)

    # 5) 정상 build와 비덮어쓰기, 결과 재계산
    out = T / "work_ok"
    rc, _ = L.build(out)
    h1 = dict((n, L.sha_file(out / n)) for n in files(out))
    try:
        L.build(out)
        second = "no_error"
    except FileExistsError:
        second = "FileExistsError"
    h2 = dict((n, L.sha_file(out / n)) for n in files(out))
    check("ok_build_no_overwrite", rc == 0 and second == "FileExistsError" and h1 == h2 and len(h1) == 3, json.dumps(sorted(h1)))
    d = json.load(open(out / "eligibility_decision.json"))
    lc = json.load(open(out / "lock_complete.json"))
    check("decision_N_controls", d["N_recovery_cohort"] == [53] and len(d["preservation_controls"]) == 1 and d["run_generation"] is True,
          json.dumps(dict(N=d["N_recovery_cohort"], controls=d["preservation_controls"], order=d["control_candidates_in_order"])))
    check("lock_complete_hashes_match", all(L.sha_file(out / n) == h for n, h in lc["files"].items()))
    # 통제 규칙 재계산: 첫 후보는 hash 최소이고 Q가 없다
    la = json.load(open(out / "atom_ledger.json"))["atoms"]
    ctl = d["preservation_controls"][0]
    check("control_has_no_Q_and_clear_P", la[str(ctl)]["Q"] == [] and any(a["status"] == "clear" for a in la[str(ctl)]["P"]))
    check("attr_checks_cover_all_P_clear", sorted(c["patient"] for c in d["attr_checks"]) == sorted(d["P_clear_patients"]))
    check("no_temp_leftover", not [p.name for p in out.iterdir() if p.name.startswith(".tmp_")])

    res = dict(n_checks=len(checks), n_pass=sum(c["passed"] for c in checks), checks=checks)
    with open(T / "regress_report100.json", "x") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(dict(n=res["n_checks"], ok=res["n_pass"], failed=[c["name"] for c in checks if not c["passed"]])))
    return 0 if res["n_pass"] == res["n_checks"] else 1


if __name__ == "__main__":
    sys.exit(main())
