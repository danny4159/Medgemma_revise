"""원시 token과 인용 판정에서 최종 산술을 별도로 검산한다. 의미 재판정은 하지 않는다."""
import json
from pathlib import Path
import math
import numpy as np
from transformers import AutoTokenizer
from i141_common import read, sha, now
from i143_runtime import save


def close(a, b):
    assert math.isclose(a, b, rel_tol=0, abs_tol=1e-12), (a, b)


def main():
    root = Path('results/iter_143')
    report = read(root / 'final_report.json')
    for p, h in report['evidence_files'].items():
        assert sha(p) == h, p
    model = Path('../hf_cache/models--google--medgemma-1.5-4b-it/snapshots/91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b')
    tokenizer = AutoTokenizer.from_pretrained(model, local_files_only=True)
    begin, end = tokenizer.convert_tokens_to_ids(['<unused94>', '<unused95>'])
    stops = read(model / 'generation_config.json')['eos_token_id']
    stops = {stops} if isinstance(stops, int) else set(stops)
    groups = {}
    seen = set()
    for directory in list(sorted((root / 'assessment_E').glob('batch*'))) + [root / 'assessment_prior']:
        prior = directory.name == 'assessment_prior'
        package = read(directory / 'packages.json')
        judgments = read(directory / 'judgments.json')['rows']
        by_id = {j['package_id']: j for j in judgments}
        assert len(by_id) == len(judgments) == len(package['rows'])
        mapping = {} if prior else read(directory / 'mapping.json')
        for p in package['rows']:
            j = by_id[p['package_id']]
            if prior:
                stage = 'prior'
            else:
                link = mapping[p['package_id']]
                path = Path(link['path'])
                assert sha(path) == link['sha256']
                raw = read(path)
                stage = path.resolve().relative_to((root / 'confirm_sharded').resolve()).parts[0]
                tokens = raw['tokens']
                assert len(tokens) == raw['n_tokens']
                assert bool(tokens[-1] in stops) == raw['eos']
                assert not any(t in stops for t in tokens[:-1])
                assert tokenizer.decode(tokens, skip_special_tokens=True) == raw['text']
                nb, ne = tokens.count(begin), tokens.count(end)
                if nb == ne == 0:
                    boundary, final = 'no_marker', tokens
                elif nb == ne == 1 and tokens[0] == begin and tokens.index(end) > 0:
                    boundary, final = 'thought_final', tokens[tokens.index(end) + 1:]
                else:
                    boundary, final = 'invalid_boundary', []
                assert boundary == raw['boundary'] == p['boundary']
                assert tokenizer.decode(final, skip_special_tokens=True) == raw['final_text'] == p['text']
                assert raw['eos'] == p['eos'] and raw['patient_id'] == p['patient_id']
            key = (stage, p['patient_id'])
            assert key not in seen
            seen.add(key)
            assert set(j['atoms']) == {a['id'] for a in p['atoms']}
            incomplete = not p['eos'] or p['boundary'] == 'invalid_boundary'
            counts = dict(matched=0, unmatched=0, unresolved=0)
            types = {}
            for a in p['atoms']:
                v = j['atoms'][a['id']]
                assert all(q and q in p['text'] for q in v['quotes'])
                state = v['status']
                if state == 'matched':
                    assert v['quotes'] and p['boundary'] != 'invalid_boundary'
                if incomplete and state == 'unmatched':
                    state = 'unresolved'
                counts[state] += 1
                types.setdefault(a['type'], dict(matched=0, unmatched=0, unresolved=0))[state] += 1
            for v in j['contradictions']:
                assert v['quote'] in p['text'] and v['atom_id'] in j['atoms']
            for v in j['internal_contradictions']:
                assert len(v['quotes']) == 2 and all(q in p['text'] for q in v['quotes'])
            n = len(p['atoms'])
            row = dict(patient_id=p['patient_id'], recall=counts['matched']/n,
                       recall_upper=(counts['matched']+counts['unresolved'])/n,
                       counts=counts, by_type=types, incomplete=incomplete,
                       contradiction=int(bool(j['contradictions'])),
                       contradiction_upper=int(bool(j['contradictions']) or incomplete or j['contradiction_unresolved']),
                       internal=int(bool(j['internal_contradictions'])),
                       internal_upper=int(bool(j['internal_contradictions']) or incomplete or j['internal_unresolved']))
            groups.setdefault(stage, []).append(row)
    assert len(seen) == 128
    for stage, rows in groups.items():
        rows.sort(key=lambda r: r['patient_id'])
        assert len(rows) == 16 and rows == report['rows'][stage]
        summary = report['summaries'][stage]
        for name in ('recall', 'recall_upper'):
            close(np.mean([r[name] for r in rows]), summary[name])
        for source, dest in [('contradiction','contradiction_count'),('contradiction_upper','contradiction_upper_count'),
                             ('internal','internal_count'),('internal_upper','internal_upper_count'),('incomplete','incomplete_count')]:
            assert sum(r[source] for r in rows) == summary[dest]
        for kind, s in summary['by_type'].items():
            selected = [r['by_type'][kind] for r in rows if kind in r['by_type']]
            assert s['patients'] == len(selected)
            assert s['counts'] == {k: sum(r[k] for r in selected) for k in ('matched','unmatched','unresolved')}
            close(np.mean([r['matched']/sum(r.values()) for r in selected]), s['patient_mean_recall'])
            close(np.mean([(r['matched']+r['unresolved'])/sum(r.values()) for r in selected]), s['patient_mean_upper'])
    for name, (a, b) in report['pairs'].items():
        x, y = groups[a], groups[b]
        assert [r['patient_id'] for r in x] == [r['patient_id'] for r in y]
        target = report['comparisons'][name]
        for field, ax, by in [('point','recall','recall'),('lower_difference_ci','recall','recall_upper'),('upper_difference_ci','recall_upper','recall')]:
            delta = np.array([r[ax]-s[by] for r,s in zip(x,y)])
            rng = np.random.default_rng(17)
            samples = delta[rng.integers(0,16,size=(10000,16))].mean(axis=1)
            close(delta.mean(), target[field]['mean'])
            assert np.allclose(np.percentile(samples,[2.5,97.5]), target[field]['ci95'], atol=1e-12, rtol=0)
        for field, pairs in [('semantic_difference',[('recall','recall_upper'),('recall_upper','recall')]),
                             ('contradiction_difference',[('contradiction','contradiction_upper'),('contradiction_upper','contradiction')])]:
            for i,(ax,by) in enumerate(pairs):
                close(np.mean([r[ax]-s[by] for r,s in zip(x,y)]),target[field][i])
    c = report['comparisons']['A_minus_S']
    if c['semantic_difference'][0] >= .05-1e-12 and c['contradiction_difference'][1] <= .05+1e-12:
        expected = 'pilot_positive' if c['point']['ci95'][0]>0 else 'promising_inconclusive'
    elif c['upper_difference_ci']['ci95'][1] < .05-1e-12:
        expected = 'current_design_gain_not_supported'
    else:
        expected = 'inconclusive'
    assert report['outcome'] == expected
    save(root / 'final_independent_verification.json', dict(created_at=now(),passed=True,
         outputs=112,prior_rows=16,comparisons=len(report['pairs']),outcome=expected,
         report_sha256=sha(root/'final_report.json'),source_sha256=sha(__file__),
         scope='원시 token·EOS·답 경계 및 고정 판정표 산술·bootstrap 검산. 의미 판정의 독립 임상 검증은 아님.'))
    print('최종 독립 산술 검산 통과')


if __name__ == '__main__':
    main()
