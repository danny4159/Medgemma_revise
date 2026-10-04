"""iter_073/074: rk73_audit/rk73_fetch fixture 검사 (코드 검증, 환자 성능 아님).

iter_074: import 시 결과 경로를 만들거나 iter_073 산출물을 덮어쓰지 않는다. 결과는 --out(새 iter_074 경로)에만 쓴다.
(1) iter_073의 순수 함수 의미 fixture, (2) 수정된 production 진입점의 접근·hash·출력 경계 fixture(synthetic), (3) 실제 허용 파일의 독립 재집계.
실제 통합 원 label은 열지 않는다.
"""
import argparse, collections, csv, hashlib, json, os, shutil, sys, time
import pandas as pd
import rk73_audit as A
import rk73_fetch as F

checks = []


def chk(name, ok, detail=''):
    checks.append({'name': name, 'ok': bool(ok), 'detail': str(detail)})


def raises(exc, fn, *a, **k):
    try:
        fn(*a, **k)
    except exc as e:
        return True, type(e).__name__ + ': ' + str(e)[:120]
    except Exception as e:  # 다른 예외는 의도한 분기가 아님
        return False, 'WRONG ' + type(e).__name__ + ': ' + str(e)[:120]
    return False, 'no exception'


class Spy:
    """pd.read_csv/json.load/grade_status 호출을 기록."""
    def __init__(self):
        self.csv, self.json, self.grade = [], [], 0

    def __enter__(self):
        self.o_csv, self.o_json, self.o_grade = pd.read_csv, json.load, A.grade_status
        spy = self

        def rc(p, *a, **k):
            spy.csv.append(str(p)); return spy.o_csv(p, *a, **k)

        def jl(f, *a, **k):
            n = getattr(f, 'name', str(f))
            if 'manifest' not in n:  # provenance manifest 읽기는 parser 호출이 아님
                spy.json.append(n)
            return spy.o_json(f, *a, **k)

        def gs(v):
            spy.grade += 1; return spy.o_grade(v)
        pd.read_csv, json.load, A.grade_status = rc, jl, gs
        return self

    def __exit__(self, *e):
        pd.read_csv, json.load, A.grade_status = self.o_csv, self.o_json, self.o_grade


def pure_fixtures():
    chk('status_zero_is_ok', A.grade_status(0) == ('ok', 0))
    chk('status_none_missing', A.grade_status(None)[0] == 'missing')
    chk('status_empty_dot_missing', A.grade_status('')[0] == 'missing' and A.grade_status('.')[0] == 'missing')
    chk('status_missing_not_zero', A.grade_status('.')[1] is None)
    chk('status_5_out_of_range', A.grade_status('5')[0] == 'out_of_range' and A.grade_status(4)[0] == 'out_of_range' and A.grade_status(-1)[0] == 'out_of_range')
    chk('status_bool_rejected', A.grade_status(True)[0] == 'bad_type')
    chk('status_string_digit', A.grade_status('2') == ('string_ok', 2))
    chk('status_garbage', A.grade_status('abc')[0] == 'bad_type')
    good = {'bounding_box': [1, 2, 3, 4, 5, 6], 'final_diagnosis': {'femur_medial_central_cartilage_lesion': {'size': 0, 'depth': 0}}}
    chk('cartilage_extract', A.cartilage_entry(good) == ('femur_medial_central', 0, 0))
    chk('cartilage_missing_size_key', A.cartilage_entry({'final_diagnosis': {'patella_medial_cartilage_lesion': {'depth': 1}}}) == ('patella_medial', None, 1))
    chk('non_cartilage_skipped', A.cartilage_entry({'final_diagnosis': {'patella_medial_BML': {'x': 1}}}) is None)
    chk('multi_key_skipped', A.cartilage_entry({'final_diagnosis': {'a_cartilage_lesion': {}, 'b_cartilage_lesion': {}}}) is None)
    chk('prompt_subregion', A.prompt_subregion_ok('can you diagnose cartilage lesions in the femur medial central subregion?', 'femur_medial_central')
        and not A.prompt_subregion_ok('cartilage lesions in the patella medial subregion', 'patella_lateral'))
    chk('test_answer_file_rejected', raises(ValueError, A.guard_not_test, '/x/generate_data/test.json')[0])
    chk('test_balanced_rejected', raises(ValueError, A.guard_not_test, '/x/generate_data/test_balanced.json')[0])
    chk('combined_label_path_rejected_even_without_test_name', raises(ValueError, A.guard_not_test, '/x/labels/taxonomymatch_kMRI_SQ_MOAKS_BICL00.csv')[0])
    chk('train_val_allowed', A.guard_not_test('/x/generate_data/train.json') is None and A.guard_not_test('/x/generate_data/val.json') is None)
    chk('norm_img', A.norm_img('../data/images/9/00M/a_1.nii.gz') == A.norm_img('/data/images/9/00M/a_1.nii.gz') == '/data/images/9/00M/a_1.nii.gz')
    rowsA = [('SQ', '65', {'patella_medial': ('2', '0')}), ('FNIH', '0.1', {'patella_medial': ('0', '0')})]
    st, c, n, m, b = A.orig_candidates(rowsA, 'patella_medial', 0)
    chk('conflict_rows_ambiguous', st == 'ambiguous' and c == [0, 2] and n == 2)
    st, c, *_ = A.orig_candidates([('SQ', '65', {'patella_medial': ('.', '0')})], 'patella_medial', 0)
    chk('missing_only_is_no_valid', st == 'no_valid' and c == [])
    st, c, *_ = A.orig_candidates([('SQ', '65', {'patella_medial': ('', '0')}), ('SQ', '22', {'patella_medial': ('1', '0')})], 'patella_medial', 0)
    chk('missing_plus_value_unique', st == 'unique' and c == [1])
    # 같은 값의 복수 후보 행도 unique(= 유효 후보 값 하나). 원 행 하나를 뜻하지 않는다.
    st, c, n, *_ = A.orig_candidates([('SQ', '65', {'patella_medial': ('1', '0')}), ('FNIH', '0.1', {'patella_medial': ('1', '0')})], 'patella_medial', 0)
    chk('same_value_multi_rows_unique_means_one_value', st == 'unique' and c == [1] and n == 2)
    st, c, n, m, b = A.orig_candidates([('SQ', '65', {'patella_medial': ('0', '5')})], 'patella_medial', 1)
    chk('depth_5_bad_code', st == 'no_valid' and b == 1)
    chk('majority_tie_lower', A.majority(collections.Counter({0: 3, 2: 3, 1: 1})) == 0)
    tr = pd.DataFrame({'subregion': ['s'] * 5, 'size': [2, 2, 0, 1, 2], 'size_status': ['ok'] * 5})
    va = pd.DataFrame({'subregion': ['s'] * 4, 'size': [2, 0, 2, 1], 'size_status': ['ok'] * 4, 'img': list('abcd')})
    v, rule = A.prior_scores(tr, va, by_sub=False)
    sc = A.score(v)
    chk('prior_global_rule', rule == 2 and abs(sc['accuracy'] - 0.5) < 1e-12)
    chk('recall_undefined_not_zero', sc['recall_by_grade']['3']['recall'] is None and sc['recall_by_grade']['3']['support'] == 0)
    chk('macro_over_defined_only', abs(sc['macro_recall_defined_classes'] - (0 + 1.0 + 0) / 3) < 1e-12)
    tr2 = pd.DataFrame({'subregion': ['s'] * 3, 'size': [None, 2, 2], 'size_status': ['missing', 'ok', 'ok']})
    v2, rule2 = A.prior_scores(tr2, va.assign(size_status=['ok', 'ok', 'missing', 'ok']), by_sub=False)
    chk('missing_excluded_from_prior', rule2 == 2 and len(v2) == 3)
    # train-only 불변성: val 값을 바꿔도 규칙(train-only majority)은 같다
    v3, rule3 = A.prior_scores(tr, va.assign(size=[0, 0, 0, 0]), by_sub=False)
    chk('prior_rule_train_only_invariant', rule3 == rule)
    chk('subregion_majority_without_class', A.majority(collections.Counter()) is None)


# ---- synthetic 경계 fixture ----
def sha(b):
    return hashlib.sha256(b).hexdigest()


def build_fx(root):
    """<root>/raw/data/... 와 <root>/manifest.json. 허용 파일 + (금지) 통합 label/test json."""
    if os.path.exists(root):
        shutil.rmtree(root)
    raw = os.path.join(root, 'raw')
    D = os.path.join(raw, 'data')
    for d in ('split_files', 'generate_data', 'labels'):
        os.makedirs(os.path.join(D, d))
    cols = ','.join(A.ID_COLS)

    def split_csv(rows):
        return cols + '\n' + ''.join('%s,%s,st,se,%s,p,/data/images/%s/%s/%s.nii.gz,l\n' % (pid, t, sd, pid, t, sd) for pid, t, sd in rows)
    sp = {'train': [('1', '00M', 'R'), ('1', '00M', 'L'), ('2', '00M', 'R')], 'val': [('3', '00M', 'R')], 'test': [('4', '00M', 'R')]}
    files = {}
    for s, rows in sp.items():
        files['data/split_files/%s_split.csv' % s] = split_csv(rows).encode()
    files['data/split_files/all_studies.csv'] = split_csv(sum(sp.values(), [])).encode()

    def js(rows, sizes):
        out = []
        for (pid, t, sd), sz in zip(rows, sizes):
            out.append({'image': '/data/images/%s/%s/%s.nii.gz' % (pid, t, sd), 'prompt': 'cartilage lesions in the patella medial subregion',
                        'final_diagnosis': {'final_diagnosis': {'patella_medial_cartilage_lesion': {'size': sz, 'depth': 0}}}})
        return json.dumps(out).encode()
    files['data/generate_data/train.json'] = js(sp['train'], [0, 2, 0])
    files['data/generate_data/val.json'] = js(sp['val'], [0])
    man = {'repo': F.REPO, 'revision': F.REV, 'files': {k: {'bytes': len(v), 'sha256': sha(v)} for k, v in files.items()}}
    for k, v in files.items():
        open(os.path.join(raw, k), 'wb').write(v)
    # 금지 파일(존재해도 읽히면 안 됨): 통합 label(test 환자 행 포함)과 test 답변
    open(os.path.join(D, 'labels/taxonomymatch_kMRI_SQ_MOAKS_BICL00.csv'), 'w').write('ID,SIDE,VERSION,V00MCMPM,V00MCMPM.1\n1,R,65,0,0\n4,R,65,3,3\n')
    open(os.path.join(D, 'generate_data/test.json'), 'w').write('[]')
    mp = os.path.join(root, 'manifest.json')
    json.dump(man, open(mp, 'w'))
    return raw, mp, sha(open(mp, 'rb').read()), files


def boundary_fixtures(base):
    # 1) load_moaks: 통합 label 파일이 존재해도 파일을 열기 전에 거부
    raw, mp, msha, files = build_fx(os.path.join(base, 'fx_ok'))
    with Spy() as s:
        ok, d = raises(A.LabelScopeError, A.load_moaks)
        ok2, d2 = raises(A.LabelScopeError, A.load_moaks, os.path.join(raw, 'data'))
    chk('load_moaks_refused_before_read', ok and ok2 and not s.csv and not s.json, d + ' | read_csv=%d' % len(s.csv))
    # 2) moaks_lookup: scope 미확인 표 거부, train_val_only 표시 표는 기존 의미대로 집계
    df = pd.DataFrame({'ID': ['1'], 'SIDE': ['R'], 'VERSION': ['65']})
    ok, d = raises(A.LabelScopeError, A.moaks_lookup, {('BICL00', 'SQ'): df})
    chk('moaks_lookup_unscoped_refused', ok, d)
    # 3) main --original-label-link: 어떤 파일도 읽기 전에 거부
    out_bad = os.path.join(base, 'out_olink')
    with Spy() as s:
        ok, d = raises(A.LabelScopeError, A.main, ['--raw', os.path.join(raw, 'data'), '--out', out_bad, '--manifest', mp, '--manifest-sha256', msha, '--original-label-link'])
    chk('main_original_label_link_refused_before_any_read', ok and not s.csv and not s.json and not os.path.exists(out_bad), d)
    # 4) 정상 train/val fixture: 처리되며 label 파일은 읽히지 않는다
    out_ok = os.path.join(base, 'out_ok')
    with Spy() as s:
        A.main(['--raw', os.path.join(raw, 'data'), '--out', out_ok, '--manifest', mp, '--manifest-sha256', msha])
    rep = json.load(open(os.path.join(out_ok, 'annotation_audit.json')))
    chk('allowed_fixture_processed', rep['original_label_linkage']['status'].startswith('deferred') and rep['json_stats']['train']['n_cartilage_rows'] == 3 and len(rep['input_sha256']) == 6)
    chk('allowed_fixture_never_reads_labels_or_test_json', not any('labels' in p or 'test.json' in p for p in s.csv + s.json), (s.csv + s.json)[:3])
    chk('allowed_fixture_test_split_id_only_used_for_overlap', rep['overlap']['patients_train_test'] == 0 and rep['split_files']['test']['patients'] == 1)
    chk('prior_unchanged_semantics_fixture', rep['train_only_prior']['global_majority']['rule'] == 0)
    # 5) 출력 경계: 기존 결과 덮어쓰기/iter_074 밖 경로 거부
    chk('main_refuses_overwrite', raises(ValueError, A.main, ['--raw', os.path.join(raw, 'data'), '--out', out_ok, '--manifest', mp, '--manifest-sha256', msha])[0])
    chk('main_refuses_iter073_out', raises(ValueError, A.main, ['--raw', os.path.join(raw, 'data'), '--out', os.path.join(A.ROOT, 'results/iter_073'), '--manifest', mp, '--manifest-sha256', msha])[0])
    # 6) hash 변조: 같은 크기 byte 변조는 parser 호출 전에 거부
    p = os.path.join(raw, 'data/generate_data/train.json')
    b = bytearray(files['data/generate_data/train.json']); i = b.index(b'0'); b[i:i + 1] = b'1'
    assert len(b) == len(files['data/generate_data/train.json'])
    open(p, 'wb').write(bytes(b))
    out_t = os.path.join(base, 'out_tamper')
    with Spy() as s:
        ok, d = raises(F.ProvenanceError, A.main, ['--raw', os.path.join(raw, 'data'), '--out', out_t, '--manifest', mp, '--manifest-sha256', msha])
    chk('same_size_byte_tamper_rejected_before_parse', ok and not s.csv and not s.json and s.grade == 0 and not os.path.exists(out_t), d)
    open(p, 'wb').write(files['data/generate_data/train.json'])
    # 7) revision / manifest 오류
    man = json.load(open(mp)); man['revision'] = 'deadbeef'
    mp2 = os.path.join(base, 'fx_ok/manifest_badrev.json'); json.dump(man, open(mp2, 'w'))
    chk('wrong_revision_rejected', raises(F.ProvenanceError, F.verify_allowed, os.path.dirname(os.path.join(raw, 'data')), A.NEEDED, mp2, sha(open(mp2, 'rb').read()))[0])
    chk('manifest_hash_mismatch_rejected', raises(F.ProvenanceError, F.verify_allowed, raw, A.NEEDED, mp, '0' * 64)[0])
    chk('manifest_missing_rejected', raises(F.ProvenanceError, F.verify_allowed, raw, A.NEEDED, os.path.join(base, 'nope.json'), msha)[0])
    man = json.load(open(mp)); del man['files']['data/split_files/val_split.csv']
    mp3 = os.path.join(base, 'fx_ok/manifest_missing_entry.json'); json.dump(man, open(mp3, 'w'))
    chk('file_not_in_manifest_rejected', raises(F.ProvenanceError, F.verify_allowed, raw, A.NEEDED, mp3, sha(open(mp3, 'rb').read()))[0])
    os.rename(os.path.join(raw, 'data/split_files/val_split.csv'), os.path.join(raw, 'data/split_files/val_split.bak'))
    chk('missing_file_rejected_no_redownload', raises(F.ProvenanceError, F.verify_allowed, raw, A.NEEDED, mp, msha)[0])
    os.rename(os.path.join(raw, 'data/split_files/val_split.bak'), os.path.join(raw, 'data/split_files/val_split.csv'))
    chk('verify_ok_after_restore', len(F.verify_allowed(raw, A.NEEDED, mp, msha)) == 6)
    # 8) 금지 이름은 manifest에 있어도 거부 (파일명에 test가 없는 통합 label 포함)
    for nm in ('data/labels/taxonomymatch_kMRI_SQ_MOAKS_BICL00.csv', 'data/generate_data/test.json', 'data/generate_data/test_balanced.json', 'data/generate_data/other.json'):
        chk('forbidden_or_unlisted_rejected:' + nm.split('/')[-1], raises(F.ProvenanceError, F.verify_allowed, raw, [nm], mp, msha)[0])
    # 9) 허용 출처 내부의 환자/영상 membership 불일치는 grade 집계 전에 실패
    D = os.path.join(raw, 'data')
    bad = json.loads(files['data/generate_data/val.json']); bad[0]['image'] = '/data/images/9/00M/R.nii.gz'
    open(os.path.join(D, 'generate_data/val.json'), 'w').write(json.dumps(bad))
    with Spy() as s:
        ok, d = raises(A.MembershipError, A.extract_split, 'val', A.load_split('val', D), D)
    chk('membership_mismatch_fails_before_grade_parse', ok and s.grade == 0, d)
    open(os.path.join(D, 'generate_data/val.json'), 'wb').write(files['data/generate_data/val.json'])
    chk('extract_split_test_refused', raises(ValueError, A.extract_split, 'test', A.load_split('test', D), D)[0])
    # 10) fetch 진입점 출력 경계
    chk('fetch_out_must_be_new_iter074', raises(F.ProvenanceError, F.main, ['--out', os.path.join(A.ROOT, 'results/iter_073/x.json')])[0])


def real_checks(base, out_dir):
    # 실제 허용 파일의 고정 manifest 대조 (통합 label·test 답변은 읽지 않음)
    res = F.verify_allowed(F.RAW_DEFAULT, A.NEEDED)
    chk('real_allowed_files_match_pinned_manifest', len(res) == 6, len(res))
    chk('real_manifest_revision', F.load_pinned_manifest()['revision'] == F.REV)
    chk('real_combined_labels_refused_by_verifier', raises(F.ProvenanceError, F.verify_allowed, F.RAW_DEFAULT, ['data/labels/taxonomymatch_kMRI_SQ_MOAKS_BICL00.csv'])[0])
    # 독립 재집계 (허용된 train/val json만)
    rep = json.load(open(os.path.join(A.ROOT, 'results/iter_073/annotation_audit.json')))
    raw = A.RAW

    def indep(split):
        d = json.load(open(os.path.join(raw, 'generate_data/%s.json' % split)))
        cnt = collections.defaultdict(collections.Counter)
        for rec in d:
            for k, v in rec['final_diagnosis']['final_diagnosis'].items():
                if k.endswith('_cartilage_lesion'):
                    cnt[k[:-17]][v['size']] += 1
        return {s: dict(c) for s, c in cnt.items()}
    ind = {s: indep(s) for s in ('train', 'val')}
    for s in ('train', 'val'):
        mine = rep['distribution'][s]['size_by_subregion']
        chk('indep_counts_%s' % s, all({int(k): v for k, v in mine[sub].items()} == ind[s][sub] for sub in ind[s]) and set(mine) == set(ind[s]))
    rule = {sub: min(g for g, c in cs.items() if c == max(cs.values())) for sub, cs in ind['train'].items()}
    tot = sum(sum(cs.values()) for cs in ind['val'].values())
    corr = sum(cs.get(rule[sub], 0) for sub, cs in ind['val'].items())
    chk('indep_prior_subregion_acc', abs(corr / tot - rep['train_only_prior']['subregion_majority']['pooled_rows']['accuracy']) < 1e-12, corr / tot)
    gc = collections.Counter()
    for cs in ind['train'].values():
        gc.update(cs)
    g0 = min(g for g, c in gc.items() if c == max(gc.values()))
    chk('indep_prior_global_acc', abs(sum(cs.get(g0, 0) for cs in ind['val'].values()) / tot - rep['train_only_prior']['global_majority']['pooled_rows']['accuracy']) < 1e-12)

    def pids(s):
        with open(os.path.join(raw, 'split_files/%s_split.csv' % s)) as f:
            return {r['patient_id'] for r in csv.DictReader(f)}
    pt, pv, pe = pids('train'), pids('val'), pids('test')
    chk('indep_patient_disjoint', not (pt & pv) and not (pt & pe) and not (pv & pe), (len(pt), len(pv), len(pe)))
    chk('test_split_has_id_columns_only', A.load_split('test').columns.tolist()[:8] == A.ID_COLS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True, help='results/iter_074/tests 아래 새 디렉터리')
    ap.add_argument('--before', required=True, help='iter_073 산출물 hash 기록(전)')
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    if '/results/iter_074/' not in out + '/' or os.path.exists(os.path.join(out, 'fixtures.json')):
        raise SystemExit('출력은 새 iter_074 경로여야 한다')
    os.makedirs(out, exist_ok=True)
    t0 = time.time()
    pure_fixtures()
    boundary_fixtures(os.path.join(out, 'work'))
    real_checks(out, out)
    before = json.load(open(a.before))
    after = {p: F.sha(p) for p in before}
    chk('iter073_artifacts_unchanged', after == before, '%d files' % len(before))
    res = {'n': len(checks), 'passed': sum(c['ok'] for c in checks), 'wall_s': round(time.time() - t0, 2), 'checks': checks}
    json.dump(res, open(os.path.join(out, 'fixtures.json'), 'w'), indent=1)
    print(res['passed'], '/', res['n'])
    for c in checks:
        if not c['ok']:
            print('FAIL', c)
    sys.exit(0 if res['passed'] == res['n'] else 1)


if __name__ == '__main__':
    main()
