"""iter_064 평가: 모델별 S/R/C BA, sens/spec, invalid·비EOS, L_count/L_content/L_total(case paired bootstrap seed64, 10,000).
진입 전 s64_run verify 통과(verify.json의 protocol digest·파일 hash 일치)를 요구한다. invalid는 오답으로 계산(주분석), valid-only는 보조.
사용: python s64_eval.py --requests R --labels L --target-manifest M --gen-dir D --verify D/verify.json --model m --out report.json"""
import argparse, glob, hashlib, json, os, sys
import numpy as np
import msd56_run as M
import s64_run as R

SEED, NB = 64, 10000


def ba(y, p):
    """y,p in {0,1} 배열(1=PRESENT). balanced accuracy."""
    y, p = np.asarray(y), np.asarray(p)
    return 0.5 * ((p[y == 1] == 1).mean() + (p[y == 0] == 0).mean())


def load(a):
    v = json.load(open(a.verify))
    assert v['n_problems'] == 0 and v['n_records'] == v['n_requests'], 'verify not clean'
    for f, h in v['record_file_sha256'].items():
        assert R.sha_file(f) == h, 'record file changed after verify ' + f
    lab = json.load(open(a.labels))
    reqs = {r['rid']: r for r in R.read_jsonl(a.requests)}
    recs = {}
    for f in sorted(glob.glob(f'{a.gen_dir}/worker*.jsonl')):
        for r in R.read_jsonl(f):
            assert r['rid'] not in recs, 'dup'
            recs[r['rid']] = r
    assert set(recs) == set(reqs) == set(lab)
    return lab, reqs, recs, v


def table(lab, recs):
    """case -> cond -> target -> dict(pred in {1,0,None}, correct, eos, text)"""
    T = {}
    for rid, r in recs.items():
        l = lab[rid]
        txt = r['attempts'][-1]['text']
        pa = M.parse_answer(txt)
        pred = None if pa is None else (1 if pa == 'PRESENT' else 0)
        gt = 1 if l['answer'] == 'PRESENT' else 0
        T.setdefault(l['case'], {}).setdefault(l['cond'], {})[l['target']] = {
            'pred': pred, 'gt': gt, 'correct': int(pred == gt), 'eos': bool(r['attempts'][-1]['ended_eos']), 'text': txt, 'retried': len(r['attempts']) > 1}
    return T


GROUPS = {'S': ['S'], 'R': ['R1', 'R2'], 'C': ['C1', 'C2'], 'R1': ['R1'], 'R2': ['R2'], 'C1': ['C1'], 'C2': ['C2']}


def case_arrays(T, cases, valid_only=False):
    """returns dict group -> (sens_c, spec_c) arrays per case (위치 평균). valid_only면 모든 비교 응답이 valid인 case만(호출자가 cases 제한)."""
    out = {}
    for g, cs in GROUPS.items():
        se = np.array([np.mean([T[c][k]['P']['correct'] for k in cs]) for c in cases])
        sp = np.array([np.mean([T[c][k]['N']['correct'] for k in cs]) for c in cases])
        out[g] = (se, sp)
    return out


def ba_arr(arr, idx=None):
    se, sp = arr
    if idx is not None:
        se, sp = se[idx], sp[idx]
    return 0.5 * (se.mean() + sp.mean())


def boot(arrs, pairs, n_cases):
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, n_cases, size=(NB, n_cases))
    res = {}
    for name, (g1, g2) in pairs.items():
        d = []
        for g in (g1, g2):
            se, sp = arrs[g]
            d.append(0.5 * (se[idx].mean(axis=1) + sp[idx].mean(axis=1)))
        diff = d[0] - d[1]
        res[name] = {'ci95': [float(np.percentile(diff, 2.5)), float(np.percentile(diff, 97.5))]}
    return res


PAIRS = {'L_count': ('S', 'R'), 'L_content': ('R', 'C'), 'L_total': ('S', 'C'), 'L_content_pos1': ('R1', 'C1'), 'L_content_pos2': ('R2', 'C2')}


def analyze(T, valid_only=False):
    cases = sorted(T)
    if valid_only:
        cases = [c for c in cases if all(T[c][k][t]['pred'] is not None for k in T[c] for t in T[c][k])]
    arrs = case_arrays(T, cases)
    out = {'n_cases': len(cases), 'groups': {}, 'diffs': {}}
    for g, a in arrs.items():
        out['groups'][g] = {'BA': float(ba_arr(a)), 'sens': float(a[0].mean()), 'spec': float(a[1].mean())}
    point = {k: out['groups'][g1]['BA'] - out['groups'][g2]['BA'] for k, (g1, g2) in PAIRS.items()}
    cis = boot(arrs, PAIRS, len(cases)) if len(cases) else {}
    for k in PAIRS:
        out['diffs'][k] = {'point': point[k], **cis.get(k, {})}
    # case 분포: R보다 C가 나쁜 case 수 (case BA 기준)
    ba_c = {g: 0.5 * (arrs[g][0] + arrs[g][1]) for g in arrs}
    out['cases_C_worse_than_R'] = int((ba_c['R'] - ba_c['C'] > 0).sum())
    out['cases_C_better_than_R'] = int((ba_c['R'] - ba_c['C'] < 0).sum())
    out['cases_R_worse_than_S'] = int((ba_c['S'] - ba_c['R'] > 0).sum())
    out['position_diff_both_positive'] = bool(point['L_content_pos1'] > 0 and point['L_content_pos2'] > 0)
    return out


def main():
    ap = argparse.ArgumentParser()
    for k in ('requests', 'labels', 'target-manifest', 'gen-dir', 'verify', 'model', 'out'):
        ap.add_argument('--' + k, required=True)
    a = ap.parse_args()
    a.target_manifest = getattr(a, 'target_manifest')
    assert not os.path.exists(a.out), 'report exists'
    lab, reqs, recs, v = load(a)
    T = table(lab, recs)
    rep = {'model': a.model, 'requests_sha256': R.sha_file(a.requests), 'labels_sha256': R.sha_file(a.labels), 'verify_sha256': R.sha_file(a.verify),
           'protocol_digest': v['protocol_digest'], 'seed': SEED, 'n_boot': NB}
    rep['primary_invalid_as_wrong'] = analyze(T)
    rep['conditional_all_valid_cases'] = analyze(T, valid_only=True)
    # 형식·cap
    fmt = {}
    for g in ('S', 'R1', 'R2', 'C1', 'C2'):
        rows = [T[c][g][t] for c in T for t in ('P', 'N')]
        fmt[g] = {'n': len(rows), 'invalid': sum(r['pred'] is None for r in rows), 'non_eos_final': sum(not r['eos'] for r in rows),
                  'retried_2048': sum(r['retried'] for r in rows),
                  'exact_PRESENT_ABSENT_uppercase': sum(r['text'].strip() in ('PRESENT', 'ABSENT') for r in rows)}
    rep['format'] = fmt
    # P/N·위치별 정답률, confusion
    byt = {}
    for g in ('S', 'R1', 'R2', 'C1', 'C2'):
        for t in ('P', 'N'):
            rows = [T[c][g][t] for c in T]
            byt[f'{g}_{t}'] = {'acc': float(np.mean([r['correct'] for r in rows])), 'pred_present': sum(r['pred'] == 1 for r in rows),
                               'pred_absent': sum(r['pred'] == 0 for r in rows), 'invalid': sum(r['pred'] is None for r in rows)}
    rep['by_target_cond'] = byt
    # S 정답 사례(target 단위)에서 C가 틀리는 비율 (보조, 사전 충분성 집단 아님)
    s_ok = [(c, t) for c in T for t in ('P', 'N') if T[c]['S'][t]['correct']]
    rep['aux_S_correct_then_C_wrong'] = {'n_S_correct_targets': len(s_ok),
        'C_wrong_frac_pos_avg': float(np.mean([1 - np.mean([T[c][k][t]['correct'] for k in ('C1', 'C2')]) for c, t in s_ok])) if s_ok else None,
        'R_wrong_frac_pos_avg': float(np.mean([1 - np.mean([T[c][k][t]['correct'] for k in ('R1', 'R2')]) for c, t in s_ok])) if s_ok else None}
    # routing 동일성: S 출력 공유 근거(요청 k번째 영상 == S 영상)
    rep['routing'] = {'rule': 'image index k in prompt -> that file only == S input', 'same_image_requests': sum(
        R.sha_file(r['images'][r['k'] - 1]) == R.sha_file(reqs[f"{r['case']}__{r['target']}__S"]['images'][0]) for r in reqs.values()),
        'n_requests': len(reqs), 'note': 'routed 입력은 S 입력과 동일 파일/처리 tensor(tech 검사); routed 성능=S 출력 공유로 정의, 별도 생성 없음'}
    # 비용(실측): 조건별 평균 입력 token·요청 처리 시간
    cost = {}
    for g in ('S', 'R1', 'R2', 'C1', 'C2'):
        rs = [recs[r] for r in recs if lab[r]['cond'] == g]
        cost[g] = {'mean_input_tokens': float(np.mean([r['n_input_tokens'] for r in rs])), 'mean_read_to_flush_s': float(np.mean([r['total_read_to_flush_s'] for r in rs])),
                   'mean_gen_s': float(np.mean([sum(x['runtime_s'] for x in r['attempts']) for r in rs]))}
    rep['cost_measured_per_request'] = cost
    json.dump(rep, open(a.out, 'w'), indent=1)
    p = rep['primary_invalid_as_wrong']
    print(a.model, {g: round(p['groups'][g]['BA'], 4) for g in ('S', 'R', 'C')}, {k: round(v['point'], 4) for k, v in p['diffs'].items() if k in ('L_count', 'L_content', 'L_total')})


if __name__ == '__main__':
    main()
