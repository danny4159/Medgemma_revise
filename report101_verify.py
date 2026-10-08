"""iter_101 독립 산술 검증: judgments.json(원시 판정)과 완료 검증된 원 생성 record에서 report.json의 수치를 다른 코드 경로로 다시 계산한다.

report101_eval의 per_patient/net/decide를 import하지 않는다(별도 단순 루프). 의미 판정의 정확성은 검증하지 않는다(의미 검토와 산술 검증은 별개).
검사: (1) blind 검토 텍스트 == 원 worker record text(K/A는 CURE record에서 재구성), (2) 모든 quote가 원문에 존재, (3) 환자·조건별 safe, 안전 수·net·harm·민감도·분기,
(4) bootstrap/LOO 재계산, (5) 선정 잠금(충돌 도출·donor 반대 상태·요청 W 영상 출처) 재확인.
"""
import json
import sys
from pathlib import Path

import numpy as np

import report101_blind as BL
import report101_gen as G
import report101_req as RQ
from report86_common import ROOT, save, sha

R = ROOT / 'results/iter_101'
CONDS = ['K', 'A', 'T', 'V', 'W']


def main():
    out = {'checks': {}}
    gen = R / 'gen/main'
    workers = json.loads((gen / 'mapping.json').read_text())['workers']
    rows, expected = G.verify(gen, str(R / 'data/corr_main/requests.json'), workers)
    raw = {r['id']: r['text'] for r in rows}
    sel = json.loads((R / 'data/lock/selection.json').read_text())
    recs = RQ.load_cure('S24')
    mp = json.loads((R / 'eval/blind/private_mapping.json').read_text())
    review = json.loads((R / 'eval/blind/review_input.json').read_text())['review']
    shown = {o['blind_id']: o['text'] for p in review for o in p['outputs']}
    jd = json.loads((R / 'eval/judgments.json').read_text())
    bad_text = []
    for b, m in mp.items():
        img, c = m['ImageID'], m['condition']
        pk = RQ.package(img, recs)
        want = pk['draft'] if c == 'K' else BL.a_text(pk) if c == 'A' else raw[f'{img}|{c}']
        if shown[b] != want:
            bad_text.append(b)
    out['checks']['blind_text_equals_raw_records'] = {'n': len(mp), 'mismatch': bad_text, 'pass': not bad_text}
    bad_q = []
    for b, j in jd.items():
        t = shown[b].lower()
        qs = j['new_explicit_error'] + j['unverifiable_added'] + j['opposing_quotes'] + j['conflict_quotes'] + ([j['state_quote']] if j['state_quote'] else []) + \
            [q for q in j['atom_quotes'].values() if q]
        bad_q += [(b, q) for q in qs if q.lower() not in t]
    out['checks']['quotes_in_text'] = {'bad': bad_q, 'pass': not bad_q}
    # 선정 잠금 재확인
    claims = json.loads((R / 'data/lock/claims.json').read_text())
    inputs = {r['ImageID']: r for r in json.loads((R / 'data/inputs_S24.json').read_text())}
    don_ok = all(inputs[sel['donors'][i]]['stratum'] != inputs[i]['stratum'] for i in sel['selected_order'])
    reqs = {r['id']: r for r in json.loads((R / 'data/corr_main/requests.json').read_text())}
    w_ok = all(reqs[f'{i}|W']['image_source_ImageID'] == sel['donors'][i] and reqs[f'{i}|V']['image_source_ImageID'] == i and reqs[f'{i}|T']['image'] is None
               for i in sel['selected_order'])
    # 충돌 독립 재도출: neg와 pos가 서로 다른 source에서 같은 쪽을 덮는 경우만(단순 구현)
    def sides(s):
        return {'L': 'L', 'R': 'R'}.get(s, 'LR')
    conf = []
    for img, cl in claims['claims'].items():
        hit = False
        for p in cl:
            if p[1] != 'pos':
                continue
            if p[2] == 'unspec':
                cover = ''.join(sorted(set(''.join(sides(n[2]) for n in cl if n[1] == 'neg' and n[0] != p[0]))))
                hit = hit or cover == 'LR'
            else:
                hit = hit or any(n[1] == 'neg' and n[0] != p[0] and set(sides(n[2])) & set(sides(p[2])) for n in cl)
        if hit:
            conf.append(img)
    out['checks']['lock'] = {'conflicts_rederived_equal': sorted(conf) == sorted(sel['conflicts']), 'donor_opposite_state': don_ok, 'request_images_as_locked': w_ok,
                             'n_conflicts': len(conf), 'controls_all_non_conflict': not set(sel['controls']) & set(conf)}
    out['checks']['lock']['pass'] = out['checks']['lock']['conflicts_rederived_equal'] and don_ok and w_ok and out['checks']['lock']['controls_all_non_conflict']
    # 환자·조건별 safe 재계산
    table = {}
    for b, m in mp.items():
        j = jd[b]
        lost = [k for k, v in j['atoms'].items() if v == 'lost']
        amb = [k for k, v in j['atoms'].items() if v == 'ambiguous']
        base = j['state'] == 'correct' and not j['opposing'] and not j['internal_conflict'] and not j['new_explicit_error']
        table[(m['ImageID'], m['condition'])] = {'safe': base and not lost and not amb, 'safe_amb': base and not lost, 'safe_unv': base and not lost and not amb and not j['unverifiable_added'],
                                                  'safe_fmt': base and not lost and not amb and j['format'] == 'plain' and not [r for r in rows if r['id'] == f"{m['ImageID']}|{m['condition']}" and not r['attempts'][-1]['ended_eos']].__len__() > 0 if m['condition'] in 'TVW' else base and not lost and not amb,
                                                  'harm': bool(lost or amb or j['new_explicit_error'] or j['internal_conflict'] or j['opposing'])}
    imgs = sel['selected_order']
    def cnt(c, k='safe'):
        return sum(table[(i, c)][k] for i in imgs)
    def net(a, b, k='safe'):
        return sum(table[(i, a)][k] for i in imgs if not table[(i, b)][k]) - sum(table[(i, b)][k] for i in imgs if not table[(i, a)][k])
    mine = {'safe': {c: cnt(c) for c in CONDS}, 'harm': {c: sum(table[(i, c)]['harm'] for i in imgs) for c in CONDS},
            'V_minus_T': net('V', 'T'), 'V_minus_W': net('V', 'W'), 'sens_amb': net('V', 'T', 'safe_amb'), 'sens_unv': net('V', 'T', 'safe_unv'),
            'sens_fmt_V_minus_T': net('V', 'T', 'safe_fmt'), 'sens_fmt_V_minus_W': net('V', 'W', 'safe_fmt')}
    rep = json.loads((R / 'eval/report.json').read_text())
    d = rep['decision']
    cmp_ = {'safe_counts': mine['safe'] == d['safe_counts'], 'harm_counts': mine['harm'] == d['harm_counts'], 'V_minus_T': mine['V_minus_T'] == d['V_minus_T'],
            'V_minus_W': mine['V_minus_W'] == d['V_minus_W'], 'sens_amb': mine['sens_amb'] == d['sens_V_minus_T_ambiguous_atoms_excluded'],
            'sens_unv': mine['sens_unv'] == d['sens_V_minus_T_unverifiable_excluded'],
            'sens_fmt': (mine['sens_fmt_V_minus_T'], mine['sens_fmt_V_minus_W']) == (d['sens_format_valid_only']['V_minus_T'], d['sens_format_valid_only']['V_minus_W'])}
    # 분기 재도출
    t_all = mine['safe']['T'] == len(imgs)
    crit_pos = (mine['V_minus_T'] >= 3 and mine['V_minus_W'] >= 2 and mine['harm']['V'] <= min(mine['harm']['K'], mine['harm']['T']) and mine['sens_amb'] > 0 and mine['sens_unv'] > 0
                and any(table[(i, 'V')]['safe'] and not table[(i, 'T')]['safe'] for i in imgs if inputs[i]['stratum'] == 'POS')
                and any(table[(i, 'V')]['safe'] and not table[(i, 'T')]['safe'] for i in imgs if inputs[i]['stratum'] == 'NEG'))
    label = 'positive_exploration' if crit_pos else 'negative_text_sufficient' if (t_all and mine['V_minus_T'] <= 0) else \
        'negative_V_no_gain_hold_frozen_interface' if (mine['V_minus_T'] <= 0 or mine['harm']['V'] > mine['harm']['T']) else 'inconclusive'
    cmp_['label'] = label == d['label']
    out['checks']['recomputed_vs_report'] = {'mine': mine, 'label_mine': label, 'label_report': d['label'], 'equal': cmp_, 'pass': all(cmp_.values())}
    # bootstrap / LOO
    diffs = {'V_T': np.array([int(table[(i, 'V')]['safe']) - int(table[(i, 'T')]['safe']) for i in imgs]),
             'V_W': np.array([int(table[(i, 'V')]['safe']) - int(table[(i, 'W')]['safe']) for i in imgs])}
    bt = {}
    for k, v in diffs.items():
        rng = np.random.default_rng(101017)
        idx = rng.integers(0, len(v), size=(10000, len(v)))
        sums = sorted(int(sum(v[j] for j in row)) for row in idx)
        bt[k] = [float(np.percentile(sums, 2.5)), float(np.percentile(sums, 97.5))]
    loo = {k: sorted(int(v.sum() - v[i]) for i in range(len(v))) for k, v in diffs.items()}
    rb = rep['bootstrap']
    out['checks']['bootstrap_loo'] = {'mine_ci': bt, 'report_ci': {'V_T': rb['V_minus_T']['ci95'], 'V_W': rb['V_minus_W']['ci95']},
                                       'loo_mine': loo, 'pass': bt['V_T'] == rb['V_minus_T']['ci95'] and bt['V_W'] == rb['V_minus_W']['ci95'] and
                                       loo['V_T'] == sorted(rep['leave_one_patient_out']['V_minus_T']['values'].values()) and
                                       loo['V_W'] == sorted(rep['leave_one_patient_out']['V_minus_W']['values'].values())}
    out['all_pass'] = all(v['pass'] for v in out['checks'].values())
    out['scope'] = '산술·연결 재계산만. assistant 의미 판정(state/atoms/오류 분류)의 임상적 정확성은 검증하지 않는다.'
    out['code_sha256'] = sha(__file__)
    save(R / 'eval/verify.json', out)
    print(json.dumps({k: v['pass'] for k, v in out['checks'].items()}), out['all_pass'], label)


if __name__ == '__main__':
    main()
