"""iter_073: rk73_audit fixture 검사(코드 검증, 환자 성능 아님) + 원 JSON/CSV에서 독립 구현한 주요 count·prior 대조."""
import collections, csv, json, os, sys
import pandas as pd
import rk73_audit as A

OUT = os.path.join(A.OUT, 'tests')
os.makedirs(OUT, exist_ok=True)
checks = []


def chk(name, ok, detail=''):
    checks.append({'name': name, 'ok': bool(ok), 'detail': str(detail)})


# ---- fixtures ----
# null 대 0
chk('status_zero_is_ok', A.grade_status(0) == ('ok', 0))
chk('status_none_missing', A.grade_status(None)[0] == 'missing')
chk('status_empty_dot_missing', A.grade_status('')[0] == 'missing' and A.grade_status('.')[0] == 'missing')
chk('status_missing_not_zero', A.grade_status('.')[1] is None)
# 잘못된 grade
chk('status_5_out_of_range', A.grade_status('5')[0] == 'out_of_range' and A.grade_status(4)[0] == 'out_of_range' and A.grade_status(-1)[0] == 'out_of_range')
chk('status_bool_rejected', A.grade_status(True)[0] == 'bad_type')
chk('status_string_digit', A.grade_status('2') == ('string_ok', 2))
chk('status_garbage', A.grade_status('abc')[0] == 'bad_type')
# 연골 항목 추출
good = {'bounding_box': [1, 2, 3, 4, 5, 6], 'final_diagnosis': {'femur_medial_central_cartilage_lesion': {'size': 0, 'depth': 0}}}
chk('cartilage_extract', A.cartilage_entry(good) == ('femur_medial_central', 0, 0))
chk('cartilage_missing_size_key', A.cartilage_entry({'final_diagnosis': {'patella_medial_cartilage_lesion': {'depth': 1}}}) == ('patella_medial', None, 1))
chk('non_cartilage_skipped', A.cartilage_entry({'final_diagnosis': {'patella_medial_BML': {'x': 1}}}) is None)
chk('multi_key_skipped', A.cartilage_entry({'final_diagnosis': {'a_cartilage_lesion': {}, 'b_cartilage_lesion': {}}}) is None)
chk('prompt_subregion', A.prompt_subregion_ok('can you diagnose cartilage lesions in the femur medial central subregion?', 'femur_medial_central')
    and not A.prompt_subregion_ok('cartilage lesions in the patella medial subregion', 'patella_lateral'))
# test 답변 거부
try:
    A.guard_not_test('/x/generate_data/test.json'); rej = False
except ValueError:
    rej = True
chk('test_answer_file_rejected', rej)
try:
    A.guard_not_test('/x/generate_data/test_balanced.json'); rej2 = False
except ValueError:
    rej2 = True
chk('test_balanced_rejected', rej2)
chk('train_val_allowed', A.guard_not_test('/x/generate_data/train.json') is None and A.guard_not_test('/x/generate_data/val.json') is None)
# 경로 정규화
chk('norm_img', A.norm_img('../data/images/9/00M/a_1.nii.gz') == A.norm_img('/data/images/9/00M/a_1.nii.gz') == '/data/images/9/00M/a_1.nii.gz')
# 중복/충돌 join 보존 (임의 첫 행 선택 금지)
rowsA = [('SQ', '65', {'patella_medial': ('2', '0')}), ('FNIH', '0.1', {'patella_medial': ('0', '0')})]
st, c, n, m, b = A.orig_candidates(rowsA, 'patella_medial', 0)
chk('conflict_rows_ambiguous', st == 'ambiguous' and c == [0, 2] and n == 2)
st, c, *_ = A.orig_candidates([('SQ', '65', {'patella_medial': ('.', '0')})], 'patella_medial', 0)
chk('missing_only_is_no_valid', st == 'no_valid' and c == [])
st, c, *_ = A.orig_candidates([('SQ', '65', {'patella_medial': ('', '0')}), ('SQ', '22', {'patella_medial': ('1', '0')})], 'patella_medial', 0)
chk('missing_plus_value_unique', st == 'unique' and c == [1])
st, c, n, m, b = A.orig_candidates([('SQ', '65', {'patella_medial': ('0', '5')})], 'patella_medial', 1)
chk('depth_5_bad_code', st == 'no_valid' and b == 1)
# majority 동률은 낮은 grade, 빈 class recall 미정의
chk('majority_tie_lower', A.majority(collections.Counter({0: 3, 2: 3, 1: 1})) == 0)
tr = pd.DataFrame({'subregion': ['s'] * 5, 'size': [2, 2, 0, 1, 2], 'size_status': ['ok'] * 5})
va = pd.DataFrame({'subregion': ['s'] * 4, 'size': [2, 0, 2, 1], 'size_status': ['ok'] * 4, 'img': list('abcd')})
v, rule = A.prior_scores(tr, va, by_sub=False)
sc = A.score(v)
chk('prior_global_rule', rule == 2 and abs(sc['accuracy'] - 0.5) < 1e-12)
chk('recall_undefined_not_zero', sc['recall_by_grade']['3']['recall'] is None and sc['recall_by_grade']['3']['support'] == 0)
chk('macro_over_defined_only', abs(sc['macro_recall_defined_classes'] - (0 + 1.0 + 0) / 3) < 1e-12)
# missing size 행은 prior 학습/평가에서 제외
tr2 = pd.DataFrame({'subregion': ['s'] * 3, 'size': [None, 2, 2], 'size_status': ['missing', 'ok', 'ok']})
v2, rule2 = A.prior_scores(tr2, va.assign(size_status=['ok', 'ok', 'missing', 'ok']), by_sub=False)
chk('missing_excluded_from_prior', rule2 == 2 and len(v2) == 3)
# 환자 누수: 같은 환자가 train/val에 있으면 감지
P1, P2 = {'1', '2'}, {'2', '3'}
chk('patient_overlap_detect', len(P1 & P2) == 1)

# ---- 실제 자료의 독립 재집계 ----
rep = json.load(open(os.path.join(A.OUT, 'annotation_audit.json')))


def indep(split):
    d = json.load(open(os.path.join(A.RAW, 'generate_data/%s.json' % split)))
    cnt = collections.defaultdict(collections.Counter)
    for rec in d:
        fdd = rec['final_diagnosis']['final_diagnosis']
        for k, v in fdd.items():
            if k.endswith('_cartilage_lesion'):
                cnt[k[:-17]][v['size']] += 1
    return {s: dict(c) for s, c in cnt.items()}


ind = {s: indep(s) for s in ('train', 'val')}
for s in ('train', 'val'):
    mine = rep['distribution'][s]['size_by_subregion']
    same = all({int(k): v for k, v in mine[sub].items()} == ind[s][sub] for sub in ind[s]) and set(mine) == set(ind[s])
    chk('indep_counts_%s' % s, same)
# 독립 prior: pooled accuracy (subregion majority, 동률 낮은 grade)
rule = {sub: min(g for g, c in cs.items() if c == max(cs.values())) for sub, cs in ind['train'].items()}
corr = sum(cs.get(rule[sub], 0) for sub, cs in ind['val'].items())
tot = sum(sum(cs.values()) for cs in ind['val'].values())
chk('indep_prior_subregion_acc', abs(corr / tot - rep['train_only_prior']['subregion_majority']['pooled_rows']['accuracy']) < 1e-12, corr / tot)
gc = collections.Counter()
for cs in ind['train'].values():
    gc.update(cs)
g0 = min(g for g, c in gc.items() if c == max(gc.values()))
gcorr = sum(cs.get(g0, 0) for cs in ind['val'].values())
chk('indep_prior_global_acc', abs(gcorr / tot - rep['train_only_prior']['global_majority']['pooled_rows']['accuracy']) < 1e-12, gcorr / tot)
# 환자 교집합 (csv 모듈)
def pids(s):
    with open(os.path.join(A.RAW, 'split_files/%s_split.csv' % s)) as f:
        return {r['patient_id'] for r in csv.DictReader(f)}
pt, pv, pe = pids('train'), pids('val'), pids('test')
chk('indep_patient_disjoint', not (pt & pv) and not (pt & pe) and not (pv & pe), (len(pt), len(pv), len(pe)))
chk('test_split_has_id_columns_only', A.load_split('test').columns.tolist()[:8] == A.ID_COLS)

res = {'n': len(checks), 'passed': sum(c['ok'] for c in checks), 'checks': checks}
json.dump(res, open(os.path.join(OUT, 'fixtures.json'), 'w'), indent=1)
print(res['passed'], '/', res['n'])
for c in checks:
    if not c['ok']:
        print('FAIL', c)
sys.exit(0 if res['passed'] == res['n'] else 1)
