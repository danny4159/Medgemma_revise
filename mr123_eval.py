"""iter_123: 평가 (BA 주지표). usage: python mr123_eval.py <stage> <out_json> [--protocol protocol.json]
UNCERTAIN/INVALID는 정답으로 세지 않는다. 양·음성 층 내 환자 paired bootstrap 10,000회, seed122, 95% CI.
"""
import hashlib, json, os, sys
import numpy as np
import mr123_run as R

SEED = 122
NB = 10000


def load_stage(stage):
    reqs = R.read_jsonl(R.GEN + stage + '/requests.jsonl')
    rid = [r['id'] for r in reqs]
    assert len(set(rid)) == len(rid)
    recs = {}
    for fn in sorted(os.listdir(R.GEN + stage)):
        if fn.startswith('worker_') and fn.endswith('.jsonl'):
            for r in R.read_jsonl(R.GEN + stage + '/' + fn):
                assert r['id'] not in recs, 'duplicate id ' + r['id']
                recs[r['id']] = r
    missing = set(rid) - set(recs)
    extra = set(recs) - set(rid)
    assert not missing and not extra, (len(missing), len(extra))
    # 요청-출력 연결, 현재 PNG hash 재검증, parser 재적용
    for q in reqs:
        r = recs[q['id']]
        assert r['cond'] == q['cond'] and r['study_uid'] == q['study_uid']
        for p, h in zip(q['paths'], q['png_sha256']):
            d = hashlib.sha256(open(p, 'rb').read()).hexdigest()
            assert d == h, 'png changed ' + p
        st, code = R.parse(r['text'])
        assert (st, code) == (r['state'], r['parse_code']), 'parser mismatch'
    return reqs, recs


def patient_table(reqs, recs):
    pt = {}
    for q in reqs:
        r = recs[q['id']]
        p = pt.setdefault(q['patient_uid'], dict(label=q['label'], batch=q['batch_id'], study=q['study_uid']))
        p[q['cond']] = r['state']
        p[q['cond'] + '_eos'] = r['eos']
        p[q['cond'] + '_code'] = r['parse_code']
    for p in pt.values():
        p['P'] = R.agg_P(p['P1'], p['P2'])
    return pt


def conf(pt, cond):
    out = {}
    for lab in ['positive', 'negative']:
        c = {s: 0 for s in ['PRESENT', 'ABSENT', 'UNCERTAIN', 'INVALID']}
        for p in pt.values():
            if p['label'] == lab:
                c[p[cond]] += 1
        out[lab] = c
    return out


def vec(pt, cond):
    ids = sorted(pt)
    lab = np.array([pt[i]['label'] == 'positive' for i in ids])
    corr = np.array([(pt[i][cond] == 'PRESENT') if pt[i]['label'] == 'positive' else (pt[i][cond] == 'ABSENT') for i in ids])
    return ids, lab, corr


def ba(lab, corr):
    return 0.5 * (corr[lab].mean() + corr[~lab].mean())


def metrics(pt, cond):
    ids, lab, corr = vec(pt, cond)
    c = conf(pt, cond)
    n_pos, n_neg = int(lab.sum()), int((~lab).sum())
    sens, spec = c['positive']['PRESENT'] / n_pos, c['negative']['ABSENT'] / n_neg
    expl = sum(1 for p in pt.values() if p[cond] in ('PRESENT', 'ABSENT')) / len(pt)
    expl_acc = (c['positive']['PRESENT'] + c['negative']['ABSENT']) / max(1, sum(1 for p in pt.values() if p[cond] in ('PRESENT', 'ABSENT')))
    return dict(BA=0.5 * (sens + spec), sensitivity=sens, specificity=spec, explicit_coverage=expl, explicit_accuracy=expl_acc, confusion=c,
                n_uncertain=sum(1 for p in pt.values() if p[cond] == 'UNCERTAIN'), n_invalid=sum(1 for p in pt.values() if p[cond] == 'INVALID'))


def paired(pt, a, b, rng):
    ids, lab, ca = vec(pt, a)
    _, _, cb = vec(pt, b)
    pos, neg = np.where(lab)[0], np.where(~lab)[0]
    d = []
    for _ in range(NB):
        ip = rng.choice(pos, len(pos)); ineg = rng.choice(neg, len(neg))
        d.append(0.5 * ((ca[ip].mean() - cb[ip].mean()) + (ca[ineg].mean() - cb[ineg].mean())))
    d = np.array(d)
    pt_est = ba(lab, ca) - ba(lab, cb)
    to_a = int(((~cb) & ca).sum()); to_b = int((cb & (~ca)).sum())  # b에서 오답→a에서 정답 / b 정답→a 오답
    by_batch = {}
    for bt in sorted({pt[i]['batch'] for i in ids}):
        m = np.array([pt[i]['batch'] == bt for i in ids])
        if m.sum() and lab[m].any() and (~lab[m]).any():
            by_batch[bt] = dict(n=int(m.sum()), n_pos=int(lab[m].sum()), diff_BA=float(ba(lab[m], ca[m]) - ba(lab[m], cb[m])),
                                fixed=int(((~cb[m]) & ca[m]).sum()), broken=int((cb[m] & (~ca[m])).sum()))
        else:
            by_batch[bt] = dict(n=int(m.sum()), n_pos=int(lab[m].sum()), diff_BA=None,
                                fixed=int(((~cb[m]) & ca[m]).sum()), broken=int((cb[m] & (~ca[m])).sum()))
    return dict(diff=float(pt_est), ci95=[float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))], fixed_by_first=to_a, broken_by_first=to_b,
                sens_diff=float(ca[lab].mean() - cb[lab].mean()), spec_diff=float(ca[~lab].mean() - cb[~lab].mean()), by_batch=by_batch)


def decide(m, pw, wc):
    flags = {}
    flags['P_minus_W_positive'] = pw['diff'] >= 0.10 and pw['ci95'][0] > 0
    flags['W_minus_C_positive'] = wc['diff'] >= 0.10 and wc['ci95'][0] > 0
    flags['simple_alt_sufficient'] = any(m[c]['BA'] >= 0.80 and m[c]['sensitivity'] >= 0.75 and m[c]['specificity'] >= 0.75 for c in ['W', 'P'])
    flags['P_minus_W_weak_ci_upper_lt_10pp'] = pw['ci95'][1] < 0.10
    flags['all_BA_le_0.60'] = all(m[c]['BA'] <= 0.60 for c in ['C', 'W', 'P'])
    if flags['P_minus_W_positive']:
        v = 'positive_P_over_W'
    elif flags['simple_alt_sufficient']:
        v = 'simple_alternative_sufficient_candidate'
    elif flags['all_BA_le_0.60']:
        v = 'negative_low_frozen_performance_all_conditions'
    elif flags['P_minus_W_weak_ci_upper_lt_10pp']:
        v = 'negative_no_large_split_gain'
    else:
        v = 'inconclusive'
    return v, flags


def main(stage, out_path):
    reqs, recs = load_stage(stage)
    pt = patient_table(reqs, recs)
    rng = np.random.default_rng(SEED)
    m = {c: metrics(pt, c) for c in ['C', 'W', 'P']}
    pw = paired(pt, 'P', 'W', rng)
    wc = paired(pt, 'W', 'C', rng)
    pc = paired(pt, 'P', 'C', rng)
    v, flags = decide(m, pw, wc)
    n_pos = sum(1 for p in pt.values() if p['label'] == 'positive')
    nonEOS = sum(1 for r in recs.values() if not r['eos'])
    parse_codes = {}
    for r in recs.values():
        parse_codes[r['parse_code']] = parse_codes.get(r['parse_code'], 0) + 1
    out = dict(stage=stage, n_patients=len(pt), n_pos=n_pos, n_neg=len(pt) - n_pos, n_requests=len(recs), n_non_eos=nonEOS, parse_codes=parse_codes,
               metrics=m, P_minus_W=pw, W_minus_C=wc, P_minus_C=pc, verdict=v, flags=flags, bootstrap=dict(n=NB, seed=SEED, stratified_by_label=True),
               per_patient={str(k): v_ for k, v_ in pt.items()})
    json.dump(out, open(out_path, 'w'), indent=1, default=str)
    print(json.dumps({k: out[k] for k in ['n_patients', 'n_pos', 'n_neg', 'n_non_eos', 'parse_codes', 'verdict', 'flags']}, indent=1))
    for c in ['C', 'W', 'P']:
        print(c, {k: (round(x, 4) if isinstance(x, float) else x) for k, x in m[c].items()})
    for k, x in [('P-W', pw), ('W-C', wc), ('P-C', pc)]:
        print(k, round(x['diff'], 4), [round(y, 4) for y in x['ci95']], 'fixed', x['fixed_by_first'], 'broken', x['broken_by_first'])


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
