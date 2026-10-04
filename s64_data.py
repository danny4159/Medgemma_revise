"""iter_064 target-slice 대조 자료: 기존 MSD D6/E48(cases.json)에서 case별 양성 P/음성 N slice를 mask로 고정 규칙 선택하고
S/R/C 요청을 만든다. msd56_data.py(원 SHA da6e755 반입)는 load_case/render/mask_slice만 사용한다.

선택 규칙(결과 보기 전 고정)
 P: mask>0 단면적 최대 axial slice(동률 작은 z). 합>0이어야 함.
 N: mask 합=0 slice 중 FLAIR nonzero pixel 수 최대(동률 작은 z). 합=0이어야 함.
 둘 중 하나가 없으면 부적격(대체 없음).
GT(정답)는 labels_*.json에만 둔다. 요청에는 case ID/좌표/slice index를 넣지 않고 영상은 anon 파일명으로 저장한다.
서브명령: audit | build --split D|E
"""
import hashlib, json, os, sys
import numpy as np
import msd56_data as MD

ROOT = 'results/iter_064'
SRC = 'results/iter_056/data'
PROMPT = ('The images are axial FLAIR slices from the same brain MRI. Consider only image {k} in the supplied order. '
          'Is a glioma-related lesion, including peritumoral edema, visible in that image? '
          'Answer with exactly one word: PRESENT or ABSENT.')
CONDS = ['S', 'R1', 'R2', 'C1', 'C2']


def sha_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for ch in iter(lambda: f.read(1 << 22), b''):
            h.update(ch)
    return h.hexdigest()


def sha_b(b):
    return hashlib.sha256(b).hexdigest()


def select_targets(flair, mask):
    """returns (P_z, N_z, info) 또는 부적격 시 (None|z, None|z, info). 순수 함수(합성 검사용)."""
    ann = mask > 0
    areas = np.array([int(ann[:, :, k].sum()) for k in range(ann.shape[2])])
    nz = np.array([int((flair[:, :, k] != 0).sum()) for k in range(flair.shape[2])])
    P = None
    if areas.max() > 0:
        P = int(np.flatnonzero(areas == areas.max())[0])
    zero = np.flatnonzero(areas == 0)
    N = None
    if len(zero):
        zn = nz[zero]
        N = int(zero[np.flatnonzero(zn == zn.max())[0]])
        if nz[N] == 0:
            N = None
    return P, N, {'area_P': int(areas[P]) if P is not None else None, 'area_N': int(areas[N]) if N is not None else None,
                  'nz_P': int(nz[P]) if P is not None else None, 'nz_N': int(nz[N]) if N is not None else None}


def png_name(cid, kind, z):
    # 영상 파일명에 case ID를 쓰지 않는다 (processor는 경로를 보지 않지만 기록 분리).
    return f'{ROOT}/png/{sha_b(f"{cid}|{kind}|{z}".encode())[:16]}.png'


def build_requests(rows):
    """rows: [{case, split, P:{png,z}, N:{png,z}}]. 요청과 정답 생성(순수)."""
    reqs, labels = [], {}
    for r in rows:
        for tk, ok in (('P', 'N'), ('N', 'P')):
            t, o = r[tk]['png'], r[ok]['png']
            spec = {'S': ([t], 1), 'R1': ([t, t], 1), 'R2': ([t, t], 2), 'C1': ([t, o], 1), 'C2': ([o, t], 2)}
            for cond in CONDS:
                ims, k = spec[cond]
                rid = f"{r['case']}__{tk}__{cond}"
                reqs.append({'rid': rid, 'case': r['case'], 'target': tk, 'cond': cond, 'k': k, 'images': ims,
                             'prompt': PROMPT.format(k=k)})
                labels[rid] = {'answer': 'PRESENT' if tk == 'P' else 'ABSENT', 'case': r['case'], 'target': tk, 'cond': cond}
    return reqs, labels


def cmd_build(split):
    cs = [c for c in json.load(open(f'{SRC}/cases.json'))['chosen'] if c['split'] == split]
    co = json.load(open(f'{SRC}/case_order.json'))
    os.makedirs(f'{ROOT}/png', exist_ok=True)
    os.makedirs(f'{ROOT}/data', exist_ok=True)
    from PIL import Image
    rows, inelig, tm = [], [], []
    for c in cs:
        cid = c['case']
        ip, lp = MD.case_paths(cid)
        # raw hash 대조 (cases.json / case_order.json)
        assert MD.sha256(open(ip, 'rb').read()) == c['img_sha256'] == co['file_hashes'][f'images/{cid}']['sha256'], cid
        assert MD.sha256(open(lp, 'rb').read()) == c['lbl_sha256'] == co['file_hashes'][f'labels/{cid}']['sha256'], cid
        flair, mask, info = MD.load_case(cid)
        assert info['shape'] == c['info']['shape'] and abs(float(flair.min()) - c['vmin']) < 1e-4 and abs(float(flair.max()) - c['vmax']) < 1e-4
        P, N, inf = select_targets(flair, mask)
        if P is None or N is None:
            inelig.append({'case': cid, 'P': P, 'N': N, 'info': inf})
            continue
        ent = {'case': cid, 'split': split, 'img_sha256': c['img_sha256'], 'lbl_sha256': c['lbl_sha256'], **inf}
        row = {'case': cid}
        for kind, z in (('P', P), ('N', N)):
            p = png_name(cid, kind, z)
            Image.fromarray(MD.render(flair, z, c['vmin'], c['vmax'])).save(p + '.tmp.png')
            os.replace(p + '.tmp.png', p)
            row[kind] = {'png': p, 'z': z}
            ent[f'{kind}_z'] = z
            ent[f'{kind}_png'] = p
            ent[f'{kind}_png_sha256'] = sha_file(p)
            ent[f'{kind}_mask_sum'] = int(MD.mask_slice(mask, z).sum())
        assert ent['P_mask_sum'] > 0 and ent['N_mask_sum'] == 0, cid
        rows.append(row); tm.append(ent)
    reqs, labels = build_requests(rows)
    with open(f'{ROOT}/data/requests_{split}.jsonl', 'w') as f:
        for r in reqs:
            f.write(json.dumps(r) + '\n')
    json.dump(labels, open(f'{ROOT}/data/labels_{split}.json', 'w'), indent=1)
    json.dump({'targets': tm, 'ineligible': inelig, 'rule': 'P=max mask area (tie small z); N=mask sum 0 with max FLAIR nonzero (tie small z)',
               'prompt': PROMPT}, open(f'{ROOT}/data/target_manifest_{split}.json', 'w'), indent=1)
    print(split, 'eligible', len(tm), 'ineligible', len(inelig), 'requests', len(reqs))


if __name__ == '__main__':
    cmd_build(sys.argv[2]) if sys.argv[1] == 'build' else sys.exit('usage')
