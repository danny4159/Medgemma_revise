"""이번 변경의 독립 범위·분기·gate·관찰표 회귀 검사. 생성/임상 판정 없음."""
import copy
import itertools
import json
import random
from pathlib import Path

import ed116_eval as EV
import ed117_verify as V
from ed117_run import technical_gate
from ed117_analyze import observations


def main():
    checks = []
    def check(name, ok):
        checks.append(dict(name=name, passed=bool(ok)))
        print(('PASS ' if ok else 'FAIL ') + name)
    rng = random.Random(11617)
    pats = []
    for i in range(8):
        base = EV.derive(rng.choice(['yes', 'no']), rng.choice(['yes', 'no']),
                         *[rng.choice(['yes', 'no', None]) for _ in range(5)])
        p = dict(id=str(i), cat='opacity', y='yes', base=base, n_det=2, n_gt=3, tp03=2, tp05=1)
        pats.append(p)
        check('shared_scalar_' + str(i), EV.point_scalars(p) == V.scalar(p, base))
        lo, hi = EV.range_scalars(p)
        vl, vh = V.bounds(p)
        check('independent_all_bounds_' + str(i), lo == vl and hi == vh)
    actual, expected = EV.group_report(pats), V.group(pats)
    check('all_counts_ranges_ci_unresolved', all(x['passed'] for x in V.compare_group(expected, actual)))
    altered = copy.deepcopy(actual)
    altered['n_unresolved_cells']['E'] += 1
    check('unresolved_count_tamper_detected', not all(x['passed'] for x in V.compare_group(expected, altered)))
    altered = copy.deepcopy(actual)
    altered['range_min']['diff_R_S'] += 1
    check('shared_range_tamper_detected', not all(x['passed'] for x in V.compare_group(expected, altered)))
    check('E_shared_with_S', V.policies(dict(K='no', B='yes', G='no', N='no', E='yes', R='yes', T='no'))['S'] == 'yes'
          and V.policies(dict(K='no', B='yes', G='no', N='no', E='no', R='yes', T='no'))['S'] == 'no')
    check('G_shared_with_M', V.policies(dict(K='yes', B='no', G='no', N='no', E='yes', R='yes', T='no'))['M'] == 'no'
          and V.policies(dict(K='yes', B='no', G='yes', N='no', E='yes', R='yes', T='no'))['M'] == 'yes')
    def synth(cor=10, harm=5, diff=5, ag_harm=4, ag_den=80):
        pt = dict(correction_R=cor, harm_R=harm, **{f'diff_R_{q}': diff for q in V.COMP})
        mm = dict(point=pt.copy(), range_min=pt.copy(), range_max=pt.copy())
        ag = dict(n_K_correct=ag_den, point=dict(harm_R=ag_harm), range_min=dict(harm_R=ag_harm), range_max=dict(harm_R=ag_harm))
        return mm, ag
    cases = [('exact_boundary', {}, 'positive_exploratory'),
             ('correction_9', dict(cor=9), 'hold_current_frozen_setting'),
             ('harm_6', dict(harm=6), 'hold_current_frozen_setting'),
             ('diff_4', dict(diff=4), 'hold_current_frozen_setting'),
             ('agreement_rate_above5pct', dict(ag_harm=5), 'hold_current_frozen_setting'),
             ('agreement_actual_denominator', dict(ag_den=79), 'hold_current_frozen_setting')]
    for name, kw, label in cases:
        mm, ag = synth(**kw)
        d, v = EV.decide(mm, ag), V.decision(mm, ag)
        check(name, all(d[k] == v[k] for k in v) and v['label'] == label)
    mm, ag = synth()
    mm['range_min']['correction_R'] = 9
    d, v = EV.decide(mm, ag), V.decision(mm, ag)
    check('inconclusive_point_pass_worst_fails', v['label'] == 'inconclusive_unresolved_flips_criteria' and all(d[k] == v[k] for k in v))
    mm, ag = synth(cor=9)
    mm['range_max']['correction_R'] = 10
    d, v = EV.decide(mm, ag), V.decision(mm, ag)
    check('inconclusive_component_best_only', v['label'] == 'inconclusive_unresolved_could_satisfy' and all(d[k] == v[k] for k in v))
    recs = []
    for fn in Path('results/iter_116/gen/TECH_w2').glob('gen_worker*.jsonl'):
        recs += [json.loads(l) for l in fn.read_text().splitlines()]
    sel = json.load(open('results/iter_116/lock/selection.json'))
    gate = technical_gate(recs, sel['tech'])
    check('T_response_auxiliary_only', gate['run'] and not gate['original_gate_run'] and gate['per_condition']['T']['n_resolved'] == 5)
    check('T_missing_input_still_blocks', not technical_gate([r for r in recs if r['cond'] != 'T'], sel['tech'])['run'])
    bad = copy.deepcopy(recs)
    for r in bad:
        if r['cond'] == 'N':
            r['suffix_text_raw'] = 'Cannot answer.'
    check('NER_response_gate_still_required', not technical_gate(bad, sel['tech'])['run'])
    check('duplicate_tech_still_blocks', not technical_gate(recs + [recs[0]], sel['tech'])['run'])
    obs = observations(dict(mismatch=pats, control=pats), [], {})
    check('observation_denominators_full', all(sum(t['policies'][q].values()) == t['n'] for t in obs['strata'].values() for q in V.POL))
    check('paired_state_partitions_full', all(sum(t['n'] for t in cells.values()) == len(pats) for g in obs['paired'].values() for cells in g.values()))
    out = dict(all_pass=all(c['passed'] for c in checks), n=len(checks), n_pass=sum(c['passed'] for c in checks), checks=checks)
    p = Path('results/iter_117/tests/fixtures_amendment.json')
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x') as f:
        json.dump(out, f, indent=1)
    print(out['n_pass'], '/', out['n'])
    raise SystemExit(0 if out['all_pass'] else 1)


if __name__ == '__main__':
    main()
