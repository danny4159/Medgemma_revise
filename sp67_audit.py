"""iter_067 자료 audit: D/E의 paired T1/T2 적격, CSV grading↔mask ordinal 연결, 기하 검증. F는 열지 않는다.
출력: results/iter_067/data/audit.json (환자별 상태·IVD 목록·제외 사유), pairs_{D,E}.json (적격 환자·IVD, grading 포함 — 모델 입력과 분리된 평가용)."""
import json, os, sys, zipfile
import numpy as np
import sp67_data as S

OUT = 'results/iter_067/data'
SI_AGREE_MM = 15.0   # 같은 ordinal의 T1/T2 S 중심 차 허용(동일 검사 내 co-registration 가정)


def audit_patient(pid, grades, names_i, names_m):
    r = {'patient': pid, 'status': 'ok', 'reasons': []}
    for s in ('t1', 't2'):
        if f'images/{pid}_{s}.mha' not in names_i or f'masks/{pid}_{s}.mha' not in names_m:
            r['status'] = 'excluded'; r['reasons'].append(f'missing_{s}')
    if r['status'] != 'ok':
        return r, None
    vols, infos = {}, {}
    try:
        for s in ('t1', 't2'):
            v = S.load_pair(pid, s)
            vols[s] = v
            infos[s] = S.ivd_info(v['L'], v['spacing'])
    except S.GeomError as e:
        r['status'] = 'excluded'; r['reasons'].append(f'geom:{e}')
        return r, None
    csv_ks = sorted(k for (p, k) in grades if p == pid)
    r['csv_ivd'] = csv_ks
    r['mask_ivd'] = {s: sorted(infos[s]) for s in infos}
    r['geom'] = {s: {k: vols[s][k] for k in ('src_sha', 'tilt_deg', 'physical_check_max_rel_err', 'size_xyz', 'header')} | {'spacing_canon': vols[s]['spacing'], 'shape_canon': list(vols[s]['V'].shape)} for s in vols}
    ks = sorted(set(infos['t1']) & set(infos['t2']))
    ks = [k for k in ks if k in csv_ks]
    # ordinal: 1..n 연속, S 순서(아래->위) 증가, T1/T2 중심 일치
    for s in infos:
        order = [infos[s][k]['si_center_mm'] for k in sorted(infos[s])]
        if any(b <= a for a, b in zip(order, order[1:])):
            r['status'] = 'excluded'; r['reasons'].append(f'{s}_ordinal_not_monotone_in_S')
    if sorted(infos['t1']) != sorted(infos['t2']):
        r['reasons'].append('t1_t2_label_sets_differ')
    if csv_ks != list(range(1, len(csv_ks) + 1)):
        r['status'] = 'excluded'; r['reasons'].append('csv_ordinal_not_contiguous')
    diffs = {}
    for k in ks:
        d = abs(infos['t1'][k]['si_center_mm'] - infos['t2'][k]['si_center_mm'])
        diffs[k] = d
        if d > SI_AGREE_MM:
            r['status'] = 'excluded'; r['reasons'].append(f'ordinal{k}_T1_T2_S_center_differs_{d:.1f}mm')
    r['si_center_diff_mm'] = diffs
    r['ivd_used'] = ks if r['status'] == 'ok' else []
    r['ivd_dropped'] = sorted(set(csv_ks) - set(ks))
    return r, (vols, infos)


def main():
    sp = json.load(open(S.SPLIT))
    grades = S.read_grades()
    zi, zm = zipfile.ZipFile(S.IMG_ZIP), zipfile.ZipFile(S.MSK_ZIP)
    ni, nm = set(zi.namelist()), set(zm.namelist())
    os.makedirs(OUT, exist_ok=True)
    report = {'source': {f: S.sha_file(f) for f in (S.IMG_ZIP.replace('images.zip', 'images_zip_verify.json'), S.GRADES, S.SPLIT)},
              'sitk_version': S.sitk.Version.VersionString(), 'splits': {}, 'F_opened': False}
    for split in ('D', 'E'):
        pats = []
        for pid in sp[split]:
            r, _ = audit_patient(pid, grades, ni, nm)
            pats.append(r)
            print(split, pid, r['status'], r['reasons'], flush=True)
        ok = [p for p in pats if p['status'] == 'ok']
        pairs = []
        for p in ok:
            pairs.append({'patient': p['patient'], 'ivd': [{'k': k, 'modic': grades[(p['patient'], k)], 'label': S.LABELS[grades[(p['patient'], k)]]} for k in p['ivd_used']]})
        report['splits'][split] = {'n_listed': len(pats), 'n_ok': len(ok), 'patients': pats,
                                   'n_ivd': sum(len(x['ivd']) for x in pairs),
                                   'grade_counts': {S.LABELS[g]: sum(1 for x in pairs for i in x['ivd'] if i['modic'] == g) for g in range(4)}}
        json.dump(pairs, open(f'{OUT}/pairs_{split}.json', 'w'), indent=1)
    json.dump(report, open(f'{OUT}/audit.json', 'w'), indent=1)
    for s in ('D', 'E'):
        print(s, {k: report['splits'][s][k] for k in ('n_listed', 'n_ok', 'n_ivd', 'grade_counts')})


if __name__ == '__main__':
    main()
