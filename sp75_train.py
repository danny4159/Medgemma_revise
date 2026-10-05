"""iter_075 MedGemma 3영상 Pfirrmann grade 직접 LoRA SFT (F: 전체 slice+ROI 표시 / R: ROI crop). 표준 SFT, 새 loss 없음.

g71_train.py의 checkpoint/재개/상태 digest 패턴을 3영상 grade task로 인자화했다. 기준 loss는 공식 forward logits의 float32 CE 합이며
시작 시 공식 labels loss와 대조한다(허용 오차 확대 없음: 상대 1e-6). 학습 ID는 sp75_data manifest의 T24 supervised(ordinal 1,3,5)만, validation은 V8 supervised만.
사용: python sp75_train.py --run-dir D --variant F|R --lr 2e-4 --epochs 16 --gpu 0 [--deterministic]

iter_077 변경: (4) --deterministic는 use_deterministic_algorithms만 켜고 SDPA backend는 기본값(iter_076의 math-only는 peak 21.3GiB; sp77_sdpa_probe로 반복 bit 일치 확인).
(5) 재개 시 checkpoint 이후 기록된 step/checkpoint 로그를 train_log.uncommitted.jsonl로 옮겨 보존하고 train_log.jsonl은 committed 상태만 남긴다(중복 step 없음).
iter_076 변경: (1) loss gate는 PASS/FAIL 상태·유한 수치·상대오차·token 수·모델/입력/코드 provenance를 모두 검사하며 실패·손상·불일치 파일은 학습을 차단한다
(재실행으로 우회 불가). (2) 비LoRA parameter 동결을 객체 단위(수·numel·byte>0, optimizer 미포함, 시작/종료 전체 byte digest 일치)로 검사한다.
(3) --deterministic: 결정적 kernel(기술 검사용; config digest에 포함).
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


GATE_REL_TOL = 1e-6


def gate_provenance(variant, train_rows, tin, code):
    return {'model_revision': generate.MODEL_REVISION, 'variant': variant, 'train_inputs_digest': tin, 'row_id': train_rows[0]['id'], 'code': code,
            'prompt_sha256': hashlib.sha256(V.PROMPTS[variant].encode()).hexdigest()}


def validate_gate(gate, prov):
    """loss gate 기록 검증. returns 문제 목록(빈 리스트면 PASS)."""
    bad = []
    if not isinstance(gate, dict):
        return ['gate is not a dict']
    if gate.get('status') != 'PASS':
        bad.append(f"status={gate.get('status')!r}")
    keys = ('official_loss', 'logits_f32_ce_mean', 'loss_sum_over_n')
    vals = [gate.get(k) for k in keys]
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in vals):
        bad.append('non-finite or missing loss values')
    else:
        rel = abs(vals[0] - vals[2]) / max(abs(vals[0]), 1e-30)
        if rel > GATE_REL_TOL:
            bad.append(f'relative diff {rel} > {GATE_REL_TOL}')
        if abs(gate.get('rel_diff_official_vs_loss_sum', -1) - rel) > 1e-12:
            bad.append('stored rel_diff inconsistent with stored losses')
    n1, n2 = gate.get('n_valid_tokens'), gate.get('n_valid_independent')
    if not (isinstance(n1, int) and n1 > 0 and n1 == n2):
        bad.append(f'valid token counts {n1} vs {n2}')
    if gate.get('provenance') != prov:
        bad.append('provenance (model/inputs/code/prompt) differs from current run')
    return bad


def quarantine_uncommitted(run_dir, ckpt_step, logf):
    """checkpoint step 이후의 학습 step·checkpoint 로그 행(미커밋 구간)을 보존 파일로 옮기고 train_log.jsonl을 committed 상태로 되돌린다.
    다른 event(val_ce 등)는 유지한다. checkpoint step에 해당하는 committed 기록이 없으면 중단한다."""
    path = os.path.join(run_dir, 'train_log.jsonl')
    logf.flush()
    lines = [l for l in open(path).read().splitlines() if l.strip()]
    recs = [json.loads(l) for l in lines]
    if ckpt_step > 0 and not any(r.get('event') == 'checkpoint' and r.get('step') == ckpt_step for r in recs):
        raise RuntimeError(f'no committed checkpoint log record for step {ckpt_step}')
    keep, dropped = [], []
    for l, r in zip(lines, recs):
        late = r.get('step', 0) > ckpt_step and ('loss' in r or r.get('event') == 'checkpoint')
        (dropped if late else keep).append(l)
    steps = [json.loads(l)['step'] for l in keep if 'loss' in json.loads(l)]
    if len(steps) != len(set(steps)) or steps != list(range(1, len(steps) + 1)):
        raise RuntimeError(f'committed log steps not contiguous/unique before resume: {steps}')
    if dropped:
        with open(os.path.join(run_dir, 'train_log.uncommitted.jsonl'), 'a') as f:
            f.write(json.dumps({'event': 'quarantine', 'ts': time.time(), 'ckpt_step': ckpt_step, 'n_rows': len(dropped)}) + '\n')
            f.write('\n'.join(dropped) + '\n')
        tmp = path + '.tmp'
        open(tmp, 'w').write('\n'.join(keep) + ('\n' if keep else ''))
        os.replace(tmp, path)
    return len(dropped)


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
    ap.add_argument('--allow-uncommitted-stop', action='store_true', help='시험 전용: --stop-after-step을 checkpoint 아닌 step에서도 허용(미커밋 로그 구간 재현)')
    ap.add_argument('--stop-after-epoch-ckpt', type=int, default=None)
    ap.add_argument('--train-split', default='T24')
    ap.add_argument('--val-split', default='V8')
    ap.add_argument('--deterministic', action='store_true', help='결정적 kernel (기술 검사용)')
    a = ap.parse_args()
    if a.deterministic:
        os.environ['CUBLAS_WORKSPACE_CONFIG'] = ':4096:8'
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
    code = {f: file_sha(f) for f in CODE}
    tin, vin = inputs_digest(train_rows, a.variant), inputs_digest(val_rows, a.variant)
    prov = gate_provenance(a.variant, train_rows, tin, code)
    gate_path = os.path.join(a.run_dir, 'loss_gate.json')
    if os.path.exists(gate_path):   # 모델 적재 전에 기존 gate를 검증한다. 실패·손상·불일치면 학습하지 않는다.
        try:
            problems = validate_gate(json.load(open(gate_path)), prov)
        except Exception as ex:
            problems = [f'unreadable gate: {ex!r}']
        if problems:
            sys.exit(f'existing loss_gate.json blocks training: {problems}')
    if a.deterministic:
        T.set_deterministic_algos(torch)
    T.seed_all(torch, a.seed)
    _, proc, model = generate.load_model()
    names = lora.apply_lora(model, CFG['r'], CFG['alpha'], CFG['dropout'], seed=a.seed)
    tok = proc.tokenizer
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False})
    model.config.use_cache = False
    params = list(lora.lora_params(model).values())
    init_digest = lora.state_digest(lora.lora_state_dict(model))
    cfg = dict(CFG, lr=a.lr, seed=a.seed, variant=a.variant, microbatch=1, n_train=len(train_rows), n_val=len(val_rows), model_revision=generate.MODEL_REVISION,
               n_lora_targets=len(names), n_trainable=sum(p.numel() for p in params), train_inputs_digest=tin, val_inputs_digest=vin, init='base',
               init_adapter_digest=init_digest, save_epochs=sorted(save_epochs), code=code, deterministic=bool(a.deterministic), deterministic_mode='use_deterministic_algorithms+default_sdpa' if a.deterministic else None, manifest_sha256=file_sha(f'{D.DATA}/manifest.json'))
    tdig = hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()
    cfg_path = os.path.join(a.run_dir, 'train_config.json')
    if os.path.exists(cfg_path):
        if json.load(open(cfg_path))['train_digest'] != tdig:
            sys.exit('train config (LR/inputs/code/manifest) differs from existing run-dir; refusing to resume')
    else:
        json.dump({'train_digest': tdig, 'config': cfg, 'env': generate.env_info(torch, proc, model)}, open(cfg_path, 'w'), indent=1, default=str)
    # 공식 loss 대조 gate (이전 CE 실패를 허용 오차로 숨기지 않는다). 기록은 원자적으로 저장하고 존재만으로 통과시키지 않는다.
    if not os.path.exists(gate_path):
        ex = V.build_example(proc, V.load_images(train_rows[0]['inputs'][a.variant]), V.PROMPTS[a.variant], str(train_rows[0]['grade']))
        model.eval()
        with torch.no_grad():
            chk = V.check_loss(torch, model, V.to_cuda(V.collate([ex], tok.pad_token_id)))
        model.train()
        chk['rel_diff_official_vs_loss_sum'] = abs(chk['official_loss'] - chk['loss_sum_over_n']) / max(abs(chk['official_loss']), 1e-30)
        chk['provenance'] = prov
        chk['status'] = 'PASS'
        chk['status'] = 'PASS' if not validate_gate(dict(chk), prov) else 'FAIL'
        T.atomic_json(chk, gate_path)
        if chk['status'] != 'PASS':
            sys.exit(f'official loss gate failed {chk}')
    opt = torch.optim.AdamW(params, lr=a.lr, betas=tuple(CFG['betas']), eps=CFG['eps'], weight_decay=CFG['weight_decay'])
    split = lora.split_report(model, params)
    if split['non_lora_requires_grad'] or split['lora_requires_grad_false'] or split['optimizer_contains_non_lora'] or not split['optimizer_lora_covered']:
        sys.exit(f'freeze check failed: {split}')
    frz0, n0, b0 = lora.exact_digest(model)
    fz_path = os.path.join(a.run_dir, 'freeze_start.json')
    if os.path.exists(fz_path):
        if json.load(open(fz_path))['non_lora_exact_digest'] != frz0:
            sys.exit('non-LoRA parameters differ from the digest recorded at run start (frozen base changed across resume)')
    else:
        T.atomic_json({'non_lora_exact_digest': frz0, 'n_params': n0, 'n_bytes': b0, 'split': split}, fz_path)
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
        n_q = quarantine_uncommitted(a.run_dir, step, logf)
        logf.close()
        logf = open(os.path.join(a.run_dir, 'train_log.jsonl'), 'a')   # closure(log_event)가 같은 변수를 참조
        restored = T.live_digests(torch, model, opt)
        if restored != blob['digests']:
            sys.exit(f'restored state != saved checkpoint {restored} vs {blob["digests"]}')
        log_event(event='resume', step=step, epoch=epoch0, pos=pos0, restored_equals_saved=True, stale_lock_reclaimed=bool(reclaimed), quarantined_rows=n_q)
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
                                   'elapsed_s': time.time() - t0, 'peak_mem_gb': torch.cuda.max_memory_allocated() / 2 ** 30, 'peak_reserved_gb': torch.cuda.max_memory_reserved() / 2 ** 30, 'batch_ids': actual,
                                   'batch_token_sha': th.hexdigest()[:24], 'rng_before': rng_before, 'opt_step_before': opt_before}) + '\n')
            logf.flush()
            saved = False
            if step % a.ckpt_every == 0 and (s + 1) < spe:
                save_ckpt(epoch, s + 1)
                saved = True
            if a.stop_after_step is not None and step == a.stop_after_step:
                if not saved and not a.allow_uncommitted_stop:
                    raise RuntimeError('--stop-after-step must coincide with a regular mid-epoch checkpoint step')
                print('test stop after step (checkpoint saved: %s)' % saved, flush=True)
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
    frz1, n1, b1 = lora.exact_digest(model)
    if frz1 != frz0:
        raise RuntimeError('non-LoRA parameters changed during training')
    T.atomic_json({'non_lora_exact_digest': frz1, 'n_params': n1, 'n_bytes': b1, 'equals_start': True, 'step': step}, os.path.join(a.run_dir, 'freeze_end.json'))
    print('training complete', flush=True)


if __name__ == '__main__':
    main()
