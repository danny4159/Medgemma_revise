"""iter_081 고정 대안 선택, paired 분석 및 원 계획 판정."""
import argparse
import numpy as np
import a81_common as C
import a81_run as R
import sp75_metrics as M


def candidates(rows):
    q = [r['Q'] for r in rows]; c = [r['C'] for r in rows]
    med = [int(np.searchsorted(np.cumsum(r['probs']), .5) + 1) for r in rows]
    out = {'Q': {'pred': q, 'calls': len(q), 'tau': -1},
           'C_argmax': {'pred': c, 'calls': 0, 'tau': -1},
           'C_median': {'pred': med, 'calls': 0, 'tau': -1}}
    for tau in [.2, .4, .6, .8, 1.01]:
        use = [max(r['probs']) < tau for r in rows]
        pred = [r['Q'] if u and r['Q'] is not None else r['C'] for r, u in zip(rows, use)]
        out[f'gate_{tau}'] = {'pred': pred, 'calls': sum(use), 'tau': tau}
    return out


def select():
    rows = C.read(C.ROOT / 'data/baseline_V8.json')
    cs = candidates(rows); true = [r['grade'] for r in rows]
    for v in cs.values():
        v['metrics'] = M.summary(true, v['pred'])
    # 완전 동률이면 위의 고정 후보 나열 순서. 결과를 보고 tie rule을 바꾸지 않는다.
    name = min(cs, key=lambda k: (cs[k]['metrics']['class_std_mae'], cs[k]['metrics']['mae'], cs[k]['calls'], cs[k]['tau']))
    out = {'name': name, 'candidates': cs, 'source_sha256': C.sha(C.ROOT / 'data/baseline_V8.json'),
           'rule': 'class_std_mae,mae,vlm_calls,tau; final exact tie fixed enumeration'}
    C.save(C.ROOT / 'selection.json', out)
    return out


def evaluate(split, protocol, out, dest):
    done = R.verify(protocol, out)
    rows = C.read(C.ROOT / f'data/baseline_{split}.json')
    sel = C.read(C.ROOT / 'selection.json')
    assert sel['source_sha256'] == C.sha(C.ROOT / 'data/baseline_V8.json')
    pred = {'Q': [r['Q'] for r in rows], 'C_argmax': [r['C'] for r in rows], 'M': candidates(rows)[sel['name']]['pred']}
    for cond in ('A', 'T', 'X'):
        rr = {x['request']['id']: x for x in done.values() if x['request']['cond'] == cond}
        assert set(rr) == {r['id'] for r in rows}
        pred[cond] = [rr[r['id']]['parsed'] for r in rows]
    true = [r['grade'] for r in rows]
    systems = {k: M.summary(true, v) for k, v in pred.items()}
    for k, v in systems.items():
        v['err_ge2_n'] = int(sum(M.abs_err(true, pred[k]) >= 2))
        v['invalid_n'] = sum(x is None for x in pred[k])
        v['matches_C_n'] = sum(a == b for a, b in zip(pred[k], pred['C_argmax']))
    paired = {f'A-{k}': M.boot_diff(rows, pred['A'], pred[k]) for k in ('M', 'T', 'X', 'Q', 'C_argmax')}
    err = {k: M.abs_err(true, v) for k, v in pred.items()}
    correction, damage, toward, disagreements = [], [], [], []
    for i, r in enumerate(rows):
        if err['A'][i] < err['C_argmax'][i]:
            correction.append(r['id'])
        if err['C_argmax'][i] == 0 and err['A'][i] > 0:
            damage.append(r['id'])
        q, a, c = pred['Q'][i], pred['A'][i], pred['C_argmax'][i]
        if q != c:
            disagreements.append({'id': r['id'], 'patient': r['patient'], 'grade': true[i], 'Q': q, 'C': c, 'A': a,
                                  'Q_error': float(err['Q'][i]), 'C_error': float(err['C_argmax'][i]), 'A_error': float(err['A'][i])})
        if q is not None and a is not None and err['Q'][i] < err['C_argmax'][i] and err['A'][i] > err['Q'][i] and abs(a-c) < abs(q-c):
            toward.append(r['id'])
    pats = {r['id']: r['patient'] for r in rows}
    nc = len({pats[i] for i in correction}); nt = len({pats[i] for i in toward})
    visual = all(paired['A-'+k]['point'] < 0 and paired['A-'+k]['ci95'][1] < 0 for k in ('T', 'X'))
    minimum = paired['A-M']['point'] <= -.1
    positive = minimum and paired['A-M']['ci95'][1] < 0 and visual and systems['A']['err_ge2_n'] <= systems['M']['err_ge2_n']
    pilot = not positive and visual and nc >= 2 and nt >= 2
    verdict = 'positive_exploratory' if positive else ('method_pilot_candidate' if pilot else ('negative' if not visual and not minimum else 'inconclusive'))
    report = {'split': split, 'n': len(rows), 'n_patients': len({r['patient'] for r in rows}), 'repeated_development': True,
              'M': sel['name'], 'systems': systems, 'paired': paired, 'predictions': pred, 'ids': [r['id'] for r in rows],
              'posthoc_transitions': {'C_error_reduced_ids': correction, 'C_error_reduced_patients': nc,
                  'C_correct_damaged_ids': damage, 'C_wrong_n': int(sum(err['C_argmax'] > 0)),
                  'C_wrong_made_exact_n': int(sum((err['C_argmax'] > 0) & (err['A'] == 0))),
                  'Q_better_moved_toward_C_ids': toward, 'Q_better_moved_toward_C_patients': nt,
                  'Q_C_disagreement': disagreements, 'A_X_changed_n': sum(a != x for a,x in zip(pred['A'], pred['X']))},
              'criteria': {'visual_contribution': visual, 'minimum_gain_vs_M': minimum, 'positive': positive, 'pilot_candidate': pilot, 'verdict': verdict},
              'proceed_E24': systems['A']['n'] - systems['A']['invalid_n'] >= 12 if split == 'V8' else None,
              'provenance': {'protocol': str(protocol), 'protocol_sha256': C.sha(protocol), 'out': str(out),
                  'baseline_sha256': C.sha(C.ROOT / f'data/baseline_{split}.json'), 'selection_sha256': C.sha(C.ROOT / 'selection.json')}}
    C.save(dest, report)
    print({'split': split, 'M': sel['name'], 'systems': {k:v['class_std_mae'] for k,v in systems.items()}, 'criteria': report['criteria']})
    return report


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('mode', choices=['select', 'eval'])
    ap.add_argument('--split'); ap.add_argument('--protocol'); ap.add_argument('--out'); ap.add_argument('--dest')
    a = ap.parse_args()
    if a.mode == 'select': print(select()['name'])
    else: evaluate(a.split, a.protocol, a.out, a.dest)
