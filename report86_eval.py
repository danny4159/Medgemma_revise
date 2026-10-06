"""iter_086 의미 판정표 평가기(CPU). 입력: 잠긴 reference 사실, 판독 산출물, 눈가림 key, 판정 파일(DSL).
python report86_eval.py <stage> <judgments.txt> <out_dir>
판정 DSL(semantic_protocol.md):  P### 줄 다음에  O#: F1=D+:"span" F2=U ... ; C=<d:F4,p:F4|-> ; I=<0|1> ; xd=<n> xp=<n>
지표(환자 단위): 확정 recall(D/#pos_def), 엄격 recall(D이고 위치 표기 '-' 아님), possible 포함 recall, 모순 3성분,
내부 모순, 추가 주장 수, 표현 정보. 주 비교는 환자 단위 paired bootstrap(10,000회, seed 84017).
"""
import json
import re
import sys
from pathlib import Path

import numpy as np

from report86_common import R86, STAGES, R85, save, sha
import report86_facts as F
from report86_view import CONDS, blind_order, load as load_stage

POS_CLASSES = ('pos_def', 'pos_hedged', 'pos_temporal', 'pos_ambiguous')
COMPARISONS = [('B0-R', 'M15-R'), ('M15-S', 'M15-R'), ('B0-S', 'M15-S'), ('C-G', 'M1-G'), ('C-H', 'C-G')]
SEED = 84017
NBOOT = 10000
FACT_RE = re.compile(r'F(\d+)=([DPNU])([+\-~]?)(?::"([^"]*)")?')


class JudgmentError(ValueError):
    pass


def parse_judgments(text, rows, refs, subset=False):
    """returns {ImageID: {condition: record}}. 형식·ID·완전성 위반은 JudgmentError."""
    out, cur, seen_p = {}, None, set()
    for ln_no, raw in enumerate(text.splitlines(), 1):
        ln = raw.strip()
        if not ln or ln.startswith('#'):
            continue
        m = re.fullmatch(r'P(\d{3})', ln)
        if m:
            idx = int(m.group(1))
            if idx >= len(rows) or idx in seen_p:
                raise JudgmentError(f'line {ln_no}: bad or duplicate patient {ln}')
            seen_p.add(idx)
            cur = rows[idx]['ImageID']
            out[cur] = {}
            order = blind_order(cur)
            continue
        m = re.match(r'O(\d):\s*(.*)', ln)
        if not m or cur is None:
            raise JudgmentError(f'line {ln_no}: cannot parse {ln[:60]}')
        oi = int(m.group(1))
        if not 1 <= oi <= 8:
            raise JudgmentError(f'line {ln_no}: output id')
        cond = order[oi - 1]
        if cond in out[cur]:
            raise JudgmentError(f'line {ln_no}: duplicate output {oi}')
        parts = [p.strip() for p in re.split(r'\s;\s', m.group(2))]
        if len(parts) != 4:
            raise JudgmentError(f'line {ln_no}: expected 4 ;-separated sections, got {len(parts)}')
        facts_txt, c_txt, i_txt, x_txt = parts
        if facts_txt.strip() == '-':  # positive 사실이 없는 환자
            facts_txt = ''
        facts = {}
        consumed = 0
        for fm in FACT_RE.finditer(facts_txt):
            fid = f'F{fm.group(1)}'
            if fid in facts:
                raise JudgmentError(f'line {ln_no}: duplicate {fid}')
            suffix = fm.group(3)
            if fm.group(2) in 'NU' and suffix:
                raise JudgmentError(f'line {ln_no}: suffix on {fm.group(2)}')
            if fm.group(2) in 'DPN' and not fm.group(4):
                raise JudgmentError(f'line {ln_no}: {fid} needs an evidence span')
            facts[fid] = {'s': fm.group(2), 'loc': suffix, 'span': fm.group(4)}
            consumed += 1
        if consumed != len(re.findall(r'F\d+=', facts_txt)):
            raise JudgmentError(f'line {ln_no}: malformed fact token')
        pos_ids = {x['fact_id'] for x in refs[cur]['facts'] if x['fact_class'] in POS_CLASSES}
        if set(facts) != pos_ids:
            raise JudgmentError(f'line {ln_no}: facts judged {sorted(facts)} != required {sorted(pos_ids)}')
        neg_ids = {x['fact_id'] for x in refs[cur]['facts'] if x['fact_class'] == 'neg_specific'}
        contra = []
        if c_txt != 'C=-':
            if not c_txt.startswith('C='):
                raise JudgmentError(f'line {ln_no}: C section')
            for it in c_txt[2:].split(','):
                mm = re.fullmatch(r'([dp]):(F\d+)', it.strip())
                if not mm or mm.group(2) not in neg_ids:
                    raise JudgmentError(f'line {ln_no}: contradiction item {it} (must cite a neg_specific fact {sorted(neg_ids)})')
                contra.append({'strength': mm.group(1), 'fact': mm.group(2)})
        mi = re.fullmatch(r'I=([01])', i_txt)
        mx = re.fullmatch(r'xd=(\d+) xp=(\d+)', x_txt)
        if not mi or not mx:
            raise JudgmentError(f'line {ln_no}: I/x section')
        out[cur][cond] = {'facts': facts, 'contra': contra, 'internal': int(mi.group(1)), 'xd': int(mx.group(1)), 'xp': int(mx.group(2))}
    if not subset and seen_p != set(range(len(rows))):
        raise JudgmentError(f'patients judged {len(seen_p)} != {len(rows)}')
    for img, d in out.items():
        if set(d) != set(CONDS):
            raise JudgmentError(f'{img}: outputs {sorted(d)}')
    return out


def per_output(img, cond, j, refs, reads):
    facts = {x['fact_id']: x for x in refs[img]['facts']}
    cls = lambda c: [fid for fid, x in facts.items() if x['fact_class'] == c]
    pd = cls('pos_def')
    n = len(pd)
    st = {fid: j['facts'][fid] for fid in j['facts']}
    D = sum(st[f]['s'] == 'D' for f in pd)
    P = sum(st[f]['s'] == 'P' for f in pd)
    N = sum(st[f]['s'] == 'N' for f in pd)
    U = sum(st[f]['s'] == 'U' for f in pd)
    Ds = sum(st[f]['s'] == 'D' and st[f]['loc'] in ('', '+') for f in pd)
    Dwrong = sum(st[f]['s'] == 'D' and st[f]['loc'] == '-' for f in pd)
    wide = [f for f in cls('pos_def') + cls('pos_hedged') + cls('pos_temporal')]
    ca_d = sum(c['strength'] == 'd' for c in j['contra'])
    ca_p = sum(c['strength'] == 'p' for c in j['contra'])
    n_neg = len(cls('neg_specific'))
    S = sum(st[f]['s'] in 'DP' for f in st)
    cc = Dwrong
    rec = reads[(img, cond)]
    return {'n_pos_def': n, 'n_neg_specific': n_neg, 'D': D, 'P': P, 'N': N, 'U': U, 'D_strict': Ds, 'D_wrongloc': Dwrong,
            'recall_def': D / n if n else None, 'recall_strict': Ds / n if n else None, 'recall_incl_possible': (D + P) / n if n else None,
            'recall_wide_D': (sum(st[f]['s'] == 'D' for f in wide) / len(wide)) if wide else None,
            'contra_a_def': ca_d, 'contra_a_poss': ca_p, 'contra_b_neg_of_positive': N, 'contra_c_wrong_loc': cc,
            'contra_primary': (int(ca_d > 0 or N > 0 or cc > 0) if (n or n_neg) else None),
            'contra_a_only': (int(ca_d > 0) if n_neg else None),
            'internal': j['internal'], 'xd': j['xd'], 'xp': j['xp'],
            'claims_supported': S, 'claims_contradicted': ca_d + ca_p + cc, 'claims_unverifiable': j['xd'] + j['xp'],
            'n_tokens': rec['n_tokens'], 'final_non_eos': int(not all(rec['final_eos'])), 'n_requests': len(rec['request_ids']),
            'n_attempts': rec['n_attempts']}


def boot_ci(diffs, rng, nboot=NBOOT):
    d = np.asarray(diffs, float)
    idx = rng.integers(0, len(d), size=(nboot, len(d)))
    m = d[idx].mean(axis=1)
    return [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]


def evaluate(stage, jtext, out_dir=None):
    rows, reads, refs = load_stage(stage)
    jud = parse_judgments(jtext, rows, refs)
    strata = {r['ImageID']: r.get('stratum', 'D8') for r in rows}
    per = {}
    for img in jud:
        for c in CONDS:
            per[(img, c)] = per_output(img, c, jud[img][c], refs, reads)
    metrics = ['recall_def', 'recall_strict', 'recall_incl_possible', 'recall_wide_D', 'contra_primary', 'contra_a_only', 'internal', 'xd', 'xp']
    sets = {'all': list(strata)}
    for s in sorted(set(strata.values())):
        sets[s] = [i for i in strata if strata[i] == s]
    rng = np.random.default_rng(SEED)
    summary = {}
    for sname, imgs in sets.items():
        summary[sname] = {'n_patients': len(imgs), 'conditions': {}}
        for c in CONDS:
            sub = [per[(i, c)] for i in imgs]
            agg = {}
            for m in metrics:
                vals = [x[m] for x in sub if x[m] is not None]
                agg[m] = {'mean': float(np.mean(vals)) if vals else None, 'n': len(vals)}
            S = sum(x['claims_supported'] for x in sub)
            Cc = sum(x['claims_contradicted'] for x in sub)
            V = sum(x['claims_unverifiable'] for x in sub)
            agg['claims'] = {'supported': S, 'contradicted': Cc, 'unverifiable': V, 'precision_lower': S / (S + Cc + V) if S + Cc + V else None,
                             'precision_upper': (S + V) / (S + Cc + V) if S + Cc + V else None, 'note': 'unverifiable를 전부 틀림/맞음으로 둔 범위; 임상 precision 아님'}
            agg['status_counts_pos_def'] = {k: sum(x[k] for x in sub) for k in ('D', 'P', 'N', 'U', 'D_strict', 'D_wrongloc', 'n_pos_def')}
            agg['contra_components_patients'] = {'a_def': sum(x['contra_a_def'] > 0 for x in sub), 'a_poss': sum(x['contra_a_poss'] > 0 for x in sub),
                                                  'b_neg_of_positive': sum(x['contra_b_neg_of_positive'] > 0 for x in sub), 'c_wrong_loc': sum(x['contra_c_wrong_loc'] > 0 for x in sub)}
            agg['final_non_eos_outputs'] = sum(x['final_non_eos'] for x in sub)
            agg['tokens_mean'] = float(np.mean([x['n_tokens'] for x in sub]))
            agg['requests_total'] = sum(x['n_requests'] for x in sub)
            agg['attempts_total'] = sum(x['n_attempts'] for x in sub)
            summary[sname]['conditions'][c] = agg
    comps = {}
    for sname, imgs in sets.items():
        comps[sname] = {}
        for a, b in COMPARISONS:
            res = {}
            for m in metrics:
                pairs = [(per[(i, a)][m], per[(i, b)][m]) for i in imgs if per[(i, a)][m] is not None and per[(i, b)][m] is not None]
                if not pairs:
                    res[m] = None
                    continue
                d = [x - y for x, y in pairs]
                res[m] = {'diff': float(np.mean(d)), 'ci95': boot_ci(d, rng) if len(d) > 1 else None, 'n': len(d)}
            comps[sname][f'{a}-{b}'] = res
    both = [i for i in strata if per[(i, 'M15-R')]['n_pos_def'] and per[(i, 'M15-R')]['n_neg_specific']]
    result = {'stage': stage, 'summary': summary, 'comparisons': comps, 'bootstrap': {'n': NBOOT, 'seed': SEED, 'unit': 'patient (paired, within stratum set)'},
              'operating_point_patients_with_pos_def_and_neg_specific': len(both),
              'judgments_sha256': None, 'per_output': {f'{i}|{c}': v for (i, c), v in per.items()}}
    return result


def main():
    stage, jpath, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    jtext = Path(jpath).read_text()
    res = evaluate(stage, jtext)
    res['judgments_sha256'] = sha(jpath)
    res['inputs'] = {'readings_sha256': sha(R86 / stage / 'readings.jsonl'), 'blind_key_sha256': sha(R86 / stage / 'blind_key_private.json') if (R86 / stage / 'blind_key_private.json').exists() else None,
                     'facts_rules_sha256': F.rules_sha(), 'eval_code_sha256': sha(__file__)}
    out.mkdir(parents=True, exist_ok=True)
    save(out / 'report.json', res)
    s = res['summary']
    for sname in s:
        print(sname, s[sname]['n_patients'])
        for c, a in s[sname]['conditions'].items():
            print(f"  {c:6s} recall_def={a['recall_def']['mean']} strict={a['recall_strict']['mean']} contra={a['contra_primary']['mean']} internal={a['internal']['mean']:.2f} xd={a['xd']['mean']:.2f} xp={a['xp']['mean']:.2f} tok={a['tokens_mean']:.0f}")


if __name__ == '__main__':
    main()
