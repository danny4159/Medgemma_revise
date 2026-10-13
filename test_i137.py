"""iter_137 CPU 검사 (GPU·모델 없음). 결과: results/iter_137/tests/cpu_tests.json (덮어쓰기 금지)."""
import copy, sys
import numpy as np
from i137_common import RES, read, save, now, digest
import i137_spec as S
import i137_eval as E
import i137_data as D

checks = {}


def chk(name, cond): checks[name] = bool(cond)


# --- spec: A/B는 마지막 설명 문장 하나만 다르다
chk('B_is_A_minus_last_sentence', S.QUESTION_A == S.QUESTION_B + ' Then give one short sentence of visible evidence.' and 'evidence' not in S.QUESTION_B)
chk('B_keeps_state_definitions', all(x in S.QUESTION_B for x in ('PRESENT means', 'ABSENT means', 'UNKNOWN means', 'On the first line output only one word')))
chk('no_new_answer_only_sentence', 'only' in S.QUESTION_A and S.QUESTION_B.count('only') == S.QUESTION_A.count('only'))
chk('prompts_no_forbidden', not any(f in p for p in S.PROMPTS.values() for f in S.FORBIDDEN_IN_PROMPT))
# --- parser (i134 규칙 그대로)
eos = True
chk('parse_present', S.parse('PRESENT\nA lesion.', eos, 'no_marker') == 'PRESENT')
chk('parse_bold_period', S.parse('**ABSENT.**', eos, 'no_marker') == 'ABSENT')
chk('parse_unknown_valid', S.parse('UNKNOWN', eos, 'no_marker') == 'UNKNOWN')
chk('parse_non_eos_invalid', S.parse('PRESENT', False, 'no_marker') is None)
chk('parse_invalid_boundary', S.parse('PRESENT', eos, 'invalid_boundary') is None)
chk('parse_empty_invalid', S.parse('  ', eos, 'no_marker') is None)
chk('parse_sentence_first_line_invalid', S.parse('The image shows PRESENT', eos, 'no_marker') is None)
chk('extra_text', S.extra_text('PRESENT\nfoo') and not S.extra_text('PRESENT') and not S.extra_text('PRESENT\n \n'))
chk('split_final', S.split_final([5, 6], 1, 2)[0] == 'no_marker' and S.split_final([1, 7, 2, 8], 1, 2) == ('thought_final', [8]) and S.split_final([7, 2], 1, 2)[0] == 'invalid_boundary')

# --- 자료/요청 계약 (실제 요청 파일)
tech = read(RES / 'requests/technical.json'); main = read(RES / 'requests/main.json')
chk('n_requests_24_180', len(tech) == 24 and len(main) == 180)
chk('unique_ids', len({r['id'] for r in tech}) == 24 and len({r['id'] for r in main}) == 180)
chk('each_patient_role_iface_once', all(len({(r['patient'], r['cond'], r['iface']) for r in rr}) == len(rr) for rr in (tech, main)))
chk('D_E_disjoint', not ({r['patient'] for r in tech} & {r['patient'] for r in main}))
chk('patients_6_45', len({r['patient'] for r in tech}) == 6 and len({r['patient'] for r in main}) == 45)
chk('prompt_by_iface', all(r['prompt'] == S.PROMPTS[r['iface']] for r in tech + main))
chk('single_image_each', all(len(r['images']) == 1 for r in tech + main))
chk('AB_share_pixels', all(len({r2['images'][0]['sha256'] for r2 in main if r2['patient'] == r['patient'] and r2['cond'] == r['cond']}) == 1 for r in main))
chk('P_N1_differ', all(len({r2['images'][0]['sha256'] for r2 in main if r2['patient'] == r['patient']}) == 2 for r in main))
chk('digest_recompute', all(digest({k: v for k, v in r.items() if k != 'request_digest'}) == r['request_digest'] for r in tech + main))
chk('no_gt_in_request', all(not any(k in r for k in ('truth', 'label', 'mask', 'area')) for r in tech + main))
chk('make_requests_deterministic', [r['id'] for r in D.make_requests(read(D.DATA / 'manifest.json')['rows']['D'])] == [r['id'] for r in tech])


# --- 평가기: 합성 record
def rec(pid, c, i, text, eos=True, status='no_marker'):
    return dict(id='%s__%s__%s' % (pid, c, i), final_text=text, text=text, eos=eos, boundary_status=status, n_tokens=3, wall_s=1.0, peak_reserved_mib=100.0, n_image_tokens=256, input_len=300)


def synth(a_ans, b_ans, n=4):
    out = []
    for k in range(n):
        p = 'S%d' % k
        for i, ans in (('A', a_ans), ('B', b_ans)):
            out += [rec(p, 'P', i, ans[0]), rec(p, 'N1', i, ans[1])]
    return out


st = E.states_of(synth(('PRESENT', 'PRESENT'), ('PRESENT', 'ABSENT')))
T = E.patient_table(st, ['S%d' % k for k in range(4)])
chk('table_ba', E.mean(T, 'ba_A') == 0.5 and E.mean(T, 'ba_B') == 1.0 and E.mean(T, 'diff_ba') == 0.5)
m, ci = E.boot(T, lambda v: v['diff_ba']); m2, ci2 = E.boot(T, lambda v: v['diff_ba'])
chk('boot_deterministic_and_degenerate', ci == ci2 and ci == [0.5, 0.5] and m == 0.5)
st = E.states_of(synth(('UNKNOWN', 'bad sentence'), ('PRESENT', 'ABSENT')))
T = E.patient_table(st, ['S%d' % k for k in range(4)])
chk('unknown_invalid_counted_wrong', E.mean(T, 'ba_A') == 0.0)
chk('non_eos_wrong', E.states_of([rec('S0', 'P', 'A', 'PRESENT', eos=False)])['S0__P__A']['state'] is None)


def fake(ba_b, sens, spec, d, lo, hi, valid=1.0):
    v = {i: dict(eos_rate=valid, boundary_valid_rate=1.0, first_line_valid_rate=valid) for i in E.IFACES}
    return dict(output_validity=v, B=dict(BA=ba_b, sensitivity=sens, specificity=spec), diff_B_minus_A=d, diff_ci95=[lo, hi])


chk('decide_positive', E.decide(fake(0.8, 0.8, 0.8, 0.3, 0.2, 0.4)) == 'positive_limited_recovery')
chk('decide_positive_needs_spec', E.decide(fake(0.8, 0.95, 0.6, 0.3, 0.2, 0.4)) != 'positive_limited_recovery')
chk('decide_positive_needs_ci_lower', E.decide(fake(0.8, 0.8, 0.8, 0.3, 0.0, 0.4)) != 'positive_limited_recovery')
chk('decide_negative_ba', E.decide(fake(0.6, 0.6, 0.6, 0.1, -0.1, 0.3)) == 'negative_no_recovery')
chk('decide_negative_ci_upper', E.decide(fake(0.7, 0.7, 0.7, 0.05, -0.1, 0.14)) == 'negative_no_recovery')
chk('decide_inconclusive', E.decide(fake(0.7, 0.7, 0.7, 0.2, 0.05, 0.35)) == 'inconclusive')
chk('decide_invalid_not_negative', E.decide(fake(0.5, 0.5, 0.5, 0.0, 0.0, 0.0, valid=0.9)) == 'invalid_output_conditions')
chk('paired_diff_no_state_change_not_success', E.mean(E.patient_table(E.states_of(synth(('PRESENT', 'PRESENT'), ('ABSENT', 'ABSENT'))), ['S%d' % k for k in range(4)]), 'diff_ba') == 0.0)

ok = all(checks.values())
save(RES / 'tests/cpu_tests.json', dict(created_at=now(), passed=ok, n=len(checks), checks=checks))
print('cpu tests', sum(checks.values()), '/', len(checks), 'passed', ok, [k for k, v in checks.items() if not v])
sys.exit(0 if ok else 1)
