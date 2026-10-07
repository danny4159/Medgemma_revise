"""iter_096 평가: judgments_E32.json(문장 offset이 붙은 구조화 주장)에서 회복·충돌·동시 발생·오류 비용을 계산한다.
report95_eval을 호출하지 않는 별도 집계다. 같은 판정표를 읽으므로 독립 의미 평가가 아니라 산술 재구현이다.
사용:
  python report96_eval.py judge   # outputs -> judgments_E32.json, sentence_review.json (새 파일만)
  python report96_eval.py eval    # judgments -> eval/report_E32.json
"""
import json
import sys
from collections import Counter, OrderedDict
from pathlib import Path

import numpy as np

import report96_ref as R
import report96_sem as S
from report96_lock import R96, R95, ROOT
from report86_common import sha, save

SEED = 95017
OPAC = R.OPAC
PAR = R.OPAC_AT
BUNDLES = OrderedDict([
    ('CG', lambda c, r: c == 'G'),
    ('L2', lambda c, r: c == 'L' and r in ('left lung', 'right lung')),
    ('D2', lambda c, r: c == 'D' and r in ('left lung', 'right lung')),
    ('L8', lambda c, r: c == 'L' and r != 'G'), ('D8', lambda c, r: c == 'D' and r != 'G'),
    ('L6', lambda c, r: c == 'L' and r not in ('left lung', 'right lung', 'G')),
    ('D6', lambda c, r: c == 'D' and r not in ('left lung', 'right lung', 'G'))])


# ---------------------------------------------------------------- 판정표 생성
def judge(ver):
    import report95_view as V
    man = json.loads((R96 / 'lock/input_manifest.json').read_text())
    outs = V.outputs_for('E32')
    rows = {(r['ImageID'], r['oid']): r for r in man['rows']}
    out, review = [], OrderedDict()
    for pi, (img, lst) in enumerate(outs.items()):
        for x in sorted(lst, key=lambda x: x['oid']):
            m = rows[(img, x['oid'])]
            assert m['request_id'] == x['rec']['id']
            sents = S.analyze_text(x['text'], x['region'])
            out.append({'p': pi, 'ImageID': img, 'oid': x['oid'], 'cond': x['cond'], 'region': x['region'], 'request_id': x['rec']['id'],
                        'text_sha256': m['text_sha256'], 'ended_eos': m['ended_eos'], 'n_new': m['n_new'], 'runtime_s_sum': m['runtime_s_sum'],
                        'sentences': sents})
            for st, en, sent in S.split_sentences(x['text']):
                r = review.setdefault(sent, {'sentence': sent, 'n': 0, 'regions_seen': [], 'final': None})
                r['n'] += 1
                if x['region'] not in r['regions_seen']:
                    r['regions_seen'].append(x['region'])
    for sent, r in review.items():
        r['final'] = S.analyze_sentence(sent, r['regions_seen'][0])
        r['override'] = S.OVERRIDES[sent][1] if sent in S.OVERRIDES else None
        # 같은 문장이 영역에 따라 다른 claim을 내면(규칙은 영역에 의존하지 않으므로 발생하지 않아야 한다) 거부
        for rg in r['regions_seen']:
            assert S.analyze_sentence(sent, rg) == r['final'], sent
    save(R96 / f'judging/judgments_E32_{ver}.json', {'rule_module_sha256': sha(ROOT / 'report96_sem.py'), 'outputs': out})
    save(R96 / f'judging/sentence_review_{ver}.json', {'n_unique_sentences': len(review), 'n_with_claims': sum(bool(r['final']) for r in review.values()),
                                                'sentences': list(review.values())})
    print(len(out), len(review))


# ---------------------------------------------------------------- 범위 연산
def resolve(scope, region, mode):
    if mode == 'narrow' and scope.get('plural'):
        return R.region_scope(region)
    if scope['sides'] is not None:
        return scope
    return R.region_scope(region) if mode in ('question', 'narrow') else dict(sides='RL', level=None, type='lung', src='global')


def ovl(a, b, lz_equal=False):
    """0 겹침 없음, 1 불확실(lobe-zone 혼합 또는 level 불명), 2 확실한 겹침/포함."""
    if not (set(a['sides']) & set(b['sides'])):
        return 0
    if a['level'] is None or b['level'] is None:
        return 2
    la, lb = set(a['level']), set(b['level'])
    if not (la & lb):
        return 0
    if len(la) > 1 or len(lb) > 1:
        return 1
    if a['type'] == b['type']:
        return 2
    return 2 if lz_equal else 1


def kind_compat(neg_kind, pos_kind, broad=False):
    if neg_kind == 'clear':
        return pos_kind in PAR
    if neg_kind in OPAC:
        return pos_kind == neg_kind or (neg_kind == 'opacity' and pos_kind in OPAC) or (broad and pos_kind in OPAC)
    return False


def flat_claims(J):
    cl = []
    for o in J['outputs']:
        for si, s in enumerate(o['sentences']):
            for ci, c in enumerate(s['claims']):
                cl.append(dict(c, p=o['p'], oid=o['oid'], cond=o['cond'], region=o['region'], eos=o['ended_eos'], s=si, c=ci,
                               quote=s['quote'], start=s['start'], end=s['end'], cid=f"{o['p']}:{o['oid']}:{si}:{ci}"))
    return cl


def in_bundle(b, cl):
    return BUNDLES[b](cl['cond'], cl['region'])


# ---------------------------------------------------------------- 충돌
VARIANTS = {
    'primary': dict(mode='question'),
    'global_scope': dict(mode='global'),
    'narrow_plural_lungs': dict(mode='narrow'),
    'plus_uncertain_scope': dict(mode='question', accept=('definite', 'uncertain_scope')),
    'plus_qualified_negation': dict(mode='question', accept=('definite', 'qualified')),
    'lobe_zone_equal': dict(mode='question', lz_equal=True),
    'broad_kind': dict(mode='question', broad=True),
    'excl_nonEOS': dict(mode='question', excl_noneos=True),
    'excl_cause_hedged_positive': dict(mode='question', excl_hedged_cause=True),   # iter_095식 문장 전체 hedge를 존재 불확실로 읽은 하한
}


def pair_status(pos, neg, mode, lz_equal=False, broad=False):
    if pos['pol'] != 'P' or neg['pol'] != 'N' or neg['kind'] == 'pneumonia' or pos['kind'] not in PAR:
        return None
    if not kind_compat(neg['kind'], pos['kind'], broad):
        return None
    o = ovl(resolve(pos['scope'], pos['region'], mode), resolve(neg['scope'], neg['region'], mode), lz_equal)
    if o == 0:
        return None
    if neg['neg'] == 'qualified':
        return 'qualified'
    if pos['pres'] != 'definite':
        return 'hedged_pos'
    return 'definite' if o == 2 else 'uncertain_scope'


def conflicts(claims, b, variant):
    kw = VARIANTS[variant]
    accept = kw.get('accept', ('definite',))
    res = {}
    cs = [c for c in claims if in_bundle(b, c) and not (kw.get('excl_noneos') and not c['eos'])]
    pos = [c for c in cs if c['pol'] == 'P' and not (kw.get('excl_hedged_cause') and any(x['cert'] == 'hedged' for x in c['cause']))]
    neg = [c for c in cs if c['pol'] == 'N']
    for p in pos:
        for n in neg:
            if p['p'] != n['p']:
                continue
            st = pair_status(p, n, kw['mode'], kw.get('lz_equal', False), kw.get('broad', False))
            if st in accept:
                res.setdefault(p['p'], []).append((p, n, st))
    return res


def cause_conflicts(claims, b):
    """원인 수준 충돌: 양성 주장이 pneumonia 원인을 제시하고 같은 번들의 부정이 pneumonia를 직접 부정(확정 범위 겹침)."""
    res = {}
    cs = [c for c in claims if in_bundle(b, c)]
    for p in [c for c in cs if c['pol'] == 'P' and any(x['name'] == 'pneumonia' for x in c['cause'])]:
        for n in [c for c in cs if c['pol'] == 'N' and c['kind'] == 'pneumonia' and c['neg'] == 'specific' and c['p'] == p['p']]:
            if ovl(resolve(p['scope'], p['region'], 'question'), resolve(n['scope'], n['region'], 'question')) >= 1:
                res.setdefault(p['p'], []).append((p, n))
    return res


# ---------------------------------------------------------------- 회복
def tcontra(claim_t, ref_t):
    if ref_t in ('decrease', 'persistent') and claim_t == 'new':   # 'increase'는 신규 출현과 모순이 아님
        return True
    if ref_t == 'new' and claim_t in ('unchanged', 'again', 'still'):
        return True
    return False


def cause_support(claim, fact):
    want = fact.get('cause')
    if not want:
        return False
    return any(x['name'] in ('pneumonia', 'infection') and x['cert'] in ('probable', 'concern') for x in claim['cause']) and want == 'infection'


def match_fact(cl, fact, lz_equal=False):
    best = None
    for alt in fact['alts']:
        kind_s = cl['kind'] in alt['strict']
        assisted = False
        if not kind_s and cl['kind'] == 'opacity' and cause_support(cl, fact):
            kind_s, assisted = True, True
        kind_l = cl['kind'] in alt['len']
        if not kind_l:
            continue
        if alt['sides'] is None:
            loc = 2
        else:
            loc = ovl(resolve(cl['scope'], cl['region'], 'question'), dict(sides=alt['sides'], level=alt['level'], type=alt['type']), lz_equal)
        if loc == 0:
            continue
        rt = alt.get('temporal', fact['temporal']) if 'temporal' in alt else fact['temporal']
        tc = tcontra(cl['temporal'], rt)
        r = dict(strict_ti=kind_s and loc == 2, strict=kind_s and loc == 2 and not tc, lenient=True, lenient_timeok=not tc, tcontra=tc,
                 assisted=assisted, loc=loc)
        if best is None or (r['strict'], r['strict_ti'], r['lenient_timeok']) > (best['strict'], best['strict_ti'], best['lenient_timeok']):
            best = r
    return best


LEVELS = ('strict', 'strict_ti', 'lenient', 'lenient_timeok')


def recoveries(claims, b, ref_pos_by_p, lz_equal=False, excl_noneos=False, no_assist=False):
    """-> {p: {fact: {level: [cid,...]}}}"""
    res = {}
    cs = [c for c in claims if in_bundle(b, c) and c['pol'] == 'P' and not (excl_noneos and not c['eos'])]
    for c in cs:
        for fkey in ref_pos_by_p.get(c['p'], []):
            m = match_fact(c, R.POS_FACTS[fkey], lz_equal)
            if not m:
                continue
            d = res.setdefault(c['p'], {}).setdefault(fkey[1], {k: [] for k in LEVELS})
            ok = dict(strict=m['strict'] and not (no_assist and m['assisted']), strict_ti=m['strict_ti'] and not (no_assist and m['assisted']),
                      lenient=True, lenient_timeok=m['lenient_timeok'])
            for k in LEVELS:
                if ok[k]:
                    d[k].append(c['cid'])
    return res


def rec_set(rec, level):
    return {(p, f) for p, fs in rec.items() for f, d in fs.items() if d[level]}


# ---------------------------------------------------------------- 오류 비용
def error_cost(claims, b, layer, excl_noneos=False):
    """양성 주장 수준 분류. 비교 reference가 있는 환자(pos/neg)에서만 contradicted/supported를 판정한다."""
    n = Counter()
    pats = {k: set() for k in ('unsupported', 'contradicted', 'temporal', 'cause')}
    ref_pos = {}
    for (p, f), fact in R.POS_FACTS.items():
        ref_pos.setdefault(p, []).append((p, f))
    for c in claims:
        if not in_bundle(b, c) or c['pol'] != 'P' or (excl_noneos and not c['eos']):
            continue
        n['positive_claims'] += 1
        lay = layer[c['p']]
        matched = False
        tstat = None
        if lay == 'pos':
            for fkey in ref_pos.get(c['p'], []):
                m = match_fact(c, R.POS_FACTS[fkey])
                if m and m['lenient']:
                    matched = True
                    tstat = 'contradicted' if m['tcontra'] else ('supported' if R.POS_FACTS[fkey]['temporal'] or any(a.get('temporal') for a in R.POS_FACTS[fkey]['alts']) else 'unsupported')
        if matched:
            n['matched_to_reference_fact'] += 1
        elif lay == 'neg':
            nr = R.NEG_REF[c['p']]
            if c['kind'] in nr['direct'] and not nr['scoped']:
                n['contradicted_by_reference_direct'] += 1
                pats['contradicted'].add(c['p'])
            elif c['kind'] in nr['qualified'] or nr['scoped'] or c['kind'] in nr['direct']:
                n['conflicts_with_reference_qualified_or_scoped'] += 1
            else:
                n['unsupported_no_reference'] += 1
                pats['unsupported'].add(c['p'])
        else:
            n['unsupported_no_reference'] += 1
            pats['unsupported'].add(c['p'])
        if c['temporal'] in ('new', 'unchanged', 'again', 'still'):
            n['temporal_assertions'] += 1
            key = 'temporal_' + (tstat or 'unsupported')
            n[key] += 1
            if (tstat or 'unsupported') != 'supported':
                pats['temporal'].add(c['p'])
        if c['cause']:
            hedged = [x for x in c['cause'] if x['cert'] == 'hedged']
            n['claims_with_cause'] += 1
            n['claims_with_nonhedged_cause'] += int(len(hedged) < len(c['cause']))
            if not (matched and lay == 'pos' and any(R.POS_FACTS[fk]['cause'] for fk in ref_pos.get(c['p'], []))):
                n['cause_unsupported_by_reference'] += 1
                pats['cause'].add(c['p'])
    out = dict(n)
    out.update({f'patients_{k}': len(v) for k, v in pats.items()})
    return out


# ---------------------------------------------------------------- 통계
def boot(a, b, n=10000):
    d = np.asarray(a, float) - np.asarray(b, float)
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(d), (n, len(d)))
    m = d[idx].mean(1)
    return {'mean': float(d.mean()), 'ci95': [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))], 'n': len(d)}


def evaluate(ver, rtag=''):
    J = json.loads((R96 / f'judging/judgments_E32_{ver}.json').read_text())
    man = json.loads((R96 / 'lock/input_manifest.json').read_text())
    ref = json.loads((R95 / 'lock/reference_target.json').read_text())
    sel = json.loads((R95 / 'lock/selection.json').read_text())
    pats = sel['E32']
    layer = {i: ref[img]['layer'] for i, img in enumerate(pats)}
    pos_idx = [i for i in range(32) if layer[i] == 'pos']
    facts_of = {p: [k for k in R.POS_FACTS if k[0] == p] for p in pos_idx}
    assert sorted(k for ks in facts_of.values() for k in ks) == sorted(R.POS_FACTS), 'reference 인코딩 불일치'
    nfacts = {p: len(ref[pats[p]]['pos_facts']) for p in pos_idx}
    for p in pos_idx:
        assert len(facts_of[p]) == nfacts[p], p
    claims = flat_claims(J)
    rep = {'inputs': {'judgments_sha256': sha(R96 / f'judging/judgments_E32_{ver}.json'), 'manifest_sha256': man['sha256'],
                      'sentence_review_sha256': sha(R96 / f'judging/sentence_review_{ver}.json'), 'eval_sha256': sha(__file__),
                      'sem_sha256': sha(ROOT / 'report96_sem.py'), 'ref_sha256': sha(ROOT / 'report96_ref.py')},
           'note': 'assistant가 조건명을 가린 O-id로 판정(영역 이름은 보임). 전문의 검토·독립 눈가림 아님. 이미 출력 일부를 본 개발 자료.',
           'n_patients': 32, 'strata': Counter(layer.values()), 'n_facts': sum(nfacts.values()), 'bundles': {}, 'compare': {}, 'cases': {}}
    rep['strata'] = dict(rep['strata'])
    out_by_bundle = {b: [o for o in J['outputs'] if BUNDLES[b](o['cond'], o['region'])] for b in BUNDLES}
    C = {b: {v: conflicts(claims, b, v) for v in VARIANTS} for b in BUNDLES}
    CC = {b: cause_conflicts(claims, b) for b in BUNDLES}
    RC = {b: recoveries(claims, b, facts_of) for b in BUNDLES}
    RCV = {'lobe_zone_equal': {b: recoveries(claims, b, facts_of, lz_equal=True) for b in BUNDLES},
           'excl_nonEOS': {b: recoveries(claims, b, facts_of, excl_noneos=True) for b in BUNDLES},
           'no_cause_assist': {b: recoveries(claims, b, facts_of, no_assist=True) for b in BUNDLES}}
    for b in BUNDLES:
        d = {'n_outputs': len(out_by_bundle[b]), 'non_eos_final': sum(not o['ended_eos'] for o in out_by_bundle[b]),
             'tokens_last_attempt': sum(o['n_new'] for o in out_by_bundle[b]), 'generation_seconds_sum': sum(o['runtime_s_sum'] for o in out_by_bundle[b]),
             'conflict_patients': {v: len(C[b][v]) for v in VARIANTS}, 'cause_conflict_patients_pneumonia': len(CC[b])}
        # 변형 합집합(상태별 분해): primary와 비-primary 쌍 상태
        stats = Counter()
        for v in ('primary',):
            for p, prs in C[b][v].items():
                stats['definite_pairs'] += len(prs)
        allp = conflicts_all_status(claims, b)
        d['pair_status_patients'] = {k: len({p for p, _ in v}) for k, v in allp.items()}
        for lv in LEVELS:
            rs = rec_set(RC[b], lv)
            d[f'facts_recovered_{lv}'] = len(rs)
            d[f'recall_{lv}'] = float(np.mean([len({f for pp, f in rs if pp == p}) / nfacts[p] for p in pos_idx]))
        d['recall_lenient_nonrecoverable_note'] = None
        d['error_cost'] = error_cost(claims, b, layer)
        d['error_cost_excl_nonEOS'] = error_cost(claims, b, layer, excl_noneos=True)
        rep['bundles'][b] = d
        rep['cases'][b] = {'conflicts': {str(p): [{'pos': pr[0]['cid'], 'neg': pr[1]['cid'], 'status': pr[2]} for pr in prs] for p, prs in C[b]['primary'].items()},
                           'recoveries': {str(p): {f: {k: v for k, v in dd.items() if v} for f, dd in fs.items()} for p, fs in RC[b].items()}}
    # ---- 회복 beyond / 환자×사실 비교
    def beyond(X, Y_list, lv, rcs=RC):
        base = set()
        for y in Y_list:
            base |= rec_set(rcs[y], lv)
        items = sorted(rec_set(rcs[X], lv) - base)
        return {'patients': len({p for p, _ in items}), 'facts': len(items), 'items': [list(i) for i in items]}
    detail = {}
    for tag, rcs in (('main', RC), ('lobe_zone_equal', RCV['lobe_zone_equal']), ('excl_nonEOS', RCV['excl_nonEOS']), ('no_cause_assist', RCV['no_cause_assist'])):
        e = {}
        for lv in LEVELS:
            t = {}
            for X in ('L8', 'D8', 'L6', 'D6', 'D2', 'L2'):
                t[f'{X}_beyond_CG'] = beyond(X, ['CG'], lv, rcs)
            t['D6_beyond_CG_D2'] = beyond('D6', ['CG', 'D2'], lv, rcs)
            t['L6_beyond_CG_L2'] = beyond('L6', ['CG', 'L2'], lv, rcs)
            t['D6_beyond_CG_D2_L2'] = beyond('D6', ['CG', 'D2', 'L2'], lv, rcs)
            t['D8_beyond_CG_L2'] = beyond('D8', ['CG', 'L2'], lv, rcs)
            base = {p for p, _ in rec_set(rcs['L8'], lv) - rec_set(rcs['CG'], lv)}
            for A in ('D8', 'D2', 'L2', 'D6'):
                keep = {p for p, _ in rec_set(rcs[A], lv) - rec_set(rcs['CG'], lv)}
                t[f'L8_extra_patients_lost_by_{A}'] = len(base - keep)
            e[lv] = t
        detail[tag] = e
    rep['detail'] = detail
    # ---- 원 계획 분기 (a)(b) 계산: 환자 수 기준
    def pats_beyond(X, Ys, lv, rcs):
        return {p for p, _ in rec_set(rcs[X], lv) - set().union(*[rec_set(rcs[y], lv) for y in Ys])}
    br = {}
    for tag, rcs in (('main', RC), ('lobe_zone_equal', RCV['lobe_zone_equal']), ('no_cause_assist', RCV['no_cause_assist']), ('excl_nonEOS', RCV['excl_nonEOS'])):
        t = {}
        for lv in ('strict', 'lenient_timeok'):
            t[lv] = {'a_describe_D6_beyond_CG_D2': sorted(pats_beyond('D6', ['CG', 'D2'], lv, rcs)),
                     'a_locate_L6_beyond_CG_L2': sorted(pats_beyond('L6', ['CG', 'L2'], lv, rcs))}
            for A in ('D8', 'D2', 'L2'):
                extra = pats_beyond('L8', ['CG'], lv, rcs)
                keep = pats_beyond(A, ['CG'], lv, rcs)
                # (b): L8의 추가 회복을 A도 회복(해당 환자)하면서 L8엔 충돌이 있고 A엔 없는 환자
                both = sorted(p for p in extra if p in keep and p in C['L8']['primary'] and p not in C[A]['primary'])
                t[lv]['b_%s_preserve_and_reduce' % A] = both
                t[lv]['b_%s_extra_preserved' % A] = sorted(extra & keep)
                t[lv]['b_%s_extra_lost' % A] = sorted(extra - keep)
        br[tag] = t
    rep['branches'] = br
    # ---- 환자 단위 4분면표: 회복(strict) x 충돌(primary)
    tabs = {}
    for b in ('CG', 'L2', 'D2', 'L8', 'D8', 'L6', 'D6'):
        for lv in ('strict', 'lenient_timeok'):
            rs = {p for p, _ in rec_set(RC[b], lv)}
            tab = Counter()
            for p in range(32):
                tab[('rec' if p in rs else 'norec') + '/' + ('conf' if p in C[b]['primary'] else 'noconf')] += 1
            tabs[f'{b}_{lv}'] = dict(tab)
    rep['patient_table'] = tabs
    # 회복한 동일 사실이 같은 번들 안에서 부정되는가
    neg_of_rec = {}
    for b in BUNDLES:
        lst = []
        for p, fs in RC[b].items():
            for f, dd in fs.items():
                cids = set(dd['strict'])
                for pr in C[b]['primary'].get(p, []):
                    if pr[0]['cid'] in cids:
                        lst.append([p, f, pr[0]['cid'], pr[1]['cid']])
        neg_of_rec[b] = lst
    rep['recovered_fact_negated_same_bundle'] = neg_of_rec
    # ---- 충돌 감소 / paired bootstrap
    cmp = {}
    for v in VARIANTS:
        cmp[v] = {}
        base = {p: int(p in C['L8'][v]) for p in range(32)}
        for A in ('D8', 'D2', 'L2', 'CG'):
            cur = {p: int(p in C[A][v]) for p in range(32)}
            cmp[v][f'L8_minus_{A}_patients'] = sum(base.values()) - sum(cur.values())
        for X, Y in (('D8', 'L8'), ('D2', 'L2'), ('D8', 'D2'), ('L8', 'L2'), ('D8', 'CG'), ('L8', 'CG'), ('D6', 'L6')):
            cmp[v][f'{X}-{Y}'] = boot([int(p in C[X][v]) for p in range(32)], [int(p in C[Y][v]) for p in range(32)])
    rep['compare']['conflict'] = cmp
    for lv in ('strict', 'lenient_timeok'):
        for X, Y in (('D8', 'L8'), ('D2', 'L2'), ('D8', 'D2'), ('L8', 'L2'), ('D8', 'CG'), ('L8', 'CG'), ('D6', 'L6')):
            fn = lambda B: [len({f for pp, f in rec_set(RC[B], lv) if pp == p}) / nfacts[p] for p in pos_idx]
            rep['compare'][f'recall_{lv}_{X}-{Y}'] = boot(fn(X), fn(Y))
    # ---- 환자 제거 민감도: D6 세부 전용 회복 환자, 충돌 환자
    loo = {}
    for lv in ('strict', 'lenient_timeok'):
        items = beyond('D6', ['CG', 'D2'], lv)['items']
        pp = sorted({p for p, _ in items})
        loo[f'D6_detail_only_{lv}'] = {'patients': pp, 'min_after_drop_one': min([len(set(pp) - {q}) for q in pp] or [0])}
    for b in ('D6', 'D8', 'L8'):
        cp = sorted(C[b]['primary'])
        loo[f'{b}_conflict_patients_primary'] = {'patients': cp, 'n': len(cp), 'min_after_drop_one': min([len(set(cp) - {q}) for q in cp] or [0])}
    rep['leave_one_patient_out'] = loo
    # ---- 형식
    rep['describe_spontaneous_coordinate_outputs_D8'] = sum(1 for o in J['outputs'] if o['cond'] == 'D' and False)
    rep['non_eos_final_outputs'] = [[o['p'], o['oid'], o['cond'], o['region']] for o in J['outputs'] if not o['ended_eos']]
    save(R96 / f'eval/report_E32_{ver}{rtag}.json', rep)
    brief = {b: dict(conf=rep['bundles'][b]['conflict_patients']['primary'], rec_s=rep['bundles'][b]['facts_recovered_strict'], rec_l=rep['bundles'][b]['facts_recovered_lenient']) for b in BUNDLES}
    print(json.dumps(brief))


def conflicts_all_status(claims, b):
    out = {'definite': [], 'uncertain_scope': [], 'qualified': [], 'hedged_pos': []}
    cs = [c for c in claims if in_bundle(b, c)]
    for p in [c for c in cs if c['pol'] == 'P']:
        for n in [c for c in cs if c['pol'] == 'N' and c['p'] == p['p']]:
            st = pair_status(p, n, 'question')
            if st:
                out[st].append((p['p'], (p['cid'], n['cid'])))
    return out


if __name__ == '__main__':
    {'judge': judge, 'eval': evaluate}[sys.argv[1]](*sys.argv[2:])
