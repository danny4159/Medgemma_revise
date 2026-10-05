"""iter_075 C: 공유 ResNet18 crop 분류기 (R과 같은 세 crop). ImageNet 초기값에서 적응, 세 영상 feature 평균 + 공통 5-class head.

- 입력: R crop PNG(L) 3장 -> 중앙 square padding(종횡비 보존) -> 224 bilinear -> gray 3채널 복제 -> ImageNet normalization. 병변 central crop 없음.
- 증강(사전 고정): 한 target의 세 slice에 같은 translate(+-8px at 224)·scale(0.9-1.1). flip/rotation/intensity 없음. 평가에는 증강 없음.
- 학습 T24 supervised(ordinal 1,3,5)만, V8 supervised로 8 epoch마다 CE/primary 평가. E24는 `predict` 단계에서 선택 파일(LOCK) 확인 후에만 읽는다.
- LR 1e-4/1e-3, AdamW wd1e-4, batch8, seed17, 최대 64 epoch. 최근 세 milestone에서 V8 CE와 primary가 모두 개선되지 않으면 종료.
사용: python sp75_c.py train --out D --gpu 0  /  python sp75_c.py predict --out D --gpu 0
"""
import argparse, hashlib, json, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results/environments/tv071'))
import numpy as np
from PIL import Image

import sp75_data as D
import sp75_metrics as M

TORCH_HOME_W = 'results/environments/ch75/torch_home/hub/checkpoints/resnet18-f37072fd.pth'
WEIGHT_SHA256 = 'f37072fd47e89c5e827621c5baffa7500819f7896bbacec160b1a16c560e07ec'
LRS = (1e-4, 1e-3)
MAX_EPOCH, MILESTONE, BATCH, SEED, WD = 64, 8, 8, 17, 1e-4
SIDE = 224
TRANS_PX, SCALE_RANGE = 8, (0.9, 1.1)
MEAN, STD = np.array([0.485, 0.456, 0.406], np.float32), np.array([0.229, 0.224, 0.225], np.float32)
CODE = ['sp75_c.py', 'sp75_data.py', 'sp75_metrics.py']


def sha_file(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def load_crop(path):
    a = np.asarray(Image.open(path))
    h, w = a.shape
    s = max(h, w)
    top, left = (s - h) // 2, (s - w) // 2
    sq = np.zeros((s, s), np.uint8)
    sq[top:top + h, left:left + w] = a
    im = Image.fromarray(sq, mode='L').resize((SIDE, SIDE), resample=Image.BILINEAR)
    x = np.asarray(im, np.float32) / 255.0
    return x


def to_tensor(x_list):
    import torch
    arr = np.stack([(np.repeat(x[:, :, None], 3, axis=2) - MEAN) / STD for x in x_list]).transpose(0, 3, 1, 2)
    return torch.from_numpy(np.ascontiguousarray(arr))


def augment(torch, xs, rng):
    """xs: (3,3,H,W) tensor. 같은 translate/scale을 세 slice에 적용."""
    import torchvision.transforms.v2.functional as TF
    tx, ty = [int(v) for v in rng.integers(-TRANS_PX, TRANS_PX + 1, 2)]
    sc = float(rng.uniform(*SCALE_RANGE))
    return TF.affine(xs, angle=0.0, translate=[tx, ty], scale=sc, shear=[0.0, 0.0])


def build_model(torch):
    import torchvision
    if sha_file(TORCH_HOME_W) != WEIGHT_SHA256:
        raise RuntimeError('resnet18 weight digest mismatch')
    m = torchvision.models.resnet18()
    m.load_state_dict(torch.load(TORCH_HOME_W, map_location='cpu', weights_only=True))
    m.fc = torch.nn.Identity()
    head = torch.nn.Linear(512, 5)
    return m, head


class Net:
    def __init__(self, torch):
        self.trunk, self.head = build_model(torch)

    def forward(self, x3):  # x3: (B,3,3,H,W) -> (B,5)
        B = x3.shape[0]
        f = self.trunk(x3.flatten(0, 1)).view(B, 3, -1).mean(1)
        return self.head(f)

    def modules(self):
        return [self.trunk, self.head]


def row_tensor(r):
    return to_tensor([load_crop(e['path']) for e in r['inputs']['R']])


def check_rows(rows):
    for r in rows:
        for e in r['inputs']['R']:
            assert sha_file(e['path']) == e['file_sha256'], f"file hash changed {e['path']}"


def evaluate(torch, net, rows, tens):
    for m in net.modules():
        m.eval()
    probs = []
    with torch.no_grad():
        for i in range(0, len(rows), 16):
            x = torch.stack([tens[j] for j in range(i, min(len(rows), i + 16))]).cuda()
            probs.append(torch.softmax(net.forward(x).float(), -1).cpu())
    return torch.cat(probs).numpy()


def ce_of(probs, rows):
    return float(-np.mean([np.log(max(probs[i, r['grade'] - 1], 1e-12)) for i, r in enumerate(rows)]))


def train_one(torch, lr, tr_rows, va_rows, tr_t, va_t, out):
    os.makedirs(out, exist_ok=True)
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    net = Net(torch)
    for m in net.modules():
        m.cuda()
    params = [p for m in net.modules() for p in m.parameters()]
    opt = torch.optim.AdamW(params, lr=lr, weight_decay=WD)
    hist, best, no_imp = [], None, 0
    t0 = time.time()
    n = len(tr_rows)
    for ep in range(1, MAX_EPOCH + 1):
        rng = np.random.default_rng(SEED * 1000 + ep)
        order = rng.permutation(n)
        for m in net.modules():
            m.train()
        tot = 0.0
        for s in range(0, n, BATCH):
            ix = order[s:s + BATCH]
            xs = torch.stack([augment(torch, tr_t[j], rng) for j in ix]).cuda()
            y = torch.tensor([tr_rows[j]['grade'] - 1 for j in ix]).cuda()
            loss = torch.nn.functional.cross_entropy(net.forward(xs).float(), y)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            if not torch.isfinite(loss):
                raise RuntimeError('non-finite loss')
            opt.step()
            tot += float(loss) * len(ix)
        if ep % MILESTONE == 0:
            pr = evaluate(torch, net, va_rows, va_t)
            pred = [int(np.argmax(p)) + 1 for p in pr]
            prim = M.class_std_mae([r['grade'] for r in va_rows], pred)[0]
            ce = ce_of(pr, va_rows)
            rec = {'epoch': ep, 'train_loss_epoch_mean': tot / n, 'val_ce': ce, 'val_primary': prim, 'elapsed_s': time.time() - t0}
            hist.append(rec)
            torch.save({'trunk': net.trunk.state_dict(), 'head': net.head.state_dict(), 'epoch': ep, 'lr': lr}, f'{out}/epoch_{ep:02d}.pt')
            improved = best is None or ce < best['ce'] - 1e-12 or prim < best['prim'] - 1e-12
            if improved:
                best = {'ce': min(ce, best['ce']) if best else ce, 'prim': min(prim, best['prim']) if best else prim}
                no_imp = 0
            else:
                no_imp += 1
            json.dump(hist, open(f'{out}/history.json', 'w'), indent=1)
            if no_imp >= 3:
                break
    return hist


def run_train(a):
    import torch
    rows_all = D.load_manifest()['rows']
    sel = lambda sp: sorted([r for r in rows_all if r['split'] == sp and r['position_set'] == 'supervised' and not r['excluded']], key=lambda r: (int(r['patient']), r['ordinal']))
    tr_rows, va_rows = sel('T24'), sel('V8')
    check_rows(tr_rows + va_rows)
    tr_t = [row_tensor(r) for r in tr_rows]
    va_t = [row_tensor(r) for r in va_rows]
    res = {'lrs': {}, 'code': {f: sha_file(f) for f in CODE}, 'weight_sha256': WEIGHT_SHA256, 'n_train': len(tr_rows), 'n_val': len(va_rows),
           'cfg': {'lrs': LRS, 'max_epoch': MAX_EPOCH, 'milestone': MILESTONE, 'batch': BATCH, 'seed': SEED, 'wd': WD, 'side': SIDE, 'trans_px': TRANS_PX, 'scale': SCALE_RANGE},
           'manifest_sha256': sha_file(f'{D.DATA}/manifest.json')}
    for lr in LRS:
        out = f'{a.out}/lr{lr:g}'
        if os.path.exists(f'{out}/history.json'):
            sys.exit(f'{out} exists')
        hist = train_one(torch, lr, tr_rows, va_rows, tr_t, va_t, out)
        res['lrs'][f'{lr:g}'] = hist
    # 선택: V8 primary 최소, 동률은 CE, 더 이른 epoch, 작은 LR
    cands = [(h['val_primary'], h['val_ce'], h['epoch'], float(lr), lr) for lr, hs in res['lrs'].items() for h in hs]
    cands.sort(key=lambda c: (round(c[0], 12), round(c[1], 12), c[2], c[3]))
    best = cands[0]
    res['selected'] = {'lr': best[4], 'epoch': best[2], 'val_primary': best[0], 'val_ce': best[1]}
    json.dump(res, open(f'{a.out}/selection.json', 'w'), indent=1)
    print(json.dumps(res['selected']))


def run_predict(a):
    import torch
    sel = json.load(open(f'{a.out}/selection.json'))
    s = sel['selected']
    for f, h in sel['code'].items():
        if sha_file(f) != h:
            sys.exit(f'code changed since selection: {f}')
    if sel['manifest_sha256'] != sha_file(f'{D.DATA}/manifest.json'):
        sys.exit('manifest changed since selection')
    ck = f"{a.out}/lr{s['lr']}/epoch_{s['epoch']:02d}.pt"
    rows_all = D.load_manifest()['rows']
    rows = sorted([r for r in rows_all if r['split'] == a.split and not r['excluded']], key=lambda r: (int(r['patient']), r['ordinal']))
    check_rows(rows)
    net = Net(torch)
    blob = torch.load(ck, map_location='cpu', weights_only=True)
    net.trunk.load_state_dict(blob['trunk'])
    net.head.load_state_dict(blob['head'])
    for m in net.modules():
        m.cuda()
    t0 = time.time()
    tens = [row_tensor(r) for r in rows]
    pr = evaluate(torch, net, rows, tens)
    dt = time.time() - t0
    out = [{'id': r['id'], 'patient': r['patient'], 'ordinal': r['ordinal'], 'position_set': r['position_set'], 'probs': pr[i].tolist(), 'pred': int(np.argmax(pr[i])) + 1}
           for i, r in enumerate(rows)]
    json.dump({'selected': s, 'checkpoint': ck, 'checkpoint_sha256': sha_file(ck), 'split': a.split, 'n': len(out), 'preds': out, 'elapsed_s': dt},
              open(f'{a.out}/pred_{a.split}.json', 'w'), indent=1)
    print('wrote', len(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['train', 'predict'])
    ap.add_argument('--out', required=True)
    ap.add_argument('--split', default='E24')
    ap.add_argument('--gpu', default=None)
    a = ap.parse_args()
    if a.gpu is not None:
        inh = os.environ.get('CUDA_VISIBLE_DEVICES', '').split(',')
        if a.gpu not in inh:
            sys.exit(f'gpu {a.gpu} not in inherited {inh}')
        os.environ['CUDA_VISIBLE_DEVICES'] = a.gpu
    os.makedirs(a.out, exist_ok=True)
    run_train(a) if a.mode == 'train' else run_predict(a)


if __name__ == '__main__':
    main()
