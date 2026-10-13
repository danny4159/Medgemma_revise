"""iter_134: 신규 RadGenome–BraTS train FLAIR 사례의 연결 감사, P/N1/N2 slice 선택·렌더링, 10조건 요청 구성.
P는 GT(whole tumor mask) 기반 oracle 관측, N1/N2는 annotation 0인 뇌 slice다. 임상 정상 slice가 아니다."""
import hashlib, json, re, sys
import numpy as np
import nibabel as nib
from PIL import Image
from i134_common import *
from i134_spec import *
from mr123_data import normalization_window, render_slice

SIDE = RENDER['side']
N_TECH, N_MAIN = 4, 32
# v2: v1은 복수형(lesions)·'abnormal signal foci' 등을 놓친 구현 오류(모델 출력 이전 발견, 폐기본은 superseded_build_v1에 보존)
REPORT_OK = re.compile(r'\b(lesions?|tumou?rs?|mass(es)?|abnormal signal|abnormal foci|foci|focus|signal (irregularit\w+|intensit\w+)|hyperintense|mixed (high|signal))', re.I)
REPORT_BAD = re.compile(r'\b(no|without|absence of) (visible |obvious |definite |abnormal )*(lesions?|tumou?rs?|abnormal (signal|foci|focus)|foci)', re.I)


def paths(pid):
    d = BRATS / BASE / pid
    return d / (pid + '-t2f.nii.gz'), d / (pid + '-seg.nii.gz')


def load_pair(pid):
    ip, sp = paths(pid); im = nib.load(ip); sg = nib.load(sp)
    info = dict(orig_axcodes=''.join(nib.aff2axcodes(im.affine)), shape=list(im.shape), zooms=[float(z) for z in im.header.get_zooms()[:3]],
                seg_shape=list(sg.shape), affine_match=bool(np.allclose(im.affine, sg.affine, atol=1e-3)))
    if len(im.shape) != 3 or im.shape != sg.shape or not info['affine_match']:
        return None, None, info
    imc = nib.as_closest_canonical(im); sgc = nib.as_closest_canonical(sg)
    a = np.asarray(imc.dataobj).astype(np.float32); s = np.rint(np.asarray(sgc.dataobj)).astype(np.int16)
    info['canon_axcodes'] = ''.join(nib.aff2axcodes(imc.affine)); info['canon_zooms'] = [float(z) for z in imc.header.get_zooms()[:3]]
    info['seg_labels'] = sorted(int(x) for x in np.unique(s))
    info['finite'] = bool(np.isfinite(a).all())
    return a, s > 0, info


def choose(a, m, zooms):
    """P/N1/N2 z 선택 (결과를 보기 전에 고정된 규칙). 제외 사유 또는 선택 dict 반환."""
    area = m.sum(axis=(0, 1)).astype(np.int64)
    if area.max() == 0: return None, 'no_tumor_mask'
    zP = int(np.argmax(area))   # 동률은 첫(가장 낮은) z
    brain = (a != 0).sum(axis=(0, 1)).astype(np.int64)
    ok = [z for z in range(a.shape[2]) if area[z] == 0 and brain[z] >= RENDER['N_min_brain_area_frac'] * brain.max()]
    ok.sort(key=lambda z: (abs(z - zP) * zooms[2], z))
    if len(ok) < 2: return None, 'fewer_than_2_eligible_N'
    sel = dict(P=zP, N1=ok[0], N2=ok[1])
    zs = np.where(area > 0)[0]
    return dict(z=sel, tumor_area={k: int(area[v]) for k, v in sel.items()}, brain_area={k: int(brain[v]) for k, v in sel.items()},
                brain_max=int(brain.max()), n_eligible_N=len(ok), tumor_z_range=[int(zs.min()), int(zs.max())],
                dist_to_tumor_range_slices={k: int(max(0, zs.min() - v, v - zs.max())) for k, v in sel.items()},
                dist_to_P_mm={k: float(abs(v - zP) * zooms[2]) for k, v in sel.items()}), None


def inspect(pid, mf):
    """연결·적격성 감사 (mask/위치 정보만, 모델 출력 없음). 반환 (row, selection|None, a, m, info)."""
    row = dict(pid=pid, report=mf[pid + '-t2f'])
    ip, sp = paths(pid)
    if not ip.exists() or not sp.exists(): row['exclude'] = 'files_missing'; return row, None, None, None, None
    a, m, info = load_pair(pid); row.update(info)
    if a is None: row['exclude'] = 'grid_mismatch'; return row, None, None, None, None
    if info['canon_axcodes'] != 'RAS' or not info['finite'] or not set(info['seg_labels']) <= {0, 1, 2, 3}:
        row['exclude'] = 'orientation_finite_or_label'; return row, None, None, None, None
    if not REPORT_OK.search(row['report']) or REPORT_BAD.search(row['report']):
        row['exclude'] = 'report_lesion_not_explicit'; return row, None, None, None, None
    sel, why = choose(a, m, info['canon_zooms'])
    if sel is None: row['exclude'] = why; return row, None, None, None, None
    row['exclude'] = None; row['selection'] = sel
    return row, sel, a, m, info


def build_images(pid, a, m, info, sel, outdir):
    lo, hi = normalization_window(a, None, 'volume_minmax'); z = info['canon_zooms']; out = {}
    for role in ('P', 'N1', 'N2'):
        k = sel['z'][role]; p = outdir / (pid + '_' + role + '_z%03d.png' % k)
        if p.exists(): raise FileExistsError(p)
        p.parent.mkdir(parents=True, exist_ok=True); render_slice(a, k, lo, hi, z).save(p)
        out[role] = dict(path=str(p), sha256=sha(p), z=k)
    return dict(window=[lo, hi], images=out)


def checks(pid, case, a, m, info):
    """저장 PNG를 독립 재렌더링과 대조하고, mask 렌더가 P에서만 양성인지·intensity 대비를 기록."""
    probs = []; z = info['canon_zooms']; lo, hi = case['window']; stats = {}
    for role, im in case['images'].items():
        k = im['z']; ref = np.asarray(render_slice(a, k, lo, hi, z)); got = np.asarray(Image.open(im['path']).convert('RGB'))
        if ref.shape != got.shape or not (ref == got).all(): probs.append('%s %s: PNG differs from independent render' % (pid, role))
        mimg = np.asarray(render_slice(m.astype(np.float32), k, 0.0, 1.0, z).convert('L')) > 127
        stats[role] = dict(mask_px_rendered=int(mimg.sum()), nonblank_px=int((got.max(-1) > 0).sum()))
        if role == 'P' and not mimg.any(): probs.append('%s: P mask not visible in render' % pid)
        if role != 'P' and mimg.any(): probs.append('%s %s: tumor mask present on N' % (pid, role))
        if m[:, :, k].any() != (role == 'P'): probs.append('%s %s: mask state mismatch' % (pid, role))
    kP = case['images']['P']['z']; s = a[:, :, kP]; inside = s[m[:, :, kP]]; outside = s[(~m[:, :, kP]) & (s != 0)]
    stats['P_contrast'] = dict(mean_in=float(inside.mean()), mean_out_brain=float(outside.mean()) if outside.size else None,
                               sd_out_brain=float(outside.std()) if outside.size else None)
    return probs, stats


def make_requests(cases, pids):
    reqs = []
    for pid in pids:
        c = cases[pid]['images']
        for cond, roles in CONDS.items():
            prompt = QUESTION + (NOIMG if not roles else '')
            assert not any(s in prompt for s in FORBIDDEN_IN_PROMPT)
            r = dict(id=pid + '__' + cond, kind='single', patient=pid, cond=cond, roles=roles, prompt=prompt,
                     images=[dict(path=c[ro]['path'], sha256=c[ro]['sha256']) for ro in roles])
            r['request_digest'] = digest(r); reqs.append(r)
    reqs.sort(key=lambda r: hashlib.sha256(('%d|%s' % (SEED, r['id'])).encode()).hexdigest())   # seed로 환자·조건 순서 균형화
    return reqs


def main():
    od = read(DATA / 'order.json'); mf = read(OLD / 'radgenome/BraTS_GLI/modal_wise_finding.json'); order = od['order']
    audit = []; picked = []; cache = {}
    for pid in order:
        if len(picked) >= N_TECH + N_MAIN: break
        row, sel, a, m, info = inspect(pid, mf); audit.append(row)
        if sel is not None: picked.append(pid); cache[pid] = (a, m, info, sel)
    assert len(picked) == N_TECH + N_MAIN, len(picked)
    tech, main_ = picked[:N_TECH], picked[N_TECH:]
    save(DATA / 'selection_v2.json', dict(created_at=now(), order_sha256=sha(DATA / 'order.json'), technical=tech, main=main_, examined=[a_['pid'] for a_ in audit],
                                       excluded={a_['pid']: a_['exclude'] for a_ in audit if a_['exclude']}))
    cases = {}; problems = []
    for pid in picked:
        a, m, info, sel = cache[pid]
        c = build_images(pid, a, m, info, sel, RES / 'png_v2'); c.update(selection=sel, info=info)
        pr, st = checks(pid, c, a, m, info); c['stats'] = st; problems += pr; cases[pid] = c
        ip, sp = paths(pid); c['t2f_sha256'] = sha(ip); c['seg_sha256'] = sha(sp); c['report_key'] = pid + '-t2f'
    allsha = [im['sha256'] for c in cases.values() for im in c['images'].values()]
    # 환자 중복: 이전 MRI 실험 manifest의 BraTS ID와 교집합 (같은 환자 ID로 연결 가능한 범위)
    lt = read(OLD / 'label_table.json'); prev_num = set(lt['val_patients']) | set(k.split('-')[2] for k in lt['val'])
    overlap = sorted(p for p in picked if p.split('-')[2] in prev_num)
    man = dict(created_at=now(), mirror=dict(repo=REPO, revision=REVISION, note='미러(비공식)·공식 BraTS data use 인증 아님. radgenome mapping 403은 반복하지 않음. 연구 내부 탐색 한정, 재배포 없음.'),
               n_cases=len(cases), cases=cases, audit=audit, problems=problems, prior_overlap_pids=overlap,
               n_images=len(allsha), n_unique_image_hashes=len(set(allsha)),
               prior_exposure_note='MedGemma/RadGenome 사전학습 노출 미확인. MSD Task01(BraTS 2016/17 파생)과의 환자 연결은 확인 불가(미확인).')
    save(DATA / 'data_manifest_v2.json', man)
    save(RES / 'requests/technical_v2.json', make_requests(cases, tech)); save(RES / 'requests/main_v2.json', make_requests(cases, main_))
    print('picked', len(picked), 'examined', len(audit), 'excluded', {a_['pid']: a_['exclude'] for a_ in audit if a_['exclude']}, 'problems', len(problems), 'overlap', overlap)
    for p in problems[:20]: print(p)
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
