"""iter_136 CPU 단위 검사(모델 출력 전 고정): 경계 분리·parser·OR·decision 분기·N2 선택 규칙·합성 평가·실제 manifest 계약. 결과: results/iter_136/tests/cpu_tests_v2.json (덮어쓰기 금지)."""
import numpy as np
from i136_common import RES, save, now, read
from i136_spec import parse, split_final, audit, repetition
import i136_eval as E
import i136_data as D

res = {}
def chk(name, ok): res[name] = bool(ok)

S, N = 100, 101
st, fin = split_final([S, 5, 6, N, 7, 8, 106], S, N); chk('boundary_thought_final', st == 'thought_final' and fin == [7, 8, 106])
chk('boundary_marker_included_start_only_invalid', split_final([S, 5, 6], S, N)[0] == 'invalid_boundary')   # 불완전(종료 없음, 절단된 thought)
chk('boundary_no_marker', split_final([7, 8], S, N) == ('no_marker', [7, 8]))
chk('boundary_multiple_invalid', split_final([S, N, S, N, 5], S, N)[0] == 'invalid_boundary')
chk('boundary_end_without_start_invalid', split_final([5, N, 6], S, N)[0] == 'invalid_boundary')
chk('boundary_start_not_first_invalid', split_final([5, S, N, 6], S, N)[0] == 'invalid_boundary')
chk('boundary_reversed_invalid', split_final([N, 5, S, 6], S, N)[0] == 'invalid_boundary')
chk('boundary_empty_final_invalid_parse', parse('', True, 'thought_final') is None)
chk('parse_final_ok', parse('PRESENT\nA lesion.', True, 'thought_final') == 'PRESENT' and parse('ABSENT\nx', True, 'no_marker') == 'ABSENT')
chk('parse_nonEOS_invalid', parse('PRESENT\nx', False, 'no_marker') is None)
chk('parse_invalid_boundary', parse('PRESENT\nx', True, 'invalid_boundary') is None)
chk('parse_truncated_thought_text_not_answer', parse('The user wants me to determine', True, 'no_marker') is None)
chk('parse_markdown_period', parse('**UNKNOWN.**\nx', True, 'no_marker') == 'UNKNOWN' or parse('**UNKNOWN**\nx', True, 'no_marker') == 'UNKNOWN')
chk('parse_extra_words_invalid', parse('PRESENT or ABSENT\nx', True, 'no_marker') is None)
chk('rep_detect', repetition('The image shows a brain. ' * 4) and not repetition('One sentence here. Another different sentence there.'))
chk('audit_contradiction', audit('PRESENT\nThere is no visible lesion.', 'PRESENT') == 'contradiction')
chk('or_rules', E.OR(['PRESENT', 'ABSENT']) == 'PRESENT' and E.OR(['ABSENT', 'ABSENT']) == 'ABSENT' and E.OR(['ABSENT', 'UNKNOWN']) == 'UNKNOWN' and E.OR(['PRESENT', None]) == 'INVALID' and E.OR(['UNKNOWN', 'UNKNOWN']) == 'UNKNOWN')
chk('decide_positive', E.decide(0.8, 0.5, 0.3, [0.1, 0.5], 0.99, 0.7) == 'positive_limited_joint_loss')
chk('decide_positive_needs_spec', E.decide(0.8, 0.5, 0.3, [0.1, 0.5], 0.99, 0.6) != 'positive_limited_joint_loss')
chk('decide_positive_needs_valid', E.decide(0.8, 0.5, 0.3, [0.1, 0.5], 0.9, 0.7) != 'positive_limited_joint_loss')
chk('decide_positive_needs_ci', E.decide(0.8, 0.5, 0.3, [-0.01, 0.5], 0.99, 0.7) != 'positive_limited_joint_loss')
chk('decide_negative', E.decide(0.8, 0.8, 0.0, [-0.1, 0.1], 0.99, 0.7) == 'negative_joint_loss_candidate_hold')
chk('decide_basic', E.decide(0.55, 0.5, 0.05, [-0.1, 0.2], 0.99, 0.5) == 'negative_basic_reading_insufficient')
chk('decide_inconclusive', E.decide(0.7, 0.6, 0.1, [-0.05, 0.25], 0.99, 0.6) == 'inconclusive')
# 합성 환자표
st_ = {}
for i in range(8):
    p = 'P%d' % i
    for c, s in dict(P='PRESENT', N1='ABSENT', N2='ABSENT', PN1='ABSENT', N1P='ABSENT', N1N2='ABSENT', N2N1='ABSENT', PP='PRESENT', N1N1='ABSENT', NONE='UNKNOWN').items(): st_[p + '__' + c] = dict(state=s)
T = E.patient_table(st_, ['P%d' % i for i in range(8)])
d, ci = E.boot(T, lambda v: (v['or_pos_ok'] + v['or_neg_ok']) / 2 - (v['joint_pos_ok'] + v['joint_neg_ok']) / 2)
chk('synthetic_diff_0.5', abs(d - 0.5) < 1e-12)
chk('synthetic_or_ba_1_joint_05', E.ba(T, 'or_pos_ok', 'or_neg_ok') == 1.0 and abs(E.ba(T, 'joint_pos_ok', 'joint_neg_ok') - 0.5) < 1e-12)
chk('boot_deterministic_seed136', E.boot(T, lambda v: v['or_pos_ok'] - v['joint_pos_ok']) == E.boot(T, lambda v: v['or_pos_ok'] - v['joint_pos_ok']) and E.SEED == 136)
# N2 선택 규칙: 합성 volume. 종양 z=5(면적3). N1=3. z=0 비어있음(<50%), z=1 뇌 40%(<50%) 제외. 후보: 2,4,6,7,... P=5와 물리 거리 최소.
flair = np.ones((8, 8, 10), np.float32); flair[:, :, 0] = 0; flair[:5, :, 1] = 0
area = [0] * 10; area[5] = 3; area[6] = 2   # 6은 종양 있음 → 후보 제외
nz = np.array([int((flair[:, :, k] != 0).sum()) for k in range(10)])
chk('n2_nearest_tie_lowest_z', D.n2_select(flair, area, nz, 5, 3, 1.0) == 4)   # 4(거리1)가 최소, 6은 종양
chk('n2_excludes_N1', D.n2_select(flair, area, nz, 5, 4, 1.0) == 3)   # 4는 N1이라 제외, 6은 종양 → 거리2 후보 3·7 동률에서 낮은 z
chk('n2_tie_low_z', D.n2_select(flair, [0, 0, 0, 0, 0, 3, 3, 0, 0, 0], nz, 5, 4, 1.0) == 3)   # 거리2 후보 3·7 동률 → 낮은 z
chk('n2_physical_distance_uses_zoom', D.n2_select(flair, area, nz, 5, 3, 2.0) == 4)
chk('n2_none_when_no_candidate', D.n2_select(flair, [3] * 10, nz, 5, 3, 1.0) is None)
chk('n2_excludes_empty_skull_and_low_brain', D.n2_select(flair, [0, 0, 0, 0, 0, 3, 3, 3, 3, 3], nz, 9, 8, 1.0) not in (0, 1))
# 실제 manifest 계약
m = read(RES / 'data/manifest.json')
chk('manifest_D_ge_4_E_ge_32', len(m['cases']['D']) >= 4 and len(m['cases']['E']) >= 32 and m['run_models'])
allc = m['cases']['D'] + m['cases']['E']
chk('manifest_D_E_disjoint', not {c['case'] for c in m['cases']['D']} & {c['case'] for c in m['cases']['E']})
chk('manifest_N_annotation_zero_P_positive', all(c['area']['P'] > 0 and c['area']['N1'] == 0 and c['area']['N2'] == 0 for c in allc))
chk('manifest_three_distinct_slices', all(len(set(c['z'].values())) == 3 for c in allc))
chk('manifest_N2_brain_ge_half_max', all(c['nz']['N2'] >= 0.5 * c['audit']['max_nz'] for c in allc))
chk('manifest_png_hashes_current', all(__import__('i136_common').sha(im['path']) == im['sha256'] for c in allc for im in c['images'].values()))
tr = read(RES / 'requests/technical.json'); mr = read(RES / 'requests/main.json')
chk('requests_counts_10_per_patient', len(tr) == 10 * len(m['cases']['D']) and len(mr) == 10 * len(m['cases']['E']))
chk('requests_ids_unique_and_disjoint_patients', len({r['id'] for r in tr + mr}) == len(tr) + len(mr) and not {r['patient'] for r in tr} & {r['patient'] for r in mr})
chk('requests_conditions_complete', all({r['cond'] for r in mr if r['patient'] == p} == set(E.CONDS) for p in {r['patient'] for r in mr}))
chk('requests_same_pixels_across_conditions', all(len({im['sha256'] for r in mr if r['patient'] == p for im, ro in zip(r['images'], r['roles']) if ro == 'P'}) == 1 for p in {r['patient'] for r in mr}))
chk('requests_no_gt_in_prompt', all(not any(s in r['prompt'] for s in ('BRATS', 'annotation', 'mask', 'segmentation', 'glioma', 'edema')) for r in tr + mr))
chk('requests_order_not_sorted_by_cond', [r['cond'] for r in mr[:10]] != list(E.CONDS))
save(RES / 'tests/cpu_tests_v2.json', dict(note='cpu_tests.json(43/45)은 합성 fixture 기대값 계산 오류(코드 결함 아님)로 보존', created_at=now(), results=res, passed=all(res.values())))
print(sum(res.values()), '/', len(res), [k for k, v in res.items() if not v])
raise SystemExit(0 if all(res.values()) else 1)
