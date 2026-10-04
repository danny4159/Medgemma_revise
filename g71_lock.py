"""E24 평가 전 잠금: 선택된 D8/R8 checkpoint, detector checkpoint·threshold, template, 코드·manifest hash를 results/iter_071/decide/e24_lock.json에 기록한다.
이미 존재하면 덮어쓰지 않고 내용이 같은지 검증만 한다. 사용: python g71_lock.py"""
import hashlib, json, os, sys

import g71_baseline as B

OUT = 'results/iter_071/decide/e24_lock.json'


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


gate = json.load(open('results/iter_071/decide/t24_gate.json'))
det = json.load(open('results/iter_071/decide/det_select_T8.json'))
best = None
for k, v in det.items():
    key = (round(v['f1@0.5'], 12), round(v['f1@0.3'], 12), v['thr'], -v['epoch'])
    if best is None or key > best[0]:
        best = (key, v)
d = best[1]
vl = {}
for init, name in gate['selected'].items():
    parts = name.split('_')
    run = f'results/iter_071/train/{parts[0]}_{parts[1]}_{parts[2]}'
    ep = int(parts[3][1:])
    ad = f'{run}/epoch_{ep:02d}/adapter.pt'
    vl[init] = {'name': name, 'run_dir': run, 'epoch': ep, 'adapter': ad, 'adapter_dir': os.path.dirname(ad), 'adapter_file_sha256': sha(ad)}
ck = f"{d['run']}/epoch_{d['epoch']:02d}/model.pt"
lock = {'enter_T24': gate['enter_T24'], 'vlm': vl, 'detector': {'run': d['run'], 'epoch': d['epoch'], 'threshold': d['thr'], 'ckpt': ck, 'ckpt_sha256': sha(ck), 'V8_f1@0.5': d['f1@0.5'],
        'selection': 'max V8 macro F1@0.5 over (lr, checkpoint, threshold); ties -> higher threshold'},
        'template': {c: {k: v for k, v in t.items()} for c, t in B.train_template('T8').items()},
        'code': {f: sha(f) for f in ['g71_data.py', 'g71_eval.py', 'g71_train.py', 'g71_gen.py', 'g71_det.py', 'g71_det_stage.py', 'g71_baseline.py', 'g71_analyze.py', 'g71_verify.py']},
        'manifest_sha256': sha('results/iter_071/data/manifest.json'), 'split_lock_sha256': sha('results/iter_071/data/split_lock.json')}
if os.path.exists(OUT):
    old = json.load(open(OUT))
    if old != lock:
        sys.exit('e24_lock.json exists and differs from current selection/code; refusing to overwrite')
    print('lock verified identical')
else:
    json.dump(lock, open(OUT, 'w'), indent=1)
    print('lock written', json.dumps({k: lock[k] for k in ('enter_T24', 'detector')}))
    print({k: v['name'] for k, v in vl.items()})
