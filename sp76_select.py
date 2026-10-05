"""iter_076 V8 기반 선택·연장·최종 checkpoint 규칙 (원 iter_075 계획 규칙을 결과 전에 코드로 고정).

규칙(원 계획 그대로):
- epoch16에서 방식(F/R)별로 V8 primary(class-standardized MAE)가 가장 좋은 LR 하나를 선택. 동률은 V8 CE, 더 이른 checkpoint, 작은 LR 순.
- 선택 trajectory의 epoch8->16에서 V8 CE가 5% 이상 감소(상대)하거나 primary MAE가 0.10 이상 개선되면 epoch32까지 한 번 연장하고 epoch32만 추가 평가.
- 최종 checkpoint(사전 고정 해석): 선택 LR trajectory에서 평가된 epoch {16, 32(연장 시)} 중 V8 primary 최소, 동률은 V8 CE, 더 이른 epoch. epoch8은 추세 확인용이며 최종 후보가 아니다.
E24는 어떤 규칙에도 사용하지 않는다. 결과 파일은 존재하면 중단(원자적 저장).
"""
import argparse, glob, json, os, sys

import numpy as np

import sp75_data as D
import sp75_metrics as M
import sp75_vlm as V

OUT = 'results/iter_076'
LRS = ('2e-5', '2e-4')
CE_REL_DROP = 0.05
PRIMARY_GAIN = 0.10
EPS = 1e-12


def traj_dir(v, lr):
    return f'{OUT}/train/{v}_lr{lr}'


def gen_dir(v, lr, ep):
    return f'{OUT}/gen/V8/{v}_lr{lr}_ep{ep:02d}'


def pick_lr(cands):
    """cands: [{'lr': '2e-5', 'primary': x, 'ce': y}] (epoch16). 최소 primary -> 최소 CE -> 작은 LR."""
    return sorted(cands, key=lambda c: (round(c['primary'], 12), round(c['ce'], 12), float(c['lr'])))[0]['lr']


def needs_extension(m8, m16):
    """m8/m16: {'primary','ce'}. CE 상대 감소 >= 5% 또는 primary 개선 >= 0.10 (경계 포함)."""
    ce_drop = (m8['ce'] - m16['ce']) / m8['ce']
    gain = m8['primary'] - m16['primary']
    return bool(ce_drop >= CE_REL_DROP - EPS or gain >= PRIMARY_GAIN - EPS), {'ce_rel_drop_8_to_16': ce_drop, 'primary_gain_8_to_16': gain}


def final_epoch(evals):
    """evals: {epoch: {'primary','ce'}} (16, 선택적으로 32). 최소 primary -> 최소 CE -> 이른 epoch."""
    cand = {e: m for e, m in evals.items() if e >= 16}
    return sorted(cand, key=lambda e: (round(cand[e]['primary'], 12), round(cand[e]['ce'], 12), e))[0]


def v8_rows():
    man = D.load_manifest()
    return sorted([r for r in man['rows'] if r['split'] == 'V8' and r['position_set'] == 'supervised' and not r['excluded']], key=lambda r: (int(r['patient']), r['ordinal']))


def metrics(v, lr, ep, rows=None):
    """한 (방식, LR, epoch)의 V8 지표. 생성 출력 완전성·provenance(adapter digest·입력 hash)와 val_ce.json의 train_digest를 확인한다."""
    import torch  # adapter 로드용
    rows = rows or v8_rows()
    edir = f'{traj_dir(v, lr)}/epoch_{ep:02d}'
    ad = torch.load(f'{edir}/adapter.pt', map_location='cpu', weights_only=True)
    vc = json.load(open(f'{edir}/val_ce.json'))
    cfg = json.load(open(f'{traj_dir(v, lr)}/train_config.json'))
    if vc['adapter_digest'] != ad['digest'] or vc['train_digest'] != cfg['train_digest'] or ad['train_digest'] != cfg['train_digest']:
        raise RuntimeError(f'{edir}: adapter/val_ce/train_config provenance mismatch')
    recs = {}
    for f in sorted(glob.glob(f'{gen_dir(v, lr, ep)}/gen_worker*.jsonl')):
        for ln in open(f):
            if ln.strip():
                r = json.loads(ln)
                if r['id'] in recs:
                    raise RuntimeError(f'duplicate {r["id"]}')
                recs[r['id']] = r
    want = [r['id'] for r in rows]
    if set(recs) != set(want):
        raise RuntimeError(f'{gen_dir(v, lr, ep)}: id set differs (missing {sorted(set(want) - set(recs))[:3]})')
    pred = []
    for r in rows:
        x = recs[r['id']]
        if x['variant'] != v or x['adapter_digest'] != ad['digest'] or x['input_pixel_sha256'] != [e['pixel_sha256_padded'] for e in r['inputs'][v]]:
            raise RuntimeError(f'provenance mismatch {r["id"]}')
        pred.append(V.parse(x['text']) if x['ended_eos'] else None)
    g = [r['grade'] for r in rows]
    cs, nc = M.class_std_mae(g, pred)
    if nc != 5:
        raise RuntimeError('V8 class missing')
    return {'variant': v, 'lr': lr, 'epoch': ep, 'primary': cs, 'ce': vc['val_ce'], 'mae': float(M.abs_err(g, pred).mean()), 'n_invalid': sum(p is None for p in pred),
            'adapter_digest': ad['digest'], 'n': len(rows)}


def atomic_write(obj, path):
    if os.path.exists(path):
        sys.exit(f'{path} exists')
    tmp = path + '.tmp'
    json.dump(obj, open(tmp, 'w'), indent=1)
    os.replace(tmp, path)


def cmd_select_v8(a):
    rows = v8_rows()
    res = {'milestones': {}, 'selected': {}, 'extend': {}}
    for v in ('F', 'R'):
        ms = {lr: {ep: metrics(v, lr, ep, rows) for ep in (8, 16)} for lr in LRS}
        res['milestones'][v] = ms
        lr = pick_lr([{'lr': lr, 'primary': ms[lr][16]['primary'], 'ce': ms[lr][16]['ce']} for lr in LRS])
        ext, info = needs_extension(ms[lr][8], ms[lr][16])
        res['selected'][v] = lr
        res['extend'][v] = {'extend_to_32': ext, **info}
    atomic_write(res, f'{OUT}/select_v8.json')
    print(json.dumps({'selected': res['selected'], 'extend': res['extend']}, indent=1))


def cmd_select_final(a):
    s8 = json.load(open(f'{OUT}/select_v8.json'))
    rows = v8_rows()
    res = {'final': {}}
    for v in ('F', 'R'):
        lr = s8['selected'][v]
        ev = {16: s8['milestones'][v][lr]['16']}
        if s8['extend'][v]['extend_to_32']:
            ev[32] = metrics(v, lr, 32, rows)
        ep = final_epoch({e: m for e, m in ev.items()})
        res['final'][v] = {'lr': lr, 'epoch': ep, 'adapter_dir': f'{traj_dir(v, lr)}/epoch_{ep:02d}', 'adapter_digest': ev[ep]['adapter_digest'], 'evaluated': {str(e): m for e, m in ev.items()}}
    atomic_write(res, f'{OUT}/select_final.json')
    print(json.dumps({k: {x: y for x, y in v.items() if x != 'evaluated'} for k, v in res['final'].items()}, indent=1))


def cmd_lock_spec(a):
    """eval lock 명세 작성: 최종 F/R adapter, base F/R, C/H 선택 근거. (실제 lock은 sp75_eval.py lock --spec)."""
    fin = json.load(open(f'{OUT}/select_final.json'))['final']
    csel = json.load(open('results/iter_075/C/selection.json'))['selected']
    vlm = {'F_base': {'variant': 'F', 'adapter_dir': None, 'adapter_digest': None, 'dir': f'{OUT}/gen/E24/F_base'},
           'R_base': {'variant': 'R', 'adapter_dir': None, 'adapter_digest': None, 'dir': f'{OUT}/gen/E24/R_base'}}
    extra = [f'{OUT}/select_v8.json', f'{OUT}/select_final.json', 'results/iter_075/data/manifest.json', 'results/iter_075/env_record.json', 'results/iter_075/C/selection.json',
             'results/iter_075/H/selection.json', 'results/iter_075/H/features_T24_V8.json',
             f"results/iter_075/C/lr{csel['lr']}/epoch_{csel['epoch']:02d}.pt"]
    for v in ('F', 'R'):
        f = fin[v]
        vlm[f'{v}_adapted'] = {'variant': v, 'adapter_dir': f['adapter_dir'], 'adapter_digest': f['adapter_digest'], 'dir': f'{OUT}/gen/E24/{v}_adapted'}
        extra += [f"{f['adapter_dir']}/adapter.pt", f"{f['adapter_dir']}/val_ce.json", f"{traj_dir(v, f['lr'])}/train_config.json"]
    code = ['sp75_pipeline.py', 'sp76_select.py', 'sp76_cpred.py', 'sp75_train.py', 'sp75_c.py', 'sp75_h.py', 'sp67_data.py', 'g71_data.py', 'rsna_diag/generate.py', 'rsna_diag/lora.py']
    spec = {'vlm': vlm, 'json_systems': {'C': f'{OUT}/pred/pred_C_E24.json', 'H': f'{OUT}/pred/pred_H_E24.json'}, 'extra_files': extra + code,
            'selection': {'final': {v: {k: fin[v][k] for k in ('lr', 'epoch', 'adapter_digest')} for v in fin}, 'C': csel}}
    os.makedirs(f'{OUT}/eval', exist_ok=True)
    atomic_write(spec, f'{OUT}/eval/lock_spec.json')
    print('wrote lock spec')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('c', choices=['select_v8', 'select_final', 'lock_spec'])
    a = ap.parse_args()
    {'select_v8': cmd_select_v8, 'select_final': cmd_select_final, 'lock_spec': cmd_lock_spec}[a.c](a)
