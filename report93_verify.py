"""iter_093 독립 verifier: report93_analyze.py 코드를 import하지 않고 원 JSON에서 핵심 수치를 다시 계산해 대조한다."""
import hashlib, json, re, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
R90 = ROOT / 'results/iter_090'
REC = R90 / 'recovery'
MAIN = ROOT / 'results/iter_093/main'
checks = []


def chk(name, ok, detail=''):
    checks.append(dict(name=name, ok=bool(ok), detail=str(detail)))


def L(p):
    return json.loads(Path(p).read_text())


T = L(R90 / 'data/T512/manifest.json')
V = L(R90 / 'data/V64/manifest.json')
tc = L(MAIN / 'target_composition.json')

# 1. 입력 manifest hash 재계산
im = L(MAIN / 'input_manifest.json')
bad = [k for k, h in im['files'].items() if hashlib.sha256((ROOT / k).read_bytes()).hexdigest() != h]
chk('input_manifest_hashes', not bad and im['n_files'] == len(im['files']), bad[:3])

# 2. target 구성: 독립 분류 (excluded index를 source_index로 제거)
def comp(rows):
    cls = dict(normal_only=0, abnormal_only=0, abnormal_plus_normal=0)
    ab_s = nm_s = 0
    for r in rows:
        ex = {e[0] for e in r['excluded_sentences']}
        keep = [s for s in r['findings'] if s['source_index'] not in ex]
        a = sum(1 for s in keep if s['abnormal']); n = len(keep) - a
        ab_s += a; nm_s += n
        cls['normal_only' if a == 0 else 'abnormal_only' if n == 0 else 'abnormal_plus_normal'] += 1
    return cls, ab_s, nm_s
for name, rows in (('T512', T), ('V64', V)):
    cls, a, n = comp(rows)
    d = tc[name]
    chk(f'target_{name}', cls == d['patient_class'] and a == d['abnormal_sentence'] and n == d['generic_normal_sentence'] + d['specific_normal_sentence'], (cls, a, n))
chk('T_V_patient_disjoint', not ({r['PatientID'] for r in T} & {r['PatientID'] for r in V}))

# 3. NLL: 평균 재현, 선택 재현, V64 순서 연결
nll = L(MAIN / 'nll_per_patient.json')
chk('nll_order_is_manifest', nll['image_ids'] == [r['ImageID'] for r in V] and nll['patient_ids'] == [r['PatientID'] for r in V])
vsha = hashlib.sha256((R90 / 'data/V64/manifest.json').read_bytes()).hexdigest()
tab = L(MAIN / 'nll_trajectories.json')
mean_ok = True
sel = {}
for m in 'RG':
    for lr in ('0.0001', '0.0002'):
        run = REC / f'train/{m}_lr{lr}'
        mean_ok &= L(run / 'config.json')['val_sha'] == vsha
        for e in (1, 2, 4, 6):
            v = L(run / f'validation_{e:02d}.json')
            a = nll['values'][f'{m}_lr{lr}'][str(e)]
            mean_ok &= a == v['per_patient'] and abs(np.mean(a) - v['report_nll']) < 1e-9
            mean_ok &= abs(tab['per_trajectory'][f'{m}_lr{lr}']['overall'][str(e)] - v['report_nll']) < 1e-9
            sel[(m, lr, e)] = v['report_nll']
chk('nll_means_and_val_sha', mean_ok)
lrs = {m: sorted(('0.0001', '0.0002'), key=lambda lr: (sel[(m, lr, 6)], float(lr)))[0] for m in 'RG'}
ce = sorted((1, 2, 4, 6), key=lambda e: (sum(sel[(m, lrs[m], e)] for m in 'RG'), e))[0]
fin = L(REC / 'selection/final.json')
chk('selection_reproduced', all(float(fin['selected'][m]['lr']) == float(lrs[m]) for m in 'RG') and fin['common_epoch'] == ce, (lrs, ce))
# 정상 전용 군 NLL 재계산 (R lr0.0002)
isn = [all(not s['abnormal'] for s in r['findings'] if s['source_index'] not in {e[0] for e in r['excluded_sentences']}) for r in V]
a = np.array(nll['values']['R_lr0.0002']['1'])
chk('group_nll_R2e4_e1', abs(a[isn].mean() - tab['per_trajectory']['R_lr0.0002']['normal_only']['1']) < 1e-9)

# 4. V32 recall: reference 확정 양성 atom 대비 strict match로 재계산
ref = {r['id']: r for r in L(R90 / 'semantic/V32_reference_v3.json')['rows']}
gen = L(MAIN / 'v32_generation.json')
view = L(MAIN / 'v32_patient_view.json')
specs = [('base@0', REC / 'semantic/epoch2/eval/per_output.json', 'base_report')]
for e in (2, 6):
    for m in 'RG':
        for lr in ('0.0001', '0.0002'):
            specs.append((f'{m}_lr{lr}@{e}', REC / f'semantic/epoch{e}/eval/per_output.json', f'{m}_lr{lr}_report'))
ok_rec = True; per_rec = {}
for key, p, cond in specs:
    out = [x for x in L(p) if x['condition'] == cond]
    ids = [x['image_id'] for x in out]
    ok_rec &= len(out) == 32 and len(set(ids)) == 32
    vals = []
    for x in out:
        pos = [a['id'] for a in ref[x['image_id']]['atoms'] if a['polarity'] == 'positive' and a['certainty'] == 'definite']
        if not pos:
            continue
        s = {m['ref'] for m in x['matches'] if m['status'] == 'strict'}
        vals.append(len(s & set(pos)) / len(pos))
    per_rec[key] = float(np.mean(vals))
    ok_rec &= len(vals) == 20 and abs(per_rec[key] - gen['conditions'][key]['strict_recall']) < 1e-9
chk('v32_strict_recall_independent', ok_rec, per_rec)

# 5. 정상문만 출력: 원문 텍스트 기반 독립 정의와 claim 기반 정의의 일치율
NORM = re.compile(r'^(no |normal|within normal|the lungs are clear|the heart size is normal|the mediastin|the visualized osseous|chest without|there is no)', re.I)
agree = tot = 0
for key, p, cond in specs:
    e = 0 if key.startswith('base') else int(key.split('@')[1])
    d = REC / ('validation/epoch2/base_report' if key.startswith('base') else f'validation/epoch{e}/{cond}')
    txt = {json.loads(l)['id'].split('|')[0]: json.loads(l)['text'] for l in (d / 'worker_0.jsonl').read_text().splitlines()}
    for row in view[key]:
        t = txt[row['image_id']]
        pieces = [s.strip() for s in re.split(r'(?<=\.)\s+|\n', re.sub(r'[\[\]]|FINDINGS:|IMPRESSION:', '', t)) if re.search(r'[A-Za-z]{3}', s)]
        text_normal = all(NORM.match(s) for s in pieces) if pieces else True
        tot += 1; agree += (text_normal == row['normal_only_output'])
chk('normal_only_text_vs_claim_agreement', agree / tot >= 0.9, f'{agree}/{tot}')

# 6. 쌍별 bootstrap 독립 재계산 (다른 seed, 근사 허용)
rng = np.random.default_rng(777)
def vec(key):
    return np.array([r['strict_recall'] for r in view[key] if r['positive_n']])
for name, a, b in (('G lr0.0001 epoch6-epoch2', 'G_lr0.0001@6', 'G_lr0.0001@2'), ('R lr0.0001 epoch6-epoch2', 'R_lr0.0001@6', 'R_lr0.0001@2'),
                   ('G-R lr0.0001 epoch2', 'G_lr0.0001@2', 'R_lr0.0001@2')):
    d = vec(a) - vec(b)
    bs = np.sort([d[rng.integers(0, 20, 20)].mean() for _ in range(10000)])
    c = gen['paired_contrasts'][name]
    chk(f'bootstrap_{name}', abs(d.mean() - c['mean']) < 1e-9 and abs(bs[249] - c['ci95'][0]) < 0.03 and abs(bs[9749] - c['ci95'][1]) < 0.03, (d.mean(), bs[249], bs[9749], c['ci95']))
    loo = [np.delete(d, i).mean() for i in range(20)]
    chk(f'loo_{name}', abs(min(loo) - c['loo_min']) < 1e-9 and abs(max(loo) - c['loo_max']) < 1e-9)

# 7. 의미 민감도: fixture 독립 재실행, claim anchor 원문 확인
sys.path.insert(0, str(ROOT))
import report93_fixtures as FX, report93_sens as S
sem = L(MAIN / 'semantic_sensitivity.json')
chk('fixtures_count_groups', len(FX.FIXTURES) >= 15 and set(f['group'] for f in FX.FIXTURES) == {'generic_normal', 'other_scope', 'acute_negation', 'specific_negation', 'location_attribute'}
    and all(any(f['group'] == g and f['expected'] == ex for f in FX.FIXTURES) for g in ('generic_normal', 'other_scope', 'acute_negation', 'specific_negation')
            for ex in ('supported', 'contradicted', 'undecidable')))
chk('fixtures_pass', all(S.judge(f['group'], f['quote'], f['finding'], f['refs'], f.get('stated_findings', ())) == f['expected'] for f in FX.FIXTURES))
chk('fixtures_sha_frozen', sem['fixtures_sha'] == hashlib.sha256((ROOT / 'report93_fixtures.py').read_bytes()).hexdigest())
anchor_ok = True
for r in sem['claim_review']:
    key = r['cond']
    e = 0 if key.startswith('base') else int(key.split('@')[1])
    cond = 'base_report' if key.startswith('base') else key.split('@')[0] + '_report'
    d = REC / ('validation/epoch2/base_report' if key.startswith('base') else f'validation/epoch{e}/{cond}')
    for l in (d / 'worker_0.jsonl').read_text().splitlines():
        j = json.loads(l)
        if j['id'].split('|')[0] == r['image_id']:
            anchor_ok &= r['quote'] in j['text']
chk('claim_quotes_in_raw_text', anchor_ok and sem['anchor_failures'] == 0)
chk('claim_review_not_bulk_retain', len({(r['original'], r['conservative']) for r in sem['claim_review']}) >= 4)

bad = [c for c in checks if not c['ok']]
Path(MAIN / 'verify.json').write_text(json.dumps(dict(passed=not bad, n=len(checks), n_failed=len(bad), checks=checks), indent=1, ensure_ascii=False))
print(len(checks), 'checks', len(bad), 'failed')
for c in bad:
    print('FAIL', c)
sys.exit(1 if bad else 0)
