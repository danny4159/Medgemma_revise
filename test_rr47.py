"""iter_047 CPU fixture: parser·지표(손계산)·자료 분류 규칙·요청 누출·verifier parser 일치·판정 규칙.
python test_rr47.py results/iter_047/tests/fixtures_rr47.json
"""
import json
import os
import sys
import traceback

import rr47_data as RD
import rr47_decide as DEC
import rr47_eval as E
import rr47_spec as S
import rr47_verify as V

RESULTS = []


def check(name, cond, detail=None):
    RESULTS.append(dict(name=name, passed=bool(cond), detail=detail))
    print(("PASS " if cond else "FAIL ") + name, flush=True)


def raw(a, b, eos="<end_of_turn>"):
    return '{"qA": "%s", "qB": "%s"}%s' % (a, b, eos)


def make_parsed(fn, kind="edit"):
    """fn(draft_code) -> (a, b) 문자열 또는 raw 문자열. returns parsed_by_cond for R2 (모든 cond 이름 채움)."""
    byc = {}
    for d in S.DRAFT_CODES:
        v = fn(d)
        text = v if isinstance(v, str) else raw(*v)
        for c in ("R1", "R2", "T"):
            byc[f"{c}_d{d}"] = S.parse_state(text, True, S.IDS)
    return byc


def metrics_for(cond_fn, truth, cond="R2"):
    byc = make_parsed(cond_fn)
    return E.patient_metrics(truth, cond, byc)


TRUTH = ["present", "absent"]  # 코드 '10'


def test_parser():
    ok = lambda t, e=True, ids=S.IDS: S.parse_state(t, e, ids)["status"]
    check("parse plain ok", ok(raw("present", "absent")) == "ok")
    check("parse fenced ok", ok("```json\n" + raw("absent", "absent", "") + "\n```<end_of_turn>") == "ok")
    check("parse trailing prose invalid", ok(raw("present", "absent", "") + " Because...<end_of_turn>") == "not_json")
    check("parse two json invalid (never picks one)", ok(raw("present", "absent", "") + "\n" + raw("absent", "absent", "")) == "multiple_json")
    check("parse dup key invalid", ok('{"qA": "present", "qA": "absent", "qB": "absent"}<end_of_turn>') == "dup_key")
    check("parse wrong keys invalid", ok('{"qA": "present"}<end_of_turn>') == "wrong_keys" and ok('{"qA":"present","qB":"absent","qC":"absent"}') == "wrong_keys")
    check("parse bad value (unknown/uppercase) invalid", ok(raw("Present", "absent")) == "bad_value" and ok(raw("unknown", "absent")) == "bad_value")
    check("parse non-EOS truncated invalid", ok(raw("present", "absent"), e=False) == "truncated")
    check("parse unclosed think marker invalid", ok("<unused94>thought" + raw("present", "absent")) == "think_marker")
    check("parse completed thinking block then strict JSON ok; JSON inside thinking not read", ok("<unused94>thought {\"qA\": \"absent\", \"qB\": \"absent\"}<unused95>" + raw("present", "absent")) == "ok"
          and S.parse_state("<unused94>thought {\"qA\": \"absent\", \"qB\": \"absent\"}<unused95>" + raw("present", "absent"), True, S.IDS)["answers"]["qA"] == "present")
    check("parse thinking without answer / two blocks / not at start invalid", ok("<unused94>thought<unused95>") == "empty" and ok("<unused94>a<unused95><unused94>b<unused95>" + raw("present", "absent")) == "think_marker"
          and ok("x<unused94>a<unused95>" + raw("present", "absent")) == "think_marker" and ok("<unused94>unclosed " + raw("present", "absent")) == "think_marker")
    check("parse empty invalid", ok("<end_of_turn>") == "empty")
    check("parse uncertain accepted as valid answer but scored 0", ok(raw("uncertain", "absent")) == "ok")
    check("parse single-id BI", S.parse_state('{"qB": "absent"}<end_of_turn>', True, ["qB"])["status"] == "ok")
    # verifier의 독립 parser와 일치
    cases = [(raw("present", "absent"), True), ("```json\n" + raw("absent", "absent", "") + "\n```<end_of_turn>", True),
             (raw("present", "absent", "") + " x<end_of_turn>", True), (raw("present", "absent", "") + "\n" + raw("a", "b", ""), True),
             ('{"qA": "present", "qA": "absent", "qB": "absent"}', True), ('{"qA": "present"}', True), (raw("Present", "absent"), True),
             (raw("present", "absent"), False), ("<unused94>x<unused95>" + raw("present", "absent"), True), ("<end_of_turn>", True), (raw("uncertain", "absent"), True),
             ("```\n" + raw("present", "absent", "") + "\n```", True), ('{"qA": "present", "qB": "absent"} ', True)]
    agree = []
    for t, e in cases:
        p = S.parse_state(t, e, S.IDS)
        q = V.parse_raw(t, e, S.IDS)
        agree.append((p["status"] == "ok") == (q is not None) and (q is None or q == p["answers"]))
    check("production parser == independent verifier parser on all cases", all(agree), agree)


def test_metrics():
    # truth=(present, absent); K
    byc = make_parsed(lambda d: raw(*S.code_states(d)))  # 초안 그대로 = K 와 같은 경로를 R2로 통과
    m = E.patient_metrics(TRUTH, "R2", byc)
    check("copy-draft: r=0 h=0 h_fail=0 acc=.5 clean=1 robust=0 sens=1 (final follows draft)", (m["r"], m["h"], m["h_fail"], m["acc"], m["clean_exact"], m["robust_exact"], m["sens"]) == (0, 0, 0, .5, 1, 0, 1), m)
    mk = E.patient_metrics(TRUTH, "K", {})
    check("K condition equals copy-draft", mk == m, mk)
    m = metrics_for(lambda d: ("present", "absent"), TRUTH)
    check("perfect (truth): r=1 h=0 hfail=0 acc=1 clean=1 robust=1 sens=0", (m["r"], m["h"], m["h_fail"], m["acc"], m["clean_exact"], m["robust_exact"], m["sens"]) == (1, 0, 0, 1, 1, 1, 0), m)
    m = metrics_for(lambda d: ("present", "present"), TRUTH)
    check("always-present: r=.5 h=.5 hfail=.5 acc=.5 clean=0 robust=0", (m["r"], m["h"], m["h_fail"], m["acc"], m["clean_exact"], m["robust_exact"]) == (.5, .5, .5, .5, 0, 0), m)
    m = metrics_for(lambda d: tuple(S.flip(s) for s in S.code_states(d)), TRUTH)
    check("always-flip: r=1 h=1 hfail=1 acc=.5 clean=0 sens=1", (m["r"], m["h"], m["h_fail"], m["acc"], m["clean_exact"], m["sens"]) == (1, 1, 1, .5, 0, 1), m)
    m = metrics_for(lambda d: '{"qA": "present"}<end_of_turn>', TRUTH)
    check("missing key -> invalid: r=0 h=0 hfail=1 acc=0", (m["r"], m["h"], m["h_fail"], m["acc"]) == (0, 0, 1, 0), m)
    m = metrics_for(lambda d: ("uncertain", "uncertain"), TRUTH)
    check("uncertain: r=0 h=0 hfail=1 acc=0 (uncertain is not preservation)", (m["r"], m["h"], m["h_fail"], m["acc"]) == (0, 0, 1, 0), m)
    m = metrics_for(lambda d: raw("present", "absent", "") + "\n" + raw("absent", "absent", "") + "<end_of_turn>", TRUTH)
    check("conflicting JSON -> invalid scored 0", (m["r"], m["acc"], m["h_fail"]) == (0, 0, 1), m)
    # 한쪽 누락: qA만 invalid, qB 정답 유지 => 상태별로 계산
    def half(d):
        return raw("present", "absent")
    byc = make_parsed(half)
    for d in S.DRAFT_CODES:  # 00 초안에서만 qA 키를 빼서 invalid
        pass
    m = metrics_for(lambda d: ("present", "absent") if d != "00" else '{"qB": "absent"}<end_of_turn>', TRUTH)
    # 00 초안 invalid: A(wrong)@00 not fixed, B(right)@00 not preserved. 나머지 3초안은 truth. r = 3/4, hfail = 1/4, acc = 6/8
    check("one draft invalid: r=.75 hfail=.25 acc=.75 robust=0", (m["r"], m["h_fail"], m["acc"], m["robust_exact"]) == (.75, .25, .75, 0), m)
    # BJ/BI는 초안에 무관하게 같은 최종 상태 적용
    bj = S.parse_state(raw("present", "present"), True, S.IDS)
    m = E.patient_metrics(TRUTH, "BJ", {"BJ": bj})
    check("BJ final reused across drafts (always-present numbers)", (m["r"], m["h"], m["acc"]) == (.5, .5, .5), m)
    bi = {"BI_qA": S.parse_state('{"qA": "present"}<end_of_turn>', True, ["qA"]), "BI_qB": S.parse_state('{"qB": "absent"}<end_of_turn>', True, ["qB"])}
    m = E.patient_metrics(TRUTH, "BI", bi)
    check("BI combines two single calls (perfect)", (m["r"], m["h"], m["acc"], m["robust_exact"]) == (1, 0, 1, 1), m)
    # 층화 bootstrap 결정성·퇴화
    table = {}
    for k in range(6):
        pid = f"P{k}"
        table[pid] = dict(stratum="10" if k < 3 else "01", truth=TRUTH, metrics={c: E.patient_metrics(TRUTH, "R2", make_parsed(lambda d: ("present", "absent"))) for c in E.CONDS})
    rep = E.summarize(table)
    rep2 = E.summarize(table)
    check("bootstrap deterministic and degenerate flagged", rep == rep2 and rep["diffs"]["BJ-R2:r"]["degenerate"] is True and rep["conds"]["R2"]["r"]["lo95"] == 1.0)


def test_data_rules():
    f = lambda en, es, ab=True, labels=("cardiomegaly",): dict(sentence_en=en, sentence_es=es, abnormal=ab, labels=list(labels))
    cs = RD.classify_sentence
    check("pos: cardiomegaly sentence", cs(f("Cardiomegaly.", "Cardiomegalia."))[0] == [("cardiomegaly", "present")])
    check("pos: 'upper limit of normal' labelled cardiomegaly is NOT accepted", cs(f("Cardiothoracic index at the upper limit of normal.", "Índice cardiotorácico en el límite alto de la normalidad."))[0] is None)
    check("pos: hedged effusion rejected", cs(f("Probable pleural effusion.", "Probable derrame pleural.", labels=("pleural effusion",)))[0] is None)
    check("pos: temporal rejected", cs(f("The left pleural effusion persists.", "Persiste el derrame pleural izquierdo.", labels=("pleural effusion",)))[0] is None)
    check("pos: 'known' rejected", cs(f("Known left pleural effusion.", "Derrame pleural izquierdo conocido.", labels=("pleural effusion",)))[0] is None)
    check("pos: label mismatch rejected", cs(f("Pleural effusion.", "Derrame pleural.", labels=("pericardial effusion",)))[0] is None)
    check("neg: 'No pleural effusion is appreciated.'", cs(f("No pleural effusion is appreciated.", "No se aprecia derrame pleural.", False))[0] == [("effusion", "absent")])
    check("neg: 'significant' qualified rejected", cs(f("No significant pleural effusion.", "Sin derrame pleural significativo.", False))[0] is None)
    check("neg: side-limited pneumothorax rejected", cs(f("Right lung without evidence of pneumothorax.", "Pulmón derecho sin neumotórax.", False))[0] is None)
    check("neg: no pneumothorax in bbox-less 'normal' general sentence is not inferred", cs(f("No other significant alterations.", "Sin otras alteraciones significativas.", False))[0] is None)
    check("neg: list negation gives two findings", cs(f("No consolidations, nodules or masses are observed.", "No se observan consolidaciones, nódulos ni masas.", False))[0] == [("consolidation", "absent"), ("nodule", "absent")])
    check("neg: 'Normal cardiothoracic index.' -> cardiomegaly absent", cs(f("Normal cardiothoracic index.", "Índice cardiotorácico normal.", False))[0] == [("cardiomegaly", "absent")])
    check("neg: general heart/vessels age sentence not accepted", cs(f("Cardiac silhouette and large vessels consistent with the patient's age.", "Silueta cardiaca y grandes vasos acordes a la edad.", False))[0] is None)
    check("neg: Spanish without negation word rejected", cs(f("No pleural effusion.", "Derrame pleural.", False))[0] is None)
    # 영상 단위 상충: 같은 영상에 같은 소견의 양성·음성
    rep = dict(ImageID="x.png", StudyID="s", findings=[f("Pleural effusion.", "Derrame pleural.", labels=("pleural effusion",)),
                                                       f("No pleural effusion.", "No hay derrame pleural.", False),
                                                       f("Scoliosis.", "Escoliosis.", labels=("scoliosis",))])
    st, amb, rows = RD.image_states(rep)
    check("conflicting annotations for same finding -> ambiguous", "effusion" in amb and "scoliosis" not in amb)
    rep2 = dict(ImageID="y.png", StudyID="s", findings=[f("Scoliosis.", "Escoliosis.", labels=("scoliosis",)),
                                                        f("Costophrenic angle blunting.", "Pinzamiento del seno costofrénico.", labels=("costophrenic angle blunting",)),
                                                        f("No pleural effusion.", "No hay derrame pleural.", False)])
    st, amb, rows = RD.image_states(rep2)
    check("costophrenic blunting sentence makes effusion-negative ambiguous (not inferred absent)", "effusion" in amb)


def test_requests_and_leak():
    rows = [json.loads(l) for l in open("results/iter_047/requests/requests_D8.jsonl")]
    man = json.load(open("results/iter_047/data/manifest_D8.json"))
    check("D8 request count 152 (120 plan + 32 oracle)", len(rows) == 152)
    from collections import Counter
    c = Counter(r["cond"].split("_")[0] for r in rows)
    check("D8 composition per patient R1 4, R2 4, T 4, BJ 1, BI 2, O 4", c == Counter(R1=32, R2=32, T=32, BJ=8, BI=16, O=32), dict(c))
    leak = []
    for r in rows:
        if r["cond"].startswith("O_"):
            continue
        low = r["prompt"].replace(S.R2_EXTRA, "").replace(S.R2_EXTRA.replace("the radiograph", "the available information"), "").lower()
        if "verified" in low or "reference" in low or "ground truth" in low or "correct" in low or "error" in low or "mistake" in low:
            leak.append(r["cond"])
    check("non-oracle prompts contain no truth/error cues", not leak, leak[:3])
    keys = set().union(*[set(r) for r in rows])
    check("request rows carry no truth/GT fields", not ({"truth", "gt", "truth_code", "states", "label"} & keys), sorted(keys))
    txt = [r for r in rows if r["modality"] == "text"]
    check("text rows have no image fields; image rows have hashes", all(r["image"] is None and r["input_pixel_sha256"] is None for r in txt) and
          all(r["image"] and r["input_pixel_sha256"] for r in rows if r["modality"] == "image") and len(txt) == 32)
    # R1/R2/T는 같은 초안·소견 mapping을 쓴다
    by = {}
    for r in rows:
        by.setdefault((r["patient"], r["cond"].split("_d")[-1] if "_d" in r["cond"] else None), []).append(r)
    ok = True
    for m in man["rows"]:
        fp = {i: m["q"][i]["finding"] for i in S.IDS}
        for d in S.DRAFT_CODES:
            items = S.draft_text(fp, d)
            for cond, fn in (("R1", S.prompt_R1), ("R2", S.prompt_R2), ("T", S.prompt_T)):
                row = [r for r in rows if r["patient"] == m["PatientID"] and r["cond"] == f"{cond}_d{d}"]
                ok = ok and len(row) == 1 and row[0]["prompt"] == fn(items)
    check("R1/R2/T prompts rebuilt from manifest match request files exactly", ok)
    # 혼합 상태 qA/qB 배치 균형 (D8: 01 두 명, 10 두 명)
    mixed = [m for m in man["rows"] if m["truth_code"] in ("01", "10")]
    check("mixed strata balanced across qA/qB position", sum(m["truth_code"] == "10" for m in mixed) == 2 and sum(m["truth_code"] == "01" for m in mixed) == 2)
    # truth mapping 일치: 문장 규칙 상태 == manifest 상태
    ok = all(S.code_states(m["truth_code"]) == [m["q"][i]["state"] for i in S.IDS] for m in man["rows"])
    check("truth_code equals per-ID states in manifest", ok)


def test_decide():
    def cond(r_lo, r_hi, h_lo, h_hi):
        return dict(r=dict(mean=(r_lo + r_hi) / 2, lo95=r_lo, hi95=r_hi), h_fail=dict(mean=(h_lo + h_hi) / 2, lo95=h_lo, hi95=h_hi))

    def rep(conds, diffs):
        base = dict((k, cond(0.1, 0.3, 0.2, 0.4)) for k in ("R1", "R2", "BJ", "BI", "T"))
        base.update(conds)
        d = {"BJ-T:acc": dict(mean=0.15, lo=0.05, hi=0.25), "BJ-R2:r": dict(mean=0.2, lo=0.05, hi=0.35), "BJ-R2:h_fail": dict(mean=0.1, lo=0.02, hi=0.2)}
        d.update(diffs)
        return dict(conds=base, diffs=d)
    check("decide: simple sufficient", DEC.decide(rep(dict(R2=cond(0.85, 0.95, 0.0, 0.04)), {}), True)["outcome"] == "simple_alternative_sufficient")
    check("decide: sufficient needs BOTH r lower>=.8 and hfail upper<=.05", DEC.decide(rep(dict(R2=cond(0.85, 0.95, 0.0, 0.07)), {}), True)["outcome"] != "simple_alternative_sufficient")
    check("decide: positive", DEC.decide(rep({}, {}), True)["outcome"] == "positive_min_method_review")
    check("decide: no image gain over text -> negative", DEC.decide(rep({}, {"BJ-T:acc": dict(mean=0.02, lo=-0.05, hi=0.08)}), True)["outcome"] == "negative_no_tradeoff")
    check("decide: wide CI -> inconclusive", DEC.decide(rep({}, {"BJ-R2:r": dict(mean=0.2, lo=-0.1, hi=0.5)}), True)["outcome"] == "inconclusive")
    check("decide: invalid run", DEC.decide(rep({}, {}), False)["outcome"] == "invalid_run")


def main():
    out = sys.argv[1]
    if os.path.exists(out):
        sys.exit(f"refuse to overwrite {out}")
    for t in (test_parser, test_metrics, test_data_rules, test_requests_and_leak, test_decide):
        try:
            t()
        except Exception:
            check(t.__name__ + " raised", False, traceback.format_exc())
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(dict(n=len(RESULTS), n_pass=sum(r["passed"] for r in RESULTS), results=RESULTS), open(out, "w"), indent=1, default=str)
    print(sum(r["passed"] for r in RESULTS), "/", len(RESULTS))
    sys.exit(0 if all(r["passed"] for r in RESULTS) else 1)


if __name__ == "__main__":
    main()
