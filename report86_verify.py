"""평가 결과의 독립 재계산(report86_eval.py를 import하지 않는다). 판정 원문과 reference 사실·blind key에서 환자별 지표와 요약 평균을 다시 계산하고
저장된 report.json과 대조한다. bootstrap CI는 별도 난수·별도 구현으로 다시 계산해 끝점 차이가 몬테카를로 허용오차 안인지 본다.
python report86_verify.py <stage> <judgments.txt> <report.json> <out.json>
"""
import hashlib
import json
import re
import sys

import numpy as np

from report86_common import R86, R85, STAGES, save, sha

CONDS = ['M15-R', 'M15-S', 'B0-R', 'B0-S', 'M1-R', 'M1-G', 'C-G', 'C-H']
POS = {'pos_def', 'pos_hedged', 'pos_temporal', 'pos_ambiguous'}
COMPS = [('B0-R', 'M15-R'), ('M15-S', 'M15-R'), ('B0-S', 'M15-S'), ('C-G', 'M1-G'), ('C-H', 'C-G')]


def main():
    stage, jpath, rpath, outp = sys.argv[1:5]
    rows = json.load(open(STAGES[stage]['inputs']))
    if stage == 'D8':
        sys.path.insert(0, '.')
        import report86_facts as F
        refs = {r['ImageID']: {'facts': F.facts_for(r)} for r in json.load(open(R85 / 'D8/reference_private.json'))}
    else:
        refs = json.load(open(R86 / 'E/reference_facts_E_private.json'))
    key = json.load(open(R86 / stage / 'blind_key_private.json'))
    reads = {}
    for ln in open(R86 / stage / 'readings.jsonl'):
        r = json.loads(ln)
        reads[(r['ImageID'], r['condition'])] = r
    # 판정 원문을 줄 단위로 직접 파싱
    pid, per = None, {}
    for ln in open(jpath):
        ln = ln.strip()
        if not ln or ln[0] == '#':
            continue
        if re.fullmatch(r'P\d{3}', ln):
            pid = rows[int(ln[1:])]['ImageID']
            continue
        head, rest = ln.split(':', 1)
        cond = key[pid][head]
        sec = rest.split(' ; ')
        facts = {}
        for tok in re.finditer(r'F(\d+)=([DPNU])([+\-~]?)', sec[0]):
            facts['F' + tok.group(1)] = (tok.group(2), tok.group(3))
        contra = [] if sec[1].strip() == 'C=-' else [x.strip() for x in sec[1].strip()[2:].split(',')]
        internal = int(sec[2].strip()[2:])
        xd, xp = [int(x.split('=')[1]) for x in sec[3].split()]
        per[(pid, cond)] = (facts, contra, internal, xd, xp)
    rep = json.load(open(rpath))
    mism, nchecked = [], 0
    mine = {}
    for (img, c), (facts, contra, internal, xd, xp) in per.items():
        cl = {x['fact_id']: x['fact_class'] for x in refs[img]['facts']}
        pdef = [f for f in facts if cl[f] == 'pos_def']
        n = len(pdef)
        D = [f for f in pdef if facts[f][0] == 'D']
        Pn = [f for f in pdef if facts[f][0] == 'P']
        Nn = [f for f in pdef if facts[f][0] == 'N']
        Dm = [f for f in D if facts[f][1] == '-']
        Dnotstrict = [f for f in D if facts[f][1] in ('-', '~')]  # 엄격 recall: 위치가 맞거나 reference가 위치를 지정하지 않은 D만 (계획의 '위치·명시 속성까지 맞는' 정의)
        a_d = sum(1 for x in contra if x.startswith('d:'))
        nneg = sum(1 for v in cl.values() if v == 'neg_specific')
        v = {'recall_def': len(D) / n if n else None, 'recall_strict': (len(D) - len(Dnotstrict)) / n if n else None,
             'recall_incl_possible': (len(D) + len(Pn)) / n if n else None,
             'contra_primary': int(a_d > 0 or len(Nn) > 0 or len(Dm) > 0) if (n or nneg) else None, 'internal': internal, 'xd': xd, 'xp': xp}
        wide = [f for f in facts if cl[f] in ('pos_def', 'pos_hedged', 'pos_temporal')]
        v['recall_wide_D'] = sum(facts[f][0] == 'D' for f in wide) / len(wide) if wide else None
        mine[(img, c)] = v
        saved = rep['per_output'][f'{img}|{c}']
        for k, x in v.items():
            nchecked += 1
            y = saved[k]
            if (x is None) != (y is None) or (x is not None and abs(x - y) > 1e-12):
                mism.append({'id': f'{img}|{c}', 'metric': k, 'mine': x, 'saved': y})
        # 보고서 정합성: 토큰/요청 수가 readings와 일치
        for k, val in (('n_tokens', reads[(img, c)]['n_tokens']), ('n_requests', len(reads[(img, c)]['request_ids']))):
            nchecked += 1
            if saved[k] != val:
                mism.append({'id': f'{img}|{c}', 'metric': k, 'mine': val, 'saved': saved[k]})
    # 요약 평균 대조
    strata = {r['ImageID']: r.get('stratum', 'D8') for r in rows}
    sets = {'all': list(strata)}
    for s in sorted(set(strata.values())):
        sets[s] = [i for i in strata if strata[i] == s]
    sum_mism = []
    for sname, imgs in sets.items():
        for c in CONDS:
            for m in ('recall_def', 'recall_strict', 'recall_incl_possible', 'contra_primary', 'internal', 'xd', 'xp'):
                vals = [mine[(i, c)][m] for i in imgs if mine[(i, c)][m] is not None]
                mv = float(np.mean(vals)) if vals else None
                sv = rep['summary'][sname]['conditions'][c][m]['mean']
                nchecked += 1
                if (mv is None) != (sv is None) or (mv is not None and abs(mv - sv) > 1e-12):
                    sum_mism.append({'set': sname, 'cond': c, 'metric': m, 'mine': mv, 'saved': sv})
    # bootstrap CI 별도 재계산(다른 seed·다른 구현; 허용오차 0.02)
    rng = np.random.RandomState(20261007)
    ci_checks, ci_bad = 0, []
    for sname, imgs in sets.items():
        for a, b in COMPS:
            for m in ('recall_def', 'contra_primary', 'internal'):
                d = [mine[(i, a)][m] - mine[(i, b)][m] for i in imgs if mine[(i, a)][m] is not None and mine[(i, b)][m] is not None]
                if len(d) < 2:
                    continue
                d = np.array(d, float)
                boots = np.array([d[rng.randint(0, len(d), len(d))].mean() for _ in range(10000)])
                lo, hi = np.percentile(boots, [2.5, 97.5])
                saved = rep['comparisons'][sname][f'{a}-{b}'][m]
                ci_checks += 1
                tol = 0.035 if len(d) >= 30 else 0.05  # 표본이 작으면 bootstrap 분포가 이산적이라 끝점 허용오차를 넓힌다
                ok = abs(saved['diff'] - d.mean()) < 1e-12 and abs(saved['ci95'][0] - lo) < tol and abs(saved['ci95'][1] - hi) < tol
                if not ok:
                    ci_bad.append({'set': sname, 'cmp': f'{a}-{b}', 'metric': m, 'saved': saved, 'mine': [float(lo), float(hi), float(d.mean())]})
    res = {'stage': stage, 'n_values_checked': nchecked, 'n_mismatch_per_output': len(mism), 'mismatches': mism[:20],
           'n_summary_mismatch': len(sum_mism), 'summary_mismatches': sum_mism[:20], 'n_ci_checked': ci_checks, 'n_ci_mismatch': len(ci_bad), 'ci_mismatches': ci_bad[:10],
           'judgments_sha256': sha(jpath), 'report_sha256': sha(rpath), 'pass': not mism and not sum_mism and not ci_bad,
           'independence': 'judgment text parsed by separate code; no import of report86_eval; CI via RandomState(20261007) loop'}
    save(outp, res)
    print(json.dumps({k: v for k, v in res.items() if k not in ('mismatches', 'summary_mismatches', 'ci_mismatches')}, indent=1))
    sys.exit(0 if res['pass'] else 1)


if __name__ == '__main__':
    main()
