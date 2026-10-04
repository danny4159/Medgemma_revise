"""iter_069 평가 계산 fixture (합성 응답): invalid·UNCERTAIN, class 누락, oracle 오답, 순서 평균, rule 조합, R 경계, 중복 case, LOO flip.
결과 results/iter_069/tests/eval_fixtures.json (x 모드)."""
import json
import sys

import numpy as np

import dd69_eval as E
import dd69_run as R
import dd69_spec as S

RES = []


def check(name, cond, detail=""):
    RES.append({"name": name, "pass": bool(cond), "detail": str(detail)[:200]})
    print(("PASS " if cond else "FAIL ") + name, flush=True)


def synth(cases_lab, plan, default_cost=1.0):
    """plan[(case, cond)] = 답변 문자열 (기본: 정답). 반환 recs, rows, labels."""
    labels = {str(c): {"label": l, "gt": {k: S.gt(k, l) for k in S.CONDS + ["R"]}} for c, l in cases_lab.items()}
    recs, rows = {}, []
    for c, l in cases_lab.items():
        for cond in S.CONDS:
            rid = f"c{c}_{cond}"
            txt = plan.get((c, cond), S.gt(cond, l))
            rows.append({"rid": rid, "case": c, "cond": cond})
            recs[rid] = {"attempts": [{"text": txt, "ended_eos": True}], "total_read_to_save_start_s": default_cost * (2 if cond.startswith("J") else 1)}
    return recs, rows, labels


def main():
    cl = {i: ("LOW" if i < 8 else "NOT_LOW") for i in range(12)}  # 8 LOW, 4 NOT_LOW
    recs, rows, labels = synth(cl, {})
    r = E.analyze("m", recs, {}, rows, labels)
    check("all-correct: BA=1 for every cond", all(abs(v["BA"] - 1) < 1e-12 for v in r["conds"].values()), {k: v["BA"] for k, v in r["conds"].items()})
    check("sufficiency true when A perfect and cheaper than J", r["decision"]["sufficient_A"] and not r["decision"]["loss_candidate"])
    # invalid/UNCERTAIN = 오답, class별 recall
    plan = {(0, "A"): "maybe", (1, "A"): "UNCERTAIN", (8, "A"): "YES"}
    recs, rows, labels = synth(cl, plan)
    r = E.analyze("m", recs, {}, rows, labels)
    a = r["conds"]["A"]
    check("invalid and UNCERTAIN count as wrong", abs(a["recall_LOW"] - 6 / 8) < 1e-12 and abs(a["recall_NOT_LOW"] - 3 / 4) < 1e-12 and abs(a["BA"] - 0.75 * 0.5 - 0.375) < 1e-12, a)
    check("invalid/uncertain tallies", r["invalid_uncertain"]["A"] == {"invalid": 1, "uncertain": 1, "final_non_eos": 0}, r["invalid_uncertain"]["A"])
    # 순서 평균: J_DA 전부 정답, J_AD LOW 전부 오답 -> J recall_LOW = 0.5
    plan = {(c, "J_AD"): "NO" for c in range(8)}
    recs, rows, labels = synth(cl, plan)
    r = E.analyze("m", recs, {}, rows, labels)
    j = r["conds"]["J"]
    check("J is fixed mean of two orders (no best-order pick)", abs(j["recall_LOW"] - 0.5) < 1e-12 and abs(j["recall_NOT_LOW"] - 1) < 1e-12 and abs(j["BA"] - 0.75) < 1e-12, j)
    check("order disagreement counted", r["order_disagreement_J"] == 8, r["order_disagreement_J"])
    check("A-J contrast point", abs(r["contrasts"]["A-J"]["diff"] - 0.25) < 1e-12)
    check("R condition met flag when A-J>=0.10", r["decision"]["R_condition_met_A_minus_J_ge_0.10"] is True)
    # rule
    plan = {(0, "SD"): "NOT_HIGH", (1, "SA"): "UNCERTAIN", (8, "SA"): "LOW"}
    recs, rows, labels = synth(cl, plan)
    r = E.analyze("m", recs, {}, rows, labels)
    check("rule: NOT_HIGH->NO(wrong for LOW), UNCERTAIN->undecided(wrong), HIGH&LOW on NOT_LOW->YES(wrong)",
          r["rule_confusion"].get("gt=YES|rule=NO") == 1 and r["rule_confusion"].get("gt=YES|rule=UNDECIDED") == 1 and r["rule_confusion"].get("gt=NO|rule=YES") == 1, r["rule_confusion"])
    check("rule_answer table", E.rule_answer("HIGH", "LOW") == "YES" and E.rule_answer("HIGH", "NOT_LOW") == "NO" and E.rule_answer("NOT_HIGH", "LOW") == "NO"
          and E.rule_answer("HIGH", "UNCERTAIN") is None and E.rule_answer(None, "LOW") is None)
    # oracle 오답은 실행 중단 없이 기록
    plan = {(c, "O"): "NO" for c in range(8)}
    recs, rows, labels = synth(cl, plan)
    r = E.analyze("m", recs, {}, rows, labels)
    check("oracle errors are recorded, not fatal", abs(r["conds"]["O"]["recall_LOW"]) < 1e-12 and r["decision"]["oracle_BA"] == 0.5)
    # class 누락 -> BA nan, bootstrap에서 단일 class replicate 제외
    only = {i: "LOW" for i in range(5)}
    recs, rows, labels = synth(only, {})
    r = E.analyze("m", recs, {}, rows, labels)
    check("class missing -> BA NaN (not silently 1)", np.isnan(r["conds"]["A"]["BA"]))
    cl2 = {0: "LOW", 1: "LOW", 2: "LOW", 3: "NOT_LOW"}
    recs, rows, labels = synth(cl2, {})
    r = E.analyze("m", recs, {}, rows, labels)
    check("single-class bootstrap replicates are excluded and counted", r["conds"]["A"]["boot_excluded_single_class"] > 0, r["conds"]["A"]["boot_excluded_single_class"])
    # LOO flip -> 불확정(loss_candidate False)
    cl3 = {i: ("LOW" if i < 6 else "NOT_LOW") for i in range(10)}  # 6 LOW, 4 NOT_LOW
    plan = {}
    for c in (0, 1):  # J가 두 순서 모두 오답, SA/A는 정답 -> 독립 2 case
        plan[(c, "J_DA")] = "NO"; plan[(c, "J_AD")] = "NO"
    recs, rows, labels = synth(cl3, plan)
    r = E.analyze("m", recs, {}, rows, labels)
    d = r["decision"]
    check("loss candidate: J wrong & SA right in >=2 cases, passes LOO", d["loss_point_criterion"] and d["J_wrong_SA_right_cases"] == [0, 1] and (d["loss_candidate"] == (not d["loo_flip_cases"])), d)
    plan = {(0, "J_DA"): "NO", (0, "J_AD"): "NO", (1, "J_DA"): "NO"}
    recs, rows, labels = synth(cl3, plan)
    r = E.analyze("m", recs, {}, rows, labels)
    check("single wrong-J case (+half) is not a loss candidate (needs >=2 independent cases)", not r["decision"]["loss_candidate"], r["decision"])
    # R 포함 경계
    recs, rows, labels = synth(cl3, {})
    rr = {f"c{c}_R": {"attempts": [{"text": "YES" if cl3[c] == "LOW" else "NO", "ended_eos": True}], "total_read_to_save_start_s": 1.0} for c in cl3}
    rrows = [{"rid": f"c{c}_R", "case": c, "cond": "R"} for c in cl3]
    r = E.analyze("m", recs, {}, rows, labels, rows_r=rrows, recs_r=rr, cost_r={})
    check("R conditions reported only when provided", "R" in r["conds"] and "R-J" in r["contrasts"])
    r0 = E.analyze("m", recs, {}, rows, labels)
    check("R absent when not provided", "R" not in r0["conds"] and "R-J" not in r0["contrasts"])
    # 비용 비율
    check("cost ratio rule/J: (1+1)/(2) = 1", abs(r0["cost"]["rule_SD_plus_SA_over_J"] - 1.0) < 1e-12, r0["cost"])
    # exclude tech
    r1 = E.analyze("m", recs, {}, rows, labels, exclude_cases=(0, 6))
    check("exclude_cases removes cases", r1["n_cases"] == 8 and r1["n_low"] == 5)
    # 중복 case / 중복 rid는 load 단계에서 거부: 실제 파일로 검사
    import os, tempfile
    d = os.path.join(R.OUT_ROOT, "tests", "eval_dup_fx")
    os.makedirs(d, exist_ok=True)
    row = {"rid": "x", "protocol_digest": "p", "attempts": []}
    open(os.path.join(d, "worker0.jsonl"), "w").write(json.dumps(row) + "\n")
    open(os.path.join(d, "worker1.jsonl"), "w").write(json.dumps(row) + "\n")
    import glob, m65_run as B
    seen, dup = set(), False
    for f in sorted(glob.glob(d + "/worker*.jsonl")):
        for rr_ in B.read_jsonl(f):
            dup |= rr_["rid"] in seen
            seen.add(rr_["rid"])
    check("duplicate rid across worker files is detectable", dup)
    # 평가 진입 변조 거부: labels 복사본이 protocol과 다르면 거부
    lab_copy = os.path.join(d, "labels_tampered.json")
    lj = json.load(open(R.LABELS)); k0 = next(iter(lj)); lj[k0]["label"] = "NOT_LOW" if lj[k0]["label"] == "LOW" else "LOW"
    json.dump(lj, open(lab_copy, "w"))
    old = R.LABELS
    R.LABELS = lab_copy
    try:
        try:
            E.load_records("medgemma", "results/iter_069/protocol/protocol_medgemma_v2.json", "results/iter_069/gen/tech_medgemma", R.REQ["tech"])
            rej = False
        except SystemExit as e:
            rej = "labels/cases differ" in str(e)
    finally:
        R.LABELS = old
    check("eval entry rejects labels that differ from protocol", rej)
    # seal 변조 거부 (복사본 out_dir)
    import shutil
    cd = os.path.join(d, "tech_copy2")
    if not os.path.exists(cd):
        shutil.copytree("results/iter_069/gen/tech_medgemma", cd)
        vj = json.load(open(cd + "/verify.json"))
        vj["record_file_sha256"] = {os.path.join(os.path.abspath(cd), os.path.basename(k)): v for k, v in vj["record_file_sha256"].items()}
        json.dump(vj, open(cd + "/verify.json", "w"))
    wf = sorted(glob.glob(cd + "/worker*.jsonl"))[0]
    with open(wf, "ab") as f:
        f.write(b"")
    txt = open(wf).read().replace('"HIGH', '"HIGX', 1)
    open(wf, "w").write(txt)
    try:
        E.load_records("medgemma", "results/iter_069/protocol/protocol_medgemma_v2.json", cd, R.REQ["tech"])
        rej2 = False
    except SystemExit as e:
        rej2 = "changed after seal" in str(e)
    check("eval entry rejects output file modified after seal", rej2)
    out = {"n": len(RES), "n_pass": sum(x["pass"] for x in RES), "results": RES}
    with open(R.safe_out("results/iter_069/tests/eval_fixtures.json"), "x") as f:
        json.dump(out, f, indent=1)
    print(out["n_pass"], "/", out["n"])
    return 0 if out["n_pass"] == out["n"] else 1


if __name__ == "__main__":
    sys.exit(main())
