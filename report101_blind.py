"""iter_101: 완료된 main 교정 생성(T/V/W)과 GPU 없는 K/A 텍스트를 조건명 없는 blind ID로 묶어 의미 검토용 파일을 만든다.

- 생성 stage는 completion과 요청·protocol 검증(report101_gen.verify)을 통과해야 한다.
- K = CURE 초안(좌표 제거), A = 초안 + 좌/우 영역 설명 단순 결합(고정 순서). T/V/W는 모델 출력(원문 그대로).
- 조건명·mapping은 private_mapping.json에만 둔다. 검토 파일에는 reference 문장·atom 표만 포함한다(모델 입력에는 없었음).
- blind는 문체로 조건을 추측할 수 있어 완전한 눈가림이 아니다(JSON 출력·'Revised Report' 머리말·FINDINGS 형식 등).
"""
import hashlib
import json
from pathlib import Path

import pg39_data as D
import report101_gen as G
import report101_req as RQ
from report86_common import ROOT, save, sha

R101 = ROOT / 'results/iter_101'
DATA = R101 / 'data'


def ensure_period(t):
    t = t.rstrip()
    return t if t.endswith(('.', '!', '?')) else t + '.'


def a_text(pk):
    return ensure_period(pk['draft']) + ' ' + pk['left'] + ' ' + pk['right']


def main():
    gen = R101 / 'gen' / 'main'
    req = DATA / 'corr_main' / 'requests.json'
    workers = json.loads((gen / 'mapping.json').read_text())['workers']
    rows, expected = G.verify(gen, str(req), workers)
    assert len(rows) == len(expected) == 18 and (gen / 'completion.json').exists()
    sel = json.loads((DATA / 'lock/selection.json').read_text())
    atoms = json.loads((DATA / 'lock/atoms.json').read_text())
    recs = RQ.load_cure('S24')
    reports, _, _ = D.load_inputs()
    rep = {r['ImageID']: r for r in reports}
    outputs, mapping = [], {}
    review = []
    byid = {r['id']: r for r in rows}
    for img in sel['selected_order']:
        pk = RQ.package(img, recs)
        texts = {'K': pk['draft'], 'A': a_text(pk)}
        flags = {'K': False, 'A': False}
        for c in ('T', 'V', 'W'):
            r = byid['%s|%s' % (img, c)]
            texts[c] = r['text']
            flags[c] = not r['attempts'][-1]['ended_eos']
        outs = []
        for c, t in texts.items():
            b = hashlib.sha256(('101017|iter101|%s|%s' % (img, c)).encode()).hexdigest()[:12]
            assert b not in mapping
            mapping[b] = {'ImageID': img, 'condition': c}
            outs.append({'blind_id': b, 'text': t, 'non_eos': flags[c], 'chars': len(t)})
        outs.sort(key=lambda o: o['blind_id'])
        i = atoms['index'][img]
        review.append({'patient_index': i, 'ref_sentences_full_report': [f['sentence_en'] for f in rep[img]['findings']],
                       'ref_state': atoms['atoms'][img]['ref_state'], 'need_sides': atoms['atoms'][img]['need_sides'],
                       'atoms': atoms['atoms'][img]['atoms'], 'draft_atoms_source': pk['draft'], 'outputs': outs})
    dest = R101 / 'eval' / 'blind'
    save(dest / 'private_mapping.json', mapping)
    save(dest / 'review_input.json', {'review': review, 'completion_sha': sha(gen / 'completion.json'), 'source_sha': sha(__file__)})
    print(len(mapping), 'blinded outputs ->', dest)


if __name__ == '__main__':
    main()
