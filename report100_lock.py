"""iter_100 적격성 정정: iter_099의 finding-only 제한(clear 속성 atom 제외)을 원 계획대로 고쳐 회복 집단 N과 보존 대조를 잠근다.

- report99_lock.py / iter_099 산출물은 수정하지 않는다(과거 기록). 그 ledger의 의미 판정(status)을 그대로 상속하고
  unknown/partial/covered_by_draft/temporal을 clear로 바꾸지 않는다. 바뀐 것은 (1) 집단 규칙에 clear 속성(attr) atom 포함,
  (2) 선택 환자 atom의 고유 ID·원문 span·영역 group/source 연결, (3) 속성 영향 경로(P-clear 14명) 확인 기록이다.
- 판정은 assistant 단일 수동 검토(전문의/독립 임상 검증 아님). 인용은 모두 원문에 존재해야 하며 존재 검사는 의미 동치의 증명이 아니다.
- 모든 검사 통과 후에만 ledger/decision을 배타 생성하고, 마지막에 lock_complete.json을 만든다. 실패하면 오류 기록만 남긴다.
"""
import copy
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import report98_data as D
import report99_lock as L99

ROOT = D.ROOT
OUT_DEFAULT = ROOT / "results" / "iter_100" / "data"
PLAN99 = ROOT.parent / "agent" / "runs" / "iter_099" / "plan.md"
PLAN99_SHA = "f4424caab23b410df7a81935bd91c93bdb3aed42cda432f49b2af06f44c60835"
PLAN100 = ROOT.parent / "agent" / "runs" / "iter_100" / "plan.md"
DECISION99 = ROOT / "results" / "iter_099" / "data" / "eligibility_decision.json"
SOURCES = ["report98_data.py", "report99_lock.py", "report100_lock.py"]
CLEAR_KINDS = ("finding", "attr")  # temporal kind는 시간 주장이므로 자동 clear로 쓰지 않는다
CONTROL_SALT = "report100_control|"

# iter_099 ledger에서 바뀌는 항목: P053 Q의 존재(P)와 크기(Q attr) 분리 설명, 속성 영향 경로 확인 기록.
# 환자 -> 모든 확인은 영역 본문 원문 인용(없으면 None)과 이유를 가진다.
ATTR_CHECKS = [
    dict(patient=3, p_fact="F1", attr="left cavities", desc_quote=None, result="no_attr_Q",
         reason="영역 설명에 좌심 chamber 언급 없음(D16 cardiac silhouette enlargement만)"),
    dict(patient=8, p_fact="F1", attr="(reference attr 없음)", desc_quote="small left pleural effusion", result="no_attr_Q",
         reason="reference F1에 크기 속성 요구가 없어 미표현 속성 atom이 아니다. 시간(persistent)은 temporal로 별도"),
    dict(patient=12, p_fact="F1", attr="chronic", desc_quote=None, result="no_attr_Q", reason="초안이 chronic을 이미 표현. 영역 설명에 실질 관련 본문 없음"),
    dict(patient=21, p_fact="F1", attr="interstitial/bilateral", desc_quote=None, result="no_attr_Q", reason="초안이 이미 bilateral interstitial 표현"),
    dict(patient=25, p_fact="F1", attr="dorsolumbar", desc_quote=None, result="no_attr_Q", reason="초안이 dorsolumbar를 이미 표현"),
    dict(patient=33, p_fact="F1", attr="marked", desc_quote="Moderate cardiomegaly is unchanged", result="not_clear",
         reason="영역 설명의 moderate는 reference의 marked와 일치하지 않는다(clear로 바꾸지 않음). 심비대 존재는 초안이 이미 표현"),
    dict(patient=45, p_fact="F1", attr="chronic", desc_quote=None, result="no_attr_Q", reason="초안이 chronic을 이미 표현"),
    dict(patient=49, p_fact="F2", attr="descending thoracic aorta", desc_quote="The aorta is tortuous", result="no_attr_Q",
         reason="영역 설명에 descending 위치 언급 없음(aortic arch의 tortuous만)"),
    dict(patient=52, p_fact="F1", attr="marked dorsolumbar", desc_quote=None, result="no_attr_Q", reason="척추 영역 설명이 29개 영역 중 없음(spine region 부재)"),
    dict(patient=53, p_fact="F3", attr="small", desc_quote="small left pleural effusion", result="clear_attr_Q",
         reason="reference의 small을 영역 설명 D08/D11이 직접 서술. left·metapneumonic은 reference 비지지로 별도 미지원 항목"),
    dict(patient=56, p_fact="F2", attr="metallic", desc_quote=None, result="no_attr_Q", reason="초안의 osteosynthesis material이 대응. 영역 설명에 관련 본문 없음"),
    dict(patient=62, p_fact="F5", attr="intense", desc_quote="moderate dextroscoliosis of the thoracic spine", result="not_clear",
         reason="영역 설명의 moderate는 reference의 intense와 일치하지 않는다. 방향(우측 볼록)은 초안이 이미 표현"),
    dict(patient=69, p_fact="F1", attr="bilateral", desc_quote=None, result="no_attr_Q", reason="영역 설명에 prosthesis 관련 본문 없음"),
    dict(patient=70, p_fact="F2", attr="(reference attr 없음)", desc_quote="mildly enlarged with a left ventricular configuration", result="no_attr_Q",
         reason="reference F2에 속성 요구가 없고 초안이 left ventricle을 이미 표현"),
]

# iter_099에서 ledger에 없던 34명의 초안-reference 양성 사실 대응을 속성 영향 관점에서 다시 훑은 결과(P-clear 없음 확인).
ABSENT_SCAN = {
    "method": "ledger 미등재 환자 34명의 초안과 reference 양성 사실(pos_*)을 읽고 P-clear(초안이 reference 지지 사실을 표현) 여부만 확인",
    "result": "P-clear 후보 없음. 경계 사례 P002(초안에 scoliosis 없음)·P032(초안 chronic parenchymal changes 대 reference apical pleuroparenchymal tracts: 동치 미확정)는 clear로 바꾸지 않음",
    "borderline": [2, 32],
    "note": "iter_099 ledger를 일괄 승계하지 않고 이번 속성 규칙에 영향이 있는 조건(P-clear 존재)만 재확인했다. 전면 재주석이 아니다.",
}


def sha_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def atomic_create(path, text):
    return L99.atomic_create(path, text)


def decorate(pi, ent, pk, am_i):
    """atom에 고유 ID와 원문 위치(draft offset / reference sentence / 영역 group·source)를 붙인 사본을 반환한다. 위치가 없으면 ValueError."""
    out = copy.deepcopy(ent)
    draft_l = pk["draft"].lower()
    fsent = {f["fact_id"]: f["sentence_en"] for f in am_i["facts"]}
    for kind in ("P", "Q"):
        for n, e in enumerate(out[kind], 1):
            e["id"] = "P%03d.%s%d" % (pi, kind, n)
            s = fsent[e["fact"]]
            j = s.lower().find(e["ref_quote"].lower())
            if j < 0:
                raise ValueError("ref_quote missing %s" % e["id"])
            e["ref_span"] = [j, j + len(e["ref_quote"]), s]
            if kind == "P":
                j = draft_l.find(e["draft_quote"].lower())
                if j < 0:
                    raise ValueError("draft_quote missing %s" % e["id"])
                e["draft_span"] = [j, j + len(e["draft_quote"])]
            else:
                hit = [g for g in pk["groups"] if e["desc_quote"].lower() in g["body"].lower()]
                if not hit:
                    raise ValueError("desc_quote missing %s" % e["id"])
                e["groups"] = [dict(gid=g["gid"], regions=g["regions"],
                                    span=[g["body"].lower().find(e["desc_quote"].lower()),
                                          g["body"].lower().find(e["desc_quote"].lower()) + len(e["desc_quote"])]) for g in hit]
    return out


def cohort(ledger, p_ok=("clear",), q_ok=("clear",), q_kinds=CLEAR_KINDS):
    """P에 clear atom, Q에 clear이며 kind가 finding/attr인 atom이 모두 있는 환자. temporal·unknown·partial·covered_by_draft는 제외."""
    out = []
    for pi, ent in sorted(ledger.items()):
        if any(a["status"] in p_ok for a in ent["P"]) and any(a["status"] in q_ok and a["kind"] in q_kinds for a in ent["Q"]):
            out.append(pi)
    return out


def control_order(ledger, am, ids):
    """보존 대조 후보: P-clear이고 Q atom이 하나도 없는 환자를 sha256(salt+ImageID) 오름차순으로 정렬. 결과 확인 전에 규칙 고정."""
    idx = {am[i]["patient_index"]: i for i in ids}
    cands = [pi for pi, e in ledger.items() if any(a["status"] == "clear" for a in e["P"]) and not e["Q"]]
    return sorted(cands, key=lambda pi: hashlib.sha256((CONTROL_SALT + idx[pi]).encode()).hexdigest())


def build_ledger():
    led = copy.deepcopy(L99.LEDGER)
    # P053: 존재(P1)와 크기(Q1)는 서로 다른 고유 atom이다. 판정(status)은 iter_099와 동일하며 설명만 보강한다.
    led[53]["P"][0]["note"] = ("effusion 존재 atom. 초안의 left는 reference가 지지하지 않는 위치(unsupported), "
                               "metapneumonic은 초안에 없고 reference 속성(원인)이다")
    led[53]["Q"][0]["note"] = ("크기(small) 속성 atom: 공통 소견이 초안에 있고 영역 설명 D08/D11이 reference의 small을 직접 서술. "
                               "left는 reference 비지지이므로 이 atom의 지지 범위에 포함하지 않는다")
    led[53]["unsupported_or_uncertain"] = [
        "초안 'Left': reference F3에 laterality 없음 -> 지지 불가(unknown)",
        "'metapneumonic': 초안·영역 설명 모두 원인 서술 없음 -> 회복 atom 아님",
        "F4 retrocardiac consolidation decreased: 영역 설명 D13 'new left lower lobe opacity'는 opacity-consolidation 동치 미확정이며 시간 방향이 반대 -> unknown 유지",
        "초안 'No suspicious lesions or infiltrates are observed': reference F4 consolidation과 모순 가능 -> P로 인정하지 않음",
        "reference F1/F2 구체적 정상(cardiothoracic index, mediastinal contour): 초안은 포괄 정상문뿐이라 P로 인정하지 않음",
    ]
    led[70]["unsupported_or_uncertain"] = [
        "초안 'No significant findings'/'Dorsal spondylosis': reference 비지지 또는 포괄 정상문 -> P 아님",
        "reference F1 probable old subcapital fracture of right humerus: 초안에 없음(hedged pos). 영역 설명에도 관련 서술 없음 -> Q 아님",
    ]
    return led


def quote_checks(ledger, ids, readings, am):
    return L99.quote_checks(ledger, ids, readings, am)


def provenance():
    paths = {
        "inputs_E96.json": D.INPUTS, "reference_facts_E_private.json": D.REF_PRIV, "reference_amend_E96.json": D.REF_AMEND,
        "readings.jsonl": D.READINGS, "iter_099_eligibility_decision.json": DECISION99, "iter_099_plan.md": PLAN99,
        "iter_100_plan.md": PLAN100, "linked.json": L99.LINKED,
    }
    for s in SOURCES:
        paths[s] = ROOT / s
    return {k: sha_file(v) for k, v in paths.items()}


def build(out=OUT_DEFAULT, ledger=None, readings_path=None):
    """검사 통과 시에만 ledger/decision/lock_complete를 만든다. 반환 (rc, problems)."""
    t0 = time.time()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    ledger = build_ledger() if ledger is None else ledger
    problems = []
    if sha_file(PLAN99) != PLAN99_SHA:
        problems.append(dict(problem="iter_099_plan_sha_mismatch"))
    ids = D.abnormal_ids()
    if len(ids) != 48 or len(set(ids)) != 48:
        problems.append(dict(problem="abnormal_ids", n=len(ids)))
    try:
        readings = D.load_readings(readings_path)
    except ValueError as e:
        problems.append(dict(problem="readings_duplicate", detail=str(e)))
        readings = None
    am = json.load(open(D.REF_AMEND))["patients"]
    if readings is not None:
        problems += quote_checks(ledger, ids, readings, am)
        by = {am[i]["patient_index"]: i for i in ids}
        for c in ATTR_CHECKS:
            if c["patient"] not in ledger:
                problems.append(dict(problem="attr_check_patient_not_in_ledger", patient=c["patient"]))
            elif c["desc_quote"]:
                bodies = " ".join(g["body"] for g in D.package(by[c["patient"]], readings)["groups"]).lower()
                if c["desc_quote"].lower() not in bodies:
                    problems.append(dict(problem="attr_check_quote", patient=c["patient"], quote=c["desc_quote"]))
    stamp = time.strftime("%Y%m%dT%H%M%S")
    if problems:
        atomic_create(out / ("lock_errors_%s_%d.json" % (stamp, os.getpid())), json.dumps(dict(problems=problems), ensure_ascii=False, indent=1))
        return 1, problems

    n_cohort = cohort(ledger)
    by = {am[i]["patient_index"]: i for i in ids}
    order = control_order(ledger, am, ids)
    controls = [pi for pi in order if pi not in n_cohort][:len(n_cohort)]
    p_clear = sorted(pi for pi, e in ledger.items() if any(a["status"] == "clear" for a in e["P"]))
    selected = sorted(set(n_cohort) | set(controls))
    atoms = {}
    for pi in sorted(ledger):
        pk = D.package(by[pi], readings)
        atoms[str(pi)] = decorate(pi, ledger[pi], pk, am[by[pi]])
    old = json.load(open(DECISION99))
    decision = dict(
        n_abnormal=48,
        rule=("N = P에 clear atom이 있고 Q에 clear인 finding 또는 attr atom이 있는 환자. temporal kind와 unknown/partial/covered_by_draft 상태는 제외. "
              "속성 포함은 의미 완화가 아니라 원 계획의 원자 사실 정의다."),
        N_recovery_cohort=n_cohort,
        run_generation=bool(n_cohort),
        control_rule=("보존 대조 = P-clear이고 Q atom이 전혀 없는 환자를 sha256('%s'+ImageID) 오름차순으로 정렬해 최대 N명 선택" % CONTROL_SALT),
        control_candidates_in_order=order,
        preservation_controls=controls,
        selected_patients=[dict(patient=pi, ImageID=by[pi], role="recovery" if pi in n_cohort else "preservation_control") for pi in selected],
        P_clear_patients=p_clear,
        iter_099=dict(N=old["N_recovery_cohort"], run_generation=old["run_generation"]),
        change_vs_iter_099=dict(N_added=sorted(set(n_cohort) - set(old["N_recovery_cohort"])),
                                cause="finding-only 제한 제거(clear attr atom 포함). 다른 status 판정 변경 없음"),
        scenario_finding_only=cohort(ledger, q_kinds=("finding",)),
        attr_checks=ATTR_CHECKS,
        absent_patients_scan=ABSENT_SCAN,
        review_note="assistant 단일 수동 검토이며 전문의/독립 임상 검증이 아니다. 인용 존재 검사는 의미 동치의 증명이 아니다.",
        lock_wall_s=round(time.time() - t0, 3),
        provenance_sha256=provenance(),
    )
    atomic_create(out / "atom_ledger.json", json.dumps(dict(atoms=atoms, reviewed_patients=48,
                                                            patients_without_candidate_atoms=[am[i]["patient_index"] for i in ids
                                                                                              if am[i]["patient_index"] not in ledger]),
                                                       ensure_ascii=False, indent=1))
    decision["atom_ledger_sha256"] = sha_file(out / "atom_ledger.json")
    atomic_create(out / "eligibility_decision.json", json.dumps(decision, ensure_ascii=False, indent=1))
    atomic_create(out / "lock_complete.json", json.dumps(dict(
        files={n: sha_file(out / n) for n in ("atom_ledger.json", "eligibility_decision.json")},
        N=n_cohort, controls=controls, run_generation=bool(n_cohort)), ensure_ascii=False, indent=1))
    print(json.dumps(dict(N=n_cohort, controls=controls, finding_only=decision["scenario_finding_only"], run_generation=bool(n_cohort),
                          order=order), ensure_ascii=False))
    return 0, []


if __name__ == "__main__":
    rc, probs = build()
    if probs:
        print(json.dumps(probs, ensure_ascii=False, indent=1))
    sys.exit(rc)
