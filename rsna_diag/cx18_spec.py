"""iter_018 target-scope 진단(CheXpert) 질문·evidence 문장·분할 규칙 (결과를 보기 전에 고정).

- 주방향 main: Cardiomegaly reference -> Pleural Effusion 질문. 보조 방향 aux: Pleural Effusion reference -> Cardiomegaly 질문.
- 조건: D(무관 evidence 없음) < U(reference 있으나 결과 unavailable) < T(실제 값) < Tscope(T + 범위 한정 문장).
- category는 (Cardiomegaly, Pleural Effusion) absent/present 4조합이며 이름은 f"{cardiomegaly}_{pleural_effusion}"이다.
- parser·출력 형식(plain/json)은 qa_spec을 그대로 재사용한다 (target 이름에 의존하지 않는 whole-string yes/no 규칙).
"""
import hashlib

from . import qa_spec as QS

FINDINGS = {"CM": "cardiomegaly", "PE": "pleural effusion"}
DIRECTIONS = {"main": {"target": "PE", "ref": "CM"}, "aux": {"target": "CM", "ref": "PE"}}
CONDITIONS = ("D", "U", "T", "Tscope")
CATEGORIES = ("absent_absent", "present_absent", "absent_present", "present_present")  # (Cardiomegaly, Pleural Effusion)

FORMATS = QS.FORMATS
parse_plain = QS.parse_plain
parse_json = QS.parse_json
parse_answer = QS.parse_answer


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()


def cat_of(cm, pe):
    return f"{cm}_{pe}"


def cat_values(cat):
    cm, pe = cat.split("_")
    if cm not in ("absent", "present") or pe not in ("absent", "present"):
        raise ValueError(f"bad category {cat!r}")
    return cm, pe


def gt_answer(direction, cat):
    """direction의 target finding에 대한 정답 yes/no (reference와 무관, 실제 label만 본다)."""
    cm, pe = cat_values(cat)
    val = pe if direction == "main" else cm
    return "yes" if val == "present" else "no"


def ref_value(direction, cat):
    """direction의 reference finding 실제 값 ('present'|'absent')."""
    cm, pe = cat_values(cat)
    return cm if direction == "main" else pe


def question(target_key, fmt):
    disp = FINDINGS[target_key]
    return f"Is {disp} present in this chest radiograph? {FORMATS[fmt]}"


def evidence_sentence(cond, ref_key, tgt_key, ref_val):
    """cond: U|T|Tscope. ref_val: T/Tscope에서만 사용('present'|'absent'), U에서는 무시된다."""
    ref_disp, tgt_disp = FINDINGS[ref_key], FINDINGS[tgt_key]
    if cond == "U":
        result = "unavailable"
    elif cond in ("T", "Tscope"):
        if ref_val not in ("present", "absent"):
            raise ValueError(f"bad ref_val {ref_val!r} for condition {cond!r}")
        result = ref_val
    else:
        raise ValueError(f"no evidence sentence for condition {cond!r}")
    sent = f"A separate assessment of this same chest radiograph considered {ref_disp}. Result: {result}."
    if cond == "Tscope":
        sent += (f" This assessment concerns only {ref_disp}; it does not determine whether {tgt_disp} is present or absent. "
                 f"Assess {tgt_disp} from the image.")
    return sent


def prompt_and_evidence(direction, cond, fmt, cat):
    """returns (prompt, evidence_digest_or_None). D는 evidence 없음(=R과 공유); U/T/Tscope는 evidence 문장을 질문 앞에 붙인다."""
    if direction not in DIRECTIONS:
        raise ValueError(f"unknown direction {direction!r}")
    if cond not in CONDITIONS:
        raise ValueError(f"unknown condition {cond!r}")
    d = DIRECTIONS[direction]
    tgt, ref = d["target"], d["ref"]
    q = question(tgt, fmt)
    if cond == "D":
        return q, None
    ev = evidence_sentence(cond, ref, tgt, ref_value(direction, cat))
    return f"{ev}\n\n{q}", sha(ev)


def split_patients(cat_patient_ids, salt="iter018-v1", n_d=4, n_e=12):
    """cat_patient_ids: {category: [patient_id,...]}. returns sets.json 형식 {"D16": {cat: [...]}, "E48": {...}, "F": {...}}.

    각 category 안에서 sha256(salt + '|' + patient_id)로 정렬해 앞 n_d명을 D16, 다음 n_e명을 E48, 나머지를 F로 잠근다."""
    out = {"D16": {}, "E48": {}, "F": {}}
    for cat, ids in cat_patient_ids.items():
        if len(set(ids)) != len(ids):
            raise ValueError(f"duplicate patient id in category {cat}")
        order = sorted(ids, key=lambda pid: sha(f"{salt}|{pid}"))
        out["D16"][cat] = order[:n_d]
        out["E48"][cat] = order[n_d:n_d + n_e]
        out["F"][cat] = order[n_d + n_e:]
    return out
