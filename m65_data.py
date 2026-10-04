"""iter_065 질문(W/E)×sequence(F/T/J) 요청 자료. 기존 MSD D6/E48(cases.json)·구간(slabs)을 유지한다.

고정 규칙(출력 전 확정)
 - 구간별 z 위치: z0 + msd56_data.equi(n, 8) (GT 미사용). F=FLAIR(채널0, 기존 case vmin/vmax 렌더), T=T1gd(채널2, volume 전체 min-max, 동일 RGB/표시 방향).
 - 정답: W=구간 내 mask∈{1,2,3} voxel 존재, E=mask==3 존재(dataset.json: 3=enhancing tumour). coverage=같은 8개 z에서 해당 label voxel 존재(평가 변수; 입력 선택 불사용).
 - J=동일 z의 F/T를 z별 교차(F_z1,T_z1,F_z2,T_z2,...) 16장.
 - E12=E48을 SHA256('iter065:'+case)로 정렬한 앞 12 case, E36=나머지.
서브명령: build --split D|E12|E36
"""
import hashlib, json, os, sys
import numpy as np
import msd56_data as MD

ROOT = 'results/iter_065'
SRC = 'results/iter_056/data'
CH_F, CH_T = 0, 2
Q = {'W': 'tumor or tumor-associated edema', 'E': 'contrast-enhancing tumor'}
CONDS = ['F', 'T', 'J']
DESC = {
    'F': 'All 8 images are FLAIR slices, ordered from inferior to superior.',
    'T': 'All 8 images are post-contrast T1-weighted slices, ordered from inferior to superior.',
    'J': 'The 16 images are 8 pairs ordered from inferior to superior; in each pair the first image is a FLAIR slice and the second is the post-contrast T1-weighted slice at the same axial position.',
}
PROMPT = ('These are ordered axial MRI slices sampled from one fixed brain interval. {desc} '
          'Is {target} present anywhere in this interval? Answer only PRESENT or ABSENT.')


def prompt(cond, q):
    return PROMPT.format(desc=DESC[cond], target=Q[q])


def sha_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for ch in iter(lambda: f.read(1 << 22), b''):
            h.update(ch)
    return h.hexdigest()


def sha_b(b):
    return hashlib.sha256(b).hexdigest()


def e_order(cases_e):
    return sorted(cases_e, key=lambda c: sha_b(('iter065:' + c).encode()))


def split_cases(split):
    ch = json.load(open(f'{SRC}/cases.json'))['chosen']
    d = [c for c in ch if c['split'] == 'D']
    e = {c['case']: c for c in ch if c['split'] == 'E'}
    order = e_order(list(e))
    pick = {'D': [c['case'] for c in d], 'E12': order[:12], 'E36': order[12:]}[split]
    allc = {c['case']: c for c in ch}
    return [allc[c] for c in pick]


def load_t1gd(cid):
    """T1gd (canonical RAS, MD.load_case와 동일 변환) + 전체 min/max."""
    import nibabel as nib
    ip, _ = MD.case_paths(cid)
    can = nib.as_closest_canonical(nib.load(ip))
    assert "".join(nib.aff2axcodes(can.affine)) == 'RAS'
    t = np.asarray(can.dataobj[..., CH_T], dtype=np.float32)
    assert np.isfinite(t).all()
    return t


def png_name(cid, seq, z):
    return f'{ROOT}/png/{sha_b(f"{cid}|{seq}|{z}".encode())[:16]}.png'


def slab_labels(mask, a, b, zs):
    sl = mask[:, :, a:b + 1]
    sz = mask[:, :, zs]
    return {'W': bool((sl > 0).any()), 'E': bool((sl == 3).any()),
            'cov_W': bool((sz > 0).any()), 'cov_E': bool((sz == 3).any()),
            'vox_W': int((sl > 0).sum()), 'vox_E': int((sl == 3).sum()),
            'cov_vox_W': int((sz > 0).sum()), 'cov_vox_E': int((sz == 3).sum())}


def build_requests(items):
    """items: [{case, slab, F:[png...], T:[png...]}] -> (requests, labels_stub). 순수 함수."""
    reqs = []
    for it in items:
        ims = {'F': it['F'], 'T': it['T'], 'J': [p for pair in zip(it['F'], it['T']) for p in pair]}
        for q in ('W', 'E'):
            for c in CONDS:
                rid = f"{it['case']}__s{it['slab']}__{q}__{c}"
                reqs.append({'rid': rid, 'case': it['case'], 'slab': it['slab'], 'q': q, 'cond': c, 'images': ims[c],
                             'prompt': prompt(c, q)})
    return reqs


def cmd_build(split):
    from PIL import Image
    cs = split_cases(split)
    co = json.load(open(f'{SRC}/case_order.json'))
    os.makedirs(f'{ROOT}/png', exist_ok=True)
    os.makedirs(f'{ROOT}/data', exist_ok=True)
    items, labels, tm = [], {}, []
    for c in cs:
        cid = c['case']
        ip, lp = MD.case_paths(cid)
        assert MD.sha256(open(ip, 'rb').read()) == c['img_sha256'] == co['file_hashes'][f'images/{cid}']['sha256'], cid
        assert MD.sha256(open(lp, 'rb').read()) == c['lbl_sha256'] == co['file_hashes'][f'labels/{cid}']['sha256'], cid
        flair, mask, info = MD.load_case(cid)
        assert info['shape'] == c['info']['shape'] and abs(float(flair.min()) - c['vmin']) < 1e-4 and abs(float(flair.max()) - c['vmax']) < 1e-4
        t1 = load_t1gd(cid)
        assert t1.shape == flair.shape
        tmin, tmax = float(t1.min()), float(t1.max())
        assert tmax > tmin
        assert set(np.unique(mask).tolist()) <= {0, 1, 2, 3}
        for si, (a, b) in enumerate(c['slabs']):
            zs = [a + i for i in MD.equi(b - a + 1, 8)]
            f_png, t_png = [], []
            for z in zs:
                for seq, vol, lo, hi, lst in (('F', flair, c['vmin'], c['vmax'], f_png), ('T', t1, tmin, tmax, t_png)):
                    p = png_name(cid, seq, z)
                    Image.fromarray(MD.render(vol, z, lo, hi)).save(p + '.tmp.png')
                    os.replace(p + '.tmp.png', p)
                    lst.append(p)
            lab = slab_labels(mask, a, b, zs)
            items.append({'case': cid, 'slab': si, 'F': f_png, 'T': t_png})
            tm.append({'case': cid, 'slab': si, 'z0': a, 'z1': b, 'zs': zs, 'img_sha256': c['img_sha256'], 'lbl_sha256': c['lbl_sha256'],
                       't1gd_min': tmin, 't1gd_max': tmax, 'flair_min': c['vmin'], 'flair_max': c['vmax'],
                       'F_png': f_png, 'T_png': t_png, 'F_png_sha256': [sha_file(p) for p in f_png], 'T_png_sha256': [sha_file(p) for p in t_png], **lab})
    reqs = build_requests(items)
    by = {(t['case'], t['slab']): t for t in tm}
    for r in reqs:
        t = by[(r['case'], r['slab'])]
        labels[r['rid']] = {'answer': 'PRESENT' if t[r['q']] else 'ABSENT', 'case': r['case'], 'slab': r['slab'], 'q': r['q'], 'cond': r['cond'],
                            'coverage': bool(t['cov_' + r['q']])}
    with open(f'{ROOT}/data/requests_{split}.jsonl', 'w') as f:
        for r in reqs:
            f.write(json.dumps(r) + '\n')
    json.dump(labels, open(f'{ROOT}/data/labels_{split}.json', 'w'), indent=1)
    json.dump({'slabs': tm, 'prompts': {f'{q}_{c}': prompt(c, q) for q in Q for c in CONDS}, 'e_order_rule': "sha256('iter065:'+case)",
               'channels': {'F': CH_F, 'T': CH_T}}, open(f'{ROOT}/data/target_manifest_{split}.json', 'w'), indent=1)
    print(split, 'cases', len(cs), 'slabs', len(tm), 'requests', len(reqs),
          'W+', sum(t['W'] for t in tm), 'E+', sum(t['E'] for t in tm), 'covW0&W+', sum(t['W'] and not t['cov_W'] for t in tm), 'covE0&E+', sum(t['E'] and not t['cov_E'] for t in tm))


if __name__ == '__main__':
    cmd_build(sys.argv[sys.argv.index('--split') + 1]) if sys.argv[1] == 'build' else sys.exit('usage: build --split D|E12|E36')
