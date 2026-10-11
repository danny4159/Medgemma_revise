"""iter_108 CPU fixture/회귀 검사. 결과: results/iter_108/tests/<name>.json (새 파일만, 덮어쓰기 거부)."""
import copy
import json
import math
import sys
from pathlib import Path

import numpy as np

import ev108_build as B
import ev108_data as D
import ev108_eval as E
import ev108_run as RUN
import ev108_spec as S

CHECKS = []


def check(name, cond, detail=None):
    CHECKS.append({"name": name, "pass": bool(cond), "detail": detail})


def rec(text, eos=True):
    return {"suffix_text_raw": text, "ended_eos": eos}


YES, NO = rec("Yes.\n<end_of_turn>"), rec("No<end_of_turn>")
EXP = rec("The image shows an opacity.<end_of_turn>")
TRUNC = rec("Yes", eos=False)


def synthetic(n_per_cat=10):
    """사람이 계산할 수 있는 합성 데이터: 환자·정답·조건별 답 지정."""
    pats, cats, ans = [], {}, {}
    for c in S.CATS:
        for k in range(n_per_cat):
            p = f"{c[:3]}{k}"
            pats.append(p)
            cats[p] = c
    return pats, cats, ans


def test_parse_and_crops():
    ok = lambda t: S.parse_saved_bbox(t + "<end_of_turn>", True)
    check("bbox_ok", ok('[{"box_2d": [143, 247, 586, 454], "label": "pulmonary opacity"}]') == ("ok", [[143, 247, 586, 454]]))
    check("bbox_empty", ok("[]") == ("empty", []))
    check("bbox_truncated_not_empty", S.parse_saved_bbox("[", False) == ("truncated", []))
    check("bbox_invalid_bad_order", ok('[{"box_2d": [500, 247, 100, 454], "label": "a"}]')[0] == "invalid")
    check("bbox_invalid_float", ok('[{"box_2d": [1.5, 2, 30, 40], "label": "a"}]')[0] == "invalid")
    check("bbox_invalid_not_json", ok("hello")[0] == "invalid")
    check("enclosing", S.enclosing([[10, 20, 30, 40], [5, 50, 25, 60]]) == [5, 20, 30, 60])
    check("crop_rect_floor_ceil", S.crop_rect([100, 100, 200, 300], 1000 + 24) == (math.floor(100 * 1024 / 1000), math.floor(100 * 1024 / 1000),
                                                                                  math.ceil(300 * 1024 / 1000), math.ceil(200 * 1024 / 1000)))
    check("crop_rect_clip", S.crop_rect([0, 0, 1000, 1000], 1024) == (0, 0, 1024, 1024))
    r = S.crop_rect([100, 200, 300, 500], 1024)
    h, w = r[3] - r[1], r[2] - r[0]
    cr = S.center_rect(h, w, 1024)
    check("center_same_size", (cr[2] - cr[0], cr[3] - cr[1]) == (w, h) and cr[0] == (1024 - w) // 2 and cr[1] == (1024 - h) // 2)
    canvas = (np.arange(64 * 64 * 3) % 251).astype(np.uint8).reshape(64, 64, 3)
    pad, aff = S.crop_square_padded(canvas, (10, 20, 30, 28))
    check("crop_square_value_preserving", pad.shape == (20, 20, 3) and aff == (6, 0, 20) and np.array_equal(pad[6:14, 0:20], canvas[20:28, 10:30]) and not pad[:6].any(), list(aff))


def test_eval_math():
    pats, cats, ans = synthetic(10)
    # opacity 10, normal 10, nno 10; O/A 정답: opacity yes,yes / normal no,no / nno no,yes
    right = {"O": {"opacity": YES, "normal": NO, "not_normal_no_opacity": NO}, "A": {"opacity": YES, "normal": NO, "not_normal_no_opacity": YES}}
    wrong = {"O": {"opacity": NO, "normal": YES, "not_normal_no_opacity": YES}, "A": {"opacity": NO, "normal": YES, "not_normal_no_opacity": NO}}
    for i, p in enumerate(pats):
        c = cats[p]
        for tg in S.TARGETS:
            for cond in ("F", "D", "T", "C", "L"):
                ans[(p, cond, tg)] = right[tg][c]
    # T: O에서 opacity 4명 오답->정답 이득 (D 오답으로), NNO A에서 3명 T 오답, 2명 T invalid
    op = [p for p in pats if cats[p] == "opacity"]
    for p in op[:4]:
        ans[(p, "D", "O")] = wrong["O"]["opacity"]
    nno = [p for p in pats if cats[p] == "not_normal_no_opacity"]
    for p in nno[:3]:
        ans[(p, "T", "A")] = wrong["A"]["not_normal_no_opacity"]
    for p in nno[3:5]:
        ans[(p, "T", "A")] = TRUNC
    r = E.comparisons(pats, cats, ans, "sem")
    c1 = r["comparisons"]["T_minus_D_O"]
    check("TminusD_O_diff", abs(c1["diff"] - 4 / 30) < 1e-12 and c1["changed_valid"] == 4 and c1["a_right_b_wrong_valid"] == 4, c1["diff"])
    c2 = r["comparisons"]["T_minus_D_A_nno"]
    check("TminusD_A_nno_diff_and_invalid", abs(c2["diff"] - (-5 / 10)) < 1e-12 and c2["changed_valid"] == 3 and c2["invalid_driven_changes"] == 2
          and c2["n_invalid_a"] == 2 and c2["n"] == 10, c2)
    check("format_bound", abs(c2["format_bound"][0] - (-0.5)) < 1e-12 and abs(c2["format_bound"][1] - (-0.3)) < 1e-12, c2["format_bound"])
    check("format_direction_stable_negative", c2["format_direction_stable"] is True)
    check("ci_contains_point", c1["ci95"][0] <= c1["diff"] <= c1["ci95"][1])
    # 독립 계산: bootstrap 없이 점추정·전이 수를 순수 python으로 재계산
    def ok(p, cond, tg):
        r_ = ans[(p, cond, tg)]
        st, a_ = S.sem(tg, r_["suffix_text_raw"], r_["ended_eos"])
        return int(st == "valid" and a_ == S.correct_answer(cats[p], tg))
    pt = sum(ok(p, "T", "O") - ok(p, "D", "O") for p in pats) / len(pats)
    check("independent_pointestimate", abs(pt - c1["diff"]) < 1e-12)
    # 결정적 bootstrap
    r2 = E.comparisons(pats, cats, ans, "sem")
    check("bootstrap_deterministic", r2["comparisons"]["T_minus_D_O"]["ci95"] == c1["ci95"])
    # 정확 이항 구간
    lo, hi = S.exact_binom_ci(0, 10)
    check("exact_binom_0_of_10", abs(lo) < 1e-9 and abs(hi - 0.308497) < 1e-4, [lo, hi])
    lo, hi = S.exact_binom_ci(5, 20)
    check("exact_binom_5_of_20", abs(lo - 0.0866) < 1e-3 and abs(hi - 0.4910) < 1e-3, [lo, hi])
    # 확대 분기
    n_e = {"T_minus_D_O": 120, "T_minus_D_A_nno": 40, "T_minus_C_O": 120}
    d = E.expansion_decision(r, n_e)
    check("expand_A_triggered", d["expand"] and d["endpoints"]["T_minus_D_A_nno"]["A"], {k: (v["A"], v["B"]) for k, v in d["endpoints"].items()})
    # 변화 0건: 확대 없음
    ans0 = {k: v for k, v in ans.items()}
    for p in op[:4]:
        ans0[(p, "D", "O")] = YES
    for p in nno[:5]:
        ans0[(p, "T", "A")] = YES
    r0 = E.comparisons(pats, cats, ans0, "sem")
    d0 = E.expansion_decision(r0, n_e)
    check("no_change_no_expand", not d0["expand"] and r0["comparisons"]["T_minus_D_O"]["changed_valid"] == 0)
    # invalid만으로는 A 조건 불가 (changed_valid=0)
    ans1 = dict(ans0)
    for p in op[:6]:
        ans1[(p, "T", "O")] = TRUNC
    r1 = E.comparisons(pats, cats, ans1, "sem")
    d1 = E.expansion_decision(r1, n_e)
    c = r1["comparisons"]["T_minus_D_O"]
    check("invalid_only_not_expanded", c["changed_valid"] == 0 and c["invalid_driven_changes"] == 6 and not d1["endpoints"]["T_minus_D_O"]["A"]
          and not d1["endpoints"]["T_minus_D_O"]["B"])
    # B 조건: 환자 4명 변화, CI가 0과 +10pp 포함, 예상 반폭<=15pp (n_E를 크게)
    fake = {"comparisons": {"T_minus_D_O": {"diff": 0.08, "ci95": [-0.05, 0.21], "changed_valid": 4, "n": 100},
                            "T_minus_D_A_nno": {"diff": 0.0, "ci95": [-0.3, 0.3], "changed_valid": 0, "n": 17},
                            "T_minus_C_O": {"diff": 0.0, "ci95": [-0.3, 0.3], "changed_valid": 3, "n": 100}}}
    dB = E.expansion_decision(fake, {"T_minus_D_O": 400, "T_minus_D_A_nno": 67, "T_minus_C_O": 400})
    check("expand_B_rule", dB["endpoints"]["T_minus_D_O"]["B"] and not dB["endpoints"]["T_minus_D_O"]["A"] and dB["expand"]
          and abs(dB["endpoints"]["T_minus_D_O"]["projected_halfwidth"] - 0.13 * math.sqrt(100 / 400)) < 1e-12)
    fake2 = copy.deepcopy(fake)
    fake2["comparisons"]["T_minus_D_O"]["ci95"] = [-0.10, 0.25]  # 반폭 0.175
    dB2 = E.expansion_decision(fake2, {"T_minus_D_O": 110, "T_minus_D_A_nno": 67, "T_minus_C_O": 110})
    check("expand_B_halfwidth_too_wide", not dB2["endpoints"]["T_minus_D_O"]["B"] and not dB2["expand"])


def test_policies():
    pats, cats, ans = synthetic(2)
    for p in pats:
        for tg in S.TARGETS:
            ans[(p, "F", tg)] = NO
    st = {p: "empty" for p in pats}
    nne = [p for p in pats if cats[p] == "opacity"][0]
    st[nne] = "ok"
    ans[(nne, "T", "O")] = YES
    ans[(nne, "L", "O")] = NO
    pol = E.policy_answers(nne, "ok", ans)
    check("policy_R_uses_T_for_O", pol["R"][0] is ans[(nne, "T", "O")] and pol["R"][1] is ans[(nne, "F", "A")])
    check("policy_RL_uses_L", pol["R_L"][0] is ans[(nne, "L", "O")])
    check("policy_RB_rule_yes", pol["R_B"][0]["suffix_text_raw"] == "yes")
    emp = [p for p in pats if st[p] == "empty"][0]
    pe = E.policy_answers(emp, "empty", ans)
    check("empty_pred_uses_F_for_R_RL", pe["R"][0] is ans[(emp, "F", "O")] and pe["R_L"][0] is ans[(emp, "F", "O")])
    check("empty_pred_RB_no", pe["R_B"][0]["suffix_text_raw"] == "no")
    ids_by_cat = {c: [p for p in pats if cats[p] == c] for c in S.CATS}
    pr = E.policy_report(ids_by_cat, cats, st, ans, "sem")
    # F는 모두 No: O는 normal/nno 맞음, A는 normal만 맞음 -> pair 정답은 normal만
    check("policy_F_scope", abs(pr["policies"]["F"]["S_scope"] - 1 / 3) < 1e-12, pr["policies"]["F"]["S_scope"])
    check("policy_RB_changes_one_patient_only", pr["policies"]["R_B"]["O_sensitivity_opacity"] == 0.5)


def test_real_data():
    sets, labels, infer, ckpt, bbox = D.load_assets()
    rep, problems = D.audit(sets, labels, infer, ckpt, bbox)
    check("audit_no_problems", not problems, problems[:3])
    check("audit_counts_plan", rep["nonempty"]["P180"] == {"opacity": 54, "normal": 1, "not_normal_no_opacity": 17}
          and rep["nonempty"]["E600"] == {"opacity": 164, "normal": 5, "not_normal_no_opacity": 67}, rep["nonempty"])
    F, comps = D.load_F()
    check("F_coverage_1200", len(F) == 1200 and all(c["n_missing"] == 0 and c["n_duplicate"] == 0 and c["verify_error"] is None for c in comps.values()))
    check("F_all_eos_cap1000", all(r["ended_eos"] for r in F.values()))
    nstage = {}
    for st_ in ("FREPRO", "TECH", "P180R", "E600R"):
        rows = RUN.read_requests(str(B.DATA / f"requests_{st_}.jsonl"))
        nstage[st_] = len(rows)
    check("request_counts", nstage == {"FREPRO": 12, "TECH": 42, "P180R": 462, "E600R": 1148}, nstage)
    allrows = [r for st_ in ("TECH", "P180R", "E600R") for r in RUN.read_requests(str(B.DATA / f"requests_{st_}.jsonl"))]
    check("total_science_requests_1652", len(allrows) == 1652)
    ids = [r["request_id"] for r in allrows]
    check("request_ids_unique", len(ids) == len(set(ids)))
    stp = json.load(open(B.DATA / "stage_patients.json"))["stages"]
    allp = stp["TECH"] + stp["P180R"] + stp["E600R"]
    check("patients_disjoint_236", len(allp) == len(set(allp)) == 236)
    # 요청 구성에 정답/조건명/box 개수가 들어가지 않는다
    leak = [r for r in allrows if any(w in r["prompt"].lower() for w in ("opacity box", "predicted", "localiz", "box_2d", "condition", "crop of", "normal radiograph"))]
    check("prompt_no_leak_terms", not leak, leak[:1])
    check("prompts_fixed_templates", all(r["prompt"] == S.prompt_for(r["cond"], r["target"]) for r in allrows))
    # 영상 연결: D 두 영상 동일, T/C 첫 영상 동일, crop 파일 hash
    geo = json.load(open(B.DATA / "geometry.json"))
    bad = 0
    for r in allrows:
        if r["images"][0]["pixel_sha256"] != geo[r["patient"]]["orig_pixel_sha256"] and r["cond"] != "L":
            bad += 1
    check("first_image_is_original", bad == 0)
    from rsna_diag import generate as G
    for pid in stp["TECH"]:
        g = geo[pid]
        canvas, _, px = B.load_canvas(g["orig_image"])
        T = g["images"]["T"]
        arr, aff = S.crop_square_padded(canvas, tuple(g["rect_T"]))
        check(f"crop_T_pixels_{pid}", B.load_canvas(T["path"])[2] == S.sha(arr.tobytes()) and D.file_sha(D.ROOT / T["path"]) == T["file_sha256"])
        hT, wT = g["rect_T"][3] - g["rect_T"][1], g["rect_T"][2] - g["rect_T"][0]
        hC, wC = g["rect_C"][3] - g["rect_C"][1], g["rect_C"][2] - g["rect_C"][0]
        check(f"crop_C_same_size_{pid}", (hT, wT) == (hC, wC) and g["rect_C"][0] == (g["side"] - wC) // 2)
    # GT가 crop 선택에 쓰이지 않음: 지오메트리는 bbox만으로 재현
    pid = stp["TECH"][0]
    st, boxes = S.parse_saved_bbox(bbox[pid]["suffix_text_raw"], bbox[pid]["ended_eos"])
    check("geometry_from_bbox_only", S.crop_rect(S.enclosing(boxes), geo[pid]["side"]) == tuple(geo[pid]["rect_T"]))
    # 변조 거부
    rows = RUN.read_requests(str(B.DATA / "requests_TECH.jsonl"))
    r0 = copy.deepcopy(rows[0])
    tmp = Path(sys.argv[1]).parent / "tamper_rows.jsonl"
    for name, mut in (("prompt", lambda r: r.update(prompt=r["prompt"] + " ")), ("cond", lambda r: r.update(cond="C")),
                      ("image_pixel", lambda r: r["images"][0].update(pixel_sha256="0" * 64)),
                      ("role", lambda r: r["images"][1].update(role="crop_center"))):
        rr = copy.deepcopy(r0)
        mut(rr)
        tmp.write_text(json.dumps(rr) + "\n")
        try:
            RUN.read_requests(str(tmp))
            check(f"tamper_rejected_{name}", False)
        except RUN.RunError:
            check(f"tamper_rejected_{name}", True)
    # request_id 재구성이 build와 동일
    check("request_id_rebuild_matches_build", all(RUN.expected_request_id(r) == r["request_id"] for r in rows))


def main():
    out = Path(sys.argv[1])
    if out.exists():
        sys.exit(f"exists {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    for fn in (test_parse_and_crops, test_eval_math, test_policies, test_real_data):
        try:
            fn()
        except Exception as e:  # noqa
            import traceback
            check(f"{fn.__name__}_raised", False, traceback.format_exc()[-800:])
    n_ok = sum(c["pass"] for c in CHECKS)
    json.dump({"n": len(CHECKS), "n_pass": n_ok, "checks": CHECKS}, open(out, "w"), indent=1, default=str)
    print(f"{n_ok}/{len(CHECKS)} pass")
    for c in CHECKS:
        if not c["pass"]:
            print("FAIL", c["name"], str(c["detail"])[:300])
    sys.exit(0 if n_ok == len(CHECKS) else 1)


if __name__ == "__main__":
    main()
