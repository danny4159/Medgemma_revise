"""iter_075 H: PyRadiomics(원 regular T2 volume + GT disc mask label 200+k) + RandomForest. oracle 전문 대안 (전체 3D volume·정밀 mask 사용).

- 환경: results/environments/ch75/site (scikit-learn, pyradiomics 3.0.1) + results/environments/sitk67/site. 기본 환경 변경 없음.
- 사전 고정 설정(출력 전): Original image만; shape/firstorder/glcm/glrlm/glszm/gldm/ngtdm; binCount=32, normalize=True(scale 100), resampling 없음, force2D=False.
  wavelet·다중 sequence·등급 기반 feature 선택 없음. 결측은 train-only median, train 상수 feature 제거.
- RF: 500 trees, max_depth {5,None} x min_samples_leaf {1,3} x class_weight {None,balanced}, random_state=17. V8 primary 최소, 동률은 config 번호 순.
- 단계: fit(T24 train, V8 선택; E24 미접근) -> LOCK(selection.json) -> predict(E24).
"""
import argparse, hashlib, itertools, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'results/environments/sitk67/site'))
sys.path.insert(0, os.path.join(HERE, 'results/environments/ch75/site'))
import numpy as np

import sp75_data as D
import sp75_metrics as M
import sp67_data as S

SETTINGS = {'binCount': 32, 'normalize': True, 'normalizeScale': 100, 'resampledPixelSpacing': None, 'force2D': False, 'correctMask': True, 'label': 1,
            'additionalInfo': False}
CLASSES = ['shape', 'firstorder', 'glcm', 'glrlm', 'glszm', 'gldm', 'ngtdm']
GRID = [{'max_depth': d, 'min_samples_leaf': l, 'class_weight': w} for d, l, w in itertools.product([5, None], [1, 3], [None, 'balanced'])]
CODE = ['sp75_h.py', 'sp75_data.py', 'sp75_metrics.py', 'sp67_data.py']
PROB_CLIP = 1e-3


def sha_file(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def extractor():
    from radiomics import featureextractor
    e = featureextractor.RadiomicsFeatureExtractor(**SETTINGS)
    e.disableAllFeatures()
    for c in CLASSES:
        e.enableFeatureClassByName(c)
    e.disableAllImageTypes()
    e.enableImageTypeByName('Original')
    return e


def extract_patient(pid, ks, ext):
    """원 grid(zip의 image/mask) -> label 200+k binary mask -> feature dict. returns {k: (feats, seconds)}."""
    import SimpleITK as sitk
    t0 = time.time()
    img, _, _ = S.read_sitk(S.IMG_ZIP, f'images/{pid}_t2.mha')
    msk, _, marr = S.read_sitk(S.MSK_ZIP, f'masks/{pid}_t2.mha')
    t_read = time.time() - t0
    img = sitk.Cast(img, sitk.sitkFloat32)
    out = {}
    for k in ks:
        t1 = time.time()
        b = sitk.Cast(msk == (200 + k), sitk.sitkUInt8)
        b.CopyInformation(img)
        r = ext.execute(img, b, label=1)
        f = {n: float(v) for n, v in r.items() if not n.startswith('diagnostics')}
        out[k] = (f, time.time() - t1 + t_read / len(ks))
    return out


def feats_for(rows, ext, cache_path):
    cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}
    by_p = {}
    for r in rows:
        if r['id'] not in cache:
            by_p.setdefault(r['patient'], []).append(r['ordinal'])
    for pid, ks in by_p.items():
        D.G71.guard(pid)
        res = extract_patient(pid, ks, ext)
        for k, (f, dt) in res.items():
            cache[D.tid(pid, k)] = {'feats': f, 'seconds': dt}
    tmp = cache_path + '.tmp'
    json.dump(cache, open(tmp, 'w'))
    os.replace(tmp, cache_path)
    return cache


def matrix(rows, cache, names=None):
    names = names or sorted(cache[rows[0]['id']]['feats'])
    X = np.array([[cache[r['id']]['feats'].get(n, np.nan) for n in names] for r in rows], float)
    return X, names


def prep_fit(X):
    X = np.where(np.isfinite(X), X, np.nan)
    med = np.nanmedian(X, axis=0)
    med = np.where(np.isnan(med), 0.0, med)
    Xf = np.where(np.isnan(X), med, X)
    keep = Xf.std(axis=0) > 0
    return med, keep


def prep_apply(X, med, keep):
    X = np.where(np.isfinite(X), X, np.nan)
    Xf = np.where(np.isnan(X), med, X)
    return Xf[:, keep]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['fit', 'predict'])
    ap.add_argument('--out', required=True)
    ap.add_argument('--split', default='E24')
    a = ap.parse_args()
    from sklearn.ensemble import RandomForestClassifier
    import sklearn, radiomics
    os.makedirs(a.out, exist_ok=True)
    rows_all = D.load_manifest()['rows']
    D.load_split()
    sel = lambda sp: sorted([r for r in rows_all if r['split'] == sp and r['position_set'] == 'supervised' and not r['excluded']], key=lambda r: (int(r['patient']), r['ordinal']))
    ext = extractor()
    if a.mode == 'fit':
        if os.path.exists(f'{a.out}/selection.json'):
            sys.exit('selection exists')
        tr, va = sel('T24'), sel('V8')
        cache = feats_for(tr + va, ext, f'{a.out}/features_T24_V8.json')
        Xtr, names = matrix(tr, cache)
        Xva, _ = matrix(va, cache, names)
        med, keep = prep_fit(Xtr)
        Xtr_, Xva_ = prep_apply(Xtr, med, keep), prep_apply(Xva, med, keep)
        ytr = np.array([r['grade'] for r in tr])
        res = []
        for ci, cfg in enumerate(GRID):
            rf = RandomForestClassifier(n_estimators=500, random_state=17, n_jobs=4, **cfg).fit(Xtr_, ytr)
            pr = rf.predict_proba(Xva_)
            cls = list(rf.classes_)
            full = np.zeros((len(va), 5))
            for j, c in enumerate(cls):
                full[:, c - 1] = pr[:, j]
            pred = [int(np.argmax(p)) + 1 for p in full]
            prim = M.class_std_mae([r['grade'] for r in va], pred)[0]
            ce = float(-np.mean([np.log(max(full[i, r['grade'] - 1], PROB_CLIP)) for i, r in enumerate(va)]))
            res.append({'cfg_index': ci, 'cfg': cfg, 'val_primary': prim, 'val_ce_clip1e-3': ce})
        best = sorted(res, key=lambda x: (round(x['val_primary'], 12), x['cfg_index']))[0]
        sel_ = {'selected': best, 'grid': res, 'settings': SETTINGS, 'classes': CLASSES, 'n_features_total': len(names), 'n_features_kept': int(keep.sum()),
                'versions': {'sklearn': sklearn.__version__, 'radiomics': radiomics.__version__}, 'code': {f: sha_file(f) for f in CODE},
                'manifest_sha256': sha_file(f'{D.DATA}/manifest.json'), 'n_train': len(tr), 'n_val': len(va),
                'extract_seconds_per_target_mean': float(np.mean([cache[r['id']]['seconds'] for r in tr + va]))}
        json.dump(sel_, open(f'{a.out}/selection.json', 'w'), indent=1)
        print(json.dumps(best))
    else:
        s = json.load(open(f'{a.out}/selection.json'))
        for f, h in s['code'].items():
            if sha_file(f) != h:
                sys.exit(f'code changed since selection: {f}')
        if s['manifest_sha256'] != sha_file(f'{D.DATA}/manifest.json'):
            sys.exit('manifest changed since selection')
        tr = sel('T24')
        cache = json.load(open(f'{a.out}/features_T24_V8.json'))
        Xtr, names = matrix(tr, cache)
        med, keep = prep_fit(Xtr)
        ytr = np.array([r['grade'] for r in tr])
        cfg = s['selected']['cfg']
        rf = RandomForestClassifier(n_estimators=500, random_state=17, n_jobs=4, **cfg).fit(prep_apply(Xtr, med, keep), ytr)
        rows = sorted([r for r in rows_all if r['split'] == a.split and not r['excluded']], key=lambda r: (int(r['patient']), r['ordinal']))
        ec = feats_for(rows, ext, f'{a.out}/features_{a.split}.json')
        X, _ = matrix(rows, ec, names)
        pr = rf.predict_proba(prep_apply(X, med, keep))
        full = np.zeros((len(rows), 5))
        for j, c in enumerate(list(rf.classes_)):
            full[:, c - 1] = pr[:, j]
        out = [{'id': r['id'], 'patient': r['patient'], 'ordinal': r['ordinal'], 'position_set': r['position_set'], 'probs': full[i].tolist(), 'pred': int(np.argmax(full[i])) + 1}
               for i, r in enumerate(rows)]
        json.dump({'selected': s['selected'], 'split': a.split, 'n': len(out), 'preds': out}, open(f'{a.out}/pred_{a.split}.json', 'w'), indent=1)
        print('wrote', len(out))


if __name__ == '__main__':
    main()
