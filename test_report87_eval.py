"""iter_087 평가기 fixture: 실제 P000·P062 판정(의미 규약 v2)으로 범위·속성·주장 집계·오류 거부를 검사한다.
python test_report87_eval.py <out_json>   (새 파일만 쓴다). 의미 fixture 통과는 모델 정답률 gate가 아니다."""
import json
import sys
from pathlib import Path

import report86_eval as E1
import report87_eval as E
from report86_common import R86, ROOT, save
from report86_view import load

PARTS = ROOT / 'results/iter_087/judgments_parts'


def main(out):
    rows, reads, v1refs = load('E96')
    amend = E.load_amend()
    v1j = E1.parse_judgments((R86 / 'E96/judgments_E96_v2.txt').read_text(), rows, v1refs)
    t0, t62 = (PARTS / 'part_P000.txt').read_text(), (PARTS / 'part_P062.txt').read_text()
    jud = E.parse_v3(t0 + '\n' + t62, rows, amend, reads, v1j, subset=True)
    i0, i62 = rows[0]['ImageID'], rows[62]['ImageID']
    po = lambda img, c: E.per_output(img, c, jud[img][c], amend, reads)
    from report86_view import blind_order
    cond = lambda img, k: blind_order(img)[k - 1]
    res = []

    def check(name, cond_ok, detail=None):
        res.append({'name': name, 'pass': bool(cond_ok), 'detail': detail})

    # 1. 속성 코드: moderate vs intense=a, 생략=o, mild=c
    for k, code in ((1, 'a'), (2, 'o'), (8, 'c')):
        check(f'P062 O{k} F5 attr={code}', jud[i62][cond(i62, k)]['facts']['F5']['attr'] == code)
    # 2. strict는 속성 a/o/c에서 실패, 개념 D는 유지
    for k in (1, 2, 8):
        p = po(i62, cond(i62, k))
        check(f'P062 O{k} concept D / strict 0', p['v1']['D'] == 1 and p['v1']['D_strict'] == 0, p['v1'])
    # 3. 속성 충돌만 C.attr 주장 + contra_attr, 원 scope(contra_common)는 0
    p = po(i62, cond(i62, 8))
    check('P062 O8 attr conflict -> contra_attr=1, contra_common=0', p['contra_attr'] == 1 and p['contra_common'] == 0 and p['claims']['C'] == 1, p['contra_components'])
    # 4. 구체적 정상 사실(normal_scoped) 충돌은 v2에서만 모순
    p = po(i62, cond(i62, 4))
    check('P062 O4 폐실질 정상 vs opacity -> contra_neg_new=1, common=0', p['contra_neg_new'] == 1 and p['contra_common'] == 0 and p['contra_v2'] == 1)
    check('P062 O4 possible-level C.neg는 definite 모순에 안 셈', p['contra_components']['neg_new'] == 1 and p['claims']['C_p'] == 1 and p['claims']['C_d'] == 1)
    # 5. bones/ribs intact는 측만의 N이 아님(v1 N -> v3 U)
    for k in (4, 5, 7):
        check(f'P062 O{k} bones intact is not N for scoliosis', jud[i62][cond(i62, k)]['facts']['F5']['s'] == 'U')
    # 6. P000 lungs clear는 폐외 소견 N이 아님, 모든 조건 모순 없음
    for c in E.CONDS:
        p = po(i0, c)
        check(f'P000 {c} no N/contra', p['v1']['N'] == 0 and p['contra_v2'] == 0 and p['contra_common'] == 0)
    p = po(i0, cond(i0, 5))
    check('P000 possible nodule: recall_def 0, incl_possible 1/3, loc a', p['v1']['recall_def'] == 0 and abs(p['v1']['recall_incl_possible'] - 1 / 3) < 1e-12
          and jud[i0][cond(i0, 5)]['facts']['F3']['loc'] == 'a')
    # 7. 영역 수 반영 주장 집계 (P062 C-H: S=26, U=9, C=0) + 다중 reference 주장은 한 번만
    ch = [c for c in E.CONDS if c == 'C-H'][0]
    p = po(i62, ch)
    check('P062 C-H claims S26 U9 C0 (영역 수 반영, 다중 ref 1회)', (p['claims']['S'], p['claims']['U'], p['claims']['C']) == (26, 9, 0), p['claims'])
    # 8. 같은 문장의 다른 영역은 병합하지 않는다: P000 C-H L6(4 regions)
    check('P000 C-H 영역 묶음 multiplicity', any(c['at'] == '@L6' and c['n'] == 4 for c in jud[i0][ch]['claims']))
    check('P000 C-H 내부 모순 2건(폐 전체 정상 vs 좌/우 음영)', len(jud[i0][ch]['internal']) == 2 and po(i0, ch)['internal_d'] == 2)
    # 9. 반복(같은 anchor)은 한 주장, 모든 위치 보존
    cl = [c for c in jud[i0][ch]['claims'] if c['anchor'] == 'opacity in the right lower lobe'][0]
    check('반복 문장은 한 주장이며 anchor 위치 2개 보존', cl['n'] == 1 and len(cl['occ'][0]['starts']) == 2, cl['occ'])
    # 10. 포괄 정상 tension 열
    check('generic_global_normal tension 집계', po(i62, cond(i62, 5))['claims']['tension_global_normal'] == 1)
    # 11. 빈 분모는 None
    check('빈 분모 None', po(i0, cond(i0, 3))['claims']['n_total'] == 1 and po(i62, cond(i62, 2))['v2']['n'] == 2)

    def must_fail(name, text, needle):
        try:
            E.parse_v3(text, rows, amend, reads, v1j, subset=True)
            check(name, False, 'accepted')
        except E.JudgmentError as e:
            check(name, needle in str(e), str(e)[:160])

    rep = lambda s, a, b: s.replace(a, b, 1)
    must_fail('D without linked claim', rep(t62, 'c S F5 +d "Dorsolumbar scoliosis with right dorsal convexity"\nc U - -d "No other relevant findings" -- generic_global_normal\nO3',
                                              'c U - -d "No other relevant findings" -- generic_global_normal\nO3'), 'has no linked claim')
    must_fail('attr conflict without C.attr claim', rep(t62, 'c C.attr F5 +d', 'c S F5 +d'), 'attr conflict needs')
    must_fail('C.attr claim without attr c code', rep(t62, 'f F5 D n c "There is a mild', 'f F5 D n a "There is a mild'), 'no conflict but C.loc/attr claim')
    must_fail('loc code must be n without loc_req', rep(t62, 'f F5 D n a "moderate dextroscoliosis of the thoracic spine"', 'f F5 D m a "moderate dextroscoliosis of the thoracic spine"'), 'loc code')
    must_fail('attr n with attr_req', rep(t62, 'f F5 D n a "moderate dextroscoliosis of the thoracic spine"', 'f F5 D n n "moderate dextroscoliosis of the thoracic spine"'), 'attr n but attr_req')
    must_fail('S without ref', rep(t62, 'c S F2 -d "The mediastinal and hilar contours are normal" @L16', 'c S - -d "The mediastinal and hilar contours are normal" @L16'), 'S needs ref')
    must_fail('anchor not found', rep(t62, '"The trachea is not deviated" @L17', '"The trachea is deviated" @L17'), 'anchor not in segment')
    must_fail('@ forbidden for non C-H', rep(t62, 'c S F1 -d "The heart size is normal"', 'c S F1 -d "The heart size is normal" @L1'), '@ not allowed')
    must_fail('C-H without @', rep(t62, 'c U - +d "The aorta is mildly tortuous" @L2', 'c U - +d "The aorta is mildly tortuous"'), 'needs @L')
    must_fail('v1 status change without why', rep(t62, 'f F5 U -- v1 N (ribs and spine appear intact) -> U: 골 intact는 골절 등 부정이며 측만을 부정하지 않음(범위 규칙)', 'f F5 U'), 'without -- why')
    must_fail('C.neg must cite neg/normal_scoped fact', rep(t62, 'c C.neg F3 +d', 'c C.neg F5 +d'), 'C.neg needs')
    must_fail('duplicate output', t62 + '\nO1\n', 'duplicate output')
    must_fail('missing fact line', rep(t62, 'f F6 U\nc U - -d "No free air below the right hemidiaphragm is seen" @L14', 'c U - -d "No free air below the right hemidiaphragm is seen" @L14'), 'facts judged')
    must_fail('N needs C.pos claim', rep(t62, 'f F5 U -- v1 N (visualized bones unremarkable) -> U: 포괄 골 정상은 측만을 부정하지 않음(범위 규칙)', 'f F5 N "The visualized bones are unremarkable"'), 'needs C.pos')
    n_pass = sum(r['pass'] for r in res)
    save(out, {'n_checks': len(res), 'n_pass': n_pass, 'checks': res})
    print(f'{n_pass}/{len(res)} PASS')
    for r in res:
        if not r['pass']:
            print('FAIL', r['name'], r['detail'])
    sys.exit(0 if n_pass == len(res) else 1)


if __name__ == '__main__':
    main(Path(sys.argv[1]))
