"""iter_099 회귀 검사: 실제 실패 입력(중복 readings, 존재하지 않는 인용, fact ID 오류, 덮어쓰기)에서 잠금이 만들어지지 않는지 확인한다."""
import copy
import json
import sys
from pathlib import Path

import report98_data as D
import report99_lock as L

T = D.ROOT / "results" / "iter_099" / "tests"
checks = []


def check(name, ok, detail=""):
    checks.append({"name": name, "pass": bool(ok), "detail": detail})


def files(d):
    return sorted(p.name for p in Path(d).iterdir() if not p.name.startswith("lock_errors"))


def errs(d):
    return sorted(p.name for p in Path(d).iterdir() if p.name.startswith("lock_errors"))


def main():
    T.mkdir(parents=True, exist_ok=True)
    # 1) 중복 readings: 같은 내용의 완전 중복 행도 거부
    lines = open(D.READINGS).read().splitlines()
    dup = T / "readings_dup.jsonl"
    with open(dup, "x") as f:
        f.write("\n".join(lines + [lines[3]]) + "\n")
    try:
        D.load_readings(dup)
        check("load_readings_rejects_exact_duplicate", False)
    except ValueError:
        check("load_readings_rejects_exact_duplicate", True)
    out1 = T / "work_dup"
    rc, pr = L.build(out1, readings_path=dup)
    check("dup_readings_no_lock", rc == 1 and files(out1) == [] and len(errs(out1)) == 1 and pr[0]["problem"] == "readings_duplicate",
          json.dumps({"rc": rc, "files": files(out1), "errs": errs(out1)}))

    # 2) 원문에 없는 영역 설명 인용
    bad = copy.deepcopy(L.LEDGER)
    bad[85]["Q"][0]["desc_quote"] = "this sentence does not exist in any region description"
    out2 = T / "work_badquote"
    rc, pr = L.build(out2, ledger=bad)
    check("bad_desc_quote_no_lock", rc == 1 and files(out2) == [] and any(p["problem"] == "desc_quote" for p in pr),
          json.dumps({"rc": rc, "files": files(out2)}))

    # 3) 존재하지 않는 reference 인용과 fact ID
    bad = copy.deepcopy(L.LEDGER)
    bad[3]["P"][0]["ref_quote"] = "nonexistent reference phrase"
    bad[8]["P"][0]["fact"] = "F9"
    out3 = T / "work_badref"
    rc, pr = L.build(out3, ledger=bad)
    kinds = sorted(p["problem"] for p in pr)
    check("bad_ref_and_fact_no_lock", rc == 1 and files(out3) == [] and "ref_quote" in kinds and "fact_id_missing" in kinds,
          json.dumps({"rc": rc, "kinds": kinds}))

    # 4) 초안 인용 오류
    bad = copy.deepcopy(L.LEDGER)
    bad[25]["P"][0]["draft_quote"] = "Left lung cavity"
    out4 = T / "work_baddraft"
    rc, pr = L.build(out4, ledger=bad)
    check("bad_draft_quote_no_lock", rc == 1 and files(out4) == [] and any(p["problem"] == "draft_quote" for p in pr))

    # 5) 정상 입력은 생성되고 두 번째 실행은 덮어쓰지 않는다
    out5 = T / "work_ok"
    rc, _ = L.build(out5)
    h1 = {n: L.sha_file(out5 / n) for n in files(out5)}
    try:
        L.build(out5)
        second = "no_error"
    except FileExistsError:
        second = "FileExistsError"
    h2 = {n: L.sha_file(out5 / n) for n in files(out5)}
    check("ok_build_then_no_overwrite", rc == 0 and second == "FileExistsError" and h1 == h2 and len(h1) == 2,
          json.dumps({"files": sorted(h1), "second": second}))
    leftovers = [p.name for p in out5.iterdir() if p.name.startswith(".tmp_")]
    check("no_temp_leftover", not leftovers, json.dumps(leftovers))

    # 6) 정상 결과의 산술 재계산(ledger에서 직접): strict/민감도 N
    d = json.load(open(out5 / "eligibility_decision.json"))
    led = json.load(open(out5 / "atom_ledger.json"))["atoms"]
    p_ok = {int(k) for k, v in led.items() if any(a["status"] == "clear" for a in v["P"])}
    q_ok = {int(k) for k, v in led.items() if any(a["status"] == "clear" and a["kind"] == "finding" for a in v["Q"])}
    check("strict_N_recomputed", sorted(p_ok & q_ok) == d["N_recovery_cohort"] and d["run_generation"] == bool(d["N_recovery_cohort"]),
          json.dumps({"N": d["N_recovery_cohort"]}))
    q_pc = {int(k) for k, v in led.items() if any(a["status"] in ("clear", "partial") and a["kind"] == "finding" for a in v["Q"])}
    check("sensitivity_Q_partial_recomputed", sorted(p_ok & q_pc) == d["scenarios_N"]["Q_partial_as_clear"])

    res = {"n_checks": len(checks), "n_pass": sum(c["pass"] for c in checks), "checks": checks}
    with open(T / "regress_report99.json", "x") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps({"n_checks": res["n_checks"], "n_pass": res["n_pass"],
                      "failed": [c["name"] for c in checks if not c["pass"]]}, ensure_ascii=False))
    return 0 if res["n_pass"] == res["n_checks"] else 1


if __name__ == "__main__":
    sys.exit(main())
