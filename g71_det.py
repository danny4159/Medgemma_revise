"""iter_071 모듈형 detector 대조군: torchvision Faster R-CNN ResNet50-FPN v2 (COCO_V1) -> background/vertebra/disc predictor 재학습.

- 같은 PNG·같은 float bbox annotation(VLM과 동일 slice/GT). mask 전체를 supervision으로 쓰지 않는다. augmentation 없음.
- 학습: SGD momentum0.9 wd1e-4, effective batch4, 첫 2 epoch warmup, epoch20/28 후 LR x0.1. BatchNorm running stats 고정(affine 학습). 32 epoch(연장 시 64).
- 재개: 25 step 및 epoch 경계 checkpoint(model·optimizer·scheduler·RNG·step/epoch/pos), 단일 writer lock, config digest 검사.
- 추론: score floor 0.001, NMS 0.5, detections_per_img 100. 원시 후보(픽셀 xyxy, score, label)를 저장하고 threshold는 평가 단계에서 적용한다.
사용: python g71_det.py train --run-dir D --lr 0.005 --train-key T8 --epochs 32 [--stop-after-step N]
      python g71_det.py infer --ckpt model.pt --key V8 --out out.json
"""
import argparse, hashlib, json, math, os, random, sys, time

sys.path.insert(0, 'results/environments/tv071')
os.environ.setdefault('TORCH_HOME', os.path.abspath('results/environments/torch_home071'))

import numpy as np
import torch
from PIL import Image

import g71_data as D
import g71_train as TR
from rsna_diag import det_lib as DL, queue_lock
from rsna_diag import geometry as G

CLASS = {'vertebra': 1, 'disc': 2}
CFG = {'lr_peak_note': 'SGD', 'momentum': 0.9, 'weight_decay': 1e-4, 'batch': 4, 'warmup_epochs': 2, 'milestones_epochs': [20, 28], 'gamma': 0.1,
       'min_size': 800, 'max_size': 1333, 'score_floor': 0.001, 'nms': 0.5, 'detections': 100, 'num_classes': 3}


def image_groups(key):
    """key의 (patient, offset) 영상별 GT: [{path, boxes_xyxy_px, labels}]. 두 category 질의가 같은 영상을 공유한다."""
    rows = TR.load_items(key)
    imgs = {}
    for r in rows:
        k = (r['patient'], r['offset'])
        d = imgs.setdefault(k, {'patient': r['patient'], 'offset': r['offset'], 'path': r['image'], 'file_sha256': r['file_sha256'], 'boxes': [], 'labels': []})
        for g in r['gt']:
            d['boxes'].append(g['xyxy_px'])
            d['labels'].append(CLASS[r['category']])
    return [imgs[k] for k in sorted(imgs, key=lambda x: (int(x[0]), x[1]))]


class DS(torch.utils.data.Dataset):
    def __init__(self, groups):
        self.g = groups

    def __len__(self):
        return len(self.g)

    def __getitem__(self, i):
        d = self.g[i]
        arr = np.asarray(Image.open(d['path']))
        if hashlib.sha256(open(d['path'], 'rb').read()).hexdigest() != d['file_sha256']:
            raise RuntimeError('image changed')
        rgb = G.to_uint8_rgb_preserving(arr)
        img = torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0
        b = torch.tensor(d['boxes'], dtype=torch.float32).reshape(-1, 4)
        l = torch.tensor(d['labels'], dtype=torch.int64)
        return img, {'boxes': b, 'labels': l}, rgb.shape[:2]


def collate(b):
    return [x[0] for x in b], [x[1] for x in b], [x[2] for x in b]


def build_model():
    return DL.build_model(num_classes=CFG['num_classes'], min_size=CFG['min_size'], max_size=CFG['max_size'])


def sha_file(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def cmd_train(a):
    os.makedirs(a.run_dir, exist_ok=True)
    lk, own, rec = queue_lock.try_lock(os.path.join(os.path.realpath(a.run_dir), 'train.lock'), queue_lock.my_info(role='g71_det'))
    if lk is None:
        sys.exit(f'run-dir owned by live process {own}')
    try:
        train(a, rec)
    finally:
        lk.release()


def train(a, reclaimed):
    dev = torch.device('cuda')
    groups = image_groups(a.train_key)
    N = len(groups)
    spe = math.ceil(N / CFG['batch'])
    weights = os.path.join(os.environ['TORCH_HOME'], 'hub/checkpoints/fasterrcnn_resnet50_fpn_v2_coco-dd69338a.pth')
    code = {f: sha_file(f) for f in ['g71_det.py', 'g71_data.py', 'g71_train.py', 'rsna_diag/det_lib.py']}
    cfg = dict(CFG, lr=a.lr, seed=a.seed, train_key=a.train_key, n_images=N, steps_per_epoch=spe, coco_weights_sha256=sha_file(weights), code=code,
               inputs=hashlib.sha256(json.dumps([(g['path'], g['file_sha256'], g['boxes'], g['labels']) for g in groups]).encode()).hexdigest())
    tdig = hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()
    cp = os.path.join(a.run_dir, 'train_config.json')
    if os.path.exists(cp):
        if json.load(open(cp))['train_digest'] != tdig:
            sys.exit('config differs from existing run-dir; refusing to resume')
    else:
        json.dump({'train_digest': tdig, 'config': cfg, 'torch': torch.__version__}, open(cp, 'w'), indent=1)
    random.seed(a.seed); np.random.seed(a.seed); torch.manual_seed(a.seed); torch.cuda.manual_seed_all(a.seed)
    model = build_model().to(dev)
    opt = DL.build_optimizer(model, lr=a.lr, momentum=CFG['momentum'], weight_decay=CFG['weight_decay'])
    sched = DL.linear_warmup_then_multistep(opt, CFG['warmup_epochs'] * spe, [m * spe for m in CFG['milestones_epochs']], CFG['gamma'])
    ck = os.path.join(a.run_dir, 'ckpt_latest.pt')
    logf = open(os.path.join(a.run_dir, 'train_log.jsonl'), 'a')
    step, epoch0, pos0 = 0, 0, 0

    def lg(**kw):
        logf.write(json.dumps({'ts': time.time(), **kw}) + '\n'); logf.flush()

    def save(epoch, pos):
        DL.atomic_save({'model': model.state_dict(), 'opt': opt.state_dict(), 'sched': sched.state_dict(), 'rng': DL.full_rng_state(), 'step': step, 'epoch': epoch,
                        'pos': pos, 'train_digest': tdig}, ck)
        lg(event='checkpoint', step=step, epoch=epoch, pos=pos)

    if os.path.exists(ck):
        b = torch.load(ck, map_location='cpu', weights_only=False)
        if b['train_digest'] != tdig:
            sys.exit('checkpoint provenance mismatch')
        model.load_state_dict(b['model']); opt.load_state_dict(b['opt']); sched.load_state_dict(b['sched'])
        DL.optimizer_state_to_device(opt, dev)
        DL.restore_rng_state(b['rng'], cuda_map=(0, 0) if len(b['rng']['torch_cuda'] or []) else None)
        step, epoch0, pos0 = b['step'], b['epoch'], b['pos']
        lg(event='resume', step=step, epoch=epoch0, pos=pos0, stale_lock_reclaimed=bool(reclaimed))
    save_eps = {int(x) for x in a.save_epochs.split(',')}
    ds = DS(groups)
    for epoch in range(epoch0, a.epochs):
        order = np.random.default_rng(a.seed * 1000 + epoch).permutation(N)
        DL.set_train_mode(model)
        for s in range(pos0 if epoch == epoch0 else 0, spe):
            idx = order[s * CFG['batch']:(s + 1) * CFG['batch']]
            imgs, tg, _ = collate([ds[int(i)] for i in idx])
            imgs = [x.to(dev) for x in imgs]
            tg = [{k: v.to(dev) for k, v in t.items()} for t in tg]
            losses = model(imgs, tg)
            loss = sum(losses.values())
            if not torch.isfinite(loss):
                raise RuntimeError(f'non-finite loss at step {step}')
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step(); sched.step(); step += 1
            lg(step=step, epoch=epoch + 1, pos=s + 1, loss=float(loss), lr=opt.param_groups[0]['lr'], ids=[f"{groups[int(i)]['patient']}_{groups[int(i)]['offset']}" for i in idx],
               parts={k: float(v) for k, v in losses.items()})
            if step % 25 == 0 and s + 1 < spe:
                save(epoch, s + 1)
                if a.stop_after_step == step:
                    print('test stop', flush=True); os._exit(5)
        e = epoch + 1
        if e in save_eps or e == a.epochs:
            os.makedirs(os.path.join(a.run_dir, f'epoch_{e:02d}'), exist_ok=True)
            DL.atomic_save({'model': model.state_dict(), 'epoch': e, 'step': step, 'train_digest': tdig}, os.path.join(a.run_dir, f'epoch_{e:02d}', 'model.pt'))
        save(e, 0)
    print('training complete', flush=True)


@torch.no_grad()
def infer(ckpt, key, out_path, batch=1):
    dev = torch.device('cuda')
    model = build_model().to(dev)
    b = torch.load(ckpt, map_location='cpu', weights_only=False)
    model.load_state_dict(b['model'])
    model.eval()
    groups = image_groups(key)
    ds = DS(groups)
    res, t0 = {}, time.time()
    for i, g in enumerate(groups):
        img, _, hw = ds[i]
        torch.cuda.synchronize(); t = time.time()
        pr = model([img.to(dev)])[0]
        torch.cuda.synchronize()
        res[f"{g['patient']}_{D.OFF_NAME[g['offset']]}"] = {'boxes_xyxy_px': pr['boxes'].cpu().numpy().tolist(), 'scores': pr['scores'].cpu().numpy().tolist(),
                                                       'labels': pr['labels'].cpu().numpy().tolist(), 'img_hw': list(hw), 'runtime_s': time.time() - t}
    json.dump({'ckpt': ckpt, 'ckpt_sha256': sha_file(ckpt), 'train_digest': b['train_digest'], 'key': key, 'epoch': b['epoch'], 'n_images': len(groups), 'preds': res,
               'wall_s': time.time() - t0}, open(out_path, 'w'))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    t = sub.add_parser('train')
    t.add_argument('--run-dir', required=True); t.add_argument('--lr', type=float, required=True); t.add_argument('--seed', type=int, default=17)
    t.add_argument('--train-key', required=True); t.add_argument('--epochs', type=int, required=True); t.add_argument('--save-epochs', default='8,16,24,32,48,64')
    t.add_argument('--stop-after-step', type=int, default=None)
    i = sub.add_parser('infer')
    i.add_argument('--ckpt', required=True); i.add_argument('--key', required=True); i.add_argument('--out', required=True)
    a = ap.parse_args()
    if a.cmd == 'train':
        cmd_train(a)
    else:
        infer(a.ckpt, a.key, a.out)
