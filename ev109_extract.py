"""iter_109 명시적 Yes/No 답 추출 (GT·영상·모델·조건 이름 없이 응답 텍스트와 질문 종류 O/A만 입력).

- 원 semantic_v1(ev108_spec.sem)이 받아들이는 응답은 그대로 유지한다 (resolve()에서 먼저 적용).
- 그 밖에 아래 두 가지 명시적 패턴만 추가로 받아들이고, 나머지는 모두 unresolved다. 패턴은 결과를 보기 전에 잠근다.
  R1 문두 직접 응답: 문두(공백·마크다운 강조 제외)의 독립된 Yes/No 뒤에 문장부호(. , : ; !) 또는 줄바꿈 또는 문자열 끝이 온다.
  R2 결론형: 독립 문장·줄(문장 경계 또는 줄 시작 직후)이 [Therefore|Thus|Hence|So|In conclusion,] [the] [final] answer is|: yes/no [.!] 로 끝난다.
     같은 답의 반복은 허용한다. 서로 다른 답이 둘 이상이면 conflict 이므로 unresolved.
- 추가 거부(unresolved): 인용/코드(`, ", “, ”, 줄머리 >), 질문 반복, 설명문 속 반대 yes/no 단어, 불확실성·조건 표현(고정 목록), 답 없음.
  `no`가 임상적 부정인지 해석해 구제하지 않는다. 설명문의 단어 no는 단지 반대 token으로 취급한다.
"""
import hashlib
import re

import ev108_spec as S
from rsna_diag import qa_spec

RULES_VERSION = "ev109_extract_v1"
EOT = qa_spec.EOT

_MD = r"[\*_]*"
R1 = re.compile(r"^\s*" + _MD + r"(yes|no)" + _MD + r"(?=\s*[.,:;!]|\s*\n|\s*$)", re.I)
R2 = re.compile(r"(?:^|(?<=\n)|(?<=[.!?]\s)|(?<=[.!?]))\s*" + _MD +
                r"(?:(?:therefore|thus|hence|so|in conclusion)\s*,?\s*)?(?:the\s+)?(?:final\s+)?answer\s*(?:is\s*:?|:)\s*" + _MD +
                r"(yes|no)" + _MD + r"\s*[.!]?\s*" + _MD + r"(?=\n|$)", re.I)
QUOTE_CHARS = re.compile(r"[`\"“”]|(?m:^\s*>)")
HEDGES = ["possibly", "possible", "probably", "probable", "may", "might", "could", "perhaps", "unclear", "uncertain", "uncertainty",
          "difficult", "cannot", "can't", "unable", "if", "unless", "whether", "hard to", "not sure", "would", "suggest", "suggests"]
HEDGE_RE = re.compile(r"\b(?:" + "|".join(re.escape(h) for h in HEDGES) + r")\b", re.I)
QUESTION_ECHO = [qa_spec.Q_O.lower()[:40], qa_spec.Q_A.lower()[:40], "answer only yes or no"]
WORD_YN = re.compile(r"\b(yes|no)\b", re.I)


def clean(raw):
    t = raw[:-len(EOT)] if raw.endswith(EOT) else raw
    return t.strip()


def extract(text, target):
    """returns dict(answer yes|no|None, rule, reason, spans). target ∈ O/A 는 인터페이스 호환용이며 규칙은 질문 종류에 의존하지 않는다."""
    if target not in qa_spec.QUESTIONS:
        raise ValueError(target)
    t = clean(text)
    if not t:
        return dict(answer=None, rule=None, reason="empty", spans=[])
    low = t.lower()
    if QUOTE_CHARS.search(t):
        return dict(answer=None, rule=None, reason="quote_or_code", spans=[])
    if any(q in low for q in QUESTION_ECHO):
        return dict(answer=None, rule=None, reason="question_echo", spans=[])
    found = []
    m1 = R1.match(t)
    if m1:
        found.append(("R1", m1.group(1).lower(), (m1.start(1), m1.end(1))))
    for m in R2.finditer(t):
        found.append(("R2", m.group(1).lower(), (m.start(1), m.end(1))))
    if not found:
        return dict(answer=None, rule=None, reason="no_explicit_answer", spans=[])
    answers = {a for _, a, _ in found}
    spans = [dict(rule=r, answer=a, span=list(s), text=t[s[0]:s[1]]) for r, a, s in found]
    if len(answers) > 1:
        return dict(answer=None, rule=None, reason="conflicting_answers", spans=spans)
    ans = answers.pop()
    # 설명 속 반대 token: 일치 span 바깥의 yes/no 단어
    used = [s for _, _, s in found]
    for m in WORD_YN.finditer(t):
        if any(s[0] <= m.start() < s[1] for s in used):
            continue
        if m.group(1).lower() != ans:
            return dict(answer=None, rule=None, reason="opposite_token", spans=spans)
    # 불확실성·조건 표현: 문장 전체 (답 span 제외 전체 텍스트)
    if HEDGE_RE.search(t):
        return dict(answer=None, rule=None, reason="hedge_or_conditional", spans=spans)
    return dict(answer=ans, rule="+".join(sorted({r for r, _, _ in found})), reason="explicit", spans=spans)


def resolve(target, raw, ended_eos):
    """원 semantic_v1 → 명시적 추출. returns dict(answer, source: semantic_v1|explicit|unresolved, reason, rule, spans). 입력에 GT/조건 없음."""
    st, ans = S.sem(target, raw, ended_eos)
    if st == "valid":
        return dict(answer=ans, source="semantic_v1", reason="semantic_v1", rule=None, spans=[])
    if st == "truncated" or not ended_eos:
        return dict(answer=None, source="unresolved", reason="truncated", rule=None, spans=[])
    e = extract(raw, target)
    if e["answer"] is not None:
        return dict(answer=e["answer"], source="explicit", reason="explicit", rule=e["rule"], spans=e["spans"])
    return dict(answer=None, source="unresolved", reason=e["reason"], rule=None, spans=e["spans"])


def rules_digest():
    import inspect
    import sys
    return hashlib.sha256(inspect.getsource(sys.modules[__name__]).encode()).hexdigest()
