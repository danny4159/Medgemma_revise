"""iter_075 MedGemma 3영상 Pfirrmann grade 직접 LoRA SFT (F: 전체 slice+ROI 표시 / R: ROI crop). 표준 SFT, 새 loss 없음.

g71_train.py의 checkpoint/재개/상태 digest 패턴을 3영상 grade task로 인자화했다. 기준 loss는 공식 forward logits의 float32 CE 합이며
시작 시 공식 labels loss와 대조한다(허용 오차 확대 없음: 상대 1e-6). 학습 ID는 sp75_data manifest의 T24 supervised(ordinal 1,3,5)만, validation은 V8 supervised만.
사용: python sp75_train.py --run-dir D --variant F|R --lr 2e-4 --epochs 16 --gpu 0
"""
import argparse, hashlib, json, math, os, sys, time

import numpy as np

import sp75_data as D
import sp75_vlm as V
from rsna_diag import generate, lora, queue_lock
from rsna_diag import train as T

HORIZON = 32
CFG = {'r': 16, 'alpha': 32, 'dropout': 0.05, 'weight_decay': 0.01, 'betas': [0.9, 0.999], 'eps': 1e-8, 'grad_clip': 1.0, 'warmup_frac': 0.05, 'eff_batch': 8,
       'horizon_epochs': HORIZON, 'schedule': 'linear warmup 5% then cosine to 0 over 32-epoch horizon', 'answer': 'single digit 1-5',
       'prompts': {k: hashlib.sha256(v.encode()).hexdigest()[:16] for k, v in V.PROMPTS.items()}}
CODE = ['sp75_train.py', 'sp75_vlm.py', 'sp75_data.py', 'rsna_diag/train.py', 'rsna_diag/lora.py', 'rsna_diag/generate.py', 'rsna_diag/queue_lock.py']


def lr_at(step, spe, peak, horizon=HORIZON, warm_frac=0.05):
    total = spe * horizon
    warm = math.ceil(warm_frac * total)
    if step < warm:
        return peak * (step + 1) / warm
    return 0.5 * peak * (1 + math.cos(math.pi * (step - warm) / (total - warm)))


def file_sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def load_rows(split):
    man = D.load_manifest()
    rows = [r for r in man['rows'] if r['split'] == split and r['position_set'] == 'supervised' and not r['excluded']]
    rows.sort(key=lambda r: (int(r['patient']), r['ordinal']))
    for r in rows:
        assert r['ordinal'] in D.SUPERVISED and r['grade'] in (1, 2, 3, 4, 5)
    return rows


class DS:
    def __init__(self, proc, rows, order, variant):
        self.proc, self.rows, self.order, self.variant = proc, rows, order, variant

    def __len__(self):
        return len(self.order)

    def __getitem__(self, k):
        r = self.rows[self.order[k]]
        ims = V.load_images(r['inputs'][self.variant])
        ex = V.build_example(self.proc, ims, V.PROMPTS[self.variant], str(r['grade']))
        ex['sample_pos'] = int(k)
        return ex


def inputs_digest(rows, variant):
    return hashlib.sha256(json.dumps([(r['id'], r['grade'], [(e['file_sha256'], e['pixel_sha256_padded']) for e in r['inputs'][variant]]) for r in rows], sort_keys=True).encode()).hexdigest()


def val_ce(torch, model, proc, rows, variant):
    model.eval()
    tot, n = 0.0, 0
    with torch.no_grad():
        for r in rows:
            ims = V.load_images(r['inputs'][variant])
            ex = V.build_example(proc, ims, V.PROMPTS[variant], str(r['grade']))
            b = V.to_cuda(V.collate([ex], proc.tokenizer.pad_token_id))
            s, c = V.loss_sum(torch, model, b)
            tot += float(s)
            n += c
    return tot / n, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-dir', required=True)
    ap.add_argument('--variant', choices=['F', 'R'], required=True)
    ap.add_argument('--lr', type=float, required=True)
    ap.add_argument('--seed', type=int, default=17)
    ap.add_argument('--epochs', type=int, required=True)
    ap.add_argument('--save-epochs', default='8,16,32', help='adapter 저장 및 validation CE epoch')
    ap.add_argument('--ckpt-every', type=int, default=3)
    ap.add_argument('--workers', type=int, default=2)
    ap.add_argument('--gpu', default=None)
    ap.add_argument('--stop-after-step', type=int, default=None)
    ap.add_argument('--stop-after-epoch-ckpt', type=int, default=None)
    ap.add_argument('--train-split', default='T24')
    ap.add_argument('--val-split', default='V8')
    a = ap.parse_args()
    if a.gpu is not None:
        inh = os.environ.get('CUDA_VISIBLE_DEVICES', '').split(',')
        if a.gpu not in inh:
            sys.exit(f'gpu {a.gpu} not in inherited CUDA_VISIBLE_DEVICES {inh}')
        os.environ['CUDA_VISIBLE_DEVICES'] = a.gpu
    if a.epochs > HORIZON:
        sys.exit('epochs exceeds fixed horizon')
    os.makedirs(a.run_dir, exist_ok=True)
    lk, own, rec = queue_lock.try_lock(os.path.join(os.path.realpath(a.run_dir), 'train.lock'), queue_lock.my_info(role='sp75_train'))
    if lk is None:
        sys.exit(f'run-dir owned by live process {own}')
    T.LOCK_FD[0] = lk.fd
    try:
        run(a, rec)
    finally:
        lk.release()


def run(a, reclaimed):
    import torch
    train_rows, val_rows = load_rows(a.train_split), load_rows(a.val_split)
    assert not {r['patient'] for r in train_rows} & {r['patient'] for r in val_rows}
    save_epochs = {int(x) for x in a.save_epochs.split(',')}
    T.seed_all(torch, a.seed)
    _, proc, model = generate.load_model()
    names = lora.apply_lora(model, CFG['r'], CFG['alpha'], CFG['dropout'], seed=a.seed)
    tok = proc.tokenizer
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False})
    model.config.use_cache = False
    params = list(lora.lora_params(model).values())
    init_digest = lora.state_digest(lora.lora_state_dict(model))
    tin, vin = inputs_digest(train_rows, a.variant), inputs_digest(val_rows, a.variant)
    code = {f: file_sha(f) for f in CODE}
    cfg = dict(CFG, lr=a.lr, seed=a.seed, variant=a.variant, microbatch=1, n_train=len(train_rows), n_val=len(val_rows), model_revision=generate.MODEL_REVISION,
               n_lora_targets=len(names), n_trainable=sum(p.numel() for p in params), train_inputs_digest=tin, val_inputs_digest=vin, init='base',
               init_adapter_digest=init_digest, save_epochs=sorted(save_epochs), code=code, manifest_sha256=file_sha(f'{D.DATA}/manifest.json'))
    tdig = hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()
    cfg_path = os.path.join(a.run_dir, 'train_config.json')
    if os.path.exists(cfg_path):
        if json.load(open(cfg_path))['train_digest'] != tdig:
            sys.exit('train config (LR/inputs/code/manifest) differs from existing run-dir; refusing to resume')
    else:
        json.dump({'train_digest': tdig, 'config': cfg, 'env': generate.env_info(torch, proc, model)}, open(cfg_path, 'w'), indent=1, default=str)
    # 공식 loss 대조 gate (이전 CE 실패를 허용 오차로 숨기지 않는다)
    gate_path = os.path.join(a.run_dir, 'loss_gate.json')
    if not os.path.exists(gate_path):
        ex = V.build_example(proc, V.load_images(train_rows[0]['inputs'][a.variant]), V.PROMPTS[a.variant], str(train_rows[0]['grade']))
        model.eval()
        with torch.no_grad():
            chk = V.check_loss(torch, model, V.to_cuda(V.collate([ex], tok.pad_token_id)))
        model.train()
        rel = abs(chk['official_loss'] - chk['loss_sum_over_n']) / abs(chk['official_loss'])
        chk['rel_diff_official_vs_loss_sum'] = rel
        json.dump(chk, open(gate_path, 'w'))
        if rel > 1e-6 or chk['n_valid_tokens'] != chk['n_valid_independent']:
            sys.exit(f'official loss gate failed {chk}')
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
            sys.exit(f'restored state != saved checkpoint {restored} vs {blob["digests"]}')
        log_event(event='resume', step=step, epoch=epoch0, pos=pos0, restored_equals_saved=True, stale_lock_reclaimed=bool(reclaimed))
        print(f'resumed step={step} epoch={epoch0} pos={pos0}', flush=True)
    t0 = time.time()

    def do_val(e):
        edir = os.path.join(a.run_dir, f'epoch_{e:02d}')
        vm = os.path.join(edir, 'val_ce.json')
        ad = torch.load(os.path.join(edir, 'adapter.pt'), map_location='cpu', weights_only=True)
        if lora.state_digest(ad['state']) != ad['digest'] or ad['train_digest'] != tdig:
            raise RuntimeError('epoch adapter digest/provenance mismatch')
        if os.path.exists(vm):
            old = json.load(open(vm))
            if old['train_digest'] != tdig or old['adapter_digest'] != ad['digest'] or old['val_inputs_digest'] != vin:
                raise RuntimeError(f'existing val_ce for epoch {e} does not match run')
            return
        rng_b, pre = T.rng_state(torch), T.live_digests(torch, model, opt)
        snap = lora.lora_state_dict(model)
        lora.load_lora_state(model, ad['state'])
        v, n = val_ce(torch, model, proc, val_rows, a.variant)
        lora.load_lora_state(model, snap)
        model.train()
        T.set_rng_state(torch, rng_b)
        if T.live_digests(torch, model, opt) != pre:
            raise RuntimeError('validation changed training state')
        T.atomic_json({'epoch': e, 'val_ce': v, 'val_tokens': n, 'adapter_digest': ad['digest'], 'train_digest': tdig, 'val_inputs_digest': vin, 'step': e * spe}, vm)
        log_event(event='val_ce', epoch=e, val_ce=v, state_unchanged=True)
        print(f'epoch {e}: val_ce {v:.4f} ({n} tokens)', flush=True)

    for e in range(1, epoch0 + 1):  # 저장은 됐으나 val_ce가 없는 epoch 복구
        if e in save_epochs and os.path.exists(os.path.join(a.run_dir, f'epoch_{e:02d}', 'adapter.pt')):
            do_val(e)
    for epoch in range(epoch0, a.epochs):
        rng = np.random.default_rng(a.seed * 1000 + epoch)
        order = rng.permutation(n_tr)
        start = pos0 if epoch == epoch0 else 0
        ds = DS(proc, train_rows, order, a.variant)
        idx = list(range(start * CFG['eff_batch'], n_tr))
        g = torch.Generator()
        g.manual_seed(a.seed * 1000 + epoch)
        dl = torch.utils.data.DataLoader(torch.utils.data.Subset(ds, idx), batch_size=1, shuffle=False, num_workers=a.workers,
                                         collate_fn=lambda ex: V.collate(ex, tok.pad_token_id), prefetch_factor=2 if a.workers else None,
                                         worker_init_fn=T.close_lock_fd, generator=g)
        model.train()
        it = iter(dl)
        for s in range(start, spe):
            grp = order[s * CFG['eff_batch']:(s + 1) * CFG['eff_batch']]
            tot_tok = 2 * len(grp)  # 각 예제 label = digit + <end_of_turn> (build_example이 보장; 아래에서 실제 수와 대조)
            lr = lr_at(step, spe, a.lr)
            for gp in opt.param_groups:
                gp['lr'] = lr
            rng_before, opt_before = T.rng_digest(torch), T.opt_step_count(opt)
            loss_acc, ntok, seen, th = 0.0, 0, [], hashlib.sha256()
            for _ in range(len(grp)):
                b = next(it)
                seen += b.pop('sample_pos').tolist()
                th.update(T.batch_token_digest(b).digest())
                b = V.to_cuda(b)
                ls, nt = V.loss_sum(torch, model, b)
                (ls / tot_tok).backward()
                loss_acc += float(ls.detach()) / tot_tok
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
            print('test stop after epoch ckpt (before validation)', flush=True)
            os._exit(3)
        if e in save_epochs:
            do_val(e)
        pos0 = 0
    print('training complete', flush=True)


if __name__ == '__main__':
    main()
