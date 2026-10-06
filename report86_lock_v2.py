"""E 선택 잠금 v2: facts 규칙에 'abnormal 표기가 있으나 특정 소견을 부정하는 문장(without appreciating)' 분기를 추가한 뒤,
이미 만든 E 표본·reference 사실(v1)이 규칙 변경으로 달라지지 않았는지 대조하고 현재 규칙 hash로 잠금을 새 파일에 기록한다. (E 생성 전)
python report86_lock_v2.py
"""
import json

from report86_common import R86, save, sha
import report86_facts as F

E = R86 / 'E'


def main():
    refs = json.loads((E / 'reference_facts_E_private.json').read_text())
    enum = {c['ImageID']: c for c in json.loads((E / 'enumeration.json').read_text())['ordered_candidates']}
    diffs = []
    for iid, r in refs.items():
        new = F.facts_for(enum[iid])
        for a, b in zip(r['facts'], new):
            if a['fact_class'] != b['fact_class'] or a['sentence_en'] != b['sentence_en']:
                diffs.append({'ImageID': iid, 'fact': a['fact_id'], 'old': a['fact_class'], 'new': b['fact_class']})
        assert len(r['facts']) == len(new)
    lock1 = json.loads((E / 'selection_lock.json').read_text())
    lock2 = {'supersedes_hash_of_facts_rules': lock1['facts_rules_sha256'], 'facts_rules_sha256': F.rules_sha(),
             'n_facts_compared': sum(len(r['facts']) for r in refs.values()), 'n_class_differences_vs_v1': len(diffs), 'differences': diffs,
             'inputs_E96_sha256': sha(E / 'inputs_E96.json'), 'inputs_E192x_sha256': sha(E / 'inputs_E192x.json'),
             'reference_facts_sha256': sha(E / 'reference_facts_E_private.json'), 'selection_lock_v1_sha256': sha(E / 'selection_lock.json'),
             'note': 'E 표본·reference 사실은 v1과 동일. 규칙 변경은 D8 P000의 문장에만 영향.'}
    save(E / 'selection_lock_v2.json', lock2)
    print(json.dumps({k: v for k, v in lock2.items() if k != 'differences'}, indent=1), diffs)


if __name__ == '__main__':
    main()
