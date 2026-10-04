"""iter_065 평가: 질문(W/E)×입력(F/T/J) 응답을 구간 단위 BA로 계산하고 질문별 고정 정책(F/F,F/T,T/F,T/T,J/J)·HD-GLIO를 비교.

진입 조건(변경 거부): verify.json이 clean이고 기록 파일 hash가 그대로이며, 현재 requests/labels/target-manifest/model 파일로 계산한
protocol digest가 verify.json·protocol과 같아야 한다 (m65_run.check_protocol, 부분 변조/교체 거부).
정책 선택(D에서만): B=argmax macro BA{F/F,T/T}, Q=argmax macro BA{F/T,T/F}; 동률은 D 전체 비용(read->saved 합) 낮은 쪽, 그다음 사전식(F/F<T/T, F/T<T/F).
bootstrap: case 단위 10,000회, seed65. 재표집에서 어느 질문이든 한 class가 사라진 replicate는 제외(유효 replicate 수 보고).
"""
import argparse, glob, json, os, sys
import numpy as np
import msd56_run as M
import m65_run as R

SEED, NB = 65, 10000
QS = ('W', 'E')
POLS = {'F/F': ('F', 'F'), 'F/T': ('F', 'T'), 'T/F': ('T', 'F'), 'T/T': ('T', 'T'), 'J/J': ('J', 'J')}
B_SET, Q_SET = ['F/F', 'T/T'], ['F/T', 'T/F']


DRIFT_OK = {'m65_run.py'}  # D·E12 생성 후 m65_run.py의 cmd_tech만 수정(E36에서 byte 동일 png 공유 허용). 생성 경로(worker/launch/verify) 불변.


def check_protocol_run_py_drift(model, requests, labels, manifest, protocol):
    """생성 시점 protocol과 현재 입력을 비교하되 code['m65_run.py'] hash 차이만 허용(기록). 그 외 모든 구성요소·모델 파일 hash는 엄격히 일치해야 한다."""
    p = json.load(open(protocol))
    comp, mf = R.components(model, requests, labels, manifest, full_model_hash=True)
    diff = [k for k in comp if comp[k] != p['components'].get(k)]
    code_diff = [f for f in comp['code'] if comp['code'][f] != p['components']['code'].get(f)]
    assert diff in ([], ['code']) and set(code_diff) <= DRIFT_OK, ('protocol mismatch', diff, code_diff)
    assert mf == {k: {**v, 'mtime_ns': mf[k]['mtime_ns']} for k, v in p['model_files'].items()} or all(
        mf[k]['sha256'] == v['sha256'] and mf[k]['size'] == v['size'] for k, v in p['model_files'].items()), 'model files changed'
    assert R.digest(p['components'], p['model_files']) == p['digest'], 'stored protocol tampered'
    return p['digest'], code_diff


def load(a, allow_drift=False):
    v = json.load(open(a.verify))
    assert v['n_problems'] == 0 and v['n_records'] == v['n_requests'], 'verify not clean'
    for f, h in v['record_file_sha256'].items():
        assert R.sha_file(f) == h, 'record file changed after verify ' + f
    if allow_drift:
        cur, _ = check_protocol_run_py_drift(a.model, a.requests, a.labels, a.target_manifest, a.protocol)
    else:
        cur = R.check_protocol(a.model, a.requests, a.labels, a.target_manifest, a.protocol, full=True)
    assert cur == v['protocol_digest'] == json.load(open(a.protocol))['digest'], 'protocol/verify digest mismatch'
    lab = json.load(open(a.labels))
    reqs = {r['rid']: r for r in R.read_jsonl(a.requests)}
    recs, cost = {}, {}
    for f in sorted(glob.glob(f'{a.gen_dir}/worker*.jsonl')):
        for r in R.read_jsonl(f):
            assert r['rid'] not in recs, 'dup'
            recs[r['rid']] = r
    for f in sorted(glob.glob(f'{a.gen_dir}/worker*.cost')):
        for r in R.read_jsonl(f):
            cost[r['rid']] = r
    assert set(recs) == set(reqs) == set(lab)
    return lab, reqs, recs, cost, v


def table(lab, recs):
    T = {}
    for rid, r in recs.items():
        l = lab[rid]
        txt = r['attempts'][-1]['text']
        pa = M.parse_answer(txt)
        pred = None if pa is None else (1 if pa == 'PRESENT' else 0)
        gt = 1 if l['answer'] == 'PRESENT' else 0
        T[rid] = {'case': l['case'], 'slab': l['slab'], 'q': l['q'], 'cond': l['cond'], 'pred': pred, 'gt': gt, 'correct': int(pred == gt),
                  'cov': bool(l['coverage']), 'eos': bool(r['attempts'][-1]['ended_eos']), 'retried': len(r['attempts']) > 1}
    return T


def counts(T, cases):
    """cases 순서 기준 배열 cnt[q][cond] -> (n_cases,4): tp,fn,tn,fp (invalid는 오답: gt1->fn, gt0->fp)."""
    idx = {c: i for i, c in enumerate(cases)}
    out = {q: {c: np.zeros((len(cases), 4)) for c in 'FTJ'} for q in QS}
    for t in T.values():
        a = out[t['q']][t['cond']][idx[t['case']]]
        if t['gt'] == 1:
            a[0 if t['pred'] == 1 else 1] += 1
        else:
            a[2 if t['pred'] == 0 else 3] += 1
    return out


def ba_from(cnt):
    """cnt (...,4) 합산 -> BA 또는 nan"""
    tp, fn, tn, fp = cnt[..., 0], cnt[..., 1], cnt[..., 2], cnt[..., 3]
    with np.errstate(divide='ignore', invalid='ignore'):
        return 0.5 * (tp / (tp + fn) + tn / (tn + fp))


def policy_macro(cnts, pol, sel):
    """cnts: q->cond->(n,4); sel: case index array (resample) 또는 None. returns (macro, W_ba, E_ba)"""
    bas = []
    for q, c in zip(QS, POLS[pol] if isinstance(pol, str) else pol):
        x = cnts[q][c]
        bas.append(ba_from(x.sum(0) if sel is None else x[sel].sum(1)))
    return 0.5 * (bas[0] + bas[1]), bas[0], bas[1]


def cost_by_cond(T, cost, recs):
    out = {}
    for rid, t in T.items():
        out.setdefault((t['q'], t['cond']), []).append(cost[rid]['read_to_saved_s'])
    return {f'{q}_{c}': float(sum(v)) for (q, c), v in out.items()}


def hd_answers(dirs):
    ans = {}
    for d in dirs:
        for f in glob.glob(f'{d}/hd_*.json'):
            r = json.load(open(f))
            assert r['case'] not in ans
            ans[r['case']] = r['answers']
    return ans


def hd_counts(hd, lab_by_case, cases):
    """HD W/E 응답 -> cnt[q] (n,4). 정답은 labels(질문별 F 조건)에서 가져온다."""
    idx = {c: i for i, c in enumerate(cases)}
    out = {q: np.zeros((len(cases), 4)) for q in QS}
    for (case, slab, q), gt in lab_by_case.items():
        pred = 1 if hd[case][slab][q] == 'PRESENT' else 0
        a = out[q][idx[case]]
        if gt == 1:
            a[0 if pred == 1 else 1] += 1
        else:
            a[2 if pred == 0 else 3] += 1
    return out


def boot(cnts, diffs, n_cases):
    rng = np.random.default_rng(SEED)
    sel = rng.integers(0, n_cases, size=(NB, n_cases))
    res = {}
    for name, (f1, f2) in diffs.items():
        a, b = f1(sel), f2(sel)
        d = a - b
        ok = ~np.isnan(d)
        res[name] = {'n_valid_replicates': int(ok.sum()),
                     'ci95': [float(np.percentile(d[ok], 2.5)), float(np.percentile(d[ok], 97.5))] if ok.sum() else None}
    return res


def main():
    ap = argparse.ArgumentParser()
    for k in ('requests', 'labels', 'target-manifest', 'gen-dir', 'verify', 'model', 'protocol', 'out'):
        ap.add_argument('--' + k, required=True)
    ap.add_argument('--hd-dirs', nargs='*', default=[])
    ap.add_argument('--select-from', default=None, help='D report.json: 여기서 고정한 B/Q 정책을 사용')
    ap.add_argument('--pool', nargs='*', default=[], help='추가 split 묶음 "requests,labels,manifest,gen_dir,verify,protocol" (각각 독립 검증 후 합침; E12+E36=E48)')
    ap.add_argument('--allow-run-py-drift', action='store_true', help='D/E12 protocol: m65_run.py hash 차이만 허용(기록)')
    a = ap.parse_args()
    assert not os.path.exists(a.out), 'report exists'
    lab, reqs, recs, cost, v = load(a, allow_drift=a.allow_run_py_drift)
    pooled = [{'requests': a.requests, 'verify': a.verify, 'protocol_digest': v['protocol_digest']}]
    for spec in a.pool:
        r_, l_, m_, g_, vf_, p_ = spec.split(',')
        b = argparse.Namespace(requests=r_, labels=l_, target_manifest=m_, gen_dir=g_, verify=vf_, protocol=p_, model=a.model)
        l2, q2, c2, k2, v2 = load(b, allow_drift=False)
        assert not (set(l2) & set(lab)), 'overlapping request ids between pooled splits'
        lab.update(l2); reqs.update(q2); recs.update(c2); cost.update(k2)
        pooled.append({'requests': r_, 'verify': vf_, 'protocol_digest': v2['protocol_digest']})
    T = table(lab, recs)
    cases = sorted({t['case'] for t in T.values()})
    cn = counts(T, cases)
    n = len(cases)
    cc = cost_by_cond(T, cost, recs)
    rep = {'model': a.model, 'requests_sha256': R.sha_file(a.requests), 'labels_sha256': R.sha_file(a.labels),
           'verify_sha256': R.sha_file(a.verify), 'protocol_digest': v['protocol_digest'], 'pooled_splits': pooled, 'seed': SEED, 'n_boot': NB, 'n_cases': n,
           'n_slabs': n * 6, 'cost_sum_read_to_saved_s_by_q_cond': cc}
    # 질문×입력 단독 지표
    per = {}
    for q in QS:
        for c in 'FTJ':
            x = cn[q][c].sum(0)
            per[f'{q}_{c}'] = {'BA': float(ba_from(x)), 'sens': float(x[0] / (x[0] + x[1])), 'spec': float(x[2] / (x[2] + x[3])),
                               'tp_fn_tn_fp': x.tolist()}
    rep['per_question_cond'] = per
    pol = {}
    for p in POLS:
        m, w, e = policy_macro(cn, p, None)
        pol[p] = {'macro_BA': float(m), 'W_BA': float(w), 'E_BA': float(e), 'cost_s': cc[f'W_{POLS[p][0]}'] + cc[f'E_{POLS[p][1]}']}
    rep['policies'] = pol
    # 선택
    if a.select_from:
        sel = json.load(open(a.select_from))['selection']
        rep['selection_source'] = a.select_from
    else:
        def pick(S):
            return sorted(S, key=lambda p: (-round(pol[p]['macro_BA'], 12), pol[p]['cost_s'], S.index(p)))[0]
        sel = {'B': pick(B_SET), 'Q': pick(Q_SET)}
        rep['selection_rule'] = 'argmax macro BA; tie -> lower D cost; tie -> lexicographic order'
    rep['selection'] = sel
    best_here = max(POLS, key=lambda p: (round(pol[p]['macro_BA'], 12), -pol[p]['cost_s']))
    rep['optimistic_best_policy_this_split'] = best_here
    # bootstrap 비교
    def pf(p):
        return lambda s, p=p: policy_macro(cn, p, s)[0]

    def pq(p, qi):
        return lambda s, p=p, qi=qi: policy_macro(cn, p, s)[1 + qi]
    diffs = {}
    Bp, Qp = sel['B'], sel['Q']
    diffs['Q-B_macro'] = (pf(Qp), pf(Bp))
    diffs['Q-J_macro'] = (pf(Qp), pf('J/J'))
    diffs['B-J_macro'] = (pf(Bp), pf('J/J'))
    diffs['F/T-B_macro'] = (pf('F/T'), pf(Bp))
    diffs['F/T-J_macro'] = (pf('F/T'), pf('J/J'))
    for qi, q in enumerate(QS):
        diffs[f'Q-B_{q}'] = (pq(Qp, qi), pq(Bp, qi))
        diffs[f'Q-J_{q}'] = (pq(Qp, qi), pq('J/J', qi))
        diffs[f'F-T_{q}'] = (pq('F/F', qi), pq('T/T', qi))
        diffs[f'J-F_{q}'] = (pq('J/J', qi), pq('F/F', qi))
        diffs[f'J-T_{q}'] = (pq('J/J', qi), pq('T/T', qi))
    cis = boot(cn, diffs, n)
    # 점추정: sel=None 경로
    def pt(p, qi=None):
        m = policy_macro(cn, p, None)
        return m[0] if qi is None else m[1 + qi]
    pts = {'Q-B_macro': pt(Qp) - pt(Bp), 'Q-J_macro': pt(Qp) - pt('J/J'), 'B-J_macro': pt(Bp) - pt('J/J'),
           'F/T-B_macro': pt('F/T') - pt(Bp), 'F/T-J_macro': pt('F/T') - pt('J/J')}
    for qi, q in enumerate(QS):
        pts[f'Q-B_{q}'] = pt(Qp, qi) - pt(Bp, qi); pts[f'Q-J_{q}'] = pt(Qp, qi) - pt('J/J', qi)
        pts[f'F-T_{q}'] = pt('F/F', qi) - pt('T/T', qi); pts[f'J-F_{q}'] = pt('J/J', qi) - pt('F/F', qi); pts[f'J-T_{q}'] = pt('J/J', qi) - pt('T/T', qi)
    rep['diffs'] = {k: {'point': float(pts[k]), **cis[k]} for k in diffs}
    # 비용비 Q/J (read->saved 합 기준, loading 제외)
    rep['cost_ratio_Q_over_J'] = pol[Qp]['cost_s'] / pol['J/J']['cost_s']
    # 형식·cap
    fmt = {}
    for c in 'FTJ':
        rows = [t for t in T.values() if t['cond'] == c]
        fmt[c] = {'n': len(rows), 'invalid': sum(t['pred'] is None for t in rows), 'non_eos_final': sum(not t['eos'] for t in rows),
                  'retried_2048': sum(t['retried'] for t in rows)}
    rep['format'] = fmt
    # coverage: 양성 FN 분리
    cov = {}
    for q in QS:
        for c in 'FTJ':
            rows = [t for t in T.values() if t['q'] == q and t['cond'] == c and t['gt'] == 1]
            cov[f'{q}_{c}'] = {'pos': len(rows), 'cov0_pos': sum(not t['cov'] for t in rows), 'FN_cov0': sum((not t['cov']) and t['pred'] != 1 for t in rows),
                               'FN_cov1': sum(t['cov'] and t['pred'] != 1 for t in rows),
                               'sens_cov1': (float(np.mean([t['pred'] == 1 for t in rows if t['cov']])) if any(t['cov'] for t in rows) else None)}
    rep['coverage_split'] = cov
    # W/E 정답이 다른 구간에서 두 답변 동시 정확
    joint = {}
    for p, (cw, ce) in POLS.items():
        ok = tot = 0
        for (case, slab) in {(t['case'], t['slab']) for t in T.values()}:
            w = T[f'{case}__s{slab}__W__{cw}']; e = T[f'{case}__s{slab}__E__{ce}']
            if w['gt'] != e['gt']:
                tot += 1; ok += w['correct'] and e['correct']
        joint[p] = {'n_discordant_gt_slabs': tot, 'both_correct': ok}
    rep['joint_when_gt_differs'] = joint
    # case oracle (낙관적 참고; selector 비용 미포함)
    orc = []
    for case in cases:
        i = cases.index(case)
        best = max(((policy_macro({q: {c: cn[q][c][[i]] for c in 'FTJ'} for q in QS}, pl, None)[0]) for pl in ('F/F', 'T/T')))
        orc.append(best)
    rep['oracle_case_F_or_T_mean_macro_BA_caseavg'] = float(np.nanmean(orc))
    # HD
    if a.hd_dirs:
        hd = hd_answers(a.hd_dirs)
        assert set(hd) == set(cases), 'HD cases mismatch'
        lab_f = {(l['case'], l['slab'], l['q']): 1 if l['answer'] == 'PRESENT' else 0 for rid, l in lab.items() if l['cond'] == 'F'}
        hc = hd_counts(hd, lab_f, cases)
        hbas = {q: float(ba_from(hc[q].sum(0))) for q in QS}
        rep['HD'] = {'W_BA': hbas['W'], 'E_BA': hbas['E'], 'macro_BA': 0.5 * (hbas['W'] + hbas['E']),
                     'tp_fn_tn_fp': {q: hc[q].sum(0).tolist() for q in QS},
                     'note': 'HD label2=contrast-enhancing(D에서 MSD label3와 Dice로 확인, hd_label_semantics_D.json); W=HD 비배경(ontology 차이 가능)'}
        rng = np.random.default_rng(SEED)
        sel_i = rng.integers(0, n, size=(NB, n))
        def hdm(s):
            return 0.5 * sum(ba_from(hc[q][s].sum(1)) for q in QS)
        hcis = {}
        for nm, f in (('Q-HD_macro', lambda s: policy_macro(cn, Qp, s)[0] - hdm(s)), ('J-HD_macro', lambda s: policy_macro(cn, 'J/J', s)[0] - hdm(s)),
                      ('Q-HD_W', lambda s: policy_macro(cn, Qp, s)[1] - ba_from(hc['W'][s].sum(1))),
                      ('Q-HD_E', lambda s: policy_macro(cn, Qp, s)[2] - ba_from(hc['E'][s].sum(1)))):
            d = f(sel_i); ok = ~np.isnan(d)
            hcis[nm] = {'n_valid_replicates': int(ok.sum()), 'ci95': [float(np.percentile(d[ok], 2.5)), float(np.percentile(d[ok], 97.5))] if ok.sum() else None}
        q_m = policy_macro(cn, Qp, None)
        hcis['Q-HD_macro']['point'] = float(q_m[0] - rep['HD']['macro_BA']); hcis['J-HD_macro']['point'] = float(pol['J/J']['macro_BA'] - rep['HD']['macro_BA'])
        hcis['Q-HD_W']['point'] = float(q_m[1] - hbas['W']); hcis['Q-HD_E']['point'] = float(q_m[2] - hbas['E'])
        rep['diffs_vs_HD'] = hcis
    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    json.dump(rep, open(a.out, 'w'), indent=1)
    print(a.model, 'selection', sel, {p: round(pol[p]['macro_BA'], 4) for p in pol})


if __name__ == '__main__':
    main()
