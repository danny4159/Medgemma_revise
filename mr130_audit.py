"""고정 BrainTRACE L2.4 자료 조건 감사. 모델 실행이나 임상 정답 생성은 하지 않는다."""
import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import pyarrow.parquet as pq

from mr130_fetch import ROOT, OUT, CODE_REV, HF_REV, PARQUET_SHA, sha

SPLITS = Path('/home/test/.local/share/medgemma/mr_rate/meta/splits.csv')


def write(path, value):
    data = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f'기존 결과 불일치; 덮어쓰기 거부: {path}')
        return
    with path.open('xb') as f:
        f.write(data)


def counts(values):
    return dict(sorted(Counter(values).items()))


def unique_index(rows, key):
    result = {}
    for row in rows:
        k = row[key]
        if not k or k in result:
            raise ValueError(f'빈 ID 또는 중복 {key}: {k}')
        result[k] = row
    return result


def csv_rows(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def main():
    start = time.monotonic()
    fetch = json.loads((OUT / 'fetch.json').read_text())
    if fetch['hf_revision'] != HF_REV or fetch['code_revision'] != CODE_REV:
        raise ValueError('revision 불일치')
    for entry in fetch['files']:
        if sha(entry['path']) != entry['sha256']:
            raise ValueError(f"source 변조: {entry['path']}")
    if sha(ROOT / 'data/test.parquet') != PARQUET_SHA:
        raise ValueError('공개 parquet SHA 불일치')
    table = pq.read_table(ROOT / 'data/test.parquet', filters=[('template', '=', 'L2.4')])
    rows = sorted(table.to_pylist(), key=lambda r: r['item_id'])
    items = unique_index(rows, 'item_id')
    co_study = unique_index(csv_rows(ROOT / 'cohort/braintrace_cohort_studies_7299.csv'), 'study_uid')
    co_patient = unique_index(csv_rows(ROOT / 'cohort/braintrace_cohort_patients_1778.csv'), 'patient_uid')
    split = unique_index(csv_rows(SPLITS), 'study_uid')
    rubric = {}
    joins = []
    for row in rows:
        rub = json.loads(row['rubric_json'])
        rubric[row['item_id']] = rub
        assert row['template'] == 'L2.4' and rub['template_id'] == 'L2.4'
        assert rub['item_id'] == row['item_id']
        assert rub['gt_value'] == rub['gt_option_text'] == row['gt_value']
        assert row['options'][rub['gt_option_index']] == row['gt_value']
        assert len(row['options']) == len(set(row['options'])) == 5
        assert len(row['study_uids']) == row['n_shown_tps'] == 1
        for study in row['study_uids']:
            c, s = co_study[study], split[study]
            patient = row['patient_id_anon']
            assert patient == c['patient_uid'] == s['patient_uid']
            assert patient in co_patient
            joins.append({'item_id': row['item_id'], 'patient_uid': patient,
                          'study_uid': study, 'mr_rate_split': s['split'],
                          'batch_id': s['batch_id'], 'cohort_match': True,
                          'split_match': True, 'patient_match': True,
                          'cohort_modalities': c['modalities']})
    groups = defaultdict(list)
    for row in rows:
        groups[row['study_uids'][0]].append(row)
    multi = {study: group for study, group in groups.items()
             if len({tuple(row['input_modalities']) for row in group}) > 1}
    origins = []
    for row in rows:
        parent_id = rubric[row['item_id']].get('item_origin_id')
        if parent_id:
            parent = items[parent_id]
            for key in ['patient_id_anon', 'study_uids', 'input_modalities', 'question', 'options', 'gt_value']:
                assert row[key] == parent[key], (row['item_id'], key)
            assert rubric[row['item_id']]['evidence_quote'] == rubric[parent_id]['evidence_quote']
            origins.append({'item_id': row['item_id'], 'item_origin_id': parent_id,
                            'same_patient_study_modality_question_options_gt_quote': True})
    schema_groups = defaultdict(list)
    for row in rows:
        key = (row['question'], tuple(sorted(rubric[row['item_id']])))
        schema_groups[key].append(row)
    representative_ids = set()
    patterns = []
    for index, (key, members) in enumerate(sorted(schema_groups.items())):
        first = members[0]
        opposite = next((r for r in members if r['gt_value'] != first['gt_value']), None)
        ids = [first['item_id']] + ([opposite['item_id']] if opposite else [])
        representative_ids.update(ids)
        patterns.append({'structure_id': index, 'question': key[0], 'rubric_keys': list(key[1]),
                         'n_rows': len(members), 'representative_ids': ids,
                         'counterexample_definition': '같은 질문·rubric 구조의 다른 gt_value; 모델 반례가 아님'})
    # 원문이 판정을 바꿀 수 있는 명시적 대조 사례. L2.4 밖으로 확장하지 않는다.
    representative_ids.update(['bulk_v1_L2_4_001', 'bulk_v1_L2_4_002', 'bulk_v1_L2_4_003',
                               'bulk_v1_L2_4_039', 'bulk_v1_L2_4_057',
                               'bulk_v1_L2_4_102', 'bulk_v1_L2_4_103', 'bulk_v1_L2_4_106'])
    for group in multi.values():
        representative_ids.update(row['item_id'] for row in group)
    for label in sorted({r['gt_value'] for r in rows}):
        representative_ids.add(next(r['item_id'] for r in rows if r['gt_value'] == label))
    representative_rows = [items[i] for i in sorted(representative_ids)]
    per_item = []
    for row in rows:
        rub = rubric[row['item_id']]
        no_lesion = row['gt_value'] == 'no lesion present'
        per_item.append({
            'item_id': row['item_id'], 'study_uid': row['study_uids'][0],
            'input_modalities': row['input_modalities'], 'gt_value': row['gt_value'],
            'evidence_source': rub['evidence_source'], 'evidence_quote': rub['evidence_quote'],
            'sequence_truth': {'published_bucket': '확인',
                               'sequence_keyed_truth_vector': '미제공',
                               'reason': 'scalar gt_value와 보고서/diagnostic_class 인용만 있음; sequence별 독립 정답을 역추정하지 않음'},
            'target_identity': {'question_target': 'no lesion' if no_lesion else 'dominant lesion',
                                'lesion_instance_id': '미제공', 'lesion_coordinates': '미제공',
                                'cross_sequence_same_target': '해당 없음(무병변 bucket)' if no_lesion else '미보장'},
            'observation_link': {'patient_study_join': '확인', 'modality_plane_recipe': '확인',
                                 'exact_series_id': '미제공', 'lesion_slice_index': '미제공',
                                 'lesion_visible_in_render': '미검증; 영상 미반입·미표시',
                                 'slice_selection_rule': row['slice_selection_rule']},
            'development_confirmation': {'braintrace_role': 'test 유지',
                                         'mr_rate_split': next(j['mr_rate_split'] for j in joins if j['item_id'] == row['item_id']),
                                         'used_for_training_or_model_selection': False,
                                         'independent_model_confirmation': False},
            'comparison_eligible': False,
            'exclusion_reason': '공동 sequence 정답·동일 병변의 독립 신호 정답과 관측 연결이 보장되지 않음'
        })
    split_patients = {s: sorted({j['patient_uid'] for j in joins if j['mr_rate_split'] == s})
                      for s in sorted({j['mr_rate_split'] for j in joins})}
    for a, aa in split_patients.items():
        for b, bb in split_patients.items():
            if a != b:
                assert not set(aa) & set(bb), '환자 split 혼합'
    stats = {
        'source_parquet_rows': pq.ParquetFile(ROOT / 'data/test.parquet').metadata.num_rows,
        'l24_rows': len(rows), 'l24_unique_items': len(items),
        'l24_unique_patients': len({r['patient_id_anon'] for r in rows}),
        'l24_unique_studies': len(groups), 'track': counts(r['track'] for r in rows),
        'modality_combinations': counts('+'.join(r['input_modalities']) for r in rows),
        'multiple_modalities_in_one_row': sum(len(r['input_modalities']) > 1 for r in rows),
        'gt_distribution': counts(r['gt_value'] for r in rows),
        'gt_by_track': {track: counts(r['gt_value'] for r in rows if r['track'] == track)
                        for track in sorted({r['track'] for r in rows})},
        'slice_rules': counts(r['slice_selection_rule'] for r in rows),
        'evidence_sources': counts(rub['evidence_source'] for rub in rubric.values()),
        'field_empty_or_null': {k: sum(r[k] is None or r[k] == '' or r[k] == [] for r in rows) for k in table.column_names},
        'rubric_field_presence': counts(k for rub in rubric.values() for k in rub),
        'question_structures': len({r['question'] for r in rows}),
        'question_rubric_structures': len(schema_groups),
        'repeated_study_count': sum(len(v) > 1 for v in groups.values()),
        'cross_sequence_study_count': len(multi),
        'cross_sequence_groups': [{'study_uid': study, 'item_ids': [r['item_id'] for r in group],
                                   'modalities': sorted({m for r in group for m in r['input_modalities']}),
                                   'gt_values': sorted({r['gt_value'] for r in group}),
                                   'same_evidence_quote': len({rubric[r['item_id']]['evidence_quote'] for r in group}) == 1}
                                  for study, group in sorted(multi.items())],
        'three_d_origin_pairs': len(origins), 'joins_complete': len(joins),
        'join_mismatch': 0, 'mr_rate_row_splits': counts(j['mr_rate_split'] for j in joins),
        'mr_rate_unique_study_splits': counts(split[study]['split'] for study in groups),
        'mr_rate_patient_splits': {s: len(v) for s, v in split_patients.items()},
        'cohort_patients': len(co_patient), 'cohort_studies': len(co_study),
        'local_split_studies': len(split),
        'eligible_joint_independent_comparison_items': 0,
        'clinical_label_validity_certified': False,
    }
    write(OUT / 'l24_rows.json', rows)
    write(OUT / 'joins.json', joins)
    write(OUT / 'origin_pairs.json', origins)
    write(OUT / 'structures_and_representatives.json', {'structures': patterns, 'rows': representative_rows})
    write(OUT / 'judgment_tables.json', per_item)
    write(OUT / 'statistics.json', stats)
    report = {
        'decision': 'hold_current_l24_joint_independent_design',
        'data_result': 'negative_for_planned_comparison', 'valid_experiment': False,
        'reason': '공개 L2.4는 단일 sequence의 scalar bucket이며 동일 병변의 sequence별 정답·관측 연결이 없다',
        'scope': '현재 revision의 L2.4 공동 대 독립 sequence 비교; BrainTRACE 전체·MRI 전체·모델 능력 판정 아님',
        'success_action_triggered': False, 'gpu_diagnostic_recommendation': False,
        'model_or_training_run': False,
        'exposure': {'full_l24_answers_and_rubrics_read': len(rows),
                     'other_templates_analyzed': 0,
                     'incidental_schema_probe': 'schema 점검 중 최초 L1.1 원행 1개가 도구 출력에 노출됨; 분석·선정·실험에 사용하지 않음',
                     'braintrace_test_converted_to_development': False,
                     'mr_rate_train_overlap_does_not_restore_test_independence': True,
                     'future_blind_confirmation': '열람한 L2.4를 설계 선택 후 새 독립 확인 집단이라고 표현할 수 없음; 공식 train/dev 또는 미노출 정답 생성 규칙은 이번 자료에서 확인되지 않음'},
        'four_decisions': {
            'sequence_truth': '미충족: 모두 scalar bucket; 선택지 다섯 개는 단일 신호 class이며 sequence 조합 정답 아님',
            'same_target': '미충족: generic dominant lesion, instance ID·좌표 없음; 3개 cross-sequence study도 신호별 근거를 보장하지 않음',
            'observation': '부분 확인: 258/258 환자/study join과 renderer 접근 경로는 확인; 실제 series·대상 가시성은 미검증',
            'development_confirmation': 'test-only; MR-RATE train/val overlap을 새 독립 개발/확인 분리로 사용하지 않음'
        },
        'baseline_support': [
            {'baseline': 'sequence별 독립 VLM 판독 + 결정적 결합',
             'required': '동일 대상의 sequence별 정답 vector, 동일 영상의 공동 질문 및 고정 결합 규칙',
             'supported': False, 'reason': '정답 vector·공동 정답/선택지 미제공; 환자별 전형 신호 추론 금지'},
            {'baseline': '전문 병변 segmentation + 국소 intensity 규칙',
             'required': '병변 instance mask와 기준 정상 조직, sequence별 정합·가시성',
             'supported': False, 'reason': '해부학 예측 mask는 병변 정답 아님; 이 release에는 병변 mask·정상 대조 영역 없음; 미설치가 제외 근거 아님'},
            {'baseline': 'MRI 신호 분류기 + 규칙 / 직접 SFT',
             'required': '학습용 관측에 연결된 신호 label과 환자 분리 validation',
             'supported': '미확인', 'reason': '공식 test만 제공; 환자별 관측-정답 연결·학습 자료는 이번 계획에서 성립하지 않음; 설치/학습 미발주'}
        ],
        'renderer_notes': {
            'source': str(ROOT / f'official_code/{CODE_REV}/reproduction/render_images.py'),
            'series_rule': '169–184: coreg 두 디렉터리에서 modality·plane filename pattern에 맞는 첫 sorted 파일',
            'broadqa_rule': '211–220,338–365: override 없으면 axial shape[2]//2; lesion 위치 기반 아님',
            'three_d_rule': '312–331,660–676,870–878: n=16, 전체 axial depth에 균등 index; rule 이름 contiguous와 실제 구현이 다름',
            'affine_visibility': '원격 영상·렌더링 실행은 없음; 방향/정합/가시성 검증을 통과했다고 보고하지 않음'},
        'recommendation': '현재 L2.4 분해 비교 투자를 보류한다. 같은 metadata 준비 반복·MRI 반입·자동 학습을 요청하지 않는다.',
        'new_evidence_needed': '동일 병변 ID와 실제 관측에 연결된 sequence별 원 정답 및 개발/독립 확인 구성; 현재 승인으로 이를 추정 생성하지 않음',
    }
    write(OUT / 'decision.json', report)
    if not (OUT / 'audit_execution.json').exists():
        write(OUT / 'audit_execution.json', {
            'finished_at': datetime.now(timezone.utc).isoformat(), 'wall_s': time.monotonic() - start,
            'inputs': {str(p): sha(p) for p in [ROOT / 'data/test.parquet',
                       ROOT / 'cohort/braintrace_cohort_studies_7299.csv',
                       ROOT / 'cohort/braintrace_cohort_patients_1778.csv', SPLITS, OUT / 'fetch.json']},
            'code': {p: sha(p) for p in ['mr130_fetch.py', 'mr130_audit.py', 'mr130_verify.py']},
            'output_hashes': {str(p): sha(p) for p in OUT.glob('*.json') if p.name not in ['audit_execution.json', 'completion.json']},
            'gpu_requests': 0, 'training_updates': 0,
            'reuse_assets': [], 'seed': '결정적 전체 행 집계; stochastic 실행 없음'})
    print(json.dumps({'l24_rows': len(rows), 'patients': stats['l24_unique_patients'],
                      'studies': len(groups), 'decision': report['decision'], 'wall_s': time.monotonic() - start}))


if __name__ == '__main__':
    main()
