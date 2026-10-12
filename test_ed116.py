"""iter_116 CPU 검사: 선택 규칙, prompt 구성, 비정사각 좌표, 독립 matching, 미해결 범위 열거, 분기 판정.
사용: python test_ed116.py <출력 json> (기존 파일 덮어쓰기 거부)"""
import itertools
import json
import random
import sys

import numpy as np

import ed116_eval as EV
import ed116_spec as ES
from rsna_diag import geometry as GEO
from rsna_diag import metrics as MET

R = []


def chk(name, ok, detail=None):
    R.append(dict(name=name, passed=bool(ok), detail=detail))
    print(("PASS " if ok else "FAIL ") + name, "" if ok else detail)


def brute_tp(pred, gt, thr):
    """독립 구현: 모든 부분 일대일 대응 열거 (소규모)."""
    best = 0
    n, m = len(gt), len(pred)
    for k in range(min(n, m), 0, -1):
        for gi in itertools.combinations(range(n), k):
            for pi in itertools.permutations(range(m), k):
                if all(MET.iou(pred[p], gt[g]) >= thr for g, p in zip(gi, pi)):
                    return k
    return best


def fake_row(i, size=(1024, 1024), scores=(0.9,), boxes=None, o_raw="Yes.\n<end_of_turn>"):
    h, w = size
    top, left, side = GEO.pad_offsets(h, w)
    boxes = boxes or [[100.0, 200.0, 400.0, 600.0]] * len(scores)
    return dict(id=f"x{i}", patient=f"p{i}", size_hw=[h, w], pad=[top, left, side], O=dict(raw=o_raw, ended_eos=True),
                SFT=dict(raw="[]<end_of_turn>", ended_eos=True), det=dict(scores=list(scores), boxes_xyxy_px=boxes, labels=[1] * len(scores), img_hw=[h, w]))


def main(out):
    ledger = json.load(open("results/iter_116/provenance/ledger_nogt.json"))["rows"]
    gt = json.load(open("results/iter_116/provenance/gt.json"))
    byid = {r["id"]: r for r in ledger}
    sel = ES.select(ledger)
    chk("selection_counts", sel["n"] == dict(mismatch=87, agree=505, unresolved=8, tech=12, control=87), sel["n"])
    chk("selection_disjoint", not (set(sel["tech"]) & set(sel["control"])) and not (set(sel["tech"]) & set(sel["mismatch"])) and
        not (set(sel["control"]) & set(sel["mismatch"])))
    chk("selection_deterministic", ES.select(ledger[::-1]) == sel)
    chk("selection_agree_hash_order", sel["tech"] + sel["control"] == sorted(sel["agree_all"], key=lambda i: ES.sel_key(byid[i]["patient"]))[:99])
    cor = lambda i, a: a == EV.gt_answer(gt[i]["category"])
    chk("planning_counts_K_correct_47_B_correct_40", sum(cor(i, ES.answer_K(byid[i])) for i in sel["mismatch"]) == 47 and
        sum(cor(i, ES.answer_B(byid[i])) for i in sel["mismatch"]) == 40)
    chk("agree_427_78", sum(cor(i, ES.answer_K(byid[i])) for i in sel["agree_all"]) == 427)
    # prompt
    tested = 0
    leak = 0
    for i in sel["mismatch"][:10] + sel["control"][:10]:
        r = byid[i]
        d = ES.answer_K(r)
        pR, pT, pN, pE = (ES.build_prompt(c, r, d) for c in "RTNE")
        assert pR == pT and pR != pN and pR != pE
        assert "first-pass" not in pE and "detector" not in pN and "Candidate" not in pN and "No candidate" not in pN
        tested += 1
        leak += int(any(w in pR.lower() for w in ("ground truth", "annotation", "label")))
    chk("prompt_R_eq_T_N_E_ablate_one_field", tested == 20 and leak == 0)
    r0 = fake_row(0)
    chk("prompt_instruction_present", "may each be wrong" in ES.build_prompt("R", r0, "yes") and ES.build_prompt("R", r0, "yes").endswith("Answer only yes or no."))
    # packet 좌표: 비정사각
    r1 = fake_row(1, size=(800, 1024), scores=(0.8, 0.95, 0.3), boxes=[[10.0, 20.0, 110.0, 220.0], [500.0, 100.0, 700.0, 300.0], [0.0, 0.0, 5.0, 5.0]])
    pk = ES.packet_text(r1)
    chk("packet_threshold_sort_normalized_orig", "Candidate 1: score 0.950, box [0.488, 0.125, 0.684, 0.375]" in pk and "Candidate 2: score 0.800" in pk
        and "Candidate 3" not in pk, pk)
    pad = r1["pad"]
    nb = EV.det_norm_boxes(r1)
    top, left, side = GEO.pad_offsets(800, 1024)
    exp0 = [(100.0 + top) * 1000 / side, (500.0 + left) * 1000 / side, (300.0 + top) * 1000 / side, (700.0 + left) * 1000 / side]
    chk("nonsquare_pad_offsets_and_norm", pad == [112, 0, 1024] and all(abs(a - b) < 1e-9 for a, b in zip(nb[0], exp0)), nb[0])
    back = GEO.norm_to_canvas(nb[0], top, left, side)
    chk("nonsquare_roundtrip", all(abs(a - b) < 1e-6 for a, b in zip(back, [500.0, 100.0, 700.0, 300.0])), back)
    chk("empty_packet_text", ES.packet_text(fake_row(2, scores=(0.2,))) == "No candidate met the detector threshold; this does not establish absence.")
    # 공동 지표: 양성 정확 일치 (비정사각, GT는 padded canvas 기준)
    gt_box = nb[0]
    pat = EV.make_patient(r1, dict(category="opacity", gt_yxyx_norm=[gt_box, nb[1]]), dict(N="yes", E="yes", R="yes", T="no"))
    sc = EV.scalars(pat, EV.derive("yes", "yes", None, "yes", "yes", "yes", "no"))
    chk("joint_positive_exact_match", sc["joint03_R"] == 1 and sc["joint03_T"] == 0 and sc["fn03_T"] == 2 and sc["posf1_03_R"] == 1.0, sc["joint03_R"])
    pat2 = EV.make_patient(r1, dict(category="opacity", gt_yxyx_norm=[gt_box]), dict(N="yes", E="yes", R="yes", T="yes"))
    sc2 = EV.scalars(pat2, pat2["base"])
    chk("joint_positive_extra_pred_fails", sc2["joint03_R"] == 0 and sc2["fp03_R"] == 1 and sc2["posf1_03_R"] < 1.0)
    pat3 = EV.make_patient(r1, dict(category="normal", gt_yxyx_norm=[]), dict(N="no", E="yes", R="no", T=None))
    sc3 = EV.scalars(pat3, pat3["base"])
    chk("joint_negative_requires_no_boxes", sc3["joint03_R"] == 1 and sc3["joint03_E"] == 0 and sc3["fp03_E"] == 2 and sc3["joint03_T"] == 0)
    # matching 독립 대조
    rnd = random.Random(1)
    bad = 0
    for _ in range(300):
        def rb():
            y, x = rnd.uniform(0, 600), rnd.uniform(0, 600)
            return [y, x, y + rnd.uniform(50, 400), x + rnd.uniform(50, 400)]
        pr, g = [rb() for _ in range(rnd.randint(0, 4))], [rb() for _ in range(rnd.randint(0, 4))]
        if rnd.random() < 0.6 and pr and g:
            pr[0] = [v + rnd.uniform(-20, 20) for v in g[0]]
        for thr in (0.3, 0.5):
            if len(MET.match(pr, g, thr)) != brute_tp(pr, g, thr):
                bad += 1
    chk("matching_vs_bruteforce_600", bad == 0, bad)
    # derive == spec.policy_answers
    mism = 0
    for r in ledger[:200]:
        ma = dict(N=rnd.choice(["yes", "no", None]), E=rnd.choice(["yes", "no", None]), R=rnd.choice(["yes", "no", None]), T=rnd.choice(["yes", "no", None]))
        a = EV.derive(ES.answer_K(r), ES.answer_B(r), ES.answer_G(r), ma["N"], ma["E"], ma["R"], ma["T"])
        mism += a != ES.policy_answers(r, ma)
    chk("derive_equals_spec_policy_answers", mism == 0, mism)
    # 정책 정의
    chk("majority_rules", ES.majority("yes", "no", None) == "yes" and ES.majority("yes", "no", "no") == "no" and ES.majority("no", "yes", "yes") == "yes")
    d = EV.derive("yes", "no", None, None, "no", "yes", None)
    chk("S_replaces_only_when_E_resolved_and_equals_B", d["S"] == "no" and EV.derive("yes", "no", None, None, "yes", None, None)["S"] == "yes"
        and EV.derive("yes", "no", None, None, None, None, None)["S"] == "yes")
    # 범위 열거 == 전수 교차곱 (3환자)
    pats = []
    specs = [dict(cat="opacity", K="no", B="yes", G=None, N="yes", E=None, R="yes", T=None),
             dict(cat="normal", K="yes", B="no", G="no", N=None, E="no", R=None, T="no"),
             dict(cat="opacity", K="yes", B="no", G=None, N=None, E=None, R=None, T=None)]
    for k, s in enumerate(specs):
        r = fake_row(10 + k, scores=(0.9,) if s["B"] == "yes" else (0.1,))
        p = EV.make_patient(r, dict(category=s["cat"], gt_yxyx_norm=[[0, 0, 1, 1]] if s["cat"] == "opacity" else []), {})
        p["base"] = EV.derive(s["K"], s["B"], s["G"], s["N"], s["E"], s["R"], s["T"])
        pats.append(p)
    lo_tot = {}
    hi_tot = {}
    per_free = [[v for v in EV.FREE if p["base"][v] is None] for p in pats]
    allsc = []
    for assign in itertools.product(*[list(itertools.product(("yes", "no"), repeat=len(f))) for f in per_free]):
        tot = {}
        for p, f, combo in zip(pats, per_free, assign):
            b = dict(p["base"])
            b.update(dict(zip(f, combo)))
            sc = EV.scalars(p, EV.derive(b["K"], b["B"], b["G"], b["N"], b["E"], b["R"], b["T"]))
            for k, v in sc.items():
                tot[k] = tot.get(k, 0) + v
        allsc.append(tot)
    keys = allsc[0].keys()
    bf_lo = {k: min(t[k] for t in allsc) for k in keys}
    bf_hi = {k: max(t[k] for t in allsc) for k in keys}
    rg = [EV.range_scalars(p) for p in pats]
    en_lo = {k: sum(lo[k] for lo, _ in rg) for k in keys}
    en_hi = {k: sum(hi[k] for _, hi in rg) for k in keys}
    chk("range_equals_full_cross_product", all(abs(bf_lo[k] - en_lo[k]) < 1e-9 and abs(bf_hi[k] - en_hi[k]) < 1e-9 for k in keys),
        [k for k in keys if abs(bf_lo[k] - en_lo[k]) > 1e-9 or abs(bf_hi[k] - en_hi[k]) > 1e-9][:5])
    chk("point_inside_range", all(en_lo[k] - 1e-9 <= sum(EV.point_scalars(p)[k] for p in pats) <= en_hi[k] + 1e-9 for k in keys))
    # decide 분기
    def synth(corr, harm, adv, agree_harm, unresolved_flip=False):
        n = 87
        pt = {"correction_R": corr, "harm_R": harm}
        for x in EV.COMP:
            pt[f"diff_R_{x}"] = adv
        mm = dict(point=dict(pt), range_min=dict(pt), range_max=dict(pt))
        if unresolved_flip:
            mm["range_min"] = {**pt, "correction_R": corr - 5, **{f"diff_R_{x}": adv - 5 for x in EV.COMP}}
        ag = dict(point={"harm_R": agree_harm}, range_min={"harm_R": agree_harm}, range_max={"harm_R": agree_harm}, n_K_correct=76)
        return EV.decide(mm, ag)
    chk("decide_positive", synth(12, 3, 7, 3)["label"] == "positive_exploratory")
    chk("decide_hold_when_harm_high", synth(12, 8, 7, 3)["label"] == "hold_current_frozen_setting")
    chk("decide_hold_when_agree_harm_high", synth(12, 3, 7, 4)["label"] == "hold_current_frozen_setting")
    chk("decide_hold_when_advantage_small", synth(12, 3, 4, 3)["label"] == "hold_current_frozen_setting")
    chk("decide_inconclusive_flip", synth(12, 3, 7, 3, True)["label"] == "inconclusive_unresolved_flips_criteria")
    chk("agree_harm_limit_is_5pct_of_Kcorrect", synth(12, 3, 7, 3)["point"]["agree_harm_rate<=0.05"] and not synth(12, 3, 7, 4)["point"]["agree_harm_rate<=0.05"])
    # bootstrap 결정성
    v = np.arange(87) % 3 - 1
    a1 = EV.ci_mean(v, EV.boot_idx(87))
    a2 = EV.ci_mean(v, EV.boot_idx(87))
    chk("bootstrap_seed_fixed", a1 == a2 and ES.SEED_BOOT == 11617 and ES.N_BOOT == 10000)
    # 실제 선택 환자에 대한 end-to-end dry-run (합성 모델 답): R=K이면 교정·손상 0, R=정답(oracle)이면 교정 40·손상 0, 범위는 점추정과 같다
    for mode in ("R=K", "R=gt"):
        pm = []
        for i in sel["mismatch"]:
            k = ES.answer_K(byid[i])
            y = EV.gt_answer(gt[i]["category"])
            ma = dict(N=k, E=k, R=(k if mode == "R=K" else y), T=k)
            pm.append(EV.make_patient(byid[i], gt[i], ma))
        rp = EV.group_report(pm)
        if mode == "R=K":
            chk("dryrun_R_eq_K", rp["point"]["correction_R"] == 0 and rp["point"]["harm_R"] == 0 and rp["point"]["diff_R_K"] == 0
                and rp["range_min"]["correct_R"] == rp["range_max"]["correct_R"] == 47 and rp["n_K_correct"] == 47 and rp["n_K_wrong"] == 40)
        else:
            chk("dryrun_R_oracle", rp["point"]["correction_R"] == 40 and rp["point"]["harm_R"] == 0 and rp["point"]["correct_R"] == 87
                and rp["ci95"]["diff_R_K"][0] == 40 / 87)
    # 기존 ev109_extract_v1 fixture를 규칙 변경 없이 실행 (iter_109 경로에는 쓰지 않는다: main()을 호출하지 않고 CASES만 사용)
    import test_ev109_extract as T9
    import ev109_extract as X9
    bad9 = [n for n, tg_, raw, eos, ea, es in T9.CASES if not (X9.resolve(tg_, raw, eos)["answer"] == ea and X9.resolve(tg_, raw, eos)["source"] == es)]
    chk("ev109_extract_v1_fixtures_unchanged", len(T9.CASES) >= 30 and not bad9 and X9.RULES_VERSION == "ev109_extract_v1", [len(T9.CASES), bad9])
    tg = EV.tech_gate([], [])
    chk("tech_gate_empty_fails", tg["run"] is False)
    n_ok = sum(r["passed"] for r in R)
    import os
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    json.dump(dict(n=len(R), n_pass=n_ok, checks=R, spec_digest=ES.rules_digest()), open(out, "x"), indent=1)
    print(f"{n_ok}/{len(R)}")
    sys.exit(0 if n_ok == len(R) else 1)


if __name__ == "__main__":
    main(sys.argv[1])
