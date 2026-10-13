"""iter_137 자료 연결 (CPU): iter_136 manifest의 D6/E45 P·N1 PNG를 읽기 전용으로 재연결하고 hash·역할·D/E 비중복·annotation 면적을 검사한 뒤,
A/B 두 인터페이스의 요청 파일(technical 24 / main 180)을 만든다. 새 표본 선정·재렌더 없음. 모델 입력에는 mask·환자 ID·slice 역할·정답을 넣지 않는다.
msd56_data.py의 case_paths는 원 NIfTI hash 확인에만 쓴다(원 hash가 없으면 PNG hash 검사로 한정하고 기록)."""
import hashlib, json, sys
from pathlib import Path
import numpy as np
from PIL import Image
from i137_common import RES, DATA, OLD136, HERE, GEN_SEED, sha, read, save, digest, now
from i137_spec import PROMPTS, IFACES, ROLES, FORBIDDEN_IN_PROMPT


def link():
    m = read(OLD136 / 'data/manifest.json'); problems = []
    cases = m['cases']; ids = {s: [c['case'] for c in cases[s]] for s in 'DE'}
    if set(ids['D']) & set(ids['E']): problems.append('D_E_overlap')
    for s in 'DE':
        if len(set(ids[s])) != len(ids[s]): problems.append('duplicate_case_' + s)
    if (len(ids['D']), len(ids['E'])) != (6, 45): problems.append('unexpected_counts %s' % [len(ids['D']), len(ids['E'])])
    png_owner = {}; rows = {'D': [], 'E': []}; raw_check = []
    try:
        import msd56_data as M
    except Exception as e:   # noqa: BLE001
        M = None; problems.append('msd56_data_import_failed:' + repr(e)[:80])
    for s in 'DE':
        for c in cases[s]:
            img = {}
            for role in ROLES:
                im = c['images'][role]; p = Path(im['path'])
                if not str(p).startswith(str(OLD136 / 'data/png') + '/'): problems.append('path_outside %s' % p)
                if sha(p) != im['sha256']: problems.append('png_sha %s %s' % (c['case'], role))
                arr = np.array(Image.open(p).convert('RGB'))
                if arr.shape[:2] != (240, 240) or not ((arr[..., 0] == arr[..., 1]).all() and (arr[..., 0] == arr[..., 2]).all()): problems.append('png_format %s %s' % (c['case'], role))
                png_owner.setdefault(im['sha256'], []).append((c['case'], role))
                img[role] = dict(path=str(p), sha256=im['sha256'], pixel_sha256=hashlib.sha256(arr.tobytes()).hexdigest(), z=c['z'][role], annotation_area=c['area'][role])
            if not (c['area']['P'] > 0 and c['area']['N1'] == 0): problems.append('area_contract %s' % c['case'])
            if img['P']['sha256'] == img['N1']['sha256']: problems.append('same_png_P_N1 %s' % c['case'])
            if c['images']['P']['same_pixels_as_iter064_png'] is not True or c['images']['N1']['same_pixels_as_iter064_png'] is not True: problems.append('iter064_pixel_link %s' % c['case'])
            if M is not None:
                ip, lp = M.case_paths(c['case'])
                if Path(ip).exists() and Path(lp).exists():
                    ok = sha(ip) == c['img_sha256'] and sha(lp) == c['lbl_sha256']; raw_check.append(ok)
                    if not ok: problems.append('raw_nifti_sha %s' % c['case'])
            rows[s].append(dict(case=c['case'], images=img))
    dup = {k: v for k, v in png_owner.items() if len({x[0] for x in v}) > 1}
    if dup: problems.append('png_duplicates_across_cases')
    return m, rows, dict(problems=problems, n_raw_nifti_checked=len(raw_check), all_raw_nifti_ok=bool(raw_check) and all(raw_check), n_cases={s: len(rows[s]) for s in 'DE'}, png_duplicates=len(dup),
                         excluded_in_iter136=[e['case'] for e in m['excluded']], iter136_manifest_sha256=sha(OLD136 / 'data/manifest.json'))


def make_requests(rows):
    reqs = []
    for c in rows:
        for role in ROLES:
            for ifc in IFACES:
                prompt = PROMPTS[ifc]; assert not any(s in prompt for s in FORBIDDEN_IN_PROMPT)
                im = c['images'][role]
                r = dict(id='%s__%s__%s' % (c['case'], role, ifc), kind='single', patient=c['case'], cond=role, iface=ifc, roles=[role], prompt=prompt,
                         images=[dict(path=im['path'], sha256=im['sha256'])])
                r['request_digest'] = digest(r); reqs.append(r)
    reqs.sort(key=lambda r: hashlib.sha256(('%d|%s' % (GEN_SEED, r['id'])).encode()).hexdigest())   # 환자·조건·인터페이스 순서 균형화(seed 고정)
    return reqs


def main():
    m, rows, checks = link()
    run = not checks['problems']
    save(DATA / 'manifest.json', dict(created_at=now(), source='results/iter_136/data/manifest.json(읽기 전용)', checks=checks, run_models=run, rows=rows,
                                       note='반복 개발 자료(MSD Task01 FLAIR). 독립 test 아님. N1은 annotation 면적 0 slice이며 임상 정상이 아니다. P는 GT 기반 선택이다.'))
    if run:
        save(RES / 'requests/technical.json', make_requests(rows['D'])); save(RES / 'requests/main.json', make_requests(rows['E']))
    print('run', run, {k: v for k, v in checks.items() if k != 'excluded_in_iter136'})


if __name__ == '__main__':
    main()
