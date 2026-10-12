"""iter_124: 선정 24명의 수동 보고서 적격성 표를 Qwen 출력 이전에 잠근다(selected_reports.txt 전문을 읽고 작성).
기준: 뇌실주위 백질 위치의 직접 명시 + FLAIR 고신호 존재 또는 해당 부위 정상의 명시 + 명시적 예외 없는 상충 없음. 새 LLM 합의 없음.
원인 질환 불확실성(예: nonspecific)은 소견 존재 불확실성과 분리한다.
usage: python mr124_lock.py   # results/iter_124/data/eligibility_lock.json (없을 때만)
"""
import hashlib, json, os, time

OUT = 'results/iter_124/data/'
# (study_uid, eligible, span/근거, 비고)
TABLE = [
    ('TT53FFT7O2', True, 'Periventricular white matter, corona radiata, and centrum semiovale are normal.', ''),
    ('SAVMGYCZLK', True, 'Periventricular white matter, corona radiata, and centrum semiovale are normal.', ''),
    ('KD67D7KQXL', True, 'Periventricular white matter, corona radiata, and centrum semiovale are normal.',
     '전두엽 피질하 gliotic foci는 periventricular가 아닌 위치로 별도 명시'),
    ('ZWCO7HXJOQ', True, 'Periventricular white matter, corona radiata, and centrum semiovale are normal.', ''),
    ('D4J2Y37VXG', True, 'Periventricular white matter, corona radiata, and centrum semiovale are normal.', ''),
    ('HAITYVF4HG', True, 'Periventricular white matter, corona radiata, and centrum semiovale are normal.', ''),
    ('PVYHN23O53', True, 'Confluent T2-weighted and FLAIR hyperintense chronic nonspecific gliotic lesions ... periventricular deep white matter', ''),
    ('5CZ7PU7243', True, 'bilateral centrum semiovale, periventricular deep white matter, ... T2-weighted and FLAIR hyperintense ... gliotic lesions', ''),
    ('FANIG52IVO', True, 'T2-weighted FLAIR hyperintense signal increases are present in the periventricular white matter', ''),
    ('VLMJGANXM5', True, 'Hyperintense chronic ischemic gliotic lesions ... T2 and FLAIR ... periventricular deep white matter', ''),
    ('A4FF3CY7NN', True, 'T2-weighted FLAIR hyperintense signal increase secondary to chronic ischemic changes is observed in the periventricular white matter.', ''),
    ('UNWCBIWH2X', True, 'in the frontal lobe periventricular white matter, a signal change ... 6 mm ... hyperintense on FLAIR sequence',
     '단일 6mm 병소(소견 존재는 명시, 원인은 nonspecific). 시각 가시성은 보장되지 않음'),
    ('Y6AEBHGPOM', True, 'Periventricular white matter, corona radiata, and centrum semiovale are normal.', ''),
    ('L5RDS7PLUI', True, 'The periventricular white matter, centrum semiovale, peripheral white matter, and cerebral cortex are normal.', ''),
    ('SDZBI7EXA5', True, 'Periventricular white matter, centrum semiovale, peripheral white matter, and cerebral cortex are normal.',
     '전두엽 white matter <3mm gliotic foci는 periventricular 아닌 위치로 별도 명시'),
    ('QMM2MZX4QF', True, 'Periventricular white matter, corona radiata, and centrum semiovale are normal.', '경막 비후는 다른 소견'),
    ('4EA2PIGANW', True, 'Periventricular white matter, centrum semiovale, peripheral white matter and cerebral cortex are normal.', ''),
    ('IUWKNFCAHI', True, 'Periventricular white matter, centrum semiovale, peripheral white matter and cerebral cortex are normal.', ''),
    ('UDRBEZLREB', True, 'Multiple T2-weighted, FLAIR hyperintense postischemic gliotic lesions ... predominantly localized in the para- and periventricular areas',
     'motion artifact 언급'),
    ('DUTKTMTWNW', True, 'T2 and FLAIR hyperintense demyelinating plaques ... periventricular white matter, and juxtacortical white matter', '이전 검사와 비교, 병변 안정'),
    ('7YYNKXI6YW', False, 'Widespread T2 and FLAIR hyperintense ischemic-gliotic foci ... subcortical white matter-periventricular areas VS '
     '"No pathological intensity change was detected within the cerebral parenchyma."',
     '넓은 정상 문장과 국소 이상이 충돌하고 명시적 예외로 해소되지 않음 -> unknown, paired 점수에서 제외(대체 없음)'),
    ('EXOJXICQZE', True, 'T2A, FLAIR hyperintense punctate gliotic lesions ... predominantly in para- and periventricular areas', ''),
    ('HICZ263FTY', True, 'Patchy T2-weighted, FLAIR hyperintense gliosis areas ... both paraventricular and periventricular areas', ''),
    ('FSPS6H2VVS', True, 'Two non-specific T2 FLAIR hyperintense foci ... periventricular deep white matter in the left frontal lobe and left occipital lobe',
     '원인 nonspecific, 소견 존재는 명시'),
]


def main():
    c = json.load(open(OUT + 'candidates.json'))
    sel = {x['study_uid']: x for x in c if x['selected']}
    assert set(sel) == {t[0] for t in TABLE} and len(TABLE) == 24
    rows = []
    for sid, ok, span, note in TABLE:
        x = sel[sid]
        rows.append(dict(study_uid=sid, patient_uid=x['patient_uid'], batch_id=x['batch_id'], label=x['label'], stratum=x['stratum'],
                         rank_in_stratum=x['rank_in_stratum'], hash124=x['hash124'], eligible=ok, evidence_span=span, note=note))
    el = {}
    for r in rows:
        el.setdefault(r['stratum'], []).append(r['eligible'])
    n_by = {k: sum(v) for k, v in el.items()}
    proceed = all(v >= 4 for v in n_by.values()) and len(n_by) == 4
    lock = dict(rule='mr124_eligibility_v1', locked_at=time.strftime('%Y-%m-%dT%H:%M:%S'), qwen_outputs_exist_at_lock=False,
                sources={'candidates.json': hashlib.sha256(open(OUT + 'candidates.json', 'rb').read()).hexdigest(),
                         'selected_reports.txt': hashlib.sha256(open(OUT + 'selected_reports.txt', 'rb').read()).hexdigest(),
                         'iter123_selection_lock': hashlib.sha256(open('results/iter_123/data/selection_lock.json', 'rb').read()).hexdigest(),
                         'mr124_lock.py': hashlib.sha256(open('mr124_lock.py', 'rb').read()).hexdigest()},
                n_selected=24, n_eligible=sum(r['eligible'] for r in rows), eligible_by_stratum=n_by, proceed=proceed, rows=rows)
    p = OUT + 'eligibility_lock.json'
    assert not os.path.exists(p)
    json.dump(lock, open(p, 'w'), indent=1)
    print(lock['n_eligible'], n_by, proceed)


if __name__ == '__main__':
    main()
