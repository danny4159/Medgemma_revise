"""iter_071 MRI anatomy-grounding 직접 LoRA SFT (D: base 새 LoRA / R: RSNA source adapter 초기화). 표준 SFT, 새 loss 없음.

재사용: rsna_diag.train의 assistant-only CE·digest·RNG·checkpoint 유틸, rsna_diag.sft_data.build_example/collate, rsna_diag.lora, generate.load_model.
이 파일은 task wrapper: 새 manifest·target(floor/ceil)·prompt·일정(32 epoch horizon cosine, 5% warmup)·validation CE·재개 검사만 연결한다.
기존 RSNA train CLI/validation pipeline/부모 결과 복사 분기는 호출하지 않는다.
사용: python g71_train.py --run-dir D --init base|source --lr 2e-4 --train-key T8 --epochs 16 [--val-key V4] --seed 17
"""
import argparse, hashlib, json, math, os, sys, time

import numpy as np

import g71_data as D
from rsna_diag import generate, lora, queue_lock, sft_data
from rsna_diag import train as T

SOURCE_ADAPTER = 'results/iter_012/train/lr2e-4_s17/epoch_05/adapter.pt'
SOURCE_DIGEST = 'e13f3c4461b826a060c90dfe4e4ee4c2ebac36a08f84be1a45a37495816cec11'
HORIZON = 32
CFG = {'r': 16, 'alpha': 32, 'dropout': 0.05, 'weight_decay': 0.01, 'betas': [0.9, 0.999], 'eps': 1e-8, 'grad_clip': 1.0,
       'warmup_frac': 0.05, 'eff_batch': 8, 'horizon_epochs': HORIZON, 'schedule': 'linear warmup 5% then cosine to 0 over 32-epoch horizon',
       'target': 'floor/ceil int box, top->bottom order', 'prompts': {c: D.prompt_sha(c) for c in D.CATS}}


def lr_at(step, spe, peak, horizon=HORIZON, warm_frac=0.05):
    total = spe * horizon
    warm = math.ceil(warm_frac * total)
    if step < warm:
        return peak * (step + 1) / warm
    return 0.5 * peak * (1 + math.cos(math.pi * (step - warm) / (total - warm)))


def load_items(key):
    sp = D.load_split()
    man = json.load(open(f'{D.DATA}/manifest.json'))
    pids = set(sp[key])
    rows = [r for r in man['rows'] if r['patient'] in pids]
    rows.sort(key=lambda r: (int(r['patient']), r['offset'], r['category']))
    infos = man['patients']
    for r in rows:
        r['pixel_sha256_padded'] = infos[r['patient']]['images'][D.OFF_NAME[r['offset']]]['pixel_sha256_padded']
    return rows


def example(proc, row):
    image, _, pxsha = generate.load_image(row['image'])
    if pxsha != row['pixel_sha256_padded']:
        raise RuntimeError(f"pixel hash changed for {row['id']}")
    tgt = D.target_text(row['category'], [g['yxyx_norm'] for g in row['gt']])
    ex = sft_data.build_example(proc, image, D.PROMPTS[row['category']], tgt)
    return ex, tgt


class DS:
    def __init__(self, proc, rows, order):
        self.proc, self.rows, self.order = proc, rows, order

    def __len__(self):
        return len(self.order)

    def __getitem__(self, k):
        ex, _ = example(self.proc, self.rows[self.order[k]])
        ex['sample_pos'] = int(k)
        return ex


def val_ce(torch, model, proc, rows, softcap):
    model.eval()
    tot, n = 0.0, 0
    with torch.no_grad():
        for r in rows:
            ex, _ = example(proc, r)
            b = {k: (v.unsqueeze(0).cuda() if k in ('input_ids', 'attention_mask', 'labels', 'token_type_ids') else v.cuda()) for k, v in ex.items() if k != 'n_prefix'}
            s, c = T.assistant_loss_sum(torch, model, b, softcap)
            tot += float(s)
            n += c
    return tot / n, n


def file_sha(p):
    h = hashlib.sha256()
    h.update(open(p, 'rb').read())
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-dir', required=True)
    ap.add_argument('--init', choices=['base', 'source'], required=True)
    ap.add_argument('--lr', type=float, required=True)
    ap.add_argument('--seed', type=int, default=17)
    ap.add_argument('--train-key', required=True, choices=['T8', 'T24'])
    ap.add_argument('--val-key', default='V4', choices=['V4', 'V8'])
    ap.add_argument('--epochs', type=int, required=True)
    ap.add_argument('--save-epochs', default='4,8,16,24,32', help='adapter 저장 및 validation CE 계산 epoch')
    ap.add_argument('--microbatch', type=int, default=1)
    ap.add_argument('--ckpt-every', type=int, default=25)
    ap.add_argument('--workers', type=int, default=2)
    ap.add_argument('--stop-after-step', type=int, default=None, help='test: 이 step의 정기 checkpoint 직후 종료(epoch 중간)')
    ap.add_argument('--stop-after-epoch-ckpt', type=int, default=None, help='test: epoch adapter/ckpt 저장 직후 종료(validation CE 전)')
    ap.add_argument('--code-files', default=None)
    a = ap.parse_args()
    if a.epochs > HORIZON:
        sys.exit('epochs exceeds fixed horizon')
    os.makedirs(a.run_dir, exist_ok=True)
    lk, own, rec = queue_lock.try_lock(os.path.join(os.path.realpath(a.run_dir), 'train.lock'), queue_lock.my_info(role='g71_train'))
    if lk is None:
        sys.exit(f'run-dir owned by live process {own}')
    T.LOCK_FD[0] = lk.fd
    try:
        run(a, rec)
    finally:
        lk.release()


def run(a, reclaimed):
    import torch
    train_rows = load_items(a.train_key)
    val_rows = load_items(a.val_key)
    assert not {r['patient'] for r in train_rows} & {r['patient'] for r in val_rows}
    save_epochs = {int(x) for x in a.save_epochs.split(',')}
    T.seed_all(torch, a.seed)
    _, proc, model = generate.load_model()
    names = lora.apply_lora(model, CFG['r'], CFG['alpha'], CFG['dropout'], seed=a.seed)
    init_info = {'init': a.init}
    if a.init == 'source':
        blob = torch.load(SOURCE_ADAPTER, map_location='cpu', weights_only=True)
        dg = lora.state_digest(blob['state'])
        if dg != SOURCE_DIGEST or blob['config'] != {'r': 16, 'alpha': 32}:
            sys.exit(f'source adapter digest/config mismatch {dg} {blob["config"]}')
        lora.load_lora_state(model, blob['state'])
        init_info.update({'source_adapter': SOURCE_ADAPTER, 'source_digest': dg, 'source_file_sha256': file_sha(SOURCE_ADAPTER)})
    tok = proc.tokenizer
    softcap = getattr(model.config.get_text_config(), 'final_logit_softcapping', None)
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False})
    model.config.use_cache = False
    params = list(lora.lora_params(model).values())
    init_digest = lora.state_digest(lora.lora_state_dict(model))
    train_ids = [r['id'] for r in train_rows]
    tin = hashlib.sha256(json.dumps([(r['id'], r['file_sha256'], r['pixel_sha256_padded'], D.target_text(r['category'], [g['yxyx_norm'] for g in r['gt']]))
                                     for r in train_rows], sort_keys=True).encode()).hexdigest()
    vin = hashlib.sha256(json.dumps([(r['id'], r['file_sha256'], r['pixel_sha256_padded'], D.target_text(r['category'], [g['yxyx_norm'] for g in r['gt']]))
                                     for r in val_rows], sort_keys=True).encode()).hexdigest()
    code = {f: file_sha(f) for f in ['g71_train.py', 'g71_data.py', 'rsna_diag/train.py', 'rsna_diag/sft_data.py', 'rsna_diag/lora.py', 'rsna_diag/generate.py']}
    cfg = dict(CFG, lr=a.lr, seed=a.seed, microbatch=a.microbatch, n_train=len(train_rows), n_val=len(val_rows), train_key=a.train_key, val_key=a.val_key,
               model_revision=generate.MODEL_REVISION, n_lora_targets=len(names), n_trainable=sum(p.numel() for p in params), train_inputs_digest=tin,
               val_inputs_digest=vin, init=init_info, init_adapter_digest=init_digest, save_epochs=sorted(save_epochs), code=code)
    tdig = hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()
    cfg_path = os.path.join(a.run_dir, 'train_config.json')
    if os.path.exists(cfg_path):
        old = json.load(open(cfg_path))
        if old['train_digest'] != tdig:
            sys.exit('train config (incl. LR/init/inputs/code) differs from existing run-dir; refusing to resume')
    else:
        json.dump({'train_digest': tdig, 'config': cfg, 'env': generate.env_info(torch, proc, model)}, open(cfg_path, 'w'), indent=1, default=str)
    opt = torch.optim.AdamW(params, lr=a.lr, betas=tuple(CFG['betas']), eps=CFG['eps'], weight_decay=CFG['weight_decay'])
    n_tr = len(train_rows)
    spe = math.ceil(n_tr / CFG['eff_batch'])
    step, epoch0, pos0 = 0, 0, 0
    ck = os.path.join(a.run_dir, 'ckpt_latest.pt')
    logf = open(os.path.join(a.run_dir, 'train_log.jsonl'), 'a')

    def log_event(**kw):
        logf.write(json.dumps({'ts': time.time(), **kw}) + '\n')
        logf.flush()

    def save_ckpt(epoch, pos):
        dg = T.live_digests(torch, model, opt)
        T.atomic_save(torch, {'lora': lora.lora_state_dict(model), 'optimizer': opt.state_dict(), 'step': step, 'epoch': epoch, 'pos_in_epoch': pos,
                              'rng': T.rng_state(torch), 'train_digest': tdig, 'digests': dg}, ck)
        log_event(event='checkpoint', step=step, epoch=epoch, pos=pos, digests=dg)

    if os.path.exists(ck):
        blob = torch.load(ck, map_location='cpu', weights_only=False)
        if blob['train_digest'] != tdig:
            sys.exit('checkpoint provenance mismatch')
        lora.load_lora_state(model, blob['lora'])
        opt.load_state_dict(blob['optimizer'])
        step, epoch0, pos0 = blob['step'], blob['epoch'], blob['pos_in_epoch']
        T.set_rng_state(torch, blob['rng'])
        restored = T.live_digests(torch, model, opt)
        if restored != blob['digests']:
            sys.exit(f'restored state != saved checkpoint state {restored} vs {blob["digests"]}')
        log_event(event='resume', step=step, epoch=epoch0, pos=pos0, restored_equals_saved=True, stale_lock_reclaimed=bool(reclaimed))
        print(f'resumed step={step} epoch={epoch0} pos={pos0}', flush=True)
    t0 = time.time()

    def do_val(e):
        edir = os.path.join(a.run_dir, f'epoch_{e:02d}')
        vm = os.path.join(edir, 'val_ce.json')
        if os.path.exists(vm):
            old = json.load(open(vm))
            ap_ = torch.load(os.path.join(edir, 'adapter.pt'), map_location='cpu', weights_only=True)
            if old['train_digest'] != tdig or old['adapter_digest'] != lora.state_digest(ap_['state']):
                raise RuntimeError(f'existing val_ce for epoch {e} does not match run')
            return
        rng_b, pre = T.rng_state(torch), T.live_digests(torch, model, opt)
        snap = lora.lora_state_dict(model)
        ad = torch.load(os.path.join(edir, 'adapter.pt'), map_location='cpu', weights_only=True)
        if lora.state_digest(ad['state']) != ad['digest']:
            raise RuntimeError('epoch adapter digest mismatch')
        lora.load_lora_state(model, ad['state'])
        v, n = val_ce(torch, model, proc, val_rows, softcap)
        lora.load_lora_state(model, snap)
        model.train()
        T.set_rng_state(torch, rng_b)
        post = T.live_digests(torch, model, opt)
        if post != pre:
            raise RuntimeError('validation changed training state')
        json.dump({'epoch': e, 'val_ce': v, 'val_tokens': n, 'adapter_digest': ad['digest'], 'train_digest': tdig, 'val_inputs_digest': vin, 'step': e * spe},
                  open(vm, 'w'))
        log_event(event='val_ce', epoch=e, val_ce=v, state_unchanged=True)
        print(f'epoch {e}: val_ce {v:.4f} ({n} tokens)', flush=True)

    for e in range(1, epoch0 + 1):  # 저장은 됐으나 val_ce가 없는 epoch 복구
        if e in save_epochs:
            do_val(e)
    for epoch in range(epoch0, a.epochs):
        rng = np.random.default_rng(a.seed * 1000 + epoch)
        order = rng.permutation(n_tr)
        start = pos0 if epoch == epoch0 else 0
        ds = DS(proc, train_rows, order)
        idx = list(range(start * CFG['eff_batch'], n_tr))
        g = torch.Generator()
        g.manual_seed(a.seed * 1000 + epoch)
        dl = torch.utils.data.DataLoader(torch.utils.data.Subset(ds, idx), batch_size=a.microbatch, shuffle=False, num_workers=a.workers,
                                         collate_fn=lambda ex: sft_data.collate(ex, tok.pad_token_id), prefetch_factor=2 if a.workers else None,
                                         worker_init_fn=T.close_lock_fd, generator=g)
        model.train()
        it = iter(dl)
        for s in range(start, spe):
            grp = order[s * CFG['eff_batch']:(s + 1) * CFG['eff_batch']]
            tot_tok = sum(T.label_count(tok, example_text(train_rows[j])) for j in grp)
            lr = lr_at(step, spe, a.lr)
            for gp in opt.param_groups:
                gp['lr'] = lr
            rng_before, opt_before = T.rng_digest(torch), T.opt_step_count(opt)
            loss_acc, ntok = 0.0, 0
            seen, th = [], hashlib.sha256()
            for _ in range(math.ceil(len(grp) / a.microbatch)):
                b = next(it)
                seen += b.pop('sample_pos').tolist()
                th.update(T.batch_token_digest(b).digest())
                b = {k: v.cuda() for k, v in b.items()}
                ls, nt = T.assistant_loss_sum(torch, model, b, softcap)
                (ls / tot_tok).backward()
                loss_acc += float(ls) / tot_tok
                ntok += nt
            if ntok != tot_tok:
                raise RuntimeError(f'label token count mismatch {ntok} != {tot_tok}')
            planned = [train_rows[j]['id'] for j in grp]
            actual = [train_rows[order[p]]['id'] for p in seen]
            if actual != planned:
                raise RuntimeError(f'step {step + 1}: DataLoader batch != planned')
            gn = float(torch.nn.utils.clip_grad_norm_(params, CFG['grad_clip']))
            if not math.isfinite(gn) or not math.isfinite(loss_acc):
                raise RuntimeError(f'non-finite loss/grad at step {step}: {loss_acc} {gn}')
            opt.step()
            opt.zero_grad(set_to_none=True)
            step += 1
            logf.write(json.dumps({'step': step, 'epoch': epoch + 1, 'pos': s + 1, 'loss': loss_acc, 'grad_norm': gn, 'lr': lr, 'n_examples': len(grp),
                                   'elapsed_s': time.time() - t0, 'peak_mem_gb': torch.cuda.max_memory_allocated() / 2 ** 30, 'batch_ids': actual,
                                   'batch_token_sha': th.hexdigest()[:24], 'rng_before': rng_before, 'opt_step_before': opt_before}) + '\n')
            logf.flush()
            saved = False
            if step % a.ckpt_every == 0 and (s + 1) < spe:
                save_ckpt(epoch, s + 1)
                saved = True
            if a.stop_after_step is not None and step == a.stop_after_step:
                if not saved:
                    raise RuntimeError('--stop-after-step must coincide with a regular mid-epoch checkpoint step')
                print('test stop after mid-epoch checkpoint', flush=True)
                os._exit(5)
        del dl, it
        e = epoch + 1
        if e in save_epochs or e == a.epochs:
            edir = os.path.join(a.run_dir, f'epoch_{e:02d}')
            os.makedirs(edir, exist_ok=True)
            T.save_adapter(torch, model, os.path.join(edir, 'adapter.pt'), {'epoch': e, 'step': step, 'train_digest': tdig})
        save_ckpt(e, 0)
        if a.stop_after_epoch_ckpt == e:
            print('test stop after epoch ckpt', flush=True)
            os._exit(3)
        if e in save_epochs:
            do_val(e)
        pos0 = 0
    print('training complete', flush=True)


def example_text(row):
    return D.target_text(row['category'], [g['yxyx_norm'] for g in row['gt']])


if __name__ == '__main__':
    main()
