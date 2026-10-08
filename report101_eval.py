"""iter_101 평가: 수동(assistant) 사실 판정표(judgments)에서 환자별 지표·paired 차이·민감도·사전 분기를 계산한다. 의미 판정은 생성하지 않는다.

판정표 형식(blind_id별):
 state: correct | wrong | none  (POS reference: 필요한 쪽(need_sides)에 흉수 존재를 확정 주장하면 correct; 존재를 부정하거나 반대쪽만이면 wrong; 언급 없음/불확정이면 none)
 opposing: bool    reference와 반대되는 흉수 주장(필요한 쪽의 명시 부정 등)
 internal_conflict: bool   출력 안에서 같은 쪽 흉수 존재와 부재를 모두 확정 주장
 atoms: {A1: kept|lost|ambiguous}   원 초안의 reference-지지 사실(P)의 보존 (U atom은 판정하지 않음)
 new_explicit_error: [quote]   K에 없던 새 주장 중 reference가 명시 반박하는 것
 unverifiable_added: [quote]   K에 없던 새 주장 중 reference에 없는 것(unknown)
 format: plain | json | other
 모든 quote는 해당 출력 원문의 부분문자열이어야 한다(대소문자 무시).
안전한 정답 환자(safe_correct) = state==correct ∧ ¬opposing ∧ ¬internal_conflict ∧ 모든 P atom=kept ∧ new_explicit_error 없음 (K 대비).
사전 분기(계획의 Evaluation 그대로, 결과 보기 전에 고정): decide() 참조.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

from report86_common import ROOT, save, sha

R101 = ROOT / 'results/iter_101'
CONDS = ['K', 'A', 'T', 'V', 'W']
BOOT_N, BOOT_SEED = 10000, 101017


def load_all():
    blind = R101 / 'eval/blind'
    mapping = json.loads((blind / 'private_mapping.json').read_text())
    review = json.loads((blind / 'review_input.json').read_text())['review']
    text = {o['blind_id']: o for p in review for o in p['outputs']}
    return mapping, review, text


def validate(judg, mapping, review, text):
    """판정표 완전성·quote 일치 검사. 문제 목록을 반환한다."""
    probs = []
    if set(judg) != set(mapping):
        probs.append(('judgment_ids_differ', sorted(set(mapping) ^ set(judg))))
    atoms_by_patient = {p['patient_index']: p['atoms'] for p in review}
    pat_of = {o['blind_id']: p['patient_index'] for p in review for o in p['outputs']}
    for b, j in judg.items():
        t = text[b]['text'].lower()
        if j['state'] not in ('correct', 'wrong', 'none'):
            probs.append((b, 'bad_state'))
        need = [a[0] for a in atoms_by_patient[pat_of[b]] if a[1] == 'P']
        if set(j['atoms']) != set(need):
            probs.append((b, 'atoms_mismatch', sorted(j['atoms']), need))
        if any(v not in ('kept', 'lost', 'ambiguous') for v in j['atoms'].values()):
            probs.append((b, 'bad_atom_value'))
        qs = list(j.get('new_explicit_error', [])) + list(j.get('unverifiable_added', [])) + list(j.get('opposing_quotes', [])) + \
            list(j.get('conflict_quotes', [])) + [q for q in [j.get('state_quote')] if q] + [q for q in j.get('atom_quotes', {}).values() if q]
        for q in qs:
            if q.lower() not in t:
                probs.append((b, 'quote_not_in_text', q))
        if j['opposing'] and not j.get('opposing_quotes'):
            probs.append((b, 'opposing_without_quote'))
        if j['internal_conflict'] and not j.get('conflict_quotes'):
            probs.append((b, 'conflict_without_quote'))
    return probs


def per_patient(judg, mapping, review):
    pat = {}
    for p in review:
        pat[p['patient_index']] = {'ref_state': p['ref_state'], 'cond': {}}
    for o_p in review:
        for o in o_p['outputs']:
            m = mapping[o['blind_id']]
            j = judg[o['blind_id']]
            lost = [a for a, v in j['atoms'].items() if v == 'lost']
            amb = [a for a, v in j['atoms'].items() if v == 'ambiguous']
            safe = j['state'] == 'correct' and not j['opposing'] and not j['internal_conflict'] and not lost and not amb and not j['new_explicit_error']
            safe_amb_excl = j['state'] == 'correct' and not j['opposing'] and not j['internal_conflict'] and not lost and not j['new_explicit_error']
            safe_unv_excl = safe and not j['unverifiable_added']
            safe_fmt = safe and j['format'] == 'plain' and not o['non_eos']
            harm = bool(lost or amb or j['new_explicit_error'] or j['internal_conflict'] or j['opposing'])
            pat[o_p['patient_index']]['cond'][m['condition']] = {
                'safe': safe, 'safe_ambiguous_atoms_excluded': safe_amb_excl, 'safe_unverifiable_excluded': safe_unv_excl,
                'safe_format_valid': safe_fmt,
                'harm_P_or_explicit': harm, 'P_lost': bool(lost), 'explicit_error': bool(j['new_explicit_error'] or j['opposing']),
                'internal_conflict': bool(j['internal_conflict']), 'state': j['state'], 'unverifiable_added': len(j['unverifiable_added']),
                'non_eos': text_flag(o), 'format': j['format'], 'chars': o['chars']}
    return pat


def text_flag(o):
    return bool(o['non_eos'])


def net(pat, x, y, key='safe', idx=None):
    ids = idx if idx is not None else sorted(pat)
    xo = sum(1 for i in ids if pat[i]['cond'][x][key] and not pat[i]['cond'][y][key])
    yo = sum(1 for i in ids if pat[i]['cond'][y][key] and not pat[i]['cond'][x][key])
    return xo - yo, xo, yo


def boot(pat, x, y, key='safe'):
    ids = sorted(pat)
    d = np.array([int(pat[i]['cond'][x][key]) - int(pat[i]['cond'][y][key]) for i in ids])
    rng = np.random.default_rng(BOOT_SEED)
    s = d[rng.integers(0, len(d), size=(BOOT_N, len(d)))].sum(axis=1)
    return {'net': int(d.sum()), 'ci95': [float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5))], 'degenerate': bool(len(set(s.tolist())) == 1)}


def loo(pat, x, y):
    ids = sorted(pat)
    vals = [net(pat, x, y, idx=[j for j in ids if j != i])[0] for i in ids]
    return {'min': min(vals), 'max': max(vals), 'values': dict(zip(ids, vals))}


def decide(pat, conflict_states, w_available=True):
    """계획의 사전 분기. 결과를 보기 전에 고정한 정의."""
    M = len(pat)
    ids = sorted(pat)
    t_safe = sum(pat[i]['cond']['T']['safe'] for i in ids)
    v_safe = sum(pat[i]['cond']['V']['safe'] for i in ids)
    vt, vt_o, tv_o = net(pat, 'V', 'T')
    vw, vw_o, wv_o = net(pat, 'V', 'W')
    by_state = {}
    for st in ('POS', 'NEG'):
        sub = [i for i in ids if pat[i]['ref_state'] == st]
        by_state[st] = {'n': len(sub), 'V_over_T': sum(1 for i in sub if pat[i]['cond']['V']['safe'] and not pat[i]['cond']['T']['safe'])}
    harm = {c: sum(pat[i]['cond'][c]['harm_P_or_explicit'] for i in ids) for c in CONDS}
    sens_amb = net(pat, 'V', 'T', 'safe_ambiguous_atoms_excluded')[0]
    sens_unv = net(pat, 'V', 'T', 'safe_unverifiable_excluded')[0]
    fmt = {c: sum(pat[i]['cond'][c]['safe_format_valid'] for i in ids) for c in CONDS}
    sens_fmt = {'V_minus_T': net(pat, 'V', 'T', 'safe_format_valid')[0], 'V_minus_W': net(pat, 'V', 'W', 'safe_format_valid')[0], 'safe_counts': fmt}
    crit = {'V_minus_T_ge_3': vt >= 3, 'V_minus_W_ge_2': w_available and vw >= 2,
            'T_improvement_in_both_states': by_state['POS']['V_over_T'] >= 1 and by_state['NEG']['V_over_T'] >= 1,
            'V_harm_not_above_K_and_T': harm['V'] <= harm['K'] and harm['V'] <= harm['T'],
            'direction_kept_ambiguous_atoms_excluded': sens_amb > 0, 'direction_kept_unverifiable_excluded': sens_unv > 0}
    one_state_bias = len(set(conflict_states)) < 2
    text_sufficient = t_safe == M and vt <= 0
    v_no_gain = vt <= 0 or harm['V'] > harm['T']
    if all(crit.values()):
        label = 'positive_exploration'
    elif text_sufficient:
        label = 'negative_text_sufficient'
    elif v_no_gain:
        label = 'negative_V_no_gain_hold_frozen_interface'
    else:
        label = 'inconclusive'
    return {'label': label, 'criteria': crit, 'V_minus_T': vt, 'V_only_vs_T': vt_o, 'T_only_vs_V': tv_o, 'V_minus_W': vw, 'V_only_vs_W': vw_o,
            'W_only_vs_V': wv_o, 'safe_counts': {c: sum(pat[i]['cond'][c]['safe'] for i in ids) for c in CONDS}, 'harm_counts': harm,
            'by_state_V_over_T': by_state, 'conflict_states': sorted(conflict_states), 'one_state_bias_in_conflict_group': one_state_bias,
            'sens_V_minus_T_ambiguous_atoms_excluded': sens_amb, 'sens_V_minus_T_unverifiable_excluded': sens_unv, 'sens_format_valid_only': sens_fmt, 'M': M, 'T_safe_all': t_safe == M}


def main():
    jf = Path(sys.argv[1])
    out = Path(sys.argv[2])
    mapping, review, text = load_all()
    judg = json.loads(jf.read_text())
    probs = validate(judg, mapping, review, text)
    assert not probs, probs
    sel = json.loads((R101 / 'data/lock/selection.json').read_text())
    atoms = json.loads((R101 / 'data/lock/atoms.json').read_text())
    inputs = {r['ImageID']: r for r in json.loads((R101 / 'data/inputs_S24.json').read_text())}
    conflict_states = [inputs[i]['stratum'] for i in sel['conflicts']]
    pat = per_patient(judg, mapping, review)
    dec = decide(pat, conflict_states)
    conflicts_idx = {atoms['index'][i] for i in sel['conflicts']}
    groups = {}
    for name, ids in (('conflict', sorted(conflicts_idx)), ('control', sorted(set(pat) - conflicts_idx))):
        groups[name] = {'n': len(ids), 'safe': {c: sum(pat[i]['cond'][c]['safe'] for i in ids) for c in CONDS},
                        'V_minus_T': net(pat, 'V', 'T', idx=ids), 'V_minus_W': net(pat, 'V', 'W', idx=ids),
                        'T_minus_K': net(pat, 'T', 'K', idx=ids), 'V_minus_K': net(pat, 'V', 'K', idx=ids)}
    # donor-recipient 연결 집단: donor를 공유하거나 donor 자신이 recipient이면 같은 집단
    don = sel['donors']
    par = {}

    def find(a):
        while par.setdefault(a, a) != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    for r, d in don.items():
        par[find(r)] = find(d)
    clusters = {}
    for r in don:
        clusters.setdefault(find(r), []).append(r)
    cl_idx = []
    for members in clusters.values():
        ix = [atoms['index'][m] for m in members if m in atoms['index']]
        if ix:
            cl_idx.append(ix)
    cl_net = {}
    for k in (('V', 'T'), ('V', 'W')):
        d = [sum(int(pat[i]['cond'][k[0]]['safe']) - int(pat[i]['cond'][k[1]]['safe']) for i in ix) for ix in cl_idx]
        cl_net[f'{k[0]}_minus_{k[1]}'] = {'cluster_sums': d, 'n_clusters': len(d), 'donor_reused': len(set(don.values())) < len(don)}
    report = {'decision': dec, 'groups': groups, 'bootstrap': {'V_minus_T': boot(pat, 'V', 'T'), 'V_minus_W': boot(pat, 'V', 'W'),
                                                              'T_minus_K': boot(pat, 'T', 'K'), 'V_minus_K': boot(pat, 'V', 'K')},
              'leave_one_patient_out': {'V_minus_T': loo(pat, 'V', 'T'), 'V_minus_W': loo(pat, 'V', 'W')}, 'donor_recipient_cluster': cl_net,
              'per_patient': {str(i): pat[i] for i in sorted(pat)}, 'judgments_sha256': sha(jf), 'code_sha256': sha(__file__),
              'note': 'assistant 수동 판정 기반 탐색 분석. 확증 검정 아님; CI는 gate로 쓰지 않음. 전문의 검토 아님.'}
    save(out, report)
    print(json.dumps({'label': dec['label'], 'safe_counts': dec['safe_counts'], 'V_minus_T': dec['V_minus_T'], 'V_minus_W': dec['V_minus_W'],
                      'harm': dec['harm_counts'], 'criteria': dec['criteria']}, indent=1))


if __name__ == '__main__':
    main()
