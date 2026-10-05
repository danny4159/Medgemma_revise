"""iter_078 평가. v8: V8 출력 점수·단순 대안 M 선택(V8에서만)·진행 판정. e24: 잠금 확인 후 E24 held 비교.

주지표: class-standardized MAE(sp75_metrics, invalid 오차 4, present-class 평균). 환자 단위 paired bootstrap 10,000회, seed 7501.
M 후보: Q, C argmax, C-kNN(k in 1,3,5 x lambda in 0,.25,.5,.75,1; posterior median), 결합(Q, C argmax, kNN3 median의 median; Q invalid면 C·kNN3 중 낮은 median).
M 선택 순서: V8 primary 최소 -> 일반 MAE 최소 -> VLM 호출 없는 후보 -> 작은 k -> 작은 lambda.
"""
import glob, hashlib, json, os, sys

import numpy as np

import rf78_gen as G
import rf78_ref as R
import rf78_vlm as RV
import sp75_data as D
import sp75_metrics as M

OUT = 'results/iter_078'
ADAPTER_DIGEST = '72417dc383a99d36b797f77d12d050124749abf370b220c70108cc51b88cfc2c'
Q_SRC = {'V8': 'results/iter_077/gen/V8/R_lr2e-4_ep16', 'E24': 'results/iter_077/gen/E24/R_adapted'}
KS = (1, 3, 5)
LAMS = (0.0, 0.25, 0.5, 0.75, 1.0)


def sha_file(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def read_dir(d):
    return [json.loads(l) for f in sorted(glob.glob(f'{d}/gen_worker*.jsonl')) for l in open(f) if l.strip()]


def median_of(dist):
    return int(np.argmax(np.cumsum(dist) >= 0.5 - 1e-12) + 1)


def load_all(split):
    reqs = json.load(open(f'{OUT}/data/refs_{split}.json'))['requests']
    lab = json.load(open(f'{OUT}/data/labels_{split}.json'))['labels']
    ft = json.load(open(R.FEAT))['items']
    man = {r['id']: r for r in D.load_manifest()['rows']}
    rows = [{'id': r['id'], 'patient': r['patient'], 'ordinal': r['ordinal'], 'grade': lab[r['id']]['grade']} for r in reqs]
    return reqs, lab, ft, man, rows


def knn_dist(qfeat, bank, k):
    sims = [(float(np.dot(qfeat, b['feat'])), b) for b in bank]
    order = sorted(sims, key=lambda t: (-round(t[0], 12), int(t[1]['patient']), t[1]['ordinal']))
    ch, seen = [], set()
    for s, b in order:
        if b['patient'] in seen:
            continue
        ch.append(b)
        seen.add(b['patient'])
        if len(ch) == k:
            break
    d = np.zeros(5)
    for b in ch:
        d[b['grade'] - 1] += 1.0 / k
    return d


def get_bank(ft):
    man = D.load_manifest()['rows']
    t24 = [r for r in man if r['split'] == 'T24' and r['position_set'] == 'supervised' and not r['excluded']]
    return [{'id': r['id'], 'patient': r['patient'], 'ordinal': r['ordinal'], 'grade': r['grade'], 'feat': np.array(ft[r['id']]['feat'])} for r in t24]


def vlm_pred(recs, reqs, cond, split, label):
    by = {}
    for r in recs:
        assert r['id'] not in by, f'dup {r["id"]} {label}'
        by[r['id']] = r
    want = [q['id'] for q in reqs]
    assert set(by) == set(want), f'{label}: id set mismatch {len(by)} vs {len(want)}'
    for q in reqs:
        r = by[q['id']]
        assert r['adapter_digest'] == ADAPTER_DIGEST, label
        if cond != 'Q':
            assert r['cond'] == cond and r['split'] == split and r['fields'] == RV.request_fields(q, cond), f'{label} provenance {q["id"]}'
        assert r['ended_eos'] is True or r['ended_eos'] is False
    return [by[i]['parsed'] if by[i]['parse_valid'] else None for i in want], by


def candidates(reqs, ft, bank, q_pred):
    n = len(reqs)
    C_probs = [np.array(ft[q['id']]['probs']) for q in reqs]
    c_arg = [ft[q['id']]['pred'] for q in reqs]
    out = {'Q': (list(q_pred), False, 0, 0.0), 'C_argmax': (c_arg, False, 0, 0.0)}
    kd = {k: [knn_dist(np.array(ft[q['id']]['feat']), bank, k) for q in reqs] for k in KS}
    for k in KS:
        for lam in LAMS:
            if lam == 0.0 and k != KS[0]:
                continue   # lambda=0은 k와 무관 (C posterior median)
            out[f'CkNN_k{k}_lam{lam:g}'] = ([median_of((1 - lam) * C_probs[i] + lam * kd[k][i]) for i in range(n)], False, k, lam)
    knn3 = [median_of(kd[3][i]) for i in range(n)]
    cm = [median_of(C_probs[i]) for i in range(n)]
    comb = []
    for i in range(n):
        if q_pred[i] is None:
            comb.append(min(cm[i], knn3[i]))
        else:
            comb.append(int(np.median([q_pred[i], c_arg[i], knn3[i]])))
    out['Combo_Q_Carg_kNN3'] = (comb, True, 3, 0.0)
    return out, kd


def score_row(true, pred):
    s = M.summary(true, pred)
    return {k: s[k] for k in ('n', 'class_std_mae', 'n_classes_present', 'mae', 'err_ge2_rate', 'invalid_rate', 'macro_f1_present', 'per_class_mae')}


def q_preds(split, reqs, man):
    recs = [r for r in read_dir(Q_SRC[split]) if r['id'] in {q['id'] for q in reqs}]
    preds, by = vlm_pred(recs, reqs, 'Q', split, 'Q')
    for q in reqs:
        r = by[q['id']]
        want = [e['pixel_sha256_padded'] for e in man[q['id']]['inputs']['R']]
        assert r.get('input_pixel_sha256') == want and r['variant'] == 'R', f'Q input mismatch {q["id"]}'
    return preds, by


def load_systems(split, gen_roots):
    reqs, lab, ft, man, rows = load_all(split)
    true = [r['grade'] for r in rows]
    qp, qby = q_preds(split, reqs, man)
    sysd = {'Q': qp}
    byc = {}
    for cond in 'LID':
        recs = read_dir(f'{gen_roots}/{cond}')
        sysd[cond], byc[cond] = vlm_pred(recs, reqs, cond, split, cond)
    return reqs, lab, ft, man, rows, true, sysd, qby, byc


def v8(a):
    reqs, lab, ft, man, rows, true, sysd, qby, byc = load_systems('V8', f'{OUT}/gen/V8_main')
    bank = get_bank(ft)
    cands, kd = candidates(reqs, ft, bank, sysd['Q'])
    table = {}
    for name, (pred, uses_vlm, k, lam) in cands.items():
        s = score_row(true, pred)
        table[name] = {'uses_vlm': uses_vlm, 'k': k, 'lam': lam, **s}
    vlm = {c: score_row(true, sysd[c]) for c in 'QLID'}
    # M 선택: Q 포함 모든 후보 중 V8 primary 최소 ...
    order = sorted(table, key=lambda n: (round(table[n]['class_std_mae'], 12), round(table[n]['mae'], 12), table[n]['uses_vlm'] or n == 'Q', table[n]['k'], table[n]['lam'], n))
    M_name = order[0]
    n_valid = {c: int(sum(p is not None for p in sysd[c])) for c in 'QLID'}
    proceed = not (n_valid['I'] < 12 and n_valid['D'] < 12)
    ref_match = {c: float(np.mean([sum(x['grade'] == lab[q['id']]['grade'] for x in q['I' if c in 'LI' else 'D']) / 3 for q in reqs])) for c in 'LID'}
    res = {'split': 'V8', 'n': len(rows), 'vlm_systems': vlm, 'n_valid_outputs': n_valid, 'candidates': table, 'selection_order': order[:6], 'M': M_name, 'M_pred': cands[M_name][0],
           'M_uses_vlm_Q': M_name in ('Q', 'Combo_Q_Carg_kNN3'), 'proceed_to_E24': proceed,
           'proceed_rule': 'hold E24 only if both I and D have <12 valid outputs among 24',
           'posthoc_ref_grade_match_rate': ref_match,
           'pred': {c: sysd[c] for c in 'QLID'},
           'v8_boot_vs_Q': {c: M.boot_diff(rows, sysd[c], sysd['Q']) for c in 'LID'},
           'sources': {'refs': sha_file(f'{OUT}/data/refs_V8.json'), 'labels': sha_file(f'{OUT}/data/labels_V8.json'), 'features': sha_file(R.FEAT),
                       'Q_src_sha256': {os.path.basename(f): sha_file(f) for f in glob.glob(f'{Q_SRC["V8"]}/gen_worker*.jsonl')}}}
    json.dump(res, open(f'{OUT}/eval/report_V8.json', 'w'), indent=1)
    sel = {'M': M_name, 'k': cands[M_name][2], 'lam': cands[M_name][3], 'selected_on': 'V8 only (24 rows)', 'v8_primary': table[M_name]['class_std_mae'], 'v8_report_sha256': sha_file(f'{OUT}/eval/report_V8.json')}
    json.dump(sel, open(f'{OUT}/eval/select_M.json', 'w'), indent=1)
    print(json.dumps({'vlm_primary': {c: round(vlm[c]['class_std_mae'], 4) for c in 'QLID'}, 'valid': n_valid, 'M': M_name, 'M_v8': table[M_name]['class_std_mae'], 'proceed': proceed}))
    for n in order[:8]:
        print(n, round(table[n]['class_std_mae'], 4), round(table[n]['mae'], 4))


def e24(a):
    sel = json.load(open(f'{OUT}/eval/select_M.json'))
    lock = json.load(open(a.lock))
    for f, h in lock['files'].items():
        if sha_file(f) != h:
            sys.exit(f'locked file changed {f}')
    assert lock['select_M_sha256'] == sha_file(f'{OUT}/eval/select_M.json')
    reqs, lab, ft, man, rows, true, sysd, qby, byc = load_systems('E24', f'{OUT}/gen/E24_main')
    bank = get_bank(ft)
    cands, kd = candidates(reqs, ft, bank, sysd['Q'])
    Mp = cands[sel['M']][0]
    table = {name: {'uses_vlm': v[1], 'k': v[2], 'lam': v[3], **score_row(true, v[0])} for name, v in cands.items()}
    sysd['M'] = Mp
    sys_scores = {c: score_row(true, sysd[c]) for c in ('Q', 'L', 'I', 'D', 'M')}
    comps = {}
    for a_, b_ in (('I', 'L'), ('I', 'D'), ('I', 'M'), ('I', 'Q'), ('L', 'Q'), ('D', 'Q'), ('M', 'Q'), ('D', 'L')):
        comps[f'{a_}-{b_}'] = M.boot_diff(rows, sysd[a_], sysd[b_])
    comps['I-C_argmax'] = M.boot_diff(rows, sysd['I'], cands['C_argmax'][0])
    n = len(rows)
    t = np.array(true)
    def eabs(p):
        return M.abs_err(true, p)
    rec_loss = {}
    for c in ('L', 'I', 'D', 'M'):
        eq, ec = eabs(sysd['Q']), eabs(sysd[c])
        rec_loss[c] = {'recovered_vs_Q': int((ec < eq).sum()), 'lost_vs_Q': int((ec > eq).sum()), 'unchanged': int((ec == eq).sum()),
                       'abs_err_change_mean': float((ec - eq).mean())}
    # 설명용(사후): 참고 grade가 대상 grade와 일치하는 정도
    post = {}
    for c, key in (('I', 'I'), ('D', 'D'), ('L', 'I')):
        mr = np.array([sum(x['grade'] == lab[q['id']]['grade'] for x in q[key]) / 3 for q in reqs])
        e = eabs(sysd[c])
        post[c] = {'mean_ref_grade_match': float(mr.mean()), 'mae_when_all3_match': float(e[mr == 1].mean()) if (mr == 1).any() else None, 'n_all3_match': int((mr == 1).sum()),
                   'mae_when_none_match': float(e[mr == 0].mean()) if (mr == 0).any() else None, 'n_none_match': int((mr == 0).sum())}
    cd = {k: v['point'] for k, v in comps.items()}
    crit = {'I_minus_M_le_-0.15': cd['I-M'] <= -0.15, 'I_minus_L_le_-0.10': cd['I-L'] <= -0.10, 'I_minus_D_le_-0.10': cd['I-D'] <= -0.10,
            'err_ge2_I_minus_M_le_0.05': sys_scores['I']['err_ge2_rate'] - sys_scores['M']['err_ge2_rate'] <= 0.05}
    crit['accuracy_candidate'] = all(crit.values())
    res = {'split': 'E24_held', 'n': n, 'n_patients': len({r['patient'] for r in rows}), 'M': sel, 'systems': sys_scores, 'candidates_all': table, 'paired': comps, 'recovery_loss_vs_Q': rec_loss,
           'posthoc_ref_grade_match': post, 'criteria': crit, 'n_valid': {c: int(sum(p is not None for p in sysd[c])) for c in ('Q', 'L', 'I', 'D')},
           'pred': {c: sysd[c] for c in ('Q', 'L', 'I', 'D', 'M')}, 'ids': [r['id'] for r in rows],
           'boot': {'n': M.BOOT_N, 'seed': M.BOOT_SEED, 'invalid_err': M.INVALID_ERR}, 'lock_sha256': sha_file(a.lock)}
    json.dump(res, open(f'{OUT}/eval/report_E24.json', 'w'), indent=1)
    print(json.dumps({'sys': {c: round(v['class_std_mae'], 4) for c, v in sys_scores.items()}, 'paired': {k: [round(v['point'], 4), [round(x, 4) for x in v['ci95']]] for k, v in comps.items()}, 'crit': crit}))


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['v8', 'e24'])
    ap.add_argument('--lock', default=None)
    a = ap.parse_args()
    os.makedirs(f'{OUT}/eval', exist_ok=True)
    (v8 if a.mode == 'v8' else e24)(a)
