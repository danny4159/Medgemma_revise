"""iter_101 자연 충돌·보존 사실·donor·교정 요청 잠금 (교정 생성 전에 한 번 실행).

입력: 완료·변조 검증을 통과한 S24 CURE 원출력(report101_req.load_cure).
수동(assistant) 판정표 CLAIMS: 원 출력(좌표 제거 후)의 흉수 존재/부재 주장을 (source, status, side, quote)로 기록한다.
  quote는 원문의 부분문자열이어야 하며 코드가 검증한다. 충돌 여부는 이 주장표에서 규칙으로 도출한다(수동 지정 금지).
  전문의 검토가 아니며 assistant 판정이다. 판정은 교정 출력을 보기 전에 작성했다.
충돌 규칙(계획): 같은 소견(흉수)에서 한 source의 존재 주장과 다른 source의 명시 부정이 같은 쪽(side)을 덮을 때 명확한 충돌.
  - 좌측 양성 vs 우측만의 부정, 'no acute findings' 류, 크기 제한 부정은 충돌이 아니다.
  - 쪽이 명시되지 않은 양성(unspec)은 다른 source의 부정이 양쪽(whole/both)을 덮거나 L·R 부정의 합집합이 양쪽을 덮을 때만 충돌이다. 단일 쪽 부정만 있으면 ambiguous로 기록하고 세지 않는다.
"""
import json
import sys
from pathlib import Path

from report86_common import ROOT, sha, sha_obj, save
import report101_req as RQ

R101 = ROOT / 'results/iter_101'
DATA = R101 / 'data'
LOCK = DATA / 'lock'

# ---- 수동 판정표 (S24 입력 순서 index → 주장 목록) ----
def _n(side, quote):  # note neg
    return ('CL' if side == 'L' else 'CR', 'neg', side, quote)

CLAIMS = {
    0: [('G', 'neg', 'whole', 'No pleural effusion is appreciated'), _n('L', 'No pleural effusions'), _n('R', 'No pleural effusions')],
    1: [('G', 'neg', 'whole', 'No pleural effusion is appreciated'), _n('L', 'No pleural effusions'), _n('R', 'No pleural effusions')],
    2: [('G', 'neg', 'whole', 'There is no evidence of pleural effusion or thickening'), _n('L', 'No pleural effusions'), _n('R', 'No pleural effusions')],
    3: [('G', 'neg', 'whole', 'No pleural effusion is appreciated'), _n('L', 'No pleural effusions'), _n('R', 'No pleural effusions')],
    4: [_n('L', 'No pleural effusions'), _n('R', 'No pleural effusions')],
    5: [('G', 'pos', 'both', 'Significant bilateral pleural effusion'), ('CL', 'pos', 'both', 'Moderate bilateral pleural effusions are unchanged'),
        ('CR', 'pos', 'both', 'Moderate bilateral pleural effusions are unchanged')],
    6: [('G', 'pos', 'L', 'Left pleural effusion'), ('CL', 'pos', 'L', 'small left pleural effusion'), _n('R', 'There is no pneumothorax or pleural effusion')],
    7: [('G', 'neg', 'whole', 'I do not appreciate pleural effusion'), _n('L', 'No pleural effusion or pneumothorax'), _n('R', 'No pleural effusion or pneumothorax')],
    8: [_n('L', 'No pleural effusions'), _n('R', 'No pleural effusions')],
    9: [_n('L', 'No pleural effusions'), _n('R', 'No pleural effusions')],
    10: [('G', 'neg', 'whole', 'There is no evidence of effusion'), _n('L', 'No pleural effusions'), _n('R', 'No pleural effusions')],
    11: [_n('L', 'No pleural effusion or pneumothorax is seen'), _n('R', 'No pleural effusions')],
    12: [('G', 'pos', 'unspec', 'Pleural effusion'), _n('L', 'There is no pneumothorax or pleural effusion'), _n('R', 'There is no pneumothorax or pleural effusion')],
    13: [('G', 'neg', 'whole', 'There is no evidence of pleural effusion or thickening'), _n('L', 'No pleural effusion or pneumothorax'), _n('R', 'No pleural effusion or pneumothorax')],
    14: [('G', 'neg', 'whole', 'There is no evidence of pleural effusion or thickening'), _n('L', 'No pleural effusion or pneumothorax'), _n('R', 'No pleural effusion or pneumothorax')],
    15: [('G', 'pos', 'L', 'left pleural effusion'), ('CL', 'pos', 'L', 'left-sided pleural effusion'), ('CR', 'pos', 'R', 'Small right pleural effusion')],
    16: [('G', 'pos', 'both', 'Bilateral pleural effusion'), _n('L', 'There is no pneumothorax or pleural effusion'), ('CR', 'pos', 'R', 'small right pleural effusion')],
    17: [('G', 'pos', 'both', 'bilateral pleural effusion'), ('CL', 'pos', 'L', 'left-sided pleural effusion'), ('CR', 'pos', 'both', 'Bilateral pleural effusions')],
    18: [('G', 'pos', 'both', 'Bilateral pleural effusion'), ('CL', 'pos', 'both', 'bilateral pleural effusions'), ('CR', 'pos', 'both', 'Bilateral pleural effusions')],
    19: [('G', 'pos', 'both', 'Bilateral pleural effusion'), ('CL', 'pos', 'L', 'left pleural effusion'),
         ('CR', 'pos', 'both', 'moderate right pleural effusion and a small left pleural effusion')],
    20: [('G', 'pos', 'both', 'bilateral pleural effusion'), ('CL', 'pos', 'L', 'moderate left pleural effusion'),
         ('CR', 'pos', 'both', 'moderate right pleural effusion and a small left pleural effusion')],
    21: [('G', 'pos', 'L', 'Left pleural effusion'), ('CL', 'pos', 'L', 'left-sided pleural effusion'),
         _n('R', 'No evidence of pneumonia, pleural effusion or pneumothorax')],
    22: [('G', 'pos', 'R', 'Small right pleural effusion'), ('CL', 'pos', 'both', 'Small bilateral pleural effusions'),
         ('CR', 'pos', 'both', 'Small bilateral pleural effusions')],
    23: [('G', 'pos', 'both', 'Bilateral pleural effusion'), _n('L', 'There is no pleural effusion or pneumothorax'), _n('R', 'No pleural effusions')],
}

# ---- 선정 환자의 초안 원자 사실(P=reference가 지지, U=reference에 없음(unknown), Q=reference가 명시 반박) ----
# 주상태 atom은 kind='main'. support는 reference 원문 문장. need_sides는 reference가 요구하는 흉수 위치.
ATOMS = {
    12: {'ref_state': 'POS', 'need_sides': 'any', 'atoms': [
        ('A1', 'P', 'catheter', 'Central venous catheter via right jugular vein, with the tip in the superior vena cava', 'Central venous catheter via right jugular vein, with the tip in the superior vena cava.'),
        ('A2', 'P', 'device', 'Nasogastric tube', 'Nasogastric tube.'),
        ('A3', 'P', 'finding', 'Increased retrocardiac density in relation to atelectasis', 'Increased retrocardiac density in relation to atelectasis.'),
        ('A4', 'P', 'main', 'Pleural effusion', 'Pleural effusion.'),
        ('A5', 'P', 'finding', 'Cardiomediastinal silhouette within normal limits', 'Cardiomediastinal silhouette within normal limits.')]},
    16: {'ref_state': 'POS', 'need_sides': 'both', 'atoms': [
        ('A1', 'P', 'main', 'Bilateral pleural effusion', 'Bilateral pleural effusion.'),
        ('A2', 'P', 'finding', 'The right basal consolidation persists slightly', 'The right basal consolidation persists slightly.')]},
    23: {'ref_state': 'POS', 'need_sides': 'both', 'atoms': [
        ('A1', 'P', 'finding', 'Small retrocardiac interstitial-alveolar infiltrate', 'Small retrocardiac interstitial-alveolar infiltrate.'),
        ('A2', 'P', 'main', 'Bilateral pleural effusion', 'Bilateral pleural effusion.'),
        ('A3', 'P', 'finding', 'Bibasal nodules with radiolucent halo, suggestive of corresponding to nipples', 'Bibasal nodules with radiolucent halo, suggestive of corresponding to nipples.'),
        ('A4', 'P', 'finding', 'Right diaphragmatic lobulation', 'Right diaphragmatic lobulation.'),
        ('A5', 'P', 'finding', 'Calcified aortic atheromatosis', 'Calcified aortic atheromatosis.'),
        ('A6', 'P', 'finding', 'Aortic elongation', 'Aortic elongation.'),
        ('A7', 'U', 'finding', 'Mechanical changes in the cervico-dorsal column', None)]},
    5: {'ref_state': 'POS', 'need_sides': 'both', 'atoms': [
        ('A1', 'P', 'catheter', 'Central venous catheter via right subclavian vein with distal end in superior vena cava', 'Central venous catheter via right subclavian vein with distal end in superior vena cava.'),
        ('A2', 'P', 'device', 'NG tube with distal end infradiaphragmatic', 'NG tube with distal end infradiaphragmatic.'),
        ('A3', 'P', 'main', 'Significant bilateral pleural effusion', 'Significant bilateral pleural effusion.'),
        ('A4', 'P', 'finding', 'Bilateral alveolar infiltrates', 'Bilateral alveolar infiltrates.'),
        ('A5', 'P', 'finding', 'Bilateral interstitial infiltrates', 'Bilateral interstitial infiltrates.'),
        ('A6', 'P', 'finding', 'Changes from abdominal surgery', 'Changes from abdominal surgery.')]},
    6: {'ref_state': 'POS', 'need_sides': 'L', 'atoms': [
        ('A1', 'P', 'main', 'Left pleural effusion', 'Left pleural effusion.'),
        ('A2', 'P', 'finding', 'Enlarged hilar size', 'Enlarged hilar size.'),
        ('A3', 'P', 'finding', 'Cardiomegaly', 'Cardiomegaly persists.'),
        ('A4', 'P', 'finding', 'Vascular redistribution', 'Vascular redistribution.'),
        ('A5', 'U', 'finding', 'Increased pulmonary vascularization', None),
        ('A6', 'U', 'finding', 'Bilateral interstitial-alveolar pattern', None)]},
    15: {'ref_state': 'POS', 'need_sides': 'any', 'atoms': [
        ('A1', 'P', 'main', 'pleural effusion', 'Pleural effusion.')]},
}
N_CONTROL_RULE = 'non-conflict reference-POS patients with >=1 supported atom, S24 order_hash order, first C (match conflict-state composition)'


def sides(side):
    return {'L': {'L'}, 'R': {'R'}, 'both': {'L', 'R'}, 'whole': {'L', 'R'}, 'unspec': {'L', 'R'}}[side]


def derive(claims):
    """claims -> {'conflict': bool, 'ambiguous': bool, 'pairs': [...]}"""
    pos = [c for c in claims if c[1] == 'pos']
    neg = [c for c in claims if c[1] == 'neg']
    pairs, amb = [], []
    for p in pos:
        for n in neg:
            if p[0] == n[0]:
                continue
            if p[2] == 'unspec':
                continue  # unspec 양성은 아래 합집합 규칙으로만 판단
            if sides(p[2]) & sides(n[2]):
                pairs.append({'pos': p, 'neg': n})
    for p in pos:
        if p[2] == 'unspec':
            others = [n for n in neg if n[0] != p[0]]
            cover = set().union(*[sides(n[2]) for n in others]) if others else set()
            if cover >= {'L', 'R'}:
                pairs.append({'pos': p, 'neg': others})
            elif others:
                amb.append({'pos': p, 'neg_partial': others})
    return {'conflict': bool(pairs), 'ambiguous': bool(amb), 'pairs': pairs, 'ambiguous_cases': amb}


def check_quotes(pk, claims):
    text = {'G': pk['draft'], 'CL': pk['left'], 'CR': pk['right']}
    for src, st, side, q in claims:
        assert q.lower() in text[src].lower(), ('quote not in source', src, q, text[src])


def donors_for(order_rows, recipients):
    """같은 stage 입력(order_hash 순)에서 반대 흉수 상태 환자를 순서대로 순환 배정. projection metadata 없음 → 동일 projection 우선 규칙 적용 불가."""
    state = {r['ImageID']: r['stratum'] for r in order_rows}
    out = {}
    for k, img in enumerate(recipients):
        opp = [r['ImageID'] for r in order_rows if state[r['ImageID']] != state[img]]
        assert opp, 'no opposite-state donor'
        out[img] = opp[k % len(opp)]
    return out


def main():
    assert not (LOCK / 'selection.json').exists(), 'already locked'
    recs = RQ.load_cure('S24')
    rows = json.loads((DATA / 'inputs_S24.json').read_text())
    pk = {r['ImageID']: RQ.package(r['ImageID'], recs) for r in rows}
    ref = json.loads((DATA / 'reference_private.json').read_text())
    der = {}
    for i, r in enumerate(rows):
        check_quotes(pk[r['ImageID']], CLAIMS[i])
        d = derive(CLAIMS[i])
        d.update({'index': i, 'ImageID': r['ImageID'], 'ref_state': r['stratum']})
        der[r['ImageID']] = d
    assert sorted(CLAIMS) == list(range(len(rows)))
    conflicts = [r['ImageID'] for r in rows if der[r['ImageID']]['conflict']]
    C = len(conflicts)
    assert C > 0, 'no natural conflict -> stop without correction generation'
    # 보존 대조: 충돌 집단의 상태 구성에 맞춤, S24 order_hash 순서
    need = {}
    for img in conflicts:
        need[der[img]['ref_state']] = need.get(der[img]['ref_state'], 0) + 1
    ctrl = []
    idx = {r['ImageID']: i for i, r in enumerate(rows)}
    for st, n in need.items():
        cand = [r['ImageID'] for i, r in enumerate(rows) if r['stratum'] == st and not der[r['ImageID']]['conflict']]
        ctrl += cand[:n]
    selected = sorted(conflicts + ctrl, key=lambda x: idx[x])
    assert len(selected) <= 24
    assert set(idx[x] for x in selected) == set(ATOMS), ('ATOMS table must cover exactly the selected patients', sorted(idx[x] for x in selected), sorted(ATOMS))
    don = donors_for(rows, selected)
    # 환자 단위 사실 표 검증: atom quote가 초안에 있는지
    for i in ATOMS:
        assert any(a[1] == 'P' for a in ATOMS[i]['atoms']), ('control/conflict patient without supported atom', i)
        img = rows[i]['ImageID']
        for aid, cls, kind, quote, support in ATOMS[i]['atoms']:
            assert quote.lower() in pk[img]['draft'].lower(), ('atom quote not in draft', i, aid, quote)
            assert (support is None) == (cls == 'U')
    ids_by_state = {r['ImageID']: r['stratum'] for r in rows}
    assert all(ids_by_state[don[x]] != ids_by_state[x] for x in selected)
    refs = {i: ref[i]['reference_sentences'] for i in ref}
    reqs, info = RQ.build_requests(selected, recs, {r['ImageID']: r for r in rows}, don)
    probs = RQ.leak_check(reqs, refs, pk) + RQ.identity_check(reqs)
    assert not probs, probs
    # D4 기술 요청(평가 아님): D4 4명 전원
    rows4 = json.loads((DATA / 'inputs_D4.json').read_text())
    recs4 = RQ.load_cure('D4', R101 / 'cure/D4_w2')
    don4 = donors_for(rows4, [r['ImageID'] for r in rows4])
    reqs4, info4 = RQ.build_requests([r['ImageID'] for r in rows4], recs4, {r['ImageID']: r for r in rows4}, don4)
    probs4 = RQ.leak_check(reqs4, {}) + RQ.identity_check(reqs4)
    assert not probs4, probs4
    save(LOCK / 'claims.json', {'claims': {rows[i]['ImageID']: CLAIMS[i] for i in CLAIMS}, 'derived': der,
                                'note': 'assistant 수동 판정(전문의 검토 아님). 교정 출력 생성 전에 작성.', 'code_sha256': sha(__file__)})
    save(LOCK / 'atoms.json', {'atoms': {rows[i]['ImageID']: ATOMS[i] for i in ATOMS}, 'index': {rows[i]['ImageID']: i for i in ATOMS},
                               'reference_full_report_source': 'grounded_reports_20240819.json (train)', 'code_sha256': sha(__file__)})
    sel = {'n_S24': len(rows), 'n_conflict_C': C, 'conflicts': conflicts, 'controls': ctrl, 'selected_order': selected,
           'M': len(selected), 'control_rule': N_CONTROL_RULE, 'conflict_state_composition': need, 'donors': don,
           'donor_rule': 'opposite-state patients in S24 order_hash order, rotated by recipient position; projection metadata unavailable',
           'ambiguous_patients': [k for k, v in der.items() if v['ambiguous']],
           'NEG_conflicts': sum(1 for k in conflicts if ids_by_state[k] == 'NEG'), 'POS_conflicts': sum(1 for k in conflicts if ids_by_state[k] == 'POS'),
           'code_sha256': sha(__file__)}
    save(LOCK / 'selection.json', sel)
    save(DATA / 'corr_main' / 'requests.json', reqs)
    save(DATA / 'corr_main' / 'manifest.json', {'n_requests': len(reqs), 'per_patient': info, 'requests_sha256': sha(DATA / 'corr_main/requests.json'),
                                                'source_sha': {'req': sha(ROOT / 'report101_req.py'), 'lock': sha(__file__)}})
    save(DATA / 'corr_D4' / 'requests.json', reqs4)
    save(DATA / 'corr_D4' / 'manifest.json', {'n_requests': len(reqs4), 'per_patient': info4, 'requests_sha256': sha(DATA / 'corr_D4/requests.json'),
                                              'donors': don4, 'note': 'technical check only; not part of the evaluation'})
    save(LOCK / 'lock_complete.json', {'files': {n: sha(LOCK / n) for n in ('claims.json', 'atoms.json', 'selection.json')},
                                       'requests_main_sha256': sha(DATA / 'corr_main/requests.json'), 'requests_D4_sha256': sha(DATA / 'corr_D4/requests.json')})
    print(json.dumps({k: sel[k] for k in ('n_conflict_C', 'M', 'conflict_state_composition', 'NEG_conflicts', 'POS_conflicts', 'ambiguous_patients')}, indent=1))
    print('conflicts idx', [idx[x] for x in conflicts], 'controls idx', [idx[x] for x in ctrl], 'requests', len(reqs), len(reqs4))


if __name__ == '__main__':
    main()
