"""iter_123: MR-RATE 뇌실주위 백질 FLAIR 고신호 존재/부재 정답 후보 (결정적 규칙 mr123_rules_v1).

기존 batch04·batch23의 공식 train만 사용. 정규식은 문장 후보 검색용이며 선정 사례마다 원문 span을 남긴다.
"""
import hashlib, json, re, sys
import pandas as pd

BASE = '/home/test/.local/share/medgemma/mr_rate/meta/'
BATCHES = ['batch04', 'batch23']
RULES = 'mr123_rules_v1'
SEED = 122

HYPER = re.compile(r'hyperintens|increased signal|high signal|signal increase|hypersignal', re.I)
UNCERT = re.compile(r'\b(may|might|possible|possibly|probably|suspect|suspicious|suggest|cannot|can not|question|differential|likely|versus|vs\.?|or )\b|\?', re.I)
NEGW = re.compile(r'\b(no|not|without|absent|nor|neither)\b', re.I)
EXCEPT = re.compile(r'\b(except|exception|apart from|other than|excluding|excluded|but|however|although|whereas|aside)\b', re.I)
PERIV = re.compile(r'periventricular|peri-ventricular|paraventricular|periventriculer', re.I)
WM = re.compile(r'white matter|\bwm\b', re.I)
ABN_ANY = re.compile(r'gliotic|gliosis|hyperintens|increased signal|high signal|lesion|demyelinat|leukoaraiosis|ischemic|plaque|\bfoci\b|focus|changes|abnormal signal|signal alteration|signal changes|hypointens|encephalomalac|infarct|microangiopath|leukomalacia|edema|dilat|prominen', re.I)
NORMAL = re.compile(r'\bnormal\b|no (abnormal|pathological|pathologic) (signal|intensity)|no (signal|intensity) (abnormal|alteration|change)|signal (intensity )?(is|was|are|were) (normal|unremarkable)|unremarkable|no (abnormal )?signal (change|alteration|abnormality)', re.I)


def sents(text):
    if not isinstance(text, str):
        return []
    out = []
    for line in re.split(r'\n+', text):
        for s in re.split(r'(?<=[.!?])\s+(?=[A-Z0-9])', line.strip()):
            s = s.strip()
            if s:
                out.append(s)
    return out


def classify_sentence(s):
    """returns one of: pos, neg, other_periv (conflict candidate), none"""
    if not PERIV.search(s):
        return 'none'
    has_wm = bool(WM.search(s))
    if has_wm and 'flair' in s.lower() and HYPER.search(s) and not NEGW.search(s) and not UNCERT.search(s) \
            and not EXCEPT.search(s) and not re.search(r'perivascular|virchow|physiolog', s, re.I) \
            and not re.search(r'\bnormal\b', s, re.I):
        return 'pos'
    if has_wm and NORMAL.search(s) and not EXCEPT.search(s) and not UNCERT.search(s) \
            and not re.search(r'normal (variant|for)', s, re.I) \
            and not re.search(r'\b(lesion|gliotic|gliosis|hyperintens|foci|focus|increased signal)\b', s, re.I) or \
            (has_wm and re.search(r'\bno (abnormal )?(signal|lesion|hyperintens)', s, re.I) and not EXCEPT.search(s) and not UNCERT.search(s)
             and not re.search(r'normal (variant|for)', s, re.I)):
        return 'neg'
    if ABN_ANY.search(s):
        return 'other_periv'
    return 'none'


def label_report(findings, impression):
    ss = [('findings', s) for s in sents(findings)] + [('impression', s) for s in sents(impression)]
    cls = [(sec, s, classify_sentence(s)) for sec, s in ss]
    pos = [(sec, s) for sec, s, c in cls if c == 'pos']
    neg = [(sec, s) for sec, s, c in cls if c == 'neg']
    oth = [(sec, s) for sec, s, c in cls if c == 'other_periv']
    # 상충 검사: 다른 periventricular 이상 문장이 있으면 unknown. 같은 문장이 반복되는 것은 허용.
    allsent = ' '.join(s for _, s, _ in cls)
    if pos and neg:
        return 'unknown', 'pos_neg_conflict', pos, neg, oth
    if pos:
        if oth:
            # 동일 소견을 다른 표현으로 반복한 문장(pos 와 같은 방향의 이상 기술)은 허용하지 않고 보수적으로 unknown
            return 'unknown', 'pos_with_other_periv_sentence', pos, neg, oth
        return 'positive', 'ok', pos, neg, oth
    if neg:
        if oth:
            return 'unknown', 'neg_with_periv_abnormality', pos, neg, oth
        for _, sx, _c in cls:
            if WM.search(sx) and HYPER.search(sx) and not NEGW.search(sx):
                return 'unknown', 'neg_with_other_wm_hyperintensity', pos, neg, oth
        # 보고서 어디서든 white matter 병변 이상이 periventricular 외 표현(예: deep white matter)이어도 범위 밖이라 허용
        return 'negative', 'ok', pos, neg, oth
    return 'unknown', 'no_explicit', pos, neg, oth


def load_candidates():
    sp = pd.read_csv(BASE + 'splits.csv')
    sp = sp[sp.batch_id.isin(BATCHES)]
    rows = []
    for b in BATCHES:
        r = pd.read_csv(BASE + f'reports/{b}_reports.csv')
        r['batch_id'] = b
        rows.append(r)
    r = pd.concat(rows)
    r = r.merge(sp[['batch_id', 'patient_uid', 'study_uid', 'split']], on=['batch_id', 'study_uid'], how='inner')
    assert (r.split == 'train').sum() > 0
    r = r[r.split == 'train'].copy()  # test/val 보고서는 라벨링에 쓰지 않는다
    out = []
    for t in r.itertuples():
        lab, why, pos, neg, oth = label_report(t.findings, t.impression)
        out.append(dict(batch_id=t.batch_id, patient_uid=int(t.patient_uid), study_uid=t.study_uid, split=t.split,
                        label=lab, reason=why, pos_spans=pos, neg_spans=neg, other_spans=oth))
    return pd.DataFrame(out)


if __name__ == '__main__':
    c = load_candidates()
    print(c.groupby(['batch_id', 'label']).size())
    print(c[c.label != 'unknown'].groupby('reason').size())
    print(c.groupby('reason').size())
