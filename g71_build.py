"""iter_071 자료 생성·검증: 분할 잠금 -> 56명 중앙 slice PNG·GT -> manifest, 기술 검사(물리좌표 방향·mask 독립·분할 중복·왕복) -> 결과 JSON.
사용: python g71_build.py
"""
import hashlib, json, os, sys, zipfile

import numpy as np
from PIL import Image, ImageDraw

import g71_data as D
import sp67_data as S
from rsna_diag import geometry as G


def main():
    sp = D.load_split()
    pids = sp['T8'] + sp['extra_train16'] + sp['V8'] + sp['E24']
    os.makedirs(D.DATA, exist_ok=True)
    rows, infos = D.build_all(pids)
    man = {'rows': rows, 'patients': infos, 'split': {k: sp[k] for k in ('T8', 'extra_train16', 'T24', 'V8', 'V4', 'E24')}}
    json.dump(man, open(f'{D.DATA}/manifest.json', 'w'))
    print('built', len(rows), 'rows', len(infos), 'patients')

    checks = {}
    # 1. 분할 중복: 환자, source member hash, decoded pixel hash, F139 교집합
    groups = {'T8': sp['T8'], 'extra_train16': sp['extra_train16'], 'V8': sp['V8'], 'E24': sp['E24']}
    inter = {f'{a}&{b}': sorted(set(groups[a]) & set(groups[b])) for a in groups for b in groups if a < b}
    checks['patient_overlap'] = {k: v for k, v in inter.items() if v}
    img_sha = [infos[p]['src_sha']['image'] for p in pids]
    msk_sha = [infos[p]['src_sha']['mask'] for p in pids]
    px = [infos[p]['images'][o]['pixel_sha256_padded'] for p in pids for o in ('m1', 'c', 'p1')]
    checks['dup_source_image_sha'] = len(img_sha) - len(set(img_sha))
    checks['dup_source_mask_sha'] = len(msk_sha) - len(set(msk_sha))
    checks['dup_decoded_pixel_sha'] = len(px) - len(set(px))
    F = set(json.load(open(D.SPLIT_SRC))['F'])
    checks['F139_intersection'] = sorted(set(pids) & F)
    # 2. PNG 재읽기 hash 일치
    bad = 0
    for p in pids:
        for o, im in infos[p]['images'].items():
            if hashlib.sha256(open(im['path'], 'rb').read()).hexdigest() != im['file_sha256']:
                bad += 1
    checks['png_file_hash_mismatch'] = bad
    # 3. bbox 왕복: render xyxy -> norm -> canvas -> 원 native mask pixel 범위, 그리고 독립 SimpleITK 물리 방향 검사
    maxerr, nbox = 0.0, 0
    orient = {}
    phys = []
    for p in pids:
        info = infos[p]
        d = S.load_pair(p, D.SEQ)
        ca = d['ca']
        orient[info['header_orientation']] = orient.get(info['header_orientation'], 0) + 1
        for o, idx in zip(D.OFFSETS, info['selected']):
            im = info['images'][D.OFF_NAME[o]]
            meta = {'scale_row_col': im['scale_row_col'], 'resized_hw': im['resized_hw'], 'pad_top_left_side': im['pad_top_left_side']}
            inst = D.gt_instances(d['L'][idx], meta)
            top, left, side = im['pad_top_left_side']
            for cat in D.CATS:
                for b in inst[cat]:
                    x0, y0, x1, y1 = G.norm_to_canvas(b['yxyx_norm'], top, left, side)
                    r0, c0, r1, c1 = b['bbox_native_rc']
                    sr, sc = im['scale_row_col']
                    maxerr = max(maxerr, abs(x0 - c0 * sc), abs(y0 - r0 * sr), abs(x1 - c1 * sc), abs(y1 - r1 * sr))
                    nbox += 1
        # 독립 물리 검사(SimpleITK): label 1(가장 아래 vertebra)의 물리 z(S+) 중심 < 최상위 label의 물리 z 중심,
        # 그리고 표시 row 중심은 반대 순서(위=superior)여야 한다. canonical -> sitk index -> physical.
        idx = info['selected'][1]
        imgs = S.read_sitk(S.IMG_ZIP, f'images/{p}_{D.SEQ}.mha')[0]
        Lc = d['L'][idx]
        labs = sorted(int(x) for x in np.unique(Lc) if 0 < x < 100)
        def cen(lab):
            pts = np.argwhere(Lc == lab)
            sel = pts[:: max(1, len(pts) // 200)]
            zs, ys = [], []
            for si, pa in sel:
                oi = S.canon_to_orig_index(ca, d['V'].shape, (idx, int(si), int(pa)))
                ph = imgs.TransformIndexToPhysicalPoint(oi)
                zs.append(ph[2]); ys.append(ph[1])
            return float(np.mean(zs)), float(np.mean(ys)), float((d['V'].shape[1] - 1 - pts[:, 0]).mean())
        lo, hi = cen(labs[0]), cen(labs[-1])
        phys.append({'patient': p, 'orientation': info['header_orientation'], 'z_low': lo[0], 'z_high': hi[0], 'row_low': lo[2], 'row_high': hi[2],
                     'ok': bool(lo[0] < hi[0] and lo[2] > hi[2])})
    checks['bbox_roundtrip_max_abs_err_px'] = maxerr
    checks['n_gt_boxes_checked'] = nbox
    checks['physical_orientation_check'] = {'n': len(phys), 'n_ok': sum(x['ok'] for x in phys), 'failures': [x for x in phys if not x['ok']]}
    json.dump(phys, open(f'{D.DATA}/physical_check.json', 'w'), indent=1)
    checks['header_orientation_counts'] = orient
    json.dump(checks, open(f'{D.DATA}/build_checks.json', 'w'), indent=1)
    print(json.dumps(checks, indent=1))


if __name__ == '__main__':
    main()
