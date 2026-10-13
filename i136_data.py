"""iter_136 자료 구성 (CPU): iter_064 target_manifest D6/E48의 case·P·N1을 유지하고 N2를 규칙으로 추가, 렌더, 무결성 검사, 요청 파일 생성.
msd56_data.py(c01661230041a54f50da493c61a098ed2bdbe46f의 blob 142c67d)에서는 load_case/render/mask_slice만 사용한다.
출력 경로: results/iter_136 (기존 산출물에 쓰지 않는다). 모델 입력에는 GT·case명·보고서·mask를 넣지 않는다."""
import hashlib, json, sys
from pathlib import Path
import numpy as np
from i136_common import RES, DATA, HERE, SEED, sha, read, save, digest, now
from i136_spec import QUESTION, NOIMG, FORBIDDEN_IN_PROMPT, CONDS
import msd56_data as M

OLD056 = HERE / 'results/iter_056'
OLD064 = HERE / 'results/iter_064/data'
N_MIN = dict(D=4, E=32)
BRAIN_FRAC = 0.5


def sha_bytes(p): return sha(p)


def n2_select(flair, area, nz, P, N1, zoom_z):
    """N2: N1과 다른 slice 중 종양 annotation 면적 0, FLAIR nonzero 면적 >= 최대값의 50%, P와의 물리 거리 |dz|*zoom 최소(동률은 낮은 z)."""
    mx = int(nz.max()); cands = [k for k in range(len(area)) if k != N1 and k != P and area[k] == 0 and nz[k] >= BRAIN_FRAC * mx]
    if not cands: return None
    return sorted(cands, key=lambda k: (abs(k - P) * zoom_z, k))[0]


def canonical_zoom_z(cid):
    import nibabel as nib
    ip, _ = M.case_paths(cid)
    return float(nib.as_closest_canonical(nib.load(ip)).header.get_zooms()[2])


def affine_voxel_check(cid):
    """독립 경로: 원 orientation 배열의 한 voxel(마스크 안 최대 FLAIR)을 affine→world→canonical index로 옮겨 canonical 배열 값과 비교."""
    import nibabel as nib
    ip, lp = M.case_paths(cid)
    img, lbl = nib.load(ip), nib.load(lp); can = nib.as_closest_canonical(img)
    raw = np.asarray(img.dataobj[..., 0], dtype=np.float32); rl = np.asarray(lbl.dataobj) > 0
    idx = np.argwhere(rl); vals = raw[rl]; ijk = idx[int(np.argmax(vals))]
    world = img.affine @ np.append(ijk, 1.0); cj = np.rint(np.linalg.inv(can.affine) @ world)[:3].astype(int)
    cv = float(np.asarray(can.dataobj[..., 0], dtype=np.float32)[tuple(cj)])
    return bool(abs(cv - float(raw[tuple(ijk)])) < 1e-6)


def inspect(cid, row, split):
    why = []
    ip, lp = M.case_paths(cid)
    if sha(ip) != row['img_sha256']: why.append('img_sha_mismatch')
    if sha(lp) != row['lbl_sha256']: why.append('lbl_sha_mismatch')
    if why: return None, why
    flair, mask, info = M.load_case(cid)   # grid/affine 일치·finite·canonical RAS 검사 포함
    vals = set(np.unique(mask).tolist())
    if not vals <= {0, 1, 2, 3}: why.append('label_values_%s' % sorted(vals))
    zoom_z = canonical_zoom_z(cid)
    ann = mask > 0; area = [int(ann[:, :, k].sum()) for k in range(flair.shape[2])]; nz = np.array([int((flair[:, :, k] != 0).sum()) for k in range(flair.shape[2])])
    P, N1 = row['P_z'], row['N_z']
    if area[P] != row['area_P'] or area[N1] != 0 or row['area_N'] != 0: why.append('manifest_area_mismatch')
    if int(nz[P]) != row['nz_P'] or int(nz[N1]) != row['nz_N']: why.append('manifest_nz_mismatch')
    # 재계산한 기존 규칙과의 일치(감사용): P=max area tie low z; N1=area 0 with max nz tie low z
    Pre = int(sorted(range(len(area)), key=lambda k: (-area[k], k))[0]); N1re = int(sorted([k for k in range(len(area)) if area[k] == 0], key=lambda k: (-nz[k], k))[0])
    N2 = n2_select(flair, area, nz, P, N1, zoom_z)
    if N2 is None: why.append('no_N2_candidate')
    if not affine_voxel_check(cid): why.append('affine_voxel_check_failed')
    vmin, vmax = float(flair.min()), float(flair.max())
    if not vmax > vmin: why.append('degenerate_range')
    audit = dict(P_recomputed=Pre, N1_recomputed=N1re, rule_reproduces_manifest=bool(Pre == P and N1re == N1), zoom_z=zoom_z, vmin=vmin, vmax=vmax, shape=info['shape'][:3],
                 zooms=info['zooms'], orig_axcodes=info['orig_axcodes'], canon_axcodes=info['canon_axcodes'], labels=sorted(vals), max_nz=int(nz.max()))
    if why: return dict(case=cid, split=split, why=why, audit=audit), why
    z = dict(P=P, N1=N1, N2=N2)
    ar = {k: area[v] for k, v in z.items()}; nzk = {k: int(nz[v]) for k, v in z.items()}
    assert ar['P'] > 0 and ar['N1'] == 0 and ar['N2'] == 0
    return dict(case=cid, split=split, z=z, area=ar, nz=nzk, dist_P_N2_mm=abs(N2 - P) * zoom_z, dist_P_N1_mm=abs(N1 - P) * zoom_z, audit=audit, img_sha256=row['img_sha256'], lbl_sha256=row['lbl_sha256'],
                old_png=dict(P=row['P_png'], N1=row['N_png']), old_png_sha=dict(P=row['P_png_sha256'], N1=row['N_png_sha256'])), []


def render_case(c):
    from PIL import Image
    flair, mask, _ = M.load_case(c['case']); a = c['audit']; out = {}
    for role, k in c['z'].items():
        arr = M.render(flair, k, a['vmin'], a['vmax'])
        p = DATA / 'png' / ('%s_%s_z%03d.png' % (c['case'], role, k))
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True); Image.fromarray(arr).save(str(p) + '.tmp.png'); Path(str(p) + '.tmp.png').replace(p)
        back = np.array(Image.open(p).convert('RGB'))
        ms = M.mask_slice(mask, k)
        # render 방향 독립 확인: pixel[Y-1-j, X-1-i] == 정규화된 canonical[i, j, k]
        X, Y = flair.shape[:2]; rng = np.random.default_rng(SEED + k); ii = rng.integers(0, X, 50); jj = rng.integers(0, Y, 50)
        exp = np.round(np.clip((flair[ii, jj, k] - a['vmin']) / (a['vmax'] - a['vmin']), 0, 1) * 255).astype(np.uint8)
        orient_ok = bool(np.array_equal(back[Y - 1 - jj, X - 1 - ii, 0], exp)) and bool((back[:, :, 0] == back[:, :, 1]).all() and (back[:, :, 0] == back[:, :, 2]).all())
        old_equal = None
        if role in ('P', 'N1'):
            op = HERE / c['old_png'][role]
            old_equal = bool(np.array_equal(np.array(Image.open(op).convert('RGB')), back)) if op.exists() else None
        out[role] = dict(path=str(p), sha256=sha(p), size=list(back.shape[:2]), mask_pixels=int(ms.sum()), orient_ok=orient_ok, same_pixels_as_iter064_png=old_equal)
    return out


def overlay(cs, outp):
    from PIL import Image
    flair_cache = {}; rows = []
    for c in cs:
        flair, mask, _ = M.load_case(c['case']); panels = []
        for role, k in c['z'].items():
            g = np.array(Image.open(c['images'][role]['path']).convert('RGB')); ms = M.mask_slice(mask, k)
            edge = ms & ~(np.roll(ms, 1, 0) & np.roll(ms, -1, 0) & np.roll(ms, 1, 1) & np.roll(ms, -1, 1)); g[edge] = [255, 0, 0]
            panels.append(np.array(Image.fromarray(g).resize((256, 256))))
        rows.append(np.concatenate(panels, 1))
    Image.fromarray(np.concatenate(rows, 0)).save(outp)


def make_requests(cases):
    reqs = []
    for c in cases:
        for cond, roles in CONDS.items():
            prompt = QUESTION + (NOIMG if not roles else '')
            assert not any(s in prompt for s in FORBIDDEN_IN_PROMPT)
            r = dict(id=c['case'] + '__' + cond, kind='single', patient=c['case'], cond=cond, roles=roles, prompt=prompt,
                     images=[dict(path=c['images'][ro]['path'], sha256=c['images'][ro]['sha256']) for ro in roles])
            r['request_digest'] = digest(r); reqs.append(r)
    reqs.sort(key=lambda r: hashlib.sha256(('%d|%s' % (SEED, r['id'])).encode()).hexdigest())   # seed로 환자·조건 순서 균형화
    return reqs


def main():
    ds = json.load(open(OLD056 / 'source/dataset.json'))
    assert ds['modality']['0'] == 'FLAIR' and ds['labels'] == {'0': 'background', '1': 'edema', '2': 'non-enhancing tumor', '3': 'enhancing tumour'} and ds['licence'] == 'CC-BY-SA 4.0', ds
    fv = read(OLD056 / 'source/fetch_verify.json')
    tm = {s: read(OLD064 / ('target_manifest_%s.json' % s)) for s in 'DE'}
    ids = {s: [t['case'] for t in tm[s]['targets']] for s in 'DE'}
    assert not set(ids['D']) & set(ids['E']) and len(set(ids['D'])) == 6 and len(set(ids['E'])) == 48
    dup_png = {}
    elig = {'D': [], 'E': []}; excluded = []
    for s in 'DE':
        for t in tm[s]['targets']:
            c, why = inspect(t['case'], t, s)
            if why: excluded.append(c or dict(case=t['case'], split=s, why=why)); continue
            c['images'] = render_case(c); elig[s].append(c)
    for s in 'DE':
        for c in elig[s]:
            for ro, im in c['images'].items(): dup_png.setdefault(im['sha256'], []).append((c['case'], ro))
    # 같은 case 안 P/N1/N2 PNG는 달라야 한다(서로 다른 slice)
    same_within = [c['case'] for s in 'DE' for c in elig[s] if len({im['sha256'] for im in c['images'].values()}) != 3]
    checks = dict(dataset_json_ok=True, licence=ds['licence'], archive_md5_verified=fv, D_E_disjoint=True, n_eligible={s: len(elig[s]) for s in 'DE'}, n_excluded=len(excluded), same_png_within_case=same_within,
                  png_sha_duplicates_across_cases=[v for v in dup_png.values() if len({x[0] for x in v}) > 1], all_orient_ok=all(im['orient_ok'] for s in 'DE' for c in elig[s] for im in c['images'].values()),
                  P_N1_pixels_equal_iter064=all(c['images'][r]['same_pixels_as_iter064_png'] for s in 'DE' for c in elig[s] for r in ('P', 'N1')),
                  rule_reproduces_manifest=all(c['audit']['rule_reproduces_manifest'] for s in 'DE' for c in elig[s]),
                  N2_distance_mm=dict(D=[c['dist_P_N2_mm'] for c in elig['D']], E_max=max(c['dist_P_N2_mm'] for c in elig['E']) if elig['E'] else None))
    run = all(len(elig[s]) >= N_MIN[s] for s in 'DE') and not same_within and not checks['png_sha_duplicates_across_cases'] and checks['all_orient_ok']
    save(DATA / 'manifest.json', dict(created_at=now(), seed=SEED, source=dict(msd56_data_blob='142c67d5063132feadd5aae0028022225d3a18ef', note='load_case/render/mask_slice만 사용'),
                                       n_min=N_MIN, checks=checks, run_models=bool(run), cases={s: elig[s] for s in 'DE'}, excluded=excluded,
                                       note='반복 개발 자료. 독립 test 아님. 종양 annotation 0 slice는 임상 정상이 아니다.'))
    if elig['D']: overlay(elig['D'], DATA / 'D_overlay.png')
    if run:
        save(RES / 'requests/technical.json', make_requests(elig['D'])); save(RES / 'requests/main.json', make_requests(elig['E']))
    print('eligible', {s: len(elig[s]) for s in 'DE'}, 'excluded', len(excluded), 'run', run)
    print({k: v for k, v in checks.items() if k not in ('archive_md5_verified', 'N2_distance_mm')})


if __name__ == '__main__':
    main()
