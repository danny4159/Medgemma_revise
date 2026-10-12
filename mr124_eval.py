"""iter_124 평가(Qwen vs MedGemma 기존 W 출력, 보고서 적격 23명). Qwen 탐색 출력 생성 전에 코드 hash를 잠근다(eval_lock.json).
 - 입력 검증: 탐색 protocol 재검증, verify.json의 record 파일 hash·digest 일치, 요청 집합 정확 일치, MedGemma 출력 23건 존재·parser 재현.
 - 정답: 보고서 기반 원 label(positive/negative). PRESENT=양성 정답, ABSENT=음성 정답. UNCERTAIN·INVALID는 해당 클래스에서 오답.
 - 주지표 BA. Qwen-MedGemma paired BA 차이: label x batch 4개 층 내 환자 bootstrap 10,000회, seed 124, 95% percentile CI.
 - 판정은 decision_contract(양성/음성/불확정)를 그대로 코드화. 임계 변경 없음.
usage: python mr124_eval.py lock | run
"""
import glob, hashlib, json, os, sys, time

import numpy as np

import mr123_run as R
import mr124_run as M

LOCK = 'results/iter_124/eval/eval_lock.json'
OUT = 'results/iter_124/eval/report.json'
PROT = 'results/iter_124/gen/explore/protocol.json'
REQ = 'results/iter_124/gen/explore/requests.jsonl'
QDIR = 'results/iter_124/gen/explore/main'
VERIFY = QDIR + '/verify.json'
CODE = ['mr124_eval.py', 'mr124_run.py', 'mr123_run.py']
SEED, NBOOT = 124, 10000


def ba(correct_pos, correct_neg):
    return 0.5 * (np.mean(correct_pos) + np.mean(correct_neg)) if len(correct_pos) and len(correct_neg) else float('nan')


def metrics(states, labels, codes, eos=None):
    pos = [s == 'PRESENT' for s, l in zip(states, labels) if l == 'positive']
    neg = [s == 'ABSENT' for s, l in zip(states, labels) if l == 'negative']
    sens, spec = float(np.mean(pos)), float(np.mean(neg))
    conf = {l: {s: sum(1 for x, y in zip(states, labels) if y == l and x == s) for s in ('PRESENT', 'ABSENT', 'UNCERTAIN', 'INVALID')} for l in ('positive', 'negative')}
    n = len(states)
    return {'BA': 0.5 * (sens + spec), 'sensitivity': sens, 'specificity': spec, 'n_pos': len(pos), 'n_neg': len(neg), 'confusion': conf,
            'explicit_coverage': sum(s in ('PRESENT', 'ABSENT') for s in states) / n, 'n_strict': sum(c == 'ok_strict' for c in codes),
            'n_loose': sum(c == 'ok_loose' for c in codes), 'n_uncertain': sum(s == 'UNCERTAIN' for s in states),
            'n_invalid': sum(s == 'INVALID' for s in states), 'n_refusal': sum(c == 'refusal' for c in codes),
            'n_non_eos': None if eos is None else sum(not e for e in eos), 'all_same_state': len(set(states)) == 1,
            'n_present': sum(s == 'PRESENT' for s in states)}


def boot_diff(cq, cm, labels, batches, seed=SEED, nboot=NBOOT):
    """cq, cm: 환자별 정답(0/1). 층(label x batch) 내 환자 재표집으로 BA(q)-BA(m)의 분포."""
    rng = np.random.default_rng(seed)
    lab = np.array(labels); bat = np.array(batches)
    strata = {}
    for i, (l, b) in enumerate(zip(lab, bat)):
        strata.setdefault((l, b), []).append(i)
    cq, cm = np.array(cq, float), np.array(cm, float)
    diffs = np.empty(nboot)
    for k in range(nboot):
        idx = np.concatenate([rng.choice(v, size=len(v), replace=True) for v in strata.values()])
        p = lab[idx] == 'positive'
        dq = 0.5 * (cq[idx][p].mean() + cq[idx][~p].mean()); dm = 0.5 * (cm[idx][p].mean() + cm[idx][~p].mean())
        diffs[k] = dq - dm
    return {'ci95': [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))], 'n_boot': nboot, 'seed': seed,
            'n_strata': len(strata), 'strata_sizes': {f'{k[0]}|{k[1]}': len(v) for k, v in strata.items()}, 'degenerate': bool(np.ptp(diffs) == 0)}


def decide(q, m, d, batch_q):
    ci_lo = d['ci95'][0]
    pos = (q['BA'] >= 0.75 and q['sensitivity'] >= 0.67 and q['specificity'] >= 0.67 and (q['BA'] - m['BA']) >= 0.20 and ci_lo > 0)
    neg = q['BA'] <= 0.60 or q['all_same_state']
    if pos:
        limited = any(b['BA'] <= 0.50 for b in batch_q.values())
        return {'branch': 'positive_limited_batch_dependent' if limited else 'positive', 'action': 'preserve limited model/interface-specificity evidence; only specialist-alternative residual-value review next; no auto expansion' if not limited else 'batch-dependent: uncertain, limited preservation only'}
    if neg:
        return {'branch': 'negative', 'action': 'hold investment in this fixed periventricular-FLAIR discrimination candidate; common internal cause not determined'}
    return {'branch': 'inconclusive', 'action': 'hold investment (insufficient evidence); no more patients/prompts/models in this plan'}


def load_inputs():
    pdig = M.check_protocol(REQ, PROT, full=True)
    rows = M.read_jsonl(REQ)
    v = json.load(open(VERIFY))
    assert v['n_problems'] == 0 and v['protocol_digest'] == pdig and v['n_records'] == len(rows) == 23
    files = sorted(glob.glob(f'{QDIR}/worker*.jsonl'))
    assert set(files) == set(v['record_file_sha256']), 'record 파일 집합 불일치'
    for f in files:
        assert M.sha_file(f) == v['record_file_sha256'][f], 'record 파일 hash 불일치 ' + f
    q = {}
    for f in files:
        for r in M.read_jsonl(f):
            assert r['id'] not in q, 'duplicate'
            q[r['id']] = r
    assert set(q) == {r['id'] for r in rows}
    mg = {}
    for f in glob.glob('results/iter_123/gen/explore/worker_m*.jsonl'):
        for r in R.read_jsonl(f):
            assert r['id'] not in mg
            mg[r['id']] = r
    for r in rows:
        o = mg[r['orig_id']]
        assert o['cond'] == 'W' and o['study_uid'] == r['study_uid'] and R.parse(o['text']) == (o['state'], o['parse_code'])
    el = json.load(open(M.LOCK_ELIG))
    assert {x['study_uid'] for x in el['rows'] if x['eligible']} == {r['study_uid'] for r in rows}
    return rows, q, mg, pdig


def run():
    assert not os.path.exists(OUT)
    lk = json.load(open(LOCK))
    for f, h in lk['code'].items():
        assert M.sha_file(f) == h, 'eval code changed after lock: ' + f
    rows, q, mg, pdig = load_inputs()
    lab = [r['label'] for r in rows]; bat = [r['batch_id'] for r in rows]
    qs = [q[r['id']]['state'] for r in rows]; qc = [q[r['id']]['parse_code'] for r in rows]; qe = [q[r['id']]['eos'] for r in rows]
    ms = [mg[r['orig_id']]['state'] for r in rows]; mc = [mg[r['orig_id']]['parse_code'] for r in rows]
    mq = metrics(qs, lab, qc, qe); mm = metrics(ms, lab, mc)
    cor = lambda st: [int((s == 'PRESENT') if l == 'positive' else (s == 'ABSENT')) for s, l in zip(st, lab)]
    cq, cm = cor(qs), cor(ms)
    d = boot_diff(cq, cm, lab, bat)
    d['delta_BA'] = mq['BA'] - mm['BA']
    d['flips_qwen_correct_medgemma_wrong'] = sum(1 for a, b in zip(cq, cm) if a == 1 and b == 0)
    d['flips_medgemma_correct_qwen_wrong'] = sum(1 for a, b in zip(cq, cm) if a == 0 and b == 1)
    byb = {}
    for b in sorted(set(bat)):
        ix = [i for i, x in enumerate(bat) if x == b]
        byb[b] = {'qwen': metrics([qs[i] for i in ix], [lab[i] for i in ix], [qc[i] for i in ix]),
                  'medgemma': metrics([ms[i] for i in ix], [lab[i] for i in ix], [mc[i] for i in ix])}
    batch_q = {b: v['qwen'] for b, v in byb.items()}
    dec = decide(mq, mm, d, batch_q)
    orig48 = json.load(open('results/iter_123/eval_explore.json'))
    rep = {'n': len(rows), 'qwen': mq, 'medgemma_w': mm, 'paired': d, 'by_batch': byb, 'constant_PRESENT_BA': 0.5, 'decision': dec,
           'per_patient': [{'study_uid': r['study_uid'], 'label': r['label'], 'batch': r['batch_id'], 'qwen': s, 'medgemma': t} for r, s, t in zip(rows, qs, ms)],
           'qwen_cost': {'n_requests': len(rows), 'read_to_save_s_sum': sum(q[r['id']]['read_to_save_s'] for r in rows),
                         'gen_s_sum': sum(q[r['id']]['gen_s'] for r in rows), 'n_new_sum': sum(q[r['id']]['n_new'] for r in rows),
                         'prompt_tokens': sorted({q[r['id']]['prompt_tokens'] for r in rows}), 'peak_mem_alloc_gb_max': max(q[r['id']]['peak_mem_alloc_gb'] for r in rows)},
           'medgemma_saved_wall_s_reference_only': sum(mg[r['orig_id']]['wall_s'] for r in rows),
           'iter123_original48_reference': {'n_patients': orig48['n_patients'], 'metrics': orig48['metrics']},
           'protocol_digest': pdig, 'eval_lock': lk['locked_at'], 'code_sha256': lk['code'], 'created_at': time.strftime('%Y-%m-%dT%H:%M:%S')}
    json.dump(rep, open(OUT, 'w'), indent=1)
    print(json.dumps({k: rep[k] for k in ('qwen', 'medgemma_w', 'paired', 'decision')}, indent=1)[:3500])


def lock():
    assert not os.path.exists(LOCK)
    assert not glob.glob(f'{QDIR}/worker*.jsonl'), 'Qwen 탐색 출력이 이미 존재'
    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    json.dump({'locked_at': time.strftime('%Y-%m-%dT%H:%M:%S'), 'qwen_explore_outputs_exist': False, 'code': {f: M.sha_file(f) for f in CODE},
               'protocol_digest': json.load(open(PROT))['digest'], 'requests': M.sha_file(REQ), 'eligibility_lock': M.sha_file(M.LOCK_ELIG)},
              open(LOCK, 'w'), indent=1)
    print('locked')


if __name__ == '__main__':
    {'lock': lock, 'run': run}[sys.argv[1]]()
