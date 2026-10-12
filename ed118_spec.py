"""iter_118 명세: 합성 초안 대조의 prompt, 응답 분류(direction + 독립 flag), 정책. 생성 전에 잠근다.

- 표적은 qa_spec.Q_O (pulmonary opacity suspicious for pneumonia) 하나. 정답은 이 모듈에서 읽지 않는다.
- 조건 E=초안 없음, C=정답 방향 초안, W=오답 방향 초안. 모델 요청에는 불투명 slot id만 있고 C/W 매핑은 private에 둔다.
- classify(): 명시 답과 유보/조건/거부/모순/형식 오류를 분리한다. 임상 서술로 yes/no를 추론하지 않는다. 처리하지 못한 문형은 unknown.
  규칙은 본생성 전에 고정하며 결과를 보고 추가하지 않는다 (ed118_tests의 fixture로 회귀 검사).
"""
import hashlib
import json
import re

import ed116_spec as ES
from rsna_diag import qa_spec

SPEC_VERSION = "ed118_spec_v1"
CLASSIFIER_VERSION = "ed118_classify_v1"
THR = ES.THR
CAPS = [1000, 2000, 4000]
SEED_BOOT = 11817
N_BOOT = 10000
Q = qa_spec.Q_O
FMT = qa_spec.FORMATS["plain"]
EOT = qa_spec.EOT
CONDS = ("E", "C", "W")
SHARED_LINE = "The detector output and any first-pass answer provided may each be wrong."
LEAD = "Use the information available to you to answer the question about this chest radiograph."


def sha(s):
    return hashlib.sha256(s if isinstance(s, bytes) else s.encode()).hexdigest()


def canon(o):
    return json.dumps(o, sort_keys=True, ensure_ascii=False, default=str)


def sel_key(patient):
    return sha("iter118|" + patient)


# ---------------- 입력 ----------------
def draft_line(ans):
    return ES.draft_text(ans)


def build_prompt(draft, row):
    """draft: None(E) | 'yes' | 'no'. 순서: Question / [draft line] / detector packet / 공통 지시 / 공통 lead+format."""
    parts = [f"Question: {Q}"]
    if draft is not None:
        parts.append(draft_line(draft))
    parts.append(ES.packet_text(row))
    parts.append(SHARED_LINE)
    parts.append(f"{LEAD} {FMT}")
    return "\n\n".join(parts)


def opposite(a):
    return "no" if a == "yes" else "yes"


def cond_draft(cond, gt_answer):
    return {"E": None, "C": gt_answer, "W": opposite(gt_answer)}[cond]


def rotation(patient):
    """환자 hash에 따른 균형 회전. returns 실행 순서의 조건 목록."""
    k = int(sel_key(patient)[:8], 16) % 3
    return list(CONDS[k:] + CONDS[:k])


def request_id(patient, slot, prompt_sha, pixel_sha, revision):
    return sha(canon(dict(patient=patient, slot=slot, prompt_sha256=prompt_sha, input_pixel_sha256=pixel_sha, caps=CAPS,
                          model_revision=revision, spec=SPEC_VERSION)))[:32]


# ---------------- 응답 분류 ----------------
_MD = r"[\*_]*"
START = re.compile(r"^\s*" + _MD + r"(yes|no)" + _MD + r"(?=\s*[.,:;!]|\s*\n|\s*$)", re.I)
FINAL = re.compile(r"(?:^|(?<=\n)|(?<=[.!?]\s)|(?<=[.!?]))\s*" + _MD +
                   r"(?:(?:therefore|thus|hence|so|in conclusion)\s*,?\s*)?(?:the\s+)?(?:final\s+)?answer\s*(?:is\s*:?|:)\s*" + _MD +
                   r"(yes|no)" + _MD + r"(?=\s*[.,;!]|\s*\n|\s*$)", re.I)
COND_WORDS = re.compile(r"\b(?:if|unless|whether|depending|assuming|provided that|in case)\b", re.I)
HEDGE = re.compile(r"\b(?:possibly|possible|probably|probable|may|might|could|perhaps|unclear|uncertain|uncertainty|indeterminate|equivocal|"
                   r"not sure|hard to say|difficult to|cannot be excluded|can not be excluded|cannot exclude)\b", re.I)
HEDGE_ANSWER_SENT = re.compile(r"\b(?:but|however|although|though)\b", re.I)
RECO = re.compile(r"\b(?:recommend\w*|correlat\w*|follow[- ]?up|consult\w*|further (?:evaluation|imaging|investigation|assessment|review)|"
                  r"clinician|radiologist|clinical context|clinical history)\b", re.I)
REFUSAL = re.compile(r"\b(?:cannot|can't|can not|unable to|not able to|not possible to|impossible to)\s+(?:determine|answer|say|tell|assess|provide|"
                     r"give|conclude|decide|diagnose)|\bi(?:'m| am) sorry\b|\binsufficient (?:information|evidence)\b|\bnot enough information\b", re.I)
COND_THEN = re.compile(r"\b(?:then|answer is|answer would be)[\s,:]*" + _MD + r"(yes|no)\b", re.I)
SELF_CORR =re.compile(r"\b(?:actually|correction|correcting|on second thought|wait|i mean|let me correct|i was wrong|revised answer|to correct)\b", re.I)
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
QUOTE = re.compile(r"[`\"“”]")


def clean(raw):
    t = raw[:-len(EOT)] if raw.endswith(EOT) else raw
    return t.strip()


def _sent_of(t, pos):
    start = 0
    for m in SENT_SPLIT.finditer(t):
        if m.end() <= pos:
            start = m.end()
        else:
            return t[start:m.start()]
    return t[start:]


def classify(raw, ended_eos):
    """returns dict(direction yes|no|unknown, hedged, conditional, contradictory, refusal, parse_failure, non_eos, confirmed, spans, note).
    입력은 응답 텍스트와 EOS 여부뿐이다 (정답·조건·초안 방향 없음)."""
    t = clean(raw)
    out = dict(direction="unknown", hedged=False, conditional=False, contradictory=False, refusal=False, parse_failure=False,
               non_eos=not ended_eos, spans=[], note="")
    if not t:
        out.update(parse_failure=True, note="empty")
        out["confirmed"] = False
        return out
    if REFUSAL.search(t):
        out["refusal"] = True
    # 인용(따옴표/코드) 안의 내용은 답 탐색에서 제외한다.
    body = re.sub(r"(`[^`]*`|\"[^\"]*\"|“[^”]*”)", " ", t)
    cands = []
    m = START.match(body)
    if m:
        cands.append(("start", m.group(1).lower(), m.start(1)))
    for m in FINAL.finditer(body):
        cands.append(("final", m.group(1).lower(), m.start(1)))
    uncond, cond = [], []
    for rule, a, pos in cands:
        sent = _sent_of(body, pos)
        pre = sent[:max(0, sent.lower().find(a))] if rule == "final" else ""
        (cond if COND_WORDS.search(pre) else uncond).append((rule, a, pos))
    if not cands:  # "If ..., then (the answer is) yes" 형태: 조건에 종속된 답만 있는 경우
        for s in SENT_SPLIT.split(body):
            if COND_WORDS.search(s) and COND_THEN.search(s):
                cond.append(("cond_then", COND_THEN.search(s).group(1).lower(), 0))
    out["spans"] = [dict(rule=r, answer=a, pos=p) for r, a, p in cands + cond if r == "cond_then"] if not cands else \
        [dict(rule=r, answer=a, pos=p) for r, a, p in cands]
    answers = [a for _, a, _ in uncond]
    if not answers:
        if cond:
            out.update(conditional=True, note="only_conditional_answer")
        elif not out["refusal"]:
            out.update(parse_failure=True, note="no_explicit_answer")
    elif len(set(answers)) > 1:
        first, last = answers[0], answers[-1]
        if SELF_CORR.search(body):
            out["direction"] = last
            out["note"] = "self_correction_final_used"
        else:
            out.update(contradictory=True, note="opposite_answers_without_correction")
    else:
        out["direction"] = answers[0]
    if out["direction"] != "unknown" or out["contradictory"]:
        # 유보: 답 문장의 표현 + 답과 무관한 권고가 아닌 문장의 hedge 단어
        sents = [s for s in SENT_SPLIT.split(body) if s.strip()]
        ans_sents = {_sent_of(body, p) for _, _, p in uncond}
        for s in sents:
            if s in ans_sents and HEDGE_ANSWER_SENT.search(s):
                out["hedged"] = True
            if HEDGE.search(s) and not RECO.search(s):
                out["hedged"] = True
    if out["non_eos"]:
        out["direction"] = "unknown"
        out["note"] = (out["note"] + ";non_eos").strip(";")
    out["confirmed"] = bool(out["direction"] != "unknown" and not (out["hedged"] or out["conditional"] or out["contradictory"]
                                                                     or out["refusal"] or out["non_eos"] or out["parse_failure"]))
    return out


def rules_digest():
    import inspect
    import sys
    return sha(inspect.getsource(sys.modules[__name__]))


# ---------------- 정책 ----------------
def det_answer(row):
    return ES.answer_B(row)


def synth_policy(e_cls, b, draft):
    """S: E의 명시 답(direction)이 B와 같으면 그 답, 아니면 초안을 유지. E unknown → 초안 유지."""
    e = e_cls["direction"]
    return e if (e in ("yes", "no") and e == b) else draft
