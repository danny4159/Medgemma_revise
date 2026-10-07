"""iter_087 의미 평가기(CPU). 규약: results/iter_087/semantic_protocol_v2.md. 입력: reference 보완(reference_amend_E96.json),
판독 산출물(iter_086 readings.jsonl, 읽기 전용), 눈가림 key, v3 판정 파일(f/c/nf/i 줄), v1 판정(변경 이력 대조용).
python report87_eval.py <judgments_v3.txt> <out_dir> [--subset]
누락·중복·상호 배타성 위반·anchor 불일치·v1 변경 사유 누락은 JudgmentError로 중단한다(점수 계산 계속하지 않는다).
"""
import json
import re
import shlex
import sys
from pathlib import Path

import numpy as np

from report86_common import R86, ROOT, save, sha
import report86_eval as E1
from report86_view import CONDS, blind_order, clean, load as load_v1

R87 = ROOT / 'results/iter_087'
SEED = 84017
NBOOT = 10000
KEPT = ('pos_def', 'pos_hedged', 'pos_temporal', 'pos_ambiguous')
LOCC, ATTRC = 'mcoan', 'mcoan'
CLS_OK = {'S', 'U', 'C.neg', 'C.pos', 'C.loc', 'C.attr', 'C.locattr'}
POLCERT = {'+d', '+p', '-d', '-p'}
COMPARISONS = E1.COMPARISONS
V1LOC = {'+': 'm', '-': 'c', '~': 'o', '': 'n'}


class JudgmentError(ValueError):
    pass


def load_amend():
    return json.loads((R87 / 'reference_amend_E96.json').read_text())['patients']


def ch_groups(rec):
    """C-H 영역 출력: report86_view.render_ch와 같은 묶음. returns ({k: [seg idx]}, G idx, per-seg source)"""
    groups, order, gidx, srcs = {}, [], None, []
    for i, s in enumerate(rec['segments']):
        src = s['source'].split('|')[1]
        srcs.append(src)
        if src == 'G':
            gidx = i
            continue
        t = clean(s['text'])
        t = re.sub(r'^Location of the [^:]*:\s*\.?\s*', '', t)
        t = re.sub(r'^Description:\s*', '', t)
        t = t.replace('Description:', '').strip()
        if t not in groups:
            groups[t] = []
            order.append(t)
        groups[t].append(i)
    return [groups[t] for t in order], gidx, srcs


def locate(rec, cond, anchor, at):
    """anchor('a||b'는 같은 사실의 서로 다른 문구) 원문 위치. returns (n_units, occurrences). C-H는 @ 필수, 그 외는 @ 금지."""
    if '||' in anchor:
        occ_all, n_u = [], None
        for a in anchor.split('||'):
            n_u, o = locate(rec, cond, a, at)
            occ_all += [dict(x, anchor=a) for x in o]
        return n_u, occ_all
    if cond == 'C-H':
        if not at:
            raise JudgmentError('C-H claim needs @L<k>/@G/@r:<region>')
        groups, gidx, srcs = ch_groups(rec)
        if at == '@G':
            segs = [gidx]
        elif at.startswith('@L'):
            k = int(at[2:])
            if not 1 <= k <= len(groups):
                raise JudgmentError(f'bad group {at} (n={len(groups)})')
            segs = groups[k - 1]
        elif at.startswith('@r:'):
            segs = [i for i, s in enumerate(srcs) if s == at[3:]]
            if not segs:
                raise JudgmentError(f'no region {at}')
        else:
            raise JudgmentError(f'bad @ {at}')
        occ = []
        for i in segs:
            t = rec['segments'][i]['text']
            p = t.find(anchor)
            if p < 0:
                raise JudgmentError(f'anchor not in segment {srcs[i]}: {anchor!r}')
            starts = [m.start() for m in re.finditer(re.escape(anchor), t)]
            occ.append({'seg': i, 'source': srcs[i], 'starts': starts})
        return len(segs), occ
    if at:
        raise JudgmentError(f'@ not allowed for {cond}')
    t = rec['text']
    starts = [m.start() for m in re.finditer(re.escape(anchor), t)]
    if not starts:
        raise JudgmentError(f'anchor not found: {anchor!r}')
    return 1, [{'seg': 0, 'source': 'text', 'starts': starts}]


def split_note(tokens):
    if '--' in tokens:
        i = tokens.index('--')
        return tokens[:i], ' '.join(tokens[i + 1:])
    return tokens, ''


def parse_patient_outputs(lines, ctx, img, reads, rows_amend, v1j):
    """lines: [(ln_no, raw)] of a patient block. returns {cond: output}"""
    order = blind_order(img)
    facts_def = {f['fact_id']: f for f in rows_amend[img]['facts']}
    pos_ids = {fid for fid, f in facts_def.items() if f['v1_class'] in KEPT}
    out, cur, curc = {}, None, None
    n_line_err = 0
    for ln_no, raw in lines:
        try:
            toks = shlex.split(raw.strip())
        except ValueError as e:
            raise JudgmentError(f'line {ln_no}: shlex {e}')
        if not toks:
            continue
        m = re.fullmatch(r'O([1-8])', toks[0])
        if m and len(toks) == 1:
            cond = order[int(m.group(1)) - 1]
            if cond in out:
                raise JudgmentError(f'line {ln_no}: duplicate output {toks[0]}')
            out[cond] = {'facts': {}, 'claims': [], 'nf': [], 'internal': [], 'cond': cond, 'oid': toks[0]}
            curc, cur = cond, out[cond]
            continue
        if cur is None:
            raise JudgmentError(f'line {ln_no}: line before output header')
        rec = reads[(img, curc)]
        kind = toks[0]
        toks, note = split_note(toks)
        try:
            if kind == 'f':
                fid, st = toks[1], toks[2]
                if fid not in pos_ids or fid in cur['facts']:
                    raise JudgmentError(f'bad/duplicate fact {fid}')
                f = facts_def[fid]
                ent = {'s': st, 'loc': None, 'attr': None, 'span': None, 'co': None, 'why': note}
                if st == 'U':
                    rest = toks[3:]
                    if rest:
                        raise JudgmentError('U takes no extra tokens')
                elif st in ('D', 'P'):
                    ent['loc'], ent['attr'], ent['span'] = toks[3], toks[4], toks[5]
                    rest = toks[6:]
                    if ent['loc'] not in LOCC or ent['attr'] not in ATTRC:
                        raise JudgmentError('loc/attr code')
                    need_loc = bool(f['loc_req'])
                    hard_attr = [a for a in f['attr_req'] if not a.startswith('?')]
                    if need_loc == (ent['loc'] == 'n'):
                        raise JudgmentError(f'loc code {ent["loc"]} vs loc_req {f["loc_req"]}')
                    if not f['attr_req'] and ent['attr'] != 'n':
                        raise JudgmentError('attr must be n (no attr_req)')
                    if f['attr_req'] and ent['attr'] == 'n' and hard_attr:
                        raise JudgmentError('attr n but attr_req present')
                    if f['attr_req'] and not hard_attr and ent['attr'] == 'o':
                        raise JudgmentError('only hedged attr_req: use n instead of o')
                elif st in ('N', 'n'):
                    ent['span'] = toks[3]
                    rest = toks[4:]
                else:
                    raise JudgmentError(f'status {st}')
                if rest:
                    if len(rest) not in (2, 3) or rest[0] != '+' or rest[1] not in ('N', 'D', 'P', 'n'):
                        raise JudgmentError('bad secondary evidence')
                    ent['co'] = {'s': rest[1], 'span': rest[2] if len(rest) > 2 else None}
                if st in ('D', 'P', 'N', 'n') and curc != 'C-H' and ent['span'] not in rec['text']:
                    raise JudgmentError(f'span not found {ent["span"]!r}')
                if st in ('D', 'P', 'N', 'n') and curc == 'C-H' and not any(ent['span'] in s['text'] for s in rec['segments']):
                    raise JudgmentError(f'span not in any segment {ent["span"]!r}')
                cur['facts'][fid] = ent
            elif kind == 'c':
                cls, ref, pc, anchor = toks[1], toks[2], toks[3], toks[4]
                at = toks[5] if len(toks) > 5 else None
                if len(toks) > 6:
                    raise JudgmentError('extra tokens in c line')
                if cls not in CLS_OK or pc not in POLCERT:
                    raise JudgmentError(f'cls/polcert {cls} {pc}')
                refs = [] if ref == '-' else ref.split(',')
                for r in refs:
                    if r not in facts_def:
                        raise JudgmentError(f'unknown ref {r}')
                if cls == 'S' and not refs:
                    raise JudgmentError('S needs ref')
                if cls.startswith('C.') and not refs:
                    raise JudgmentError('C needs ref')
                if cls in ('C.neg',) and (pc[0] != '+' or not all(facts_def[r]['v2_class'] in ('neg_specific', 'normal_scoped') for r in refs)):
                    raise JudgmentError('C.neg needs + claim and neg_specific/normal_scoped refs')
                if cls == 'C.pos' and (pc[0] != '-' or not all(facts_def[r]['v1_class'] in KEPT for r in refs)):
                    raise JudgmentError('C.pos needs - claim and positive refs')
                if cls in ('C.loc', 'C.attr', 'C.locattr') and (pc[0] != '+' or not all(facts_def[r]['v1_class'] in KEPT for r in refs)):
                    raise JudgmentError('C.loc/attr needs + claim and positive refs')
                n_units, occ = locate(rec, curc, anchor, at)
                cur['claims'].append({'cls': cls, 'refs': refs, 'pol': pc[0], 'cert': pc[1], 'anchor': anchor, 'at': at, 'n': n_units,
                                      'occ': occ, 'note': note})
            elif kind == 'nf':
                n_units, occ = locate(rec, curc, toks[1], toks[2] if len(toks) > 2 else None)
                cur['nf'].append({'anchor': toks[1], 'n': n_units})
            elif kind == 'i':
                strength, dim = toks[1], toks[2]
                if strength not in ('d', 'p') or dim not in ('presence', 'location', 'attribute'):
                    raise JudgmentError('i strength/dim')
                rest = toks[3:]
                parts, j = [], 0
                while j < len(rest):
                    a = rest[j]
                    at = None
                    if j + 1 < len(rest) and rest[j + 1].startswith('@'):
                        at = rest[j + 1]
                        j += 1
                    j += 1
                    _, occ = locate(rec, curc, a, at)
                    parts.append({'anchor': a, 'at': at, 'occ': occ})
                if len(parts) != 2:
                    raise JudgmentError('i needs two anchors')
                cur['internal'].append({'strength': strength, 'dim': dim, 'parts': parts, 'note': note})
            else:
                raise JudgmentError(f'unknown line kind {kind}')
        except IndexError:
            msg = f'line {ln_no}: missing token ({raw.strip()[:70]})'
            if ctx is None:
                raise JudgmentError(msg)
            ctx.append(msg)
            n_line_err += 1
        except JudgmentError as e:
            msg = f'line {ln_no}: {e} :: {raw.strip()[:90]}'
            if ctx is None:
                raise JudgmentError(msg)
            ctx.append(msg)
            n_line_err += 1
    if n_line_err:
        return out
    if set(out) != set(CONDS):
        raise JudgmentError(f'{img[:8]}: outputs {sorted(out)}')
    # 출력별 완전성·대응 검사
    for cond, o in out.items():
        if set(o['facts']) != pos_ids:
            raise JudgmentError(f'{img[:8]} {o["oid"]}: facts judged {sorted(o["facts"])} != required {sorted(pos_ids)}')
        for fid, ent in o['facts'].items():
            linked = [c for c in o['claims'] if fid in c['refs']]
            f = facts_def[fid]
            if ent['s'] in ('D', 'P'):
                if not linked:
                    raise JudgmentError(f'{img[:8]} {o["oid"]}: {fid} {ent["s"]} has no linked claim')
                kinds = {c['cls'] for c in linked}
                if ent['loc'] == 'c' and not (kinds & {'C.loc', 'C.locattr'}):
                    raise JudgmentError(f'{img[:8]} {o["oid"]}: {fid} loc conflict needs C.loc/C.locattr claim')
                if ent['attr'] == 'c' and not (kinds & {'C.attr', 'C.locattr'}):
                    raise JudgmentError(f'{img[:8]} {o["oid"]}: {fid} attr conflict needs C.attr/C.locattr claim')
                if ent['loc'] != 'c' and ent['attr'] != 'c' and kinds & {'C.loc', 'C.attr', 'C.locattr'}:
                    raise JudgmentError(f'{img[:8]} {o["oid"]}: {fid} no conflict but C.loc/attr claim')
                if ent['co'] and ent['co']['s'] in ('N', 'n') and 'C.pos' not in kinds:
                    raise JudgmentError(f'{img[:8]} {o["oid"]}: {fid} co-evidence N needs a C.pos claim')
                if ent['loc'] != 'c' and 'C.loc' in kinds or ent['attr'] != 'c' and 'C.attr' in kinds:
                    raise JudgmentError(f'{img[:8]} {o["oid"]}: {fid} claim kind vs code mismatch')
            elif ent['s'] in ('N', 'n'):
                pc = [c for c in linked if c['cls'] == 'C.pos']
                if not pc:
                    raise JudgmentError(f'{img[:8]} {o["oid"]}: {fid} {ent["s"]} needs C.pos claim')
                want = '-d' if ent['s'] == 'N' else '-p'
                if not any(c['pol'] + c['cert'] == want for c in pc):
                    raise JudgmentError(f'{img[:8]} {o["oid"]}: {fid} {ent["s"]} needs a {want} C.pos claim')
            else:
                if any(c['cls'] in ('C.pos', 'C.loc', 'C.attr', 'C.locattr') for c in linked):
                    raise JudgmentError(f'{img[:8]} {o["oid"]}: {fid} U but conflict claim')
        for c in o['claims']:
            for r in c['refs']:
                if c['cls'] in ('C.pos', 'C.loc', 'C.attr', 'C.locattr') and r in o['facts'] and o['facts'][r]['s'] == 'U':
                    raise JudgmentError(f'{img[:8]} {o["oid"]}: claim refs U fact {r}')
        # v1 대비 변경은 사유 필요
        v1 = v1j.get(img, {}).get(cond) if v1j else None
        if v1:
            for fid, ent in o['facts'].items():
                a = v1['facts'][fid]
                s1 = a['s']
                changed = s1 != ent['s'] and not (s1 == 'U' and ent['s'] == 'n')  # 약화된 정상(n)은 v1에서 U였던 규칙 변경
                if ent['s'] in ('D', 'P') and s1 == ent['s'] and a['loc'] != '' and facts_def[fid]['loc_req'] and V1LOC[a['loc']] != ent['loc']:
                    changed = True
                if changed and not ent['why']:
                    msg = f'{img[:8]} {o["oid"]}: {fid} changed from v1 ({s1}{a["loc"]}) to {ent["s"]} without -- why'
                    if ctx is None:
                        raise JudgmentError(msg)
                    ctx.append(msg)
    return out


def parse_v3(text, rows, amend, reads, v1j=None, subset=False):
    blocks, cur = {}, None
    for ln_no, raw in enumerate(text.splitlines(), 1):
        s = raw.strip()
        if not s or s.startswith('#'):
            continue
        m = re.fullmatch(r'P(\d{3})', s)
        if m:
            idx = int(m.group(1))
            if idx >= len(rows) or idx in blocks:
                raise JudgmentError(f'line {ln_no}: bad/duplicate patient {s}')
            cur = idx
            blocks[idx] = []
            continue
        if cur is None:
            raise JudgmentError(f'line {ln_no}: before first patient')
        blocks[cur].append((ln_no, raw))
    if not subset and set(blocks) != set(range(len(rows))):
        raise JudgmentError(f'patients judged {len(blocks)} != {len(rows)}')
    missing = []
    res = {rows[i]['ImageID']: parse_patient_outputs(blocks[i], missing, rows[i]['ImageID'], reads, amend, v1j) for i in sorted(blocks)}
    if missing:
        raise JudgmentError('missing -- why for v1 changes:\n  ' + '\n  '.join(missing))
    return res


def per_output(img, cond, o, amend, reads):
    facts = {f['fact_id']: f for f in amend[img]['facts']}
    res = {}
    for den, key in (('v1', 'v1_class'), ('v2', 'v2_class')):
        pd = [fid for fid, f in facts.items() if f[key] == 'pos_def']
        st = {fid: o['facts'].get(fid) for fid in pd}
        # v2에서 P041 F2처럼 정정된 사실은 v1 pos_temporal이므로 판정은 f 줄에 있다.
        n = len(pd)
        D = sum(st[f]['s'] == 'D' for f in pd)
        P = sum(st[f]['s'] == 'P' for f in pd)
        Ds = sum(st[f]['s'] == 'D' and st[f]['loc'] in 'nm' and st[f]['attr'] in 'nm' for f in pd)
        res[den] = {'n': n, 'D': D, 'P': P, 'N': sum(st[f]['s'] == 'N' for f in pd), 'n_hedged': sum(st[f]['s'] == 'n' for f in pd),
                    'D_strict': Ds, 'loc_c': sum(st[f]['s'] in 'DP' and st[f]['loc'] == 'c' for f in pd),
                    'loc_o': sum(st[f]['s'] in 'DP' and st[f]['loc'] == 'o' for f in pd),
                    'attr_c': sum(st[f]['s'] in 'DP' and st[f]['attr'] == 'c' for f in pd),
                    'attr_o': sum(st[f]['s'] in 'DP' and st[f]['attr'] == 'o' for f in pd),
                    'recall_def': D / n if n else None, 'recall_strict': Ds / n if n else None, 'recall_incl_possible': (D + P) / n if n else None}
    wide = [fid for fid, f in facts.items() if f['v2_class'] in ('pos_def', 'pos_hedged', 'pos_temporal')]
    res['recall_wide_D'] = (sum(o['facts'][f]['s'] == 'D' for f in wide) / len(wide)) if wide else None
    # 주장 집계(영역 수 반영)
    S = {'d': 0, 'p': 0}
    C = {'d': 0, 'p': 0}
    U = {'d': 0, 'p': 0}
    comp = {k: 0 for k in ('neg_v1', 'neg_new', 'neg_new_weakonly', 'pos_neg', 'pos_neg_other', 'loc', 'attr', 'neg_v1_poss', 'pos_neg_poss')}
    tension = 0
    has_pos_ref = any(f['v1_class'] in KEPT for f in facts.values())
    for c in o['claims']:
        tgt = {'S': S, 'U': U}.get(c['cls'], C)
        tgt[c['cert']] += c['n']
        if 'generic_global_normal' in c['note'] and has_pos_ref:
            tension += c['n']
        if c['cls'] == 'C.neg':
            fs = [facts[r] for r in c['refs']]
            if c['cert'] == 'd':
                if any(f['v1_class'] == 'neg_specific' for f in fs):
                    comp['neg_v1'] += c['n']
                nonweak = [f for f in fs if f['v2_class'] == 'normal_scoped' and not f['weak']]
                if nonweak:
                    comp['neg_new'] += c['n']
                elif any(f['v2_class'] == 'normal_scoped' for f in fs) and not any(f['v1_class'] == 'neg_specific' for f in fs):
                    comp['neg_new_weakonly'] += c['n']
            elif any(f['v1_class'] == 'neg_specific' for f in fs):
                comp['neg_v1_poss'] += c['n']
        elif c['cls'] == 'C.pos':
            fs = [facts[r] for r in c['refs']]
            if c['cert'] == 'd':
                if any(f['v2_class'] == 'pos_def' for f in fs):
                    comp['pos_neg'] += c['n']
                else:
                    comp['pos_neg_other'] += c['n']
            else:
                comp['pos_neg_poss'] += c['n']
        elif c['cls'] in ('C.loc', 'C.locattr') and c['cert'] == 'd':
            comp['loc'] += c['n']
        if c['cls'] in ('C.attr', 'C.locattr') and c['cert'] == 'd':
            comp['attr'] += c['n']
    nS, nC, nU = sum(S.values()), sum(C.values()), sum(U.values())
    n_pos_v1 = sum(f['v1_class'] == 'pos_def' for f in facts.values())
    n_neg_v1 = sum(f['v1_class'] == 'neg_specific' for f in facts.values())
    n_norm = sum(f['v2_class'] == 'normal_scoped' for f in facts.values())
    comp_def = bool(n_pos_v1 or n_neg_v1)
    ext_def = bool(comp_def or n_norm)
    b = lambda x: int(x > 0)
    # v1 pos_def의 위치 충돌 / 부정 성분 (common scope)
    loc_v1 = sum(o['facts'][f]['s'] in 'DP' and o['facts'][f]['loc'] == 'c' and f in
                 {fid for fid, ff in facts.items() if ff['v1_class'] == 'pos_def'} for f in o['facts'])
    pos_neg_v1scope = sum(o['facts'][f]['s'] == 'N' for f in o['facts'] if facts[f]['v1_class'] == 'pos_def')
    common = b(comp['neg_v1'] + pos_neg_v1scope + loc_v1) if comp_def else None
    v2 = b(comp['neg_v1'] + comp['neg_new'] + comp['pos_neg'] + comp['loc'] + comp['attr']) if ext_def else None
    v2nw = b(comp['neg_v1'] + comp['pos_neg'] + comp['loc'] + comp['attr']) if ext_def else None
    res.update({'claims': {'S': nS, 'C': nC, 'U': nU, 'S_d': S['d'], 'S_p': S['p'], 'C_d': C['d'], 'C_p': C['p'], 'U_d': U['d'], 'U_p': U['p'],
                           'n_total': nS + nC + nU, 'nonfactual': sum(x['n'] for x in o['nf']), 'tension_global_normal': tension},
                'contra_components': comp, 'contra_common': common, 'contra_v2': v2, 'contra_v2_noweak': v2nw,
                'contra_neg_v1': b(comp['neg_v1']) if ext_def else None, 'contra_neg_new': b(comp['neg_new']) if ext_def else None,
                'contra_pos_neg': b(comp['pos_neg']) if ext_def else None, 'contra_loc': b(comp['loc']) if ext_def else None,
                'contra_attr': b(comp['attr']) if ext_def else None,
                'internal_d': len([x for x in o['internal'] if x['strength'] == 'd']), 'internal_p': len([x for x in o['internal'] if x['strength'] == 'p']),
                'co_evidence': sum(1 for e in o['facts'].values() if e['co']),
                'defined_common': comp_def, 'defined_extended': ext_def})
    r = reads[(img, cond)]
    res.update({'n_tokens': r['n_tokens'], 'final_non_eos': int(not all(r['final_eos'])), 'n_requests': len(r['request_ids']), 'n_attempts': r['n_attempts']})
    return res


def flat(p):
    """환자×조건 지표 dict(비교·bootstrap 대상)."""
    out = {}
    for den in ('v1', 'v2'):
        for m in ('recall_def', 'recall_strict', 'recall_incl_possible'):
            out[f'{m}_{den}'] = p[den][m]
        out[f'loc_c_{den}'] = p[den]['loc_c'] if p[den]['n'] else None
        out[f'attr_c_{den}'] = p[den]['attr_c'] if p[den]['n'] else None
    out['recall_wide_D'] = p['recall_wide_D']
    for k in ('contra_common', 'contra_v2', 'contra_v2_noweak', 'contra_neg_v1', 'contra_neg_new', 'contra_pos_neg', 'contra_loc', 'contra_attr'):
        out[k] = p[k]
    out['internal_d'] = int(p['internal_d'] > 0)
    out['internal_p'] = int(p['internal_p'] > 0)
    out['claims_S'], out['claims_C'], out['claims_U'] = p['claims']['S'], p['claims']['C'], p['claims']['U']
    out['claims_total'] = p['claims']['n_total']
    return out


def boot_ci(d, nboot=NBOOT):
    d = np.asarray(d, float)
    idx = np.random.default_rng(SEED).integers(0, len(d), size=(nboot, len(d)))
    m = d[idx].mean(axis=1)
    return [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]


def evaluate(jud, rows, amend, reads):
    strata = {r['ImageID']: r['stratum'] for r in rows}
    per = {(i, c): per_output(i, c, jud[i][c], amend, reads) for i in jud for c in CONDS}
    fl = {k: flat(v) for k, v in per.items()}
    metrics = list(next(iter(fl.values())).keys())
    sets = {'all': list(jud), 'abnormal': [i for i in jud if strata[i] == 'abnormal'], 'no_abnormal': [i for i in jud if strata[i] == 'no_abnormal']}
    summary, comps = {}, {}
    for sn, imgs in sets.items():
        summary[sn] = {'n_patients': len(imgs), 'conditions': {}}
        for c in CONDS:
            agg = {}
            for m in metrics:
                vals = [fl[(i, c)][m] for i in imgs if fl[(i, c)][m] is not None]
                agg[m] = {'mean': float(np.mean(vals)) if vals else None, 'n': len(vals)}
            cl = {k: sum(per[(i, c)]['claims'][k] for i in imgs) for k in ('S', 'C', 'U', 'S_d', 'S_p', 'C_d', 'C_p', 'U_d', 'U_p', 'n_total', 'nonfactual', 'tension_global_normal')}
            tot = cl['S'] + cl['C'] + cl['U']
            cl['precision_lower'] = cl['S'] / tot if tot else None
            cl['precision_upper'] = (cl['S'] + cl['U']) / tot if tot else None
            cl['coverage'] = (cl['S'] + cl['C']) / tot if tot else None
            td = cl['S_d'] + cl['C_d'] + cl['U_d']
            cl['precision_lower_definite'] = cl['S_d'] / td if td else None
            cl['precision_upper_definite'] = (cl['S_d'] + cl['U_d']) / td if td else None
            cl['patients_with_no_claim'] = sum(per[(i, c)]['claims']['n_total'] == 0 for i in imgs)
            agg['claims_total'] = cl
            comp = {k: sum(per[(i, c)]['contra_components'][k] for i in imgs) for k in per[(imgs[0], c)]['contra_components']}
            agg['contra_components_counts'] = comp
            agg['contra_components_patients'] = {k: sum(per[(i, c)]['contra_components'][k] > 0 for i in imgs) for k in comp}
            for den in ('v1', 'v2'):
                agg['status_counts_' + den] = {k: sum(per[(i, c)][den][k] for i in imgs) for k in ('n', 'D', 'P', 'N', 'n_hedged', 'D_strict', 'loc_c', 'loc_o', 'attr_c', 'attr_o')}
            agg['internal_counts'] = {'d': sum(per[(i, c)]['internal_d'] for i in imgs), 'p': sum(per[(i, c)]['internal_p'] for i in imgs)}
            agg['final_non_eos_outputs'] = sum(per[(i, c)]['final_non_eos'] for i in imgs)
            agg['requests_total'] = sum(per[(i, c)]['n_requests'] for i in imgs)
            agg['tokens_mean'] = float(np.mean([per[(i, c)]['n_tokens'] for i in imgs]))
            summary[sn]['conditions'][c] = agg
        comps[sn] = {}
        for a, b in COMPARISONS:
            res = {}
            for m in metrics:
                pr = [(fl[(i, a)][m], fl[(i, b)][m]) for i in imgs if fl[(i, a)][m] is not None and fl[(i, b)][m] is not None]
                if not pr:
                    res[m] = None
                    continue
                d = [x - y for x, y in pr]
                res[m] = {'diff': float(np.mean(d)), 'ci95': boot_ci(d) if len(d) > 1 else None, 'n': len(d)}
            comps[sn][f'{a}-{b}'] = res
    return {'summary': summary, 'comparisons': comps, 'bootstrap': {'n': NBOOT, 'seed': SEED, 'unit': 'patient paired, fresh rng(seed) per comparison-metric'},
            'per_output': {f'{i}|{c}': v for (i, c), v in per.items()}}


def serialize_judgments(jud):
    """claims/anchor 위치를 포함한 저장용 구조(원문 span·영역 출처 연결)."""
    out = {}
    for img, d in jud.items():
        out[img] = {c: {'facts': o['facts'], 'claims': o['claims'], 'nf': o['nf'], 'internal': o['internal']} for c, o in d.items()}
    return out


def run(jpaths, out_dir, subset=False):
    rows, reads, _ = load_v1('E96')
    amend = load_amend()
    v1refs = load_v1('E96')[2]
    v1j = E1.parse_judgments((R86 / 'E96/judgments_E96_v2.txt').read_text(), rows, v1refs)
    text = '\n'.join(Path(p).read_text() for p in jpaths)
    jud = parse_v3(text, rows, amend, reads, v1j, subset=subset)
    res = evaluate(jud, rows, amend, reads)
    res['inputs'] = {'judgments': {str(p): sha(p) for p in jpaths}, 'reference_amend_sha256': sha(R87 / 'reference_amend_E96.json'),
                     'protocol_v2_sha256': sha(R87 / 'semantic_protocol_v2.md'), 'readings_sha256': sha(R86 / 'E96/readings.jsonl'),
                     'eval_code_sha256': sha(__file__), 'subset': subset, 'n_patients': len(jud)}
    out_dir = Path(out_dir)
    save(out_dir / 'report.json', res)
    save(out_dir / 'judgments_structured.json', serialize_judgments(jud))
    return res


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    run(args[:-1], args[-1], subset='--subset' in sys.argv)
