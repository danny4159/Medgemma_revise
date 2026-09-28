"""생성 suffix 전용 엄격 parser (iter_009).

규칙(계획 5절)
- suffix만 파싱한다. EOS 없이 끝난 요청은 status='truncated' (내용 오류와 구분).
- thinking(<unused94> ... <unused95>)을 분리한다. 열리고 닫히지 않으면 'unclosed_thinking'.
- 답 영역에서 'Final Answer:' 마커를 우선한다. 마커가 없으면 영역 전체에서 완결 JSON 목록이 정확히 하나일 때만 허용(marker_missing 표시).
- 복수의 서로 다른 최종 목록은 'ambiguous'. 빈 목록은 유효한 미검출.
- 좌표가 유한 수치, 0..1000, y0<y1 & x0<x1이 아니면 'coord_invalid'. clipping/정렬 구제 없음. 반환 box 전체를 보존한다.
- 라벨 비어있음/누락은 'schema_error'.
status 분류: valid_nonempty, valid_empty (유효 출력) / truncated, unclosed_thinking, no_answer, no_json, grammar_error,
             ambiguous, schema_error, coord_invalid (형식·좌표 실패).
"""
import json
import math
import re

THINK_OPEN, THINK_CLOSE = "<unused94>", "<unused95>"
EOT = "<end_of_turn>"
VALID = ("valid_nonempty", "valid_empty")
FINAL_RE = re.compile(r"Final Answer\s*:", re.I)
FENCE_RE = re.compile(r"```(?:json)?", re.I)


def _spans(text):
    """문자열 리터럴을 존중하는 최상위 [...] 균형 구간 목록 [(start, end_exclusive, complete)]."""
    out, i, n = [], 0, len(text)
    while i < n:
        if text[i] == "[":
            depth, j, in_s, esc = 0, i, False, False
            while j < n:
                c = text[j]
                if in_s:
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == '"':
                        in_s = False
                else:
                    if c == '"':
                        in_s = True
                    elif c == "[":
                        depth += 1
                    elif c == "]":
                        depth -= 1
                        if depth == 0:
                            break
                j += 1
            if depth == 0 and j < n:
                out.append((i, j + 1, True))
                i = j + 1
                continue
            out.append((i, n, False))
            break
        i += 1
    return out


def _candidates(region):
    """region에서 JSON 목록 후보를 찾는다. returns list of dict(kind, value/raw)."""
    region = FENCE_RE.sub(" ", region)
    cands = []
    for s, e, complete in _spans(region):
        raw = region[s:e]
        if not complete:
            if '"box_2d"' in raw or "box_2d" in raw:
                cands.append({"kind": "grammar_error", "raw": raw})
            continue
        try:
            v = json.loads(raw)
        except Exception:
            if "box_2d" in raw:
                cands.append({"kind": "grammar_error", "raw": raw})
            continue
        if isinstance(v, list) and (len(v) == 0 or any(isinstance(x, dict) and "box_2d" in x for x in v)
                                    or all(isinstance(x, dict) for x in v)):
            cands.append({"kind": "list", "value": v, "raw": raw})
    return cands


def _entry(e):
    """returns (box or None, label, problems list)."""
    prob = []
    if not isinstance(e, dict) or "box_2d" not in e:
        return None, None, ["schema:not_object_or_no_box_2d"]
    b, lab = e["box_2d"], e.get("label")
    if not isinstance(lab, str) or not lab.strip():
        prob.append("schema:empty_label")
    if not (isinstance(b, list) and len(b) == 4 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in b)):
        return None, lab, prob + ["schema:box_2d_not_4_numbers"]
    if not all(math.isfinite(v) for v in b):
        return [float(v) if math.isfinite(v) else v for v in b], lab, prob + ["coord:nonfinite"]
    b = [float(v) for v in b]
    if any(v < 0 or v > 1000 for v in b):
        prob.append("coord:out_of_range")
    if not (b[0] < b[2] and b[1] < b[3]):
        prob.append("coord:inverted_or_zero_area")
    return b, lab, prob


def parse_response(raw_suffix, ended_eos):
    res = {"status": None, "boxes": [], "labels": [], "flags": [], "problems": [], "n_candidates": 0}
    if not ended_eos:
        res["status"] = "truncated"
        return res
    text = raw_suffix
    if text.endswith(EOT):
        text = text[:-len(EOT)]
    region = text
    if THINK_OPEN in text or THINK_CLOSE in text:
        res["flags"].append("thinking_present")
        if THINK_CLOSE not in text:
            res["status"] = "unclosed_thinking"
            return res
        region = text.split(THINK_CLOSE, 1)[1]
        if THINK_OPEN in region or THINK_CLOSE in region:
            res["flags"].append("multiple_thinking_blocks")
    if not region.strip():
        res["status"] = "no_answer"
        return res
    markers = list(FINAL_RE.finditer(region))
    if markers:
        segs = [region[markers[i].end(): markers[i + 1].start() if i + 1 < len(markers) else len(region)]
                for i in range(len(markers))]
    else:
        res["flags"].append("marker_missing")
        segs = [region]
    if "```" in region:
        res["flags"].append("fenced")
    all_c = []
    for sgm in segs:
        all_c += _candidates(sgm)
    res["n_candidates"] = len(all_c)
    if not all_c:
        res["status"] = "no_json"
        return res
    if any(c["kind"] == "grammar_error" for c in all_c):
        res["status"] = "grammar_error"
        return res
    uniq = {json.dumps(c["value"], sort_keys=True) for c in all_c}
    if len(uniq) > 1:
        res["status"] = "ambiguous"
        return res
    if len(all_c) > 1:
        res["flags"].append("repeated_identical_final")
    val = all_c[0]["value"]
    res["raw_list"] = val
    probs = []
    for e in val:
        b, lab, p = _entry(e)
        res["boxes"].append(b)
        res["labels"].append(lab)
        probs += p
    res["problems"] = probs
    if any(p.startswith("schema") for p in probs):
        res["status"] = "schema_error"
    elif any(p.startswith("coord") for p in probs):
        res["status"] = "coord_invalid"
    else:
        res["status"] = "valid_nonempty" if val else "valid_empty"
    return res


def duplicates(boxes):
    seen, d = set(), 0
    for b in boxes:
        t = tuple(b)
        d += t in seen
        seen.add(t)
    return d
