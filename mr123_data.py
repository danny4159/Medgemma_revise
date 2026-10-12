"""iter_123: study ZIP 안전 추출, FLAIR/brain-mask 검사, 뇌 범위 기반 slice 선택·렌더링 (규칙 mr123_rules_v1)."""
import hashlib, json, os, zipfile
import numpy as np
import nibabel as nib
from PIL import Image

ROOT = '/home/test/.local/share/medgemma/mr_rate/'
RES = '/SSD1_1TB/home/milab/daniel/08_medgemma/research/results/iter_123/'
SIDE = 896
AREA_FRAC = 0.05  # 뇌 범위: slice별 brain-mask 면적이 최대 면적의 5% 이상인 연속 구간 (사전 고정)
N_SLICE = 8


def sha_file(p):
    d = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            d.update(b)
    return d.hexdigest()


def extract(zip_path, study, series_id, out_root=ROOT + 'extracted/'):
    """flair 영상과 brain-mask만 안전 추출. 경로 이탈·symlink 거부, 기존 파일 덮어쓰기 금지."""
    out = os.path.join(out_root, study)
    os.makedirs(out, exist_ok=True)
    want = {f'{study}/img/{study}_{series_id}.nii.gz': 'img.nii.gz',
            f'{study}/seg/{study}_{series_id}_brain-mask.nii.gz': 'brain.nii.gz'}
    z = zipfile.ZipFile(zip_path)
    res = {}
    for info in z.infolist():
        if info.filename in want:
            assert '..' not in info.filename and not info.filename.startswith('/')
            assert (info.external_attr >> 16) & 0o170000 != 0o120000, 'symlink'
            dst = os.path.join(out, want[info.filename])
            if not os.path.exists(dst):
                with z.open(info) as s, open(dst + '.part', 'wb') as d:
                    while True:
                        b = s.read(1 << 22)
                        if not b:
                            break
                        d.write(b)
                os.replace(dst + '.part', dst)
            res[want[info.filename]] = dict(path=dst, sha256=sha_file(dst), size=os.path.getsize(dst), zip_member=info.filename)
    missing = set(want.values()) - set(res)
    return res, sorted(missing)


def load_case(img_path, brain_path):
    im = nib.load(img_path)
    bm = nib.load(brain_path)
    info = dict(orig_axcodes=''.join(nib.aff2axcodes(im.affine)), shape=list(im.shape), zooms=[float(z) for z in im.header.get_zooms()[:3]],
                brain_shape=list(bm.shape), brain_axcodes=''.join(nib.aff2axcodes(bm.affine)),
                affine_match=bool(np.allclose(im.affine, bm.affine, atol=1e-3)), ndim=len(im.shape))
    if len(im.shape) != 3 or tuple(im.shape) != tuple(bm.shape):
        return None, None, info
    im = nib.as_closest_canonical(im)
    bm = nib.as_closest_canonical(bm)
    a = np.asarray(im.dataobj).astype(np.float32)
    b = np.asarray(bm.dataobj) > 0
    info['canon_axcodes'] = ''.join(nib.aff2axcodes(im.affine))
    info['canon_shape'] = list(a.shape)
    info['canon_zooms'] = [float(z) for z in im.header.get_zooms()[:3]]
    return a, b, info


def brain_range(b):
    area = b.sum(axis=(0, 1)).astype(np.float64)
    if area.max() <= 0:
        return None
    ok = area >= AREA_FRAC * area.max()
    best, s = None, None
    for i, v in enumerate(list(ok) + [False]):
        if v and s is None:
            s = i
        if not v and s is not None:
            if best is None or (i - 1 - s) > (best[1] - best[0]):
                best = (s, i - 1)
            s = None
    return best


def pick(lo, hi, f0, f1, n=N_SLICE):
    L = hi - lo
    pos = [lo + L * (f0 + (f1 - f0) * i / (n - 1)) for i in range(n)]
    idx = [int(round(p)) for p in pos]
    return idx


def intensity_window(a, b):
    v = a[b]
    return float(np.percentile(v, 1)), float(np.percentile(v, 99))


def render_slice(a, k, lo_v, hi_v, zooms):
    s = a[:, :, k]
    s = np.clip((s - lo_v) / max(hi_v - lo_v, 1e-6), 0, 1)
    s = (s * 255 + 0.5).astype(np.uint8)
    img = s.T[::-1, ::-1]  # RAS 정렬 후: 위=anterior, 영상 왼쪽=환자 오른쪽(radiological)
    h, w = img.shape
    # 평면내 spacing 보정 (x: 열 방향 zooms[0], y: 행 방향 zooms[1])
    hh = h * zooms[1]
    ww = w * zooms[0]
    scale = SIDE / max(hh, ww)
    nh, nw = max(1, int(round(hh * scale))), max(1, int(round(ww * scale)))
    pil = Image.fromarray(img).resize((nw, nh), Image.BICUBIC)
    canvas = Image.new('L', (SIDE, SIDE), 0)
    canvas.paste(pil, ((SIDE - nw) // 2, (SIDE - nh) // 2))
    return canvas.convert('RGB')


def build_case(rec, zip_path, out_dir):
    """returns dict with qc info and rendered PNG paths; None 사유 포함."""
    ex, missing = extract(zip_path, rec['study_uid'], rec['series_id'])
    info = dict(study_uid=rec['study_uid'], patient_uid=rec['patient_uid'], series_id=rec['series_id'], files=ex, missing=missing)
    if missing:
        info['exclude'] = 'missing_member:' + ','.join(missing)
        return info
    a, b, li = load_case(ex['img.nii.gz']['path'], ex['brain.nii.gz']['path'])
    info.update(li)
    if a is None:
        info['exclude'] = 'shape_or_ndim_mismatch'
        return info
    if not info['affine_match']:
        info['exclude'] = 'affine_mismatch'
        return info
    if not np.isfinite(a).all():
        info['exclude'] = 'nonfinite'
        return info
    if info['canon_axcodes'] != 'RAS':
        info['exclude'] = 'orientation_not_RAS'
        return info
    br = brain_range(b)
    if br is None:
        info['exclude'] = 'no_brain_range'
        return info
    lo, hi = br
    info['brain_slice_range'] = [lo, hi]
    info['n_brain_slices'] = hi - lo + 1
    info['brain_voxels'] = int(b.sum())
    C = pick(lo, hi, 0.25, 0.75)
    W = pick(lo, hi, 0.05, 0.95)
    info['C_idx'], info['W_idx'] = C, W
    if len(set(C)) < N_SLICE or len(set(W)) < N_SLICE:
        info['exclude'] = 'lt8_unique_slices'
        return info
    lo_v, hi_v = intensity_window(a, b)
    info['window_p1_p99'] = [lo_v, hi_v]
    if not hi_v > lo_v:
        info['exclude'] = 'degenerate_window'
        return info
    os.makedirs(out_dir, exist_ok=True)
    pngs = {}
    for k in sorted(set(C) | set(W)):
        p = os.path.join(out_dir, f'{rec["study_uid"]}_s{k:03d}.png')
        im = render_slice(a, k, lo_v, hi_v, info['canon_zooms'])
        if not os.path.exists(p):
            im.save(p)
        pngs[k] = dict(path=p, sha256=sha_file(p))
    info['pngs'] = {str(k): v for k, v in pngs.items()}
    info['exclude'] = None
    return info


def montage(info, which, out_path):
    ims = [Image.open(info['pngs'][str(k)]['path']).resize((224, 224)) for k in info[which + '_idx']]
    M = Image.new('RGB', (224 * 4, 224 * 2))
    for i, im in enumerate(ims):
        M.paste(im, ((i % 4) * 224, (i // 4) * 224))
    M.save(out_path)
