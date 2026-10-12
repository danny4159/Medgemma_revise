"""iter_114 분석 코드 fixture 검사 (CPU). 합성 입력만 사용. 결과: results/iter_114/tests/fixtures_core.json (all_pass)."""
import itertools
import json
import os
import random
import sys
import tempfile
from pathlib import Path

import nr113_core as B
import nr114_core as C
import nr114_run as R

RES = []


def check(name, cond, detail=None):
    RES.append({"name": name, "pass": bool(cond), "detail": detail})


def ent(key, patient, D, P, Bv, e, eh=None):
    return {"item_key": key, "patient": patient, "tk": B.tie_key(key), "D": D, "P": P, "B": Bv, "e": e, "eh": eh, "annot": B.annot_status(e, eh)}


def led(key, patient, M, scores, Cb, P, GT, ALT=None, **kw):
    d = {"item_key": key, "PatientID": patient, "M": M, "M_scores": scores, "C": Cb, "P": P, "GT": GT, "ALT": ALT or []}
    d.update(kw)
    return d


def main():
    # 1) 위험 값: 빈 출력 규칙(두 빈 / 한쪽 빈 / 빈 M 의 confidence)
    check("risk_both_empty_0", B.risk_d([], []) == 0.0)
    check("risk_one_empty_1", B.risk_d([[0, 0, .5, .5]], []) == 1.0 and B.risk_d([], [[0, 0, .5, .5]]) == 1.0)
    check("risk_conf_empty_M_is_1", B.risk_b([]) == 1.0 and abs(B.risk_b([0.9, 0.85]) - 0.15) < 1e-12)
    check("error_empty_M", B.is_error([], [[0, 0, .5, .5]]) == 1)
    # 2) 동률 규칙: 위험 같으면 해시 오름차순, 복제 순번 보조
    es = [ent(f"k{i}", f"p{i}", 0.5, 0.5, 0.5, i % 2) for i in range(8)]
    sel, K = B.select(es, "D")
    order = sorted(range(8), key=lambda i: B.tie_key(f"k{i}"))
    check("tie_hash_order", K == 2 and sel == set(order[:2]))
    check("tie_replicate_index_breaks", B.tie_key("kx", 0) < B.tie_key("kx", 1))
    # 3) 세 순위 포착과 ΔA, ΔB 산술
    es = [ent("a", "p1", .9, .1, .1, 1), ent("b", "p2", .1, .9, .1, 1), ent("c", "p3", .2, .8, .95, 1), ent("d", "p4", .05, .05, .05, 0)]
    dA, dB, cap, sel, K = C.deltas(es)
    check("deltas_toy", K == 1 and cap == {"B": 1, "D": 1, "P": 1} and dA == 0 and dB == 0)
    es2 = [ent("a", "p1", .9, .1, .1, 1), ent("b", "p2", .1, .9, .2, 0), ent("c", "p3", .2, .3, .95, 1), ent("d", "p4", .05, .05, .05, 0),
           ent("e", "p5", .4, .4, .3, 0), ent("f", "p6", .3, .2, .1, 0), ent("g", "p7", .2, .2, .3, 0), ent("h", "p8", .1, .1, .1, 0)]
    dA, dB, cap, sel, K = C.deltas(es2)
    check("deltas_toy2", K == 2 and cap["D"] == 1 and cap["B"] == 1 and cap["P"] == 0 and dA == 0 and dB == 1, {"cap": cap})
    # 4) 보수적 범위를 전수 열거와 대조(무작위 소형)
    rng = random.Random(7)
    ok_all = True
    for t in range(60):
        n = rng.randint(5, 9)
        vals = [0.0, 0.5, 1.0, 0.25]
        e = [ent(f"t{t}_{i}", f"p{i % 4}", rng.choice(vals), rng.choice(vals), rng.choice(vals), rng.randint(0, 1), rng.choice([None, 0, 1])) for i in range(n)]
        und = [x["annot"].startswith("undetermined") for x in e]
        K = B.k_of(n)

        def tsets(f):
            v = sorted((x[f] for x in e), reverse=True)
            rk = v[K - 1]
            forced = [i for i, x in enumerate(e) if x[f] > rk]
            tied = [i for i, x in enumerate(e) if x[f] == rk]
            return [set(forced) | set(c) for c in itertools.combinations(tied, K - len(forced))]
        for fy in ("B", "P"):
            br = C.bounds_pair(e, "D", fy, und)
            sxs, sys_ = tsets("D"), tsets(fy)
            unds = [i for i in range(n) if und[i]]
            det = [i for i in range(n) if not und[i]]
            lo, hi = 99, -99
            for sx in sxs:
                for sy in sys_:
                    base = sum(e[i]["e"] * ((i in sx) - (i in sy)) for i in det)
                    lo = min(lo, base + sum(min(0, (i in sx) - (i in sy)) for i in unds))
                    hi = max(hi, base + sum(max(0, (i in sx) - (i in sy)) for i in unds))
            tv = [sum(e[i]["e"] * ((i in sx) - (i in sy)) for i in range(n)) for sx in sxs for sy in sys_]
            ok_all &= [lo, hi] == list(br["tie_and_annot"]) and [min(tv), max(tv)] == list(br["tie_only"])
    check("bounds_vs_bruteforce_60_random", ok_all)
    # 5) 두 empty / 한쪽 empty / no_box 연결 (ledger → entry)
    L = [led("k1", "p1", [], [], [], [], [[.1, .1, .5, .5]]), led("k2", "p2", [[.1, .1, .5, .5]], [.9], [], [[.1, .1, .5, .5]], [[.1, .1, .5, .5]]),
         led("k3", "p3", [[.1, .1, .5, .5]], [.8], [[.1, .1, .5, .5]], [], [[.6, .6, .9, .9]]),
         led("k4", "p4", [[.1, .1, .5, .5]], [.95], [[.1, .1, .5, .5]], [[.1, .1, .5, .5]], [[.1, .1, .5, .5]], excluded_from_ranking="cure_truncated")]
    en, ex = C.build_entries(L)
    byk = {x["item_key"]: x for x in en}
    check("entry_both_empty_risk0_conf1_error", byk["k1"]["D"] == 0.0 and byk["k1"]["P"] == 0.0 and byk["k1"]["B"] == 1.0 and byk["k1"]["e"] == 1)
    check("entry_cure_empty_one_sided", byk["k2"]["D"] == 1.0 and byk["k2"]["P"] == 0.0 and byk["k2"]["e"] == 0)
    check("entry_mspc_empty_one_sided", byk["k3"]["P"] == 1.0 and byk["k3"]["D"] == 0.0 and byk["k3"]["e"] == 1)
    check("cure_invalid_common_exclusion", [x["item_key"] for x in ex] == ["k4"] and "k4" not in byk)
    # 6) MSPC 기술 결함 검출
    d0 = {"boxes_orig_xyxy": [[.1, .1, .5, .5]], "scores": [.9]}
    check("mspc_defects_clean", C.mspc_defects(d0) == [])
    check("mspc_defect_nan", "mspc_invalid_box" in C.mspc_defects({"boxes_orig_xyxy": [[float("nan"), .1, .5, .5]], "scores": [.9]}))
    check("mspc_defect_range", "mspc_invalid_box" in C.mspc_defects({"boxes_orig_xyxy": [[.1, .1, 1.2, .5]], "scores": [.9]}))
    check("mspc_defect_inverted", "mspc_invalid_box" in C.mspc_defects({"boxes_orig_xyxy": [[.5, .1, .1, .5]], "scores": [.9]}))
    check("mspc_defect_score_below_thr", "mspc_score_below_thr" in C.mspc_defects({"boxes_orig_xyxy": [[.1, .1, .5, .5]], "scores": [.5]}))
    check("mspc_defect_length", C.mspc_defects({"boxes_orig_xyxy": [[.1, .1, .5, .5]], "scores": []}) == ["mspc_scores_length"])
    check("mg_target_defect_out_of_range_box", C.mg_target_defects({"boxes_orig_xyxy": [[.4, -0.0088, .55, 1.078]], "scores": [.9]}) == ["mg_A_invalid_box"])
    check("mg_target_clean_and_empty_ok", C.mg_target_defects({"boxes_orig_xyxy": [[.1, .1, .5, .5]], "scores": [.9]}) == [] and C.mg_target_defects({"boxes_orig_xyxy": [], "scores": []}) == [])
    check("mg_target_score_below_thr", C.mg_target_defects({"boxes_orig_xyxy": [[.1, .1, .5, .5]], "scores": [.7]}) == ["mg_A_score_below_thr"])
    check("mspc_empty_is_valid_not_hidden_defect", C.mspc_defects({"boxes_orig_xyxy": [], "scores": []}) == [])
    # 7) 환자 복제: bootstrap 복제 항목이 서로 다른 동률 순번을 갖고 환자 단위 재표집(작은 입력, 결정성)
    es3 = [ent(f"z{i}", f"p{i // 2}", .5, .5, .5, i % 2) for i in range(8)]
    b1, b2 = C.bootstrap(es3, 200, 5), C.bootstrap(es3, 200, 5)
    check("bootstrap_deterministic", b1 == b2 and all(x[2] % 2 == 0 for x in b1))
    check("bootstrap_N_varies_with_patient_sizes", len({x[2] for x in C.bootstrap([ent("a", "p1", .1, .1, .1, 0), ent("b", "p1", .2, .2, .2, 1), ent("c", "p2", .3, .3, .3, 1)], 100, 3)}) > 1)
    # 8) 확대 규칙
    def mk(a_lo, a_hi, b_lo, b_hi):
        return {"bootstrap": {"A": {"ci_9875": [a_lo, a_hi], "half_width": (a_hi - a_lo) / 2}, "B": {"ci_9875": [b_lo, b_hi], "half_width": (b_hi - b_lo) / 2}}}
    check("expand_wide_and_upper_ge_005", C.expansion_decision(mk(-.1, .08, -.2, .0), 33)["expand"])
    check("no_expand_upper_below_005", not C.expansion_decision(mk(-.2, .04, -.2, .03), 33)["expand"])
    check("no_expand_narrow_half_width", not C.expansion_decision(mk(.02, .10, .0, .01), 33)["expand"])
    check("expand_B_only_even_if_A_not", C.expansion_decision(mk(-.2, .01, -.1, .09), 33)["expand"])
    check("no_expand_without_remaining", not C.expansion_decision(mk(-.1, .08, -.2, .0), 0)["expand"])
    check("small_negative_point_still_expands_if_upper_ok", C.expansion_decision(mk(-.15, .06, -.15, .0), 10)["expand"])
    # 9) 최종 판정
    def rep(dA, dB, ciA, ciB, tA, tB, loA=0, loB=0):
        r = {"dA": dA, "dB": dB, "bounds_A": {"tie_and_annot": [tA, tA + 3]}, "bounds_B": {"tie_and_annot": [tB, tB + 3]},
             "bootstrap": {"A": {"ci_9875": ciA}, "B": {"ci_9875": ciB}},
             "leave_one_patient_out": {"A": {"n_negative": loA}, "B": {"n_negative": loB}}}
        r["positive_checks"] = {"A": C.positive_checks(r, "A"), "B": C.positive_checks(r, "B")}
        return r
    j = C.judge(rep(.08, .07, [.01, .15], [.005, .14], 1, 1), True)
    check("judge_A_and_B_positive", j["summary"] == "A_and_B_positive")
    j = C.judge(rep(.08, .0, [.01, .15], [-.1, .03], 1, -2), True)
    check("judge_A_only_positive", j["summary"] == "A_only_positive" and j["general_control_sufficient"])
    j = C.judge(rep(.06, .0, [-.03, .15], [-.1, .03], 1, -1), True)
    check("judge_general_sufficient_when_B_upper_lt_005_and_cost_true", j["summary"] == "general_control_sufficient_hold_specific_investment")
    j = C.judge(rep(.06, .0, [-.03, .15], [-.1, .03], 1, -1), None)
    check("judge_cost_unresolved_not_sufficient", j["summary"] == "inconclusive_or_excluded" and j["general_control_cost_unresolved"])
    j = C.judge(rep(-.06, -.05, [-.12, -.01], [-.1, -.001], -3, -3), True)
    check("judge_excluded_opposite_direction", j["A"]["status"] == "min_useful_effect_excluded_opposite_direction")
    j = C.judge(rep(.06, .06, [.01, .15], [.01, .15], 1, 1, loA=1), True)
    check("judge_positive_requires_no_negative_loo", j["A"]["status"] == "inconclusive")
    j = C.judge(rep(.06, .06, [.01, .15], [.01, .15], 0, 1), True)
    check("judge_positive_requires_conservative_range_gt0", j["A"]["status"] == "inconclusive")
    # 10) seal: stale PASS / 미검증 거부
    with tempfile.TemporaryDirectory(dir=str(R.R114 / "tests")) as td:
        td = Path(td)
        an = td / "analysis"
        (an / "result_init").mkdir(parents=True)
        f = an / "result_init" / "report.json"
        f.write_text("{}")
        vp = an / "verify_init.json"
        vp.write_text(json.dumps({"all_pass": True, "verified_files": {"result_init/report.json": R.sha(f)}}))
        old_an, old_vp = R.AN, R.verify_protocol
        R.AN = an
        R.verify_protocol = lambda: None
        try:
            R.cmd_seal()
            ok_seal = (an / "completion.json").exists()
            (an / "completion.json").unlink()
            f.write_text('{"x": 1}')
            try:
                R.cmd_seal()
                stale_rejected = False
            except SystemExit:
                stale_rejected = True
            f.write_text("{}")
            vp.write_text(json.dumps({"all_pass": False, "verified_files": {"result_init/report.json": R.sha(f)}}))
            try:
                R.cmd_seal()
                fail_rejected = False
            except SystemExit:
                fail_rejected = True
            vp.unlink()
            try:
                R.cmd_seal()
                missing_rejected = False
            except SystemExit:
                missing_rejected = True
        finally:
            R.AN, R.verify_protocol = old_an, old_vp
    check("seal_ok_when_verified_digests_match", ok_seal)
    check("seal_rejects_stale_pass", stale_rejected)
    check("seal_rejects_failed_verification", fail_rejected)
    check("seal_rejects_missing_verification", missing_rejected)
    # 11) 기존 결과 디렉터리 입력 digest 불일치 거부 / 덮어쓰기 거부
    with tempfile.TemporaryDirectory(dir=str(R.R114 / "tests")) as td:
        p = Path(td) / "x.json"
        R.wjson(p, {"a": 1})
        try:
            R.wjson(p, {"a": 2})
            over = False
        except SystemExit:
            over = True
        check("wjson_refuses_overwrite", over and json.loads(p.read_text()) == {"a": 1})
    allp = all(r["pass"] for r in RES)
    out = R.R114 / ("tests/" + (sys.argv[1] if len(sys.argv) > 1 else "fixtures_core.json"))
    with out.open("x") as f:
        json.dump({"all_pass": allp, "n": len(RES), "n_pass": sum(r["pass"] for r in RES), "results": RES}, f, indent=1)
    print(json.dumps({"all_pass": allp, "n": len(RES), "failed": [r["name"] for r in RES if not r["pass"]]}))
    sys.exit(0 if allp else 1)


if __name__ == "__main__":
    main()
