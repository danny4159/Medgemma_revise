"""iter_118 생성 전 고정 fixture: 응답 분류 규칙 + 요청 구성·정오 매핑 분리 + guard. 결과는 results/iter_118/tests/fixtures.json (새 파일).

fixture 기대값은 본출력을 보기 전에 작성했다. 본출력을 보고 규칙/기대값을 고르지 않는다.
"""
import json
import os
import sys

import ed118_spec as S

E = S.EOT
# (name, raw, ended_eos, direction, flags 중 True여야 하는 것(나머지는 False여야 함))
CASES = [
    ("plain_yes", "Yes", True, "yes", set()),
    ("plain_no_period", "No.", True, "no", set()),
    ("yes_with_eot", "Yes" + E, True, "yes", set()),
    ("markdown_yes", "**Yes**", True, "yes", set()),
    ("yes_explained", "Yes. There is a focal opacity in the right lower zone.", True, "yes", set()),
    ("yes_hedged_could", "Yes. This could represent pneumonia.", True, "yes", {"hedged"}),
    ("no_hedged_may", "No, although a subtle finding may be present.", True, "no", {"hedged"}),
    ("yes_but", "Yes, but only mildly.", True, "yes", {"hedged"}),
    ("no_with_recommendation", "No. Clinical correlation is recommended.", True, "no", set()),
    ("yes_follow_up", "Yes. Follow-up imaging is recommended to confirm.", True, "yes", set()),
    ("final_answer_line", "The radiograph shows a patchy area.\nFinal answer: Yes", True, "yes", set()),
    ("therefore_answer", "The lungs look clear. Therefore, the answer is no.", True, "no", set()),
    ("the_answer_is", "The answer is yes.", True, "yes", set()),
    ("no_candidate_start", "No candidate region is convincing, so I would say no opacity.", True, "unknown", {"parse_failure"}),
    ("conditional_only", "If the detector box is correct, then the answer is yes.", True, "unknown", {"conditional"}),
    ("conditional_then_yes", "If this is a true opacity then yes.", True, "unknown", {"conditional"}),
    ("refusal", "I cannot determine this from the information provided.", True, "unknown", {"refusal"}),
    ("refusal_sorry", "I'm sorry, I cannot answer this.", True, "unknown", {"refusal"}),
    ("yes_then_refusal", "Yes. However, I cannot determine the extent.", True, "yes", {"refusal"}),
    ("contradiction", "Yes.\nThe lungs are clear.\nFinal answer: No", True, "unknown", {"contradictory"}),
    ("self_correction", "Yes.\nActually, on reflection the answer is no.\nFinal answer: No", True, "no", set()),
    ("quoted_draft", "The first-pass answer was \"Yes\" but the image is clear.", True, "unknown", {"parse_failure"}),
    ("draft_echo_sentence", "The first-pass answer was Yes. I disagree after reviewing the image.", True, "unknown", {"parse_failure"}),
    ("question_echo", "Question: Is there a pulmonary opacity suspicious for pneumonia?", True, "unknown", {"parse_failure"}),
    ("empty", "", True, "unknown", {"parse_failure"}),
    ("non_eos_yes", "Yes. The", False, "unknown", {"non_eos"}),
    ("non_eos_none", "The radiograph shows", False, "unknown", {"non_eos", "parse_failure"}),
    ("uncertain_word", "Yes, it is uncertain whether this is pneumonia.", True, "yes", {"hedged"}),
    ("no_prose_only", "There is no focal consolidation.", True, "unknown", {"parse_failure"}),
    ("yes_colon", "Yes: right lower zone opacity.", True, "yes", set()),
    ("repeat_same", "Yes.\nTherefore, the answer is yes.", True, "yes", set()),
]


def run_cases():
    res = []
    for name, raw, eos, d, flags in CASES:
        c = S.classify(raw, eos)
        got = {k for k in ("hedged", "conditional", "contradictory", "refusal", "parse_failure", "non_eos") if c[k]}
        ok = c["direction"] == d and got == flags
        res.append(dict(name=name, ok=ok, expected=[d, sorted(flags)], got=[c["direction"], sorted(got)], note=c["note"]))
    return res


def run_misc():
    out = []
    row = dict(size_hw=[1024, 1024], det=dict(scores=[0.9, 0.5], boxes_xyxy_px=[[100, 200, 300, 400], [1, 1, 2, 2]]))
    pe = S.build_prompt(None, row)
    pc = S.build_prompt("yes", row)
    pw = S.build_prompt("no", row)
    out.append(dict(name="prompt_E_has_no_draft", ok="first-pass answer to this question was" not in pe))
    out.append(dict(name="prompt_C_W_differ_only_in_draft_word", ok=pc.replace("Yes.", "No.", 1) == pw and pc != pw))
    out.append(dict(name="prompt_E_equals_C_minus_draft_line", ok=pe == pc.replace("\n\n" + S.draft_line("yes"), "")))
    out.append(dict(name="packet_filters_below_threshold", ok="Candidate 1: score 0.900" in pe and "Candidate 2" not in pe))
    out.append(dict(name="shared_line_in_all", ok=all(S.SHARED_LINE in p for p in (pe, pc, pw))))
    out.append(dict(name="no_label_words", ok=not any(w in p.lower() for p in (pe, pc, pw) for w in ("correct", "incorrect", "ground truth", "category"))
                    or all("correct" not in p.lower().replace("may each be wrong", "") for p in (pe, pc, pw))))
    out.append(dict(name="rotation_balanced", ok=sorted(S.rotation("00012345")) == ["C", "E", "W"]))
    out.append(dict(name="synth_policy", ok=S.synth_policy(dict(direction="yes"), "yes", "no") == "yes"
                    and S.synth_policy(dict(direction="no"), "yes", "no") == "no"
                    and S.synth_policy(dict(direction="unknown"), "yes", "no") == "no"))
    return out


def run_synth():
    """합성 record로 평가·독립 verifier 일치와 손계산 기대값 검사 (모델 출력 없음)."""
    import ed118_eval as EV
    import ed118_verify as V
    cats = ["opacity"] * 4 + ["normal"] * 4 + ["not_normal_no_opacity"] * 4
    # 환자별 (E, W, C) 텍스트: opacity gt=yes, 그 외 gt=no
    txt = {"y": "Yes", "n": "No", "u": "I cannot determine this.", "h": "Yes. This could be pneumonia."}
    plan = [("y", "n", "y"), ("y", "y", "y"), ("n", "y", "n"), ("u", "n", "y"),     # opacity: E ok→W bad (H+1), ok→ok, E bad→W ok (H−1), E unk
            ("n", "y", "n"), ("n", "n", "n"), ("y", "n", "y"), ("n", "u", "n"),     # normal: E ok→W bad(+1), ok→ok, E bad→W ok (−1), W unk
            ("n", "n", "n"), ("n", "y", "n"), ("n", "y", "u"), ("y", "y", "n")]     # nlonn: ok→ok, ok→bad(+1), ok→bad(+1), E bad→W bad
    labels, ledger, recs, cmap = {}, [], [], {}
    for i, (cat, (e, w, c)) in enumerate(zip(cats, plan)):
        pid = f"{i:08d}"
        pos = cat == "opacity"
        box = [100, 100, 300, 300]
        labels[pid] = dict(category=cat, gt_answer="yes" if pos else "no", boxes_xyxy_px=[box] if pos else [])
        ledger.append(dict(id=pid, size_hw=[1024, 1024], det=dict(scores=[0.9] if pos else [], boxes_xyxy_px=[box] if pos else [])))
        order = ["E", "W", "C"]
        cmap[pid] = {f"s{k}": o for k, o in enumerate(order)}
        for k, o in enumerate(order):
            t = txt[{"E": e, "W": w, "C": c}[o]]
            recs.append(dict(patient=pid, cond=f"s{k}", suffix_text_raw=t + E, ended_eos=True, n_output_tokens=3, runtime_s_total=1.0, wall_s=1.0,
                             attempts=[1], peak_mem_reserved_gb_max=1.0))
    ps = EV.build_patients(recs, cmap, labels, ledger)
    rep = EV.report(ps)
    out = []
    # 손계산 기대값은 plan 표에서 독립적으로 센다 (평가 코드 호출 없음)
    exp_pos = sum(1 for (cat, (e, w, c)) in zip(cats, plan) if (e == ("y" if cat == "opacity" else "n")) and (w == ("n" if cat == "opacity" else "y")))
    exp_neg = sum(1 for (cat, (e, w, c)) in zip(cats, plan) if (e == ("n" if cat == "opacity" else "y")) and (w == ("y" if cat == "opacity" else "n")))
    out.append(dict(name="synth_H_W_matches_handcalc", ok=abs(rep["H"]["W"]["point"] - (exp_pos - exp_neg) / 12) < 1e-12, exp=[exp_pos, exp_neg]))
    out.append(dict(name="synth_unknown_not_counted_in_H", ok=rep["transitions"]["W"]["unk"]["bad"] + rep["transitions"]["W"]["ok"]["unk"] >= 1))
    checks = V.verify(ps, rep, recs, cmap, labels)
    out += [dict(name="verifier_" + c["name"], ok=c["ok"]) for c in checks]
    # 공동 성공: 양성 yes+정확 box, 음성 no
    out.append(dict(name="joint_positive_yes", ok=ps[1]["joint"]["E"] is True and ps[0]["joint"]["E"] is True))
    out.append(dict(name="joint_unknown_false", ok=ps[3]["joint"]["E"] is False))
    return out


def run_guard():
    """worker와 같은 guard: private/labels.json open은 PermissionError, 허용 파일(요청)은 열린다. 열린 경로는 로그에 남는다."""
    import subprocess
    import tempfile
    log = os.path.join(tempfile.mkdtemp(), "access.json")
    code = ("import ed118_guard, ed118_gen, json, sys\n"
            "ed118_guard.install(ed118_gen.GUARD_DENY, sys.argv[1])\n"
            "r={}\n"
            "for p in ['results/iter_118/private/labels.json','results/iter_118/private/../private/cond_map.json','results/iter_010/manifests/gt_manifest.json']:\n"
            "    try:\n        open(p).read(1); r[p]='opened'\n    except PermissionError: r[p]='denied'\n"
            "open('results/iter_118/requests/TECH.jsonl').read(1); r['req']='opened'\n"
            "print(json.dumps(r))\n")
    p = subprocess.run([sys.executable, "-c", code, log], capture_output=True, text=True)
    res = json.loads(p.stdout.strip().splitlines()[-1]) if p.returncode == 0 else {}
    logged = json.load(open(log)) if os.path.exists(log) else {}
    ok = (res.get("results/iter_118/private/labels.json") == "denied" and res.get("results/iter_118/private/../private/cond_map.json") == "denied"
          and res.get("results/iter_010/manifests/gt_manifest.json") == "denied" and res.get("req") == "opened" and len(logged.get("denied", [])) == 3)
    return [dict(name="guard_denies_private_and_logs", ok=ok, res=res, n_denied=len(logged.get("denied", [])))]


def main():
    cases = run_cases()
    misc = run_misc() + run_synth() + run_guard()
    allr = cases + misc
    out = dict(n=len(allr), n_pass=sum(r["ok"] for r in allr), all_pass=all(r["ok"] for r in allr), cases=cases, misc=misc,
               classifier_version=S.CLASSIFIER_VERSION, rules_digest=S.rules_digest())
    path = "results/iter_118/tests/fixtures.json"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "x") as f:
        json.dump(out, f, indent=1)
    for r in allr:
        if not r["ok"]:
            print("FAIL", r)
    print(out["n_pass"], "/", out["n"])
    sys.exit(0 if out["all_pass"] else 1)


if __name__ == "__main__":
    main()
