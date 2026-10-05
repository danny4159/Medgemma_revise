"""iter_078 생성 launcher: cond별로(순차) GPU당 W개 worker를 띄워 같은 out-dir의 claim 큐를 공유한다.

- 허용 GPU는 상속된 CUDA_VISIBLE_DEVICES 안에서만 선택. 시작 직전 nvidia-smi 여유 + worker당 est GiB + 2GiB 여유를 확인한다.
- 모든 자식의 종료 코드·wall·nvidia-smi peak 점유(2초 sampling)를 launch_result 에 저장. 같은 tag의 기존 결과가 있으면 중단.
사용: python rf78_launch.py --split V8 --conds L,I,D --wpg 1 --gpus 0,1 --est-gb 10.5 --tag V8_main [--lock L] [--ids F] [--out-root D] [--max-requests N]
"""
import argparse, json, os, subprocess, sys, threading, time

ADAPTER = 'results/iter_077/train/R_lr2e-4/epoch_16'


def smi():
    out = subprocess.run(['nvidia-smi', '--query-gpu=index,uuid,memory.used,memory.total', '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True).stdout
    d = {}
    for ln in out.strip().splitlines():
        i, u, used, tot = [x.strip() for x in ln.split(',')]
        d[i] = {'uuid': u, 'used_mib': int(used), 'total_mib': int(tot)}
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--split', required=True)
    ap.add_argument('--conds', required=True)
    ap.add_argument('--wpg', type=int, default=1)
    ap.add_argument('--gpus', required=True)
    ap.add_argument('--est-gb', type=float, required=True)
    ap.add_argument('--tag', required=True)
    ap.add_argument('--out-root', default='results/iter_078/gen')
    ap.add_argument('--lock', default=None)
    ap.add_argument('--ids', default=None)
    ap.add_argument('--max-requests', type=int, default=None)
    ap.add_argument('--adapter', default=ADAPTER)
    a = ap.parse_args()
    inh = os.environ.get('CUDA_VISIBLE_DEVICES', '').split(',')
    gpus = a.gpus.split(',')
    for g in gpus:
        if g not in inh:
            sys.exit(f'gpu {g} not in inherited {inh}')
    res_path = f'{a.out_root}/{a.tag}/launch_result.json'
    if os.path.exists(res_path):
        sys.exit(f'{res_path} exists')
    os.makedirs(f'{a.out_root}/{a.tag}', exist_ok=True)
    before = smi()
    for g in gpus:
        phys = list(before.keys())[int(g)] if len(before) > int(g) else g
        free = before[phys]['total_mib'] - before[phys]['used_mib']
        need = a.wpg * (a.est_gb + 2.0) * 1024
        if need > free:
            sys.exit(f'admission failed gpu {g}: need {need:.0f} MiB free {free} MiB')
    result = {'args': vars(a), 'smi_before': before, 'conds': {}}
    peaks = {}
    stop = threading.Event()

    def sampler():
        while not stop.is_set():
            try:
                s = smi()
                for k, v in s.items():
                    peaks[k] = max(peaks.get(k, 0), v['used_mib'])
            except Exception:
                pass
            stop.wait(2.0)
    th = threading.Thread(target=sampler, daemon=True)
    th.start()
    t_all = time.time()
    for cond in a.conds.split(','):
        out_dir = f'{a.out_root}/{a.tag}/{cond}'
        procs = []
        t0 = time.time()
        w = 0
        for g in gpus:
            for _ in range(a.wpg):
                cmd = [sys.executable, 'rf78_gen.py', '--split', a.split, '--cond', cond, '--adapter', a.adapter, '--out-dir', out_dir, '--worker', str(w), '--gpu', g]
                if a.lock:
                    cmd += ['--lock', a.lock]
                if a.ids:
                    cmd += ['--ids', a.ids]
                if a.max_requests is not None:
                    cmd += ['--max-requests', str(a.max_requests)]
                os.makedirs(out_dir, exist_ok=True)
                lf = open(f'{out_dir}/worker{w}.stdout.log', 'ab')
                procs.append((w, g, subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT)))
                w += 1
        rcs = {str(w): p.wait() for w, g, p in procs}
        result['conds'][cond] = {'out_dir': out_dir, 'exit_codes': rcs, 'wall_s': time.time() - t0, 'workers': {str(w): g for w, g, p in procs}}
        if any(rcs.values()):
            break
    stop.set()
    th.join()
    result['wall_total_s'] = time.time() - t_all
    result['smi_peak_used_mib_by_physical_gpu'] = peaks
    json.dump(result, open(res_path, 'w'), indent=1)
    print(json.dumps({'rc': {c: v['exit_codes'] for c, v in result['conds'].items()}, 'wall': result['wall_total_s'], 'peaks': peaks}))
    sys.exit(1 if any(any(v['exit_codes'].values()) for v in result['conds'].values()) else 0)


if __name__ == '__main__':
    main()
