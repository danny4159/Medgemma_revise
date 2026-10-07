"""iter_096 회귀·fixture 검사. P001/P004/P005/P018의 실제 문장, 반대 예제, 변조 거부.
사용: python test_report96.py <out.json>   (새 파일만 쓴다)"""
import copy
import json
import sys

import report96_eval as E
import report96_sem as S
import report96_verify as V
from report96_lock import R96
from report86_common import save


def claims(sent, region='left lung'):
    return S.analyze_sentence(sent, region)


def mk(sent, region, oid='O01', cond='D', p=0):
    cl = []
    for i, c in enumerate(claims(sent, region)):
        cl.append(dict(c, p=p, oid=oid, cond=cond, region=region, eos=True, s=0, c=i, quote=sent, start=0, end=len(sent), cid='%d:%s:0:%d' % (p, oid, i)))
    return cl


def status(pos_sent, pos_region, neg_sent, neg_region, mode='question', lz=False):
    ps, ns = mk(pos_sent, pos_region, 'O01'), mk(neg_sent, neg_region, 'O02')
    out = []
    for p in ps:
        for n in ns:
            out.append(E.pair_status(p, n, mode, lz))
    return out


def main(outp):
    t = []

    def ok(name, cond, detail=None):
        t.append({'name': name, 'pass': bool(cond), 'detail': detail})

    # --- P005: 원인 hedge는 존재 hedge가 아니다 / 시간은 별도 항목
    c = claims('There is a new right upper lobe opacity, which may represent pneumonia.')[0]
    ok('P005_presence_definite_cause_hedged', c['pres'] == 'definite' and c['cause'] == [{'name': 'pneumonia', 'cert': 'hedged'}] and c['temporal'] == 'new', c)
    c = claims('There is a possible opacity in the right upper lobe.')
    ok('presence_hedge_detected', c and c[0]['pres'] == 'hedged', c)
    # --- P004/P018: 급성 부정은 확정 충돌이 아니다, 구체 부정은 확정
    st = status('In the right lower lobe, a small infiltrate is seen.', 'right mid lung zone', 'No acute pulmonary infiltrates are identified.', 'right lung')
    ok('P018_acute_negation_not_definite', st == ['qualified'], st)
    st = status('In the right lower lobe, a small infiltrate is seen.', 'right mid lung zone', 'No infiltrates or lung condensations are appreciated.', 'right lung')
    ok('P004_specific_negation_whole_lung_definite', 'definite' in st, st)
    st = status('In the right lower lobe, a small infiltrate is seen.', 'right mid lung zone', 'No infiltrates or lung condensations are appreciated.', 'right lower lung zone')
    ok('lobe_vs_zone_same_level_uncertain', 'uncertain_scope' in st and 'definite' not in st, st)
    st = status('In the right lower lobe, a small infiltrate is seen.', 'right mid lung zone', 'No infiltrates or lung condensations are appreciated.', 'right lower lung zone', lz=True)
    ok('lobe_zone_equal_sensitivity_definite', 'definite' in st, st)
    st = status('In the right lower lobe, a small infiltrate is seen.', 'right mid lung zone', 'No infiltrates or lung condensations are appreciated.', 'left lung')
    ok('opposite_side_no_conflict', st == [None] * len(st), st)
    # --- 정상 폐 실질 표현(P018, 소견명 없이도 부정으로 기록), 기구·혈관 정상은 폐 소견 부정이 아니다
    ok('P018_parenchyma_normal_is_clear', [x['kind'] for x in claims('The pulmonary parenchyma shows a normal structure.')] == ['clear'])
    ok('vascular_normal_not_lung_negation', claims('The pulmonary vascularity is normal.') == [] and claims('There is no pleural effusion or pneumothorax.') == [])
    st = status('There is a vague opacity in the left upper lung which could represent a granuloma.', 'left upper lung zone', 'The lungs are clear.', 'right lung')
    ok('explicit_lungs_clear_global_primary_conflict', 'definite' in st, st)
    st = status('There is a vague opacity in the left upper lung which could represent a granuloma.', 'left upper lung zone', 'The lungs are clear.', 'right lung', mode='narrow')
    ok('plural_lungs_narrow_sensitivity_no_conflict', st == [None] * len(st), st)
    # --- 급성 부정(P004/P018): 일반 acute cardiopulmonary 문장은 소견 부정으로 세지 않는다
    ok('generic_acute_cardiopulmonary_not_a_claim', claims('No evidence of acute cardiopulmonary disease.') == [] and claims('No acute cardiopulmonary process.') == [])
    ok('resolved_is_qualified_negation', claims('The previously described opacities in the right lower lobe have resolved.')[0]['neg'] == 'qualified')
    # --- P001: 시간 표현은 별도 항목, 'again'
    c = claims('In comparison with the study of ___, there is again increased opacification at the right base medially, consistent with pneumonia.')[0]
    ok('P001_temporal_again_cause_probable', c['temporal'] == 'again' and c['cause'] == [{'name': 'pneumonia', 'cert': 'probable'}] and c['scope']['level'] == 'L', c)
    # --- 문장별 분리·번호 목록 offset
    r = S.analyze_text('There is a new left lower lobe opacity. 1. New left lower lobe opacity concerning for pneumonia.', 'left mid lung zone')
    txt = 'There is a new left lower lobe opacity. 1. New left lower lobe opacity concerning for pneumonia.'
    ok('numbered_list_offsets', len(r) == 2 and all(txt[x['start']:x['end']] == x['quote'] for x in r) and r[1]['quote'].startswith('New left'), [x['quote'] for x in r])
    # --- 범위: 폐 전체 vs lobe 포함, 다른 level 은 겹침 없음
    a = dict(sides='L', level=None, type='lung')
    b = dict(sides='L', level='L', type='lobe')
    ok('lung_contains_lobe', E.ovl(a, b) == 2 and E.ovl(b, dict(sides='L', level='U', type='lobe')) == 0 and E.ovl(b, dict(sides='L', level='L', type='zone')) == 1)
    # --- 변조 거부(quote offset, text hash, 중복 id)
    man = json.loads((R96 / 'lock/input_manifest.json').read_text())
    J = json.loads((R96 / 'judging/judgments_E32_v3.json').read_text())
    texts, recs = V.raw_texts(man)
    n, bad = V.check_offsets(J, texts)
    ok('offsets_clean_on_real_data', n > 0 and not bad, [n, len(bad)])
    J2 = copy.deepcopy(J)
    o = next(o for o in J2['outputs'] if o['sentences'])
    o['sentences'][0]['start'] += 1
    n, bad = V.check_offsets(J2, texts)
    ok('tamper_offset_rejected', len(bad) == 1, bad)
    J3 = copy.deepcopy(J)
    o = next(o for o in J3['outputs'] if o['sentences'])
    o['sentences'][0]['quote'] = o['sentences'][0]['quote'] + 'x'
    n, bad = V.check_offsets(J3, texts)
    ok('tamper_quote_rejected', len(bad) == 1, bad)
    J4 = copy.deepcopy(J)
    J4['outputs'][0]['text_sha256'] = '0' * 64
    n, bad = V.check_offsets(J4, texts)
    ok('tamper_text_hash_rejected', len(bad) >= 1, bad[:1])
    ids = [o['request_id'] for o in J['outputs']]
    ok('request_ids_unique', len(ids) == len(set(ids)) == 544)
    # --- 비EOS는 숨기지 않는다
    ne = [(o['p'], o['oid'], o['cond'], o['region']) for o in J['outputs'] if not o['ended_eos']]
    ok('non_eos_final_kept_and_listed', ne == [(7, 'O03', 'L', 'left lung')], ne)
    ok('all', True)
    t.pop()
    res = {'n': len(t), 'n_pass': sum(x['pass'] for x in t), 'tests': t}
    save(R96 / 'tests' / outp, res)
    print(res['n_pass'], '/', res['n'])
    for x in t:
        if not x['pass']:
            print('FAIL', x)
    return res['n_pass'] == res['n']


if __name__ == '__main__':
    sys.exit(0 if main(sys.argv[1]) else 1)
