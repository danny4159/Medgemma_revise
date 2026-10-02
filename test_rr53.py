"""iter_053 CPU fixture: prompt 정합(T=R2, BT=BJ, oracle O2 수정), 요청 누출·집합, parser/지표 손계산, macro·bootstrap·verifier 일치(합성 실행),
판정 규칙, gate 변조(stale·wrong stage·run=false), iter_047 D8 회귀(점수·oracle 29/32), 자료 gate 거부 사례.
python test_rr53.py results/iter_053/tests/fixtures_rr53.json   (기존 파일을 덮어쓰지 않는다)
"""
import copy
import glob
import json
import os
import shutil
import sys
import traceback

import numpy as np

import pg43_run as PR
import rr53_build as B
import rr53_data as D
import rr53_decide as DEC
import rr53_eval as E
import rr53_run as RUN
import rr53_spec as S
import rr53_verify as V

OUT = "results/iter_053"
RESULTS = []
TMP = f"{OUT}/tests/tmp_fixture_work"


def check(name, cond, detail=None):
    RESULTS.append(dict(name=name, passed=bool(cond), detail=detail))
    print(("PASS " if cond else "FAIL ") + name, flush=True)


def raw(a, b, eos="<end_of_turn>"):
    return '{"qA": "%s", "qB": "%s"}%s' % (a, b, eos)


def fake_manifest(strata_sizes, with_pc=False):
    rows = []
    n = 0
    for code, k in strata_sizes.items():
        st = S.code_states(code)
        for _ in range(k):
            n += 1
            rows.append(dict(set="E", truth_code=code, PatientID=f"P{n:03d}", ImageID=f"P{n:03d}", StudyID=f"P{n:03d}/s",
                             q={i: dict(finding=S.FINDING_PAIR[i], state=st[k2]) for k2, i in enumerate(S.IDS)},
                             image_meta=dict(path="x.jpg", file_sha256="0" * 64, u8_pixel_sha256="1" * 64, h=1, w=1)))
    return dict(rows=rows)


def fake_requests_and_recs(man, policy, stage="E", with_oracle=False, pc_rows=None):
    """policy(cond, patient_row, draft_code, ids) -> raw suffix string. returns (reqs, recs)."""
    reqs, recs = [], []

    def add(m, cond, targets, modality, draft, set_name):
        rid = S.sha(f"{m['PatientID']}|{cond}")[:32]
        reqs.append(dict(request_id=rid, patient=m["PatientID"], cond=cond, targets=list(targets), modality=modality, set=set_name, kind="rr53"))
        recs.append(dict(request_id=rid, suffix_text_raw=policy(cond, m, draft, targets), ended_eos=True, final_cap=1000))

    for m in man["rows"]:
        for d in S.DRAFT_CODES:
            for c in ("R1", "R2", "T"):
                add(m, f"{c}_d{d}", S.IDS, "image" if c != "T" else "text", d, stage)
        add(m, "BJ", S.IDS, "image", None, stage)
        add(m, "BT", S.IDS, "text", None, stage)
        for i in S.IDS:
            add(m, f"BI_{i}", [i], "image", None, stage)
        if with_oracle:
            for d in S.DRAFT_CODES:
                add(m, f"O_d{d}", S.IDS, "image", d, stage)
                add(m, f"OT_d{d}", S.IDS, "text", d, stage)
    for m in (pc_rows or []):
        for d in S.DRAFT_CODES:
            add(m, f"O_d{d}", S.IDS, "image", d, "pc_D8")
            add(m, f"OT_d{d}", S.IDS, "text", d, "pc_D8")
    return reqs, recs


def make_policy(seed):
    rng = np.random.default_rng(seed)
    table = {}

    def policy(cond, m, d, targets):
        truth = [m["q"][i]["state"] for i in S.IDS]
        key = (m["PatientID"], cond)
        if key not in table:
            base = cond.split("_")[0]
            r = rng.random()
            if base in ("O", "OT"):
                a, b = truth
            elif base == "R1":
                a, b = [(t if rng.random() < 0.6 else s) for t, s in zip(truth, S.code_states(d))]
            elif base == "R2":
                a, b = [(s if rng.random() < 0.7 else t) for t, s in zip(truth, S.code_states(d))]
            elif base == "T":
                a, b = S.code_states(d)
            else:
                a, b = [(t if rng.random() < 0.85 else S.flip(t)) for t in truth]
            if base == "BI":
                out = '{"%s": "%s"}<end_of_turn>' % (targets[0], dict(qA=a, qB=b)[targets[0]])
            elif r < 0.04 and base not in ("O", "OT"):
                out = "not json at all<end_of_turn>"
            elif r < 0.07 and base not in ("O", "OT"):
                a = "uncertain"
                out = raw(a, b)
            else:
                out = raw(a, b)
            table[key] = out
        return table[key]
    return policy


def test_prompts_and_requests():
    pair = S.FINDING_PAIR
    for d in S.DRAFT_CODES:
        it = S.draft_text(pair, d)
        check(f"T == R2 byte-identical d{d}", S.prompt_T(it) == S.prompt_R2(it))
    check("BT == BJ byte-identical", S.prompt_BT(pair) == S.prompt_BJ(pair))
    it = S.draft_text(pair, "10")
    truth = [("qA", "present"), ("qB", "absent")]
    o2, o1 = S.prompt_O2(it, truth), S.B.prompt_O(it, truth)
    check("O2 = old O + authority sentence only", o2.replace(" " + S.AUTH_SENTENCE, "") == o1 and S.AUTH_SENTENCE in o2 and S.AUTH_SENTENCE not in o1)
    check("authority sentence exact text", S.AUTH_SENTENCE == "For this consistency check, the verified final status is authoritative. Copy it exactly; do not infer a different status from the draft or image.")
    # 실제 요청 파일
    for st, n in (("P", 48), ("D", 448), ("E", 768), ("F", 1680)):
        got = RUN.check_requests(st, f"{OUT}/requests/requests_{st}.jsonl")
        check(f"requests_{st} equals manifest reconstruction ({n})", len(got) == n)
    for st in ("D", "E", "F"):
        rows = [json.loads(l) for l in open(f"{OUT}/requests/requests_{st}.jsonl")]
        leak = False
        by = {}
        for r in rows:
            if r["cond"].startswith(("O_", "OT_")):
                continue
            by.setdefault((r["cond"], r["prompt_sha256"]), set()).add(r["patient"])
        # 비 oracle prompt는 정답 상태가 아니라 초안·finding에만 의존: 같은 (cond) 이면 prompt 종류가 초안(4)·BI(2)로만 다양
        kinds = {}
        for (c, ps), _ in by.items():
            kinds.setdefault(c, set()).add(ps)
        ok = all(len(v) == 1 for c, v in kinds.items())
        check(f"{st}: non-oracle prompt per condition is a single text (no truth/corruption leak)", ok, {c: len(v) for c, v in kinds.items()})
        ids = [r["request_id"] for r in rows]
        check(f"{st}: unique request ids", len(ids) == len(set(ids)))
        tx = [r for r in rows if r["modality"] == "text"]
        check(f"{st}: text rows carry no image fields", all(r["image"] is None and r["input_pixel_sha256"] is None for r in tx))
        base = {}
        for r in rows:
            base.setdefault(r["patient"], {})[r["cond"]] = r
        same = all(v["T_d" + d]["prompt"] == v["R2_d" + d]["prompt"] and v["BT"]["prompt"] == v["BJ"]["prompt"] for p, v in base.items() for d in S.DRAFT_CODES if "R2_d" + d in v)
        check(f"{st}: per patient T prompt==R2 prompt and BT==BJ in the request file", same)
    rows = [json.loads(l) for l in open(f"{OUT}/requests/requests_D.jsonl")]
    oo = [r for r in rows if r["cond"].startswith(("O_", "OT_"))]
    check("D: 192 oracle requests (image/text pairs share identical prompt)", len(oo) == 192 and all(
        {r["prompt"] for r in oo if r["patient"] == p and r["cond"][-3:] == d} .__len__() == 1 for p in {r["patient"] for r in oo} for d in ("d00", "d01", "d10", "d11")))
    check("D: oracle prompts contain authority sentence", all(S.AUTH_SENTENCE in r["prompt"] for r in oo))
    mf = json.load(open(f"{OUT}/data/manifest_D.json"))
    check("D: 16 CheXpert + 8 PadChest D8 patients", len(mf["rows"]) == 16 and len(mf["pc_oracle_rows"]) == 8)
    pm = {s: sum(1 for r in json.load(open(f"{OUT}/data/manifest_F.json"))["rows"] if r["truth_code"] == s) for s in S.DRAFT_CODES}
    check("F stratum sizes 56/17/20/12", pm == {"00": 56, "01": 17, "10": 20, "11": 12}, pm)


def test_parser_metrics():
    ok = lambda t, e=True, ids=S.IDS: S.parse_state(t, e, ids)["status"]
    check("parser: strict ok / trailing prose / dup / wrong keys / bad value / truncated",
          ok(raw("present", "absent")) == "ok" and ok(raw("present", "absent", "") + " x") == "not_json" and ok('{"qA":"present","qA":"absent","qB":"absent"}') == "dup_key"
          and ok('{"qA":"present"}') == "wrong_keys" and ok(raw("Present", "absent")) == "bad_value" and ok(raw("present", "absent"), False) == "truncated")
    # 지표 손계산: truth=(present, absent) 코드 '10'. 완벽 교정자
    truth = ["present", "absent"]

    def byc(fn):
        out = {}
        for d in S.DRAFT_CODES:
            for c in ("R1", "R2", "T"):
                out[f"{c}_d{d}"] = S.parse_state(fn(d), True, S.IDS)
        out["BJ"] = S.parse_state(raw(*truth), True, S.IDS)
        out["BT"] = S.parse_state(raw("absent", "absent"), True, S.IDS)
        for i in S.IDS:
            out[f"BI_{i}"] = S.parse_state('{"%s": "%s"}<end_of_turn>' % (i, dict(qA=truth[0], qB=truth[1])[i]), True, [i])
        return out
    perfect = E.patient_metrics(truth, "R2", byc(lambda d: raw(*truth)))[0]
    check("metrics: perfect corrector r=1 h=0 h_fail=0 acc=1 robust=1 sens=0", perfect == dict(r=1.0, h=0.0, h_fail=0.0, acc=1.0, clean_exact=1.0, robust_exact=1.0, sens=0.0), perfect)
    copier = E.patient_metrics(truth, "R2", byc(lambda d: raw(*S.code_states(d))))[0]
    check("metrics: copier r=0 h=0 h_fail=0 acc=.5 robust=0", copier["r"] == 0 and copier["h"] == 0 and copier["h_fail"] == 0 and copier["acc"] == 0.5 and copier["robust_exact"] == 0, copier)
    flipper = E.patient_metrics(truth, "R2", byc(lambda d: raw(*[S.flip(x) for x in S.code_states(d)])))[0]
    check("metrics: flipper r=1.0 on wrong drafts? (flip of wrong=truth) h=1 h_fail=1", flipper["r"] == 1.0 and flipper["h"] == 1.0 and flipper["h_fail"] == 1.0 and flipper["acc"] == 0.5, flipper)
    unc = E.patient_metrics(truth, "R2", byc(lambda d: raw("uncertain", "uncertain")))[0]
    check("metrics: all uncertain r=0 h=0 h_fail=1 acc=0", unc["r"] == 0 and unc["h"] == 0 and unc["h_fail"] == 1.0 and unc["acc"] == 0, unc)
    inv = E.patient_metrics(truth, "R2", byc(lambda d: "garbage"))[0]
    check("metrics: invalid counted as failure not correct", inv["r"] == 0 and inv["h_fail"] == 1.0 and inv["acc"] == 0, inv)
    bt = E.patient_metrics(truth, "BT", byc(lambda d: raw(*truth)))[0]
    check("metrics: BT uses BT request (not BJ)", bt["acc"] == 0.5 + 0.0 and bt["r"] == 0.5 or bt["acc"] < 1.0, bt)
    bi = E.patient_metrics(truth, "BI", byc(lambda d: raw(*truth)))[0]
    check("metrics: BI uses two single-ID requests", bi["acc"] == 1.0)


def synthetic_report(seed=3, sizes=None, with_oracle=False, stage="E"):
    sizes = sizes or {"00": 4, "01": 3, "10": 5, "11": 2}
    man = fake_manifest(sizes)
    pc = None
    if with_oracle:
        pc = []
        for k, code in enumerate(S.DRAFT_CODES):
            st = S.code_states(code)
            pc.append(dict(set="pc_D8", truth_code=code, PatientID=f"PC{k}", q={i: dict(finding="cardiomegaly" if i == "qA" else "effusion", state=st[j]) for j, i in enumerate(S.IDS)}))
        man["pc_oracle_rows"] = pc
    reqs, recs = fake_requests_and_recs(man, make_policy(seed), stage=stage, with_oracle=with_oracle, pc_rows=pc)
    return man, reqs, recs


def test_eval_verify_agree():
    for stage, wo in (("E", False), ("D", True)):
        man, reqs, recs = synthetic_report(with_oracle=wo, stage=stage)
        rep = E.make_report(stage, man, reqs, recs)
        rep["source"] = {}
        labels = {m["PatientID"]: dict(cardiomegaly=m["q"]["qA"]["state"], pleural_effusion=m["q"]["qB"]["state"]) for m in man["rows"]}
        bad, n, _ = V.compare(stage, reqs, recs, man, rep, labels)
        check(f"verifier == production on synthetic stage {stage} (all conds/metrics/diffs/simult/common-valid/oracle)", not bad and n > 80, dict(n=n, bad=bad[:3]))
        # 변조: report 수치 하나 변경 -> verifier 검출
        r2 = copy.deepcopy(rep)
        r2["conds"]["R2"]["r"]["mean"] += 0.01
        b2, _, _ = V.compare(stage, reqs, recs, man, r2, labels)
        check(f"verifier detects altered cond mean ({stage})", len(b2) >= 1)
        r3 = copy.deepcopy(rep)
        r3["diffs"]["BJ-R2:r"]["lo"] += 0.01
        check(f"verifier detects altered diff CI ({stage})", len(V.compare(stage, reqs, recs, man, r3, labels)[0]) >= 1)
        r4 = copy.deepcopy(rep)
        r4["common_valid"]["BJ-R2"]["r_diff"] += 0.01
        check(f"verifier detects altered common-valid ({stage})", len(V.compare(stage, reqs, recs, man, r4, labels)[0]) >= 1)
        # 라벨 변조: manifest 정답이 labels.json과 다르면 검출
        lab2 = copy.deepcopy(labels)
        k0 = sorted(lab2)[0]
        lab2[k0]["cardiomegaly"] = S.flip(lab2[k0]["cardiomegaly"])
        check(f"verifier detects manifest truth != labels ({stage})", len(V.compare(stage, reqs, recs, man, rep, lab2)[0]) >= 1)
        # record 훼손(원시 출력 변경) -> report와 불일치
        recs2 = copy.deepcopy(recs)
        for r in recs2:
            if r["request_id"] in {q["request_id"] for q in reqs if q["cond"] == "BJ"}:
                r["suffix_text_raw"] = raw("uncertain", "uncertain")
        check(f"verifier detects altered raw output ({stage})", len(V.compare(stage, reqs, recs2, man, rep, labels)[0]) >= 1)
        if wo:
            oc = rep["oracle"]
            check("oracle report counts for synthetic D (chexpert/padchest × image/text)", set(oc) == {"chexpert_D16:image", "chexpert_D16:text", "padchest_D8:image", "padchest_D8:text"}
                  and oc["chexpert_D16:image"]["n"] == 4 * 14 and oc["padchest_D8:text"]["n"] == 16 and all(v["ok"] == v["n"] for v in oc.values()), {k: (v["n"], v["ok"]) for k, v in oc.items()})
    # macro: 층별 크기가 다를 때 macro != natural
    man, reqs, recs = synthetic_report(seed=4, sizes={"00": 6, "01": 2, "10": 3, "11": 1})
    rep = E.make_report("E", man, reqs, recs)
    d = rep["conds"]["R2"]["r"]
    st = {}
    for pid, v in rep["per_patient_metrics"].items():
        st.setdefault(v["stratum"], []).append(v["metrics"]["R2"]["r"])
    check("macro mean = mean of stratum means (hand)", abs(d["mean"] - np.mean([np.mean(v) for v in st.values()])) < 1e-12 and abs(d["natural_mean"] - np.mean([x for v in st.values() for x in v])) < 1e-12
          and abs(d["mean"] - d["natural_mean"]) > 1e-6)


def test_decisions():
    man, reqs, recs = synthetic_report(seed=5, sizes={"00": 12, "01": 12, "10": 12, "11": 12})
    rep = E.make_report("E", man, reqs, recs)
    ver = dict(passed=True)
    rep["n_non_eos_final"] = 0
    sizes = {"00": 56, "01": 17, "10": 20, "11": 12}
    # 합성 report를 직접 구성해 규칙 경계를 시험한다
    def fake_rep(r_vals, hf_vals, acc_diff, rd, hd, valid=0.99, cvdir=True):
        c = {}
        for k in ("R1", "R2", "BJ", "BI", "T", "BT", "K"):
            c[k] = {m: dict(mean=0.5, lo95=0.4, hi95=0.6, simult_lo=0.3, simult_hi=0.7, degenerate_exact=None) for m in ("r", "h_fail", "h", "acc")}
        for k in ("R1", "R2", "BJ", "BI"):
            c[k]["r"]["mean"] = r_vals[k]
            c[k]["h_fail"]["mean"] = hf_vals[k]
        df = {"BJ-BT:acc": dict(mean=acc_diff[0], lo=acc_diff[1], hi=acc_diff[2]), "BJ-R2:r": dict(mean=rd[0], lo=rd[1], hi=rd[2]), "BJ-R2:h_fail": dict(mean=hd[0], lo=hd[1], hi=hd[2])}
        pp = {}
        rng = np.random.default_rng(1)
        n = 0
        for code in S.DRAFT_CODES:
            for _ in range(12):
                n += 1
                pp[f"p{n}"] = dict(stratum=code, truth=None, metrics={"BJ": dict(r=0.7 + 0.05 * float(rng.random()), h_fail=0.25 * float(rng.random() < 0.1) + 0.12),
                                                                          "R2": dict(r=0.5 + 0.05 * float(rng.random()), h_fail=0.02)})
        return dict(stage="E", conds=c, diffs=df, per_patient_metrics=pp, n_non_eos_final=0, valid_rate_by_cond={k: valid for k in DEC.CONDS_VALID},
                    common_valid={"BJ-R2": dict(r_diff=0.1 if cvdir else -0.1, hfail_diff=0.05)})
    r_ok = dict(R1=0.5, R2=0.5, BJ=0.7, BI=0.6)
    hf_ok = dict(R1=0.1, R2=0.02, BJ=0.12, BI=0.1)
    e = DEC.decide_e(fake_rep(r_ok, hf_ok, (0.2, 0.1, 0.3), (0.2, 0.1, 0.3), (0.1, 0.05, 0.15)), ver, sizes, True)
    check("decide_e: all entry conditions -> run", e["run"] is True and e["outcome"] == "enter_F", e["checks"].get("expected_half_width"))
    e2 = DEC.decide_e(fake_rep(r_ok, hf_ok, (0.05, -0.02, 0.1), (0.2, 0.1, 0.3), (0.1, 0.05, 0.15)), ver, sizes, True)
    check("decide_e: BJ-BT acc point <0.10 -> hold", e2["run"] is False)
    e3 = DEC.decide_e(fake_rep(r_ok, hf_ok, (0.2, -0.01, 0.3), (0.2, 0.1, 0.3), (0.1, 0.05, 0.15)), ver, sizes, True)
    check("decide_e: acc CI lower bound <=0 -> hold", e3["run"] is False)
    e4 = DEC.decide_e(fake_rep(r_ok, hf_ok, (0.2, 0.1, 0.3), (0.1, 0.0, 0.2), (0.1, 0.05, 0.15)), ver, sizes, True)
    check("decide_e: r diff <0.15 -> hold", e4["run"] is False)
    e5 = DEC.decide_e(fake_rep(r_ok, hf_ok, (0.2, 0.1, 0.3), (0.2, 0.1, 0.3), (0.03, 0.0, 0.1)), ver, sizes, True)
    check("decide_e: h_fail diff <0.05 -> hold", e5["run"] is False)
    e6 = DEC.decide_e(fake_rep(r_ok, hf_ok, (0.2, 0.1, 0.3), (0.2, 0.1, 0.3), (0.1, 0.05, 0.15), cvdir=False), ver, sizes, True)
    check("decide_e: common-valid opposite direction -> hold", e6["run"] is False)
    e7 = DEC.decide_e(fake_rep(dict(R1=0.9, R2=0.5, BJ=0.7, BI=0.6), dict(R1=0.0, R2=0.02, BJ=0.12, BI=0.1), (0.2, 0.1, 0.3), (0.2, 0.1, 0.3), (0.1, 0.05, 0.15)), ver, sizes, True)
    check("decide_e: R1 point r>=.8 and h_fail<=.05 -> simple alternative point-sufficient hold", e7["run"] is False)
    e8 = DEC.decide_e(fake_rep(r_ok, hf_ok, (0.2, 0.1, 0.3), (0.2, 0.1, 0.3), (0.1, 0.05, 0.15), valid=0.9), ver, sizes, True)
    check("decide_e: valid<95% -> invalid_run, no F", e8["run"] is False and e8["outcome"] == "invalid_run")
    e9 = DEC.decide_e(fake_rep(r_ok, hf_ok, (0.2, 0.1, 0.3), (0.2, 0.1, 0.3), (0.1, 0.05, 0.15)), dict(passed=False), sizes, True)
    check("decide_e: verifier fail -> invalid_run", e9["run"] is False and e9["outcome"] == "invalid_run")
    e10 = DEC.decide_e(fake_rep(r_ok, hf_ok, (0.2, 0.1, 0.3), (0.2, 0.1, 0.3), (0.1, 0.05, 0.15)), ver, sizes, False)
    check("decide_e: F independence not ok -> no F", e10["run"] is False)
    rz = fake_rep(r_ok, hf_ok, (0.2, 0.1, 0.3), (0.2, 0.1, 0.3), (0.1, 0.05, 0.15))
    for v in rz["per_patient_metrics"].values():
        v["metrics"]["BJ"]["h_fail"] = 0.0
        v["metrics"]["R2"]["h_fail"] = 0.0
    e11 = DEC.decide_e(rz, ver, sizes, True)
    check("decide_e: zero within-stratum variance -> no precision evidence, hold F", e11["run"] is False and "zero_within_stratum_variance_precision_not_supported_hold_F" in e11["flags"])
    # 예상 반폭 손계산
    pp = {}
    vals = {"00": [0.0, 1.0, 0.5], "01": [0.2, 0.4], "10": [0.0, 0.0, 1.0], "11": [0.5, 0.5, 1.0, 0.0]}
    for code, vs in vals.items():
        for k, v in enumerate(vs):
            pp[f"{code}{k}"] = dict(stratum=code, metrics={"BJ": dict(r=v, h_fail=v), "R2": dict(r=0.0, h_fail=0.0)})
    hw, s2 = DEC.expected_half_width(pp, sizes, "r")
    hand = 2.242 * np.sqrt(sum(np.var(vals[k], ddof=1) / sizes[k] for k in vals) / 16)
    check("expected half-width formula = 2.242*sqrt(sum(s2_h/n_h)/16) (hand)", abs(hw - hand) < 1e-12, dict(hw=hw, hand=float(hand)))
    check("F effective n (equal variance) ~ 76.19", abs(1 / sum((1 / 4) ** 2 / n for n in sizes.values()) - 76.19) < 0.01)
    # F 판정 경계 (simult 구간 사용)
    def f_rep(simple_ok=False, pos=True, cv=True):
        c = {}
        for k in ("R1", "R2", "BJ", "BI"):
            c[k] = dict(r=dict(mean=0.5, simult_lo=0.3, simult_hi=0.6, degenerate_exact=None), h_fail=dict(mean=0.1, simult_lo=0.07, simult_hi=0.2, degenerate_exact=None))
        if simple_ok:
            c["R2"] = dict(r=dict(mean=0.95, simult_lo=0.85, simult_hi=1.0, degenerate_exact=None), h_fail=dict(mean=0.0, simult_lo=0.0, simult_hi=0.04, degenerate_exact=None))
        df = {"BJ-BT:acc": dict(mean=0.2, lo=0.1, hi=0.3), "BJ-R2:r": dict(mean=0.2, lo=0.1, hi=0.3), "BJ-R2:h_fail": dict(mean=0.1, lo=0.03, hi=0.2)}
        if not pos:
            df["BJ-R2:r"] = dict(mean=0.02, lo=-0.05, hi=0.1)
        return dict(stage="F", conds=c, diffs=df, n_non_eos_final=0, valid_rate_by_cond={k: 0.99 for k in DEC.CONDS_VALID}, common_valid={"BJ-R2": dict(r_diff=0.1 if cv else -0.1, hfail_diff=0.05)})
    check("decide_f: positive when all criteria (simult bounds) hold", DEC.decide_f(f_rep(), ver)["outcome"] == "positive_min_method_review")
    check("decide_f: simple alternative sufficient overrides", DEC.decide_f(f_rep(simple_ok=True), ver)["outcome"] == "simple_alternative_sufficient")
    check("decide_f: CI upper below threshold -> negative", DEC.decide_f(f_rep(pos=False), ver)["outcome"] == "negative_no_tradeoff")
    check("decide_f: common-valid opposite -> not positive", DEC.decide_f(f_rep(cv=False), ver)["outcome"] != "positive_min_method_review")
    check("decide_f: verifier failure -> invalid_run", DEC.decide_f(f_rep(), dict(passed=False))["outcome"] == "invalid_run")
    # 퇴화 경계 사용 (모든 환자 사건 0)
    c0 = dict(r=dict(mean=1.0, simult_lo=1.0, simult_hi=1.0, degenerate_exact=dict(any_event_patient_fraction_upper=0.1)),
              h_fail=dict(mean=0.0, simult_lo=0.0, simult_hi=0.0, degenerate_exact=dict(any_event_patient_fraction_upper=0.04)))
    check("sufficient(): degenerate exact bound used instead of [1,1]/[0,0] bootstrap", DEC.sufficient(c0)[0] is True and DEC.sufficient(c0)[1]["r_lower"] == 0.9)
    c1 = dict(r=dict(mean=1.0, simult_lo=1.0, simult_hi=1.0, degenerate_exact=dict(any_event_patient_fraction_upper=0.3)),
              h_fail=dict(mean=0.0, simult_lo=0.0, simult_hi=0.0, degenerate_exact=dict(any_event_patient_fraction_upper=0.04)))
    check("sufficient(): small-n degenerate result cannot be called sufficient", DEC.sufficient(c1)[0] is False)
    # 퇴화 경계 계산 (합성 report)
    allperfect = lambda cond, m, d, t: raw(*[x for x in [dict(qA=None)]]) if False else None
    sizes2 = {"00": 4, "01": 4, "10": 4, "11": 4}
    man2 = fake_manifest(sizes2)

    def perfect_policy(cond, m, d, targets):
        truth = dict(zip(S.IDS, [m["q"][i]["state"] for i in S.IDS]))
        if cond.startswith("BI"):
            return '{"%s": "%s"}<end_of_turn>' % (targets[0], truth[targets[0]])
        return raw(truth["qA"], truth["qB"])
    rq, rc = fake_requests_and_recs(man2, perfect_policy)
    rp = E.make_report("E", man2, rq, rc)
    ub = float(np.mean([1 - (0.05 / (4 * 8)) ** (1 / 4)] * 4))
    de = rp["conds"]["R2"]["h_fail"]["degenerate_exact"]
    check("degenerate exact binomial bound for all-zero events (hand: 1-alpha^(1/n), alpha=.05/(4*8))", de is not None and abs(de["any_event_patient_fraction_upper"] - ub) < 1e-12, de)
    check("degenerate flagged in diff for identical conditions", rp["diffs"]["BJ-R2:r"]["degenerate"] is True)


def test_gate_stale():
    os.makedirs(TMP, exist_ok=True)
    f_in = os.path.join(TMP, "gate_input_a.json")
    json.dump({"x": 1}, open(f_in, "w"))
    chk = D.file_sha(f"{OUT}/data/data_check.json")
    gate = os.path.join(TMP, "gate_ok.json")
    json.dump(dict(run=True, stage="D", data_check_sha256=chk, inputs=dict(a=dict(path=f_in, sha256=D.file_sha(f_in)))), open(gate, "w"))

    def rej(fn):
        try:
            fn()
            return False
        except PR.RunError:
            return True
    check("gate: valid decision accepted for its stage", RUN.check_gate_inputs(gate, "D")["run"] is True)
    check("gate: wrong stage rejected (E protocol given D-stage? F given D decision)", rej(lambda: RUN.check_gate_inputs(gate, "E")))
    g2 = os.path.join(TMP, "gate_false.json")
    json.dump(dict(run=False, stage="D", data_check_sha256=chk, inputs=dict(a=dict(path=f_in, sha256=D.file_sha(f_in)))), open(g2, "w"))
    check("gate: run=false rejected", rej(lambda: RUN.check_gate_inputs(g2, "D")))
    g3 = os.path.join(TMP, "gate_bare.json")
    json.dump(dict(run=True, stage="D", data_check_sha256=chk), open(g3, "w"))
    check("gate: bare run=true without input digests rejected", rej(lambda: RUN.check_gate_inputs(g3, "D")))
    g4 = os.path.join(TMP, "gate_baddc.json")
    json.dump(dict(run=True, stage="D", data_check_sha256="0" * 64, inputs=dict(a=dict(path=f_in, sha256=D.file_sha(f_in)))), open(g4, "w"))
    check("gate: stale data_check digest rejected", rej(lambda: RUN.check_gate_inputs(g4, "D")))
    json.dump({"x": 2}, open(f_in, "w"))
    check("gate: stale (changed) input file rejected", rej(lambda: RUN.check_gate_inputs(gate, "D")))


def test_regression_iter047():
    """iter_047 D8(구 prompt) 원시 출력에 새 평가 코드를 적용해 보고된 점수와 oracle 29/32를 재현한다. 구 결과는 읽기만 한다."""
    d = "results/iter_047/gen/D8_v2_4w"
    recs = []
    for f in sorted(glob.glob(d + "/gen_worker*.jsonl")):
        recs += PR.read_records(f)
    rows = [json.loads(l) for l in open("results/iter_047/requests/requests_D8.jsonl")]
    man = json.load(open("results/iter_047/data/manifest_D8.json"))
    old = json.load(open("results/iter_047/eval/D8_report.json"))
    by = {r["request_id"]: r for r in recs}
    parsed = {}
    for q in rows:
        r = by[q["request_id"]]
        p = S.parse_state(r["suffix_text_raw"], r["ended_eos"], q["targets"])
        parsed.setdefault(q["patient"], {})[q["cond"]] = p
    maxdiff = 0.0
    n = 0
    for m in man["rows"]:
        truth = [m["q"][i]["state"] for i in S.IDS]
        for c in ("K", "R1", "R2", "T", "BJ", "BI"):
            met = E.patient_metrics(truth, c, parsed[m["PatientID"]])[0]
            for k, v in met.items():
                maxdiff = max(maxdiff, abs(v - old["per_patient_metrics"][m["PatientID"]]["metrics"][c][k]))
                n += 1
    check("regression: iter_047 D8 per-patient metrics reproduced by iter_053 code", maxdiff == 0 and n == 8 * 6 * 7, dict(maxdiff=maxdiff, n=n))
    ok = bad = 0
    for m in man["rows"]:
        truth = {i: m["q"][i]["state"] for i in S.IDS}
        fp = {i: m["q"][i]["finding"] for i in S.IDS}
        for d in S.DRAFT_CODES:
            p = parsed[m["PatientID"]][f"O_d{d}"]
            fin = {i: S.final_state(p, i) for i in S.IDS}
            if fin == truth and S.render_final(fp, fin) == [S.FINDINGS[fp[i]][truth[i]] for i in S.IDS]:
                ok += 1
            else:
                bad += 1
    check("regression: iter_047 oracle 29/32 reproduced (old O prompt; errors kept as content errors)", ok == 29 and bad == 3, dict(ok=ok, bad=bad))


def test_data_gate_rejects():
    """자료 gate 거부: HF Path 중복, 잘못된 digest, 분할 변조가 GateError."""
    import pandas as pd
    hf = pd.read_parquet(D.CD.HF_PARQUET)
    dup = pd.concat([hf, hf.iloc[:1]], ignore_index=True)
    check("data gate input: duplicated HF Path would be detected by uniqueness rule", len(dup["Path"]) != len(set(dup["Path"])) and len(hf["Path"]) == len(set(hf["Path"])) == 234)
    orig = D.HF_SHA256
    D.HF_SHA256 = "0" * 64
    try:
        D.checked_sources()
        rejected = False
    except D.GateError:
        rejected = True
    finally:
        D.HF_SHA256 = orig
    check("data gate: wrong pinned parquet digest rejected", rejected)
    orig_csv = D.CSV_SHA256
    D.CSV_SHA256 = "0" * 64
    try:
        D.checked_sources()
        rejected = False
    except D.GateError:
        rejected = True
    finally:
        D.CSV_SHA256 = orig_csv
    check("data gate: wrong pinned csv digest rejected", rejected)
    chk = json.load(open(f"{OUT}/data/data_check.json"))
    check("data_check: passed, F independence ok, intersections all 0, legacy exact dup none", chk["passed"] and chk["f_independence_ok"]
          and all(v == 0 for d in chk["d_e_f_intersections"].values() for v in d.values()) and not chk["legacy_exact_duplicate"]["exact_file_or_pixel_matches"])
    sets = json.load(open("results/iter_018/manifests/sets.json"))
    m = {k: {p for v in sets[k].values() for p in v} for k in sets}
    check("splits D16/E48/F sizes 16/48/105 and disjoint", (len(m["D16"]), len(m["E48"]), len(m["F"])) == (16, 48, 105) and not (m["D16"] & m["E48"]) and not (m["D16"] & m["F"]) and not (m["E48"] & m["F"]))
    # split_patients 변조 입력 (중복 환자 ID) 거부
    try:
        D.CX.split_patients({"absent_absent": ["a", "a"]})
        rej = False
    except ValueError:
        rej = True
    check("split_patients rejects duplicate patient id", rej)


def test_run_rejects():
    """rr53_run 고유 거부: 요청 파일 변조/누락(manifest 재구성 불일치), 잘못된 stage의 gate 요구, 보호된 stage protocol의 gate 부재."""
    os.makedirs(TMP, exist_ok=True)
    src = f"{OUT}/requests/requests_E.jsonl"
    rows = [json.loads(l) for l in open(src)]

    def rej(fn):
        try:
            fn()
            return False
        except PR.RunError:
            return True
    alt = os.path.join(TMP, "requests_E_dropped.jsonl")
    open(alt, "w").write("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows[1:]))
    check("run: request file with a dropped row rejected (count/manifest reconstruction)", rej(lambda: RUN.check_requests("E", alt)))
    alt2 = os.path.join(TMP, "requests_E_prompt.jsonl")
    r2 = [dict(r) for r in rows]
    r2[0]["prompt"] = r2[0]["prompt"] + " "
    r2[0]["prompt_sha256"] = S.sha(r2[0]["prompt"])
    open(alt2, "w").write("".join(json.dumps(r, sort_keys=True) + "\n" for r in r2))
    check("run: request with altered prompt (consistent hash) rejected by reconstruction", rej(lambda: RUN.check_requests("E", alt2)))
    alt3 = os.path.join(TMP, "requests_E_modality.jsonl")
    r3 = [dict(r) for r in rows]
    k = [i for i, r in enumerate(r3) if r["modality"] == "text"][0]
    r3[k]["modality"] = "image"
    open(alt3, "w").write("".join(json.dumps(r, sort_keys=True) + "\n" for r in r3))
    check("run: text row relabeled image rejected", rej(lambda: RUN.check_requests("E", alt3)))
    check("run: E protocol without D gate refused", rej(lambda: RUN.make("E", os.path.join(TMP, "p_nogate.json"), None)))
    check("run: F protocol without E decision refused", rej(lambda: RUN.make("F", os.path.join(TMP, "p_nogate_f.json"), None)))
    fin = os.path.join(TMP, "gate_input_b.json")
    json.dump({"y": 1}, open(fin, "w"))
    dg = os.path.join(TMP, "gate_D_valid.json")
    json.dump(dict(run=True, stage="D", data_check_sha256=D.file_sha(f"{OUT}/data/data_check.json"), inputs=dict(b=dict(path=fin, sha256=D.file_sha(fin)))), open(dg, "w"))
    check("run: control — that D gate is itself valid for stage D", RUN.check_gate_inputs(dg, "D")["run"] is True)
    check("run: F protocol given a D-stage gate refused (wrong stage)", rej(lambda: RUN.make("F", os.path.join(TMP, "p_wrongstage.json"), dg)))


def main():
    out = sys.argv[1]
    if os.path.exists(out):
        sys.exit(f"refuse to overwrite {out}")
    if os.path.exists(TMP):
        shutil.rmtree(TMP) if False else None
    for fn in (test_prompts_and_requests, test_parser_metrics, test_eval_verify_agree, test_decisions, test_gate_stale, test_run_rejects, test_regression_iter047, test_data_gate_rejects):
        try:
            fn()
        except Exception:
            check(f"{fn.__name__} raised", False, traceback.format_exc()[-600:])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(dict(n=len(RESULTS), passed=sum(r["passed"] for r in RESULTS), results=RESULTS), open(out + ".tmp", "w"), indent=1, default=str)
    os.replace(out + ".tmp", out)
    print(f"{sum(r['passed'] for r in RESULTS)}/{len(RESULTS)} passed")
    sys.exit(0 if all(r["passed"] for r in RESULTS) else 1)


if __name__ == "__main__":
    main()
