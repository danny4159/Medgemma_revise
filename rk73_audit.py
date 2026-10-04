"""iter_073/074: 3DReasonKnee 공개 train/val annotation의 연골 size grade 연결·결측·prior 점검 (CPU, 모델 호출 없음).

iter_074 경계: 통합 원 MOAKS label(data/labels/*)은 test 환자 행을 포함하므로 어떤 진입점에서도 파싱하지 않는다(load_moaks는 항상 거부).
안전한 train/val 전용 원 label 출처가 확인되기 전까지 원 label 연결(link_original)은 보류한다. 입력은 파싱 전에 고정 manifest hash와 대조한다.
- test 답변(generate_data/test*.json)은 읽지 않는다. test_split.csv는 ID 열만 있는지 확인한 뒤 환자 교집합에만 쓴다.
- grade_dict의 초기값 0을 정답으로 쓰지 않는다. null/빈값/'.'/범위 밖 코드는 실제 0과 구별한다.
- CoT/answer 문자열은 저장하지 않는다.
"""
import collections, csv, json, os, re, sys, time
import pandas as pd
import rk73_fetch as F

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, 'results/iter_073/raw/data')
OUT = os.path.join(ROOT, 'results/iter_073')
ID_COLS = ['patient_id', 'time', 'study_folder', 'series_folder', 'knee_side', 'path', 'image_filepath', 'label_filepath']

# 질문 순서(16-29)에 대응하는 공식 subregion 키와 MOAKS 원 label(V00MCM*) 열 접미사. 대응은 가정이며 아래 일치율로 확인한다.
SUBREGION_COL = collections.OrderedDict([
    ('patella_medial', 'PM'), ('patella_lateral', 'PL'),
    ('femur_medial_trochlea', 'FMA'), ('femur_lateral_trochlea', 'FLA'),
    ('femur_medial_posterior', 'FMP'), ('femur_lateral_posterior', 'FLP'),
    ('femur_medial_central', 'FMC'), ('femur_lateral_central', 'FLC'),
    ('tibia_medial_anterior', 'TMA'), ('tibia_lateral_anterior', 'TLA'),
    ('tibia_medial_central', 'TMC'), ('tibia_lateral_central', 'TLC'),
    ('tibia_medial_posterior', 'TMP'), ('tibia_lateral_posterior', 'TLP')])
TIME_FILE = {'00M': 'BICL00', '12M': 'BICL01', '24M': 'BICL03', '48M': 'BICL06'}  # 가정; 교차 일치율로 확인
LABEL_FILES = {'SQ': 'taxonomymatch_kMRI_SQ_MOAKS_%s.csv', 'FNIH': 'taxonomymatch_kMRI_FNIH_SQ_MOAKS_%s.csv'}
GRADES = (0, 1, 2, 3)


def norm_img(p):
    """'../data/images/..' 와 '/data/images/..' 를 같은 키로."""
    i = p.find('data/images/')
    return '/' + p[i:] if i >= 0 else p


class LabelScopeError(RuntimeError):
    pass


class MembershipError(RuntimeError):
    pass


def guard_not_test(path):
    if os.path.basename(path).lower().startswith('test') or F.is_forbidden(path) or '/labels/' in path.replace('\\', '/'):
        raise ValueError('test 답변/통합 원 label 파일은 읽지 않는다: %s' % path)


def grade_status(v):
    """(status, value). int 0-3만 ok. None/''/'.'은 missing, 그 외는 구별해 보존."""
    if v is None:
        return 'missing', None
    if isinstance(v, bool):
        return 'bad_type', None
    if isinstance(v, int):
        return ('ok', v) if v in GRADES else ('out_of_range', v)
    if isinstance(v, float):
        return ('ok', int(v)) if v in (0.0, 1.0, 2.0, 3.0) else ('out_of_range', v)
    if isinstance(v, str):
        s = v.strip()
        if s in ('', '.'):
            return 'missing', None
        if re.fullmatch(r'-?\d+', s):
            n = int(s)
            return ('string_ok', n) if n in GRADES else ('out_of_range', n)
        return 'bad_type', None
    return 'bad_type', None


def cartilage_entry(fd):
    """final_diagnosis dict -> (subregion, size_raw, depth_raw) 또는 None. 키가 정확히 하나의 *_cartilage_lesion일 때만."""
    if not isinstance(fd, dict) or not isinstance(fd.get('final_diagnosis'), dict):
        return None
    ks = list(fd['final_diagnosis'].keys())
    if len(ks) != 1 or not ks[0].endswith('_cartilage_lesion'):
        return None
    sub = ks[0][:-len('_cartilage_lesion')]
    v = fd['final_diagnosis'][ks[0]]
    if not isinstance(v, dict):
        return sub, 'MISSING_DICT', 'MISSING_DICT'
    return sub, v.get('size', None), v.get('depth', None)


def prompt_subregion_ok(prompt, sub):
    return ('cartilage lesions in the %s subregion' % sub.replace('_', ' ')) in prompt


def load_split(split, raw=None):
    p = os.path.join(raw or RAW, 'split_files/%s_split.csv' % split)
    d = pd.read_csv(p, dtype=str, keep_default_na=False)
    assert list(d.columns) == ID_COLS, (split, list(d.columns))  # ID 메타데이터만 (test 답변 열 없음)
    d['img'] = d.image_filepath.map(norm_img)
    return d


def extract_split(split, split_df, raw=None):
    """generate_data/{train,val}.json에서 연골 항목만 추출. 반환: long rows, per-image 통계. split 밖 영상이 있으면 grade 집계 전에 MembershipError."""
    if split not in ('train', 'val'):
        raise ValueError('train/val만 허용: %s' % split)
    path = os.path.join(raw or RAW, 'generate_data/%s.json' % split)
    guard_not_test(path)
    data = json.load(open(path))
    foreign = {norm_img(r['image']) for r in data} - set(split_df.img)
    if foreign:
        raise MembershipError('%s.json에 split 밖 영상 %d개' % (split, len(foreign)))
    rows, per_img_total, per_img_cart = [], collections.Counter(), collections.Counter()
    seen = collections.Counter()
    prompt_bad = 0
    img_set = set(split_df.img)
    orphan = collections.Counter()
    for rec in data:
        im = norm_img(rec['image'])
        per_img_total[im] += 1
        if im not in img_set:
            orphan[im] += 1
        c = cartilage_entry(rec.get('final_diagnosis'))
        if c is None:
            continue
        sub, s_raw, d_raw = c
        per_img_cart[im] += 1
        seen[(im, sub)] += 1
        pok = prompt_subregion_ok(rec['prompt'], sub)
        prompt_bad += (not pok)
        ss, sv = grade_status(s_raw)
        ds, dv = grade_status(d_raw)
        rows.append((im, sub, s_raw if ss not in ('ok', 'string_ok') else sv, ss, sv, d_raw if ds not in ('ok', 'string_ok') else dv, ds, dv, pok))
    del data
    df = pd.DataFrame(rows, columns=['img', 'subregion', 'size_raw', 'size_status', 'size', 'depth_raw', 'depth_status', 'depth', 'prompt_ok'])
    stats = {'n_json_records': int(sum(per_img_total.values())), 'n_images_in_json': len(per_img_total),
             'records_per_image_hist': dict(collections.Counter(per_img_total.values())),
             'cartilage_per_image_hist': dict(collections.Counter(per_img_cart.values())),
             'n_cartilage_rows': len(rows), 'dup_image_subregion_keys': int(sum(1 for v in seen.values() if v > 1)),
             'prompt_subregion_mismatch': int(prompt_bad), 'orphan_images': len(orphan),
             'split_images_missing_in_json': len(img_set - set(per_img_total))}
    return df, stats


def load_moaks(*args, **kwargs):
    """통합 원 MOAKS 표는 test 환자 행을 포함하므로 파일을 열기 전에 항상 거부한다(안전한 train/val 전용 출처 확인 전까지)."""
    raise LabelScopeError('통합 원 MOAKS label은 test 환자 행을 포함해 읽지 않는다. train/val 전용 출처가 확인되기 전 원 label 연결은 보류.')


def moaks_lookup(moaks):
    """(tag, pid, side) -> [(src, version, {sub: (size_raw, depth_raw)}), ...]. 중복 행을 임의로 고르지 않고 모두 보존."""
    if not all(getattr(d, 'attrs', {}).get('scope') == 'train_val_only' for d in moaks.values()):
        raise LabelScopeError('train_val_only로 확인되지 않은 label 표는 집계하지 않는다.')
    table = collections.defaultdict(list)
    for (tag, src), d in moaks.items():
        for _, r in d.iterrows():
            key = (tag, r['ID'], r['SIDE'])
            vals = {sub: (r['V00MCM' + c], r['V00MCM' + c + '.1']) for sub, c in SUBREGION_COL.items()}
            table[key].append((src, r['VERSION'], vals))
    multi = [k for k, v in table.items() if len(v) > 1]
    conflict = [k for k in multi if any(x[2] != table[k][0][2] for x in table[k][1:])]
    return dict(table), {'keys': len(table), 'keys_with_multiple_rows': len(multi), 'keys_with_conflicting_cartilage_rows': len(conflict)}


def orig_candidates(rows, sub, which):
    """which=0(size)/1(depth). 반환 (status, sorted valid values, n_rows, n_missing_rows, n_bad_rows)."""
    vals, miss, bad = set(), 0, 0
    for _, _, v in rows:
        st, x = grade_status(v[sub][which])
        if st in ('ok', 'string_ok'):
            vals.add(x)
        elif st == 'missing':
            miss += 1
        else:
            bad += 1
    status = 'no_valid' if not vals else ('unique' if len(vals) == 1 else 'ambiguous')
    return status, sorted(vals), len(rows), miss, bad


def majority(counter):
    """동률이면 낮은 grade."""
    if not counter:
        return None
    best = max(counter.values())
    return min(g for g, c in counter.items() if c == best)


def prior_scores(train_df, val_df, by_sub):
    """train-only majority를 val에 적용. ok/string_ok size만 사용. recall은 support 0이면 None."""
    tr = train_df[train_df.size_status.isin(['ok', 'string_ok'])]
    va = val_df[val_df.size_status.isin(['ok', 'string_ok'])].copy()
    if by_sub:
        pred = {s: majority(collections.Counter(g.loc[:, 'size'])) for s, g in tr.groupby('subregion')}
        va['pred'] = va.subregion.map(pred)
    else:
        va['pred'] = majority(collections.Counter(tr['size']))
    va['size'] = va['size'].astype(int)
    va['pred'] = va['pred'].astype(int)
    return va, ({s: int(v) for s, v in pred.items()} if by_sub else int(va['pred'].iloc[0]))


def score(va):
    out = {'n': int(len(va)), 'accuracy': float((va['size'] == va['pred']).mean()),
           'mae': float((va['size'] - va['pred']).abs().mean())}
    rec = {}
    for g in GRADES:
        m = va['size'] == g
        rec[str(g)] = {'support': int(m.sum()), 'recall': (float((va.loc[m, 'pred'] == g).mean()) if m.sum() else None)}
    out['recall_by_grade'] = rec
    defined = [v['recall'] for v in rec.values() if v['recall'] is not None]
    out['macro_recall_defined_classes'] = float(sum(defined) / len(defined)) if defined else None
    return out


def patient_weighted(va, pid_of_img):
    va = va.copy()
    va['pid'] = va.img.map(pid_of_img)
    va['hit'] = (va['size'] == va['pred']).astype(float)
    va['ae'] = (va['size'] - va['pred']).abs().astype(float)
    g = va.groupby('pid')[['hit', 'ae']].mean()
    return {'n_patients': int(len(g)), 'accuracy_patient_mean': float(g.hit.mean()), 'mae_patient_mean': float(g.ae.mean())}


def link_original(longs, table, res):
    """가정한 방문·부위 mapping으로 배포 label과 원 MOAKS 후보를 연결한다. 안전한 train/val 전용 원 label 출처가 확인될 때만 호출(현재 출처 없음)."""
    # 원 label과 연결: 후보 값 전체를 보존
    agree = {}
    for s, df in longs.items():
        cols = collections.defaultdict(list)
        for r in df.itertuples():
            tag = TIME_FILE.get(r.time)
            rows = table.get((tag, r.patient_id, r.knee_side)) if tag else None
            if rows is None:
                for k in ('orig_rows', 'orig_size_status', 'orig_size_cands', 'orig_size_missing_rows', 'orig_size_bad_rows',
                          'orig_depth_status', 'orig_depth_cands', 'orig_depth_missing_rows', 'orig_depth_bad_rows'):
                    cols[k].append(0 if k == 'orig_rows' else ('no_row' if k.endswith('status') else None))
                continue
            st, c, n, m, b = orig_candidates(rows, r.subregion, 0)
            dst, dc, _, dm, db = orig_candidates(rows, r.subregion, 1)
            cols['orig_rows'].append(n); cols['orig_size_status'].append(st); cols['orig_size_cands'].append('|'.join(map(str, c)))
            cols['orig_size_missing_rows'].append(m); cols['orig_size_bad_rows'].append(b)
            cols['orig_depth_status'].append(dst); cols['orig_depth_cands'].append('|'.join(map(str, dc)))
            cols['orig_depth_missing_rows'].append(dm); cols['orig_depth_bad_rows'].append(db)
        for k, v in cols.items():
            df[k] = v
        df['size_in_cands'] = [(str(int(sz)) in c.split('|')) if isinstance(c, str) and c else False for sz, c in zip(df['size'], df.orig_size_cands)]
        df['depth_in_cands'] = [(str(int(dp)) in c.split('|')) if isinstance(c, str) and c and dp == dp and dp is not None else False for dp, c in zip(df['depth'], df.orig_depth_cands)]
        a = {'rows': len(df), 'rows_with_orig_key': int((df.orig_rows > 0).sum()),
             'images_with_orig_key': int(df[df.orig_rows > 0].img.nunique()), 'images': int(df.img.nunique()),
             'orig_size_status_counts': df.orig_size_status.value_counts().to_dict(),
             'orig_rows_hist': {str(k): int(v) for k, v in df.orig_rows.value_counts().sort_index().items()}}
        for nm in ('size', 'depth'):
            res_nm = {}
            for stt in ('unique', 'ambiguous'):
                g = df[df['orig_%s_status' % nm] == stt]
                res_nm[stt] = {'n': int(len(g)), 'distributed_in_candidates': int(g['%s_in_cands' % nm].sum())}
            res_nm['no_valid_orig'] = {'n': int((df['orig_%s_status' % nm] == 'no_valid').sum()),
                                       'distributed_values': {str(k): int(v) for k, v in df[df['orig_%s_status' % nm] == 'no_valid'][nm].value_counts(dropna=False).items()}}
            res_nm['rows_with_missing_or_bad_orig_cells'] = {
                'missing_rows': int((df['orig_%s_missing_rows' % nm] > 0).sum()), 'bad_code_rows': int((df['orig_%s_bad_rows' % nm] > 0).sum())}
            a[nm] = res_nm
        u = df[df.orig_size_status == 'unique']
        a['size_unique_confusion_orig_to_dist'] = {'%s->%d' % (c, int(sz)): int(v) for (c, sz), v in u.groupby(['orig_size_cands', 'size']).size().items()}
        a['size_unique_agree_by_subregion'] = {sub: {'n': int(len(g)), 'agree': int(g.size_in_cands.sum())} for sub, g in u.groupby('subregion')}
        a['size_unique_agree_by_time'] = {t: {'n': int(len(g)), 'agree': int(g.size_in_cands.sum())} for t, g in u.groupby('time')}
        amb = df[df.orig_size_status == 'ambiguous']
        a['size_ambiguous_agree_by_time'] = {t: {'n': int(len(g)), 'in_cands': int(g.size_in_cands.sum())} for t, g in amb.groupby('time')}
        agree[s] = a
    res['distributed_vs_original'] = agree

    # 불일치 구조: unique 원 row 기준 무릎(영상) 단위 불일치와 VERSION별 비율
    ms = {}
    for s, df in longs.items():
        uq = df[df.orig_size_status == 'unique'].copy()
        uq['ver'] = [table[(TIME_FILE[t], p, sd)][0][0] + ':' + table[(TIME_FILE[t], p, sd)][0][1] if len(table[(TIME_FILE[t], p, sd)]) == 1 else 'multi_row'
                     for t, p, sd in zip(uq.time, uq.patient_id, uq.knee_side)]
        bad = uq[~uq.size_in_cands]
        per_img = uq.groupby('img').apply(lambda g: int((~g.size_in_cands).sum()), include_groups=False)
        ms[s] = {'unique_rows': int(len(uq)), 'mismatch_rows': int(len(bad)), 'images_with_unique_rows': int(len(per_img)),
                 'images_with_any_mismatch': int((per_img > 0).sum()),
                 'mismatch_rows_per_image_hist': {str(k): int(v) for k, v in per_img[per_img > 0].value_counts().sort_index().items()},
                 'by_version_single_row_keys': {v: {'rows': int(len(g)), 'mismatch': int((~g.size_in_cands).sum())}
                                                for v, g in uq.groupby('ver') if len(g) >= 200},
                 'mismatch_by_time': {t: {'rows': int(len(g)), 'mismatch': int((~g.size_in_cands).sum())} for t, g in uq.groupby('time')}}
    res['mismatch_structure'] = ms

    # 시점-파일 대응 교차 확인: 각 time의 분배 size가 어느 BICL 파일과 가장 잘 맞는가
    cross = {}
    df = longs['train']
    df = df[df.size_status.isin(['ok', 'string_ok'])]
    for t in TIME_FILE:
        sub = df[df.time == t]
        cross[t] = {}
        for tag in TIME_FILE.values():
            n = ag = 0
            for r in sub.sample(n=min(len(sub), 4000), random_state=0).itertuples():
                rows = table.get((tag, r.patient_id, r.knee_side))
                if rows is None:
                    continue
                stt, cands, _, _, _ = orig_candidates(rows, r.subregion, 0)
                if stt == 'unique':
                    n += 1; ag += int(cands[0] == int(r.size))
            cross[t][tag] = {'n': n, 'agree': ag, 'rate': (ag / n if n else None)}
    res['time_file_cross_check'] = cross
    return res


NEEDED = ['data/split_files/%s' % f for f in ('all_studies.csv', 'train_split.csv', 'val_split.csv', 'test_split.csv')] + \
    ['data/generate_data/train.json', 'data/generate_data/val.json']


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw', default=RAW)
    ap.add_argument('--out', required=True, help='새 결과 디렉터리(results/iter_074/ 아래, 기존 산출물 덮어쓰기 금지)')
    ap.add_argument('--manifest', default=F.PINNED_MANIFEST)
    ap.add_argument('--manifest-sha256', default=F.PINNED_MANIFEST_SHA256)
    ap.add_argument('--original-label-link', action='store_true', help='현재 항상 거부(안전한 train/val 전용 출처 없음)')
    a = ap.parse_args(argv)
    if a.original_label_link:
        raise LabelScopeError('원 label 연결 요청은 파싱 전에 거부: 안전한 train/val 전용 label 출처가 없다.')
    out = os.path.abspath(a.out)
    if '/results/iter_074/' not in out + '/' or os.path.exists(os.path.join(out, 'annotation_audit.json')):
        raise ValueError('출력은 새 iter_074 경로여야 한다: %s' % out)
    raw = a.raw
    prov = F.verify_allowed(os.path.dirname(raw), NEEDED, a.manifest, a.manifest_sha256)  # 파싱 전 고정 manifest 대조; raw = .../raw/data
    t0 = time.time()
    os.makedirs(out, exist_ok=True)
    res = {'revision': F.load_pinned_manifest(a.manifest, a.manifest_sha256)['revision'], 'input_sha256': prov}
    splits = {s: load_split(s, raw) for s in ('train', 'val', 'test')}
    allst = pd.read_csv(os.path.join(raw, 'split_files/all_studies.csv'), dtype=str, keep_default_na=False)
    allst['img'] = allst.image_filepath.map(norm_img)
    res['split_files'] = {s: {'rows': len(d), 'patients': d.patient_id.nunique(), 'images': d.img.nunique(),
                              'dup_image_rows': int(d.img.duplicated().sum()),
                              'time': d.time.value_counts().to_dict(), 'knee_side': d.knee_side.value_counts().to_dict()}
                          for s, d in splits.items()}
    res['all_studies'] = {'rows': len(allst), 'images': allst.img.nunique(),
                          'covered_by_splits': int(allst.img.isin(set().union(*[set(d.img) for d in splits.values()])).sum())}
    # 환자/이미지 교집합 (test는 ID만)
    P = {s: set(d.patient_id) for s, d in splits.items()}
    I = {s: set(d.img) for s, d in splits.items()}
    res['overlap'] = {'patients_train_val': len(P['train'] & P['val']), 'patients_train_test': len(P['train'] & P['test']),
                      'patients_val_test': len(P['val'] & P['test']),
                      'images_train_val': len(I['train'] & I['val']), 'images_train_test': len(I['train'] & I['test']),
                      'images_val_test': len(I['val'] & I['test'])}
    # 같은 환자·시점·무릎의 복수 series
    for s, d in splits.items():
        k = d.groupby(['patient_id', 'time', 'knee_side']).size()
        res['split_files'][s]['patient_time_side_with_multiple_series'] = int((k > 1).sum())
        res['split_files'][s]['patients_both_knees'] = int((d.groupby('patient_id').knee_side.nunique() > 1).sum())

    longs, jstats = {}, {}
    for s in ('train', 'val'):
        df, st = extract_split(s, splits[s], raw)
        meta = splits[s][['img', 'patient_id', 'time', 'knee_side', 'study_folder', 'series_folder']]
        df = df.merge(meta, on='img', how='left', validate='many_to_one')
        df['split'] = s
        longs[s], jstats[s] = df, st
    res['json_stats'] = jstats

    # 원 label 연결은 보류: 통합 label 파일을 열지 않는다(빈 결과를 검증 완료로 쓰지 않음).
    res['original_label_linkage'] = {'status': 'deferred_no_safe_train_val_label_source'}

    # 분포
    dist = {}
    for s, df in longs.items():
        ok = df[df.size_status.isin(['ok', 'string_ok'])]
        d = {'rows': len(df), 'size_status_counts': df.size_status.value_counts().to_dict(),
             'depth_status_counts': df.depth_status.value_counts().to_dict(),
             'prompt_subregion_mismatch': int((~df.prompt_ok).sum()),
             'size_overall': {str(int(k)): int(v) for k, v in ok['size'].astype(int).value_counts().sort_index().items()},
             'size_by_subregion': {sub: {str(int(k)): int(v) for k, v in g['size'].astype(int).value_counts().sort_index().items()}
                                   for sub, g in ok.groupby('subregion')},
             'size_by_time': {t: {str(int(k)): int(v) for k, v in g['size'].astype(int).value_counts().sort_index().items()} for t, g in ok.groupby('time')},
             'size_by_side': {t: {str(int(k)): int(v) for k, v in g['size'].astype(int).value_counts().sort_index().items()} for t, g in ok.groupby('knee_side')},
             'depth_pos_with_size0': int(((df.depth_status.isin(['ok', 'string_ok'])) & (df.size_status.isin(['ok', 'string_ok'])) & (df['depth'].astype(float) > 0) & (df['size'].astype(float) == 0)).sum())}
        per_img = ok.groupby('img')['size'].agg(lambda x: x.astype(int).nunique())
        mx = ok.groupby('img')['size'].agg(lambda x: int(x.astype(int).max()))
        full = ok.groupby('img').size()
        d['knees_with_all14_valid'] = int((full == 14).sum())
        d['knees_with_distinct_size_grades'] = {str(k): int(v) for k, v in per_img.value_counts().sort_index().items()}
        d['knees_max_size_grade'] = {str(k): int(v) for k, v in mx.value_counts().sort_index().items()}
        dist[s] = d
    res['distribution'] = dist

    # train-only prior
    pid_of_img = splits['val'].set_index('img').patient_id.to_dict()
    pri = {}
    va, g = prior_scores(longs['train'], longs['val'], by_sub=False)
    pri['global_majority'] = {'rule': g, 'pooled_rows': score(va), 'patient_mean': patient_weighted(va, pid_of_img)}
    va2, gs = prior_scores(longs['train'], longs['val'], by_sub=True)
    pri['subregion_majority'] = {'rule': gs, 'pooled_rows': score(va2), 'patient_mean': patient_weighted(va2, pid_of_img)}
    pri['subregion_majority']['by_subregion_accuracy'] = {s_: {'n': int(len(x)), 'accuracy': float((x['size'] == x['pred']).mean())} for s_, x in va2.groupby('subregion')}
    res['train_only_prior'] = pri
    res['wall_s'] = round(time.time() - t0, 1)
    json.dump(res, open(os.path.join(out, 'annotation_audit.json'), 'w'), indent=1, default=str)
    for s, df in longs.items():
        df.to_csv(os.path.join(out, 'cartilage_long_%s.csv' % s), index=False)
    print('done', res['wall_s'])


if __name__ == '__main__':
    main()
