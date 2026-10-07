"""iter_096 reference 구조화(수동 인코딩). 원문은 results/iter_095/lock/reference_target.json의 sentence.

양성 reference fact -> alts(대안 위치/종류). 위치 표기는 report96_sem scope와 동일 (sides, level, type).
type: 'lobe'|'zone'|'lung'|None ; sides None = reference에 위치 없음(위치 비교 불가, 종류/시간만 사용).
temporal: ref 문장이 말하는 시간 변화 (decrease|persistent|increase|new|None)
cause: reference가 말하는 원인 (infection 등) — 일치하는 원인 표현만 'cause 지지'
인코딩 근거는 각 항목의 note. lobe/zone 대응이 불확실한 reference 표현은 type을 None이 아닌 'zone'(해부 표현이 영상 구역)으로 둔다.
"""
OPAC = {'opacity', 'infiltrate', 'consolidation'}
OPAC_AT = OPAC | {'atelectasis'}

POS_FACTS = {
    # key: (patient_idx, fact_id)
    (0, 'F4'): dict(note='retrocardiac consolidation decreased in size', temporal='decrease', cause=None,
                    alts=[dict(strict={'consolidation'}, len=OPAC, sides='L', level='L', type='zone')]),
    (1, 'F1'): dict(note='right basal infiltrate, infectious-inflammatory', temporal=None, cause='infection',
                    alts=[dict(strict={'infiltrate'}, len=OPAC, sides='R', level='L', type='zone')]),
    (2, 'F2'): dict(note='persistent atelectasis-condensation (위치 없음)', temporal='persistent', cause=None,
                    alts=[dict(strict={'atelectasis', 'consolidation'}, len=OPAC_AT, sides=None, level=None, type=None)]),
    (3, 'F1'): dict(note='slight retrocardiac infiltrate', temporal=None, cause=None,
                    alts=[dict(strict={'infiltrate'}, len=OPAC, sides='L', level='L', type='zone')]),
    (4, 'F1'): dict(note='decrease in bilateral basal infiltrates', temporal='decrease', cause=None,
                    alts=[dict(strict={'infiltrate'}, len=OPAC, sides='RL', level='L', type='zone')]),
    (4, 'F2'): dict(note='persistent slight right basal atelectasis', temporal='persistent', cause=None,
                    alts=[dict(strict={'atelectasis'}, len={'atelectasis'}, sides='R', level='L', type='zone')]),
    (5, 'F2'): dict(note='opacities in both vertices (right>left) and right lower lobe of new appearance', temporal=None, cause=None,
                    alts=[dict(strict={'opacity'}, len=OPAC, sides='RL', level='U', type='zone', temporal=None),
                          dict(strict={'opacity'}, len=OPAC, sides='R', level='L', type='lobe', temporal='new')]),
    (6, 'F1'): dict(note='increased infiltrate in right lung base', temporal='increase', cause=None,
                    alts=[dict(strict={'infiltrate'}, len=OPAC, sides='R', level='L', type='zone')]),
    (7, 'F1'): dict(note='small poorly defined infiltrate at left cardiac border (level 불명: M 또는 L)', temporal=None, cause=None,
                    alts=[dict(strict={'infiltrate'}, len=OPAC, sides='L', level='ML', type='zone')]),
    (8, 'F1'): dict(note='laminar atelectasis in lingula and middle lobe', temporal=None, cause=None,
                    alts=[dict(strict={'atelectasis'}, len={'atelectasis'}, sides='RL', level='M', type='lobe')]),
}

# 명시적 부재 reference. direct=직접 부정된 종류, qualified=수식으로 범위가 좁은 종류, scoped=범위 제한 문장
NEG_REF = {
    9: dict(direct={'infiltrate', 'consolidation'}, qualified=set(), scoped=False),
    10: dict(direct={'consolidation'}, qualified={'opacity'}, scoped=False),       # 'significant pulmonary opacities'
    11: dict(direct={'infiltrate'}, qualified={'consolidation'}, scoped=False),    # 'infiltrates suggestive of consolidation'
    12: dict(direct=set(), qualified={'opacity', 'consolidation'}, scoped=True),   # 'In the rest of the study ... pathological appearance'
    13: dict(direct={'infiltrate', 'consolidation'}, qualified=set(), scoped=False),
    14: dict(direct={'consolidation', 'nodule'}, qualified=set(), scoped=False),
    15: dict(direct={'consolidation', 'nodule'}, qualified=set(), scoped=False),
    16: dict(direct={'consolidation'}, qualified=set(), scoped=False),
}


def region_scope(region):
    """질문 영역 문자열 -> scope dict."""
    r = region.lower()
    if r == 'g':
        return dict(sides='RL', level=None, type='lung', src='question')
    sides = 'L' if r.startswith('left') else 'R'
    for lv, w in (('U', 'upper'), ('M', 'mid'), ('L', 'lower')):
        if w in r:
            return dict(sides=sides, level=lv, type='zone', src='question')
    return dict(sides=sides, level=None, type='lung', src='question')
