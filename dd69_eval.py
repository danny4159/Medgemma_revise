"""iter_069 평가: 원시 응답 -> confusion counts / BA / 사전 고정 판정. 평가 진입점이 protocol·labels·cases·요청·출력 seal을 현재 파일과 대조한다.

사전 고정 규칙(plan.md Evaluation):
 - BA = (positive recall + negative recall)/2, positive = ADC LOW(YES), negative = NOT_LOW(NO). UNCERTAIN/invalid는 오답.
 - J = J_DA, J_AD 두 순서 점수의 평균(최선 순서 선택 없음). rule(SD+SA): HIGH&LOW->YES, 유효한 다른 조합->NO, UNCERTAIN/invalid 포함 -> 오답.
 - 10,000회 case bootstrap(seed 69), 한 class가 사라진 replicate는 제외하고 개수 보고. CI는 실행 gate가 아님.
 - recognition: SA BA>=0.75 & 각 class recall>=0.60. loss: recognition & (A-J>=0.10 or rule-J>=0.10) & J오답(두 순서 모두 오답)이면서 SA 정답인 독립 case>=2
   & leave-one-case-out으로 기준이 뒤집히지 않음. sufficiency: (A 또는 SA rule) BA>=0.80, class recall>=0.70, BA>=J, 비용 비증가.
   followup: loss 후보 & sufficiency 아님 & rule-J>=0.10 & 비용(rule)/비용(J)>=1.5.
 - R: A-J>=0.10인 모델에서만 실행(조건부)된 경우에 R-J, R-A 보고.
"""
import argparse, glob, hashlib, json, os, sys, time

import numpy as np

import dd69_run as R
import dd69_spec as S
import m65_run as B

SEED, NB = 69, 10000
EVAL_CODE = ['dd69_eval.py', 'dd69_spec.py', 'dd69_run.py']


def lock_eval(out, protos, gens):
    d = {'code': {f: B.sha_file(f) for f in EVAL_CODE}, 'labels': B.sha_file(R.LABELS), 'cases': B.sha_file(R.CASES), 'requests': {k: B.sha_file(v) for k, v in R.REQ.items()},
         'protocols': {m: B.sha_file(p) for m, p in protos.items()}, 'locked_at': time.strftime('%Y-%m-%dT%H:%M:%S')}
    with open(R.safe_out(out), 'x') as f:
        json.dump(d, f, indent=1)
    return d


def check_eval_lock(lock, protos):
    d = json.load(open(lock))
    cur = {'code': {f: B.sha_file(f) for f in EVAL_CODE}, 'labels': B.sha_file(R.LABELS), 'cases': B.sha_file(R.CASES), 'requests': {k: B.sha_file(v) for k, v in R.REQ.items()},
           'protocols': {m: B.sha_file(p) for m, p in protos.items()}}
    for k in cur:
        if cur[k] != d[k]:
            sys.exit('EVAL LOCK MISMATCH in ' + k)
    return d


def load_records(model, protocol, out_dir, requests):
    """출력 seal(verify.json)·protocol digest·요청 집합·record 파일 hash를 모두 대조한 뒤 rid->record 반환. 불일치는 즉시 중단."""
    R.req_in_protocol(requests, protocol)
    p = json.load(open(protocol))
    if p['model'] != model:
        sys.exit('protocol model mismatch')
    if p['components']['labels'] != B.sha_file(R.LABELS) or p['components']['cases'] != B.sha_file(R.CASES):
        sys.exit('labels/cases differ from protocol')
    ver = json.load(open(f'{out_dir}/verify.json'))
    if ver['n_problems'] or ver['protocol_digest'] != p['digest'] or ver['requests_sha256'] != B.sha_file(requests):
        sys.exit('verify seal mismatch ' + out_dir)
    for f, h in ver['record_file_sha256'].items():
        if B.sha_file(f) != h:
            sys.exit('record file changed after seal: ' + f)
    recs, cost = {}, {}
    for f in sorted(glob.glob(f'{out_dir}/worker*.jsonl')):
        for r in B.read_jsonl(f):
            if r['rid'] in recs:
                sys.exit('duplicate rid ' + r['rid'])
            recs[r['rid']] = r
    for f in glob.glob(f'{out_dir}/worker*.cost'):
        for r in B.read_jsonl(f):
            cost[r['rid']] = r
    rows = B.read_jsonl(requests)
    if set(recs) != {r['rid'] for r in rows}:
        sys.exit('record set != request set')
    for r in rows:
        if recs[r['rid']]['protocol_digest'] != p['digest']:
            sys.exit('record protocol digest mismatch')
    return recs, cost, rows


def answers(recs, rows):
    """(case, cond) -> parsed answer (None=invalid), final_non_eos."""
    out = {}
    for q in rows:
        r = recs[q['rid']]
        a = r['attempts'][-1]
        out[(q['case'], q['cond'])] = (S.parse(q['cond'], a['text']), bool(a['ended_eos']), r)
    return out


def rule_answer(sd, sa):
    if sd is None or sa is None or sd == 'UNCERTAIN' or sa == 'UNCERTAIN':
        return None
    return 'YES' if (sd == 'HIGH' and sa == 'LOW') else 'NO'


def ba(c, lab):
    pos, neg = c[lab == 1], c[lab == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float('nan')
    return 0.5 * (pos.mean() + neg.mean())


def recalls(c, lab):
    return (float(c[lab == 1].mean()) if (lab == 1).any() else float('nan'), float(c[lab == 0].mean()) if (lab == 0).any() else float('nan'))


def boot(fn, n, rng):
    vals, excluded = [], 0
    for _ in range(NB):
        ix = rng.integers(0, n, n)
        v = fn(ix)
        if np.isnan(v):
            excluded += 1
        else:
            vals.append(v)
    a = np.array(vals)
    if len(a) == 0:
        return [float('nan'), float('nan')], excluded
    return [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))], excluded


def analyze(model, recs, cost, rows, labels, rows_r=None, recs_r=None, cost_r=None, exclude_cases=()):
    cases = [c for c in sorted(int(k) for k in labels) if c not in exclude_cases]
    lab = np.array([1 if labels[str(c)]['label'] == 'LOW' else 0 for c in cases])
    ans = answers(recs, rows)
    gtm = {c: {k: labels[str(c)]['gt'][k] for k in S.CONDS} for c in cases}
    corr = {}
    for cond in ['SA', 'A', 'T', 'O', 'J_DA', 'J_AD']:
        corr[cond] = np.array([1.0 if ans[(c, cond)][0] == gtm[c][cond] else 0.0 for c in cases])
    corr['J'] = 0.5 * (corr['J_DA'] + corr['J_AD'])
    corr['SD_sens'] = np.array([1.0 if ans[(c, 'SD')][0] == 'HIGH' else 0.0 for c in cases])
    rl = [rule_answer(ans[(c, 'SD')][0], ans[(c, 'SA')][0]) for c in cases]
    corr['rule'] = np.array([1.0 if rl[i] == gtm[c]['A'] else 0.0 for i, c in enumerate(cases)])
    if recs_r is not None:
        ansr = answers(recs_r, rows_r)
        corr['R'] = np.array([1.0 if ansr[(c, 'R')][0] == gtm[c]['A'] else 0.0 for c in cases])
    rng = np.random.default_rng(SEED)
    res = {'model': model, 'n_cases': len(cases), 'n_low': int(lab.sum()), 'n_not_low': int((1 - lab).sum()), 'conds': {}}
    for k in ['SA', 'A', 'T', 'O', 'J_DA', 'J_AD', 'J', 'rule', 'R']:
        if k not in corr:
            continue
        r0, r1 = recalls(corr[k], lab)
        ci, ex = boot(lambda ix, k=k: ba(corr[k][ix], lab[ix]), len(cases), rng)
        res['conds'][k] = {'BA': ba(corr[k], lab), 'recall_LOW': r0, 'recall_NOT_LOW': r1, 'BA_CI95': ci, 'boot_excluded_single_class': ex}
    # confusion counts (원 응답 분포)
    cc = {}
    for cond in S.CONDS:
        tab = {}
        for i, c in enumerate(cases):
            g = gtm[c][cond]
            a = ans[(c, cond)][0]
            key = f'gt={g}|ans={"INVALID" if a is None else a}'
            tab[key] = tab.get(key, 0) + 1
        cc[cond] = tab
    res['confusion'] = cc
    res['rule_confusion'] = {}
    for i, c in enumerate(cases):
        key = f'gt={gtm[c]["A"]}|rule={"UNDECIDED" if rl[i] is None else rl[i]}'
        res['rule_confusion'][key] = res['rule_confusion'].get(key, 0) + 1
    res['sd_sensitivity_HIGH'] = float(corr['SD_sens'].mean())
    res['invalid_uncertain'] = {cond: {'invalid': sum(1 for c in cases if ans[(c, cond)][0] is None),
                                       'uncertain': sum(1 for c in cases if ans[(c, cond)][0] == 'UNCERTAIN'),
                                       'final_non_eos': sum(1 for c in cases if not ans[(c, cond)][1])} for cond in S.CONDS}
    res['order_disagreement_J'] = int(sum(1 for c in cases if ans[(c, 'J_DA')][0] != ans[(c, 'J_AD')][0]))
    # contrasts (case bootstrap)
    def diff(a, b):
        f = lambda ix: ba(corr[a][ix], lab[ix]) - ba(corr[b][ix], lab[ix])
        ci, ex = boot(f, len(cases), rng)
        return {'diff': ba(corr[a], lab) - ba(corr[b], lab), 'CI95': ci, 'boot_excluded_single_class': ex}
    pairs = [('A', 'J'), ('SA', 'A'), ('rule', 'J'), ('A', 'T'), ('J', 'T'), ('J_DA', 'J_AD'), ('A', 'O'), ('O', 'T')]
    if 'R' in corr:
        pairs += [('R', 'J'), ('R', 'A')]
    res['contrasts'] = {f'{a}-{b}': diff(a, b) for a, b in pairs}
    # cost: 사례별 합 (모델 단일 attempt 기준 read->save)
    def c_of(rid, rr, cc_):
        r = rr[rid]['total_read_to_save_start_s']
        return r + (cc_[rid]['save_s'] if rid in cc_ else 0.0)
    cm = {}
    for cond in S.CONDS:
        cm[cond] = np.array([c_of(f'c{c}_{cond}', recs, cost) for c in cases])
    res['cost_s_mean_per_request'] = {k: float(v.mean()) for k, v in cm.items()}
    costJ = 0.5 * (cm['J_DA'] + cm['J_AD'])
    costRule = cm['SD'] + cm['SA']
    ratio = lambda ix: costRule[ix].sum() / costJ[ix].sum()
    ci, _ = boot(ratio, len(cases), rng)
    res['cost'] = {'rule_SD_plus_SA_over_J': float(costRule.sum() / costJ.sum()), 'rule_ratio_CI95': ci,
                   'A_over_J': float(cm['A'].sum() / costJ.sum()), 'SA_over_J': float(cm['SA'].sum() / costJ.sum()),
                   'n_cost_rows_missing': sum(1 for c in cases for cond in S.CONDS if f'c{c}_{cond}' not in cost),
                   'note': 'read->answer saved monotonic wall time per request; MedGemma ran 2 workers sharing one GPU, Qwen 1 worker; latency, not throughput'}
    # 판정
    s = res['conds']
    rec_ok = s['SA']['BA'] >= 0.75 and s['SA']['recall_LOW'] >= 0.60 and s['SA']['recall_NOT_LOW'] >= 0.60
    dA, dR = res['contrasts']['A-J']['diff'], res['contrasts']['rule-J']['diff']
    jwrong = [c for i, c in enumerate(cases) if corr['J_DA'][i] == 0 and corr['J_AD'][i] == 0 and corr['SA'][i] == 1]
    def loo_pass(i_out):
        keep = np.array([i != i_out for i in range(len(cases))])
        d1 = ba(corr['A'][keep], lab[keep]) - ba(corr['J'][keep], lab[keep])
        d2 = ba(corr['rule'][keep], lab[keep]) - ba(corr['J'][keep], lab[keep])
        return max(d1, d2) >= 0.10
    loss_pt = rec_ok and (dA >= 0.10 or dR >= 0.10)
    loo_flip = [cases[i] for i in range(len(cases)) if loss_pt and not loo_pass(i)]
    loss_cand = loss_pt and len(jwrong) >= 2 and not loo_flip
    costJ_total = float(costJ.sum())
    def suff(k, cost_k):
        r0, r1 = recalls(corr[k], lab)
        return ba(corr[k], lab) >= 0.80 and r0 >= 0.70 and r1 >= 0.70 and ba(corr[k], lab) >= ba(corr['J'], lab) and cost_k <= costJ_total
    suffA, suffSA = suff('A', float(cm['A'].sum())), suff('SA', float(cm['SA'].sum()))
    followup = loss_cand and not (suffA or suffSA) and dR >= 0.10 and res['cost']['rule_SD_plus_SA_over_J'] >= 1.5
    res['decision'] = {'recognition_SA_ok': bool(rec_ok), 'A_minus_J': dA, 'rule_minus_J': dR, 'R_condition_met_A_minus_J_ge_0.10': bool(dA >= 0.10),
                       'loss_point_criterion': bool(loss_pt), 'J_wrong_SA_right_cases': jwrong, 'loo_flip_cases': loo_flip, 'loss_candidate': bool(loss_cand),
                       'sufficient_A': bool(suffA), 'sufficient_SA_rule': bool(suffSA), 'followup_method_candidate': bool(followup),
                       'oracle_BA': s['O']['BA'], 'text_only_BA': s['T']['BA']}
    # 부위별 표(label과 target 연결)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['lock', 'run'])
    ap.add_argument('--out', required=True)
    ap.add_argument('--main-medgemma', default='results/iter_069/gen/main_medgemma')
    ap.add_argument('--main-qwen', default='results/iter_069/gen/main_qwen')
    ap.add_argument('--r-medgemma', default=''); ap.add_argument('--r-qwen', default='')
    ap.add_argument('--lock', default='results/iter_069/eval/eval_lock.json')
    a = ap.parse_args()
    protos = {'medgemma': 'results/iter_069/protocol/protocol_medgemma_v2.json', 'qwen': 'results/iter_069/protocol/protocol_qwen_v2.json'}
    if a.cmd == 'lock':
        os.makedirs(os.path.dirname(R.safe_out(a.out)), exist_ok=True)
        print(json.dumps(lock_eval(a.out, protos, None))[:200])
        return 0
    lk = check_eval_lock(a.lock, protos)
    labels = json.load(open(R.LABELS))
    cases = {c['case']: c for c in json.load(open(R.CASES))['cases']}
    tech_cases = (7006, 14955)
    out = {'eval_lock': lk, 'models': {}}
    for m, od, rd in (('medgemma', a.main_medgemma, a.r_medgemma), ('qwen', a.main_qwen, a.r_qwen)):
        recs, cost, rows = load_records(m, protos[m], od, R.REQ['main'])
        kw = {}
        if rd:
            rr, rc, rrows = load_records(m, protos[m], rd, R.REQ['R'])
            kw = {'rows_r': rrows, 'recs_r': rr, 'cost_r': rc}
        full = analyze(m, recs, cost, rows, labels, **kw)
        notech = analyze(m, recs, cost, rows, labels, exclude_cases=tech_cases, **kw)
        out['models'][m] = {'all_20': full, 'excluding_tech_cases': notech,
                            'engine': {'attempt_files': sorted(os.path.basename(f) for f in glob.glob(f'{od}/worker*.attempt_*.json'))}}
    out['by_case'] = {str(c): {'label': labels[str(c)]['label'], 'target': cases[c]['target']} for c in sorted(cases)}
    with open(R.safe_out(a.out), 'x') as f:
        json.dump(out, f, indent=1)
    for m, v in out['models'].items():
        s = v['all_20']['conds']
        print(m, {k: round(x['BA'], 3) for k, x in s.items()}, v['all_20']['decision'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
