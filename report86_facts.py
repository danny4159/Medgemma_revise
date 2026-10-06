"""PadChest-GR reference 문장 -> 평가 사실 분류(CPU, 모델 출력을 보지 않음). E 생성 전에 규칙과 수동 override를 hash로 잠근다.

fact class:
  pos_def        abnormal==True, 시간 변화 표현·불확실 표현·부정문이 아닌 현재 양성 소견 (주 recall 분모)
  pos_hedged     reference 자체가 probable/likely/suggestive 등 (민감도 분석에서만 recall 분모)
  pos_temporal   progression 필드 또는 시간 비교 표현이 있는 양성 소견 (현재 존재는 암시되나 주분석 제외, 민감도에 포함)
  pos_ambiguous  경계 사례(정상 상한 등)로 사람이 표시한 사실 (모든 분모 제외, 기록만)
  excluded       abnormal 표기와 문장 내용이 모순되거나 부재·해결 문장 (현재 양성 사실로 쓰지 않음)
  neg_specific   명시적·특정 소견의 부정(예: no pleural effusion) -> 모순 판정의 근거
  generic_normal 'no relevant findings' 등 범위 불명확한 정상/메타 문구 (질환별 음성으로 확장하지 않음)
  neg_scoped     '나머지에서'처럼 범위가 한정된 부정 (모순 근거로 쓰지 않음)
"""
import hashlib
import json
import re

from report86_common import ROOT, sha

NEG_START = re.compile(r"^\s*(no\b|there is no\b|without\b|not\b|i do not\b|rest\b|no other)", re.I)
NEG_ANY = re.compile(r"\b(no|not|without|free|clear|absence|absent|do not|does not|don't)\b", re.I)
HEDGE = re.compile(r"\b(probable|probably|likely|suggest\w*|compatible|possible|possibly|suspicio\w*|suspect\w*|may|could|might|perhaps|appear\w* to|rule out)\b", re.I)
# pg39의 TEMPORAL_RE는 QA 적격성용으로 'changes'·'increased'(크기 표현)까지 잡아 과도하다. 판독 사실에는 명시적 비교 표현만 쓴다.
TEMPORAL = re.compile(
    r"\b(unchanged|previous\w*|prior|compar\w*|new|resolv\w*|stable|worsen\w*|improv\w*|persist\w*|progress\w*|interval|again|"
    r"remain\w*|since|follow-?up|reduc\w*|ago|evolution|evolv\w*|decreas\w*|no (significant |major )?changes?|has increased|have increased|"
    r"increase in size|increased in size)\b", re.I)
ORIGIN_HEDGE = re.compile(r"\b(of|with)\s+(probable|possible)\s+\w+\s+(origin|etiology|aetiology|character)\b", re.I)
LIMIT_OF_NORMAL = re.compile(r"limit of normal", re.I)
SPECIFIC_NEG_TERMS = re.compile(r"(consolidat|infiltrat|effusion|nodul|mass|fractur|tubercul|condensation|opacit|sinus|angle|pneumothorax|pneumonia)", re.I)
SCOPED = re.compile(r"\b(rest of|remaining|other)\b", re.I)

# 사람이 reference 문장을 읽고 지정한 override: (ImageID 앞 8자, 문장 index) -> (class, 이유). 모델 출력 확인 전에 작성한다.
OVERRIDES = {}


def classify(f):
    s = f['sentence_en'].strip()
    abn = f.get('abnormal') is True
    prog = f.get('progression')
    if abn:
        if prog == 'resolved':
            return 'excluded', 'progression resolved (현재 부재)'
        if NEG_START.search(s) or re.search(r"\b(not appreciated|not mentioned|without (radiological )?alterations|without appreciating)\b", s, re.I):
            if SPECIFIC_NEG_TERMS.search(s) and re.search(r"without appreciating", s, re.I):
                return 'neg_specific', 'abnormal 표기가 있으나 특정 소견의 명시적 부정문'
            return 'excluded', 'abnormal 표기와 부정문 불일치'
        if prog is not None or TEMPORAL.search(s):
            return 'pos_temporal', 'progression/시간 표현'
        if LIMIT_OF_NORMAL.search(s):
            return 'pos_ambiguous', '정상 상한 경계 표현'
        if HEDGE.search(ORIGIN_HEDGE.sub('', s)):
            return 'pos_hedged', 'reference 불확실 표현'
        return 'pos_def', ''
    if NEG_ANY.search(s) and SPECIFIC_NEG_TERMS.search(s):
        if re.search(r"\b(rest of the study)\b", s, re.I):
            return 'neg_scoped', '범위 한정(나머지)'
        return 'neg_specific', ''
    return 'generic_normal', ''


def facts_for(cand):
    """cand: {ImageID, findings}. returns list of facts with stable ids F1.. in sentence order."""
    out = []
    for idx, f in enumerate(cand['findings']):
        cls, why = classify(f)
        ov = OVERRIDES.get((cand['ImageID'][:8], idx))
        if ov:
            cls, why = ov
        out.append({'fact_id': f'F{idx + 1}', 'sentence_idx': idx, 'sentence_en': f['sentence_en'], 'sentence_es': f.get('sentence_es'),
                    'abnormal_flag': f.get('abnormal'), 'labels': f.get('labels') or [], 'locations': f.get('locations') or [],
                    'progression': f.get('progression'), 'n_boxes': len(f.get('boxes') or []), 'fact_class': cls, 'class_reason': why,
                    'override': bool(ov)})
    return out


def eligible_abnormal(facts):
    return any(x['fact_class'] == 'pos_def' for x in facts)


def rules_sha():
    return sha(__file__)
