"""iter_125: 사례별 수동 검토 결과(출력 전)를 고정. 정규식은 후보 검색만 했고 아래 선택은 hash 순서 + 수동 적격성 판정.
적격 조건: 양측/복수 측뇌실의 크기 기술이 명시(양성: 확장·prominent·widen 등, 음성: 정상 크기/폭). 단수 'lateral ventricle', 편측, 상충은 unknown.
usage: python mr125_lock.py show | lock"""
import hashlib, json, re, sys

import pandas as pd

M = '/home/test/.local/share/medgemma/mr_rate/meta/'
RES = 'results/iter_125/data/'
# (cell) -> 최종 환자 순서(= hash 순서 중 적격만). 앞2 tech, 다음3 calib, 나머지10 explore
SEL = {
    'batch04|positive': [14670, 14967, 3405, 14550, 1967, 18291, 17804, 15758, 14950, 17759, 14770, 17564, 15179, 7790, 16347],
    'batch23|positive': [69340, 68412, 68807, 70842, 67665, 68616, 68389, 70433, 69253, 70116, 70707, 70654, 70911, 70531, 69184],
    'batch04|negative': [16576, 17117, 16714, 16713, 17201, 16623, 17856, 16764, 16614, 17185, 16463, 10914, 16451, 15764, 15453],
    'batch23|negative': [36505, 353, 70814, 68800, 70189, 69066, 70113, 70291, 68654, 68298, 69946, 69573, 68622, 41333, 36182],
}
EXCLUDED_AFTER_REVIEW = {
    # patient: reason (hash 순서에서 건너뛴 사례; 모두 선정 전 원문 검토)
    17182: 'singular lateral ventricle (ambiguous side)', 16645: 'unilateral left only', 15831: 'unilateral', 16126: 'unilateral',
    14766: 'narrowing', 16246: 'ventricular system, size compatible with age (hedged)', 16029: 'size compatible with age (hedged)',
    70917: 'singular', 70362: 'unilateral', 70259: 'normal/enlarged conflict', 68783: 'singular', 70042: 'singular',
    68414: 'unilateral+generic mix', 70379: 'conflict', 70005: 'singular', 68702: 'unilateral variant', 68627: 'normal ventricles (regex mislabel)',
    68528: 'singular',
}


def sents(t):
    t = re.sub(r'\s+', ' ', str(t))
    return [s.strip() for s in re.split(r'(?<=[.;])\s+(?=[A-Z])', t) if s.strip()]


def main(mode):
    C = json.load(open(RES + 'ordered_candidates.json'))
    by = {c['patient_uid']: c for v in C.values() for c in v}
    rep = {}
    for b in ['batch04', 'batch23']:
        r = pd.read_csv(M + f'reports/{b}_reports.csv')
        rep.update({x.study_uid: x for x in r.itertuples()})
    man = []
    for cell, ids in SEL.items():
        b, lab = cell.split('|')
        for i, pid in enumerate(ids):
            c = by[pid]
            assert c['batch_id'] == b and c['cand_label'] == lab
            role = 'tech' if i < 2 else 'calib' if i < 5 else 'explore'
            r = rep[c['study_uid']]
            ven = [(k, s) for k in ['findings', 'impression'] for s in sents(getattr(r, k)) if re.search(r'ventric', s, re.I) and not re.fullmatch(r'.*4th ventricle.*', s) ]
            man.append(dict(role=role, batch_id=b, label=lab, patient_uid=pid, study_uid=c['study_uid'], series_id=c['series_id'], array_shape=c['array_shape'],
                            array_spacing_mm=c['array_spacing_mm'], span_key=c['pos'] if lab == 'positive' else c['neg'], all_ventricle_sentences=ven))
    if mode == 'show':
        for m in man:
            print(m['label'][:3], m['batch_id'], m['patient_uid'], m['study_uid'])
            for k, s in m['all_ventricle_sentences']:
                print('    ', k[:3], s[:230])
        return
    assert len({m['patient_uid'] for m in man}) == 60
    src = {f: hashlib.sha256(open(M + f, 'rb').read()).hexdigest() for f in ['splits.csv', 'metadata/batch04_metadata.csv', 'metadata/batch23_metadata.csv', 'reports/batch04_reports.csv', 'reports/batch23_reports.csv']}
    L = dict(seed=125, rule='per batch x label: SHA256("125|patient") order, manual eligibility review, first 15 eligible: 2 tech, 3 calib, 10 explore',
             source_sha256=src, code_sha256={f: hashlib.sha256(open(f, 'rb').read()).hexdigest() for f in ['mr125_select.py', 'mr125_order.py', 'mr125_lock.py']},
             excluded_after_review=EXCLUDED_AFTER_REVIEW, manifest=man)
    import os
    assert not os.path.exists(RES + 'selection_lock.json')
    json.dump(L, open(RES + 'selection_lock.json', 'w'), indent=1)
    print('locked', len(man))


if __name__ == '__main__':
    main(sys.argv[1])
