"""iter_125: 측뇌실 크기 기술 후보 검색(정규식은 후보 검색만; 최종 적격성은 mr125_lock.py의 사례별 검토). 출력 전 규칙 고정, seed125."""
import json, os, re
import pandas as pd

M = '/home/test/.local/share/medgemma/mr_rate/meta/'
RES = 'results/iter_125/data/'
SEED = 125
LV = re.compile(r'lateral\s+ventric', re.I)
ENL = re.compile(r'(enlarg|dilat|ectas|prominen|widen|expan|hydroceph|ventriculomegal)', re.I)
NEGENL = re.compile(r'\b(no|not|without|non)\b[^.]{0,30}(enlarg|dilat|ectas|prominen|widen)', re.I)
NORM = re.compile(r'(normal|within normal|nonectatic|non-ectatic)', re.I)


def sents(txt):
    txt = re.sub(r'\s+', ' ', str(txt))
    return [s.strip() for s in re.split(r'(?<=[.;])\s+(?=[A-Z])', txt) if s.strip()]


def old_patients():
    s = set()
    L = json.load(open('results/iter_123/data/selection_lock.json'))
    s |= {int(r['patient_uid']) for r in L['manifest']}
    for p in ['results/iter_124/data/eligibility_lock.json', 'results/iter_124/data/candidates.json']:
        if os.path.exists(p):
            s |= {int(x) for x in re.findall(r'"patient_uid":\s*(\d+)', open(p).read())}
    return s


def main():
    sp = pd.read_csv(M + 'splits.csv')
    old = old_patients()
    rows = []
    for b in ['batch04', 'batch23']:
        m = pd.read_csv(M + f'metadata/{b}_metadata.csv', usecols=['patient_uid', 'study_uid', 'series_id', 'classified_modality', 'acquisition_plane', 'is_derived', 'is_localizer', 'array_shape', 'array_spacing_mm'], low_memory=False)
        t = m[(m.classified_modality == 'T2w') & (m.acquisition_plane == 'AXIAL') & (m.is_derived.astype(str) == 'False') & (m.is_localizer.astype(str) == 'False')].copy()
        sp_ = t.array_spacing_mm.map(json.loads)
        t['dz'] = sp_.map(lambda v: v[2])
        t['area'] = sp_.map(lambda v: v[0] * v[1])
        t = t.sort_values(['study_uid', 'dz', 'area', 'series_id']).groupby('study_uid').head(1)
        t = t.merge(sp[sp.batch_id == b][['study_uid', 'split']], on='study_uid')
        t = t[t.split == 'train']
        r = pd.read_csv(M + f'reports/{b}_reports.csv')
        t = t.merge(r, on='study_uid')
        t['batch_id'] = b
        rows.append(t)
    d = pd.concat(rows)
    d = d[~d.patient_uid.isin(old)]
    d = d.sort_values(['patient_uid', 'study_uid']).groupby('patient_uid').head(1)
    out = []
    for _, x in d.iterrows():
        hits = []
        for k in ['findings', 'impression']:
            for s in sents(x[k]):
                if LV.search(s):
                    hits.append((k, s))
        if not hits:
            continue
        pos = [h for h in hits if ENL.search(h[1]) and not NEGENL.search(h[1])]
        neg = [h for h in hits if h not in pos and (NORM.search(h[1]) or NEGENL.search(h[1]))]
        out.append(dict(batch_id=x.batch_id, patient_uid=int(x.patient_uid), study_uid=x.study_uid, series_id=x.series_id, array_shape=x.array_shape,
                        array_spacing_mm=x.array_spacing_mm, hits=hits, pos=pos, neg=neg))
    json.dump(out, open(RES + 'candidates_raw.json', 'w'), indent=1)
    for b in ['batch04', 'batch23']:
        o = [c for c in out if c['batch_id'] == b]
        print(b, len(o), 'pos-only', sum(1 for c in o if c['pos'] and not c['neg']), 'neg-only', sum(1 for c in o if c['neg'] and not c['pos']), 'both', sum(1 for c in o if c['pos'] and c['neg']))


if __name__ == '__main__':
    main()
