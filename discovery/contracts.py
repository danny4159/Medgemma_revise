"""모델 응답 계약과 최소 근거 연결 검사. 과학적 판단의 자동 증명은 아니다."""
import re
from urllib.parse import urlsplit


AXES = ("importance", "originality", "leadership", "impact", "medical_origin", "generalization", "feasibility")
TEXT = {"type": "string"}
BOOL = {"type": "boolean"}


def enum(*values):
    return {"type": "string", "enum": list(values)}


def array(item, maximum=None):
    result = {"type": "array", "items": item}
    if maximum is not None:
        result["maxItems"] = maximum
    return result


def obj(**fields):
    return {"type": "object", "properties": fields, "required": list(fields), "additionalProperties": False}


SOURCE = obj(id=TEXT, url=TEXT, title=TEXT,
             kind=enum("paper", "deployment", "industry", "standard", "public_report", "other"),
             primary=BOOL, access=enum("full_text", "abstract", "snippet", "unavailable"),
             publication_date=TEXT, checked_at=TEXT, locator=TEXT, claim=TEXT, limitations=TEXT)
ASSESSMENT = obj(key=enum(*AXES), judgment=enum("supported", "plausible", "unknown", "unsupported"),
                 reason=TEXT, source_ids=array(TEXT))
CANDIDATE = obj(id=TEXT, problem_key=TEXT, title=TEXT,
                status=enum("exploring", "investigating", "nominate", "held", "excluded"),
                summary=TEXT, problem=TEXT, medical_origin=TEXT, users_and_workflow=TEXT,
                generalization=TEXT, strongest_objection=TEXT, uncertainty=TEXT,
                reopen_reason=TEXT, next_questions=array(TEXT), assessments=array(ASSESSMENT, 7),
                sources=array(SOURCE), closest_work=array(obj(source_id=TEXT, solves=TEXT, leaves_open=TEXT)),
                report_markdown=TEXT)
EXPLORE = obj(question=TEXT, why_this_question=TEXT, search_queries=array(TEXT), what_changed=TEXT,
              evidence_added=BOOL, next_action=enum("continue", "pause"), next_question=TEXT,
              focus_id=TEXT, selection_reason=TEXT, candidates=array(CANDIDATE, 3), report_markdown=TEXT)
CRITIC = obj(verdict=enum("recommend", "deepen", "hold", "exclude"), reason=TEXT,
             next_question=TEXT, blocking_issues=array(TEXT),
             criteria=array(obj(key=enum(*AXES), passed=BOOL, reason=TEXT), 7),
             source_checks=array(obj(source_id=TEXT, verified=BOOL, supports_claim=BOOL, notes=TEXT)),
             additional_sources=array(SOURCE), report_markdown=TEXT)


def validate(value, schema, path="response"):
    expected = schema["type"]
    types = {"object": dict, "array": list, "string": str, "boolean": bool}
    if not isinstance(value, types[expected]):
        raise ValueError(f"{path}: {expected} 필요")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: 허용되지 않은 값")
    if expected == "object":
        if set(value) != set(schema["properties"]):
            raise ValueError(f"{path}: 필수/알 수 없는 필드")
        for key, child in schema["properties"].items():
            validate(value[key], child, path + "." + key)
    if expected == "array":
        if len(value) > schema.get("maxItems", len(value)):
            raise ValueError(f"{path}: 항목 수 초과")
        for i, child in enumerate(value):
            validate(child, schema["items"], f"{path}[{i}]")


def sources_valid(sources):
    ids = set()
    for source in sources:
        if not source["id"] or source["id"] in ids:
            raise ValueError("출처 id 누락/중복")
        ids.add(source["id"])
        url = urlsplit(source["url"])
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
            raise ValueError("출처는 인증정보 없는 HTTP(S) URL이어야 합니다")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", source["checked_at"]):
            raise ValueError("출처 확인 날짜는 YYYY-MM-DD 필요")
        if source["access"] == "full_text" and not all(source[k].strip() for k in ("locator", "claim", "title")):
            raise ValueError("원문 확인에는 위치·주장·제목이 필요")
    return ids


def axes_valid(items):
    if len(items) != len(AXES) or {x["key"] for x in items} != set(AXES):
        raise ValueError("일곱 평가 축을 중복 없이 기록해야 합니다")


def candidate_valid(candidate):
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,63}", candidate["id"]):
        raise ValueError("후보 id는 안전한 영문 slug 필요")
    if not candidate["problem_key"].strip() or not candidate["problem"].strip():
        raise ValueError("후보 문제/중복 비교 key 누락")
    ids = sources_valid(candidate["sources"])
    axes_valid(candidate["assessments"])
    for item in candidate["assessments"]:
        if not set(item["source_ids"]).issubset(ids):
            raise ValueError("평가 근거가 없는 출처를 참조")
    if any(x["source_id"] not in ids for x in candidate["closest_work"]):
        raise ValueError("가까운 연구의 출처 연결 누락")


def nomination_problems(candidate):
    good = {s["id"]: s for s in candidate["sources"] if s["primary"] and s["access"] == "full_text"}
    problems = []
    if not any(good.get(w["source_id"], {}).get("kind") == "paper"
               and w["solves"].strip() and w["leaves_open"].strip() for w in candidate["closest_work"]):
        problems.append("원문 확인된 가까운 연구와 해결/미해결 비교 부족")
    if not any(s["kind"] in {"deployment", "industry", "standard", "public_report"} for s in good.values()):
        problems.append("원문 확인된 수요 관련 1차 근거 부족")
    for axis in candidate["assessments"]:
        if axis["judgment"] in {"unknown", "unsupported"} or not axis["reason"].strip() or not (set(axis["source_ids"]) & good.keys()):
            problems.append(f"{axis['key']} 근거 미충족")
    if not candidate["strongest_objection"].strip() or not candidate["uncertainty"].strip():
        problems.append("반론/미확인 범위 누락")
    return problems


def recommendation_problems(candidate, review):
    problems = nomination_problems(candidate)
    axes_valid(review["criteria"])
    sources_valid(review["additional_sources"])
    ids = {s["id"] for s in candidate["sources"]}
    checked = [x["source_id"] for x in review["source_checks"]]
    if len(checked) != len(set(checked)) or not set(checked).issubset(ids):
        raise ValueError("심사 출처 id 중복/알 수 없는 출처")
    required = {s["id"] for s in candidate["sources"] if s["primary"] and s["access"] == "full_text"}
    verified = {c["source_id"] for c in review["source_checks"] if c["verified"] and c["supports_claim"] and c["notes"].strip()}
    if not required.issubset(verified):
        problems.append("핵심 원문 재확인/주장 지지 미충족")
    if review["blocking_issues"] or not all(c["passed"] for c in review["criteria"]):
        problems.append("추천 기준 미충족/해결되지 않은 반론")
    return problems
