"""iter_123: 정답·환자·series 선정 manifest 잠금 (모델 출력 전). 결과: results/iter_123/data/"""
import ast, hashlib, json, os, sys, warnings
warnings.filterwarnings('ignore')
import pandas as pd
import mr123_labels as m

OUT = '/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_123/data/'
os.makedirs(OUT, exist_ok=True)
SEED = m.SEED


def h(*a):
    return hashlib.sha256('|'.join(map(str, a)).encode()).hexdigest()


def sha_file(p):
    d = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            d.update(b)
    return d.hexdigest()


def main():
    if os.path.exists(OUT + 'selection_lock.json'):
        print('이미 잠금 존재: 덮어쓰지 않음'); return
    c = m.load_candidates()
    cols = ['patient_uid', 'study_uid', 'series_id', 'classified_modality', 'is_derived', 'acquisition_plane', 'is_localizer',
            'is_subtraction', 'array_shape', 'array_spacing_mm', 'StudyDescription', 'ProcedureCodeSequence_0_CodeMeaning']
    md = pd.concat([pd.read_csv(m.BASE + f'metadata/{b}_metadata.csv', low_memory=False, usecols=cols).assign(batch_id=b) for b in m.BATCHES])
    f = md[(md.classified_modality == 'FLAIR') & (md.acquisition_plane == 'AXIAL') & (md.is_localizer.astype(str) == 'False')
           & (md.is_derived.astype(str) == 'False') & (md.is_subtraction.astype(str) == 'False')].copy()
    f['brain'] = f.StudyDescription.fillna('').str.contains('BEYIN|Cranial|CRANIAL', regex=True)
    f = f[f.brain]
    f['sp'] = f.array_spacing_mm.apply(lambda s: ast.literal_eval(s))
    f['thick_proxy'] = f.sp.apply(max)
    ex = c[c.label.isin(['positive', 'negative'])]
    ex = ex.merge(f.drop(columns=['patient_uid']), on=['batch_id', 'study_uid'])
    # study당 series 선택: 가장 작은 through-plane(proxy: 최대 spacing), 동률 series_id
    ex = ex.sort_values(['batch_id', 'study_uid', 'thick_proxy', 'series_id']).drop_duplicates(['batch_id', 'study_uid'])
    # 환자당 1 study: seed hash 순서 첫 study. 한 환자가 양·음성 모두 가지면 해당 환자는 제외(라벨 상충 방지)
    lab_per_p = ex.groupby('patient_uid').label.nunique()
    mixed = set(lab_per_p[lab_per_p > 1].index)
    ex = ex[~ex.patient_uid.isin(mixed)].copy()
    ex['h'] = ex.apply(lambda r: h(SEED, r.patient_uid, r.study_uid), axis=1)
    ex = ex.sort_values('h').drop_duplicates('patient_uid')
    ex['order_h'] = ex.apply(lambda r: h(SEED, 'order', r.patient_uid), axis=1)
    ex = ex.sort_values(['label', 'order_h'])
    sel = {}
    tech = []
    for lab in ['positive', 'negative']:
        t = ex[ex.label == lab].head(3)
        tech += t.to_dict('records')
    tech_p = {r['patient_uid'] for r in tech}
    rest = ex[~ex.patient_uid.isin(tech_p)]
    plan = {'positive': {'batch23': 12, 'batch04': 12}, 'negative': {'batch04': 12, 'batch23': 12}}
    explore, reserve = [], []
    for lab in ['positive', 'negative']:
        pool = {b: rest[(rest.label == lab) & (rest.batch_id == b)].to_dict('records') for b in m.BATCHES}
        take = {b: min(plan[lab][b], len(pool[b])) for b in m.BATCHES}
        short = 24 - sum(take.values())
        if short > 0:  # 한 batch 부족분은 다른 기존 batch에서만 보충
            for b in m.BATCHES:
                room = len(pool[b]) - take[b]
                add = min(room, short)
                take[b] += add; short -= add
        for b in m.BATCHES:
            explore += pool[b][:take[b]]
            reserve += pool[b][take[b]:take[b] + 6]
    def slim(r, role):
        return dict(role=role, batch_id=r['batch_id'], patient_uid=int(r['patient_uid']), study_uid=r['study_uid'], label=r['label'],
                    series_id=r['series_id'], array_shape=r['array_shape'], array_spacing_mm=r['array_spacing_mm'],
                    study_desc=r['StudyDescription'], pos_spans=r['pos_spans'], neg_spans=r['neg_spans'],
                    zip_path=f"mri/{r['batch_id']}/{r['study_uid']}.zip")
    man = [slim(r, 'tech') for r in tech] + [slim(r, 'explore') for r in explore] + [slim(r, 'reserve') for r in reserve]
    lock = dict(rules=m.RULES, seed=SEED, hf_revision='f6e39794e7820c96c18465231a30da424e6d1c69',
                source_sha256={k: sha_file(m.BASE + k) for k in ['splits.csv', 'reports/batch04_reports.csv', 'reports/batch23_reports.csv',
                                                                  'metadata/batch04_metadata.csv', 'metadata/batch23_metadata.csv']},
                code_sha256={k: sha_file(k) for k in ['mr123_labels.py', 'mr123_select.py']},
                n_label_candidates=c.groupby(['batch_id', 'label']).size().rename(lambda x: str(x)).reset_index().to_dict('records') if False else
                {f'{a}|{b}': int(n) for (a, b), n in c.groupby(['batch_id', 'label']).size().items()},
                n_eligible_axial_flair={f'{a}|{b}': int(n) for (a, b), n in ex.groupby(['batch_id', 'label']).size().items()},
                n_mixed_label_patients_excluded=len(mixed), plan=plan,
                replacement_rule='데이터 검사(ZIP/영상/뇌범위) 실패 시에만 같은 label·batch의 다음 reserve로 대체; 모델 출력은 사용하지 않음',
                manifest=man)
    json.dump(lock, open(OUT + 'selection_lock.json', 'w'), indent=1, default=str)
    print({r: sum(1 for x in man if x['role'] == r) for r in ['tech', 'explore', 'reserve']})
    print(pd.DataFrame(man).groupby(['role', 'label', 'batch_id']).size())


if __name__ == '__main__':
    main()
