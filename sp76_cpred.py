"""iter_076: iter_075에서 선택·고정한 C(ResNet18)/H(radiomics RF)의 E24 예측을 새 결과 경로에 생성한다. 선택·학습은 재실행하지 않는다.

sp75_c.py / sp75_h.py는 수정하지 않고 import해서 같은 함수를 쓴다(선택 파일의 code hash가 현재 파일과 같을 때만 실행 = 읽기 전용 재사용).
사용: python sp76_cpred.py C|H --out results/iter_076/pred --lock results/iter_076/eval/eval_lock.json [--gpu 0]
E24 예측은 사전 eval_lock이 있을 때만 생성한다. 출력이 존재하면 중단.
"""
import argparse, hashlib, json, os, sys, time

SEL_DIR = {'C': 'results/iter_075/C', 'H': 'results/iter_075/H'}


def sha_file(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def check_lock(path):
    lock = json.load(open(path))
    for f, h in lock['files'].items():
        if sha_file(f) != h:
            sys.exit(f'locked file changed: {f}')
    return lock


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('system', choices=['C', 'H'])
    ap.add_argument('--out', required=True)
    ap.add_argument('--lock', required=True)
    ap.add_argument('--split', default='E24')
    ap.add_argument('--gpu', default=None)
    a = ap.parse_args()
    lock = check_lock(a.lock)
    if a.gpu is not None:
        inh = os.environ.get('CUDA_VISIBLE_DEVICES', '').split(',')
        if a.gpu not in inh:
            sys.exit(f'gpu {a.gpu} not in inherited {inh}')
        os.environ['CUDA_VISIBLE_DEVICES'] = a.gpu
    out_path = f'{a.out}/pred_{a.system}_{a.split}.json'
    if lock['json_systems'].get(a.system) != out_path:
        sys.exit(f'{out_path} not registered in lock')
    if os.path.exists(out_path):
        sys.exit('prediction exists')
    os.makedirs(a.out, exist_ok=True)
    sel_dir = SEL_DIR[a.system]
    sel = json.load(open(f'{sel_dir}/selection.json'))
    for f, h in sel['code'].items():
        if sha_file(f) != h:
            sys.exit(f'code changed since selection: {f}')
    t0 = time.time()
    import numpy as np
    import sp75_data as D
    if sel['manifest_sha256'] != sha_file(f'{D.DATA}/manifest.json'):
        sys.exit('manifest changed since selection')
    rows_all = D.load_manifest()['rows']
    D.load_split()
    rows = sorted([r for r in rows_all if r['split'] == a.split and not r['excluded']], key=lambda r: (int(r['patient']), r['ordinal']))
    if a.system == 'C':
        import torch
        import sp75_c as C
        s = sel['selected']
        ck = f"{sel_dir}/lr{s['lr']}/epoch_{s['epoch']:02d}.pt"
        C.check_rows(rows)
        net = C.Net(torch)
        blob = torch.load(ck, map_location='cpu', weights_only=True)
        net.trunk.load_state_dict(blob['trunk'])
        net.head.load_state_dict(blob['head'])
        for m in net.modules():
            m.cuda()
        tens = [C.row_tensor(r) for r in rows]
        pr = C.evaluate(torch, net, rows, tens)
        meta = {'checkpoint': ck, 'checkpoint_sha256': sha_file(ck)}
    else:
        import sp75_h as H
        from sklearn.ensemble import RandomForestClassifier
        s = sel['selected']
        tr = sorted([r for r in rows_all if r['split'] == 'T24' and r['position_set'] == 'supervised' and not r['excluded']], key=lambda r: (int(r['patient']), r['ordinal']))
        cache = json.load(open(f'{sel_dir}/features_T24_V8.json'))
        Xtr, names = H.matrix(tr, cache)
        med, keep = H.prep_fit(Xtr)
        rf = RandomForestClassifier(n_estimators=500, random_state=17, n_jobs=4, **s['cfg']).fit(H.prep_apply(Xtr, med, keep), np.array([r['grade'] for r in tr]))
        ec = H.feats_for(rows, H.extractor(), f'{a.out}/features_{a.split}.json')
        X, _ = H.matrix(rows, ec, names)
        p_ = rf.predict_proba(H.prep_apply(X, med, keep))
        pr = np.zeros((len(rows), 5))
        for j, c in enumerate(list(rf.classes_)):
            pr[:, c - 1] = p_[:, j]
        meta = {'features_T24_V8_sha256': sha_file(f'{sel_dir}/features_T24_V8.json')}
    preds = [{'id': r['id'], 'patient': r['patient'], 'ordinal': r['ordinal'], 'position_set': r['position_set'], 'probs': [float(x) for x in pr[i]],
              'pred': int(np.argmax(pr[i])) + 1} for i, r in enumerate(rows)]
    tmp = out_path + '.tmp'
    json.dump({'system': a.system, 'selected': s, 'selection_sha256': sha_file(f'{sel_dir}/selection.json'), 'split': a.split, 'n': len(preds), 'preds': preds,
               'elapsed_s': time.time() - t0, **meta}, open(tmp, 'w'), indent=1)
    os.replace(tmp, out_path)
    print('wrote', len(preds), out_path)


if __name__ == '__main__':
    main()
