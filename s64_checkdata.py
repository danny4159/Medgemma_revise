"""iter_064 자료 검사: (1) NIfTI→PNG 독립 계산(nibabel orientation 변환 경로, msd56_data와 다른 코드) 비교
(2) P/N 규칙 독립 재선택 (3) split/ID/pixel 중복 (4) 요청 구조·GT 비노출 (5) D6 overlay 저장.
출력: results/iter_064/tests/data_check.json, D6_overlay.png"""
import json, hashlib, sys
import numpy as np, nibabel as nib
from PIL import Image
import msd56_data as MD
import s64_data as S

ROOT = S.ROOT
res = {'fails': 0, 'checks': []}


def chk(name, ok, **kw):
    res['checks'].append({'name': name, 'ok': bool(ok), **kw})
    if not ok:
        res['fails'] += 1


def indep_arrays(cid):
    ip, lp = MD.case_paths(cid)
    img, lbl = nib.load(ip), nib.load(lp)
    ornt = nib.orientations.io_orientation(img.affine)
    ras = nib.orientations.axcodes2ornt(('R', 'A', 'S'))
    tr = nib.orientations.ornt_transform(ornt, ras)
    fl = nib.orientations.apply_orientation(np.asarray(img.dataobj[..., 0], dtype=np.float32), tr)
    mk = nib.orientations.apply_orientation(np.asarray(lbl.dataobj), tr)
    return fl, mk


def disp(a, k):  # 행: anterior 위, 열: 환자 right가 영상 왼쪽 (서술된 규약을 별도 표현)
    s = a[:, :, k]            # (R,A)
    s = np.flipud(s)          # R축 반전 -> 왼쪽이 patient right 쪽... (msd56_data: [::-1,:,k].T[::-1])
    s = s.T                   # (A,R)
    return np.flipud(s)       # anterior 위


def main():
    cases = {c['case']: c for c in json.load(open(f'{S.SRC}/cases.json'))['chosen']}
    allp = {}
    seen_img, seen_split = {}, {}
    for split in ('D', 'E'):
        man = json.load(open(f'{ROOT}/data/target_manifest_{split}.json'))
        reqs = [json.loads(l) for l in open(f'{ROOT}/data/requests_{split}.jsonl')]
        labels = json.load(open(f'{ROOT}/data/labels_{split}.json'))
        for t in man['targets']:
            cid = t['case']
            fl, mk = indep_arrays(cid)
            c = cases[cid]
            ann = mk > 0
            areas = [int(ann[:, :, k].sum()) for k in range(ann.shape[2])]
            nzs = [int((fl[:, :, k] != 0).sum()) for k in range(fl.shape[2])]
            Pz = int(np.argmax(areas))  # argmax = first max = smallest z
            zero = [k for k in range(len(areas)) if areas[k] == 0]
            Nz = max(zero, key=lambda k: (nzs[k], -k))
            chk(f'{cid} P/N reselect', Pz == t['P_z'] and Nz == t['N_z'] and areas[Pz] > 0 and areas[Nz] == 0, P=Pz, N=Nz)
            for kind, z in (('P', Pz), ('N', Nz)):
                s = disp(fl, z)
                u = np.round(np.clip((s - c['vmin']) / (c['vmax'] - c['vmin']), 0, 1) * 255).astype(np.uint8)
                png = np.array(Image.open(t[f'{kind}_png']))
                chk(f'{cid} {kind} png==indep', png.shape == (*u.shape, 3) and (png == u[:, :, None]).all() and (png[..., 0] == png[..., 1]).all())
                chk(f'{cid} {kind} mask-slice match', int(disp(ann, z).sum()) == t[f'{kind}_mask_sum'] == (areas[z]))
                chk(f'{cid} {kind} png sha', S.sha_file(t[f'{kind}_png']) == t[f'{kind}_png_sha256'])
                allp.setdefault(t[f'{kind}_png_sha256'], []).append((cid, kind))
            seen_img.setdefault(t['img_sha256'], []).append(cid)
            seen_split.setdefault(cid, []).append(split)
        # 요청 구조
        by = {}
        for r in reqs:
            by[r['rid']] = r
            ims = r['images']
            tgt = ims[r['k'] - 1]
            tman = {t['case']: t for t in man['targets']}[r['case']]
            ok = tgt == tman[f"{r['target']}_png"] and len(ims) == (1 if r['cond'] == 'S' else 2) and r['prompt'] == S.PROMPT.format(k=r['k'])
            if r['cond'].startswith('R'):
                ok = ok and ims[0] == ims[1]
            if r['cond'].startswith('C'):
                oth = ims[2 - r['k']]
                ok = ok and oth == tman['N_png' if r['target'] == 'P' else 'P_png']
            chk(f"req {r['rid']}", ok)
            blob = json.dumps(r)
            leak = [x for x in (r['case'], 'BRATS', 'mask', 'label') if x in r['prompt'] or any(x in p for p in ims)]
            chk(f"leak {r['rid']}", not leak and r['rid'].count('__') == 2)
        chk(f'{split} requests==labels keys', set(by) == set(labels) and len(by) == 10 * len(man['targets']))
        # overlay (D만)
        if split == 'D':
            rows = []
            for t in man['targets']:
                c = cases[t['case']]
                fl, mk = indep_arrays(t['case'])
                tiles = []
                for kind in ('P', 'N'):
                    z = t[f'{kind}_z']
                    g = np.array(Image.open(t[f'{kind}_png'])).copy()
                    m = disp(mk > 0, z)
                    edge = m & ~(np.roll(m, 1, 0) & np.roll(m, -1, 0) & np.roll(m, 1, 1) & np.roll(m, -1, 1))
                    g[edge] = [255, 0, 0]
                    tiles.append(g)
                rows.append(np.concatenate(tiles, axis=1))
            w = max(r.shape[1] for r in rows)
            rows = [np.pad(r, ((0, 0), (0, w - r.shape[1]), (0, 0))) for r in rows]
            Image.fromarray(np.concatenate(rows, axis=0)).save(f'{ROOT}/tests/D6_overlay.png')
    dup_img = [v for v in seen_img.values() if len(v) > 1]
    chk('no duplicate raw image across D/E cases', not dup_img, dup=dup_img)
    chk('case in exactly one split', all(len(v) == 1 for v in seen_split.values()))
    ps = [v for v in allp.values() if len(v) > 1]
    chk('no duplicate rendered png across (case,kind)', not ps, dup=ps[:3])
    json.dump(res, open(f'{ROOT}/tests/data_check.json', 'w'), indent=1)
    print('fails', res['fails'], 'of', len(res['checks']))
    sys.exit(1 if res['fails'] else 0)


if __name__ == '__main__':
    import os
    os.makedirs(f'{ROOT}/tests', exist_ok=True)
    main()
