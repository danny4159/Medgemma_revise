"""iter_096 의미 판정 규칙: 문장 -> 구조화된 주장(claim). 소견 존재/원인/시간/부정 종류/범위를 분리해 기록한다.

이 모듈은 '초안 생성기 + 규약'이다. 최종 판정은 문장 단위 검토표(results/iter_096/judging/sentence_review.json)에서
assistant가 원문을 읽고 확정한 값이며, 규칙 출력과 다른 문장은 OVERRIDES에 이유와 함께 남긴다.
조건명(G/L/D)은 보지 않는 O-id 기준이나 영역 이름은 보이므로 독립 눈가림이 아니며 전문의 검토도 아니다.

claim 필드
  pol      P(현재 존재 서술) | N(부정)
  kind     opacity|infiltrate|consolidation|atelectasis|pneumonia(원인 부정 전용)|nodule|clear(정상 폐 실질 서술)
  neg      N일 때: specific(소견 이름을 직접 부정) | clear(폐 실질 정상 서술) | qualified(급성/의심/clear 등 수식으로 범위가 좁은 부정)
  pres     definite | hedged  (소견 자체의 존재 확실성. 'which may represent X'는 원인 hedge이며 존재 hedge가 아님)
  cause    원인/진단 표현 목록 [{'name','cert'}] (cert: hedged|probable|concern)
  temporal new|unchanged|again|resolved|still|None
  scope    {'sides':'R'|'L'|'RL'|None, 'level':'U'|'M'|'L'|None, 'type':'lung'|'lobe'|'zone'|None, 'src':'text'|'question'}
           sides/level/type이 None이면 원문에 위치가 없다. 평가기가 질문 범위/전역 해석을 적용한다.
"""
import re

KIND_PATS = [('atelectasis', r'atelecta|collaps'),
             ('consolidation', r'consolidat|condensation|airspace disease'),
             ('infiltrate', r'infiltrat'),
             ('opacity', r'opacit|opacif|increased density|\bopaque\b'),
             ('nodule', r'\bnodule\b')]
NEG_CUE = re.compile(r'\b(no|not|without|free of|absent|negative for)\b|\bnor\b|do not (identify|appreciate)|have resolved|\bresolved\b', re.I)
PRES_HEDGE = re.compile(r'\b(possible|possibly|probable|questionable|suspected|equivocal)\b|cannot be (excluded|ruled out)', re.I)
CAUSE_CUE = re.compile(r'(which|that)?\s*(may|could|might)\s+represent\s+(?P<c>.+?)(?:\.|$)|(?P<k>concern(ing)? for|worrisome for|consistent with|suggesting|suggestive of)\s+(?P<c2>.+?)(?:\.|$)', re.I)
CAUSE_NAMES = [('pneumonia', r'pneumonia|pneumonitis'), ('infection', r'infection|infectious|infected'), ('aspiration', r'aspiration'),
               ('granuloma', r'granuloma'), ('atelectasis', r'atelectasis'), ('mass', r'\bmass\b'), ('scarring', r'scarr'),
               ('skin lesion', r'skin lesion'), ('infiltrate', r'infiltrate')]
TEMP = [('resolved', r'\bresolved\b'), ('unchanged', r'\bunchanged\b'), ('still', r'\bstill\b'), ('again', r'\bagain\b|in comparison'),
        ('new', r'\bnew\b|since the prior|from the prior')]
GENERIC_NORMAL = re.compile(r'^(no (acute )?(significant|relevant|other relevant)? ?findings?|no findings|within normal limits|no significant radiological findings|no other relevant findings)', re.I)


def split_sentences(text):
    """(start, end, sentence) 목록. 번호 목록 접두 '1. '은 문장에서 제외하되 offset은 원문 기준."""
    out = []
    pos = 0
    for m in re.finditer(r'[^.;]+(?:\.(?!\s|$)[^.;]*)*[.;]?', text):
        s = m.group(0)
        if not s.strip():
            continue
        st = m.start() + (len(s) - len(s.lstrip()))
        sent = s.strip()
        mm = re.match(r'^\d+\.\s*', sent)
        if mm:
            st += mm.end()
            sent = sent[mm.end():]
        if sent:
            out.append((st, st + len(sent), sent))
    return out


def _scope(sent, region):
    s = sent.lower()
    sides = set()
    if re.search(r'bibasilar|bibasal|both|bilateral|\blungs\b|upper lungs|lung bases', s):
        if not re.search(r'\b(left|right)\b', s) or re.search(r'bibasilar|bilateral|both|\blungs\b', s):
            sides = {'R', 'L'}
    if not sides:
        if re.search(r'\bright\b', s):
            sides.add('R')
        if re.search(r'\bleft\b', s):
            sides.add('L')
    level, typ = None, None
    if re.search(r'bibasilar|bibasal|lung bases|\bbase\b|basal|\bbases\b', s):
        level, typ = 'L', 'zone'
    elif re.search(r'lower lobe', s):
        level, typ = 'L', 'lobe'
    elif re.search(r'upper lobe', s):
        level, typ = 'U', 'lobe'
    elif re.search(r'middle lobe|lingula', s):
        level, typ = 'M', 'lobe'
    elif re.search(r'upper (lung|zone|lungs)|apical', s):
        level, typ = 'U', 'zone'
    elif re.search(r'mid lung|mid zone', s):
        level, typ = 'M', 'zone'
    elif re.search(r'lower (lung|zone|fields)', s):
        level, typ = 'L', 'zone'
    if sides and level is None:
        typ = 'lung'
    if not sides and level is not None:  # 측면 없는 'upper lungs' 등은 위에서 처리됨
        sides = {'R', 'L'}
    if not sides:
        return {'sides': None, 'level': None, 'type': None, 'src': 'question'}
    plural = bool(re.search(r'\blungs\b', s)) and not re.search(r'\b(both|bilateral)\b', s)  # 'The lungs are clear' 류: 질문 영역으로 좁혀 읽을 수 있는 복수 표현
    return {'sides': ''.join(sorted(sides, reverse=True)), 'level': level, 'type': typ, 'src': 'text', 'plural': plural}


def _kinds(sent):
    return [k for k, p in KIND_PATS if re.search(p, sent, re.I)]


def _causes(sent):
    out = []
    m = re.search(r'(?:which |that )?(?:may|could|might) represent (.+)$|(concern(?:ing)? for|worrisome for|consistent with|suggesting|suggestive of) (.+)$', sent, re.I)
    if not m:
        return out
    cert = 'hedged' if m.group(1) else ('probable' if (m.group(2) or '').lower().startswith('consistent') else 'concern')
    tail = (m.group(1) or m.group(3) or '')
    for name, pat in CAUSE_NAMES:
        if re.search(pat, tail, re.I):
            out.append({'name': name, 'cert': cert})
    return out


def _temporal(sent):
    for t, p in TEMP:
        if re.search(p, sent, re.I):
            return t
    return None


def _c(pol, kind, sides, level, typ, **kw):
    d = dict(pol=pol, kind=kind, neg=kw.get('neg'), pres='definite', cause=kw.get('cause', []), temporal=kw.get('temporal'),
             scope={'sides': sides, 'level': level, 'type': typ, 'src': 'text', 'plural': False})
    return d


# 문장 단위 검토에서 규칙 초안이 틀려 수정한 문장. 값: (claims, 이유)
OVERRIDES = {
    'The left lung is opaque, with a left pleural effusion and left basal atelectasis.':
        ([_c('P', 'opacity', 'L', None, 'lung'), _c('P', 'atelectasis', 'L', 'L', 'zone')],
         '규칙 초안이 두 소견에 basal 범위를 공유시킴: opaque는 왼쪽 폐 전체, atelectasis는 왼쪽 기저'),
    'Increased density in both lung fields, predominantly in the lower fields [0.29,0.53,0.26,0.27] [0.72,0.54,0.26,0.29].':
        ([_c('P', 'opacity', 'RL', None, 'lung')],
         '양쪽 폐야 전체의 증가 음영(하부 우세): 하부로 축소하지 않고 양측 전체 범위로 기록(하부 우세는 보조)'),
}


def analyze_sentence(sent, region):
    """규칙 초안 + 검토 수정. 반환: claim dict 목록(quote는 sent 전체)."""
    if sent in OVERRIDES:
        return [dict(c, scope=dict(c['scope'])) for c in OVERRIDES[sent][0]]
    s = sent.strip()
    low = s.lower()
    if re.search(r'\[\s*0?\.\d+\s*,', s) and not _kinds(s):
        return []  # 좌표 포함 비폐실질 소견(심비대 등)
    claims = []
    kinds = _kinds(s)
    sc = _scope(s, region)
    if re.search(r'lungs? (is|are) clear|\bclear lungs?\b|lungs? (is|are) grossly clear', low) or \
            re.search(r'pulmonary parenchyma (and the cardiomediastinal silhouette are normal|shows a normal structure|without major alterations)', low):
        claims.append(dict(pol='N', kind='clear', neg='clear', pres='definite', cause=[], temporal=None, scope=sc))
        if re.search(r'without focal consolidation', low):
            claims.append(dict(pol='N', kind='consolidation', neg='specific', pres='definite', cause=[], temporal=None, scope=sc))
        return claims
    neg = bool(NEG_CUE.search(s))
    if neg:
        # 부정문: 'no X, Y or Z' 열거. 수식 확인
        acute = bool(re.search(r'\bacute\b', low))
        qualified = acute or bool(re.search(r'suspicious|clear condensations|resolved|pathological', low))
        ntype = 'qualified' if qualified else 'specific'
        for k in kinds:
            if k in ('atelectasis', 'nodule') and not re.search(k[:6], low):
                continue
            claims.append(dict(pol='N', kind=k, neg=ntype, pres='definite', cause=[], temporal='resolved' if 'resolved' in low else None, scope=sc))
        if re.search(r'pneumonia|pneumonitis', low):
            claims.append(dict(pol='N', kind='pneumonia', neg='qualified' if acute else 'specific', pres='definite', cause=[], temporal=None, scope=sc))
        if re.search(r'(lung disease|pulmonary changes)', low) and re.search(r'acute or chronic', low):
            claims.append(dict(pol='N', kind='clear', neg='clear', pres='definite', cause=[], temporal=None, scope=sc))
        return claims
    pres = 'hedged' if PRES_HEDGE.search(s) else 'definite'
    cs = _causes(s)
    tmp = _temporal(s)
    for k in kinds:
        if k == 'infiltrate' and cs and any(c['name'] == 'infiltrate' for c in cs) and 'opacity' in kinds:
            continue  # 'opacity ... may represent an acute infiltrate': infiltrate는 원인 후보, 별도 존재 주장이 아님
        if k == 'atelectasis' and 'opacity' in kinds and any(c['name'] == 'atelectasis' for c in cs):
            continue
        claims.append(dict(pol='P', kind=k, neg=None, pres=pres, cause=cs, temporal=tmp, scope=sc))
    return claims


def _sig(c):
    sc = c['scope']
    return (c['pol'], c['kind'], c['neg'], c['pres'], c['temporal'], sc['sides'], sc['level'], sc['type'], tuple((x['name'], x['cert']) for x in c['cause']))


def analyze_text(text, region):
    """출력 전체 -> [{start,end,quote,claims:[...],dup_claims:n}] (문장 단위, claim도 dup도 없는 문장은 생략).
    번호 목록 등으로 같은 출력 안에서 동일 속성(극성·종류·범위·시간·원인)의 주장이 반복되면 첫 번째만 세고 dup_claims로 기록한다."""
    out, seen = [], set()
    for st, en, sent in split_sentences(text):
        cl, dup = [], 0
        for c in analyze_sentence(sent, region):
            k = _sig(c)
            if k in seen:
                dup += 1
                continue
            seen.add(k)
            cl.append(c)
        if cl or dup:
            out.append({'start': st, 'end': en, 'quote': sent, 'claims': cl, 'dup_claims': dup})
    return out
