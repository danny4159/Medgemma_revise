"""iter_125: SynthSeg 결과 -> 원 T2 격자 변환, U/A slice 선택, 렌더링(896 canvas, brain p1-p99), 점수 S(측뇌실 부피/ICV), QC.
mr123_data.py의 brain_range/intensity_window/render_slice/pick을 재사용(렌더 규칙 동일). usage: python mr125_build.py ROLE"""
import hashlib, json, os, sys
import numpy as np
import nibabel as nib
from PIL import Image
import mr123_data as D

RES = 'results/iter_125/'
LV = (4, 43)  # SynthSeg left/right lateral ventricle (labels table 확인; inferior lateral 5/44 제외)
FRAC = 0.05
N = 8


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def spread(lo, hi, n=N):
    return [int(round(lo + (hi - lo) * i / (n - 1))) for i in range(n)]


def resample_nn(vol, vaff, shape, aff):
    """nearest-neighbor: 목표 격자 voxel -> world -> 원 seg voxel 인덱스 (scipy 없이)."""
    M = np.linalg.inv(vaff) @ aff
    out = np.zeros(shape, dtype=vol.dtype)
    ii, jj = np.meshgrid(np.arange(shape[0]), np.arange(shape[1]), indexing='ij')
    for k in range(shape[2]):
        p = M[:3, 0, None] * ii.ravel()[None] + M[:3, 1, None] * jj.ravel()[None] + (M[:3, 2, None] * k + M[:3, 3, None])
        q = np.rint(p).astype(np.int64)
        ok = np.all((q >= 0) & (q < np.array(vol.shape)[:, None]), axis=0)
        v = np.zeros(ii.size, dtype=vol.dtype)
        v[ok] = vol[q[0, ok], q[1, ok], q[2, ok]]
        out[:, :, k] = v.reshape(shape[0], shape[1])
    return out


def build(m, prov, out_png):
    f = prov['files']
    im = nib.load(f['img.nii.gz']['path'])
    bm = nib.load(f['brain.nii.gz']['path'])
    seg = nib.load(prov['seg'])
    info = dict(study_uid=m['study_uid'], patient_uid=m['patient_uid'], label=m['label'], batch_id=m['batch_id'], role=m['role'], series_id=m['series_id'],
                orig_axcodes=''.join(nib.aff2axcodes(im.affine)), shape=list(im.shape), zooms=[float(z) for z in im.header.get_zooms()[:3]],
                seg_shape=list(seg.shape), seg_axcodes=''.join(nib.aff2axcodes(seg.affine)), seg_zooms=[float(z) for z in seg.header.get_zooms()[:3]])
    if len(im.shape) != 3 or im.shape != bm.shape or not np.allclose(im.affine, bm.affine, atol=1e-3):
        info['exclude'] = 'img_brain_mismatch'
        return info
    # 1mm seg -> 원 T2 격자 (nearest). 원 T2 grid 위 mask
    sd_native = np.rint(np.asarray(seg.dataobj)).astype(np.int16)
    sd = resample_nn(sd_native, seg.affine, im.shape, im.affine)
    # canonical RAS 정렬
    ic = nib.as_closest_canonical(im)
    bc = nib.as_closest_canonical(bm)
    sc = nib.as_closest_canonical(nib.Nifti1Image(sd, im.affine))
    a = np.asarray(ic.dataobj).astype(np.float32)
    b = np.asarray(bc.dataobj) > 0
    s = np.asarray(sc.dataobj)
    info['canon_axcodes'] = ''.join(nib.aff2axcodes(ic.affine))
    info['canon_zooms'] = [float(z) for z in ic.header.get_zooms()[:3]]
    if info['canon_axcodes'] != 'RAS' or not np.isfinite(a).all():
        info['exclude'] = 'orientation_or_nonfinite'
        return info
    br = D.brain_range(b)
    if br is None:
        info['exclude'] = 'no_brain_range'
        return info
    lo, hi = br
    info['brain_slice_range'] = [lo, hi]
    vent = np.isin(s, LV)
    # 부피(1mm native seg 기준) / ICV = native seg 비배경 voxel 합 (SynthSeg의 total intracranial 정의)
    vz = float(np.prod(seg.header.get_zooms()[:3]))
    v_vent = float(np.isin(sd_native, LV).sum() * vz)
    icv = float((sd_native > 0).sum() * vz)
    info['vent_mm3'] = v_vent
    info['icv_mm3'] = icv
    info['S'] = v_vent / icv if icv > 0 else None
    info['vent_voxels_in_T2_grid'] = int(vent.sum())
    info['vent_in_brainmask_frac'] = float((vent & b).sum() / max(vent.sum(), 1))
    info['vent_vol_ratio_T2grid_vs_native'] = float(vent.sum() * np.prod(info['canon_zooms']) / max(v_vent, 1))
    area = vent.sum(axis=(0, 1)).astype(float)
    info['vent_area_by_slice'] = area.tolist()
    # U
    U = D.pick(lo, hi, 0.05, 0.95)
    info['U_idx'] = U
    # A
    info['A_fallback'] = None
    A = None
    if area.max() > 0:
        ok = np.where(area >= FRAC * area.max())[0]
        alo, ahi = int(ok.min()), int(ok.max())
        info['A_range'] = [alo, ahi]
        A = spread(alo, ahi)
        if len(set(A)) < N:
            A = None
            info['A_fallback'] = 'lt8_unique'
    else:
        info['A_fallback'] = 'no_ventricle_voxels'
    if A is None:
        A = list(U)
    info['A_idx'] = A
    if len(set(U)) < N:
        info['exclude'] = 'U_lt8_unique'
        return info
    lo_v, hi_v = D.intensity_window(a, b)
    info['window_p1_p99'] = [lo_v, hi_v]
    os.makedirs(out_png, exist_ok=True)
    pngs = {}
    for k in sorted(set(U) | set(A)):
        p = os.path.join(out_png, f'{m["study_uid"]}_s{k:03d}.png')
        if not os.path.exists(p):
            D.render_slice(a, k, lo_v, hi_v, info['canon_zooms']).save(p)
        pngs[str(k)] = dict(path=p, sha256=sha(p))
    info['pngs'] = pngs
    # QC 확인용(모델 입력 아님): 측뇌실 outline overlay montage
    ov = []
    for k in A:
        base = np.array(D.render_slice(a, k, lo_v, hi_v, info['canon_zooms']))
        mk = D.render_slice(np.where(np.arange(a.shape[2])[None, None, :] == k, vent.astype(np.float32), 0), k, 0, 1, info['canon_zooms'])
        mk = np.array(mk)[:, :, 0] > 127
        base[mk, 0] = 255
        ov.append(Image.fromarray(base).resize((224, 224)))
    M = Image.new('RGB', (224 * 4, 224 * 2))
    for i, x in enumerate(ov):
        M.paste(x, ((i % 4) * 224, (i // 4) * 224))
    M.save(os.path.join(RES, 'qc', f'overlayA_{m["study_uid"]}.png'))
    info['exclude'] = None
    return info


def main(role):
    L = json.load(open(RES + 'data/selection_lock.json'))
    prov = json.load(open(RES + f'seg/prov_{role}.json'))
    os.makedirs(RES + 'qc', exist_ok=True)
    out = {}
    for m in L['manifest']:
        if m['role'] == role:
            out[m['study_uid']] = build(m, prov[m['study_uid']], os.path.join('/home/test/.local/share/medgemma/mr_rate/png125', m['study_uid']))
            i = out[m['study_uid']]
            print(m['study_uid'], m['label'], i.get('exclude'), 'S=%.4f' % (i.get('S') or -1), 'A_fb', i.get('A_fallback'), 'U', i.get('U_idx'), 'A', i.get('A_idx'))
    p = RES + f'seg/build_{role}.json'
    assert not os.path.exists(p)
    json.dump(out, open(p, 'w'), indent=1)


if __name__ == '__main__':
    main(sys.argv[1])
