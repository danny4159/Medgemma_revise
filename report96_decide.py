"""iter_096: 원 계획(iter_095/096 plan)의 확대 분기·최소 pilot·단순 대안·음성/불확정 기준을 판정표 결과에 기계적으로 적용한다.
문턱은 계획에 적힌 값이며 결과를 보고 바꾸지 않는다. 사용: python report96_decide.py <ver> <report_tag>"""
import json
import sys

from report96_lock import R96
from report86_common import save, sha


def main(ver, rtag):
    rep = json.loads((R96 / f'eval/report_E32_{ver}{rtag}.json').read_text())
    br = rep['branches']
    c = rep['bundles']
    out = {'inputs': {'report_sha256': sha(R96 / f'eval/report_E32_{ver}{rtag}.json')}, 'criteria': {}}
    cr = out['criteria']

    def n(x):
        return len(x)

    # (a) 세부 영역이 CG·같은 형식 넓은 영역이 놓친 명확한 현재 소견을 최소 2명에서 회복
    a = {}
    for tag in ('main', 'lobe_zone_equal', 'no_cause_assist', 'excl_nonEOS'):
        a[tag] = {lv: {'describe': n(br[tag][lv]['a_describe_D6_beyond_CG_D2']), 'locate': n(br[tag][lv]['a_locate_L6_beyond_CG_L2'])} for lv in ('strict', 'lenient_timeok')}
    primary_a = max(a['main']['strict']['describe'], a['main']['strict']['locate'])
    cr['a_detail_recovers_beyond_broad'] = {'threshold_patients': 2, 'patients_by_variant': a, 'primary_strict_time_consistent': primary_a,
                                           'status': '미충족' if primary_a < 2 else '충족',
                                           'sensitivity_changes_decision': (a['lobe_zone_equal']['strict']['describe'] >= 2) != (primary_a >= 2) or (a['no_cause_assist']['strict']['describe'] >= 2) != (primary_a >= 2)}
    # (b) Describe 또는 넓은 영역 선택이 최소 2명에서 L8의 추가 회복을 보존하며 충돌을 줄임
    b = {}
    for tag in ('main', 'lobe_zone_equal', 'no_cause_assist'):
        b[tag] = {lv: {A: n(br[tag][lv][f'b_{A}_preserve_and_reduce']) for A in ('D8', 'D2', 'L2')} for lv in ('strict', 'lenient_timeok')}
    primary_b = max(b['main']['strict'].values())
    cr['b_preserve_recovery_and_reduce_conflict'] = {'threshold_patients': 2, 'patients_by_variant': b, 'primary_strict_time_consistent': primary_b,
                                                    'status': '미충족' if primary_b < 2 else '충족'}
    # (c) E64에 판단을 바꿀 reference 기회가 있는가 (selection.json의 E64_remaining_strata)
    sel = json.loads((R96.parent / 'iter_095/lock/selection.json').read_text())
    opp = sel['E64_remaining_strata']
    cr['c_events_few_but_remaining_reference_opportunity'] = {'E64_remaining_strata': opp, 'status': '미충족(남은 E64에 양성/명시적 부재 reference 기회 0)' if opp['pos'] == 0 and opp['neg'] == 0 else '검토'}
    # 최소 pilot 양성: Describe 세부 추가 회복 >=3, 명확한 충돌 >=5, 모호 표현 제외·한 환자 제거 후 유지
    loo = rep['leave_one_patient_out']
    d6s = loo['D6_detail_only_strict']
    cr['pilot_positive'] = {
        'additional_recovery_ge3': {'strict_time_consistent': n(d6s['patients']), 'lobe_zone_equal_strict': a['lobe_zone_equal']['strict']['describe'], 'lenient_timeok': n(loo['D6_detail_only_lenient_timeok']['patients'])},
        'clear_conflicts_ge5': {'D6_only': c['D6']['conflict_patients']['primary'], 'D8_detail_plus_broad': c['D8']['conflict_patients']['primary'], 'D8_excluding_cause_hedged_positive': c['D8']['conflict_patients']['excl_cause_hedged_positive']},
        'drop_one_patient_strict_recovery_remaining': d6s['min_after_drop_one'],
        'status': '미충족(모호 표현 제외 후 추가 회복 1명)'}
    cr['simple_alternative_E96'] = {'note': 'E32만으로 E96 운영 기준(회복 손실 환자 1명 이하·충돌 감소 최소 5명)을 선언하지 않음',
                                    'L8_extra_patients_lost_by_D2_strict': br['main']['strict']['b_D2_extra_lost'], 'L8_extra_patients_lost_by_D2_lenient': br['main']['lenient_timeok']['b_D2_extra_lost'],
                                    'conflict_free_broad_bundles': {k: c[k]['conflict_patients']['primary'] for k in ('CG', 'L2', 'D2')}, 'status': '미평가(E96 비실행)'}
    anat = out['criteria']['a_detail_recovers_beyond_broad']['sensitivity_changes_decision']
    out['verdict'] = {
        'expansion_branches': '(a)(b)(c) 모두 primary(strict·시간 일치·lobe-zone 불확실 분리)에서 미충족',
        'ambiguity': '(a)는 lobe-zone 대응 또는 원인 지원 인정 여부에 따라 결과가 바뀐다(해부 선택 의존) -> 불확정' if anat else '(a) 민감도 변화 없음',
        'decision': '현재 CURE 폐 영역 회복 후보 투자 보류. 좌표·영역 판독·위치 supervision 전체의 무용성 판정이 아님',
        'resume_condition': 'lobe–zone 대응을 박스 좌표 등 독립 근거로 확정할 수 있고, 양성 reference가 더 많은(현 E32는 양성 9명·10사실) 자료에서 모호 대응을 해소하는 독립 의미 검증',
    }
    save(R96 / f'eval/decision_E32_{ver}{rtag}.json', out)
    print(json.dumps(out['verdict'], ensure_ascii=False))
    for k, v in cr.items():
        print(k, v.get('status'))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
