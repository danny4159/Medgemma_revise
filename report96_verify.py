"""iter_096 검증: (1) 입력·digest·request ID, (2) 판정 quote가 원본 request 출력의 정확한 offset과 일치하는지,
(3) report96_eval 함수를 쓰지 않는 별도 산술(셀 집합 기반)로 충돌·회복·CI를 재계산해 report와 대조한다.
같은 판정표를 읽으므로 독립 의미 평가가 아니라 산술·연결 검증이다. 실패 시 비정상 종료.
사용: python report96_verify.py <ver>"""
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np

import report96_ref as R
from report96_lock import R96, R95, ROOT
from report86_common import sha, save, record_digest

CELLS = {'U': 0, 'M': 1, 'L': 2}


def raw_texts(man):
    """원본 outputs.jsonl을 직접 읽어 request_id -> 정리된 텍스트. (report95_view/old_C_records를 쓰지 않는다.)"""
    pre1 = re.compile(r'^Location of the [^:]*:\s*\[[^\]]*\]\.?\s*Description:\s*')
    pre2 = re.compile(r'^Description of the [^:]*:\s*')
    out, recs = {}, {}
    files = [f for f in man['file_sha256'] if f.endswith('outputs.jsonl')]
    for f in files:
        for ln in (ROOT / f).read_text().splitlines():
            if not ln.strip():
                continue
            r = json.loads(ln)
            t = pre2.sub('', pre1.sub('', r['text'].strip())).strip()
            out[r['id']] = t
            recs[r['id']] = r
    return out, recs


def cells(scope, region, mode):
    """scope -> (set of (side, level) cells, kind) ; 별도 구현: 측면×3단계 셀."""
    sc = scope
    if sc['sides'] is None or (mode == 'narrow' and sc.get('plural')):
        sc = R.region_scope(region) if mode in ('question', 'narrow') else dict(sides='RL', level=None, type='lung')
    lv = sc['level'] or 'UML'
    return {(s, l) for s in sc['sides'] for l in lv}, sc['type'], sc['level'] is None


def overlap(a, b, lz_equal=False):
    ca, ta, wa = a
    cb, tb, wb = b
    inter = ca & cb
    if not inter:
        return 0
    if wa or wb:
        return 2
    if len(ca) > 2 and False:
        return 1
    if (len({l for _, l in ca}) > 1) or (len({l for _, l in cb}) > 1):
        return 1
    return 2 if (ta == tb or lz_equal) else 1


PAR = {'opacity', 'infiltrate', 'consolidation', 'atelectasis'}
OPC = {'opacity', 'infiltrate', 'consolidation'}


def indep_conflict_patients(J, bundle_fn, mode='question', accept=('definite',), lz_equal=False, broad=False, excl_noneos=False, excl_hedged_cause=False):
    pats = set()
    byp = {}
    for o in J['outputs']:
        if not bundle_fn(o['cond'], o['region']) or (excl_noneos and not o['ended_eos']):
            continue
        for s in o['sentences']:
            for c in s['claims']:
                byp.setdefault(o['p'], []).append((o['region'], c))
    for p, lst in byp.items():
        for rp, cp in lst:
            if cp['pol'] != 'P' or cp['kind'] not in PAR or (excl_hedged_cause and any(x['cert'] == 'hedged' for x in cp['cause'])):
                continue
            for rn, cn in lst:
                if cn['pol'] != 'N' or cn['kind'] == 'pneumonia':
                    continue
                if cn['kind'] == 'clear':
                    ok = True
                elif cn['kind'] in OPC:
                    ok = cp['kind'] == cn['kind'] or (cn['kind'] == 'opacity' and cp['kind'] in OPC) or (broad and cp['kind'] in OPC)
                else:
                    ok = False
                if not ok:
                    continue
                ov = overlap(cells(cp['scope'], rp, mode), cells(cn['scope'], rn, mode), lz_equal)
                if ov == 0:
                    continue
                st = 'qualified' if cn['neg'] == 'qualified' else ('hedged_pos' if cp['pres'] != 'definite' else ('definite' if ov == 2 else 'uncertain_scope'))
                if st in accept:
                    pats.add(p)
    return pats


def check_offsets(J, texts):
    """(문장 수, 불일치 목록). 원문 텍스트의 [start:end]가 quote와 정확히 같아야 하며 text sha가 일치해야 한다."""
    nq, mism = 0, []
    for o in J['outputs']:
        t = texts[o['request_id']]
        if hashlib.sha256(t.encode()).hexdigest() != o['text_sha256']:
            mism.append([o['request_id'], 'text_sha'])
        for s in o['sentences']:
            nq += 1
            if t[s['start']:s['end']] != s['quote']:
                mism.append([o['request_id'], s['start'], s['end']])
    return nq, mism


def verify(ver, tag=''):
    man = json.loads((R96 / 'lock/input_manifest.json').read_text())
    J = json.loads((R96 / f'judging/judgments_E32_{ver}.json').read_text())
    rep = json.loads((R96 / f'eval/report_E32_{ver}{tag}.json').read_text())
    checks = []

    def chk(name, ok, detail=None):
        checks.append({'name': name, 'pass': bool(ok), 'detail': detail})

    # 1. 입력 digest
    bad = [f for f, h in man['file_sha256'].items() if sha(ROOT / f) != h]
    chk('manifest_file_hashes', not bad, bad)
    chk('manifest_self_sha', man['sha256'] == __import__('report86_common').sha_obj({k: v for k, v in man.items() if k not in ('rows', 'sha256')}))
    chk('plan95_sha', sha(ROOT.parent / 'agent/runs/iter_095/plan.md') == man['baseline_plan']['sha256'])
    for k, f in (('selection_sha256', R95 / 'lock/selection.json'), ('reference_target_sha256', R95 / 'lock/reference_target.json'), ('blind_key_sha256', R95 / 'judging/blind_key_private_E32.json')):
        chk(k, sha(f) == man[k])
    texts, recs = raw_texts(man)
    ids = [r['request_id'] for r in man['rows']]
    chk('544_unique_request_ids', len(ids) == 544 == len(set(ids)))
    chk('request_ids_in_raw_outputs', all(i in recs for i in ids), [i for i in ids if i not in recs][:3])
    rd_bad = [i for i in ids if i in recs and recs[i].get('record_digest') != record_digest(recs[i])]
    chk('record_digest', not rd_bad, rd_bad[:3])
    chk('judgment_outputs_match_manifest', [o['request_id'] for o in J['outputs']] == [r['request_id'] for r in sorted(man['rows'], key=lambda r: (r['p'], r['oid']))])
    # 2. quote offset (원본 텍스트 기준)
    nq, mism = check_offsets(J, texts)
    nb = len(mism)
    chk('quote_offsets_exact', nb == 0 and not mism, {'n_sentences': nq, 'bad': mism[:5]})
    # non-EOS
    chk('non_eos_listed', [[o['p'], o['oid']] for o in J['outputs'] if not o['ended_eos']] == [[r[0], r[1]] for r in man['non_eos_final']])
    # 3. 별도 산술
    from report96_eval import BUNDLES, VARIANTS
    for b, fn in BUNDLES.items():
        for v, kw in VARIANTS.items():
            mode = kw['mode']
            mine = indep_conflict_patients(J, fn, mode=mode, accept=kw.get('accept', ('definite',)), lz_equal=kw.get('lz_equal', False), broad=kw.get('broad', False), excl_noneos=kw.get('excl_noneos', False), excl_hedged_cause=kw.get('excl_hedged_cause', False))
            chk(f'conflict_{b}_{v}', len(mine) == rep['bundles'][b]['conflict_patients'][v], [len(mine), rep['bundles'][b]['conflict_patients'][v]])
        mine_set = sorted(indep_conflict_patients(J, fn))
        chk(f'conflict_patients_set_{b}', mine_set == sorted(int(p) for p in rep['cases'][b]['conflicts']), mine_set)
    # 회복(strict) 별도 계산: 종류·셀 겹침·시간 규칙을 다시 구현
    pos_p = sorted({k[0] for k in R.POS_FACTS})
    for b, fn in BUNDLES.items():
        got = set()
        for o in J['outputs']:
            if o['p'] not in pos_p or not fn(o['cond'], o['region']):
                continue
            for s in o['sentences']:
                for c in s['claims']:
                    if c['pol'] != 'P':
                        continue
                    for (p, f), fact in R.POS_FACTS.items():
                        if p != o['p']:
                            continue
                        for alt in fact['alts']:
                            ks = c['kind'] in alt['strict'] or (c['kind'] == 'opacity' and fact['cause'] == 'infection' and any(x['name'] in ('pneumonia', 'infection') and x['cert'] in ('probable', 'concern') for x in c['cause']))
                            if not ks:
                                continue
                            if alt['sides'] is None:
                                ov = 2
                            else:
                                a = cells(c['scope'], o['region'], 'question')
                                lv = alt['level'] or 'UML'
                                bb = ({(s_, l) for s_ in alt['sides'] for l in lv}, alt['type'], alt['level'] is None)
                                ov = overlap(a, bb)
                            rt = alt['temporal'] if 'temporal' in alt else fact['temporal']
                            tc = (rt in ('decrease', 'persistent') and c['temporal'] == 'new') or (rt == 'new' and c['temporal'] in ('unchanged', 'again', 'still'))
                            if ov == 2 and not tc:
                                got.add((p, f))
        chk(f'recovery_strict_{b}', len(got) == rep['bundles'][b]['facts_recovered_strict'], [len(got), rep['bundles'][b]['facts_recovered_strict']])
    # bootstrap CI (D8-L8 conflict)
    a = np.array([int(p in indep_conflict_patients(J, BUNDLES['D8'])) for p in range(32)], float)
    bb = np.array([int(p in indep_conflict_patients(J, BUNDLES['L8'])) for p in range(32)], float)
    d = a - bb
    rng = np.random.default_rng(95017)
    m = d[rng.integers(0, 32, (10000, 32))].mean(1)
    mine = [float(d.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]
    ref = rep['compare']['conflict']['primary']['D8-L8']
    chk('bootstrap_D8_L8', abs(mine[0] - ref['mean']) < 1e-12 and abs(mine[1] - ref['ci95'][0]) < 1e-12 and abs(mine[2] - ref['ci95'][1]) < 1e-12, mine)
    ok = all(c['pass'] for c in checks)
    res = {'version': ver, 'all_pass': ok, 'n_checks': len(checks), 'n_pass': sum(c['pass'] for c in checks), 'checks': checks,
           'inputs': {'judgments_sha256': sha(R96 / f'judging/judgments_E32_{ver}.json'), 'report_sha256': sha(R96 / f'eval/report_E32_{ver}{tag}.json'), 'verify_sha256': sha(__file__)},
           'note': '같은 판정표를 읽는 산술·연결 검증이며 독립 의미 평가가 아니다.'}
    save(R96 / f'eval/verify_E32_{ver}{tag}.json', res)
    print(res['n_pass'], '/', res['n_checks'])
    for c in checks:
        if not c['pass']:
            print('FAIL', c)
    return ok


if __name__ == '__main__':
    sys.exit(0 if verify(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else '') else 1)
