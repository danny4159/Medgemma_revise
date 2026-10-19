"""잠긴 E16 출력과 인용 판정표의 최종 집계. 의미 판정과 원 기준을 바꾸지 않는다."""
import argparse
import hashlib
from pathlib import Path
import statistics

from i141_common import read, sha, digest, now
from i143_data import OUT
from i143_runtime import save
from i143_assess import score, compare
from i143_decision import outcome, swap_condition


def selection_bound():
    from i143_confirm_shard import runtime_bound
    from i143_train import bound
    runtime_bound()
    gate = read(OUT / 'training_gate.json')
    bound(gate)
    selection = read(OUT / 'selection.json')
    assert selection['passed'] and selection['gate_sha256'] == sha(OUT / 'training_gate.json')
    for path, value in selection['evidence_files'].items():
        assert sha(path) == value, path
    assert selection['swap_condition'] == swap_condition(selection['validation_metrics'])
    assert selection['epoch'] == (16 if read(OUT / 'extension_decision.json')['extend'] else 8)
    return selection, gate


def prior_packages():
    selection_bound()
    contract = read(OUT / 'eval_contract.json')
    rows = []
    for ref in contract['rows']:
        if ref['split'] != 'E':
            continue
        rows.append(dict(package_id=digest(dict(prior_sha256=sha(OUT / 'eval_contract.json'),
             patient_id=ref['patient_id']))[:16], patient_id=ref['patient_id'],
             text=contract['prior_text'], atoms=ref['atoms'], eos=True, boundary='no_marker'))
    assert len(rows) == 16
    save(OUT / 'assessment_prior' / 'packages.json', dict(created_at=now(), rows=rows,
         contract_sha256=sha(OUT / 'eval_contract.json'),
         scope='학습 자료만으로 사전 고정한 prior 문장의 E16 항목 대응. 모델 출력 아님.'))


def summarize(rows):
    kinds = sorted({k for r in rows for k in r['by_type']})
    by_type = {}
    for kind in kinds:
        totals = {s: sum(r['by_type'].get(kind, {}).get(s, 0) for r in rows)
                  for s in ('matched', 'unmatched', 'unresolved')}
        eligible = [r['by_type'][kind] for r in rows if kind in r['by_type']]
        by_type[kind] = dict(counts=totals, patients=len(eligible),
            patient_mean_recall=statistics.mean(t['matched'] / sum(t.values()) for t in eligible),
            patient_mean_upper=statistics.mean((t['matched'] + t['unresolved']) / sum(t.values()) for t in eligible))
    return dict(n=len(rows), recall=statistics.mean(r['recall'] for r in rows),
        recall_upper=statistics.mean(r['recall_upper'] for r in rows),
        contradiction_count=sum(r['contradiction'] for r in rows),
        contradiction_upper_count=sum(r['contradiction_upper'] for r in rows),
        internal_count=sum(r['internal'] for r in rows),
        internal_upper_count=sum(r['internal_upper'] for r in rows),
        incomplete_count=sum(r['incomplete'] for r in rows), by_type=by_type)


def collect():
    selection, gate = selection_bound()
    epoch = selection['epoch']
    stages = [f'{c}_epoch{e:02d}' for c in 'SAN' for e in (0, epoch)]
    swapped = f'{selection["swap_condition"]}_epoch{epoch:02d}_swap'
    stages.append(swapped)
    contract = read(OUT / 'eval_contract.json')
    refs = {r['patient_id']: r['atoms'] for r in contract['rows'] if r['split'] == 'E'}
    assert len(refs) == 16
    evidence = {str(OUT / name): sha(OUT / name) for name in
                ('selection.json', 'training_gate.json', 'confirm_runtime_protocol.json', 'eval_contract.json')}
    expected_paths = set()
    from i143_confirm_schedule import merge
    for stage in stages:
        completion = OUT / 'confirm_sharded' / stage / 'completion.json'
        assert completion.exists(), completion
        merge(stage, stage == swapped)
        evidence[str(completion)] = sha(completion)
        expected_paths.update(str(Path(p).resolve()) for p in read(completion)['files'])
    assert len(expected_paths) == 112

    adapters = {}
    import torch
    for c in 'SAN':
        initial = OUT / 'train' / c / 'initial_adapter_hashes.json'
        evidence[str(initial)] = sha(initial)
        adapters[c, 0] = digest(read(initial))
        path = Path(selection['checkpoints'][c]['path'])
        assert sha(path) == selection['checkpoints'][c]['sha256']
        evidence[str(path)] = sha(path)
        state = torch.load(path, map_location='cpu', weights_only=False)
        assert state['epoch'] == epoch and state['updates'] == epoch * 6
        assert state['config']['condition'] == c
        adapters[c, epoch] = digest({k: hashlib.sha256(v.numpy().tobytes()).hexdigest()
                                    for k, v in state['adapter'].items()})
        del state
    scored, seen_paths = {}, set()
    for directory in sorted((OUT / 'assessment_E').glob('batch*')):
        packages = read(directory / 'packages.json')
        mapping = read(directory / 'mapping.json')
        judgments = read(directory / 'judgments.json')['rows']
        by_id = {j['package_id']: j for j in judgments}
        assert len(by_id) == len(judgments)
        assert set(by_id) == set(mapping) == {p['package_id'] for p in packages['rows']}
        assert packages['contract_sha256'] == sha(OUT / 'eval_contract.json')
        for name in ('packages.json', 'mapping.json', 'judgments.json'):
            evidence[str(directory / name)] = sha(directory / name)
        for p in packages['rows']:
            link = mapping[p['package_id']]
            path = Path(link['path'])
            assert str(path.resolve()) in expected_paths and str(path.resolve()) not in seen_paths
            seen_paths.add(str(path.resolve()))
            assert sha(path) == link['sha256']
            evidence[str(path)] = sha(path)
            raw = read(path)
            stage = path.resolve().relative_to((OUT / 'confirm_sharded').resolve()).parts[0]
            assert raw['digest'] == digest({k: v for k, v in raw.items() if k != 'digest'})
            assert (raw['condition'], raw['epoch']) == (link['condition'], link['epoch'])
            assert p['patient_id'] == raw['patient_id'] and p['atoms'] == refs[raw['patient_id']]
            assert (p['text'], p['eos'], p['boundary']) == (raw['final_text'], raw['eos'], raw['boundary'])
            prov = raw['provenance']
            assert prov['adapter_digest'] == adapters[raw['condition'], raw['epoch']]
            assert prov['cap'] == gate['cap'] and prov['cache_enabled'] == gate['cache_enabled']
            assert prov['manifest_sha256'] == sha(OUT / 'data_manifest.json')
            key = (stage, p['patient_id'])
            assert key not in scored
            scored[key] = score(p, by_id[p['package_id']])
    assert seen_paths == expected_paths
    assert set(scored) == {(s, p) for s in stages for p in refs}
    directory = OUT / 'assessment_prior'
    packages = read(directory / 'packages.json')
    judgments = read(directory / 'judgments.json')['rows']
    by_id = {j['package_id']: j for j in judgments}
    assert len(by_id) == len(judgments) == 16
    assert set(by_id) == {p['package_id'] for p in packages['rows']}
    assert {p['patient_id'] for p in packages['rows']} == set(refs)
    assert packages['contract_sha256'] == sha(OUT / 'eval_contract.json')
    for name in ('packages.json', 'judgments.json'):
        evidence[str(directory / name)] = sha(directory / name)
    for p in packages['rows']:
        assert p['text'] == contract['prior_text'] and p['atoms'] == refs[p['patient_id']]
        assert p['eos'] and p['boundary'] == 'no_marker'
        scored['prior', p['patient_id']] = score(p, by_id[p['package_id']])
    groups = {s: [scored[s, p] for p in sorted(refs)] for s in stages + ['prior']}
    return selection, groups, evidence


def report():
    selection, groups, evidence = collect()
    e = selection['epoch']
    a, s, n = (f'{c}_epoch{e:02d}' for c in 'ASN')
    pairs = dict(A_minus_S=(a, s), A_minus_N=(a, n), N_minus_S=(n, s))
    for c in 'SAN':
        pairs[c + '_adapted_minus_base'] = (f'{c}_epoch{e:02d}', f'{c}_epoch00')
        pairs[c + '_adapted_minus_prior'] = (f'{c}_epoch{e:02d}', 'prior')
    original = f'{selection["swap_condition"]}_epoch{e:02d}'
    pairs['original_minus_swapped'] = (original, original + '_swap')
    comparisons = {k: compare(groups[x], groups[y]) for k, (x, y) in pairs.items()}
    result = dict(created_at=now(), epoch=e, summaries={k: summarize(v) for k, v in groups.items()},
        comparisons=comparisons, rows=groups, pairs=pairs,
        outcome=outcome(comparisons['A_minus_S'], valid_learning=True),
        evidence_files=evidence, aggregation_source_sha256=sha(__file__),
        scope='사전 산술의 사후 집계. assistant 텍스트 대응이며 독립 임상 평가가 아니다. 기술·학습 유효성 근거는 별도 보고한다.')
    save(OUT / 'final_report.json', result)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=('prepare-prior', 'report'))
    a = p.parse_args()
    prior_packages() if a.command == 'prepare-prior' else report()
