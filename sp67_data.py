"""iter_067 SPIDER Modic 과제의 자료 연결·기하 검증·IVD 중심 sagittal stack 렌더.

- 영상/mask는 results/iter_021/source/{images,masks}.zip (iter_021 검증본)에서 읽는다. 독립 기준은 SimpleITK(격리 설치, results/environments/sitk67/site).
- 모든 volume을 물리축(LPS: x=L+, y=P+, z=S+) 기준 canonical 배열 V[lr, si, pa]로 바꾼다. 축 선택은 header 문자열이 아니라
  SimpleITK direction 행렬의 지배 성분으로 한다. canonical index -> physical 대응은 SimpleITK TransformIndexToPhysicalPoint로 대조한다.
- mask label 200+k(k=1이 가장 아래)와 radiological_gradings.csv의 'IVD label' k를 연결한다. 해부학 이름으로 변환하지 않는다.
- 모델 입력에는 Modic 등급·병변 mask·신호 설명을 넣지 않는다. IVD mask는 위치 지정 oracle(crop 범위 계산)로만 사용한다.
"""
import csv, hashlib, io, json, os, sys, tempfile, zipfile

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results/environments/sitk67/site'))
import SimpleITK as sitk  # noqa: E402

from rsna_diag import mi19_mha as M  # noqa: E402
from rsna_diag import mi19_render as R  # noqa: E402

SRC = 'results/iter_021/source'
IMG_ZIP, MSK_ZIP = f'{SRC}/images.zip', f'{SRC}/masks.zip'
GRADES = f'{SRC}/radiological_gradings.csv'
SPLIT = 'results/iter_021/data/split.json'
TMP = 'results/iter_067/tmp'
SIDE = 448            # 모든 slice를 SIDE x SIDE 정사각 canvas로(긴 변 기준 물리 등방 resize 후 중앙 padding)
MARGIN_SI_FACTOR = 1.0   # superior/inferior 각각 disc AP 폭 x 1.0
MARGIN_AP_FACTOR = 0.25  # AP 방향 각각 폭 x 0.25
GRID_TOL = 1e-4
LABELS = ['0', 'I', 'II', 'III']


def sha_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for ch in iter(lambda: f.read(1 << 22), b''):
            h.update(ch)
    return h.hexdigest()


def read_sitk(zpath, member):
    """zip member -> SimpleITK image (임시 파일은 읽은 뒤 제거)."""
    os.makedirs(TMP, exist_ok=True)
    data = zipfile.ZipFile(zpath).read(member)
    fd, p = tempfile.mkstemp(suffix='.mha', dir=TMP)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        img = sitk.ReadImage(p)
        img = sitk.Cast(img, img.GetPixelID())  # 파일 의존 해제(메모리 로드)
        arr_check = sitk.GetArrayFromImage(img)
    finally:
        try:
            os.remove(p)
        except OSError:
            pass
    return img, data, arr_check


class GeomError(RuntimeError):
    pass


def canon_axes(direction):
    """direction(9, row-major, SimpleITK) -> {'perm': [array axis for canonical axis (x,z,y)], 'flip': [bool]*3, 'idx_axis': [index axis i]}.
    index axis i의 방향 = D[:, i]. 각 index axis는 하나의 물리축에 지배적(>=0.9)으로 대응해야 한다."""
    D = np.array(direction, dtype=float).reshape(3, 3)
    if not np.all(np.isfinite(D)):
        raise GeomError('non-finite direction')
    phys_of_idx, sign_of_idx = {}, {}
    for i in range(3):
        col = D[:, i]
        p = int(np.argmax(np.abs(col)))
        if abs(col[p]) < 0.9:
            raise GeomError(f'index axis {i} not dominantly aligned: {col}')
        phys_of_idx[i], sign_of_idx[i] = p, (1 if col[p] > 0 else -1)
    if sorted(phys_of_idx.values()) != [0, 1, 2]:
        raise GeomError(f'index->physical axes not a permutation: {phys_of_idx}')
    idx_of_phys = {p: i for i, p in phys_of_idx.items()}
    order_phys = [0, 2, 1]  # canonical axes: x(L), z(S), y(P)
    idx_axis = [idx_of_phys[p] for p in order_phys]
    return {'idx_axis': idx_axis, 'flip': [sign_of_idx[i] < 0 for i in idx_axis],
            'perm': [2 - i for i in idx_axis]}  # numpy array axis = 2 - index axis


def to_canonical(arr_zyx, spacing_xyz, ca):
    V = np.transpose(arr_zyx, ca['perm'])
    for ax, fl in enumerate(ca['flip']):
        if fl:
            V = np.flip(V, axis=ax)
    sp = [spacing_xyz[i] for i in ca['idx_axis']]
    return np.ascontiguousarray(V), sp


def canon_to_orig_index(ca, shape_can, idx_can):
    """canonical index (a,b,c) -> sitk index (i,j,k) (x,y,z 순)."""
    out = [0, 0, 0]
    for ax in range(3):
        v = idx_can[ax]
        if ca['flip'][ax]:
            v = shape_can[ax] - 1 - v
        out[ca['idx_axis'][ax]] = int(v)
    return out


def grid_equal(a, b):
    if a.GetSize() != b.GetSize():
        return False
    for u, v in ((a.GetSpacing(), b.GetSpacing()), (a.GetOrigin(), b.GetOrigin()), (a.GetDirection(), b.GetDirection())):
        if not np.allclose(u, v, rtol=GRID_TOL, atol=1e-4):
            return False
    return True


def load_pair(pid, seq):
    """영상+mask를 읽고 기하 검증 후 canonical volume/label을 반환. 오류는 GeomError."""
    img, ibytes, iarr = read_sitk(IMG_ZIP, f'images/{pid}_{seq}.mha')
    msk, mbytes, marr = read_sitk(MSK_ZIP, f'masks/{pid}_{seq}.mha')
    if not grid_equal(img, msk):
        raise GeomError('image/mask grid mismatch')
    if not np.all(np.isfinite(iarr.astype(np.float64))):
        raise GeomError('non-finite image values')
    sp = img.GetSpacing()
    if not all(np.isfinite(s) and s > 0 for s in sp):
        raise GeomError(f'non-positive spacing {sp}')
    ca = canon_axes(img.GetDirection())
    V, spc = to_canonical(iarr, sp, ca)
    L, _ = to_canonical(marr, sp, ca)
    # 독립 기준(SimpleITK physical)과 대조: mask 내 임의 voxel 8개
    rng = np.random.RandomState(0)
    coords = np.argwhere(L >= 200)
    pts = coords[rng.choice(len(coords), min(8, len(coords)), replace=False)] if len(coords) else []
    maxerr = 0.0
    for c in pts:
        oi = canon_to_orig_index(ca, V.shape, c)
        # 원 배열 값과 canonical 값이 같은 voxel인지
        if iarr[oi[2], oi[1], oi[0]] != V[tuple(c)] or marr[oi[2], oi[1], oi[0]] != L[tuple(c)]:
            raise GeomError('canonical voxel does not match original voxel')
        ph = np.array(img.TransformIndexToPhysicalPoint(oi))
        # canonical 축 (x, z, y)의 물리 성분을 회전 없이 재현: 이웃 voxel 차이가 canonical 축 방향과 일치해야 함
        for ax in range(3):
            d = np.zeros(3, int); d[ax] = 1
            c2 = tuple(np.array(c) + d)
            if c2[ax] >= V.shape[ax]:
                continue
            oi2 = canon_to_orig_index(ca, V.shape, c2)
            ph2 = np.array(img.TransformIndexToPhysicalPoint(oi2))
            delta = ph2 - ph
            phys_axis = [0, 2, 1][ax]
            maxerr = max(maxerr, abs(abs(delta[phys_axis]) - spc[ax]) / spc[ax] if abs(delta[phys_axis]) > 0.9 * spc[ax] else 1.0)
            if delta[phys_axis] <= 0:
                raise GeomError(f'canonical axis {ax} does not increase along physical axis {phys_axis}')
    D = np.array(img.GetDirection()).reshape(3, 3)
    return {'V': V, 'L': L, 'spacing': spc, 'ca': ca, 'src_sha': {'image': hashlib.sha256(ibytes).hexdigest(), 'mask': hashlib.sha256(mbytes).hexdigest()},
            'tilt_deg': float(max(np.degrees(np.arccos(min(1.0, np.abs(D[:, i]).max()))) for i in range(3))),
            'physical_check_max_rel_err': float(maxerr), 'size_xyz': list(img.GetSize()),
            'direction': [float(x) for x in img.GetDirection()], 'origin': [float(x) for x in img.GetOrigin()],
            'header': M.parse_header(ibytes[:8192])[0].get('AnatomicalOrientation')}


def ivd_info(L, spacing):
    """label 201.. -> bbox(canonical idx inclusive)와 S 중심(mm, canonical z index 기반)."""
    out = {}
    for lab in np.unique(L):
        if lab < 200:
            continue
        idx = np.argwhere(L == lab)
        lo, hi = idx.min(0), idx.max(0)
        out[int(lab) - 200] = {'lo': [int(x) for x in lo], 'hi': [int(x) for x in hi], 'n_vox': int(len(idx)),
                               'si_center_mm': float(idx[:, 1].mean() * spacing[1])}
    return out


def read_grades():
    rows = {}
    with open(GRADES) as f:
        for r in csv.DictReader(f):
            rows[(r['Patient'], int(r['IVD label']))] = int(r['Modic'])
    return rows


def crop_box(info, shape, spacing):
    """IVD bbox -> crop index range (si, pa)와 clipping/margin 기록. 좌우 slice는 전부 사용."""
    sx, ss, sp_ = spacing
    s_lo, s_hi, p_lo, p_hi = info['lo'][1], info['hi'][1], info['lo'][2], info['hi'][2]
    W = (p_hi - p_lo + 1) * sp_   # disc AP 폭(mm)
    s0 = int(np.floor(s_lo - MARGIN_SI_FACTOR * W / ss)); s1 = int(np.ceil(s_hi + 1 + MARGIN_SI_FACTOR * W / ss))
    p0 = int(np.floor(p_lo - MARGIN_AP_FACTOR * W / sp_)); p1 = int(np.ceil(p_hi + 1 + MARGIN_AP_FACTOR * W / sp_))
    c = {'si_clipped_lo': s0 < 0, 'si_clipped_hi': s1 > shape[1], 'pa_clipped_lo': p0 < 0, 'pa_clipped_hi': p1 > shape[2]}
    s0c, s1c, p0c, p1c = max(0, s0), min(shape[1], s1), max(0, p0), min(shape[2], p1)
    return {'si': [s0c, s1c], 'pa': [p0c, p1c], 'disc_ap_width_mm': float(W), 'clip': c,
            'margin_mm': {'sup': float((s_lo - s0c) * ss), 'inf': float((s1c - 1 - s_hi) * ss), 'ant': float((p_lo - p0c) * sp_), 'post': float((p1c - 1 - p_hi) * sp_)}}


def render_stack(V, spacing, cb, side=SIDE):
    """canonical volume V[lr,si,pa]의 모든 sagittal slice를 같은 crop·window·scale로 side x side RGB uint8 목록으로 반환.
    row=superior(위)->inferior, col=anterior->posterior(physical y 증가 방향)."""
    lo, hi = R.volume_window(V)
    s0, s1 = cb['si']; p0, p1 = cb['pa']
    h_mm, w_mm = (s1 - s0) * spacing[1], (p1 - p0) * spacing[2]
    mm_per_px = max(h_mm, w_mm) / side
    new_h, new_w = max(1, round(h_mm / mm_per_px)), max(1, round(w_mm / mm_per_px))
    top, left = (side - new_h) // 2, (side - new_w) // 2
    outs = []
    for i in range(V.shape[0]):
        sl = V[i, s0:s1, p0:p1][::-1]
        u8 = R.to_uint8(sl, lo, hi)
        im = Image.fromarray(u8, mode='L').resize((new_w, new_h), resample=Image.BILINEAR)
        canvas = np.zeros((side, side), np.uint8)
        canvas[top:top + new_h, left:left + new_w] = np.asarray(im)
        outs.append(np.repeat(canvas[:, :, None], 3, axis=2))
    return outs, {'window': [lo, hi], 'resized_hw': [new_h, new_w], 'pad_top_left': [top, left], 'mm_per_px': mm_per_px}


def save_png(path, arr):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format='PNG')
    tmp = f'{path}.tmp{os.getpid()}'
    with open(tmp, 'wb') as f:
        f.write(buf.getvalue())
    os.replace(tmp, path)
    return hashlib.sha256(buf.getvalue()).hexdigest()
