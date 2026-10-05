"""iter_075 실행 orchestration: 학습(4 trajectory) -> V8 생성 -> 선택/연장 -> E24 생성. 단계별 CLI. 모든 작업은 results/iter_075 아래에만 쓴다.

GPU 배정은 상속된 CUDA_VISIBLE_DEVICES 안에서만 한다. 작업 시작 직전 nvidia-smi 여유 메모리가 (예상 peak + 2GiB)보다 작으면 대기한다.
ledger: results/iter_075/ledger.jsonl (모든 subprocess의 명령·GPU·wall·rc를 append).
"""
import argparse, json, os, subprocess, sys, time

OUT = 'results/iter_075'
LEDGER = f'{OUT}/ledger.jsonl'
TRAIN = f'{OUT}/train'
GEN = f'{OUT}/gen'
LRS = {'F': ('2e-5', '2e-4'), 'R': ('2e-5', '2e-4')}


def gpus():
    return os.environ.get('CUDA_VISIBLE_DEVICES', '0,1').split(',')


def free_mib():
    out = subprocess.check_output(['nvidia-smi', '--query-gpu=index,uuid,memory.used,memory.total', '--format=csv,noheader,nounits']).decode().strip().splitlines()
    res = {}
    for ln in out:
        i, u, used, tot = [x.strip() for x in ln.split(',')]
        res[i] = (int(tot) - int(used), u)
    return res


def run_jobs(jobs, per_gpu, peak_gb, tag):
    """jobs: [{'name','cmd'(list without --gpu),'gpu_ok'}]. 각 GPU에 최대 per_gpu개 동시, 메모리 여유 확인."""
    g = gpus()
    running, pending, results = {}, list(jobs), []
    while pending or running:
        for k, (p, j, gid, t0) in list(running.items()):
            rc = p.poll()
            if rc is not None:
                rec = {'tag': tag, 'name': j['name'], 'cmd': j['cmd'], 'gpu': gid, 'rc': rc, 'wall_s': time.time() - t0, 'ts_end': time.time()}
                open(LEDGER, 'a').write(json.dumps(rec) + '\n')
                results.append(rec)
                del running[k]
        for gid in g:
            if not pending:
                break
            n_on = sum(1 for (_, _, gg, _) in running.values() if gg == gid)
            if n_on >= per_gpu:
                continue
            fm = free_mib().get(gid, (0, None))[0]
            if fm < (peak_gb + 2) * 1024:
                continue
            j = pending.pop(0)
            os.makedirs(os.path.dirname(j['log']), exist_ok=True)
            p = subprocess.Popen(j['cmd'] + ['--gpu', gid], stdout=open(j['log'], 'a'), stderr=subprocess.STDOUT)
            running[j['name']] = (p, j, gid, time.time())
            time.sleep(25)  # 메모리 점유가 올라올 시간을 준다
        time.sleep(5)
    bad = [r for r in results if r['rc'] != 0]
    if bad:
        raise SystemExit(f'jobs failed: {[(r["name"], r["rc"]) for r in bad]}')
    return results


def traj_dir(v, lr):
    return f'{TRAIN}/{v}_lr{lr}'


def cmd_train(a):
    jobs = []
    for v in ('F', 'R'):
        for lr in LRS[v]:
            jobs.append({'name': f'train_{v}_{lr}', 'log': f'{OUT}/logs/train_{v}_{lr}.log',
                         'cmd': [sys.executable, 'sp75_train.py', '--run-dir', traj_dir(v, lr), '--variant', v, '--lr', lr, '--epochs', str(a.epochs), '--workers', '2']})
    run_jobs(jobs, per_gpu=1, peak_gb=11.5, tag='train')


def gen_cmd(v, split, positions, adapter, out, worker=0):
    return [sys.executable, 'sp75_gen.py', '--variant', v, '--split', split, '--positions', positions, '--adapter', adapter, '--out-dir', out, '--worker', str(worker)]


def cmd_gen_v8(a):
    jobs = []
    for v in ('F', 'R'):
        for lr in LRS[v]:
            for ep in a.epochs.split(','):
                ad = f'{traj_dir(v, lr)}/epoch_{int(ep):02d}'
                out = f'{GEN}/V8/{v}_lr{lr}_ep{int(ep):02d}'
                jobs.append({'name': f'genV8_{v}_{lr}_{ep}', 'log': f'{OUT}/logs/genV8_{v}_{lr}_{ep}.log', 'cmd': gen_cmd(v, 'V8', 'supervised', ad, out)})
    run_jobs(jobs, per_gpu=a.per_gpu, peak_gb=a.peak_gb, tag='gen_v8')


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='c', required=True)
    t = sp.add_parser('train'); t.add_argument('--epochs', type=int, default=16)
    g = sp.add_parser('gen_v8'); g.add_argument('--epochs', default='8,16'); g.add_argument('--per-gpu', type=int, default=1); g.add_argument('--peak-gb', type=float, default=10.0)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    {'train': cmd_train, 'gen_v8': cmd_gen_v8}[a.c](a)


if __name__ == '__main__':
    main()
