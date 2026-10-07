"""실제 재점검 기록을 요구하고 원 판정을 보존한 새 평가 묶음을 만든다."""
import json
from pathlib import Path
from report86_common import save, sha
from report90_numeric import OUT as ORIGINAL

OUT = ORIGINAL / 'recovery'


def main():
    original = OUT / 'semantic/E'
    review = OUT / 'semantic/E_recheck'
    selection = json.loads((review / 'selection.json').read_text())
    for path, digest in selection['sources'].items():
        assert sha(path) == digest
    notes_path = review / 'notes.json'
    notes = json.loads(notes_path.read_text())
    assert notes['selection_sha'] == sha(review / 'selection.json')
    rows = notes['reviews']
    by_id = {row['blind_id']: row for row in rows}
    assert len(rows) == len(by_id)
    assert set(by_id) == set(selection['expected_blind_ids'])
    for row in rows:
        assert row['reviewed'] is True and row['evidence_note'].strip()
        assert row['decision'] in ['retain', 'amend']
        if row['decision'] == 'amend':
            assert row['replacement']['blind_id'] == row['blind_id']
    target = OUT / 'semantic/E_adjudicated'
    assert not target.exists(), '기존 평가 묶음을 덮어쓰지 않는다'
    sources = {str(p): sha(p) for p in [review / 'selection.json', notes_path,
               original / 'blinded.json', original / 'private_mapping.json', Path(__file__)]}
    blinded = json.loads((original / 'blinded.json').read_text())
    blinded['provenance'].update(sources)
    save(target / 'blinded.json', blinded)
    save(target / 'private_mapping.json', json.loads((original / 'private_mapping.json').read_text()))
    seen = set()
    amendments = []
    for path in sorted((original / 'judgments').glob('part_*.json')):
        data = json.loads(path.read_text())
        assert data['blinded_sha'] == sha(original / 'blinded.json')
        sources[str(path)] = sha(path)
        for i, judgment in enumerate(data['judgments']):
            bid = judgment['blind_id']
            assert bid not in seen
            seen.add(bid)
            if bid in by_id and by_id[bid]['decision'] == 'amend':
                replacement = by_id[bid]['replacement']
                amendments.append(dict(blind_id=bid, before=judgment, after=replacement,
                                       reason=by_id[bid]['evidence_note']))
                data['judgments'][i] = replacement
        data['blinded_sha'] = sha(target / 'blinded.json')
        data['original_part_sha'] = sha(path)
        save(target / 'judgments' / path.name, data)
    assert set(by_id) <= seen and len(seen) == 512
    save(target / 'adjudication.json', dict(sources=sources, reviewed_n=len(rows),
         total_n=len(seen), amendments=amendments,
         scope='assistant의 원문 재점검. 독립 전문의 검증 또는 임상 gold가 아님.'))
    print('재점검 연결:', len(rows), '판정 수정:', len(amendments), '; 집계·독립 검증은 별도 실행 필요')


if __name__ == '__main__':
    main()
