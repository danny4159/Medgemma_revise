"""동일 환자·reference·출력 문자열의 기존 판정만 재사용 후보로 연결한다."""
import argparse
import json
from pathlib import Path
from report86_common import save, sha


def main(a):
    old = Path(a.source).resolve()
    new = Path(a.target).resolve()
    verification = old / 'eval/verification.json'
    verified = json.loads(verification.read_text())
    assert verified['passed'] and not verified['differences']
    for path, digest in verified['sources'].items():
        assert sha(path) == digest
    before = json.loads((old / 'blinded.json').read_text())
    after = json.loads((new / 'blinded.json').read_text())
    assert before['reference_sha'] == after['reference_sha']
    judgments = {}
    paths = sorted((old / 'judgments').glob('part_*.json'))
    for path in paths:
        data = json.loads(path.read_text())
        assert data['blinded_sha'] == sha(old / 'blinded.json')
        for row in data['judgments']:
            assert row['blind_id'] not in judgments
            judgments[row['blind_id']] = row
    lookup = {}
    for row in before['records']:
        key = (row['image_id'], row['text'], row['non_eos'])
        judgment = {k: v for k, v in judgments[row['blind_id']].items() if k != 'blind_id'}
        lookup.setdefault(key, []).append((row['blind_id'], judgment))
    reusable = []
    manual = []
    for row in after['records']:
        candidates = lookup.get((row['image_id'], row['text'], row['non_eos']), [])
        if not candidates:
            manual.append(dict(blind_id=row['blind_id'], reason='새 문자열 또는 종료 상태'))
            continue
        canonical = {json.dumps(j, sort_keys=True, ensure_ascii=False) for _, j in candidates}
        if len(canonical) != 1:
            manual.append(dict(blind_id=row['blind_id'], reason='같은 기존 문자열의 판정 기록 불일치'))
            continue
        reusable.append(dict(blind_id=row['blind_id'], source_blind_ids=[x[0] for x in candidates],
                             judgment=dict(candidates[0][1], blind_id=row['blind_id'])))
    save(new / 'exact_reuse.json', dict(reusable=reusable, manual=manual,
         sources={str(p): sha(p) for p in [verification, old / 'blinded.json', new / 'blinded.json', *paths, Path(__file__)]},
         scope='완료 판정 파일이 아닌 후보 목록. 새 문자열은 실제 의미 검토가 필요하다.'))
    print('동일 내용 재사용 후보', len(reusable), '새 검토', len(manual))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--source', required=True)
    p.add_argument('--target', required=True)
    main(p.parse_args())
