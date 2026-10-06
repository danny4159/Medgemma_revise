"""iter_086 판정 parser·평가기 fixture. 결과: results/iter_086/tests/eval_fixtures.json
python test_report86_eval.py
"""
import json
import sys

from report86_common import R86, save, sha
import report86_eval as E
from report86_view import load as load_stage

results = []


def check(name, ok, detail=''):
    results.append({'name': name, 'pass': bool(ok), 'detail': detail})
    print(('PASS ' if ok else 'FAIL ') + name, detail[:160])


def expect_error(name, text, rows, refs):
    try:
        E.parse_judgments(text, rows, refs)
        check(name, False, 'no error raised')
    except E.JudgmentError as e:
        check(name, True, str(e)[:100])


def main():
    rows, reads, refs = load_stage('D8')
    base = (R86 / 'D8/judgments_D8.txt').read_text()
    jud = E.parse_judgments(base, rows, refs)
    check('parse_D8_ok', len(jud) == 8 and all(len(v) == 8 for v in jud.values()))
    res = E.evaluate('D8', base)
    # 손으로 계산한 C-G recall_def: 환자별 1/3,0/3,6/6,2/2,3/3,0/2,0/4,2/3 -> 평균 0.5
    cg = res['summary']['all']['conditions']['C-G']
    check('C-G_recall_def_hand_value', abs(cg['recall_def']['mean'] - 0.5) < 1e-12, str(cg['recall_def']))
    # C-G 모순: 모든 환자에서 N 또는 C 없음 -> 0
    check('C-G_contra_zero', cg['contra_primary']['mean'] == 0.0)
    # C-H P001(O3) 가능(p) 모순 2건, N(F3) 때문에 contra_primary=1
    po = res['per_output']
    key = [k for k in po if k.endswith('|C-H') and po[k]['contra_a_poss'] == 2]
    check('C-H_P001_possible_contra_counted', len(key) == 1 and po[key[0]]['contra_primary'] == 1 and po[key[0]]['contra_a_def'] == 0, str(key))
    # 결정성: 같은 입력으로 두 번 평가하면 bootstrap CI까지 동일
    res2 = E.evaluate('D8', base)
    check('deterministic_bootstrap', res['comparisons'] == res2['comparisons'])
    # 오류 거부
    lines = base.splitlines()
    expect_error('reject_missing_fact', base.replace('O2: F1=U F2=U F4=U ;', 'O2: F1=U F2=U ;', 1), rows, refs)
    expect_error('reject_span_missing', base.replace('F2=D+:"Volume loss in the left hemithorax" F4=N', 'F2=D+ F4=N', 1), rows, refs)
    expect_error('reject_suffix_on_U', base.replace('O2: F1=U F2=U F4=U', 'O2: F1=U+ F2=U F4=U', 1), rows, refs)
    expect_error('reject_C_not_neg_fact', base.replace('C=p:F4,p:F4', 'C=p:F1', 1), rows, refs)
    expect_error('reject_duplicate_patient', base + '\nP000\n', rows, refs)
    expect_error('reject_missing_output', '\n'.join(l for l in lines if not l.startswith('O8: F1=D:"heart appears enlarged" F2=D:"pacemaker visible"')), rows, refs)
    expect_error('reject_unknown_state', base.replace('F1=U F2=U F4=U ; C=- ; I=0 ; xd=0 xp=0', 'F1=X F2=U F4=U ; C=- ; I=0 ; xd=0 xp=0', 1), rows, refs)
    # 간단한 수작업 예: 사실 2개(D+, N) -> recall 0.5, contra_primary 1, strict 0.5
    mini = {'facts': {'F1': {'s': 'D', 'loc': '+', 'span': 'a'}, 'F2': {'s': 'N', 'loc': '', 'span': 'b'}}, 'contra': [], 'internal': 0, 'xd': 1, 'xp': 2}
    fake_refs = {'img': {'facts': [{'fact_id': 'F1', 'fact_class': 'pos_def'}, {'fact_id': 'F2', 'fact_class': 'pos_def'}]}}
    fake_reads = {('img', 'M15-R'): {'n_tokens': 10, 'final_eos': [True], 'request_ids': ['x'], 'n_attempts': 1}}
    o = E.per_output('img', 'M15-R', mini, fake_refs, fake_reads)
    check('mini_hand_example', o['recall_def'] == 0.5 and o['recall_strict'] == 0.5 and o['contra_primary'] == 1 and o['claims_unverifiable'] == 3 and o['claims_supported'] == 1, str(o['recall_def']))
    mini['facts']['F1']['loc'] = '-'
    o = E.per_output('img', 'M15-R', mini, fake_refs, fake_reads)
    check('wrong_location_not_strict', o['recall_def'] == 0.5 and o['recall_strict'] == 0.0 and o['contra_c_wrong_loc'] == 1, str(o))
    save(R86 / 'tests/eval_fixtures.json', {'results': results, 'n_pass': sum(r['pass'] for r in results), 'n': len(results),
                                            'sources': {f: sha(f) for f in ['report86_eval.py', 'report86_view.py', 'report86_facts.py']}})
    return 0 if all(r['pass'] for r in results) else 1


if __name__ == '__main__':
    sys.exit(main())
