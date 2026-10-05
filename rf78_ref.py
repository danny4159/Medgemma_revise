"""iter_078 참고 사례 검색·요청 구성.

- C(iter_075 선택 checkpoint, 고정)의 세 crop 평균 penultimate feature(512, L2 정규화)를 T24(supervised 70) / V8(24) / E24 held(47)에 대해 추출한다.
- 검색(top3, I)과 먼 사례(D)는 query의 grade를 받지 않는 함수 `retrieve(q_feat, bank)`로 구현한다. bank는 T24 grade만 가진다.
- 요청 파일은 query grade를 포함하지 않는다. grade는 labels_{split}.json에만 둔다.
사용: python rf78_ref.py features --gpu 0 | python rf78_ref.py build
"""
import argparse, hashlib, json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results/environments/tv071'))
import numpy as np

import sp75_c as C
import sp75_data as D

OUT = 'results/iter_078'
FEAT = f'{OUT}/features.json'
C_DIR = 'results/iter_075/C'
TOPK = 3
SPLITS = {'V8': ('V8', 'supervised'), 'E24': ('E24', 'held')}


def sha_file(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def sha_str(s):
    return hashlib.sha256(s.encode()).hexdigest()


def sel_rows(split, pos):
    rows = [r for r in D.load_manifest()['rows'] if r['split'] == split and r['position_set'] == pos and not r['excluded']]
    return sorted(rows, key=lambda r: (int(r['patient']), r['ordinal']))


def all_targets():
    """feature 추출 대상: T24 supervised, V8 supervised, E24 held (T24/V8 미사용 위치와 E24 supervised는 열지 않는다)."""
    out = {'T24': sel_rows('T24', 'supervised'), 'V8': sel_rows('V8', 'supervised'), 'E24': sel_rows('E24', 'held')}
    return out


def verify_c_lock():
    sel = json.load(open(f'{C_DIR}/selection.json'))
    for f, h in sel['code'].items():
        if sha_file(f) != h:
            sys.exit(f'C code changed since selection: {f}')
    if sel['manifest_sha256'] != sha_file(f'{D.DATA}/manifest.json'):
        sys.exit('manifest changed since C selection')
    s = sel['selected']
    ck = f"{C_DIR}/lr{s['lr']}/epoch_{s['epoch']:02d}.pt"
    return sel, ck


def run_features(a):
    import torch
    sel, ck = verify_c_lock()
    tg = all_targets()
    for rows in tg.values():
        C.check_rows(rows)
    net = C.Net(torch)
    blob = torch.load(ck, map_location='cpu', weights_only=True)
    net.trunk.load_state_dict(blob['trunk'])
    net.head.load_state_dict(blob['head'])
    for m in net.modules():
        m.cuda().eval()
    out = {'checkpoint': ck, 'checkpoint_sha256': sha_file(ck), 'selection_sha256': sha_file(f'{C_DIR}/selection.json'),
           'manifest_sha256': sha_file(f'{D.DATA}/manifest.json'), 'code': {f: sha_file(f) for f in ('sp75_c.py', 'sp75_data.py', 'sp75_metrics.py', 'rf78_ref.py')}, 'items': {}}
    with torch.no_grad():
        for sp, rows in tg.items():
            for r in rows:
                x = C.row_tensor(r)[None].cuda()
                f = net.trunk(x.flatten(0, 1)).view(1, 3, -1).mean(1)
                lg = net.head(f).float()
                pr = torch.softmax(lg, -1)[0].cpu().numpy()
                f = f[0].float().cpu().numpy()
                fn = f / np.linalg.norm(f)
                out['items'][r['id']] = {'split': sp, 'patient': r['patient'], 'ordinal': r['ordinal'], 'feat': [float(v) for v in fn], 'probs': [float(v) for v in pr],
                                         'pred': int(pr.argmax()) + 1, 'input_file_sha256': [e['file_sha256'] for e in r['inputs']['R']]}
    tmp = FEAT + '.tmp'
    json.dump(out, open(tmp, 'w'))
    os.replace(tmp, FEAT)
    print('features', len(out['items']))


def retrieve(q_feat, bank, exclude_patient_of=None):
    """query feature만 받는다. bank: [{'id','patient','ordinal','grade','feat'(np)}] (T24).
    I: cosine 내림차순(동률 patient int, ordinal)으로 서로 다른 환자 상위 TOPK. D: I의 j번째 grade를 유지하며 같은 grade에서 I_j 환자·D 내 이미 선택된 환자를 제외하고
    cosine 최소(동률 patient int, ordinal) 사례."""
    sims = [(float(np.dot(q_feat, b['feat'])), b) for b in bank]
    order = sorted(sims, key=lambda t: (-round(t[0], 12), int(t[1]['patient']), t[1]['ordinal']))
    I, seen = [], set()
    for s, b in order:
        if b['patient'] in seen:
            continue
        I.append((s, b))
        seen.add(b['patient'])
        if len(I) == TOPK:
            break
    D_, used = [], set()
    for s_i, bi in I:
        cand = [(s, b) for s, b in sims if b['grade'] == bi['grade'] and b['patient'] != bi['patient'] and b['patient'] not in used]
        if not cand:
            raise RuntimeError('no far candidate')
        s, b = sorted(cand, key=lambda t: (round(t[0], 12), int(t[1]['patient']), t[1]['ordinal']))[0]
        D_.append((s, b))
        used.add(b['patient'])
    return I, D_


def ref_entry(s, b, rows_by_id):
    r = rows_by_id[b['id']]
    return {'ref_id': b['id'], 'patient': b['patient'], 'ordinal': b['ordinal'], 'grade': b['grade'], 'cosine': s,
            'images': [{'path': e['path'], 'file_sha256': e['file_sha256'], 'pixel_sha256_padded': e['pixel_sha256_padded']} for e in r['inputs']['R']]}


def build(a):
    if not os.path.exists(FEAT):
        sys.exit('features.json missing')
    ft = json.load(open(FEAT))
    sel, ck = verify_c_lock()
    assert ft['checkpoint_sha256'] == sha_file(ck) and ft['manifest_sha256'] == sha_file(f'{D.DATA}/manifest.json')
    tg = all_targets()
    t24 = tg['T24']
    rows_by_id = {r['id']: r for r in t24}
    bank = [{'id': r['id'], 'patient': r['patient'], 'ordinal': r['ordinal'], 'grade': r['grade'], 'feat': np.array(ft['items'][r['id']]['feat'])} for r in t24]
    bank_pat = {b['patient'] for b in bank}
    for sp in ('V8', 'E24'):
        assert not ({r['patient'] for r in tg[sp]} & bank_pat), 'patient overlap with T24'
    os.makedirs(f'{OUT}/data', exist_ok=True)
    for sp in ('V8', 'E24'):
        reqs, labels = [], {}
        for r in tg[sp]:
            qf = np.array(ft['items'][r['id']]['feat'])
            I, Dd = retrieve(qf, bank)        # query grade 비접근
            reqs.append({'id': r['id'], 'patient': r['patient'], 'ordinal': r['ordinal'], 'split': sp,
                         'query_images': [{'path': e['path'], 'file_sha256': e['file_sha256'], 'pixel_sha256_padded': e['pixel_sha256_padded']} for e in r['inputs']['R']],
                         'I': [ref_entry(s, b, rows_by_id) for s, b in I], 'D': [ref_entry(s, b, rows_by_id) for s, b in Dd]})
            labels[r['id']] = {'grade': r['grade'], 'patient': r['patient'], 'ordinal': r['ordinal']}
        json.dump({'split': sp, 'features_sha256': sha_file(FEAT), 'manifest_sha256': ft['manifest_sha256'], 'rf78_ref_sha256': sha_file('rf78_ref.py'), 'requests': reqs},
                  open(f'{OUT}/data/refs_{sp}.json', 'w'), indent=1)
        json.dump({'split': sp, 'labels': labels}, open(f'{OUT}/data/labels_{sp}.json', 'w'), indent=1)
        print(sp, len(reqs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['features', 'build'])
    ap.add_argument('--gpu', default=None)
    a = ap.parse_args()
    if a.gpu is not None:
        inh = os.environ.get('CUDA_VISIBLE_DEVICES', '').split(',')
        if a.gpu not in inh:
            sys.exit(f'gpu {a.gpu} not in inherited {inh}')
        os.environ['CUDA_VISIBLE_DEVICES'] = a.gpu
    os.makedirs(OUT, exist_ok=True)
    run_features(a) if a.mode == 'features' else build(a)


if __name__ == '__main__':
    main()
