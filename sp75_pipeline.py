"""iter_076 실행 orchestration (원 iter_075 파이프라인의 완료 흐름 연결판).

단계 CLI (각 단계는 이전 단계 산출물·상태를 검증하고, 모든 새 결과는 results/iter_076 아래에만 쓴다):
  train     : F/R x LR{2e-5,2e-4} 네 trajectory를 --epochs(기본16)까지 학습 (epoch8·16에서 V8 val CE)
  gen_v8    : milestone adapter의 V8 supervised 24요청 생성 (--epochs 8,16 | 32 --variants F,R)
  select_v8 : (sp76_select.py) LR 선택 + 연장 여부 결정
  extend    : 연장 대상 trajectory를 32 epoch까지 학습 -> gen_v8 --epochs 32 -> select_final
  lock      : 첫 E24 출력 전에 F/R/C/H 선택·코드·입력 hash를 eval_lock.json에 고정
  gen_e24   : base/adapted F/R E24 118요청 생성 + C/H 예측 (lock 필수)
  seal / eval / verify / cost : 평가 흐름 (sp75_eval.py, sp75_verify.py, sp75_cost.py)
GPU 배정은 상속된 CUDA_VISIBLE_DEVICES 안에서만, 시작 직전 nvidia-smi 여유가 (예상 peak + worker당 2GiB)보다 작으면 대기한다.
이미 실행 중인 같은 run-dir은 train.lock/worker lock이 거부한다. 모든 subprocess는 ledger(JSONL)에 명령·GPU·rc·wall·peak 점유를 남긴다.
자식이 비정상 종료하거나 출력이 불완전하면 비정상 종료한다.
"""
import argparse, json, os, subprocess, sys, time

OUT = 'results/iter_076'
LEDGER = f'{OUT}/ledger.jsonl'
TRAIN = f'{OUT}/train'
GEN = f'{OUT}/gen'
LRS = {'F': ('2e-5', '2e-4'), 'R': ('2e-5', '2e-4')}
LOCK = f'{OUT}/eval/eval_lock.json'


def gpus():
    return os.environ.get('CUDA_VISIBLE_DEVICES', '0,1').split(',')


def gpu_state():
    out = subprocess.check_output(['nvidia-smi', '--query-gpu=index,uuid,memory.used,memory.total', '--format=csv,noheader,nounits']).decode().strip().splitlines()
    res = {}
    for ln in out:
        i, u, used, tot = [x.strip() for x in ln.split(',')]
        res[i] = {'free': int(tot) - int(used), 'used': int(used), 'uuid': u}
    return res


def run_jobs(jobs, per_gpu, peak_gb, tag):
    """jobs: [{'name','cmd'(--gpu 제외),'log'}]. 각 GPU에 최대 per_gpu개 동시, 메모리 여유 확인. 실패하면 SystemExit."""
    g = gpus()
    running, pending, results = {}, list(jobs), []
    peaks = {}
    while pending or running:
        for k, (p, j, gid, t0) in list(running.items()):
            rc = p.poll()
            if rc is not None:
                rec = {'tag': tag, 'name': j['name'], 'cmd': j['cmd'], 'gpu': gid, 'gpu_uuid': gpu_state().get(gid, {}).get('uuid'), 'rc': rc, 'wall_s': time.time() - t0,
                       'ts_end': time.time(), 'peak_gpu_used_mib_sampled': peaks.get(k), 'per_gpu': per_gpu, 'est_peak_gb': peak_gb}
                open(LEDGER, 'a').write(json.dumps(rec) + '\n')
                results.append(rec)
                del running[k]
        st = gpu_state()
        for k, (p, j, gid, t0) in running.items():
            peaks[k] = max(peaks.get(k, 0), st[gid]['used'])
        for gid in g:
            if not pending:
                break
            n_on = sum(1 for (_, _, gg, _) in running.values() if gg == gid)
            if n_on >= per_gpu:
                continue
            if st[gid]['free'] < (peak_gb + 2) * 1024:
                continue
            j = pending.pop(0)
            os.makedirs(os.path.dirname(j['log']), exist_ok=True)
            p = subprocess.Popen(j['cmd'] + ['--gpu', gid], stdout=open(j['log'], 'a'), stderr=subprocess.STDOUT)
            running[j['name']] = (p, j, gid, time.time())
            time.sleep(45)   # 메모리 점유가 올라올 시간을 준다 (다음 시작 판단 전)
            st = gpu_state()
        time.sleep(10)
    bad = [r for r in results if r['rc'] != 0]
    if bad:
        raise SystemExit(f'jobs failed: {[(r["name"], r["rc"]) for r in bad]}')
    return results


def traj_dir(v, lr):
    return f'{TRAIN}/{v}_lr{lr}'


def check_trained(v, lr, epochs, milestones):
    d = traj_dir(v, lr)
    for e in milestones:
        if not os.path.exists(f'{d}/epoch_{e:02d}/val_ce.json') or not os.path.exists(f'{d}/epoch_{e:02d}/adapter.pt'):
            raise SystemExit(f'{d}: epoch {e} adapter/val_ce missing after training')
    if not os.path.exists(f'{d}/freeze_end.json'):
        raise SystemExit(f'{d}: freeze_end.json missing (training did not complete)')


def cmd_train(a):
    jobs = []
    for v in a.variants.split(','):
        for lr in LRS[v]:
            jobs.append({'name': f'train_{v}_{lr}_to{a.epochs}', 'log': f'{OUT}/logs/train_{v}_{lr}.log',
                         'cmd': [sys.executable, 'sp75_train.py', '--run-dir', traj_dir(v, lr), '--variant', v, '--lr', lr, '--epochs', str(a.epochs), '--workers', '2']})
    run_jobs(jobs, per_gpu=a.per_gpu, peak_gb=a.peak_gb, tag='train')
    for v in a.variants.split(','):
        for lr in LRS[v]:
            check_trained(v, lr, a.epochs, [e for e in (8, 16, 32) if e <= a.epochs])


def gen_cmd(v, split, positions, adapter, out, worker=0, lock=None):
    c = [sys.executable, 'sp75_gen.py', '--variant', v, '--split', split, '--positions', positions, '--adapter', adapter, '--out-dir', out, '--worker', str(worker)]
    return c + (['--lock', lock] if lock else [])


def expected_count(split):
    import sp75_data as D
    return sum(1 for r in D.load_manifest()['rows'] if r['split'] == split and not r['excluded'] and (split != 'V8' or r['position_set'] == 'supervised'))


def count_out(d):
    n, ids = 0, set()
    for f in os.listdir(d) if os.path.isdir(d) else []:
        if f.startswith('gen_worker') and f.endswith('.jsonl'):
            for ln in open(f'{d}/{f}'):
                if ln.strip():
                    ids.add(json.loads(ln)['id'])
                    n += 1
    return n, len(ids)


def cmd_gen_v8(a):
    jobs, outs = [], []
    sel = None
    for v in a.variants.split(','):
        lrs = LRS[v]
        if a.only_selected:
            sel = json.load(open(f'{OUT}/select_v8.json'))
            lrs = (sel['selected'][v],)
        for lr in lrs:
            for ep in a.epochs.split(','):
                ad = f'{traj_dir(v, lr)}/epoch_{int(ep):02d}'
                out = f'{GEN}/V8/{v}_lr{lr}_ep{int(ep):02d}'
                outs.append(out)
                jobs.append({'name': f'genV8_{v}_{lr}_{ep}', 'log': f'{OUT}/logs/genV8_{v}_{lr}_{ep}.log', 'cmd': gen_cmd(v, 'V8', 'supervised', ad, out)})
    run_jobs(jobs, per_gpu=a.per_gpu, peak_gb=a.peak_gb, tag='gen_v8')
    n = expected_count('V8')
    for o in outs:
        tot, uniq = count_out(o)
        if tot != n or uniq != n:
            raise SystemExit(f'{o}: {tot} records / {uniq} unique, expected {n}')


def cmd_extend(a):
    sel = json.load(open(f'{OUT}/select_v8.json'))
    jobs = []
    for v in ('F', 'R'):
        if sel['extend'][v]['extend_to_32']:
            lr = sel['selected'][v]
            jobs.append({'name': f'train_{v}_{lr}_to32', 'log': f'{OUT}/logs/train_{v}_{lr}_ext.log',
                         'cmd': [sys.executable, 'sp75_train.py', '--run-dir', traj_dir(v, lr), '--variant', v, '--lr', lr, '--epochs', '32', '--workers', '2']})
    if jobs:
        run_jobs(jobs, per_gpu=1, peak_gb=a.peak_gb, tag='extend')
        for v in ('F', 'R'):
            if sel['extend'][v]['extend_to_32']:
                check_trained(v, sel['selected'][v], 32, [32])


def cmd_gen_e24(a):
    lock = json.load(open(LOCK))
    jobs = []
    for name, v in lock['vlm'].items():
        ad = v.get('adapter_dir') or 'none'
        jobs.append({'name': f'genE24_{name}', 'log': f'{OUT}/logs/genE24_{name}.log', 'cmd': gen_cmd(v['variant'], 'E24', 'all', ad, v['dir'], lock=LOCK)})
    for s in ('C', 'H'):
        pass   # C/H 예측은 별도 CPU/GPU 소형 작업: 아래에서 순차 실행
    run_jobs(jobs, per_gpu=a.per_gpu, peak_gb=a.peak_gb, tag='gen_e24')
    n = expected_count('E24')
    for name, v in lock['vlm'].items():
        tot, uniq = count_out(v['dir'])
        if tot != n or uniq != n:
            raise SystemExit(f'{v["dir"]}: {tot}/{uniq}, expected {n}')
    g = gpus()[0]
    for s in ('C', 'H'):
        t0 = time.time()
        rc = subprocess.call([sys.executable, 'sp76_cpred.py', s, '--out', f'{OUT}/pred', '--lock', LOCK, '--gpu', g], stdout=open(f'{OUT}/logs/pred_{s}.log', 'a'), stderr=subprocess.STDOUT)
        open(LEDGER, 'a').write(json.dumps({'tag': 'pred', 'name': f'pred_{s}', 'gpu': g, 'rc': rc, 'wall_s': time.time() - t0}) + '\n')
        if rc != 0:
            raise SystemExit(f'pred {s} failed rc={rc}')


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='c', required=True)
    t = sp.add_parser('train'); t.add_argument('--epochs', type=int, default=16); t.add_argument('--variants', default='F,R'); t.add_argument('--per-gpu', type=int, default=1)
    t.add_argument('--peak-gb', type=float, default=11.5)
    g = sp.add_parser('gen_v8'); g.add_argument('--epochs', default='8,16'); g.add_argument('--variants', default='F,R'); g.add_argument('--per-gpu', type=int, default=2)
    g.add_argument('--peak-gb', type=float, default=10.0); g.add_argument('--only-selected', action='store_true')
    e = sp.add_parser('extend'); e.add_argument('--peak-gb', type=float, default=11.5)
    ge = sp.add_parser('gen_e24'); ge.add_argument('--per-gpu', type=int, default=2); ge.add_argument('--peak-gb', type=float, default=10.0)
    a = ap.parse_args()
    os.makedirs(f'{OUT}/logs', exist_ok=True)
    {'train': cmd_train, 'gen_v8': cmd_gen_v8, 'extend': cmd_extend, 'gen_e24': cmd_gen_e24}[a.c](a)


if __name__ == '__main__':
    main()
