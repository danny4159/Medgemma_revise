"""iter_096: iter_095 판정(report95_eval 함수를 읽기 전용으로 호출)과 iter_096 판정표의 primary 충돌 환자를 번들별로 비교하고
차이 사유를 환자 쌍의 원 판정 필드로 분류한다. 단일 원인 귀속이 아니라 자동 분류다.
사용: python report96_diff.py <ver>"""
import json
import sys
from collections import Counter

import report95_eval as E95
import report96_eval as E
from report86_common import save
from report96_lock import R96, R95


def main(ver, tag=''):
    J = json.loads((R96 / f'judging/judgments_E32_{ver}.json').read_text())
    claims, outs_text, _ = E95.load_judgments(['E32'])
    B = E95.bundle_outputs(outs_text)
    cl = E.flat_claims(J)
    sel = json.loads((R95 / 'lock/selection.json').read_text())['E32']
    old_rep = json.loads((R95 / 'eval/report_E32_v2.json').read_text())
    res = {}
    for b in E.BUNDLES:
        old = E95.conflicts(claims, B[b], mode='question')
        oldp = {sel.index(i) for i, v in old.items() if v}
        assert len(oldp) == old_rep['bundles'][b]['conflict_patients']['primary'], (b, len(oldp))
        newc = E.conflicts(cl, b, 'primary')
        new = set(newc)
        ent = {'old_patients': sorted(oldp), 'new_patients': sorted(new), 'new_only': {}, 'old_only': {}}
        for p in sorted(new - oldp):
            reasons = set()
            for pos, neg, st in newc[p]:
                oc = claims.get((sel[p], pos['oid']), [])
                on = claims.get((sel[p], neg['oid']), [])
                if any(c['pol'] == 'Pu' for c in oc):
                    reasons.add('원인 hedge가 있는 문장 전체를 존재 불확실(Pu)로 처리했던 규칙 -> 존재 확정으로 정정')
                elif not on:
                    reasons.add('정상 폐 실질 표현을 iter_095가 부정으로 기록하지 않음 -> 정정')
                else:
                    reasons.add('기타(범위·종류 규칙 변경)')
            ent['new_only'][str(p)] = sorted(reasons)
        for p in sorted(oldp - new):
            reasons = set()
            for pr in old[sel[p]]:
                nn = [c for c in claims.get((sel[p], pr[1]), []) if c['pol'] == 'N']
                txt = ' '.join(c['quote'] for c in nn)
                reasons.add('급성(acute) 수식 부정을 소견 부정으로 처리했던 규칙 -> 확정 충돌에서 제외(qualified)' if 'acute' in txt.lower() else '기타(예: lobe 양성 vs zone 부정의 같은 level 대응은 불확실 범위로 분류해 확정 충돌에서 제외)')
            ent['old_only'][str(p)] = sorted(reasons)
        res[b] = ent
    save(R96 / f'eval/correction_diff_E32_{ver}{tag}.json',
         {'note': 'iter_095 판정과 iter_096 판정의 primary 충돌 환자 비교. 사유는 환자 쌍의 원 판정 필드로 자동 분류.', 'bundles': res})
    for b in ('L8', 'D8'):
        print(b, len(res[b]['old_patients']), len(res[b]['new_patients']), 'old_only', res[b]['old_only'], 'new_only', len(res[b]['new_only']))
    print(Counter(r for b in ('L8', 'D8') for v in res[b]['new_only'].values() for r in v))


if __name__ == '__main__':
    main(*sys.argv[1:])
