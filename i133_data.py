"""iter_133: 기존 RadGenome-BraTS FLAIR 15사례의 연결 감사, 동일 slice U/L/M 렌더링, 요청 구성.
U=무표시 FLAIR, L=동일 FLAIR+seg>0 외접 직사각형, M=회색 배경+동일 직사각형. 선택 slice는 GT로 정한 oracle 관측이다."""
import json, sys
from fractions import Fraction
import numpy as np
import nibabel as nib
from PIL import Image, ImageDraw
from i133_common import RES, SRC, BRATS, sha, digest, read, save, now
from i133_spec import RENDER, PROMPTS, FORBIDDEN_IN_PROMPT
from mr123_data import normalization_window, render_slice

SIDE = RENDER['side']; N = RENDER['n_slices']
TECH = ['BraTS-GLI-00012-000', 'BraTS-GLI-00456-000']


def eligible():
    t = read(SRC / 'label_table.json'); assert t['revision'] == '0348ba42fad134da57b50e736ba858a8e73eb086'
    out = []
    for pid, v in t['val'].items():
        if v['label'] in ('HIGH', 'MIXED_HIGH_LOW'):
            assert v['auto'] == v['label'] and v['key'] == pid + '-t2f'
            out.append(dict(pid=pid, report_label=v['label'], evidence=v['evidence'], report=v['report']))
    assert len(out) == 15 and sum(o['report_label'] == 'MIXED_HIGH_LOW' for o in out) == 11
    return out


def pick_indices(lo, hi, n=N):
    """등간격 위치, 반올림 동률은 낮은 index (정확한 분수 계산)."""
    idx = []
    for i in range(n):
        x = Fraction(lo) + Fraction(hi - lo) * i / (n - 1)
        fl = x.numerator // x.denominator
        idx.append(fl if (x - fl) <= Fraction(1, 2) else fl + 1)
    return idx


def load_pair(pid):
    d = BRATS / pid
    im = nib.load(d / f'{pid}-t2f.nii.gz'); sg = nib.load(d / f'{pid}-seg.nii.gz')
    info = dict(orig_axcodes=''.join(nib.aff2axcodes(im.affine)), shape=list(im.shape), zooms=[float(z) for z in im.header.get_zooms()[:3]],
                seg_shape=list(sg.shape), affine_match=bool(np.allclose(im.affine, sg.affine, atol=1e-3)))
    assert im.shape == sg.shape and info['affine_match'] and len(im.shape) == 3
    imc = nib.as_closest_canonical(im); sgc = nib.as_closest_canonical(sg)
    a = np.asarray(imc.dataobj).astype(np.float32); s = np.rint(np.asarray(sgc.dataobj)).astype(np.int16)
    info['canon_axcodes'] = ''.join(nib.aff2axcodes(imc.affine)); assert info['canon_axcodes'] == 'RAS'
    info['canon_zooms'] = [float(z) for z in imc.header.get_zooms()[:3]]
    info['seg_labels'] = sorted(int(x) for x in np.unique(s)); assert set(info['seg_labels']) <= {0, 1, 2, 3}
    assert np.isfinite(a).all()
    return a, s > 0, info


def geometry(shape2, zooms):
    nX, nY = shape2; h, w = nY, nX
    hh, ww = h * zooms[1], w * zooms[0]; sc = SIDE / max(hh, ww)
    nh, nw = max(1, int(round(hh * sc))), max(1, int(round(ww * sc)))
    return dict(h=h, w=w, nh=nh, nw=nw, ox=(SIDE - nw) // 2, oy=(SIDE - nh) // 2)


def rect_canvas(m2, zooms):
    """m2: (nX,nY) bool. 반환 (left,top,right,bottom) canvas 정수 좌표(오른쪽·아래 exclusive) 또는 None."""
    if not m2.any():
        return None
    xs = np.where(m2.any(axis=1))[0]; ys = np.where(m2.any(axis=0))[0]
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    g = geometry(m2.shape, zooms); nX, nY = m2.shape
    c0, c1 = nX - 1 - x1, nX - 1 - x0; r0, r1 = nY - 1 - y1, nY - 1 - y0
    l = g['ox'] + c0 * g['nw'] / g['w']; r = g['ox'] + (c1 + 1) * g['nw'] / g['w']
    t = g['oy'] + r0 * g['nh'] / g['h']; b = g['oy'] + (r1 + 1) * g['nh'] / g['h']
    return int(round(l)), int(round(t)), int(round(r)), int(round(b))


def draw_rect(img, rc):
    d = ImageDraw.Draw(img); l, t, r, b = rc
    d.rectangle([l, t, r - 1, b - 1], outline=tuple(RENDER['rect_rgb']), width=RENDER['rect_px'])
    return img


def build_case(pid, outdir):
    a, m, info = load_pair(pid); z = info['canon_zooms']
    zs = np.where(m.any(axis=(0, 1)))[0]; lo, hi = int(zs.min()), int(zs.max())
    idx = pick_indices(lo, hi); assert len(set(idx)) == N, (pid, idx)
    vlo, vhi = normalization_window(a, None, 'volume_minmax')
    tot = int(m.sum()); rows = []; paths = {c: [] for c in 'ULM'}
    for k in idx:
        m2 = m[:, :, k]; rc = rect_canvas(m2, z)
        u = render_slice(a, k, vlo, vhi, z); l = u.copy()
        if rc: draw_rect(l, rc)
        mm = Image.new('RGB', (SIDE, SIDE), tuple(RENDER['gray']))
        if rc: draw_rect(mm, rc)
        for c, im in zip('ULM', (u, l, mm)):
            p = outdir / c / f'{pid}_s{k:03d}.png'; p.parent.mkdir(parents=True, exist_ok=True)
            if p.exists(): raise FileExistsError(p)
            im.save(p); paths[c].append(dict(path=str(p), sha256=sha(p)))
        rows.append(dict(index=k, mask_voxels=int(m2.sum()), mask_present=bool(m2.any()), rect_canvas=rc,
                         frac_of_total_positive=float(m2.sum()) / tot))
    return dict(pid=pid, info=info, mask_z_range=[lo, hi], window=[vlo, vhi], total_positive_voxels=tot, slices=rows,
                selected_fraction_positive=float(sum(r['mask_voxels'] for r in rows)) / tot, images=paths)


def checks(case):
    """좌표·픽셀 동일성·정보 누설 검사. 문제 목록 반환."""
    probs = []; pid = case['pid']; a, m, info = load_pair(pid); z = info['canon_zooms']; red = np.array(RENDER['rect_rgb']); gray = np.array(RENDER['gray'])
    for n, sl in enumerate(case['slices']):
        k = sl['index']; U = np.asarray(Image.open(case['images']['U'][n]['path']).convert('RGB')).astype(int)
        L = np.asarray(Image.open(case['images']['L'][n]['path']).convert('RGB')).astype(int)
        M = np.asarray(Image.open(case['images']['M'][n]['path']).convert('RGB')).astype(int)
        diff = (U != L).any(-1); isred = (L == red).all(-1)
        if not (diff <= isred).all(): probs.append(f'{pid} s{k}: L differs from U outside red outline')
        if (L == red).all(-1).sum() != (M == red).all(-1).sum(): probs.append(f'{pid} s{k}: L/M outline mismatch')
        if not (isred == (M == red).all(-1)).all(): probs.append(f'{pid} s{k}: outline pixel positions differ L vs M')
        rest = ~(M == red).all(-1)
        if not (M[rest] == gray).all(): probs.append(f'{pid} s{k}: M contains non-gray non-red pixel')
        if (U == red).all(-1).any() and not sl['mask_present']: pass
        # 직사각형 vs 독립 렌더링한 mask 위치
        rc = sl['rect_canvas']
        if sl['mask_present']:
            mimg = np.asarray(render_slice(m.astype(np.float32), k, 0.0, 1.0, z).convert('L')).astype(float) / 255
            ys, xs = np.where(mimg > 0.5)
            ind = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
            if max(abs(ind[0] - rc[0]), abs(ind[1] - rc[1]), abs(ind[2] - rc[2]), abs(ind[3] - rc[3])) > 3:
                probs.append(f'{pid} s{k}: rect {rc} vs independent mask bbox {ind}')
        else:
            if isred.any(): probs.append(f'{pid} s{k}: outline without mask')
    return probs


def make_requests(cases, pids, stage):
    reqs = []
    for pid in pids:
        c = cases[pid]
        for cond in 'ULM':
            r = dict(id=f'{pid}__{cond}', kind='single', patient=pid, cond=cond, prompt=PROMPTS[cond], groups=[c['images'][cond]])
            assert not any(s in r['prompt'] for s in FORBIDDEN_IN_PROMPT)
            r['request_digest'] = digest(r); reqs.append(r)
    return reqs


def main():
    RES.mkdir(parents=True, exist_ok=True); out = RES / 'png'
    t0 = now(); el = eligible(); man = read(SRC / 'brats_manifest.json'); mf = man['sha256']
    modal = read(SRC / 'radgenome/BraTS_GLI/modal_wise_finding.json'); problems = []; cases = {}; audit = []
    for e in el:
        pid = e['pid']; rel = f'ASNR-MICCAI-BraTS2023-GLI-Challenge-TrainingData/{pid}/{pid}'
        for suf in ('-t2f.nii.gz', '-seg.nii.gz'):
            p = BRATS / pid / (pid + suf); h = sha(p)
            if mf[rel + suf] != h: problems.append(f'sha mismatch {pid}{suf}')
        if modal[pid + '-t2f'] != e['report']: problems.append(f'report text mismatch {pid}')
        cases[pid] = build_case(pid, out)
        audit.append(dict(pid=pid, report_label=e['report_label'], t2f_sha256=mf[rel + '-t2f.nii.gz'], seg_sha256=mf[rel + '-seg.nii.gz'],
                          report_key=pid + '-t2f', **{k: cases[pid]['info'][k] for k in ('orig_axcodes', 'canon_axcodes', 'shape', 'zooms', 'seg_labels')}))
        problems += checks(cases[pid])
    allsha = [im['sha256'] for c in cases.values() for cond in 'ULM' for im in c['images'][cond]]
    manifest = dict(created_at=t0, finished_at=now(), source_manifest=str(SRC / 'brats_manifest.json'), source_manifest_sha256=sha(SRC / 'brats_manifest.json'),
                    label_table_sha256=sha(SRC / 'label_table.json'), modal_finding_sha256=sha(SRC / 'radgenome/BraTS_GLI/modal_wise_finding.json'),
                    mirror=dict(repo='MedOtter/brats2023-gli-dataset', revision=man['revision'], license='cc-by-4.0 (HF card, 비gated; 공식 BraTS 접근 인증이 아닌 mirror 이용 조건)',
                                radgenome_license='mit (README.md)', note='mirror 접근 가능성은 공식 data use 동의가 아니다. 연구 내부 탐색 한정, 재배포 없음.'),
                    render=RENDER, prompts=PROMPTS, n_cases=len(cases), cases=cases, audit=audit, n_images=len(allsha), n_unique_image_hashes=len(set(allsha)),
                    problems=problems)
    save(RES / 'data_manifest.json', manifest)
    tech = make_requests(cases, TECH, 'technical'); main_ = make_requests(cases, [e['pid'] for e in el], 'main')
    (RES / 'requests').mkdir(exist_ok=True)
    save(RES / 'requests/technical.json', tech); save(RES / 'requests/main.json', main_)
    print('cases', len(cases), 'problems', len(problems), 'tech', len(tech), 'main', len(main_))
    for p in problems[:20]: print(p)
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
