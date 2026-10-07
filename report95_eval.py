"""iter_095 평가: 판정(judgments)·match 파일을 검증해 번들(CG/L2/D2/L8/D8/L6/D6)별 충돌·회복·오류 비용·비용을 계산한다.
독립 단위는 환자. 판정은 assistant가 조건명을 가린 출력 id로 작성(전문의 검토 아님). 결과는 새 파일에만 쓴다.
사용: python report95_eval.py E32 <out.json>  (E96이면 E32+E64 판정을 모두 합친다)"""
import json
import re
import sys

import numpy as np

import report95_common as C
import report95_view as V
from report95_common import R95, REGIONS, BROAD, DETAIL, save, sha

ZONES = ['RU', 'RM', 'RL', 'LU', 'LM', 'LL']
ALL6 = set(ZONES)
OPAC = {'opacity', 'infiltrate', 'consolidation'}
KINDS = OPAC | {'atelectasis', 'pneumonia', 'clear'}
REGION_SCOPE = {'left lung': {'LU', 'LM', 'LL'}, 'right lung': {'RU', 'RM', 'RL'}, 'left upper lung zone': {'LU'},
                'left mid lung zone': {'LM'}, 'left lower lung zone': {'LL'}, 'right upper lung zone': {'RU'},
                'right mid lung zone': {'RM'}, 'right lower lung zone': {'RL'}, 'G': set(ALL6)}
BUNDLES = {'CG': lambda c, r: c == 'G', 'L2': lambda c, r: c == 'L' and r in BROAD, 'D2': lambda c, r: c == 'D' and r in BROAD,
           'L8': lambda c, r: c == 'L' and r in REGIONS, 'D8': lambda c, r: c == 'D' and r in REGIONS,
           'L6': lambda c, r: c == 'L' and r in DETAIL, 'D6': lambda c, r: c == 'D' and r in DETAIL}
SEED = 95017
LINE = re.compile(r'^(O\d\d) \| (.+)$')


def parse_scope(tok, region, mode):
    """mode 'question': q -> 질문 영역, 'global': q -> 전체 폐. 반환 집합."""
    if tok == 'q' or (mode == 'narrow' and tok == 'B'):
        return set(REGION_SCOPE[region]) if mode in ('question', 'narrow') else set(ALL6)
    out = set()
    for t in tok.split(','):
        if t == 'B':
            out |= ALL6
        elif t in ('R', 'L'):
            out |= {z for z in ZONES if z[0] == t}
        else:
            assert t in ALL6, f'bad scope {tok}'
            out.add(t)
    return out


def load_judgments(stage_list):
    claims, outs_text, outs_meta = {}, {}, {}
    pidx = 0
    for st in stage_list:
        outs = V.outputs_for(st)
        text = (R95 / f'judging/judgments_{st}.txt').read_text().splitlines()
        cur, plist = None, list(outs)
        seen = {}
        for ln in text:
            if ln.startswith('## P'):
                cur = int(ln[4:])
                img = plist[cur]
                seen[img] = set()
                continue
            m = LINE.match(ln)
            if not m:
                continue
            oid, rest = m.groups()
            seen[img].add(oid)
            if rest.strip() == '-':
                continue
            pol, kind, scope, fl, quote = [x.strip() for x in rest.split(' | ', 4)]
            assert pol in ('P', 'Pu', 'N') and kind in KINDS, ln
            o = next(x for x in outs[img] if x['oid'] == oid)
            q = quote.strip('"')
            assert q in o['text'] or re.sub(r'^\d+\.\s*', '', q) in o['text'], f'quote not in output: {ln}'
            parse_scope(scope, o['region'], 'question')
            claims.setdefault((img, oid), []).append({'pol': pol, 'kind': kind, 'scope': scope, 'flags': fl, 'quote': q})
        for img, lst in outs.items():
            assert seen[img] == {x['oid'] for x in lst}, f'missing judged outputs for {img}'
            for x in lst:
                outs_meta[(img, x['oid'])] = x
        outs_text.update({img: lst for img, lst in outs.items()})
    return claims, outs_text, outs_meta


def load_matches(stage_list, outs_text, claims):
    out = []
    for st in stage_list:
        p = R95 / f'judging/matches_{st}.txt'
        if not p.exists():
            continue
        plist = list(V.outputs_for(st))
        for ln in p.read_text().splitlines():
            if not ln.startswith('M|'):
                continue
            f = ln.split('|')
            img = plist[int(f[1][1:])]
            key = (img, f[2])
            assert any(c['kind'] == f[3] and c['scope'] == f[4] and c['pol'] in ('P', 'Pu') for c in claims.get(key, [])), f'match without claim {ln}'
            assert f[6] in ('S', 'W')
            out.append({'img': img, 'oid': f[2], 'kind': f[3], 'scope': f[4], 'fact': f[5], 'grade': f[6], 'T': len(f) > 7 and f[7] == 'T'})
    return out


def bundle_outputs(outs_text):
    b = {k: {} for k in BUNDLES}
    for img, lst in outs_text.items():
        for x in lst:
            for k, fn in BUNDLES.items():
                if fn(x['cond'], x['region']):
                    b[k].setdefault(img, []).append(x)
    return b


def compatible(n, p, broad=False, noclear=False):
    if n['kind'] == 'pneumonia' or p['kind'] == 'pneumonia':
        return False
    if n['kind'] == 'clear':
        return (not noclear) and p['kind'] in OPAC | {'atelectasis'}
    if broad:
        return n['kind'] in OPAC and p['kind'] in OPAC
    return n['kind'] == p['kind'] or (n['kind'] == 'opacity' and p['kind'] in OPAC)


def conflicts(claims, bundle_outs, mode='question', use_pu=False, broad=False, noclear=False):
    """환자 -> 충돌 쌍 목록. 같은 번들 안의 positive(P[, Pu]) 와 negative가 범위 겹치고 종류 호환일 때."""
    res = {}
    for img, outs in bundle_outs.items():
        pos, neg = [], []
        for x in outs:
            for c in claims.get((img, x['oid']), []):
                sc = parse_scope(c['scope'], x['region'], mode)
                rec = {**c, 'sc': sc, 'oid': x['oid'], 'region': x['region']}
                if c['pol'] == 'N':
                    neg.append(rec)
                elif c['pol'] == 'P' or use_pu:
                    pos.append(rec)
        pairs = [(p['oid'], n['oid']) for p in pos for n in neg if p['sc'] & n['sc'] and compatible(n, p, broad, noclear)]
        res[img] = pairs
    return res


def recovery(bundle_outs, matches, facts_by_img, level, notime):
    """환자 -> 회복한 reference fact 집합."""
    rec = {}
    for img, outs in bundle_outs.items():
        oids = {x['oid'] for x in outs}
        got = set()
        for m in matches:
            if m['img'] != img or m['oid'] not in oids:
                continue
            if level == 'S' and m['grade'] != 'S':
                continue
            if notime and m['T']:
                continue
            got.add(m['fact'])
        rec[img] = got
    return rec


def neg_cover(sentence):
    s = sentence.lower()
    cov = set()
    if re.search(r'consolidat|condensat', s):
        cov.add('consolidation')
    if re.search(r'infiltrat', s):
        cov.add('infiltrate')
    if re.search(r'opacit', s):
        cov |= OPAC
    return cov


def boot(vals_a, vals_b, n=10000):
    rng = np.random.default_rng(SEED)
    d = np.asarray(vals_a, float) - np.asarray(vals_b, float)
    if len(d) == 0:
        return None
    idx = rng.integers(0, len(d), (n, len(d)))
    m = d[idx].mean(1)
    return {'mean': float(d.mean()), 'ci95': [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))], 'n': len(d)}


def main():
    stage = sys.argv[1]
    outp = sys.argv[2]
    stages = ['E32'] if stage == 'E32' else ['E32', 'E64']
    claims, outs_text, outs_meta = load_judgments(stages)
    matches = load_matches(stages, outs_text, claims)
    ref = json.loads((R95 / 'lock/reference_target.json').read_text())
    imgs = list(outs_text)
    facts = {i: [f['fact_id'] for f in ref[i]['pos_facts']] for i in imgs}
    layer = {i: ref[i]['layer'] for i in imgs}
    pos_imgs = [i for i in imgs if layer[i] == 'pos']
    B = bundle_outputs(outs_text)
    rep = {'stage': stage, 'n_patients': len(imgs), 'strata': {k: sum(layer[i] == k for i in imgs) for k in ('pos', 'neg', 'rest')},
           'n_match_lines': len(matches), 'bundles': {}, 'compare': {}, 'detail': {}}
    # ---- 충돌
    conf_variants = {'primary': dict(mode='question'), 'with_hedged': dict(mode='question', use_pu=True), 'global_q': dict(mode='global'),
                     'no_generic_clear': dict(mode='question', noclear=True), 'broad_kind': dict(mode='question', broad=True),
                     'narrow_generic_lungs': dict(mode='narrow')}
    conf = {b: {v: conflicts(claims, B[b], **kw) for v, kw in conf_variants.items()} for b in B}
    rec = {b: {(lv, nt): recovery(B[b], matches, facts, lv, nt) for lv in ('S', 'W') for nt in (False, True)} for b in B}
    nfact = sum(len(facts[i]) for i in pos_imgs)
    for b in B:
        d = {'n_requests': sum(len(v) for v in B[b].values()) , 'conflict_patients': {v: sum(bool(conf[b][v][i]) for i in imgs) for v in conf_variants}}
        for lv, nm in (('S', 'strict'), ('W', 'lenient')):
            for nt in (False, True):
                r = rec[b][(lv, nt)]
                d[f'recall_{nm}{"_notime" if nt else ""}'] = float(np.mean([len(r[i]) / len(facts[i]) for i in pos_imgs]))
                d[f'facts_recovered_{nm}{"_notime" if nt else ""}'] = sum(len(r[i]) for i in pos_imgs)
        # 비용 (생성 token / 초)
        toks = secs = 0
        for img, outs in B[b].items():
            for x in outs:
                at = x['rec']['attempts']
                toks += at[-1]['n_new']
                secs += sum(a['runtime_s'] for a in at)
        d['tokens_last_attempt'] = toks
        d['generation_seconds_sum'] = secs
        d['nonEOS_final'] = sum(not x['rec']['attempts'][-1]['ended_eos'] for outs in B[b].values() for x in outs)
        rep['bundles'][b] = d
    rep['facts_total'] = nfact
    # ---- 오류 비용 (claim 수준, 환자 수준)
    cov = {i: set().union(*[neg_cover(f['sentence']) for f in ref[i]['neg_facts'] if f['class'] == 'neg_specific']) if ref[i]['neg_facts'] else set() for i in imgs}
    matched = {(m['img'], m['oid'], m['kind'], m['scope']) for m in matches}
    for b in B:
        n = dict(pos_claims=0, matched=0, contradicted=0, unsupported=0, temporal_unsupported=0, causal_flag=0, nonref_pos_patients=0)
        pc, pt = set(), set()
        for img, outs in B[b].items():
            for x in outs:
                for c in claims.get((img, x['oid']), []):
                    if c['pol'] == 'N':
                        continue
                    n['pos_claims'] += 1
                    key = (img, x['oid'], c['kind'], c['scope'])
                    if key in matched:
                        n['matched'] += 1
                    elif c['kind'] in cov[img]:
                        n['contradicted'] += 1
                        pc.add(img)
                    else:
                        n['unsupported'] += 1
                        pt.add(img)
                        if 't' in c['flags']:
                            n['temporal_unsupported'] += 1
                    if 'c' in c['flags']:
                        n['causal_flag'] += 1
        n['patients_with_contradicted'] = len(pc)
        n['patients_with_unsupported'] = len(pt)
        rep['bundles'][b]['error_cost'] = n
    # ---- 회복 beyond 비교
    def beyond(X, Y_list, lv, nt):
        """X가 회복했으나 Y_list 어느 번들도 회복하지 못한 (환자,fact)와 환자."""
        pats, items = set(), []
        for i in pos_imgs:
            for f in rec[X][(lv, nt)][i]:
                if all(f not in rec[y][(lv, nt)][i] for y in Y_list):
                    pats.add(i)
                    items.append((i, f))
        return pats, items
    for lv, nm in (('S', 'strict'), ('W', 'lenient')):
        for nt in (False, True):
            tag = nm + ('_notime' if nt else '')
            e = {}
            for X in ('L8', 'D8', 'L6', 'D6', 'D2', 'L2'):
                p, it = beyond(X, ['CG'], lv, nt)
                e[f'{X}_beyond_CG'] = {'patients': len(p), 'facts': len(it), 'items': [[pos_imgs.index(i), f] for i, f in it]}
            p, it = beyond('D6', ['CG', 'D2'], lv, nt)
            e['D6_detail_only_vs_CG_D2'] = {'patients': len(p), 'facts': len(it), 'items': [[pos_imgs.index(i), f] for i, f in it]}
            p, it = beyond('D6', ['CG', 'D2', 'L2'], lv, nt)
            e['D6_detail_only_vs_CG_D2_L2'] = {'patients': len(p), 'facts': len(it)}
            p, it = beyond('L6', ['CG', 'L2'], lv, nt)
            e['L6_detail_only_vs_CG_L2'] = {'patients': len(p), 'facts': len(it)}
            # 단순 대안이 L8의 추가 회복을 보존하는가
            base = beyond('L8', ['CG'], lv, nt)[0]
            for A in ('D8', 'D2', 'L2'):
                keep = beyond(A, ['CG'], lv, nt)[0]
                e[f'lost_vs_L8_by_{A}'] = len(base - keep)
            rep['detail'][tag] = e
    # ---- 충돌 감소
    for v in conf_variants:
        rep['compare'][f'conflict_{v}'] = {}
        base = {i: bool(conf['L8'][v][i]) for i in imgs}
        for A in ('D8', 'D2', 'L2', 'CG'):
            cur = {i: bool(conf[A][v][i]) for i in imgs}
            rep['compare'][f'conflict_{v}'][f'L8_minus_{A}_patients'] = sum(base.values()) - sum(cur.values())
        for X, Y in (('D8', 'L8'), ('D2', 'L2'), ('D8', 'D2'), ('L8', 'L2'), ('D8', 'CG'), ('L8', 'CG')):
            rep['compare'][f'conflict_{v}'][f'{X}-{Y}_boot'] = boot([bool(conf[X][v][i]) for i in imgs], [bool(conf[Y][v][i]) for i in imgs])
    # ---- recall paired CI
    for lv, nm in (('S', 'strict'), ('W', 'lenient')):
        for X, Y in (('D8', 'L8'), ('D2', 'L2'), ('D8', 'D2'), ('L8', 'L2'), ('D8', 'CG'), ('L8', 'CG'), ('D6', 'L6')):
            rep['compare'][f'recall_{nm}_{X}-{Y}_boot'] = boot([len(rec[X][(lv, False)][i]) / len(facts[i]) for i in pos_imgs],
                                                               [len(rec[Y][(lv, False)][i]) / len(facts[i]) for i in pos_imgs])
    # ---- leave-one-patient-out: D6 detail-only 환자 수 (strict/lenient)
    loo = {}
    for lv, nm in (('S', 'strict'), ('W', 'lenient')):
        p, _ = beyond('D6', ['CG', 'D2'], lv, False)
        loo[nm] = {'n': len(p), 'min_after_drop_one': (len(p) - 1) if p else 0}
    rep['detail']['loo_D6_detail_only'] = loo
    # ---- 형식 관찰: Describe 좌표 자발 출력, 비EOS
    d_coord = sum(bool(re.search(r'\[\s*0?\.\d+\s*,', x['rec']['text'])) for outs in B['D8'].values() for x in outs)
    rep['describe_spontaneous_coords'] = d_coord
    rep['judgment_source'] = {'judgments_sha': {s: sha(R95 / f'judging/judgments_{s}.txt') for s in stages},
                              'matches_sha': {s: sha(R95 / f'judging/matches_{s}.txt') for s in stages if (R95 / f'judging/matches_{s}.txt').exists()},
                              'eval_sha': sha(__file__), 'view_sha': sha(V.__file__.replace('.pyc', '.py')),
                              'note': 'assistant 판정(조건명 제거 id), 전문의 검토 아님; reference 비교는 pos 환자 9명에서만 가능'}
    save(R95 / 'eval' / outp, rep)
    print(json.dumps({k: rep[k] for k in ('strata', 'facts_total')}), json.dumps({b: {kk: rep['bundles'][b][kk] for kk in ('conflict_patients', 'recall_strict', 'recall_lenient')} for b in B}))


if __name__ == '__main__':
    main()
