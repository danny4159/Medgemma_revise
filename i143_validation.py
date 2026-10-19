"""완료된 V8의 인용 판정표를 기존 산술로 집계하고 공통 종료점을 봉인한다."""
import argparse
from pathlib import Path
import statistics
import hashlib
import math
import random

from i141_common import read, sha, digest, now
from i143_data import OUT
from i143_assess import score
from i143_decision import extension, swap_condition
from i143_runtime import save


def preserve(path, value):
    """집계 중 중단 후 동일 내용만 재사용하며 이전 결과를 덮어쓰지 않는다."""
    if Path(path).exists():
        old = read(path)
        assert {k: v for k, v in old.items() if k != 'created_at'} == {
            k: v for k, v in value.items() if k != 'created_at'}, path
        return old
    save(path, value)
    return value


def collect(epoch):
    manifest = read(OUT / 'data_manifest.json')
    expected = {r['patient_id'] for r in manifest['rows'] if r['split'] == 'V'}
    input_rows = {r['patient_id']: r for r in manifest['rows'] if r['split'] == 'V'}
    train = [r for r in manifest['rows'] if r['split'] == 'T']
    assert len(train) == 24
    assert len(expected) == 8
    milestones = [0, 2, 4, 8] + ([16] if epoch == 16 else [])
    evidence = {}

    def include(path):
        path = Path(path)
        evidence[str(path)] = sha(path)
        return read(path)

    gate = include(OUT / 'training_gate.json')
    assert gate['passed']
    for path, value in gate['files'].items():
        assert sha(path) == value, path
    include(OUT / 'data_manifest.json')
    contract = include(OUT / 'eval_contract.json')
    refs = {r['patient_id']: r['atoms'] for r in contract['rows']}
    adapters = {}
    initial_hashes = None
    for condition in 'SAN':
        config = include(OUT / 'train' / condition / 'config.json')
        from i143_train import CONFIG
        assert config == dict(CONFIG, condition=condition,
                              gate_sha256=sha(OUT / 'training_gate.json'))
        initial = include(OUT / 'train' / condition / 'initial_adapter_hashes.json')
        if initial_hashes is None:
            initial_hashes = initial
        assert initial == initial_hashes
        adapters[condition, 0] = digest(initial)
        complete = include(OUT / 'train' / condition / f'complete{epoch:02d}.json')
        assert complete['epoch'] == epoch and complete['updates'] == epoch * 6
        assert complete['config_digest'] == digest(config)
        for number in range(1, epoch + 1):
            seal = include(OUT / 'train' / condition / f'epoch{number:02d}.json')
            checkpoint = OUT / 'train' / condition / f'epoch{number:02d}.pt'
            assert sha(checkpoint) == seal['sha256']
            assert seal['updates'] == number * 6
            assert seal['config_digest'] == digest(config)
            order = list(range(len(train)))
            random.Random(17 + number).shuffle(order)
            assert seal['patient_order'] == [train[i]['patient_id'] for i in order]
            assert len(seal['losses']) == 24 and all(math.isfinite(v) for v in seal['losses'])
            if number in milestones:
                import torch
                state = torch.load(checkpoint, map_location='cpu', weights_only=False)
                assert state['config'] == config and state['epoch'] == number
                assert state['updates'] == seal['updates']
                assert state['losses'] == seal['losses']
                assert state['patient_order'] == seal['patient_order']
                assert set(state['adapter']) == set(initial)
                adapters[condition, number] = digest({
                    k: hashlib.sha256(v.numpy().tobytes()).hexdigest()
                    for k, v in state['adapter'].items()})
                del state

    scored = {}
    for directory in sorted((OUT / 'assessment').glob('batch*')):
        packages = include(directory / 'packages.json')
        assert packages['contract_sha256'] == sha(OUT / 'eval_contract.json')
        mapping = include(directory / 'mapping.json')
        judgments = include(directory / 'judgments.json')['rows']
        by_id = {r['package_id']: r for r in judgments}
        assert len(by_id) == len(judgments)
        assert set(by_id) == set(mapping) == {r['package_id'] for r in packages['rows']}
        for package in packages['rows']:
            link = mapping[package['package_id']]
            path = Path(link['path'])
            assert path.resolve().is_relative_to((OUT / 'generation').resolve())
            assert sha(path) == link['sha256']
            raw = include(path)
            assert raw['digest'] == digest({k: v for k, v in raw.items() if k != 'digest'})
            assert raw['condition'] == link['condition'] and raw['epoch'] == link['epoch']
            assert package['text'] == raw['final_text']
            assert package['eos'] == raw['eos'] and package['boundary'] == raw['boundary']
            assert package['patient_id'] == raw['patient_id']
            assert package['atoms'] == refs[raw['patient_id']]
            assert raw['provenance']['gate_sha256'] == sha(OUT / 'training_gate.json')
            assert raw['epoch'] in milestones and raw['patient_id'] in expected
            assert raw['provenance']['manifest_sha256'] == sha(OUT / 'data_manifest.json')
            assert raw['provenance']['cap'] == gate['cap']
            assert raw['provenance']['cache_enabled'] == gate['cache_enabled']
            assert raw['provenance']['adapter_digest'] == adapters[raw['condition'], raw['epoch']]
            assert math.isfinite(raw['target_nll'])
            assert raw['image_source_patient'] == raw['patient_id']
            assert raw['input_hashes'] == [im['sha256'] for im in input_rows[raw['patient_id']]['images']]
            assert raw['n_tokens'] == len(raw['tokens']) and 0 < raw['n_tokens'] <= gate['cap']
            key = (raw['condition'], raw['epoch'], raw['patient_id'])
            assert key not in scored
            value = score(package, by_id[package['package_id']])
            value.update(target_nll=raw['target_nll'], n_tokens=raw['n_tokens'],
                         package_id=package['package_id'], source=str(path))
            scored[key] = value
    assert set(scored) == {(c, e, p) for c in 'SAN' for e in milestones for p in expected}
    metrics = {}
    for condition in 'SAN':
        metrics[condition] = {}
        for number in milestones:
            rows = [scored[condition, number, p] for p in sorted(expected)]
            metrics[condition][str(number)] = dict(
                recall=statistics.mean(r['recall'] for r in rows),
                recall_upper=statistics.mean(r['recall_upper'] for r in rows),
                target_nll=statistics.mean(r['target_nll'] for r in rows),
                contradiction_count=sum(r['contradiction'] for r in rows),
                incomplete_count=sum(r['incomplete'] for r in rows), rows=rows)
    return metrics, evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--epoch', type=int, choices=[8, 16], required=True)
    args = parser.parse_args()
    metrics, evidence = collect(args.epoch)
    report_path = OUT / f'validation_epoch{args.epoch:02d}.json'
    report = dict(created_at=now(),metrics=metrics,evidence_files=evidence,
                  aggregation_source_sha256=sha(__file__),
                  scope='기존 산술의 사후 집계. 원 의미 규약과 판정 문턱은 변경하지 않음.')
    preserve(report_path, report)
    evidence[str(report_path)] = sha(report_path)
    evidence[str(Path(__file__))] = sha(__file__)
    if args.epoch == 8:
        decision = extension(metrics)
        decision.update(created_at=now(), evidence_files=dict(evidence),
                        decision_source_sha256=sha('i143_decision.py'))
        decision = preserve(OUT / 'extension_decision.json', decision)
    else:
        decision = read(OUT / 'extension_decision.json')
        assert decision['extend']
        for path, value in decision['evidence_files'].items():
            assert sha(path) == value
    evidence[str(OUT / 'extension_decision.json')] = sha(OUT / 'extension_decision.json')
    if args.epoch == 8 and decision['extend']:
        print('사전 기준에 따라 세 조건 공통 epoch16 연장. E는 아직 열지 않음.')
        return
    final = {c: metrics[c][str(args.epoch)] for c in 'SAN'}
    checkpoints = {}
    for condition in 'SAN':
        path = OUT / 'train' / condition / f'epoch{args.epoch:02d}.pt'
        checkpoints[condition] = dict(path=str(path), sha256=sha(path))
    preserve(OUT / 'selection.json', dict(passed=True, created_at=now(), epoch=args.epoch,
         gate_sha256=sha(OUT / 'training_gate.json'), evidence_files=evidence,
         validation_metrics=final, swap_condition=swap_condition(final), checkpoints=checkpoints))
    print('공통 종료 epoch 및 영상 교환 조건 봉인 완료')


if __name__ == '__main__':
    main()
