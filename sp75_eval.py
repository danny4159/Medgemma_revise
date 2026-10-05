"""iter_075/076 E24 개발 평가 (한 번; iter_076에서 결과 경로·잠금/봉인 흐름을 수정). F/R(미적응·적응), C, H, train-only prior, 예측 교환을 같은 행 집합에서 비교한다.

- 평가 행: E24 non-excluded (supervised ordinal 1·3·5, held ordinal 2·4). Primary = held(ordinal 2/4) class-standardized MAE.
- VLM 예측: 원시 출력 text를 고정 whole-string parser로 다시 해석(EOS 종료 + [1-5] 한 숫자). 비EOS/형식 오류는 invalid(오차 4). 보조: 후보 likelihood argmax.
- prior: T24 supervised train-only (global 및 ordinal; held ordinal 2/4는 이웃 ordinal 분포 동일 가중 평균). 선택 grade는 median(동률은 낮은 grade).
- 교환: 같은 ordinal 안에서 환자 ID hash 순 cyclic shift(+1).
- 환자 단위 paired bootstrap 10,000회 seed 7501 (같은 환자의 모든 위치 함께 재표집).
- LOCK(첫 E24 출력 전): 코드·선택 근거·checkpoint·manifest·환경 hash를 eval_lock.json에 기록(`lock`). 생성 출력은 lock에 넣지 않는다.
- SEAL(출력 완료 후): 모든 E24 출력의 완전성(요청 집합·중복·누락) 확인 후 출력 파일 hash를 eval_seal.json에 기록(`seal`).
- `run`은 lock·seal이 현재 파일과 일치할 때만 실행하고 결과를 새 파일에 원자적으로 쓴다(존재하면 중단).
"""
import argparse, glob, hashlib, json, os, sys

import numpy as np

import sp75_data as D
import sp75_metrics as M
import sp75_vlm as V

OUT = 'results/iter_077'
EVAL = f'{OUT}/eval'
CODE = ['sp75_eval.py', 'sp75_metrics.py', 'sp75_vlm.py', 'sp75_data.py', 'sp75_gen.py']
MARGIN = 0.20          # 최소 투자 폭 (MAE grade)
PASS_ABS = 1.0         # held class-standardized MAE 상한
H_TOL = 0.10           # H보다 이 이상 나쁘면 VLM 실용 우위 미확정
C_NOT_WORSE = 0.10     # C가 best VLM보다 이 이상 나쁘지 않아야 충분성 후보


def sha_file(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def files_of(dirpath):
    return sorted(glob.glob(os.path.join(dirpath, 'gen_worker*.jsonl')) + glob.glob(os.path.join(dirpath, 'gen_worker*.env.json')))


def load_vlm(dirpath, rows, variant, adapter_expected):
    recs = {}
    for f in sorted(glob.glob(os.path.join(dirpath, 'gen_worker*.jsonl'))):
        for ln in open(f):
            if ln.strip():
                r = json.loads(ln)
                if r['id'] in recs:
                    raise RuntimeError(f'duplicate {r["id"]} in {dirpath}')
                recs[r['id']] = r
    want = [r['id'] for r in rows]
    missing = [i for i in want if i not in recs]
    extra = [i for i in recs if i not in set(want)]
    if missing or extra:
        raise RuntimeError(f'{dirpath}: missing {missing[:3]} extra {extra[:3]}')
    pred, cand, eos = [], [], []
    for r in rows:
        x = recs[r['id']]
        if x['variant'] != variant or x['adapter_digest'] != adapter_expected:
            raise RuntimeError(f'{dirpath}: variant/adapter mismatch for {r["id"]}')
        if x['input_pixel_sha256'] != [e['pixel_sha256_padded'] for e in r['inputs'][variant]]:
            raise RuntimeError(f'{dirpath}: input hash mismatch {r["id"]}')
        ended = bool(x['ended_eos'])
        p = V.parse(x['text']) if ended else None
        pred.append(p)
        eos.append(ended)
        cand.append(int(np.argmax(x['cand_loglik'])) + 1)
    return pred, cand, eos


def load_json_pred(path, rows):
    d = json.load(open(path))
    ids = [p['id'] for p in d['preds']]
    if len(ids) != len(set(ids)):
        raise RuntimeError(f'{path}: duplicate prediction ids {sorted({i for i in ids if ids.count(i) > 1})[:3]}')
    want = [r['id'] for r in rows]
    if set(ids) != set(want):
        raise RuntimeError(f'{path}: missing {sorted(set(want) - set(ids))[:3]} extra {sorted(set(ids) - set(want))[:3]}')
    by = {p['id']: p for p in d['preds']}
    for r in rows:
        x = by[r['id']]
        if x['pred'] not in (1, 2, 3, 4, 5) or x['patient'] != r['patient'] or x['ordinal'] != r['ordinal'] or x['position_set'] != r['position_set']:
            raise RuntimeError(f'{path}: bad prediction row {r["id"]}')
    return [by[r['id']]['pred'] for r in rows], d


def report_systems(rows, systems):
    held = [i for i, r in enumerate(rows) if r['position_set'] == 'held']
    sup = [i for i, r in enumerate(rows) if r['position_set'] == 'supervised']
    out = {}
    g = [r['grade'] for r in rows]
    for name, pred in systems.items():
        sw = M.swap_predictions(rows, pred)
        out[name] = {}
        for pname, ix in (('held', held), ('supervised', sup), ('all', list(range(len(rows))))):
            tt = [g[i] for i in ix]
            out[name][pname] = M.summary(tt, [pred[i] for i in ix])
            # 교환은 ordinal 내부이므로 위치 집합별로 계산 (all은 두 집합 합산)
        sub = lambda ix, pr: ([rows[i] for i in ix], [pr[i] for i in ix])
        for pname, ix in (('held', held), ('supervised', sup)):
            rr, pp = sub(ix, pred)
            sw_ = M.swap_predictions(rr, pp)
            out[name][pname]['swap_class_std_mae'] = M.class_std_mae([r['grade'] for r in rr], sw_)[0]
    return out


def verify_lock_seal():
    lock = json.load(open(f'{EVAL}/eval_lock.json'))
    for f, h in lock['files'].items():
        if sha_file(f) != h:
            sys.exit(f'locked file changed: {f}')
    seal = json.load(open(f'{EVAL}/eval_seal.json'))
    if seal['lock_sha256'] != sha_file(f'{EVAL}/eval_lock.json'):
        sys.exit('seal does not match current lock')
    for f, h in seal['outputs'].items():
        if sha_file(f) != h:
            sys.exit(f'sealed E24 output changed: {f}')
    cur = {f for v in lock['vlm'].values() for f in files_of(v['dir'])}
    if cur != set(seal['outputs']) - set(lock['json_systems'].values()):
        sys.exit('E24 output file set differs from seal')
    return lock


def cmd_run(a):
    if os.path.exists(f'{EVAL}/report.json') or os.path.exists(f'{EVAL}/per_row.json'):
        sys.exit('report exists; refusing to overwrite')
    lock = verify_lock_seal()
    man = D.load_manifest()
    rows = sorted([r for r in man['rows'] if r['split'] == 'E24' and not r['excluded']], key=lambda r: (int(r['patient']), r['ordinal']))
    tr = sorted([r for r in man['rows'] if r['split'] == 'T24' and r['position_set'] == 'supervised' and not r['excluded']], key=lambda r: (int(r['patient']), r['ordinal']))
    systems, aux, meta = {}, {}, {}
    for name, spec in lock['vlm'].items():
        pred, cand, eos = load_vlm(spec['dir'], rows, spec['variant'], spec['adapter_digest'])
        systems[name] = pred
        aux[name + '_cand_argmax'] = cand
        meta[name] = {'n_invalid': sum(p is None for p in pred), 'n_not_eos': sum(not e for e in eos)}
    for name, path in lock['json_systems'].items():
        pred, d = load_json_pred(path, rows)
        systems[name] = pred
    gp, op, pri = M.prior_predictions(tr, rows)
    systems['prior_global'], systems['prior_ordinal'] = gp, op
    rep = {'n_rows': len(rows), 'n_held': sum(r['position_set'] == 'held' for r in rows), 'n_supervised': sum(r['position_set'] == 'supervised' for r in rows),
           'priors': pri, 'systems': report_systems(rows, systems), 'aux_candidate_argmax': {}, 'meta': meta}
    held_rows = [r for r in rows if r['position_set'] == 'held']
    sup_rows = [r for r in rows if r['position_set'] == 'supervised']
    hi = [i for i, r in enumerate(rows) if r['position_set'] == 'held']
    for name, c in aux.items():
        rep['aux_candidate_argmax'][name] = {p: M.summary([rows[i]['grade'] for i in ix], [c[i] for i in ix])['class_std_mae'] for p, ix in
                                            (('held', hi), ('supervised', [i for i in range(len(rows)) if i not in set(hi)]))}
    # paired bootstrap (held primary)
    sub = lambda pred, ix: [pred[i] for i in ix]
    swapped = {n: [None] * len(rows) for n in systems}
    for n in systems:
        # 위치 집합 안에서 교환
        for ix in (hi, [i for i in range(len(rows)) if i not in set(hi)]):
            rr = [rows[i] for i in ix]
            sw = M.swap_predictions(rr, [systems[n][i] for i in ix])
            for i, p in zip(ix, sw):
                swapped[n][i] = p
    comps = {}
    vl = [n for n in systems if n.startswith('F_') or n.startswith('R_')]
    sysh0 = {n: rep['systems'][n]['held']['class_std_mae'] for n in systems}
    best_vlm0 = min([v for v in ('F_adapted', 'R_adapted') if v in systems], key=lambda v: (sysh0[v], v))
    pairs = [(n, 'prior_ordinal') for n in vl] + [(n, 'prior_global') for n in vl] + [(n, 'C') for n in vl if n in ('F_adapted', 'R_adapted')] + \
            [(n, 'H') for n in vl if n in ('F_adapted', 'R_adapted')] + [('F_adapted', 'R_adapted'), ('F_adapted', 'F_base'), ('R_adapted', 'R_base'), ('C', 'H'), ('C', 'prior_ordinal'), ('H', 'prior_ordinal'), ('C', best_vlm0), (best_vlm0, 'H')]
    for x, y in pairs:
        if x in systems and y in systems:
            comps[f'{x}_minus_{y}'] = {p: M.boot_diff(rr, sub(systems[x], ix), sub(systems[y], ix)) for p, rr, ix in (('held', held_rows, hi), ('supervised', sup_rows, [i for i in range(len(rows)) if i not in set(hi)]))}
    for n in systems:
        comps[f'{n}_minus_swap'] = {p: M.boot_diff(rr, sub(systems[n], ix), sub(swapped[n], ix)) for p, rr, ix in (('held', held_rows, hi), ('supervised', sup_rows, [i for i in range(len(rows)) if i not in set(hi)]))}
    rep['paired_bootstrap_patient_resampling'] = comps
    sysh = {n: rep['systems'][n]['held']['class_std_mae'] for n in systems}
    flags = {}
    for v in ('F_adapted', 'R_adapted'):
        if v not in systems:
            continue
        c = comps
        flags[v] = {'held_primary': sysh[v], 'le_1.0': sysh[v] <= PASS_ABS,
                    'better_than_prior_ordinal_by_0.20': -c[f'{v}_minus_prior_ordinal']['held']['point'] >= MARGIN,
                    'better_than_swap_by_0.20': -c[f'{v}_minus_swap']['held']['point'] >= MARGIN,
                    'better_than_C_by_0.20': -c[f'{v}_minus_C']['held']['point'] >= MARGIN,
                    'H_better_than_vlm_by_more_than_0.10': (sysh[v] - sysh['H']) > H_TOL}
        flags[v]['all_candidate_conditions_point'] = all(flags[v][k] for k in ('le_1.0', 'better_than_prior_ordinal_by_0.20', 'better_than_swap_by_0.20', 'better_than_C_by_0.20'))
    best_vlm = best_vlm0
    flags['best_vlm'] = best_vlm
    ci = lambda key: comps[key]['held']['ci95']
    for v in ('F_adapted', 'R_adapted'):
        if v in flags:
            flags[v]['ci95_held_vs_prior_ordinal'] = ci(f'{v}_minus_prior_ordinal')
            flags[v]['ci95_held_vs_C'] = ci(f'{v}_minus_C')
            flags[v]['ci95_excludes_0_vs_prior_ordinal'] = ci(f'{v}_minus_prior_ordinal')[1] < 0
            flags[v]['ci95_excludes_0_vs_C'] = ci(f'{v}_minus_C')[1] < 0
    cb = ci(f'C_minus_{best_vlm}')
    flags['C_minus_best_vlm_ci95'] = cb
    flags['C_minus_best_vlm_ci_contains_both_plus_minus_0.20'] = bool(cb[0] < -MARGIN and cb[1] > MARGIN)
    flags['C_basic_signal'] = {'better_than_prior_by_0.20': -comps['C_minus_prior_ordinal']['held']['point'] >= MARGIN,
                               'better_than_swap_by_0.20': -comps['C_minus_swap']['held']['point'] >= MARGIN}
    flags['C_not_worse_than_best_vlm_by_0.10'] = (sysh['C'] - sysh[best_vlm]) < C_NOT_WORSE
    rep['predeclared_flags_point_estimates'] = flags
    per = [{'id': r['id'], 'patient': r['patient'], 'ordinal': r['ordinal'], 'position_set': r['position_set'], 'grade': r['grade'],
            **{n: systems[n][i] for n in systems}, **{n + '_swap': swapped[n][i] for n in systems}} for i, r in enumerate(rows)]
    for obj, fn in ((per, 'per_row.json'), (rep, 'report.json')):
        json.dump(obj, open(f'{EVAL}/{fn}.tmp', 'w'), indent=1)
        os.replace(f'{EVAL}/{fn}.tmp', f'{EVAL}/{fn}')
    print(json.dumps({'held_primary': sysh, 'flags': flags}, indent=1))


def cmd_lock(a):
    """첫 E24 출력 전: 코드·선택 근거·checkpoint·manifest·환경 hash를 고정. 생성 출력은 포함하지 않는다(별도 seal)."""
    spec = json.load(open(a.spec))
    files = {f: sha_file(f) for f in CODE}
    for name, p in spec['json_systems'].items():
        if os.path.exists(p):
            sys.exit(f'E24 prediction output already exists before lock: {p}')
    for name, v in spec['vlm'].items():
        if files_of(v['dir']):
            sys.exit(f'E24 output already exists before lock: {v["dir"]}')
    for f in spec.get('extra_files', []):
        files[f] = sha_file(f)
    if os.path.exists(f'{EVAL}/eval_lock.json'):
        sys.exit('lock exists')
    os.makedirs(EVAL, exist_ok=True)
    tmp = f'{EVAL}/eval_lock.json.tmp'
    json.dump({'vlm': spec['vlm'], 'json_systems': spec['json_systems'], 'files': files, 'selection': spec.get('selection')}, open(tmp, 'w'), indent=1)
    os.replace(tmp, f'{EVAL}/eval_lock.json')
    print('locked', len(files))


def cmd_seal(a):
    """E24 출력 완료 후: 요청 집합 완전성·provenance 확인 뒤 출력 파일 hash를 봉인한다."""
    lock = json.load(open(f'{EVAL}/eval_lock.json'))
    for f, h in lock['files'].items():
        if sha_file(f) != h:
            sys.exit(f'locked file changed: {f}')
    man = D.load_manifest()
    rows = sorted([r for r in man['rows'] if r['split'] == 'E24' and not r['excluded']], key=lambda r: (int(r['patient']), r['ordinal']))
    outputs = {}
    for name, spec in lock['vlm'].items():
        load_vlm(spec['dir'], rows, spec['variant'], spec['adapter_digest'])   # 누락/중복/집합 밖/입력 hash/adapter 불일치면 예외
        for f in files_of(spec['dir']):
            outputs[f] = sha_file(f)
    for name, p in lock['json_systems'].items():
        load_json_pred(p, rows)
        outputs[p] = sha_file(p)
    if os.path.exists(f'{EVAL}/eval_seal.json'):
        sys.exit('seal exists')
    tmp = f'{EVAL}/eval_seal.json.tmp'
    json.dump({'lock_sha256': sha_file(f'{EVAL}/eval_lock.json'), 'outputs': outputs, 'n_rows': len(rows)}, open(tmp, 'w'), indent=1)
    os.replace(tmp, f'{EVAL}/eval_seal.json')
    print('sealed', len(outputs))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='c', required=True)
    sp.add_parser('run')
    l = sp.add_parser('lock'); l.add_argument('--spec', required=True)
    sp.add_parser('seal')
    a = ap.parse_args()
    {'run': cmd_run, 'lock': cmd_lock, 'seal': cmd_seal}[a.c](a)
