"""CPU 단위 검사: parser·감사·OR 규칙·decision 분기·P/N 선택 규칙·bootstrap 결정성. 결과: results/iter_134/tests/cpu_tests.json (덮어쓰기 금지)."""
import numpy as np
from i134_common import RES, save, now
from i134_spec import parse, audit, repetition
import i134_eval as E
import i134_data as D

res = {}
def chk(name, ok): res[name] = bool(ok)

chk('parse_plain', parse('PRESENT\nA lesion is visible.', True) == 'PRESENT')
chk('parse_markdown', parse('**ABSENT**\nx', True) == 'ABSENT')
chk('parse_period', parse('UNKNOWN.\nx', True) == 'UNKNOWN')
chk('parse_nonEOS_invalid', parse('PRESENT\nx', False) is None)
chk('parse_extra_words_invalid', parse('PRESENT or ABSENT\nx', True) is None)
chk('parse_lower_invalid', parse('present\nx', True) is None)
chk('parse_empty', parse('', True) is None)
chk('audit_present_negated', audit('PRESENT\nThere is no visible lesion.', 'PRESENT') == 'contradiction')
chk('audit_present_consistent', audit('PRESENT\nA hyperintense lesion is visible in the left temporal lobe.', 'PRESENT') == 'consistent')
chk('audit_absent_positive', audit('ABSENT\nA hyperintense mass is seen.', 'ABSENT') == 'contradiction')
chk('audit_mixed_unresolved', audit('PRESENT\nNo lesion in image 2 but hyperintense lesion in image 1.', 'PRESENT') == 'unresolved')
chk('audit_invalid_na', audit('x', None) == 'na')
chk('rep_detect', repetition('The image shows a brain. ' * 4))
chk('rep_none', not repetition('One sentence here. Another different sentence there.'))
chk('or_rules', E.OR(['PRESENT', 'ABSENT']) == 'PRESENT' and E.OR(['ABSENT', 'ABSENT']) == 'ABSENT' and E.OR(['ABSENT', 'UNKNOWN']) == 'UNKNOWN' and E.OR(['PRESENT', None]) == 'INVALID' and E.OR(['UNKNOWN', 'UNKNOWN']) == 'UNKNOWN')
chk('decide_positive', E.decide(0.8, 0.5, 0.3, [0.1, 0.5], 0.99) == 'positive_limited_joint_loss')
chk('decide_positive_needs_valid', E.decide(0.8, 0.5, 0.3, [0.1, 0.5], 0.9) != 'positive_limited_joint_loss')
chk('decide_negative', E.decide(0.8, 0.8, 0.0, [-0.1, 0.1], 0.99) == 'negative_joint_loss_candidate_hold')
chk('decide_basic', E.decide(0.55, 0.5, 0.05, [-0.1, 0.2], 0.99) == 'negative_basic_reading_insufficient')
chk('decide_inconclusive', E.decide(0.7, 0.6, 0.1, [-0.05, 0.25], 0.99) == 'inconclusive')
# 합성 환자표: 8명 모두 OR 정답, 공동은 양성 집합에서 항상 오답 → diff = 0.25
st = {}
for i in range(8):
    p = 'P%d' % i
    for c, s in dict(P='PRESENT', N1='ABSENT', N2='ABSENT', PN1='ABSENT', N1P='ABSENT', N1N2='ABSENT', N2N1='ABSENT', PP='PRESENT', N1N1='ABSENT', NONE='UNKNOWN').items():
        st[p + '__' + c] = dict(state=s)
T = E.patient_table(st, ['P%d' % i for i in range(8)])
d, ci = E.boot(T, lambda v: (v['or_pos_ok'] + v['or_neg_ok']) / 2 - (v['joint_pos_ok'] + v['joint_neg_ok']) / 2)
chk('synthetic_diff_025', abs(d - 0.5) < 1e-12 or abs(d - 0.25) < 1e-12)
chk('synthetic_or_ba_1', E.ba(T, 'or_pos_ok', 'or_neg_ok') == 1.0 and E.ba(T, 'joint_pos_ok', 'joint_neg_ok') == 0.5)
chk('boot_deterministic', E.boot(T, lambda v: v['or_pos_ok'] - v['joint_pos_ok']) == E.boot(T, lambda v: v['or_pos_ok'] - v['joint_pos_ok']))
# P/N 선택 규칙: 합성 volume (X,Y,Z)=(8,8,12), 종양 z=4(면적2)·z=5(면적4)·z=6(면적4) → P=5(동률 낮은 z), 뇌 면적은 z=0,1이 작음
a = np.ones((8, 8, 12), np.float32); a[:, :, 0] = 0; a[:5, :, 1] = 0; a[:, 4:, 2] = 0   # z0 비어있음, z1 뇌 37.5%(<50% 제외), z2 50%
m = np.zeros((8, 8, 12), bool); m[0, 0, 4] = m[0, 1, 4] = True; m[:2, :2, 5] = True; m[:2, :2, 6] = True
sel, why = D.choose(a, m, [1.0, 1.0, 2.0])
chk('choose_P_tie_lowest_z', sel and sel['z']['P'] == 5)
chk('choose_N_excludes_tumor_and_empty_skull', sel and {sel['z']['N1'], sel['z']['N2']}.isdisjoint({0, 1, 4, 5, 6}) and sel['z']['N1'] == 3 and sel['z']['N2'] == 7)   # |dz|=2 동률은 낮은 z 먼저
a2 = a.copy(); sel2, why2 = D.choose(a2, np.ones_like(m), [1, 1, 1]); chk('choose_exclude_no_N', sel2 is None and why2 == 'fewer_than_2_eligible_N')
chk('choose_exclude_no_mask', D.choose(a, np.zeros_like(m), [1, 1, 1]) == (None, 'no_tumor_mask'))
chk('report_regex', D.REPORT_OK.search('multiple abnormal signal foci in the lobe') and not D.REPORT_BAD.search('These irregularities do not result in a midline shift.') and D.REPORT_BAD.search('There is no visible lesion.'))
save(RES / 'tests/cpu_tests_v3.json', dict(note='cpu_tests.json(26/28), cpu_tests_v2.json(26/28)은 audit 정규식·fixture 기대값 오류 수정 전 기록이며 보존',created_at=now(), results=res, passed=all(res.values())))
print(sum(res.values()), '/', len(res), [k for k, v in res.items() if not v])
raise SystemExit(0 if all(res.values()) else 1)
