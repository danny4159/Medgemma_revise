"""iter_099 적격성 정정: E96 비정상 48명의 P/Q를 원자 사실(atom) 단위로 다시 기록하고 회복 집단 N을 잠근다.

- iter_098(report98_lock.py)의 문장 단위 제외(시간·원인 hedge와 소견 존재를 합친 판단)를 대체한다. 기존 iter_098 산출물은 건드리지 않는다.
- 판정은 assistant 단일 수동 검토(전문의/독립 임상 검증 아님)이며 모든 인용은 원문(기존 reference/초안/영역 설명)에 존재해야 한다.
- 상태: clear(소견·측면·위치가 미해결 동치 없이 대응) / partial(소견·측면은 대응하나 위치·범위 대응에 lobe-zone 등 미해결 동치) /
  unknown(동치 미확정) / covered_by_draft(초안이 이미 표현했을 가능성) / temporal(시간 속성만) / attr(미표현 속성 atom).
- N(회복 집단) = P에 clear atom이 있고 Q에 clear atom(소견 수준)이 있는 환자. unknown/partial을 clear로 바꾸는 규칙 탐색은 하지 않는다.
  민감도 시나리오는 사전 정의된 완화만 계산하며(결정 기준 아님) 생성 허용은 strict N만으로 결정한다.
- 모든 검사를 통과한 뒤에만 결정/ledger 파일을 배타적·원자적으로 만든다. 실패하면 오류 기록만 남기고 잠금·허용 파일은 만들지 않는다.
"""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import report98_data as D

ROOT = D.ROOT
OUT_DEFAULT = ROOT / "results" / "iter_099" / "data"
PLAN98_SHA = "8983be9b98075892fe1595a3a232badf56f9459849e2b428e2b31ad7a1f38d9f"
PLAN98 = ROOT.parent / "agent" / "runs" / "iter_098" / "plan.md"
LINKED = ROOT / "results" / "iter_088" / "adjudication" / "linked.json"
DECISION98 = ROOT / "results" / "iter_098" / "data" / "eligibility_decision.json"
SOURCES = ["report98_data.py", "report99_lock.py"]


def P(fid, ref, draft, status, note=""):
    return {"fact": fid, "ref_quote": ref, "draft_quote": draft, "status": status, "note": note}


def Q(fid, ref, desc, status, note="", kind="finding"):
    return {"fact": fid, "ref_quote": ref, "desc_quote": desc, "status": status, "kind": kind, "note": note}


# 환자 index -> {"P": [...], "Q": [...], "note": ...}. 목록에 없는 환자는 '후보 없음'(reference 양성 사실에 대응하는 영역 설명이
# 없거나 초안이 대응 소견을 표현하지 않음)으로 처리한다. 48명 전체를 읽고 확인했다(view_abnormal48.txt).
LEDGER = {
    0: {"P": [], "Q": [Q("F3", "Nodular image in the lower third of the right hemithorax",
                         "vague opacity in the right lower lobe, which is new since the prior exam", "unknown",
                         "nodular image-opacity 동치 미확정")],
        "note": "초안이 'No relevant findings'뿐이라 P 없음"},
    3: {"P": [P("F1", "Cardiomegaly", "Cardiomegaly", "clear", "left cavities 속성 미표현")], "Q": []},
    5: {"P": [P("F1", "Laminar atelectasis in the lingula and middle lobe", "Left basal laminar atelectasis", "partial",
                "소견은 대응하나 lingula/middle lobe 대 left basal 위치 미해결")], "Q": []},
    8: {"P": [P("F1", "Left pleural effusion", "Left pleural effusion", "clear"),
              P("F2", "atelectasis-condensation", "Increased density in the left hemithorax", "unknown",
                "초안의 density+volume loss가 현재 atelectasis-condensation을 표현하는지 동치 미확정(자동 동치/누락 처리 안 함)")],
        "Q": [Q("F2", "atelectasis-condensation", "large left lower lobe consolidation with volume loss", "covered_by_draft",
                "초안이 density/volume loss로 이미 표현했을 가능성. 영역 설명이 새로 추가한 소견으로 단정 불가"),
              Q("F2", "Persistent", "The left upper lobe is still collapsed", "temporal",
                "'persistent'는 단일 영상으로 검증 불가한 시간 속성이며 소견 존재와 분리", kind="temporal")]},
    12: {"P": [P("F1", "Chronic changes in lung parenchyma", "Chronic changes of the pulmonary parenchyma", "clear")], "Q": []},
    21: {"P": [P("F1", "Bilateral interstitial pattern", "Bilateral interstitial pattern", "clear")], "Q": []},
    25: {"P": [P("F1", "Dorsolumbar scoliosis", "Dorsolumbar scoliosis", "clear")], "Q": []},
    33: {"P": [P("F1", "increase in the cardiomedastinal silhouette", "Cardiomegaly", "clear",
                 "'marked'와 cardiomediastinal 범위는 초안에 미표현(속성 분리)")],
         "Q": [Q("F2", "Pulmonary opacities in both pulmonary vertices predominantly on the right side",
                 "new right upper lobe opacity, which may represent pneumonia", "partial",
                 "소견 존재는 확정 서술이고 pneumonia hedge는 원인에만 붙음. 그러나 reference의 vertex(apex) 대 upper lobe는 lobe-zone 동치 미확정"),
               Q("F2", "both pulmonary vertices", "new left upper lobe opacity, which could represent pneumonia or aspiration", "partial",
                 "좌측 대응은 같은 lobe-zone 미해결. 양측 부분 대응을 전체 회복으로 계산하지 않음"),
               Q("F2", "in the right lower lobe", "Right upper lobe opacity is unchanged", "unknown",
                 "RLL 대응 영역 설명 없음. 오히려 'unchanged'가 reference의 'new'와 충돌(D18 대 D19)", kind="temporal")]},
    36: {"P": [], "Q": [Q("F1", "bilateral basal infiltrates", "In the left lower lobe, a small infiltrate is seen", "partial",
                          "basal 대 lower lobe 위치 미해결, 'decrease'(시간)는 별도 atom")],
         "note": "초안이 'No significant findings'뿐이라 P 없음"},
    42: {"P": [P("F1", "infiltrate at the left cardiac border", "Left basal infiltrate", "partial",
                 "소견·좌측은 대응, left cardiac border 대 basal 위치와 small/poorly defined 미해결")], "Q": [],
         "note": "P 제외 사유: 위치 미해결(partial). 영역 11번에 'There is no pulmonary edema.' 반복 폭주 출력이 있으나 본문은 그대로 사용 대상"},
    45: {"P": [P("F1", "Chronic changes in lung parenchyma", "Chronic pulmonary changes", "clear")], "Q": []},
    49: {"P": [P("F2", "Elongation of the descending thoracic aorta", "Aortic elongation", "clear", "descending 위치 미표현")], "Q": []},
    52: {"P": [P("F1", "scoliosis", "Dorsal scoliosis", "clear", "marked/dorsolumbar 속성은 부분 대응")], "Q": []},
    53: {"P": [P("F3", "effusion", "Left pleural effusion", "clear",
                 "small/metapneumonic 속성 미표현. 초안의 left는 reference가 지지하지 않는 위치(unknown)")],
         "Q": [Q("F3", "Small", "There is a small left pleural effusion", "clear",
                 "공통 소견이 초안에 있고 영역 설명이 크기 속성만 제공(속성 atom)", kind="attr"),
               Q("F4", "retrocardiac consolidation", "new left lower lobe opacity, which may represent atelectasis or pneumonia", "unknown",
                 "opacity-consolidation, retrocardiac-LLL 동치 미확정이며 'new'가 reference의 'decreased'와 충돌"),
               ],
         "note": "원인 hedge와 소견 존재를 분리해도 Q 소견 atom은 unknown. attr atom은 N 판정에 쓰지 않음"},
    56: {"P": [P("F2", "Metallic structure in the right humeral head", "Osteosynthesis material in the right humeral head", "clear")],
         "Q": []},
    62: {"P": [P("F5", "scoliosis", "Dorsolumbar scoliosis", "clear", "Intense 속성 미표현"),
               P("F3", "No alterations are observed in the lung parenchyma", "No lung infiltrates or condensations are observed",
                 "partial", "초안의 부정은 infiltrate/condensation으로 reference 범위(parenchyma 전체)보다 좁음")], "Q": []},
    69: {"P": [P("F1", "Bilateral mammary prostheses", "Suggestive of mammary prostheses", "clear", "초안은 'suggestive' hedge")], "Q": []},
    70: {"P": [P("F2", "Increased cardiothoracic index", "Cardiomegaly at the expense of the left ventricle", "clear")], "Q": []},
    76: {"P": [], "Q": [Q("F1", "Increased infiltrate in the right lung base", "New right lower lobe opacity concerning for pneumonia", "unknown",
                          "opacity-infiltrate, base-lobe 동치 미확정, 'new/pneumonia' 해석 혼합")],
         "note": "초안에 reference 지지 소견 없음"},
    80: {"P": [], "Q": [Q("F2", "Aortic elongation", "The aorta is tortuous", "unknown", "tortuous-elongation 동치 미확정"),
                        Q("F3", "Mechanical changes in the dorsal spine", "Mild degenerative changes are seen in the thoracic spine", "unknown",
                          "degenerative-mechanical 동치 미확정")],
         "note": "초안이 'No significant findings'뿐이라 P 없음"},
    82: {"P": [P("F1", "Chronic pleuroparenchymal changes", "Perihilar interstitial pattern", "unknown", "동치 미확정")], "Q": [],
         "note": "P 제외 사유: interstitial pattern이 chronic pleuroparenchymal changes와 같은 사실인지 미확정"},
    85: {"P": [], "Q": [Q("F1", "Right basal infiltrate, related to an infectious - inflammatory process",
                          "increased opacification at the right base medially, consistent with pneumonia", "clear",
                          "우측 base와 감염성 원인이 대응. 초안의 scoliosis는 reference 미지지")],
         "note": "P 없음(초안의 'slight dorsal scoliosis'는 reference가 지지하지 않음)"},
    86: {"P": [], "Q": [Q("F4", "Aortic elongation", "mild unfolding of the thoracic aorta", "unknown", "unfolding-elongation 동치 미확정")],
         "note": "초안이 'No pathological findings'뿐이라 P 없음"},
    90: {"P": [], "Q": [Q("F3", "Elevation of the right hemidiaphragm", "Elevation of the right hemidiaphragm is unchanged", "clear",
                          "'unchanged'는 시간 속성이며 소견 존재와 분리")],
         "note": "P 없음: 초안의 'No significant findings'는 reference의 구체적 부정(F1)을 대신하지 않는다"},
}


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha_file(p):
    return sha_bytes(Path(p).read_bytes())


def atomic_create(path, text):
    """배타 생성(덮어쓰기 금지) + 원자적 공개: 임시 파일을 완성한 뒤 hard link로 이름을 선점한다."""
    path = Path(path)
    tmp = path.with_name(".tmp_%d_%s" % (os.getpid(), path.name))
    with open(tmp, "x") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.link(tmp, path)  # 이미 존재하면 FileExistsError
    finally:
        os.unlink(tmp)


def quote_checks(ledger, ids, readings, am):
    """모든 ledger 인용이 실제 원문에 존재하는지, fact ID가 존재하는지 검사한다. 문제 목록을 반환."""
    problems = []
    idx_of = {am[i]["patient_index"]: i for i in ids}
    for pi, ent in ledger.items():
        if pi not in idx_of:
            problems.append({"patient": pi, "problem": "not_in_abnormal48"})
            continue
        i = idx_of[pi]
        pk = D.package(i, readings)
        draft = pk["draft"].lower()
        bodies = " ".join(g["body"] for g in pk["groups"]).lower()
        fsent = {f["fact_id"]: f["sentence_en"].lower() for f in am[i]["facts"]}
        for kind in ("P", "Q"):
            for e in ent[kind]:
                if e["fact"] not in fsent:
                    problems.append({"patient": pi, "kind": kind, "problem": "fact_id_missing", "fact": e["fact"]})
                    continue
                if e["ref_quote"].lower() not in fsent[e["fact"]]:
                    problems.append({"patient": pi, "kind": kind, "problem": "ref_quote", "quote": e["ref_quote"]})
                if kind == "P" and e["draft_quote"].lower() not in draft:
                    problems.append({"patient": pi, "kind": kind, "problem": "draft_quote", "quote": e["draft_quote"]})
                if kind == "Q" and e["desc_quote"].lower() not in bodies:
                    problems.append({"patient": pi, "kind": kind, "problem": "desc_quote", "quote": e["desc_quote"]})
    return problems


def cohort(ledger, p_ok, q_ok, q_kinds=("finding",)):
    """P에 p_ok 상태 atom, Q에 q_ok 상태이며 kind가 q_kinds인 atom이 모두 있는 환자 index."""
    out = []
    for pi, ent in sorted(ledger.items()):
        has_p = any(e["status"] in p_ok for e in ent["P"])
        has_q = any(e["status"] in q_ok and e["kind"] in q_kinds for e in ent["Q"])
        if has_p and has_q:
            out.append(pi)
    return out


def scenarios(ledger):
    """사전 정의 민감도. strict만 생성 허용에 쓴다. 나머지는 결정 민감도 보고용."""
    return {
        "strict": cohort(ledger, {"clear"}, {"clear"}),
        "Q_partial_as_clear": cohort(ledger, {"clear"}, {"clear", "partial"}),
        "Q_partial_and_attr_as_clear": cohort(ledger, {"clear"}, {"clear", "partial"}, ("finding", "attr")),
        "Q_partial_attr_and_P_partial": cohort(ledger, {"clear", "partial"}, {"clear", "partial"}, ("finding", "attr")),
        "Q_unknown_covered_as_clear(max)": cohort(ledger, {"clear", "partial", "unknown"},
                                                  {"clear", "partial", "unknown", "covered_by_draft"}, ("finding", "attr")),
    }


def provenance(extra_paths=()):
    paths = {
        "inputs_E96.json": D.INPUTS, "reference_facts_E_private.json": D.REF_PRIV,
        "reference_amend_E96.json": D.REF_AMEND, "readings.jsonl": D.READINGS, "linked.json": LINKED,
        "iter_098_eligibility_decision.json": DECISION98, "iter_098_plan.md": PLAN98,
    }
    for s in SOURCES:
        paths[s] = ROOT / s
    for p in extra_paths:
        paths[Path(p).name] = Path(p)
    return {k: sha_file(v) for k, v in paths.items()}


def build(out=OUT_DEFAULT, ledger=None, readings_path=None):
    """검사 통과 시에만 ledger/decision을 만든다. 반환: (rc, problems)."""
    t0 = time.time()
    ledger = LEDGER if ledger is None else ledger
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    problems = []
    if sha_file(PLAN98) != PLAN98_SHA:
        problems.append({"problem": "iter_098_plan_sha_mismatch"})
    ids = D.abnormal_ids()
    if len(ids) != 48 or len(set(ids)) != 48:
        problems.append({"problem": "abnormal_ids", "n": len(ids)})
    try:
        readings = D.load_readings(readings_path)
    except ValueError as e:
        problems.append({"problem": "readings_duplicate", "detail": str(e)})
        readings = None
    am = json.load(open(D.REF_AMEND))["patients"]
    if readings is not None:
        problems += quote_checks(ledger, ids, readings, am)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    if problems:
        err = out / ("lock_errors_%s_%d.json" % (stamp, os.getpid()))
        atomic_create(err, json.dumps({"problems": problems}, ensure_ascii=False, indent=1))
        return 1, problems

    sc = scenarios(ledger)
    n_strict = sc["strict"]
    old = json.load(open(DECISION98))
    p_clear = sorted(pi for pi, e in ledger.items() if any(a["status"] == "clear" for a in e["P"]))
    q_clear = sorted(pi for pi, e in ledger.items() if any(a["status"] == "clear" and a["kind"] == "finding" for a in e["Q"]))
    decision = {
        "n_abnormal": len(ids),
        "N_recovery_cohort": n_strict,
        "run_generation": bool(n_strict),
        "P_clear_patients": p_clear,
        "Q_clear_finding_patients": q_clear,
        "scenarios_N": sc,
        "iter_098": {"P_clear_patients": old["manual_P_clear_patients"], "Q_clear_patients": old["manual_Q_clear_patients"],
                     "N": old["N_recovery_cohort"]},
        "changes_vs_iter_098": {
            "P_added": sorted(set(p_clear) - set(old["manual_P_clear_patients"])),
            "P_removed": sorted(set(old["manual_P_clear_patients"]) - set(p_clear)),
            "Q_clear_added": sorted(set(q_clear) - set(old["manual_Q_clear_patients"])),
            "Q_clear_removed": sorted(set(old["manual_Q_clear_patients"]) - set(q_clear)),
        },
        "reason": ("strict 규약에서 P와 Q가 모두 clear인 환자가 없어 계획된 종료 분기(자료 적합성 부족)에 따라 생성 요청을 만들지 않는다."
                   if not n_strict else "strict N이 비어 있지 않음"),
        "review_note": "assistant 단일 수동 검토이며 전문의/독립 임상 검증이 아니다. unknown/partial을 clear로 바꾸는 규칙 탐색은 하지 않았다.",
        "lock_wall_s": round(time.time() - t0, 3),
        "provenance_sha256": provenance(),
    }
    ledger_doc = {"atoms": {str(k): v for k, v in sorted(ledger.items())},
                  "reviewed_patients": 48,
                  "patients_without_candidate_atoms": [am[i]["patient_index"] for i in ids
                                                       if am[i]["patient_index"] not in ledger]}
    atomic_create(out / "atom_ledger.json", json.dumps(ledger_doc, ensure_ascii=False, indent=1))
    decision["atom_ledger_sha256"] = sha_file(out / "atom_ledger.json")
    atomic_create(out / "eligibility_decision.json", json.dumps(decision, ensure_ascii=False, indent=1))
    print(json.dumps({k: decision[k] for k in ("N_recovery_cohort", "run_generation", "P_clear_patients",
                                              "Q_clear_finding_patients", "scenarios_N", "changes_vs_iter_098")}, ensure_ascii=False))
    return 0, []


if __name__ == "__main__":
    rc, probs = build()
    if probs:
        print(json.dumps(probs, ensure_ascii=False, indent=1))
    sys.exit(rc)
