"""production 감사기를 import하지 않는 원 parquet·CSV 기반 독립 검산."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import pandas as pd

RESULT = Path('results/iter_130')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(name):
    return json.loads((RESULT / name).read_text())


def write_once(path, content):
    data = (json.dumps(content, ensure_ascii=False, indent=2) + '\n').encode()
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f'기존 산출물 덮어쓰기 거부: {path}')
        return
    with path.open('xb') as f:
        f.write(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seal', action='store_true')
    args = parser.parse_args()
    start = time.monotonic()
    checks = []

    def check(name, condition):
        checks.append({'name': name, 'pass': bool(condition)})
        if not condition:
            raise AssertionError(name)

    fetch = read('fetch.json')
    files = {e['name']: e for e in fetch['files'] if e['source'] == 'hf'}
    for entry in fetch['files']:
        check('source_digest:' + entry['source'] + ':' + entry['name'], digest(entry['path']) == entry['sha256'])
    check('published_parquet_sha', digest(files['data/test.parquet']['path']) ==
          '9fb3d82729f4de24e3b9f794496c4bcc50edf45ce9ed0b7f2b9b23c0c731d737')
    execution = read('audit_execution.json')
    for kind in ['code', 'inputs', 'output_hashes']:
        for name, expected in execution[kind].items():
            check(kind + ':' + name, digest(name) == expected)
    df = pd.read_parquet(files['data/test.parquet']['path'], filters=[('template', '=', 'L2.4')])
    original = json.loads(df.to_json(orient='records'))
    original.sort(key=lambda r: r['item_id'])
    check('full_original_row_snapshot', original == read('l24_rows.json'))
    check('item_unique', df.item_id.is_unique)
    check('single_timepoint_all_rows', df.study_uids.map(len).eq(1).all() and df.n_shown_tps.eq(1).all())
    check('single_sequence_all_rows', df.input_modalities.map(len).eq(1).all())
    df['study_uid'] = df.study_uids.map(lambda a: a[0])
    df['modality'] = df.input_modalities.map(lambda a: a[0])
    cs = pd.read_csv(files['cohort/braintrace_cohort_studies_7299.csv']['path'], dtype=str)
    cp = pd.read_csv(files['cohort/braintrace_cohort_patients_1778.csv']['path'], dtype=str)
    local_split_path = next(p for p in execution['inputs'] if p.endswith('/meta/splits.csv'))
    sp = pd.read_csv(local_split_path, dtype=str)
    check('unique_cohort_study_patient_and_split_keys', cs.study_uid.is_unique and cp.patient_uid.is_unique and sp.study_uid.is_unique)
    joined = df[['item_id', 'patient_id_anon', 'study_uid']].merge(
        cs[['study_uid', 'patient_uid']], on='study_uid', how='left', validate='many_to_one')
    joined = joined.merge(sp[['study_uid', 'patient_uid', 'split', 'batch_id']], on='study_uid',
                          how='left', validate='many_to_one', suffixes=('_cohort', '_split'))
    check('all_join_keys_present', not joined.isna().any().any())
    check('exact_patient_match', joined.patient_id_anon.eq(joined.patient_uid_cohort).all() and
          joined.patient_id_anon.eq(joined.patient_uid_split).all())
    check('all_patient_manifest_members', joined.patient_id_anon.isin(cp.patient_uid).all())
    planned_joins = read('joins.json')
    jj = {r['item_id']: r for r in planned_joins}
    check('join_unique_and_complete', len(jj) == len(planned_joins) == len(df))
    check('join_values_independent', all(jj[r.item_id]['patient_uid'] == r.patient_id_anon and
          jj[r.item_id]['study_uid'] == r.study_uid and jj[r.item_id]['mr_rate_split'] == r.split and
          jj[r.item_id]['batch_id'] == r.batch_id for r in joined.itertuples()))
    stats = read('statistics.json')
    expected = {
        'l24_rows': len(df), 'l24_unique_items': df.item_id.nunique(),
        'l24_unique_patients': df.patient_id_anon.nunique(), 'l24_unique_studies': df.study_uid.nunique(),
        'track': df.track.value_counts().to_dict(), 'gt_distribution': df.gt_value.value_counts().to_dict(),
        'modality_combinations': df.modality.value_counts().to_dict(),
        'slice_rules': df.slice_selection_rule.value_counts().to_dict(),
        'mr_rate_row_splits': joined.split.value_counts().to_dict(),
        'mr_rate_unique_study_splits': joined.drop_duplicates('study_uid').split.value_counts().to_dict(),
        'mr_rate_patient_splits': joined.groupby('split').patient_id_anon.nunique().to_dict(),
        'question_structures': df.question.nunique(), 'cohort_patients': len(cp), 'cohort_studies': len(cs),
        'local_split_studies': len(sp), 'multiple_modalities_in_one_row': 0,
    }
    decoded = [json.loads(s) for s in df.rubric_json]
    expected['evidence_sources'] = dict(Counter(r['evidence_source'] for r in decoded))
    expected['rubric_field_presence'] = dict(Counter(k for r in decoded for k in r))
    expected['three_d_origin_pairs'] = sum('item_origin_id' in r for r in decoded)
    expected['question_rubric_structures'] = len({(q, tuple(sorted(r))) for q, r in zip(df.question, decoded)})
    expected['cross_sequence_study_count'] = int(df.groupby('study_uid').modality.nunique().gt(1).sum())
    expected['repeated_study_count'] = int(df.groupby('study_uid').size().gt(1).sum())
    for key, val in expected.items():
        check('statistic:' + key, stats[key] == val)
    check('patient_split_disjoint', joined.groupby('patient_id_anon').split.nunique().eq(1).all())
    check('rubric_option_binding', all(rub['item_id'] == row['item_id'] and
          rub['gt_value'] == rub['gt_option_text'] == row['gt_value'] == row['options'][rub['gt_option_index']]
          for row, rub in zip(json.loads(df.to_json(orient='records')), decoded)))
    check('scalar_only_truth_schema', all(set(r) <= {'item_id', 'template_id', 'authored_by', 'authored_at',
          'gt_value', 'gt_option_text', 'gt_option_index', 'evidence_source', 'evidence_quote', 'item_origin_id'} for r in decoded))
    rep = read('structures_and_representatives.json')
    raw_index = {r['item_id']: r for r in original}
    check('representative_originals', all(raw_index[r['item_id']] == r for r in rep['rows']))
    check('all_structure_coverage', len(rep['structures']) == expected['question_rubric_structures'] and
          sum(s['n_rows'] for s in rep['structures']) == len(df))
    check('structure_members_and_counterexamples', all(
        (raw_index[i]['question'], sorted(json.loads(raw_index[i]['rubric_json']))) == (s['question'], s['rubric_keys'])
        for s in rep['structures'] for i in s['representative_ids']))
    judgments = read('judgment_tables.json')
    check('four_tables_complete', len(judgments) == len(df) and len({r['item_id'] for r in judgments}) == len(df) and
          {r['item_id'] for r in judgments} == set(df.item_id))
    check('judgment_sources_and_splits', all(r['evidence_quote'] == json.loads(raw_index[r['item_id']]['rubric_json'])['evidence_quote']
          and r['development_confirmation']['mr_rate_split'] == jj[r['item_id']]['mr_rate_split'] for r in judgments))
    check('no_eligible_claim_from_missing_truth', all(not r['comparison_eligible'] and
          r['sequence_truth']['sequence_keyed_truth_vector'] == '미제공' for r in judgments))
    check('no_clinical_visibility_certification', all('미검증' in r['observation_link']['lesion_visible_in_render'] for r in judgments))
    decision = read('decision.json')
    check('negative_data_scope_and_no_model_claim', decision['data_result'] == 'negative_for_planned_comparison' and
          not decision['valid_experiment'] and not decision['model_or_training_run'] and not decision['success_action_triggered'])
    check('test_role_retained', not decision['exposure']['braintrace_test_converted_to_development'])
    input_digests = {str(p): digest(p) for p in RESULT.glob('*.json') if p.name not in
                     ['verification.json', 'completion.json']}
    content = {'all_pass': True, 'checks': checks, 'n_checks': len(checks),
               'verified_files': input_digests, 'code': execution['code'],
               'finished_at': datetime.now(timezone.utc).isoformat(), 'wall_s': time.monotonic() - start,
               'independence': 'production 감사기 import 없음; pandas parquet/CSV merge와 별도 집계',
               'scope': '원행·통계·환자/study join·대표 원문 연결 검산; 임상 정답·영상 가시성 검증 아님'}
    if (RESULT / 'verification.json').exists():
        old = read('verification.json')
        check('previous_verification_binding', old['all_pass'] and old['verified_files'] == input_digests and
              old['code'] == execution['code'])
    else:
        write_once(RESULT / 'verification.json', content)
    if args.seal:
        if (RESULT / 'completion.json').exists():
            old = read('completion.json')
            for path, expected_sha in old['files'].items():
                check('completion:' + path, digest(path) == expected_sha)
        else:
            check('human_report_exists', (RESULT / 'data_audit.md').exists())
            write_once(RESULT / 'completion.json', {
                'state': 'metadata_audit_complete', 'valid_experiment': False,
                'decision': decision['decision'], 'self_check': 'PASS',
                'finished_at': datetime.now(timezone.utc).isoformat(),
                'verification_sha256': digest(RESULT / 'verification.json'),
                'files': {str(p): digest(p) for p in RESULT.iterdir() if p.is_file()},
                'code': execution['code'], 'gpu_requests': 0, 'mri_download_bytes': 0})
    print(json.dumps({'all_pass': True, 'n_checks': len(checks), 'wall_s': time.monotonic() - start,
                      'sealed': args.seal}))


if __name__ == '__main__':
    main()
