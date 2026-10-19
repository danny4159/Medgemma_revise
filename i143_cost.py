"""보존된 실행 기록의 비용 집계. 미측정 구간을 전체 비용으로 보간하지 않는다."""
import argparse
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import json

from i141_common import read, sha, now
from i143_data import OUT
from i143_runtime import save


def collect():
    evidence = {}

    def record(path):
        evidence[str(path)] = sha(path)
        value = read(path)
        assert sha(path) == evidence[str(path)], path
        return value

    schedules = []
    for pattern in ('schedule/epoch*', 'confirm_schedule/*'):
        for directory in sorted(OUT.glob(pattern)):
            path = directory / 'resources.jsonl'
            if not path.is_file():
                continue
            evidence[str(path)] = sha(path)
            samples = [json.loads(line) for line in path.read_text().splitlines() if line]
            assert sha(path) == evidence[str(path)], path
            assert samples
            times = [datetime.fromisoformat(s.get('time', s.get('created_at'))) for s in samples]
            assert all(a <= b for a, b in zip(times, times[1:]))
            gpu = {}
            for sample in samples:
                for row in sample['gpu']:
                    g = gpu.setdefault(row['index'], dict(peak_used_mib=0, min_free_mib=float('inf')))
                    g['peak_used_mib'] = max(g['peak_used_mib'], int(row['used']))
                    g['min_free_mib'] = min(g['min_free_mib'], int(row['free']))
            completion = record(directory / 'completion.json') if (directory / 'completion.json').exists() else None
            launches = {p.stem: record(p) for p in directory.glob('*launch.json')}
            exits = {p.stem: record(p) for p in directory.glob('*exit.json')}
            schedules.append(dict(path=str(directory), samples=len(samples),
                first_sample=times[0].isoformat(), last_sample=times[-1].isoformat(),
                observed_wall_seconds=(times[-1] - times[0]).total_seconds(),
                completion=completion, launches=launches, exits=exits, gpu=gpu))

    training = {}
    for condition in 'SAN':
        seals = [record(p) for p in sorted((OUT / 'train' / condition).glob('epoch[0-9][0-9].json'))]
        training[condition] = dict(epochs=len(seals),
            recorded_training_seconds=sum(s['seconds'] for s in seals),
            updates=max((s['updates'] for s in seals), default=0))
    generation = defaultdict(lambda: dict(requests=0, seconds=0., saved_prefix_seconds=0., tokens=0,
                                          non_eos=0, peak_reserved_mib=0.))
    paths = list((OUT / 'generation').glob('*/epoch*/sub-*.json'))
    paths += list((OUT / 'confirm_sharded').glob('*/shard*/outputs/sub-*.json'))
    for path in sorted(paths):
        r = record(path)
        group = str(path.parent.relative_to(OUT))
        item = generation[group]
        item['requests'] += 1
        item['seconds'] += r['seconds']
        item['saved_prefix_seconds'] += r.get('saved_prefix_seconds', 0.)
        item['tokens'] += r['n_tokens']
        item['non_eos'] += not r['eos']
        item['peak_reserved_mib'] = max(item['peak_reserved_mib'], r['peak_reserved_mib'])
    return dict(created_at=now(), schedules=schedules, training=training,
        generation=dict(generation), evidence_files=evidence, source_sha256=sha(__file__),
        limits=[
            '학습 seconds는 보존된 epoch 학습 구간이며 모델 적재·validation을 제외한다.',
            '생성 seconds는 해당 요청 생성 구간이며 이후 target NLL 계산을 제외한다. 재개 prefix 비용은 별도다.',
            '감독기 관측 wall은 첫/마지막 자원 표본 사이 구간이다. 중단 후 마지막 표본 밖의 시간을 추정하지 않는다.',
            'GPU used/free는 다른 프로세스를 포함한 장치 전체 측정이다. 프로세스별 reserved와 구분한다.',
            '원 감독기의 마지막 자식 exit/conditions 누락은 완료 봉인과 별도로 확인해야 한다.',
            '이 집계는 본학습·평가 경로만 포함한다. 기술 검사·다운로드·평가자 시간은 별도이며 합산 전체 비용이 아니다.'])


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', required=True)
    a = p.parse_args()
    destination = Path(a.output)
    assert destination.resolve().is_relative_to(OUT.resolve())
    save(destination, collect())
