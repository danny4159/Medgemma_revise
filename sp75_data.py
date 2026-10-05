"""iter_075 SPIDER Pfirrmann(IVD ordinal) 자료: allowlist·위치 분할·등급 연결·ROI·F/R 입력 materialize·검증.

- 환자 분리: results/iter_071/data/split_lock.json(T24/V8/E24)을 새 make_split과 대조해 그대로 사용한다. F139와 개발 56명 밖의 환자는 접근하지 않는다.
- 등급: radiological_gradings.csv를 환자 ID 필터 뒤에 읽는다(허용 환자·필요한 (split, ordinal)만 보관). T24/V8의 ordinal 2/4 등급은 보관하지 않는다.
  'Pfirrman grade' 1-5를 그대로 보존하고 결측/범위 밖은 imputation 없이 기술 제외로 기록한다.
- 위치: 학습 supervision ordinal {1,3,5}; 미제공(held) ordinal {2,4}는 E24 평가에서만 읽는다. ordinal은 해부학 이름(L1-S1)이 아니다.
- 영상: g71_data.render_slice(regular T2, 중앙 j-1,j,j+1, volume min-max, spacing 보정). slice 선택은 mask/grade와 무관.
- ROI: 대상 disc mask(label 200+k)의 세 slice bbox union(+각 방향 25%). 중앙 slice에 mask가 없거나 연결 성분이 2개 이상이면 사전 기술 제외.
  F: 전체 slice에 ROI 바깥 경계만 빨간 선(두께 2px)으로 표시. R/C: 같은 ROI를 세 slice에 공통 crop.
"""
import csv, hashlib, io, json, os, sys

import numpy as np
from PIL import Image

import g71_data as G71
import sp67_data as S
from rsna_diag import generate as GEN

OUT = 'results/iter_075'
DATA = f'{OUT}/data'
S.TMP = f'{OUT}/tmp'
G71.DATA = DATA
SUPERVISED = (1, 3, 5)
HELD = (2, 4)
MARGIN = 0.25
LINE = 2
OFFS = G71.OFFSETS
OFFN = G71.OFF_NAME
SPLIT_LOCK_071 = 'results/iter_071/data/split_lock.json'
GRADE_CSV = S.GRADES


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def tid(pid, k):
    return f'{pid}_k{k:02d}'


def load_split():
    """iter_071 잠금 분할을 읽고 현재 make_split과 대조. 허용 환자와 split 이름 반환."""
    sp = json.load(open(SPLIT_LOCK_071))
    G71.FORBIDDEN = set(json.load(open(G71.SPLIT_SRC))['F'])
    want, _ = G71.make_split()
    for key in ('T8', 'extra_train16', 'V8', 'E24', 'T24', 'V4'):
        assert sp[key] == want[key], f'split lock mismatch {key}'
    split_of = {}
    for name in ('T24', 'V8', 'E24'):
        for p in sp[name]:
            assert p not in split_of and p not in G71.FORBIDDEN
            split_of[p] = name
    assert len(split_of) == 56
    return sp, split_of


def read_grades(split_of):
    """Patient 필터를 먼저 적용. 필요한 (split, ordinal)만 보관. 반환 {(pid,k): {'grade': int|None, 'raw': str, 'split': s}}와 감사 정보."""
    out, dup, n_rows_total, n_rows_allowed = {}, [], 0, 0
    with open(GRADE_CSV) as f:
        for r in csv.DictReader(f):
            n_rows_total += 1
            pid = r['Patient']
            if pid not in split_of:      # F139 및 기타 환자의 등급은 파싱·집계하지 않는다
                continue
            n_rows_allowed += 1
            k = int(r['IVD label'])
            sname = split_of[pid]
            need = SUPERVISED + HELD if sname == 'E24' else SUPERVISED
            if k not in need:
                continue
            raw = r['Pfirrman grade']
            if (pid, k) in out:
                dup.append((pid, k))
                continue
            try:
                g = int(raw)
                g = g if 1 <= g <= 5 else None
            except ValueError:
                g = None
            out[(pid, k)] = {'grade': g, 'raw': raw, 'split': sname}
    return out, {'rows_total': n_rows_total, 'rows_allowed_patients': n_rows_allowed, 'duplicates': dup}


def components_2d(mask2d):
    import SimpleITK as sitk
    img = sitk.GetImageFromArray(mask2d.astype(np.uint8))
    cc = sitk.ConnectedComponent(img, True)
    return int(sitk.GetArrayFromImage(cc).max())


def roi_for(L_slices, metas, k):
    """L_slices: {off: canonical label slice[si,pa]}; metas: render meta. returns (roi dict | None, exclusion reason | None)."""
    lab = 200 + k
    per, boxes = {}, []
    for off in OFFS:
        M = L_slices[off][::-1]
        sr, sc = metas[off]['scale_row_col']
        rr, cc = np.nonzero(M == lab)
        if len(rr) == 0:
            per[OFFN[off]] = {'n_vox': 0}
            continue
        r0, c0, r1, c1 = int(rr.min()), int(cc.min()), int(rr.max()) + 1, int(cc.max()) + 1
        per[OFFN[off]] = {'n_vox': int(len(rr)), 'bbox_native_rc': [r0, c0, r1, c1], 'xyxy_px': [c0 * sc, r0 * sr, c1 * sc, r1 * sr]}
        boxes.append(per[OFFN[off]]['xyxy_px'])
    if per['c']['n_vox'] == 0:
        return None, 'target mask absent in central slice', per
    ncomp = components_2d(L_slices[0][::-1] == lab)
    per['c']['n_components'] = ncomp
    if ncomp != 1:
        return None, f'target mask has {ncomp} connected components in central slice', per
    x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes); x1 = max(b[2] for b in boxes); y1 = max(b[3] for b in boxes)
    w, h = x1 - x0, y1 - y0
    nh, nw = metas[0]['resized_hw']
    ex = [x0 - MARGIN * w, y0 - MARGIN * h, x1 + MARGIN * w, y1 + MARGIN * h]
    clipped = [ex[0] < 0, ex[1] < 0, ex[2] > nw, ex[3] > nh]
    roi = [max(0.0, ex[0]), max(0.0, ex[1]), min(float(nw), ex[2]), min(float(nh), ex[3])]
    # 정수 pixel crop 범위(half-open): floor/ceil
    ib = [int(np.floor(roi[0])), int(np.floor(roi[1])), int(np.ceil(roi[2])), int(np.ceil(roi[3]))]
    return {'union_xyxy_px': [x0, y0, x1, y1], 'roi_xyxy_px': roi, 'roi_int_xyxy': ib, 'clipped_lo_x_lo_y_hi_x_hi_y': clipped,
            'margin': MARGIN, 'slices_present': [OFFN[o] for o in OFFS if per[OFFN[o]]['n_vox'] > 0]}, None, per


def draw_outline(arr_rgb, roi_int):
    """ROI 바깥 경계에 두께 LINE px 빨간 선. ROI 내부는 변경하지 않는다. 영상 밖은 clip."""
    out = arr_rgb.copy()
    H, W = out.shape[:2]
    x0, y0, x1, y1 = roi_int
    X0, Y0, X1, Y1 = x0 - LINE, y0 - LINE, x1 + LINE, y1 + LINE
    m = np.zeros((H, W), bool)
    xs0, xs1, ys0, ys1 = max(0, X0), min(W, X1), max(0, Y0), min(H, Y1)
    m[ys0:ys1, xs0:xs1] = True
    m[max(0, y0):min(H, y1), max(0, x0):min(W, x1)] = False
    out[m] = (255, 0, 0)
    return out, int(m.sum())


def save_png_bytes(path, arr, mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    Image.fromarray(arr, mode=mode).save(buf, format='PNG') if mode else Image.fromarray(arr).save(buf, format='PNG')
    tmp = f'{path}.tmp{os.getpid()}'
    with open(tmp, 'wb') as f:
        f.write(buf.getvalue())
    os.replace(tmp, path)
    return sha_bytes(buf.getvalue())


def build_patient(pid, grades, split_of):
    """한 환자의 영상 3장과 해당 target 목록(ROI, F/R 입력)을 만든다."""
    assert pid in split_of
    G71.guard(pid)
    d = S.load_pair(pid, G71.SEQ)
    V, L, spc = d['V'], d['L'], d['spacing']
    n = V.shape[0]
    idxs = G71.select_slices(n)
    metas, base_paths, base_sha, L_slices = {}, {}, {}, {}
    for off, idx in zip(OFFS, idxs):
        arr, meta = G71.render_slice(V, spc, idx)
        path = f'{DATA}/images/{pid}_{OFFN[off]}.png'
        base_sha[off] = save_png_bytes(path, arr, 'L')
        _, aff, pxsha = GEN.load_image(path)
        assert list(aff) == meta['pad_top_left_side']
        metas[off] = dict(meta, slice_index=int(idx), file_sha256=base_sha[off], pixel_sha256_padded=pxsha, path=path)
        base_paths[off] = path
        L_slices[off] = L[idx]
    present = sorted(int(x) - 200 for x in np.unique(L) if x >= 200)
    rows = []
    sname = split_of[pid]
    for k in (SUPERVISED + HELD if sname == 'E24' else SUPERVISED):
        g = grades.get((pid, k))
        row = {'id': tid(pid, k), 'patient': pid, 'ordinal': k, 'split': sname, 'position_set': 'supervised' if k in SUPERVISED else 'held',
               'grade': None if g is None else g['grade'], 'grade_raw': None if g is None else g['raw'], 'excluded': None}
        if g is None:
            row['excluded'] = 'no grading row for this Patient x IVD'
        elif g['grade'] is None:
            row['excluded'] = f"grade missing/out of range raw={g['raw']!r}"
        elif k not in present:
            row['excluded'] = f'no mask label {200 + k} in volume'
        if row['excluded']:
            rows.append(row)
            continue
        roi, why, per = roi_for(L_slices, metas, k)
        row['slices'] = per
        if roi is None:
            row['excluded'] = why
            rows.append(row)
            continue
        row['roi'] = roi
        row['inputs'] = {'F': [], 'R': []}
        for off in OFFS:
            img = np.asarray(Image.open(base_paths[off]))
            rgb = np.repeat(img[:, :, None], 3, axis=2)
            fimg, n_line = draw_outline(rgb, roi['roi_int_xyxy'])
            fp = f'{DATA}/inputs/F/{tid(pid, k)}_{OFFN[off]}.png'
            fsha = save_png_bytes(fp, fimg)
            x0, y0, x1, y1 = roi['roi_int_xyxy']
            crop = img[y0:y1, x0:x1]
            rp = f'{DATA}/inputs/R/{tid(pid, k)}_{OFFN[off]}.png'
            rsha = save_png_bytes(rp, crop, 'L')
            _, _, fpx = GEN.load_image(fp)
            _, _, rpx = GEN.load_image(rp)
            row['inputs']['F'].append({'off': OFFN[off], 'path': fp, 'file_sha256': fsha, 'pixel_sha256_padded': fpx, 'outline_pixels': n_line})
            row['inputs']['R'].append({'off': OFFN[off], 'path': rp, 'file_sha256': rsha, 'pixel_sha256_padded': rpx, 'crop_hw': list(crop.shape)})
        rows.append(row)
    info = {'patient': pid, 'split': sname, 'n_lr': int(n), 'selected': idxs, 'spacing_canon': [float(x) for x in spc], 'direction': d['direction'], 'origin': d['origin'],
            'header_orientation': d['header'], 'src_sha': d['src_sha'], 'size_xyz': d['size_xyz'], 'tilt_deg': d['tilt_deg'],
            'physical_check_max_rel_err': d['physical_check_max_rel_err'], 'ivd_labels_present': present,
            'images': {OFFN[o]: metas[o] for o in OFFS}}
    return rows, info


def build_all():
    sp, split_of = load_split()
    grades, gaudit = read_grades(split_of)
    all_rows, infos = [], {}
    for pid in sorted(split_of, key=int):
        rows, info = build_patient(pid, grades, split_of)
        all_rows += rows
        infos[pid] = info
    return all_rows, infos, gaudit, sp, split_of


def load_manifest():
    return json.load(open(f'{DATA}/manifest.json'))


if __name__ == '__main__':
    os.makedirs(DATA, exist_ok=True)
    rows, infos, gaudit, sp, split_of = build_all()
    man = {'rows': rows, 'patients': infos, 'grade_audit': gaudit, 'split': {k: sp[k] for k in ('T24', 'V8', 'E24')},
           'grade_csv_sha256': S.sha_file(GRADE_CSV), 'split_lock_sha256': S.sha_file(SPLIT_LOCK_071), 'margin': MARGIN, 'line_px': LINE}
    tmp = f'{DATA}/manifest.json.tmp'
    json.dump(man, open(tmp, 'w'), indent=1)
    os.replace(tmp, f'{DATA}/manifest.json')
    exc = [r for r in rows if r['excluded']]
    print('targets', len(rows), 'excluded', len(exc))
    for r in exc:
        print(r['id'], r['split'], r['ordinal'], r['excluded'])
