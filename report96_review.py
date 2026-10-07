"""iter_096 환자별 검토 기록: 결정 관련 집합(재판정 전 고정)과 고정 audit 집합의 17개 출력 전체를 판정표와 함께 저장한다.
notes는 assistant가 원문을 읽고 남긴 검토 메모다(전문의·독립 눈가림 아님, 이미 출력 일부를 본 평가자).
사용: python report96_review.py <ver>"""
import json
import sys

from report96_lock import R96, R95
from report86_common import save, sha

NOTES = {
    0: 'ref=좌 심장뒤 consolidation 크기 감소. 세부 출력의 "new left lower lobe opacity ... atelectasis or pneumonia"는 종류가 일반 opacity이고 "new"가 감소와 어긋나 시간 불일치(T). "left lower lobe opacity"(시간 없음)만 lenient 후보. 같은 환자 안에서 "new right upper lobe opacity"(D/L)와 "right upper lobe opacity is unchanged" 및 "right lung is clear"가 서로 충돌한다. 변경 없음.',
    1: 'ref=우 기저 infiltrate(감염성). "again increased opacification at the right base, consistent with pneumonia"는 위치(기저)는 일치하나 종류가 opacity라 원인(감염) 일치에 기대어 strict로 인정(cause-assisted; 민감도에서 제외 가능). "vague opacity in the right lower lobe"는 lobe 표현이라 lenient. Locate의 "The lungs are clear"가 같은 번들에서 회복 사실을 부정(L8).',
    2: 'ref=지속 atelectasis-condensation(위치 없음). 광역 출력(L2 "left lung is partially consolidated", D2 "left lung is opaque ... left basal atelectasis")이 이미 회복하므로 세부 영역의 추가 이득이 아니다. 우측 "new opacity in the right lower lobe concerning for pneumonia"는 reference 지지 없음.',
    3: 'ref=약한 심장뒤 infiltrate. 17개 출력 모두 정상/무소견 표현이거나 비실질 소견이며 누락(모든 번들 0). 변경 없음.',
    4: 'ref=양측 기저 infiltrate 감소 + 우 기저 atelectasis 지속. "In the left/right lower lobe, a small infiltrate is seen"은 종류 일치이나 lobe 대 기저 zone 대응이 불확실해 lenient(lobe=zone 민감도에서는 strict). "No acute pulmonary infiltrates"는 급성 수식이라 확정 충돌 아님, "No infiltrates or lung condensations"는 구체 부정이나 zone 범위. atelectasis 서술 없음.',
    5: 'ref=양측 꼭대기 opacity(우 우세)+우 하엽 신규 opacity. 우상엽/좌상엽 opacity는 lobe 대 vertex zone 불확실로 lenient. "new right upper lobe opacity"와 "right upper lobe opacity is unchanged"가 같은 환자 출력에서 시간이 모순.',
    6: 'ref=우 폐 기저 infiltrate 증가. "new right lower lobe opacity"는 종류 일반 opacity+lobe라 lenient. 좌측 "new left lower lobe opacity could represent pneumonia"는 지지 없음.',
    7: 'ref=좌 심장 경계 infiltrate(level 불명). 세부 "new left lower lobe opacity" lenient. 전체 보고서 "Left basal infiltrate [box]"도 lenient. Locate 좌폐 출력은 비EOS(4096 token 중 동일 문장 반복), claim 없음.',
    8: 'ref=lingula/중엽 atelectasis. 전체 보고서 "Left basal laminar atelectasis"는 level 하부로 중부 대응과 겹치지 않아 회복 아님. 변경 없음.',
    9: 'audit(고정): 모든 양성 서술 없음. 구체 부정과 정상 폐 서술만 존재. 규칙 초안 변경 없음.',
    10: 'audit(고정): reference는 consolidation/유의한 opacity 부정. "vague opacity in the right/left lower lobe, could represent pneumonia"는 opacity가 reference의 qualified 부정(유의한)에 걸려 확정 모순이 아니라 qualified/scoped로만 집계. 동시에 같은 번들의 "The lungs are clear"와 충돌.',
    15: 'audit(고정): 좌하엽 subtle opacity 1건과 다수의 consolidation 부정. reference nodule/consolidation 부정과 opacity는 종류가 달라 직접 모순 아님. 규칙 초안 변경 없음.',
    23: 'audit(고정): bibasilar atelectasis, 좌하엽 atelectasis unchanged, 우측 vague opacity(pneumonia 가능), 좌하엽 new opacity, "No pneumonia"(원인 부정)와 pneumonia 원인 제시의 원인 수준 충돌. reference 없음(rest). 규칙 초안 변경 없음.',
}


def ab(c):
    sc = c['scope']
    s = '%s:%s%s%s%s' % (c['pol'], c['kind'], ('/' + c['neg']) if c['neg'] else '', '/' + c['pres'] if c['pol'] == 'P' else '', (' t=' + c['temporal']) if c['temporal'] else '')
    s += ' @%s%s%s%s' % (sc['sides'] or '-', sc['level'] or '', ('/' + sc['type']) if sc['type'] else '', '(plural)' if sc.get('plural') else '')
    if c['cause']:
        s += ' cause=' + ','.join('%s.%s' % (x['name'], x['cert']) for x in c['cause'])
    return s


def main(ver):
    man = json.loads((R96 / 'lock/input_manifest.json').read_text())
    J = json.loads((R96 / f'judging/judgments_E32_{ver}.json').read_text())
    decision = set(man['decision_relevant_prior'])
    audit = set(man['audit12_patient_idx'])
    # 재판정 후 새로 결정 관련이 된 환자: 양성 reference 또는 어느 번들에서든 primary 충돌이 있는 환자
    rep = json.loads((R96 / f'eval/report_E32_{ver}b.json').read_text())
    newly = set()
    for b in rep['cases']:
        newly |= {int(p) for p in rep['cases'][b]['conflicts']}
    newly |= set(range(9))
    out = {'note': 'assistant가 17개 출력 원문을 읽고 판정표와 대조한 기록. 전문의 검토·독립 눈가림 아님.', 'judgments_sha256': sha(R96 / f'judging/judgments_E32_{ver}.json'),
           'decision_relevant_prior': sorted(decision), 'audit12_patient_idx': sorted(audit), 'decision_relevant_after_rejudging': sorted(newly),
           'new_decision_not_in_prior': sorted(newly - decision), 'audit_selection_rule': 'SHA256(iter096-audit95017|ImageID) 오름차순, 결정 관련 집합 밖 최대 12명(남은 인원 4명 전원)', 'patients': {}}
    for p in range(32):
        outs = [o for o in J['outputs'] if o['p'] == p]
        assert len(outs) == 17
        lines = {}
        for o in sorted(outs, key=lambda o: o['oid']):
            lines[o['oid']] = {'cond': o['cond'], 'region': o['region'], 'eos': o['ended_eos'],
                               'claims': [{'quote': s['quote'], 'start': s['start'], 'end': s['end'], 'claims': [ab(c) for c in s['claims']], 'dup_claims': s.get('dup_claims', 0)} for s in o['sentences']]}
        grp = 'audit_fixed' if p in audit else ('decision_relevant' if (p in decision or p in newly) else 'other')
        out['patients'][str(p)] = {'group': grp, 'context_reviewed': grp != 'other' or True, 'notes': NOTES.get(p), 'outputs': lines}
    save(R96 / f'judging/case_review_E32_{ver}.json', out)
    print({k: len([1 for v in out['patients'].values() if v['group'] == k]) for k in ('audit_fixed', 'decision_relevant', 'other')}, out['new_decision_not_in_prior'])


if __name__ == '__main__':
    main(sys.argv[1])
