"""iter_093 보수적 의미 민감도 규칙. report93_fixtures.py의 사전 고정 정답으로만 검증한 한정 규칙이며 범용 평가기가 아니다.
출력: supported / contradicted / undecidable. 미표기를 음성으로, 단어 부분 일치를 위치 일치로 쓰지 않는다."""
import re

MINOR = ('scoliosis', 'gynecomastia', 'metallic', 'prosthesis', 'pacemaker', 'osteosynthesis', 'sternotomy', 'catheter', 'tube')
PULM = ('infiltrate', 'consolidation', 'alveolar', 'atelectasis', 'nodule', 'mass', 'fibrosis', 'fibrotic', 'chronic pulmonary', 'neoplasm', 'ground glass', 'bulla', 'cavit')
MED = ('mediastinal', 'aortic', 'goiter', 'hilar', 'hilum', 'tracheal')
BONE = ('scoliosis', 'fracture', 'kyphosis', 'spondylosis', 'osteopenia', 'vertebral', 'degenerative')
ACUTE = ('infiltrate', 'alveolar', 'consolidation', 'pleural effusion', 'pneumothorax', 'edema')
FAMILY = {'pleural effusion': ('pleural effusion',), 'pneumothorax': ('pneumothorax',), 'pulmonary nodule/mass': ('nodule', 'mass'),
          'infiltrate/consolidation': ('infiltrate', 'consolidation', 'alveolar'), 'humeral prosthesis': ('prosthesis',),
          'central venous catheter': ('catheter',), 'pacemaker': ('pacemaker',)}
SITES = ('jugular', 'subclavian', 'femoral')
TYPES = (('biventricular', 'biventricular'), ('dual', 'dual'), ('bicameral', 'dual'), ('single', 'single'), ('monochamber', 'single'))


def text(a):
    return (a['finding'] + ' ' + a.get('location', '') + ' ' + a.get('attributes', '')).lower()


def has(refs, words, positive=True, definite=True):
    return [a for a in refs if (a['polarity'] == 'positive') == positive and (a['certainty'] == 'definite' or not definite)
            and any(w in a['finding'].lower() for w in words)]


def positives(refs, definite=True):
    return [a for a in refs if a['polarity'] == 'positive' and (a['certainty'] == 'definite' or not definite)]


def nsf(refs):
    return [a for a in refs if a['polarity'] == 'negative' and a['finding'] in ('no significant finding', 'other relevant finding')]


def sides(s):
    return {w for w in ('left', 'right', 'bilateral') if re.search(r'\b' + w + r'\b', s.lower())}


def kinds(s, table):
    s = s.lower()
    return {v for k, v in table if re.search(r'\b' + k + r'\b', s)}


def judge(group, quote, finding, refs, stated=()):
    q = quote.lower()
    if group in ('generic_normal', 'other_scope'):
        pos = positives(refs)
        if group == 'other_scope':
            cand = [a for a in pos if not any(w in a['finding'].lower() or a['finding'].lower() in w for w in stated)]
            if cand:
                return 'contradicted'
            return 'supported' if nsf(refs) else 'undecidable'
        if finding == 'chest abnormality':
            major = [a for a in pos if not any(m in a['finding'].lower() for m in MINOR)]
        elif finding == 'pulmonary opacity':
            major = [a for a in pos if any(m in text(a) for m in PULM)]
        elif finding == 'mediastinal abnormality':
            major = [a for a in pos if any(m in text(a) for m in MED)]
        elif finding == 'osseous abnormality':
            major = [a for a in pos if any(m in a['finding'].lower() for m in BONE)]
        else:
            major = [a for a in pos if not any(m in a['finding'].lower() for m in MINOR)]
        if major:
            return 'contradicted'
        if pos:
            return 'undecidable'
        return 'supported' if nsf(refs) else 'undecidable'
    if group == 'acute_negation':
        if has(refs, ACUTE):
            return 'contradicted'
        if has(refs, ACUTE, definite=False):
            return 'undecidable'
        return 'supported' if nsf(refs) else 'undecidable'
    if group == 'specific_negation':
        fam = FAMILY[finding]
        if has(refs, fam):
            return 'contradicted'
        if has(refs, fam, positive=False):
            return 'supported'
        return 'undecidable'
    if group == 'location_attribute':
        fam = FAMILY[finding]
        match = [a for a in refs if a['polarity'] == 'positive' and any(w in a['finding'].lower() for w in fam)]
        if not match:
            return 'undecidable'
        a = match[0]
        rt = (a.get('location', '') + ' ' + a.get('attributes', '')).lower()
        agree = conflict = False
        for o, r in ((sides(q), sides(rt)), (kinds(q, tuple((s, s) for s in SITES)), kinds(rt, tuple((s, s) for s in SITES))),
                     (kinds(q, TYPES), kinds(rt, TYPES))):
            if o and r:
                if o == r:
                    agree = True
                else:
                    conflict = True
        if conflict:
            return 'contradicted'
        return 'supported' if agree else 'undecidable'
    raise ValueError(group)
