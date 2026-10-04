"""iter_071 SPIDER T2 sagittal anatomy-grounding 자료: 분할 잠금, mask-free 중앙 slice 선택·렌더, instance bbox GT, 입력 검증.

- 영상/mask 읽기·canonical 축·SimpleITK 물리좌표 대조는 sp67_data.load_pair(iter_067, 선별 반입)를 사용한다. Modic/IVD crop/sequence 비교 함수는 호출하지 않는다.
- 선택 slice: canonical 좌우축 길이 n에서 j=floor((n-1)/2)와 j-1, j, j+1. mask·GT를 보지 않는다 (render/select 함수는 mask 인자가 없다).
- 렌더: volume 유한값 min/max uint8, spacing 보정(더 촘촘한 간격 기준 PIL bilinear), 추가 crop 없음. PNG는 square padding 전(L mode)이며
  모델 입력은 rsna_diag.generate.load_image가 값 보존 RGB + 중앙 square padding으로 만든다 (RSNA source adapter와 같은 경로).
- GT: slice의 label instance(1..99=vertebra, 201+=disc, 100=canal 제외)별 mask bbox, 분리 성분은 union bbox. float 정규화 yxyx(0-1000, padding canvas 기준).
  학습 정수 target은 lower=floor/upper=ceil. F139 환자는 어떤 함수에서도 열지 않는다(assert).
"""
import csv, hashlib, io, json, math, os, sys

import numpy as np
from PIL import Image

import sp67_data as S
from rsna_diag import geometry as G
from rsna_diag import mi19_render as R

OUT = 'results/iter_071'
DATA = f'{OUT}/data'
SPLIT_SRC = 'results/iter_021/data/split.json'
SALT = 'iter071-split-v1'
SEQ = 't2'
OFFSETS = (-1, 0, 1)
OFF_NAME = {-1: 'm1', 0: 'c', 1: 'p1'}
CATS = ('vertebra', 'disc')
LABEL_STR = {'vertebra': 'vertebra', 'disc': 'intervertebral disc'}
PROMPTS = {
    'vertebra': ('Localize all vertebrae visible in this sagittal spine MRI slice. Return only a JSON list. '
                 'Each entry must contain "box_2d": [y_min, x_min, y_max, x_max] and a nonempty "label" string. '
                 'Each box must enclose one whole vertebra including its posterior arch. '
                 'Coordinates must be between 0 and 1000 relative to the entire square-padded image, with y before x. '
                 'Return [] if no such vertebra is visible.'),
    'disc': ('Localize all intervertebral discs visible in this sagittal spine MRI slice. Return only a JSON list. '
             'Each entry must contain "box_2d": [y_min, x_min, y_max, x_max] and a nonempty "label" string. '
             'Coordinates must be between 0 and 1000 relative to the entire square-padded image, with y before x. '
             'Return [] if no such disc is visible.'),
}
S.TMP = f'{OUT}/tmp'  # iter_067 경로에 쓰지 않는다
FORBIDDEN = None  # F139 id 집합 (load_split에서 채움)


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def prompt_sha(cat):
    return sha_bytes(PROMPTS[cat].encode())


def split_hash(pid):
    return hashlib.sha256(f'{SALT}|{pid}'.encode()).hexdigest()


def make_split():
    """기존 D8/E48(F139 제외)에서 T8/train16/V8/E24를 hash 순으로 고정한다. 기관 metadata는 overview.csv에 없다(제조사/모델만) -> 층화 미실행."""
    src = json.load(open(SPLIT_SRC))
    D, E, F = list(src['D']), list(src['E']), list(src['F'])
    assert not (set(D) | set(E)) & set(F)
    order = sorted(E, key=lambda p: (split_hash(p), p))
    sp = {'T8': sorted(D, key=int), 'extra_train16': sorted(order[:16], key=int), 'V8': sorted(order[16:24], key=int), 'E24': sorted(order[24:], key=int)}
    sp['T24'] = sorted(sp['T8'] + sp['extra_train16'], key=int)
    v_order = [p for p in order[16:24]]  # hash 순
    sp['V4'] = sorted(v_order[:4], key=int)
    allp = [sp['T8'], sp['extra_train16'], sp['V8'], sp['E24']]
    flat = [p for g in allp for p in g]
    assert len(flat) == 56 == len(set(flat)) and not set(flat) & set(F)
    sp.update({'salt': SALT, 'institution_stratification': 'not_executed: overview.csv has no institution field (only Manufacturer/ManufacturerModelName/DeviceSerialNumber)',
               'F139_ids_blocked': len(F), 'prior_exposure': 'D8 and E48 were used in iter_019-021 (reference-instance tasks) and parts in iter_067; E24 is a fixed development evaluation, '
               'not a new independent confirmation.'})
    return sp, set(F)


def load_split():
    global FORBIDDEN
    p = f'{DATA}/split_lock.json'
    if os.path.exists(p):
        sp = json.load(open(p))
        src = json.load(open(SPLIT_SRC))
        FORBIDDEN = set(src['F'])
        want, _ = make_split()
        for k in ('T8', 'extra_train16', 'V8', 'E24', 'T24', 'V4'):
            assert sp[k] == want[k], f'split lock mismatch {k}'
        return sp
    sp, F = make_split()
    FORBIDDEN = F
    os.makedirs(DATA, exist_ok=True)
    json.dump(sp, open(p, 'w'), indent=1)
    return sp


def guard(pid):
    assert FORBIDDEN is not None, 'call load_split() first'
    if pid in FORBIDDEN:
        raise PermissionError(f'F139 patient {pid} is blocked')


def select_slices(n_lr):
    """mask-free: canonical 좌우축 slice 수만 사용."""
    j = (n_lr - 1) // 2
    return [j + o for o in OFFSETS]


def render_slice(V, spacing, idx):
    """V[lr,si,pa], 선택 slice idx -> (L-mode uint8 2D(위=superior), meta). volume 전체 finite min/max window. mask 인자 없음."""
    fin = V[np.isfinite(V)]
    if fin.size != V.size:
        raise ValueError('non-finite voxel in volume')
    lo, hi = float(V.min()), float(V.max())
    if hi <= lo:
        raise ValueError('flat volume')
    sl = V[idx][::-1]  # row 0 = superior
    u8 = R.to_uint8(sl, lo, hi)
    nrow, ncol = u8.shape
    srow, scol = R.resize_scale(spacing[1], spacing[2])
    nh, nw = max(1, round(nrow * srow)), max(1, round(ncol * scol))
    im = Image.fromarray(u8, mode='L').resize((nw, nh), resample=Image.BILINEAR)
    arr = np.asarray(im)
    return arr, {'window': [lo, hi], 'native_hw': [nrow, ncol], 'resized_hw': [nh, nw], 'scale_row_col': [nh / nrow, nw / ncol],
                 'pad_top_left_side': list(G.pad_offsets(nh, nw))}


def gt_instances(Lslice, meta):
    """Lslice[si,pa] canonical label slice -> {cat: [ {label, bbox_native_rc, xyxy_px(render), yxyx_norm} ]}. 분리 성분은 같은 label의 union bbox."""
    M = Lslice[::-1]
    sr, sc = meta['scale_row_col']
    nh, nw = meta['resized_hw']
    top, left, side = meta['pad_top_left_side']
    out = {c: [] for c in CATS}
    for lab in [int(x) for x in np.unique(M) if x != 0]:
        if lab == 100:
            continue
        cat = 'vertebra' if 1 <= lab <= 99 else ('disc' if lab >= 200 else None)
        if cat is None:
            raise ValueError(f'unexpected label {lab}')
        rr, cc = np.nonzero(M == lab)
        r0, c0, r1, c1 = int(rr.min()), int(cc.min()), int(rr.max()) + 1, int(cc.max()) + 1
        xyxy = [c0 * sc, r0 * sr, c1 * sc, r1 * sr]
        out[cat].append({'label': lab, 'bbox_native_rc': [r0, c0, r1, c1], 'n_vox': int(len(rr)), 'xyxy_px': xyxy,
                         'yxyx_norm': G.canvas_to_norm(xyxy, top, left, side)})
    for c in CATS:
        out[c].sort(key=lambda b: ((b['yxyx_norm'][0] + b['yxyx_norm'][2]) / 2, (b['yxyx_norm'][1] + b['yxyx_norm'][3]) / 2, b['label']))
    return out


def target_boxes(boxes_norm):
    """float GT -> 정수 학습 target: lower=floor, upper=ceil, [0,1000] 안으로 고정. 순서는 입력 순서(상->하)를 유지."""
    res = []
    for y0, x0, y1, x1 in boxes_norm:
        b = [int(math.floor(y0)), int(math.floor(x0)), int(math.ceil(y1)), int(math.ceil(x1))]
        b = [max(0, min(1000, v)) for v in b]
        if not (b[0] < b[2] and b[1] < b[3]):
            raise ValueError(f'invalid integer box {boxes_norm}')
        res.append(b)
    return res


def target_text(cat, boxes_norm):
    return json.dumps([{'box_2d': b, 'label': LABEL_STR[cat]} for b in target_boxes(boxes_norm)])


def item_id(pid, off, cat):
    return f'{pid}_{OFF_NAME[off]}_{cat}'


def build_patient(pid, outdir=None):
    guard(pid)
    outdir = outdir or f'{DATA}/images'
    d = S.load_pair(pid, SEQ)
    V, L, spc = d['V'], d['L'], d['spacing']
    n = V.shape[0]
    rows, imgs = [], {}
    for off, idx in zip(OFFSETS, select_slices(n)):
        arr, meta = render_slice(V, spc, idx)
        path = f'{outdir}/{pid}_{OFF_NAME[off]}.png'
        buf = io.BytesIO()
        Image.fromarray(arr, mode='L').save(buf, format='PNG')
        os.makedirs(outdir, exist_ok=True)
        with open(path, 'wb') as f:
            f.write(buf.getvalue())
        inst = gt_instances(L[idx], meta)
        rgb, aff, pxsha = None, None, None
        from rsna_diag import generate as GEN
        _, aff, pxsha = GEN.load_image(path)
        imgs[off] = {'path': path, 'file_sha256': sha_bytes(buf.getvalue()), 'pixel_sha256_padded': pxsha, 'slice_index': int(idx), **meta}
        assert list(aff) == meta['pad_top_left_side']
        for cat in CATS:
            rows.append({'id': item_id(pid, off, cat), 'patient': pid, 'offset': off, 'category': cat, 'image': path, 'file_sha256': imgs[off]['file_sha256'],
                         'gt': inst[cat]})
    info = {'patient': pid, 'n_lr': int(n), 'selected': select_slices(n), 'spacing_canon': [float(x) for x in spc], 'direction': d['direction'], 'origin': d['origin'],
            'header_orientation': d['header'], 'src_sha': d['src_sha'], 'size_xyz': d['size_xyz'], 'tilt_deg': d['tilt_deg'],
            'physical_check_max_rel_err': d['physical_check_max_rel_err'], 'images': {OFF_NAME[k]: v for k, v in imgs.items()}}
    return rows, info


def build_all(pids):
    all_rows, infos = [], {}
    for pid in pids:
        rows, info = build_patient(pid)
        all_rows += rows
        infos[pid] = info
    return all_rows, infos
